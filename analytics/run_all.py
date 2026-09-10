"""
run_all.py
----------
Runs demographics + all cohort completeness in a single tunnel session.
One connection, pre-aggregated queries — much faster than running separately.
Run with: python -m analytics.run_all
"""
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*pandas only supports SQLAlchemy.*")

import sys
import os
import json
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import get_tunnel, get_connection
from config.demographics import DEMOGRAPHICS_VARIABLES, DEFAULT_EMAILS
from config.cohorts import (
    EXCLUDED_GROUP_IDS,
    EXCLUDED_GROUP_NAMES,
    WITHDRAWN_GROUP_IDS,
    NO_PRE_KRT_FOLLOWUP_COHORTS,
    NO_BIOCHEMISTRY_COHORTS,
    COHORT_LETTERS,
)
from analytics.utils import build_result, logger


def is_missing(series: pd.Series) -> pd.Series:
    return series.isna() | (series.astype(str).str.strip() == "")


def run():
    print("Opening SSH tunnel...")
    tunnel = get_tunnel()
    tunnel.start()
    print(f"Tunnel open on local port: {tunnel.local_bind_port}")

    conn = None
    try:
        conn = get_connection()
        print("Connected to PostgreSQL!\n")

        # Resolve name-based exclusions (e.g. "Data Completeness") to group IDs
        # and merge with the static ID-based exclusion list. Doing this once,
        # up front, means every downstream query's existing "NOT IN (excluded)"
        # filter picks it up automatically.
        excluded_by_name_df = pd.read_sql(
            "SELECT id FROM groups WHERE type = 'COHORT' AND LOWER(name) = ANY(%(names)s)",
            conn,
            params={"names": [n.lower() for n in EXCLUDED_GROUP_NAMES]},
        )
        excluded_ids = set(EXCLUDED_GROUP_IDS) | set(excluded_by_name_df["id"].tolist())
        excluded      = ",".join(str(i) for i in sorted(excluded_ids))
        withdrawn_ids = ",".join(str(i) for i in WITHDRAWN_GROUP_IDS)
        today         = pd.Timestamp.today().normalize()

        # ════════════════════════════════════════════════════════
        # STEP 1 — Pre-aggregate cohort recruitment / diagnosis / withdrawal
        #          dates per patient ONCE (avoids slow full-table joins later)
        # ════════════════════════════════════════════════════════

        # ── Pre-aggregate cohort recruitment date per patient ──
        # group_patients.from_date where group type = COHORT is the "Recruited On" date
        # shown on the RaDaR front end — this is the true enrolment date.
        # A patient may be in multiple cohorts so we take the earliest.
        print("Pre-aggregating cohort recruitment dates...")
        enrolment_df = pd.read_sql("""
            SELECT gp.patient_id, MIN(COALESCE(gp.from_date::date, gp.created_date::date)) AS enrolled
            FROM group_patients gp
            JOIN groups g ON g.id = gp.group_id
            WHERE g.type = 'COHORT'
            GROUP BY gp.patient_id
        """, conn)
        enrolment_df["enrolled"] = pd.to_datetime(enrolment_df["enrolled"], errors="coerce")
        enrolment_map = enrolment_df.set_index("patient_id")["enrolled"].to_dict()
        print(f"  Cohort recruitment date loaded for {len(enrolment_map):,} patients\n")

        # ── Pre-aggregate diagnosis date per patient (for diagnosis-based follow-up) ──
        # Strict match: patient's primary diagnosis must be tied to a cohort they
        # actually belong to (diagnosis_id AND group_id both match), restricted to
        # their active membership and active diagnosis record. A looser match (just
        # "is this diagnosis primary somewhere") over-counts.
        print("Pre-aggregating diagnosis dates...")
        diagnosis_date_df = pd.read_sql(f"""
            WITH base AS (
                SELECT gp.patient_id, gp.group_id
                FROM group_patients gp
                JOIN groups g ON g.id = gp.group_id AND g.type = 'COHORT'
                JOIN patients p ON p.id = gp.patient_id AND p.test = FALSE AND p.control = FALSE
                WHERE gp.group_id NOT IN ({excluded})
                  AND gp.to_date IS NULL
            ),
            cohort_prd AS (
                SELECT group_id, diagnosis_id
                FROM group_diagnoses
                WHERE type = 'PRIMARY'
            )
            SELECT
                pd.patient_id,
                MIN(pd.from_date)::date AS diagnosis_date
            FROM patient_diagnoses pd
            JOIN cohort_prd ON cohort_prd.diagnosis_id = pd.diagnosis_id
            JOIN base ON base.patient_id = pd.patient_id AND base.group_id = cohort_prd.group_id
            WHERE pd.to_date IS NULL
            GROUP BY pd.patient_id
        """, conn)
        diagnosis_date_df["diagnosis_date"] = pd.to_datetime(diagnosis_date_df["diagnosis_date"], errors="coerce")
        diagnosis_date_map = diagnosis_date_df.set_index("patient_id")["diagnosis_date"].to_dict()
        print(f"  Diagnosis date loaded for {len(diagnosis_date_map):,} patients")

        # ── Pre-aggregate withdrawal date per patient (withdrawn-consent groups) ──
        print("Pre-aggregating withdrawal dates...")
        withdrawal_df = pd.read_sql(f"""
            SELECT patient_id, MIN(from_date)::date AS withdrawal_date
            FROM group_patients
            WHERE group_id IN ({withdrawn_ids})
            GROUP BY patient_id
        """, conn)
        withdrawal_df["withdrawal_date"] = pd.to_datetime(withdrawal_df["withdrawal_date"], errors="coerce")
        withdrawal_date_map = withdrawal_df.set_index("patient_id")["withdrawal_date"].to_dict()
        print(f"  Withdrawal date loaded for {len(withdrawal_date_map):,} patients\n")


        # ════════════════════════════════════════════════════════
        # STEP 2 — Patient Demographics (Section A)
        # ════════════════════════════════════════════════════════
        print("── Section A: Overall RaDaR ──")
        print("  Loading demographics data...")
        # LEFT JOIN patient_demographics — a patient enrolled in a cohort but with
        # NO RADAR demographics row must still appear (with NULL fields) so they're
        # counted as missing below, not silently dropped from total/numerator alike.
        # Mirrors the cohort-level population + no_demo logic used in STEP 3.
        demographics = pd.read_sql(f"""
            SELECT
                base.patient_id,
                pd.first_name, pd.last_name, pd.date_of_birth, pd.date_of_death,
                pd.gender, pd.ethnicity_id, pd.email_address,
                CASE WHEN pnum.patient_id IS NOT NULL
                     THEN TRUE ELSE FALSE END AS has_nhs_number
            FROM (
                SELECT DISTINCT gp2.patient_id
                FROM group_patients gp2
                JOIN groups g2 ON g2.id = gp2.group_id AND g2.type = 'COHORT'
                JOIN patients p ON p.id = gp2.patient_id AND p.test = FALSE AND p.control = FALSE
                WHERE gp2.group_id NOT IN ({excluded})
            ) base
            LEFT JOIN patient_demographics pd
                ON  pd.patient_id  = base.patient_id
               AND  pd.source_type = 'RADAR'
            LEFT JOIN (
                SELECT DISTINCT patient_id
                FROM patient_numbers
                WHERE source_type IN ('RADAR', 'UKRDC')
                  AND number_group_id IN (120, 121, 122)
            ) pnum
                ON pnum.patient_id = base.patient_id
        """, conn)

        # Use earliest cohort from_date as enrolment — fallback to patients.created_date
        demographics["enrolled"] = demographics["patient_id"].map(enrolment_map)

        total          = len(demographics)
        deceased       = demographics[demographics["date_of_death"].notna()]
        deceased_total = len(deceased)

        # Adults / children
        dob  = pd.to_datetime(demographics["date_of_birth"], errors="coerce")
        age  = (today - dob).dt.days / 365.25
        adults_total   = int((age >= 18).sum())
        children_total = int((age <  18).sum())
        unknown_age    = int(age.isna().sum())

        demographics["enrolled"]      = pd.to_datetime(demographics["enrolled"],      errors="coerce", utc=True).dt.tz_localize(None)
        demographics["date_of_death"] = pd.to_datetime(demographics["date_of_death"], errors="coerce", utc=True).dt.tz_localize(None)

        # ── Start date for follow-up: diagnosis date, falling back to cohort
        #    entry (recruitment date) when no diagnosis date is recorded ──
        demographics["diagnosis_date"]  = demographics["patient_id"].map(diagnosis_date_map)
        demographics["withdrawal_date"] = demographics["patient_id"].map(withdrawal_date_map)
        demographics["start_date"]      = demographics["diagnosis_date"].fillna(demographics["enrolled"])
        withdrawn_mask = demographics["withdrawal_date"].notna()

        # ── Overall follow-up: start date → death or today. Withdrawn patients
        #    are excluded from the population entirely (not censored at their
        #    withdrawal date), so the denominator = total patients - withdrawn. ──
        overall_pop = demographics[~withdrawn_mask].copy()
        overall_pop["overall_end"] = overall_pop["date_of_death"].fillna(today)
        overall_pop["overall_follow_up_years"] = (
            (overall_pop["overall_end"] - overall_pop["start_date"]).dt.days / 365.25
        )
        bad_overall = int((overall_pop["overall_follow_up_years"] < 0).sum())
        if bad_overall:
            print(f"  WARNING: {bad_overall} patients excluded from Overall follow-up — start date after follow-up end (data error)")
            logger.warning(f"Demographics: {bad_overall} patients with start date after Overall follow-up end")
        overall_fu = overall_pop["overall_follow_up_years"].dropna()
        overall_fu = overall_fu[overall_fu >= 0]
        overall_median_fu = round(overall_fu.median(), 1) if len(overall_fu) else 0.0
        overall_q1_fu     = round(overall_fu.quantile(0.25), 1) if len(overall_fu) else 0.0
        overall_q3_fu     = round(overall_fu.quantile(0.75), 1) if len(overall_fu) else 0.0

        print(f"  Total patients   : {total:,}")
        print(f"  Deceased         : {deceased_total:,}")
        print(f"  Adults           : {adults_total:,}  |  Children: {children_total:,}")
        if unknown_age:
            print(f"  Unknown age      : {unknown_age:,}")
        print(f"  Median Overall follow-up : {overall_median_fu} yrs (IQR {overall_q1_fu}–{overall_q3_fu}) — {len(overall_fu):,} patients")

        # Completeness variables
        demo_results = []
        for var in DEMOGRAPHICS_VARIABLES:
            var_name = var["name"]
            var_col  = var["column"]

            if var_name == "EMAIL_ADDRESS":
                missing = int((
                    demographics["email_address"].isna() |
                    demographics["email_address"].isin(DEFAULT_EMAILS)
                ).sum())
                result = build_result(var, missing, total)

            elif var_name == "DATE_OF_DEATH":
                result = build_result(var, 0, total)
                result["pct_missing"] = None
                result["missing"]     = deceased_total
                result["total"]       = total
                result["desc"]        = (
                    f"Date of death — {deceased_total:,} of {total:,} patients "
                    f"({round(deceased_total/total*100,1)}%) have a recorded death date"
                )
                demo_results.append(result)
                continue

            elif var_name == "DIAGNOSIS":
                continue  # PRD data loaded in Step 3 — inserted into demo_results after prd_df is built

            elif var_name == "NHS_NUMBER":
                missing = int((demographics["has_nhs_number"] == False).sum())
                result  = build_result(var, missing, total)

            else:
                missing = int(is_missing(demographics[var_col]).sum())
                result  = build_result(var, missing, total)

            pct    = result["pct_missing"]
            status = "✓" if pct < 10 else "!" if pct < 50 else "✗"
            print(f"  [{status}] {var_name}: {pct}% missing ({missing:,}/{total:,})")
            logger.info(f"{var_name}: {pct}% missing ({missing}/{total})")
            demo_results.append(result)


        # demo_section is built after STEP 3 once KF patient IDs are known
        print(f"  Section A variables ready — {len(demo_results)} (KF row added after cohort step)\n")


        # ════════════════════════════════════════════════════════
        # STEP 3 — Cohort groups (Sections B–AH)
        # ════════════════════════════════════════════════════════
        print("── Cohort Groups ──")

        groups_df = pd.read_sql(f"""
            SELECT id, name
            FROM groups
            WHERE type = 'COHORT'
              AND id NOT IN ({excluded})
            ORDER BY LOWER(name)
        """, conn)
        print(f"  Found {len(groups_df)} cohort groups in database")

        if len(groups_df) > len(COHORT_LETTERS):
            raise ValueError(
                f"DB returned {len(groups_df)} cohorts but only "
                f"{len(COHORT_LETTERS)} letters defined in config/cohorts.py."
            )

        # Counts: total, adults, children — one query for all cohorts
        counts_df = pd.read_sql(f"""
            SELECT
                gp.group_id,
                COUNT(DISTINCT gp.patient_id)  AS patient_count,
                COUNT(DISTINCT CASE
                    WHEN DATE_PART('year', AGE(pd.date_of_birth)) >= 18
                    THEN gp.patient_id END)     AS adults,
                COUNT(DISTINCT CASE
                    WHEN DATE_PART('year', AGE(pd.date_of_birth)) < 18
                    THEN gp.patient_id END)     AS children
            FROM group_patients gp
            JOIN groups g
                ON  g.id   = gp.group_id
               AND  g.type = 'COHORT'
            JOIN patients p
                ON  p.id = gp.patient_id
               AND p.test    = FALSE
               AND p.control = FALSE
            LEFT JOIN patient_demographics pd
                ON  pd.patient_id  = gp.patient_id
               AND  pd.source_type = 'RADAR'
            WHERE gp.group_id NOT IN ({excluded})
            GROUP BY gp.group_id
        """, conn)
        counts_map = counts_df.set_index("group_id").to_dict(orient="index")

        # Follow-up per cohort — enrolment/death per patient per cohort membership
        print("  Calculating cohort follow-up...")
        cohort_patients_df = pd.read_sql(f"""
            SELECT
                gp.group_id,
                p.id              AS patient_id,
                COALESCE(gp.from_date::date, gp.created_date::date) AS enrolled,
                pd.date_of_death
            FROM group_patients gp
            JOIN groups g
                ON  g.id   = gp.group_id
               AND  g.type = 'COHORT'
            JOIN patients p
                ON  p.id = gp.patient_id
               AND p.test    = FALSE
               AND p.control = FALSE
            LEFT JOIN patient_demographics pd
                ON  pd.patient_id  = gp.patient_id
               AND  pd.source_type = 'RADAR'
            WHERE gp.group_id NOT IN ({excluded})
        """, conn)

        # enrolled = from_date for that specific cohort (the "Recruited On" date on RaDaR front end)
        # fallback to earliest cohort date across all cohorts if from_date is null
        cohort_patients_df["enrolled"] = pd.to_datetime(cohort_patients_df["enrolled"], errors="coerce")
        cohort_patients_df["enrolled"] = cohort_patients_df["enrolled"].fillna(
            cohort_patients_df["patient_id"].map(enrolment_map)
        )
        cohort_patients_df["date_of_death"] = pd.to_datetime(cohort_patients_df["date_of_death"], errors="coerce", utc=True).dt.tz_localize(None)

        # Full cohort patient set (all patients, including withdrawn) — this is
        # the true membership universe used for KF / transplant denominators.
        all_cohort_pids       = set(cohort_patients_df["patient_id"])
        total_cohort_patients = len(all_cohort_pids)
        cohort_pid_map = (
            cohort_patients_df.groupby("group_id")["patient_id"]
            .apply(set)
            .to_dict()
        )

        # ── Start date per patient per cohort: diagnosis date, else cohort entry ──
        cohort_patients_df["diagnosis_date"]  = cohort_patients_df["patient_id"].map(diagnosis_date_map)
        cohort_patients_df["withdrawal_date"] = cohort_patients_df["patient_id"].map(withdrawal_date_map)
        cohort_patients_df["start_date"]      = cohort_patients_df["diagnosis_date"].fillna(cohort_patients_df["enrolled"])
        cohort_withdrawn_mask = cohort_patients_df["withdrawal_date"].notna()

        # ── Overall follow-up per cohort: start date → death or today, withdrawn excluded ──
        overall_cohort_df = cohort_patients_df[~cohort_withdrawn_mask].copy()
        overall_cohort_df["overall_end"] = overall_cohort_df["date_of_death"].fillna(today)
        overall_cohort_df["overall_follow_up_years"] = (
            (overall_cohort_df["overall_end"] - overall_cohort_df["start_date"]).dt.days / 365.25
        )
        bad_overall = overall_cohort_df[overall_cohort_df["overall_follow_up_years"] < 0].groupby("group_id").size()
        if not bad_overall.empty:
            print(f"  WARNING: {bad_overall.sum()} patients excluded from Overall follow-up across {len(bad_overall)} cohort(s) — start date after follow-up end (data error)")
            logger.warning(f"Cohorts: {bad_overall.sum()} patients with start date after Overall follow-up end: {bad_overall.to_dict()}")

        overall_valid_df = overall_cohort_df[
            overall_cohort_df["overall_follow_up_years"].notna() & (overall_cohort_df["overall_follow_up_years"] >= 0)
        ]
        overall_fu_map = (
            overall_valid_df.groupby("group_id")["overall_follow_up_years"]
            .agg(
                overall_median_fu=lambda x: round(x.median(), 1),
                overall_q1_fu    =lambda x: round(x.quantile(0.25), 1),
                overall_q3_fu    =lambda x: round(x.quantile(0.75), 1),
                overall_fu_count ="count",
            )
            .to_dict(orient="index")
        )

        # ── Load all RADAR demographics for cohort-level completeness ──
        # Section A uses group_id=123 only. Cohort sections need their own patients,
        # so we load demographics for all non-test/control patients here.
        print("  Loading demographics for all cohort patients...")
        all_demo_df = pd.read_sql("""
            SELECT
                pd.patient_id,
                pd.first_name, pd.last_name, pd.date_of_birth, pd.date_of_death,
                pd.gender, pd.ethnicity_id,
                pd.email_address,
                CASE WHEN pnum.patient_id IS NOT NULL THEN TRUE ELSE FALSE END AS has_nhs_number
            FROM patient_demographics pd
            INNER JOIN patients p
                ON  p.id = pd.patient_id
               AND p.test    = FALSE
               AND p.control = FALSE
            LEFT JOIN (
                SELECT DISTINCT patient_id
                FROM patient_numbers
                WHERE source_type IN ('RADAR', 'UKRDC')
                  AND number_group_id IN (120, 121, 122)
            ) pnum
                ON pnum.patient_id = pd.patient_id
            WHERE pd.source_type = 'RADAR'
        """, conn)
        print(f"  {len(all_demo_df):,} RADAR demographic records loaded for cohorts")

        # ── Primary Renal Diagnosis (PRD) per patient per cohort ──
        # A patient has a PRD if they have a diagnosis in patient_diagnoses whose
        # diagnosis_id matches a group_diagnoses row with type='PRIMARY' for the
        # same cohort group the patient is enrolled in.
        print("  Loading Primary Renal Diagnosis (PRD) data...")
        prd_df = pd.read_sql(f"""
            SELECT DISTINCT pdiag.patient_id, gp.group_id
            FROM patient_diagnoses pdiag
            JOIN group_patients gp
                ON  gp.patient_id = pdiag.patient_id
            JOIN groups g
                ON  g.id   = gp.group_id
                AND g.type = 'COHORT'
            JOIN group_diagnoses gd
                ON  gd.diagnosis_id = pdiag.diagnosis_id
                AND gd.group_id     = gp.group_id
                AND gd.type         = 'PRIMARY'
            WHERE gp.group_id NOT IN ({excluded})
        """, conn)
        prd_overall_pids = set(prd_df["patient_id"]) & all_cohort_pids
        prd_cohort_map   = prd_df.groupby("group_id")["patient_id"].apply(set).to_dict()
        print(f"  {len(prd_overall_pids):,} patients with a Primary Renal Diagnosis recorded")

        # Insert Section A DIAGNOSIS before NHS_NUMBER (after A.9 EMAIL_ADDRESS)
        diag_missing_a = int(total - len(set(demographics["patient_id"]) & prd_overall_pids))
        diag_pct_a     = round(diag_missing_a / total * 100, 1) if total > 0 else 0.0
        status         = "✓" if diag_pct_a < 10 else "!" if diag_pct_a < 50 else "✗"
        print(f"  [{status}] DIAGNOSIS (PRD): {diag_pct_a}% missing ({diag_missing_a:,}/{total:,})")
        nhs_idx = next((i for i, v in enumerate(demo_results) if v.get("name") == "NHS_NUMBER"), len(demo_results))
        demo_results.insert(nhs_idx, {
            "id":          "A.10",
            "name":        "Primary Renal Diagnosis",
            "pct_missing": diag_pct_a,
            "missing":     diag_missing_a,
            "total":       total,
            "required":    True,
            "desc":        "Primary Renal Diagnosis",
        })

        # ── Kidney Failure patients (single query, reused for section A + all cohorts) ──
        # KF = earliest of: transplant date, dialysis from_date, or eGFR<15 confirmed
        # twice ≥28 days apart with no eGFR≥15 in between.
        # NOTE: based on RaDaR data only — not linked to UKRR.
        print("  Calculating Kidney Failure patients...")
        kf_df = pd.read_sql("""
            WITH egfr_below_15 AS (
                SELECT patient_id, date, value::numeric AS egfr_value
                FROM results
                WHERE observation_id = 47
                  AND value::numeric < 15
            ),
            intervening_high AS (
                SELECT DISTINCT r.patient_id
                FROM results r
                JOIN (
                    SELECT patient_id, MIN(date) AS first_low, MAX(date) AS last_low
                    FROM egfr_below_15
                    GROUP BY patient_id
                ) bounds ON bounds.patient_id = r.patient_id
                WHERE r.observation_id = 47
                  AND r.value::numeric >= 15
                  AND r.date > bounds.first_low
                  AND r.date < bounds.last_low
            ),
            egfr_kf AS (
                -- KF confirmation date = date of the 2nd qualifying reading (≥28 days after the 1st)
                SELECT e1.patient_id, MIN(e2.date) AS kf_date
                FROM egfr_below_15 e1
                JOIN egfr_below_15 e2
                    ON  e1.patient_id = e2.patient_id
                    AND e2.date >= e1.date + INTERVAL '28 days'
                WHERE e1.patient_id NOT IN (SELECT patient_id FROM intervening_high)
                GROUP BY e1.patient_id
            ),
            transplant_dates AS (
                SELECT patient_id, MIN(date) AS kf_date FROM transplants GROUP BY patient_id
            ),
            dialysis_dates AS (
                SELECT patient_id, MIN(from_date) AS kf_date FROM dialysis GROUP BY patient_id
            ),
            all_kf_dates AS (
                SELECT patient_id, kf_date FROM transplant_dates
                UNION ALL
                SELECT patient_id, kf_date FROM dialysis_dates
                UNION ALL
                SELECT patient_id, kf_date FROM egfr_kf
            )
            SELECT patient_id, MIN(kf_date) AS kf_date
            FROM all_kf_dates
            GROUP BY patient_id
        """, conn)
        # Source columns (transplants.date, dialysis.from_date, results.date) are
        # timestamptz — normalise to tz-naive, same as every other date column in
        # this file, so downstream comparisons don't mix aware/naive timestamps.
        kf_df["kf_date"] = pd.to_datetime(kf_df["kf_date"], errors="coerce", utc=True).dt.tz_localize(None)
        # Restrict to the cohort patients only (excludes excluded groups)
        kf_patient_ids = set(kf_df["patient_id"]) & all_cohort_pids
        kf_date_map    = kf_df.set_index("patient_id")["kf_date"].to_dict()
        print(f"  {len(kf_patient_ids):,} patients with Kidney Failure events (within cohort patients)")

        # ── Follow-up pre-KRT: start date → KRT (kidney failure)/death/today,
        #    withdrawn excluded. Patients already at/past KRT by their start date
        #    (diagnosis or cohort entry) yield a negative window and are excluded
        #    from the count — this is expected, not a data error. ──
        print("  Calculating Follow-up pre-KRT...")

        demographics["kf_date"] = demographics["patient_id"].map(kf_date_map)
        pre_krt_pop = demographics[~withdrawn_mask].copy()
        pre_krt_pop["pre_krt_end"] = pre_krt_pop.apply(
            lambda r: min([d for d in [today, r["date_of_death"], r["kf_date"]] if pd.notna(d)]),
            axis=1,
        )
        pre_krt_pop["pre_krt_follow_up_years"] = (
            (pre_krt_pop["pre_krt_end"] - pre_krt_pop["start_date"]).dt.days / 365.25
        )
        pre_krt_fu = pre_krt_pop["pre_krt_follow_up_years"].dropna()
        pre_krt_fu = pre_krt_fu[pre_krt_fu >= 0]
        pre_krt_median_fu = round(pre_krt_fu.median(), 1) if len(pre_krt_fu) else 0.0
        pre_krt_q1_fu     = round(pre_krt_fu.quantile(0.25), 1) if len(pre_krt_fu) else 0.0
        pre_krt_q3_fu     = round(pre_krt_fu.quantile(0.75), 1) if len(pre_krt_fu) else 0.0

        cohort_patients_df["kf_date"] = cohort_patients_df["patient_id"].map(kf_date_map)
        pre_krt_cohort_df = cohort_patients_df[~cohort_withdrawn_mask].copy()
        pre_krt_cohort_df["pre_krt_end"] = pre_krt_cohort_df.apply(
            lambda r: min([d for d in [today, r["date_of_death"], r["kf_date"]] if pd.notna(d)]),
            axis=1,
        )
        pre_krt_cohort_df["pre_krt_follow_up_years"] = (
            (pre_krt_cohort_df["pre_krt_end"] - pre_krt_cohort_df["start_date"]).dt.days / 365.25
        )
        pre_krt_valid_df = pre_krt_cohort_df[
            pre_krt_cohort_df["pre_krt_follow_up_years"].notna() & (pre_krt_cohort_df["pre_krt_follow_up_years"] >= 0)
        ]
        pre_krt_fu_map = (
            pre_krt_valid_df.groupby("group_id")["pre_krt_follow_up_years"]
            .agg(
                pre_krt_median_fu=lambda x: round(x.median(), 1),
                pre_krt_q1_fu    =lambda x: round(x.quantile(0.25), 1),
                pre_krt_q3_fu    =lambda x: round(x.quantile(0.75), 1),
                pre_krt_fu_count ="count",
            )
            .to_dict(orient="index")
        )
        print(f"  Overall RaDaR — {len(pre_krt_fu):,} patients with a valid Follow-up pre-KRT window")

        # ── Biochemistry (creatinine/proteinuria) results, pre-KRT ──
        # Creatinine = observation_id 46. Proteinuria = ACR (1) + PCR (2) combined.
        # Only rows with a value, deduped to at most one result per patient per day.
        print("  Loading biochemistry (creatinine/proteinuria) results...")
        creatinine_days_df = pd.read_sql("""
            SELECT DISTINCT patient_id, date::date AS result_date
            FROM results
            WHERE observation_id = 46
              AND value IS NOT NULL
              AND value::text <> ''
        """, conn)
        proteinuria_days_df = pd.read_sql("""
            SELECT DISTINCT patient_id, date::date AS result_date
            FROM results
            WHERE observation_id IN (1, 2)
              AND value IS NOT NULL
              AND value::text <> ''
        """, conn)
        creatinine_days_df["result_date"]  = pd.to_datetime(creatinine_days_df["result_date"],  errors="coerce")
        proteinuria_days_df["result_date"] = pd.to_datetime(proteinuria_days_df["result_date"], errors="coerce")

        # Cutoff per patient: their KF/KRT date if they've reached it, else today
        # (denominator is ALL patients — those never reaching KRT are censored at today).
        cutoff_map = {
            pid: (kf_date_map.get(pid) if pd.notna(kf_date_map.get(pid)) else today)
            for pid in all_cohort_pids
        }

        def _pre_cutoff_counts(days_df):
            df = days_df[days_df["patient_id"].isin(all_cohort_pids)].copy()
            df["cutoff"] = df["patient_id"].map(cutoff_map)
            df = df[df["result_date"] < df["cutoff"]]
            return df.groupby("patient_id").size()

        creatinine_pre_counts  = _pre_cutoff_counts(creatinine_days_df)
        proteinuria_pre_counts = _pre_cutoff_counts(proteinuria_days_df)
        print(f"  Creatinine pre-cutoff results for {len(creatinine_pre_counts):,} patients; "
              f"Proteinuria (ACR+PCR) for {len(proteinuria_pre_counts):,} patients")

        # ── Transplant counts per patient (restricted to cohort patients) ──
        print("  Calculating transplant counts per patient...")
        transplant_counts_df = pd.read_sql("""
            SELECT patient_id, COUNT(DISTINCT date) AS transplant_count
            FROM transplants
            GROUP BY patient_id
        """, conn)
        # Restrict to cohort patients only
        transplant_counts_df = transplant_counts_df[
            transplant_counts_df["patient_id"].isin(all_cohort_pids)
        ]
        transplant_count_map = transplant_counts_df.set_index("patient_id")["transplant_count"].to_dict()
        print(f"  Transplant counts loaded for {len(transplant_count_map):,} patients")

        # ── Section A: add overall KF row then finalise demo_section ──
        kf_total_a = len(kf_patient_ids)
        kf_pct_a   = round(kf_total_a / total_cohort_patients * 100, 1) if total_cohort_patients > 0 else 0.0
        demo_results.append({
            "id":          "A.13",
            "name":        "KIDNEY_FAILURE",
            "pct_missing": None,
            "missing":     kf_total_a,
            "total":       total_cohort_patients,
            "required":    False,
            "desc":        (
                f"Kidney Failure — {kf_total_a:,} of {total_cohort_patients:,} patients ({kf_pct_a}%) "
                f"have evidence of kidney failure based on transplant records, dialysis records, or eGFR "
                f"below 15 ml/min/1.73m² on two occasions ≥28 days apart with no recovery."
            ),
        })
        print(f"  [ℹ] KIDNEY_FAILURE: {kf_total_a:,} / {total_cohort_patients:,} ({kf_pct_a}%)")

        single_tx_a = int(sum(1 for pid in all_cohort_pids if transplant_count_map.get(pid, 0) == 1))
        multi_tx_a  = int(sum(1 for pid in all_cohort_pids if transplant_count_map.get(pid, 0) >= 2))
        demo_results.append({
            "id": "A.14", "name": "TRANSPLANT_SINGLE",
            "pct_missing": None, "missing": single_tx_a, "total": total_cohort_patients,
            "required": False,
            "desc": f"Patients with exactly 1 transplant — {single_tx_a:,} of {total_cohort_patients:,}",
        })
        demo_results.append({
            "id": "A.15", "name": "TRANSPLANT_MULTIPLE",
            "pct_missing": None, "missing": multi_tx_a, "total": total_cohort_patients,
            "required": False,
            "desc": f"Patients with 2 or more transplants — {multi_tx_a:,} of {total_cohort_patients:,}",
        })
        print(f"  [ℹ] TRANSPLANT_SINGLE: {single_tx_a:,}  |  TRANSPLANT_MULTIPLE: {multi_tx_a:,}")
        demo_results.append({
            "id":          "A.16",
            "name":        "OVERALL_FOLLOW_UP",
            "pct_missing": None,
            "missing":     None,
            "total":       len(overall_fu),
            "required":    False,
            "desc":        (
                f"Median follow-up: {overall_median_fu} yrs (IQR {overall_q1_fu}–{overall_q3_fu} yrs) — "
                f"from diagnosis date (or cohort entry if unavailable) until death or the current date"
            ),
        })
        demo_results.append({
            "id":          "A.17",
            "name":        "FOLLOW_UP_PRE_KRT",
            "pct_missing": None,
            "missing":     None,
            "total":       len(pre_krt_fu),
            "required":    False,
            "desc":        (
                f"Median follow-up: {pre_krt_median_fu} yrs (IQR {pre_krt_q1_fu}–{pre_krt_q3_fu} yrs) — "
                f"from diagnosis (or cohort entry if unavailable) until KRT/death or the current date"
            ),
        })

        demo_section = {
            "section":   "A",
            "title":     "Overall RaDaR",
            "variables": demo_results,
            "stats": {
                "adults":    adults_total,
                "children":  children_total,
                "median_fu": overall_median_fu,
                "q1_fu":     overall_q1_fu,
                "q3_fu":     overall_q3_fu,
            },
        }
        print(f"  Section A done — {len(demo_results)} variables\n")

        # Cohorts excluded from "Follow up pre KRT" / Biochemistry Metadata
        no_pre_krt_names = {n.strip().lower() for n in NO_PRE_KRT_FOLLOWUP_COHORTS}
        no_biochem_names = {n.strip().lower() for n in NO_BIOCHEMISTRY_COHORTS}

        # Build cohort sections
        cohort_sections = []
        for letter, (_, row) in zip(COHORT_LETTERS, groups_df.iterrows()):
            group_id = int(row["id"])
            db_name  = row["name"]
            closed   = db_name.lower().startswith("z ")
            name_lower        = db_name.strip().lower()
            skip_pre_krt      = name_lower in no_pre_krt_names
            skip_biochemistry = name_lower in no_biochem_names

            counts        = counts_map.get(group_id, {})
            patient_count = int(counts.get("patient_count", 0))
            adults        = int(counts.get("adults",        0))
            children      = int(counts.get("children",      0))

            overall_stats  = overall_fu_map.get(group_id, {})
            overall_median = overall_stats.get("overall_median_fu", 0)
            overall_q1     = overall_stats.get("overall_q1_fu",     0)
            overall_q3     = overall_stats.get("overall_q3_fu",     0)
            overall_count  = int(overall_stats.get("overall_fu_count", 0))

            pre_krt_stats  = pre_krt_fu_map.get(group_id, {})
            pre_krt_median = pre_krt_stats.get("pre_krt_median_fu", 0)
            pre_krt_q1     = pre_krt_stats.get("pre_krt_q1_fu",     0)
            pre_krt_q3     = pre_krt_stats.get("pre_krt_q3_fu",     0)
            pre_krt_count  = int(pre_krt_stats.get("pre_krt_fu_count", 0))

            # ── Demographics completeness for this cohort ──
            cohort_pids     = cohort_pid_map.get(group_id, set())
            cohort_demo     = all_demo_df[all_demo_df["patient_id"].isin(cohort_pids)]
            no_demo         = max(patient_count - len(cohort_demo), 0)  # patients without RADAR demographics row
            cohort_deceased = cohort_demo[cohort_demo["date_of_death"].notna()]
            cohort_dec_n    = len(cohort_deceased)

            demo_vars = []
            for var in DEMOGRAPHICS_VARIABLES:
                var_name      = var["name"]
                var_col       = var["column"]
                cohort_var_id = f"{letter}.d{var['id'].split('.')[-1]}"

                if var_name == "DATE_OF_DEATH":
                    pct_dec = round(cohort_dec_n / patient_count * 100, 1) if patient_count else 0.0
                    demo_vars.append({
                        "id":          cohort_var_id,
                        "name":        var_name,
                        "pct_missing": None,
                        "missing":     cohort_dec_n,
                        "total":       patient_count,
                        "required":    False,
                        "desc":        f"Date of death — {cohort_dec_n:,} of {patient_count:,} patients ({pct_dec}%) have a recorded death date",
                    })
                    continue

                elif var_name == "EMAIL_ADDRESS":
                    missing_in_demo = int((
                        cohort_demo["email_address"].isna() |
                        cohort_demo["email_address"].isin(DEFAULT_EMAILS)
                    ).sum())

                elif var_name == "DIAGNOSIS":
                    prd_pids      = prd_cohort_map.get(group_id, set())
                    total_missing = int(len(cohort_pids - prd_pids))
                    pct           = round(total_missing / patient_count * 100, 1) if patient_count > 0 else 0.0
                    demo_vars.append({
                        "id":          cohort_var_id,
                        "name":        "Primary Renal Diagnosis",
                        "pct_missing": pct,
                        "missing":     total_missing,
                        "total":       patient_count,
                        "required":    var["required"],
                        "desc":        f"Primary Renal Diagnosis for enrolled cohort — {total_missing:,} of {patient_count:,} patients missing",
                    })
                    continue

                elif var_name == "NHS_NUMBER":
                    missing_in_demo = int((cohort_demo["has_nhs_number"] == False).sum())

                else:
                    missing_in_demo = int(is_missing(cohort_demo[var_col]).sum())

                total_missing = missing_in_demo + no_demo
                pct = round(total_missing / patient_count * 100, 1) if patient_count > 0 else 0.0
                demo_vars.append({
                    "id":          cohort_var_id,
                    "name":        var_name,
                    "pct_missing": pct,
                    "missing":     total_missing,
                    "total":       patient_count,
                    "required":    var["required"],
                    "desc":        var["desc"],
                })

            kf_count    = int(len(cohort_pids & kf_patient_ids))
            kf_pct      = round(kf_count / patient_count * 100, 1) if patient_count > 0 else 0.0
            single_tx_c = int(sum(1 for pid in cohort_pids if transplant_count_map.get(pid, 0) == 1))
            multi_tx_c  = int(sum(1 for pid in cohort_pids if transplant_count_map.get(pid, 0) >= 2))

            variables = [
                {
                    "id": f"{letter}.total",   "name": "TOTAL_PATIENTS",
                    "pct_missing": None, "missing": None, "total": patient_count,
                    "required": False,
                    "desc": "Total patients enrolled in this cohort (test and control patients excluded)",
                },
                {
                    "id": f"{letter}.adults",  "name": "ADULTS",
                    "pct_missing": None, "missing": None, "total": adults,
                    "required": False, "desc": "Patients aged 18 or over",
                },
                {
                    "id": f"{letter}.children","name": "CHILDREN",
                    "pct_missing": None, "missing": None, "total": children,
                    "required": False, "desc": "Patients aged under 18",
                },
            ] + demo_vars + [
                {
                    "id":          f"{letter}.kf",
                    "name":        "KIDNEY_FAILURE",
                    "pct_missing": None,
                    "missing":     kf_count,
                    "total":       patient_count,
                    "required":    False,
                    "desc":        (
                        f"Kidney Failure — {kf_count:,} of {patient_count:,} patients ({kf_pct}%) "
                        f"have evidence of kidney failure based on transplant records, dialysis records, or eGFR "
                        f"below 15 ml/min/1.73m² on two occasions ≥28 days apart with no recovery."
                    ),
                },
                {
                    "id": f"{letter}.tx1", "name": "TRANSPLANT_SINGLE",
                    "pct_missing": None, "missing": single_tx_c, "total": patient_count,
                    "required": False,
                    "desc": f"Patients with exactly 1 transplant — {single_tx_c:,} of {patient_count:,}",
                },
                {
                    "id": f"{letter}.tx2", "name": "TRANSPLANT_MULTIPLE",
                    "pct_missing": None, "missing": multi_tx_c, "total": patient_count,
                    "required": False,
                    "desc": f"Patients with 2 or more transplants — {multi_tx_c:,} of {patient_count:,}",
                },
                {
                    "id": f"{letter}.overall_followup", "name": "OVERALL_FOLLOW_UP",
                    "pct_missing": None, "missing": None, "total": overall_count,
                    "required": False,
                    "desc": (
                        f"Median follow-up: {overall_median} yrs (IQR {overall_q1}–{overall_q3} yrs) — "
                        f"from diagnosis date (or cohort entry if unavailable) until death or the current date"
                    ),
                },
            ]

            if not skip_pre_krt:
                variables.append({
                    "id": f"{letter}.followup_pre_krt", "name": "FOLLOW_UP_PRE_KRT",
                    "pct_missing": None, "missing": None, "total": pre_krt_count,
                    "required": False,
                    "desc": (
                        f"Median follow-up: {pre_krt_median} yrs (IQR {pre_krt_q1}–{pre_krt_q3} yrs) — "
                        f"from diagnosis (or cohort entry if unavailable) until KRT/death or the current date"
                    ),
                })

            section = {
                "section": letter, "title": db_name,
                "closed": closed,  "variables": variables,
            }

            if not skip_biochemistry:
                # ── Biochemistry pre-KRT — denominator is all patients in the cohort ──
                cohort_pids_list  = list(cohort_pids)
                cohort_creat_cnt  = creatinine_pre_counts.reindex(cohort_pids_list,  fill_value=0)
                cohort_prot_cnt   = proteinuria_pre_counts.reindex(cohort_pids_list, fill_value=0)

                creatinine_n_patients   = int((cohort_creat_cnt >= 1).sum())
                proteinuria_n_patients  = int((cohort_prot_cnt  >= 1).sum())
                creatinine_total_results  = int(cohort_creat_cnt.sum())
                proteinuria_total_results = int(cohort_prot_cnt.sum())

                creat_nonzero = cohort_creat_cnt[cohort_creat_cnt >= 1]
                prot_nonzero  = cohort_prot_cnt[cohort_prot_cnt >= 1]
                creat_median = round(creat_nonzero.median(), 1) if len(creat_nonzero) else 0
                creat_q1     = round(creat_nonzero.quantile(0.25), 1) if len(creat_nonzero) else 0
                creat_q3     = round(creat_nonzero.quantile(0.75), 1) if len(creat_nonzero) else 0
                prot_median  = round(prot_nonzero.median(), 1) if len(prot_nonzero) else 0
                prot_q1      = round(prot_nonzero.quantile(0.25), 1) if len(prot_nonzero) else 0
                prot_q3      = round(prot_nonzero.quantile(0.75), 1) if len(prot_nonzero) else 0

                section["biochemistry"] = {
                    "creatinine": {
                        "count": creatinine_n_patients, "total": patient_count,
                        "total_results": creatinine_total_results,
                        "median_per_patient": creat_median,
                        "q1_per_patient": creat_q1, "q3_per_patient": creat_q3,
                    },
                    "proteinuria": {
                        "count": proteinuria_n_patients, "total": patient_count,
                        "total_results": proteinuria_total_results,
                        "median_per_patient": prot_median,
                        "q1_per_patient": prot_q1, "q3_per_patient": prot_q3,
                    },
                }

            cohort_sections.append(section)

            closed_tag = " [CLOSED]" if closed else ""
            print(f"  {letter:>2}  {db_name[:50]:<50}  {patient_count:>5} total  {adults:>5} adults  {children:>4} children{closed_tag}")
            logger.info(f"{letter} {db_name}: {patient_count} total, {adults} adults, {children} children")


        # ════════════════════════════════════════════════════════
        # STEP 4 — Write JSON
        # ════════════════════════════════════════════════════════
        os.makedirs("output", exist_ok=True)
        output = [demo_section] + cohort_sections
        with open("output/completeness.json", "w") as f:
            json.dump(output, f, indent=2)

        print(f"\nDone! output/completeness.json written.")
        print(f"  Sections: 1 demographics + {len(cohort_sections)} cohorts")
        logger.info("run_all: completeness.json written successfully")

    except Exception as e:
        print(f"Error: {e}")
        logger.error(f"Error in run_all: {e}")
        raise

    finally:
        if conn:
            conn.close()
        tunnel.stop()
        print("Connection closed. Tunnel closed.")
        logger.info("Connection and tunnel closed")


if __name__ == "__main__":
    run()
