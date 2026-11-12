"""
test_biopsies.py
-----------------
Unit tests for analytics/pipeline/biopsies.py — renal biopsy type
classification and per-cohort counts. No DB needed; synthetic data only.

Run with: python -m pytest tests/test_biopsies.py -v
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import pytest
from analytics.pipeline.biopsies import classify_biopsies, summarise_biopsies

FIRST_TX = pd.Timestamp("2020-01-01")


def _biopsy(patient_id, date, kidney_type):
    return {"patient_id": patient_id, "biopsy_date": pd.Timestamp(date), "kidney_type": kidney_type}


def _types(classified, patient_id):
    return sorted(classified[classified["patient_id"] == patient_id]["biopsy_type"])


# ── Labelled records keep their label ──

def test_labelled_native_stays_native_even_after_transplant():
    df = pd.DataFrame([_biopsy(1, "2021-01-01", "NATIVE")])
    out = classify_biopsies(df, {1: FIRST_TX})
    assert _types(out, 1) == ["native"]
    assert not out["inferred"].any()


def test_labelled_transplant_stays_transplant_without_transplant_record():
    df = pd.DataFrame([_biopsy(1, "2015-01-01", "TRANSPLANT")])
    out = classify_biopsies(df, {})
    assert _types(out, 1) == ["transplant"]


def test_time_zero_counts_as_transplant():
    df = pd.DataFrame([_biopsy(1, "2020-01-01", "TIME ZERO TRANSPLANT")])
    out = classify_biopsies(df, {1: FIRST_TX})
    assert _types(out, 1) == ["transplant"]


# ── Blank type is inferred from the first transplant date ──

@pytest.mark.parametrize("date, first_tx, expected", [
    ("2015-01-01", None,       "native"),      # no transplant recorded
    ("2019-12-31", FIRST_TX,   "native"),      # before first transplant
    ("2020-01-01", FIRST_TX,   "transplant"),  # on first transplant date
    ("2022-06-01", FIRST_TX,   "transplant"),  # after first transplant
])
def test_blank_type_inferred_from_first_transplant(date, first_tx, expected):
    df = pd.DataFrame([_biopsy(1, date, None)])
    first_tx_map = {1: first_tx} if first_tx is not None else {}
    out = classify_biopsies(df, first_tx_map)
    assert _types(out, 1) == [expected]
    assert out["inferred"].all()


def test_empty_string_type_treated_as_blank():
    df = pd.DataFrame([_biopsy(1, "2022-06-01", "  ")])
    out = classify_biopsies(df, {1: FIRST_TX})
    assert _types(out, 1) == ["transplant"]
    assert out["inferred"].all()


# ── One biopsy per patient per date per type ──

def test_duplicate_entries_on_same_date_count_once():
    df = pd.DataFrame([
        _biopsy(1, "2018-03-01", "NATIVE"),
        _biopsy(1, "2018-03-01", "NATIVE"),
    ])
    assert len(classify_biopsies(df, {})) == 1


def test_transplant_and_time_zero_on_same_date_count_once():
    df = pd.DataFrame([
        _biopsy(1, "2020-01-01", "TRANSPLANT"),
        _biopsy(1, "2020-01-01", "TIME ZERO TRANSPLANT"),
    ])
    assert len(classify_biopsies(df, {1: FIRST_TX})) == 1


def test_time_of_day_does_not_split_a_date():
    df = pd.DataFrame([
        _biopsy(1, "2018-03-01 09:00", "NATIVE"),
        _biopsy(1, "2018-03-01 15:30", "NATIVE"),
    ])
    assert len(classify_biopsies(df, {})) == 1


def test_native_and_transplant_on_same_date_both_count():
    df = pd.DataFrame([
        _biopsy(1, "2020-01-01", "NATIVE"),
        _biopsy(1, "2020-01-01", "TRANSPLANT"),
    ])
    assert _types(classify_biopsies(df, {1: FIRST_TX}), 1) == ["native", "transplant"]


# ── Per-cohort summary ──

@pytest.fixture
def classified():
    df = pd.DataFrame([
        _biopsy(1, "2015-01-01", "NATIVE"),
        _biopsy(1, "2016-01-01", "NATIVE"),
        _biopsy(1, "2021-01-01", "TRANSPLANT"),
        _biopsy(2, "2017-01-01", None),          # inferred native
        _biopsy(3, "2019-01-01", "NATIVE"),      # patient 3 not in the cohort
    ])
    return classify_biopsies(df, {1: FIRST_TX})


def test_summarise_counts_patients_and_biopsies_in_cohort_only(classified):
    stats = summarise_biopsies(classified, {1, 2, 4}, patient_count=3)
    assert stats["native"] == {"count": 2, "total": 3, "total_biopsies": 3}
    assert stats["transplant"] == {"count": 1, "total": 3, "total_biopsies": 1}


def test_summarise_cohort_with_no_biopsies(classified):
    stats = summarise_biopsies(classified, {99}, patient_count=1)
    assert stats["native"] == {"count": 0, "total": 1, "total_biopsies": 0}
    assert stats["transplant"] == {"count": 0, "total": 1, "total_biopsies": 0}


def test_classify_empty_input():
    empty = pd.DataFrame(columns=["patient_id", "biopsy_date", "kidney_type"])
    out = classify_biopsies(empty, {})
    assert out.empty
    stats = summarise_biopsies(out, {1}, patient_count=1)
    assert stats["native"]["count"] == 0
