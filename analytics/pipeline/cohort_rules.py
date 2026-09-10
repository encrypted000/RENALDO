"""
cohort_rules.py
----------------
Pure, config-driven rules for per-cohort behaviour — no DB access, so these
are fully unit-testable. Cohort names are matched case-insensitively with
surrounding whitespace stripped, since that's how they arrive from the
database (config/cohorts.py stores the canonical display form).
"""
from config.cohorts import NO_PRE_KRT_FOLLOWUP_COHORTS, NO_BIOCHEMISTRY_COHORTS


def _normalise(name: str) -> str:
    return name.strip().lower()


def is_closed_cohort(db_name: str) -> bool:
    """RaDaR convention: a cohort no longer recruiting has a "z " name prefix."""
    return db_name.lower().startswith("z ")


def should_skip_pre_krt(db_name: str) -> bool:
    return _normalise(db_name) in {_normalise(n) for n in NO_PRE_KRT_FOLLOWUP_COHORTS}


def should_skip_biochemistry(db_name: str) -> bool:
    return _normalise(db_name) in {_normalise(n) for n in NO_BIOCHEMISTRY_COHORTS}
