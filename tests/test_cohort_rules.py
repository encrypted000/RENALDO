"""
test_cohort_rules.py
---------------------
Unit tests for analytics/pipeline/cohort_rules.py — the config-driven,
per-cohort name-matching rules (closed cohorts, pre-KRT/biochemistry
exclusions). No DB needed.

Run with: python -m pytest tests/test_cohort_rules.py -v
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics.pipeline.cohort_rules import (
    is_closed_cohort,
    should_skip_pre_krt,
    should_skip_biochemistry,
    biopsy_types_shown,
    unmatched_biopsy_rule_names,
)
from config.cohorts import NO_BIOPSY_COHORTS, BIOPSY_TRANSPLANT_ONLY_COHORTS


def test_closed_cohort_detected_by_z_prefix():
    assert is_closed_cohort("z Old Cohort Name") is True


def test_closed_cohort_case_insensitive():
    assert is_closed_cohort("Z Old Cohort Name") is True


def test_open_cohort_not_flagged_closed():
    assert is_closed_cohort("Alport Syndrome") is False


def test_z_prefix_without_space_is_not_closed():
    # "Z" must be a standalone word prefix ("z "), not just any name starting with Z
    assert is_closed_cohort("Zellweger Syndrome") is False


def test_cmv_post_transplant_skips_pre_krt():
    assert should_skip_pre_krt("CMV Post Transplant") is True


def test_bk_nephropathy_skips_pre_krt():
    assert should_skip_pre_krt("BK Nephropathy") is True


def test_pre_krt_match_is_case_and_whitespace_insensitive():
    assert should_skip_pre_krt("  cmv post transplant  ") is True


def test_other_cohorts_get_pre_krt():
    assert should_skip_pre_krt("Alport Syndrome") is False


def test_cmv_post_transplant_skips_biochemistry():
    assert should_skip_biochemistry("CMV Post Transplant") is True


def test_bk_nephropathy_skips_biochemistry():
    assert should_skip_biochemistry("BK Nephropathy") is True


def test_other_cohorts_get_biochemistry():
    assert should_skip_biochemistry("Alport Syndrome") is False


def test_default_cohort_shows_both_biopsy_types():
    assert biopsy_types_shown("Alport Syndrome") == ("native", "transplant")


def test_transplant_only_cohort_case_insensitive():
    assert biopsy_types_shown("  cystinosis ") == ("transplant",)


def test_no_biopsy_cohort_shows_nothing():
    assert biopsy_types_shown("Calciphylaxis") == ()


def test_biopsy_rule_lists_do_not_overlap():
    no_bx = {n.lower() for n in NO_BIOPSY_COHORTS}
    assert not no_bx & {n.lower() for n in BIOPSY_TRANSPLANT_ONLY_COHORTS}


def test_unmatched_biopsy_rule_names_flags_missing_cohorts():
    all_configured = list(NO_BIOPSY_COHORTS + BIOPSY_TRANSPLANT_ONLY_COHORTS)
    assert unmatched_biopsy_rule_names(all_configured) == []
    assert unmatched_biopsy_rule_names(all_configured[1:]) == [all_configured[0]]
