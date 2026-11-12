"""
biopsies.py
------------
Pure calculation for the renal biopsy rows of the "Lab Results Metadata"
section — native vs transplant biopsies per cohort, across all dates.
No DB access: takes the pathology records plus each patient's first
transplant date. Fully unit-testable with synthetic data, see
tests/test_biopsies.py.

Rules (agreed with UKKA, Nov 2026):
  - NATIVE -> native; TRANSPLANT and TIME ZERO TRANSPLANT -> transplant.
    A labelled record keeps its label whatever its date.
  - Blank kidney_type is inferred from the patient's first transplant date:
    before it, or no transplant recorded -> native; on or after it -> transplant.
  - One biopsy per patient per date per type, so a biopsy entered twice
    (or as both TRANSPLANT and TIME ZERO TRANSPLANT) counts once.
"""
import pandas as pd

NATIVE_LABELS     = {"NATIVE"}
TRANSPLANT_LABELS = {"TRANSPLANT", "TIME ZERO TRANSPLANT"}
BIOPSY_TYPES      = ("native", "transplant")


def classify_biopsies(biopsies_df: pd.DataFrame, first_tx_map: dict) -> pd.DataFrame:
    """
    One row per patient per biopsy date per type, with columns
    patient_id, biopsy_date, biopsy_type ("native"/"transplant") and
    inferred (True where the type came from the transplant date).
    """
    columns = ["patient_id", "biopsy_date", "biopsy_type", "inferred"]
    if biopsies_df.empty:
        return pd.DataFrame(columns=columns)

    df = biopsies_df.copy()
    df["biopsy_date"] = pd.to_datetime(df["biopsy_date"], errors="coerce").dt.normalize()
    df = df[df["biopsy_date"].notna()]

    label    = df["kidney_type"].fillna("").astype(str).str.strip().str.upper()
    first_tx = pd.to_datetime(df["patient_id"].map(first_tx_map), errors="coerce")
    after_tx = first_tx.notna() & (df["biopsy_date"] >= first_tx)

    df["inferred"]    = ~label.isin(NATIVE_LABELS | TRANSPLANT_LABELS)
    df["biopsy_type"] = "native"
    df.loc[label.isin(TRANSPLANT_LABELS), "biopsy_type"] = "transplant"
    df.loc[df["inferred"] & after_tx,     "biopsy_type"] = "transplant"

    # A date counts as inferred only if no labelled record backs it up
    return (
        df.groupby(["patient_id", "biopsy_date", "biopsy_type"], as_index=False)["inferred"]
          .all()[columns]
    )


def summarise_biopsies(classified: pd.DataFrame, cohort_pids: set, patient_count: int) -> dict:
    """Per type: patients with >=1 biopsy, cohort size, and total biopsies."""
    in_cohort = classified[classified["patient_id"].isin(cohort_pids)]
    stats = {}
    for biopsy_type in BIOPSY_TYPES:
        rows = in_cohort[in_cohort["biopsy_type"] == biopsy_type]
        stats[biopsy_type] = {
            "count":          int(rows["patient_id"].nunique()),
            "total":          int(patient_count),
            "total_biopsies": int(len(rows)),
        }
    return stats
