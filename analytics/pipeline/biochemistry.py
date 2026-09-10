"""
biochemistry.py
----------------
Pure calculation for the "Biochemistry Metadata Prior to Kidney Replacement
Therapy" section — per-patient result counts and first-result timing,
relative to each patient's own cutoff (their KRT date if reached, else
today). No DB access: takes a results dataframe (one row per patient per
day with a qualifying result) plus a patient set and a cutoff map, and
returns per-patient Series that the caller reindexes per cohort — same
pattern as follow_up.py. Fully unit-testable with synthetic data, see
tests/test_biochemistry.py.
"""
import pandas as pd


def _pre_cutoff(days_df: pd.DataFrame, patient_ids: set, cutoff_map: dict) -> pd.DataFrame:
    """Rows for the given patients, before each patient's own cutoff date."""
    df = days_df[days_df["patient_id"].isin(patient_ids)].copy()
    df["cutoff"] = df["patient_id"].map(cutoff_map)
    return df[df["result_date"] < df["cutoff"]]


def counts_per_patient(days_df: pd.DataFrame, patient_ids: set, cutoff_map: dict) -> pd.Series:
    """Number of pre-cutoff results per patient. A patient with zero
    qualifying results is absent from the result, not present as zero."""
    pre_cutoff = _pre_cutoff(days_df, patient_ids, cutoff_map)
    if pre_cutoff.empty:
        return pd.Series(dtype=int)
    return pre_cutoff.groupby("patient_id").size()


def years_to_cutoff_per_patient(days_df: pd.DataFrame, patient_ids: set, cutoff_map: dict) -> pd.Series:
    """
    Years from each patient's FIRST pre-cutoff result to their cutoff
    (their KRT date if reached, else today). A patient with no pre-cutoff
    result is absent from the result, not zero.
    """
    pre_cutoff = _pre_cutoff(days_df, patient_ids, cutoff_map)
    if pre_cutoff.empty:
        return pd.Series(dtype=float)
    first_date = pre_cutoff.groupby("patient_id")["result_date"].min()
    cutoffs = pd.Series(cutoff_map).reindex(first_date.index)
    return (cutoffs - first_date).dt.days / 365.25


def summarise_counts(counts: pd.Series) -> dict:
    """Median/IQR number of results per patient, among patients with >=1."""
    nonzero = counts.dropna()
    nonzero = nonzero[nonzero >= 1]
    if len(nonzero) == 0:
        return {"n_patients": 0, "total_results": 0, "median": 0, "q1": 0, "q3": 0}
    return {
        "n_patients":    int(len(nonzero)),
        "total_results": int(nonzero.sum()),
        "median":        round(nonzero.median(), 1),
        "q1":            round(nonzero.quantile(0.25), 1),
        "q3":            round(nonzero.quantile(0.75), 1),
    }


def summarise_years_to_cutoff(years: pd.Series) -> dict:
    """Median/IQR/count of valid (non-negative) years-to-cutoff values."""
    valid = years.dropna()
    valid = valid[valid >= 0]
    if len(valid) == 0:
        return {"median": 0.0, "q1": 0.0, "q3": 0.0, "count": 0}
    return {
        "median": round(valid.median(), 1),
        "q1":     round(valid.quantile(0.25), 1),
        "q3":     round(valid.quantile(0.75), 1),
        "count":  int(len(valid)),
    }
