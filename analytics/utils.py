import logging
import os
import pandas as pd

# ── Logging setup ──
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/radar.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def calc_pct_missing(series: pd.Series) -> float:
    """
    Calculate % missing — catches both NULL and empty/whitespace strings.
    A value is considered missing if it is:
      - NULL (NaN in pandas)
      - Empty string ""
      - Whitespace only e.g. "   "
    """
    if len(series) == 0:
        return 0.0

    missing = series.isna() | (series.astype(str).str.strip() == "")

    # Exclude 'nan' string that appears when NaN is cast to str
    # e.g. pd.Series([None]).astype(str) gives "nan" not ""
    # So we must treat "nan" as missing too
    missing = missing | (series.astype(str).str.lower() == "nan")

    return round(missing.sum() / len(series) * 100, 1)


def calc_pct_missing_email(series: pd.Series, default_emails: list) -> float:
    """Calculate % missing for email — null OR in the default email list."""
    if len(series) == 0:
        return 0.0
    missing = series.isna() | series.isin(default_emails)
    return round(missing.sum() / len(series) * 100, 1)


def calc_pct_not_in(main_ids: pd.Series, lookup_ids: set) -> float:
    """Calculate % of patient IDs in main that are NOT in lookup set."""
    if len(main_ids) == 0:
        return 0.0
    missing = ~main_ids.isin(lookup_ids)
    return round(missing.sum() / len(main_ids) * 100, 1)


def get_valid_patient_ids(engine) -> list:
    """Return list of valid patient IDs — excludes test and control patients."""
    df = pd.read_sql(
        """
        SELECT id
        FROM patients
        WHERE (test    IS NULL OR test    = FALSE)
          AND (control IS NULL OR control = FALSE)
        """,
        engine,
    )
    logger.info(f"Valid patients loaded: {len(df)}")
    return df["id"].tolist()


def build_result(var: dict, missing: int, total: int) -> dict:
    """Build a standard result dict for one variable."""
    pct = round(missing / total * 100, 1) if total > 0 else 0.0
    return {
        "id":          var["id"],
        "name":        var["name"],
        "pct_missing": pct,
        "missing":     int(missing),
        "total":       total,
        "required":    var["required"],
        "desc":        var["desc"],
    }
