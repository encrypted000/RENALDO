"""
follow_up.py
------------
Pure calculation logic for the two follow-up metrics shown on the
dashboard — Overall follow-up and Follow-up pre-KRT. No DB access here:
everything takes dataframes/series in and returns computed results out,
so this is fully unit-testable with synthetic data — see
tests/test_follow_up.py.
"""
import pandas as pd


def start_date(diagnosis_date: pd.Series, entry_date: pd.Series) -> pd.Series:
    """Diagnosis date, falling back to cohort entry (recruitment date) when
    no diagnosis date is recorded."""
    return diagnosis_date.fillna(entry_date)


def _summarise(years: pd.Series) -> dict:
    """Median/IQR/count over valid (non-negative) follow-up years."""
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


def overall_follow_up(df: pd.DataFrame, today: pd.Timestamp, group_col: str = None):
    """
    Overall follow-up: start_date -> death or today. Withdrawn patients are
    excluded from the population entirely (not censored at their withdrawal
    date), so the count = population size - withdrawn, not lower.

    df must have columns: start_date, date_of_death, withdrawal_date
    (+ group_col if grouping per-cohort).

    Returns (enriched_df, stats):
      - enriched_df is the non-withdrawn population with "_end"/"_years"
        columns added. A negative "_years" value is a data error (start
        date fell after the follow-up end date) — the caller should warn
        on these, they are not an expected exclusion.
      - stats is a dict (group_col=None) or {group_value: dict}.
    """
    pop = df[df["withdrawal_date"].isna()].copy()
    if pop.empty:
        return pop, ({} if group_col else _summarise(pd.Series(dtype=float)))
    pop["_end"]   = pop["date_of_death"].fillna(today)
    pop["_years"] = (pop["_end"] - pop["start_date"]).dt.days / 365.25

    if group_col is None:
        return pop, _summarise(pop["_years"])
    stats = {g: _summarise(sub["_years"]) for g, sub in pop.groupby(group_col)}
    return pop, stats


def pre_krt_follow_up(df: pd.DataFrame, today: pd.Timestamp, group_col: str = None):
    """
    Follow-up pre-KRT: start_date -> earliest of KRT (kidney failure) date,
    death, or today. Withdrawn patients excluded. A patient already at/past
    KRT by their start date (diagnosis or cohort entry) gets a negative
    window, which _summarise() drops from the count — this is an expected
    outcome (they started KRT before diagnosis/recruitment), not a data
    error, so unlike overall_follow_up() the caller should not warn on it.

    df must have columns: start_date, date_of_death, withdrawal_date, kf_date
    (+ group_col if grouping per-cohort). Returns (enriched_df, stats) with
    the same shape as overall_follow_up().
    """
    pop = df[df["withdrawal_date"].isna()].copy()
    if pop.empty:
        return pop, ({} if group_col else _summarise(pd.Series(dtype=float)))
    pop["_end"] = pop.apply(
        lambda r: min([d for d in [today, r["date_of_death"], r["kf_date"]] if pd.notna(d)]),
        axis=1,
    )
    pop["_years"] = (pop["_end"] - pop["start_date"]).dt.days / 365.25

    if group_col is None:
        return pop, _summarise(pop["_years"])
    stats = {g: _summarise(sub["_years"]) for g, sub in pop.groupby(group_col)}
    return pop, stats
