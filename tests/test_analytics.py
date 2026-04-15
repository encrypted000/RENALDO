"""
test_analytics.py
------------------
Unit tests for analytics/utils.py calculation functions.
Run with: python -m pytest tests/
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import pytest
from analytics.utils import (
    calc_pct_missing,
    calc_pct_missing_email,
    calc_pct_not_in,
    build_result,
)


# ── calc_pct_missing ──

def test_pct_missing_all_null():
    s = pd.Series([None, None, None])
    assert calc_pct_missing(s) == 100.0

def test_pct_missing_none_null():
    s = pd.Series([1, 2, 3])
    assert calc_pct_missing(s) == 0.0

def test_pct_missing_half_null():
    s = pd.Series([1, None, 2, None])
    assert calc_pct_missing(s) == 50.0

def test_pct_missing_empty_series():
    s = pd.Series([], dtype=object)
    assert calc_pct_missing(s) == 0.0

def test_pct_missing_rounds_to_one_decimal():
    # 1 out of 3 = 33.333...% → should round to 33.3
    s = pd.Series([None, 1, 2])
    assert calc_pct_missing(s) == 33.3


# ── calc_pct_missing_email ──

DEFAULT_EMAILS = ["radar@radar.org", "noemail@radar.radar"]

def test_email_all_default():
    s = pd.Series(["radar@radar.org", "noemail@radar.radar"])
    assert calc_pct_missing_email(s, DEFAULT_EMAILS) == 100.0

def test_email_none_missing():
    s = pd.Series(["real@email.com", "another@nhs.uk"])
    assert calc_pct_missing_email(s, DEFAULT_EMAILS) == 0.0

def test_email_null_counts_as_missing():
    s = pd.Series([None, "real@email.com"])
    assert calc_pct_missing_email(s, DEFAULT_EMAILS) == 50.0

def test_email_mix():
    s = pd.Series(["real@email.com", "radar@radar.org", None, "another@nhs.uk"])
    assert calc_pct_missing_email(s, DEFAULT_EMAILS) == 50.0


# ── calc_pct_not_in ──

def test_not_in_all_missing():
    ids = pd.Series([1, 2, 3])
    lookup = set()
    assert calc_pct_not_in(ids, lookup) == 100.0

def test_not_in_none_missing():
    ids = pd.Series([1, 2, 3])
    lookup = {1, 2, 3}
    assert calc_pct_not_in(ids, lookup) == 0.0

def test_not_in_half_missing():
    ids = pd.Series([1, 2, 3, 4])
    lookup = {1, 2}
    assert calc_pct_not_in(ids, lookup) == 50.0

def test_not_in_empty():
    ids = pd.Series([], dtype=int)
    lookup = {1, 2, 3}
    assert calc_pct_not_in(ids, lookup) == 0.0


# ── build_result ──

def test_build_result_structure():
    var = {"id": "D.1", "name": "TEST", "required": True, "desc": "Test variable"}
    result = build_result(var, missing=10, total=100)
    assert result["id"]          == "D.1"
    assert result["name"]        == "TEST"
    assert result["pct_missing"] == 10.0
    assert result["missing"]     == 10
    assert result["total"]       == 100
    assert result["required"]    is True

def test_build_result_zero_total():
    var = {"id": "D.1", "name": "TEST", "required": True, "desc": "Test"}
    result = build_result(var, missing=0, total=0)
    assert result["pct_missing"] == 0.0

def test_build_result_full_missing():
    var = {"id": "D.1", "name": "TEST", "required": True, "desc": "Test"}
    result = build_result(var, missing=500, total=500)
    assert result["pct_missing"] == 100.0
