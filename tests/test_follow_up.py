"""
test_follow_up.py
------------------
Unit tests for analytics/pipeline/follow_up.py — Overall follow-up and
Follow-up pre-KRT. No DB needed; everything runs against synthetic patient
rows so the withdrawn-exclusion, cohort-entry-fallback, and negative-window
rules can be checked precisely.

Run with: python -m pytest tests/test_follow_up.py -v
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import pytest
from analytics.pipeline.follow_up import start_date, overall_follow_up, pre_krt_follow_up

TODAY = pd.Timestamp("2026-09-10")


def _row(patient_id, diagnosis_date=None, enrolled=None, date_of_death=None,
         withdrawal_date=None, kf_date=None):
    return dict(
        patient_id=patient_id,
        diagnosis_date=pd.Timestamp(diagnosis_date) if diagnosis_date else pd.NaT,
        enrolled=pd.Timestamp(enrolled) if enrolled else pd.NaT,
        date_of_death=pd.Timestamp(date_of_death) if date_of_death else pd.NaT,
        withdrawal_date=pd.Timestamp(withdrawal_date) if withdrawal_date else pd.NaT,
        kf_date=pd.Timestamp(kf_date) if kf_date else pd.NaT,
    )


@pytest.fixture
def patients():
    df = pd.DataFrame([
        # 1: normal, alive, has a diagnosis date
        _row(1, diagnosis_date="2015-01-01", enrolled="2016-01-01"),
        # 2: no diagnosis date -> falls back to cohort entry
        _row(2, diagnosis_date=None, enrolled="2018-06-01"),
        # 3: deceased -> end = death date
        _row(3, diagnosis_date="2010-01-01", enrolled="2011-01-01", date_of_death="2020-01-01"),
        # 4: withdrawn -> excluded entirely from both metrics
        _row(4, diagnosis_date="2012-01-01", enrolled="2013-01-01", withdrawal_date="2019-01-01"),
        # 5: reached KRT after diagnosis -> pre-KRT end = kf_date (shorter than overall)
        _row(5, diagnosis_date="2010-01-01", enrolled="2011-01-01", kf_date="2015-01-01"),
        # 6: already on KRT before diagnosis/recruitment -> negative pre-KRT window
        _row(6, diagnosis_date="2020-01-01", enrolled="2019-01-01", kf_date="2015-01-01"),
        # 7: no diagnosis AND no enrolment date at all (edge case)
        _row(7, diagnosis_date=None, enrolled=None),
    ])
    df["start_date"] = start_date(df["diagnosis_date"], df["enrolled"])
    return df


def test_start_date_prefers_diagnosis_date(patients):
    assert patients.loc[patients.patient_id == 1, "start_date"].iloc[0] == pd.Timestamp("2015-01-01")


def test_start_date_falls_back_to_cohort_entry(patients):
    assert patients.loc[patients.patient_id == 2, "start_date"].iloc[0] == pd.Timestamp("2018-06-01")


def test_start_date_missing_when_both_unavailable(patients):
    assert pd.isna(patients.loc[patients.patient_id == 7, "start_date"].iloc[0])


def test_overall_follow_up_excludes_withdrawn_patients(patients):
    pop, stats = overall_follow_up(patients, TODAY)
    assert 4 not in set(pop["patient_id"])
    assert stats["count"] == 5  # 6 non-withdrawn minus patient 7 (no start date)


def test_overall_follow_up_ends_at_death_for_deceased(patients):
    pop, _ = overall_follow_up(patients, TODAY)
    row = pop[pop.patient_id == 3].iloc[0]
    assert row["_end"] == pd.Timestamp("2020-01-01")
    assert row["_years"] == pytest.approx((pd.Timestamp("2020-01-01") - pd.Timestamp("2010-01-01")).days / 365.25)


def test_overall_follow_up_ends_at_today_for_alive_patients(patients):
    pop, _ = overall_follow_up(patients, TODAY)
    row = pop[pop.patient_id == 1].iloc[0]
    assert row["_end"] == TODAY


def test_overall_follow_up_drops_patient_with_no_start_date(patients):
    pop, stats = overall_follow_up(patients, TODAY)
    row = pop[pop.patient_id == 7].iloc[0]
    assert pd.isna(row["_years"])
    assert stats["count"] == 5


def test_pre_krt_ends_at_kf_date_when_reached(patients):
    pop, _ = pre_krt_follow_up(patients, TODAY)
    row = pop[pop.patient_id == 5].iloc[0]
    assert row["_end"] == pd.Timestamp("2015-01-01")
    assert row["_years"] == pytest.approx((pd.Timestamp("2015-01-01") - pd.Timestamp("2010-01-01")).days / 365.25)


def test_pre_krt_negative_window_excluded_from_count(patients):
    pop, stats = pre_krt_follow_up(patients, TODAY)
    row = pop[pop.patient_id == 6].iloc[0]
    assert row["_years"] < 0
    # patients 1,2,3,5 valid; 4 withdrawn (not in pop); 6 negative; 7 no start date
    assert stats["count"] == 4


def test_pre_krt_also_excludes_withdrawn(patients):
    pop, _ = pre_krt_follow_up(patients, TODAY)
    assert 4 not in set(pop["patient_id"])


def test_overall_and_pre_krt_grouped_by_cohort():
    df = pd.DataFrame([
        _row(1, diagnosis_date="2015-01-01", enrolled="2016-01-01") | {"group_id": 10},
        _row(2, diagnosis_date="2010-01-01", enrolled="2011-01-01", kf_date="2015-01-01") | {"group_id": 10},
        _row(3, diagnosis_date="2018-01-01", enrolled="2019-01-01") | {"group_id": 20},
        _row(4, diagnosis_date="2012-01-01", enrolled="2013-01-01", withdrawal_date="2019-01-01") | {"group_id": 20},
    ])
    df["start_date"] = start_date(df["diagnosis_date"], df["enrolled"])

    _, overall_stats = overall_follow_up(df, TODAY, group_col="group_id")
    assert overall_stats[10]["count"] == 2
    assert overall_stats[20]["count"] == 1  # patient 4 withdrawn

    _, pre_krt_stats = pre_krt_follow_up(df, TODAY, group_col="group_id")
    assert pre_krt_stats[10]["count"] == 2
    assert pre_krt_stats[20]["count"] == 1


def test_empty_dataframe_does_not_error():
    empty = pd.DataFrame(columns=["patient_id", "start_date", "date_of_death", "withdrawal_date", "kf_date"])
    pop, stats = overall_follow_up(empty, TODAY)
    assert stats == {"median": 0.0, "q1": 0.0, "q3": 0.0, "count": 0}
    pop, stats = pre_krt_follow_up(empty, TODAY)
    assert stats == {"median": 0.0, "q1": 0.0, "q3": 0.0, "count": 0}
