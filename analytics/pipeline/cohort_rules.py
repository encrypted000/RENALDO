"""
cohort_rules.py
----------------
Pure, config-driven rules for per-cohort behaviour — no DB access, so these
are fully unit-testable. Cohort names are matched case-insensitively with
surrounding whitespace stripped, since that's how they arrive from the
database (config/cohorts.py stores the canonical display form).
"""
from config.cohorts import (
    NO_PRE_KRT_FOLLOWUP_COHORTS,
    NO_BIOCHEMISTRY_COHORTS,
    NO_BIOPSY_COHORTS,
    BIOPSY_TRANSPLANT_ONLY_COHORTS,
)


def _normalise(name: str) -> str:
    return name.strip().lower()


def is_closed_cohort(db_name: str) -> bool:
    """RaDaR convention: a cohort no longer recruiting has a "z " name prefix."""
    return db_name.lower().startswith("z ")


def should_skip_pre_krt(db_name: str) -> bool:
    return _normalise(db_name) in {_normalise(n) for n in NO_PRE_KRT_FOLLOWUP_COHORTS}


def should_skip_biochemistry(db_name: str) -> bool:
    return _normalise(db_name) in {_normalise(n) for n in NO_BIOCHEMISTRY_COHORTS}


def biopsy_types_shown(db_name: str) -> tuple:
    """Which biopsy types this cohort publishes: both, transplant only, or none."""
    name = _normalise(db_name)
    if name in {_normalise(n) for n in NO_BIOPSY_COHORTS}:
        return ()
    if name in {_normalise(n) for n in BIOPSY_TRANSPLANT_ONLY_COHORTS}:
        return ("transplant",)
    return ("native", "transplant")


def unmatched_biopsy_rule_names(db_names) -> list:
    """Configured biopsy-rule cohort names that match no cohort in the DB —
    a typo here would silently publish figures UKKA asked to leave out."""
    known = {_normalise(n) for n in db_names}
    return [n for n in NO_BIOPSY_COHORTS + BIOPSY_TRANSPLANT_ONLY_COHORTS
            if _normalise(n) not in known]
