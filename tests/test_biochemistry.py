"""
test_biochemistry.py
---------------------
Unit tests for analytics/pipeline/biochemistry.py — the "Biochemistry
Metadata Prior to Kidney Replacement Therapy" calculations. No DB needed.

Run with: python -m pytest tests/test_biochemistry.py -v
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import pytest
from analytics.pipeline.biochemistry import (
    counts_per_patient,
    years_to_cutoff_per_patient,
    summarise_counts,
    summarise_years_to_cutoff,
)

TODAY = pd.Timestamp("2026-09-10")


def _result(patient_id, date):
    return {"patient_id": patient_id, "result_date": pd.Timestamp(date)}


@pytest.fixture
def days_df():
    return pd.DataFrame([
        # patient 1: three results, all before their KRT cutoff (2020-01-01)
        _result(1, "2015-01-01"),
        _result(1, "2016-01-01"),
        _result(1, "2019-06-01"),
        # patient 2: one result after cutoff (today, not yet reached KRT) -> counts
        _result(2, "2022-01-01"),
        # patient 3: one result AFTER their KRT date -> excluded (not pre-cutoff)
        _result(3, "2021-01-01"),
        # patient 4: no results at all (not in this dataframe)
    ])


@pytest.fixture
def cutoff_map():
    return {
        1: pd.Timestamp("2020-01-01"),  # reached KRT
        2: TODAY,                        # not yet reached KRT -> cutoff = today
        3: pd.Timestamp("2020-01-01"),  # reached KRT before their only result
        4: TODAY,
    }


def test_counts_per_patient_excludes_post_cutoff_results(days_df, cutoff_map):
    counts = counts_per_patient(days_df, {1, 2, 3, 4}, cutoff_map)
    assert counts.to_dict() == {1: 3, 2: 1}
    assert 3 not in counts.index  # only result was after cutoff
    assert 4 not in counts.index  # no results at all


def test_summarise_counts_median_and_total():
    counts = pd.Series({1: 3, 2: 1, 3: 2})
    stats = summarise_counts(counts)
    assert stats["n_patients"] == 3
    assert stats["total_results"] == 6
    assert stats["median"] == 2


def test_summarise_counts_empty():
    stats = summarise_counts(pd.Series(dtype=int))
    assert stats == {"n_patients": 0, "total_results": 0, "median": 0, "q1": 0, "q3": 0}


def test_years_to_cutoff_uses_first_result(days_df, cutoff_map):
    years = years_to_cutoff_per_patient(days_df, {1, 2, 3, 4}, cutoff_map)
    expected_1 = (pd.Timestamp("2020-01-01") - pd.Timestamp("2015-01-01")).days / 365.25
    assert years[1] == pytest.approx(expected_1)


def test_years_to_cutoff_excludes_patients_with_no_pre_cutoff_result(days_df, cutoff_map):
    years = years_to_cutoff_per_patient(days_df, {1, 2, 3, 4}, cutoff_map)
    assert 3 not in years.index
    assert 4 not in years.index


def test_summarise_years_to_cutoff_drops_negative():
    years = pd.Series({1: 2.0, 2: -1.0, 3: 4.0})
    stats = summarise_years_to_cutoff(years)
    assert stats["count"] == 2
    assert stats["median"] == pytest.approx(3.0)


def test_summarise_years_to_cutoff_empty():
    stats = summarise_years_to_cutoff(pd.Series(dtype=float))
    assert stats == {"median": 0.0, "q1": 0.0, "q3": 0.0, "count": 0}


def test_empty_days_df_does_not_error():
    empty = pd.DataFrame(columns=["patient_id", "result_date"])
    counts = counts_per_patient(empty, {1, 2}, {1: TODAY, 2: TODAY})
    years = years_to_cutoff_per_patient(empty, {1, 2}, {1: TODAY, 2: TODAY})
    assert len(counts) == 0
    assert len(years) == 0
