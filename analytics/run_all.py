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
from config.cohorts import EXCLUDED_GROUP_IDS, COHORT_LETTERS
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

        excluded = ",".join(str(i) for i in EXCLUDED_GROUP_IDS)
        today    = pd.Timestamp.today().normalize()

        # ════════════════════════════════════════════════════════
        # STEP 1 — Pre-aggregate last activity per patient ONCE
        #          (avoids slow full-table joins in every query)
        # ════════════════════════════════════════════════════════
        print("Pre-aggregating last activity per patient...")
        last_activity_df = pd.read_sql("""
            SELECT patient_id, MAX(last_date) AS last_activity
            FROM (
                SELECT patient_id, MAX(date::date)         AS last_date FROM results     GROUP BY patient_id
                UNION ALL
                SELECT patient_id, MAX(created_date::date) AS last_date FROM medications GROUP BY patient_id
            ) sub
            GROUP BY patient_id
        """, conn)
        last_activity_df["last_activity"] = pd.to_datetime(last_activity_df["last_activity"], errors="coerce")
        last_activity_map = last_activity_df.set_index("patient_id")["last_activity"].to_dict()
        print(f"  Last activity loaded for {len(last_activity_map):,} patients")

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


        # ════════════════════════════════════════════════════════
        # STEP 2 — Patient Demographics (Section A)
        # ════════════════════════════════════════════════════════
        print("── Section A: Overall RaDaR ──")
        print("  Loading demographics data...")
        demographics = pd.read_sql(f"""
            SELECT
                pd.*,
                CASE WHEN pdiag.patient_id IS NOT NULL
                     THEN TRUE ELSE FALSE END AS has_diagnosis,
                CASE WHEN pnum.patient_id  IS NOT NULL
                     THEN TRUE ELSE FALSE END AS has_nhs_number
            FROM patient_demographics pd
            INNER JOIN patients p
                ON  p.id = pd.patient_id
               AND p.test    = FALSE
               AND p.control = FALSE
            INNER JOIN (
                SELECT DISTINCT gp2.patient_id
                FROM group_patients gp2
                JOIN groups g2 ON g2.id = gp2.group_id AND g2.type = 'COHORT'
                WHERE gp2.group_id NOT IN ({excluded})
            ) cohort_pts ON cohort_pts.patient_id = pd.patient_id
            LEFT JOIN (SELECT DISTINCT patient_id FROM patient_diagnoses) pdiag
                ON pdiag.patient_id = pd.patient_id
            LEFT JOIN (SELECT DISTINCT patient_id FROM patient_numbers) pnum
                ON pnum.patient_id = pd.patient_id
            WHERE pd.source_type = 'RADAR'
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

        # Follow-up using pre-aggregated last_activity
        demographics["enrolled"]      = pd.to_datetime(demographics["enrolled"],      errors="coerce", utc=True).dt.tz_localize(None)
        demographics["date_of_death"] = pd.to_datetime(demographics["date_of_death"], errors="coerce", utc=True).dt.tz_localize(None)
        demographics["last_activity"] = demographics["patient_id"].map(last_activity_map)
        # last_activity before enrolment = batch upload of historical data → use today
        # death before enrolment = genuine data error → exclude
        demographics["last_activity_adj"] = demographics.apply(
            lambda r: today if pd.notna(r["last_activity"]) and r["last_activity"] < r["enrolled"] else r["last_activity"],
            axis=1,
        )
        demographics["end_date"] = demographics["date_of_death"].fillna(
            demographics["last_activity_adj"].fillna(today)
        )
        demographics["follow_up_years"] = (
            (demographics["end_date"] - demographics["enrolled"]).dt.days / 365.25
        )
        # Only negative remaining = death before enrolment (real error) → exclude
        bad_death = int((demographics["follow_up_years"] < 0).sum())
        if bad_death:
            print(f"  WARNING: {bad_death} patients excluded — date_of_death before enrolment (data error)")
            logger.warning(f"Demographics: {bad_death} patients with date_of_death before enrolment")
        fu = demographics["follow_up_years"].dropna()
        fu = fu[fu >= 0]
        median_fu = round(fu.median(), 1)
        q1_fu     = round(fu.quantile(0.25), 1)
        q3_fu     = round(fu.quantile(0.75), 1)

        print(f"  Total patients   : {total:,}")
        print(f"  Deceased         : {deceased_total:,}")
        print(f"  Adults           : {adults_total:,}  |  Children: {children_total:,}")
        if unknown_age:
            print(f"  Unknown age      : {unknown_age:,}")
        print(f"  Median follow-up : {median_fu} yrs (IQR {q1_fu}–{q3_fu})")

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

            elif var_name == "CAUSE_OF_DEATH":
                missing = int(is_missing(deceased["cause_of_death"]).sum())
                pct     = round(missing / deceased_total * 100, 1) if deceased_total > 0 else 0.0
                result  = build_result(var, missing, deceased_total)
                result["pct_missing"] = pct
                result["desc"]        = (
                    f"Cause of death — calculated among {deceased_total:,} deceased patients only"
                )
                demo_results.append(result)
                continue

            elif var_name == "DIAGNOSIS":
                missing = int((demographics["has_diagnosis"] == False).sum())
                result  = build_result(var, missing, total)

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

        # Follow-up per cohort — join pre-aggregated last_activity, no big table joins
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
        cohort_patients_df["last_activity"] = cohort_patients_df["patient_id"].map(last_activity_map)
        # last_activity before enrolment = batch upload of historical data → use today
        # death before enrolment = genuine data error → exclude and warn
        cohort_patients_df["last_activity_adj"] = cohort_patients_df.apply(
            lambda r: today if pd.notna(r["last_activity"]) and r["last_activity"] < r["enrolled"] else r["last_activity"],
            axis=1,
        )
        cohort_patients_df["end_date"] = cohort_patients_df["date_of_death"].fillna(
            cohort_patients_df["last_activity_adj"].fillna(today)
        )
        cohort_patients_df["follow_up_years"] = (
            (cohort_patients_df["end_date"] - cohort_patients_df["enrolled"]).dt.days / 365.25
        )
        # Warn per cohort if any genuine errors remain (death before enrolment)
        bad = cohort_patients_df[cohort_patients_df["follow_up_years"] < 0].groupby("group_id").size()
        if not bad.empty:
            print(f"  WARNING: {bad.sum()} patients excluded across {len(bad)} cohort(s) — date_of_death before enrolment (data error)")
            logger.warning(f"Cohorts: {bad.sum()} patients with date_of_death before enrolment: {bad.to_dict()}")

        # Capture full cohort patient set BEFORE dropping negative follow-up rows
        # so KF / transplant denominators = 39,178, not 39,160
        all_cohort_pids       = set(cohort_patients_df["patient_id"])
        total_cohort_patients = len(all_cohort_pids)

        cohort_patients_df = cohort_patients_df[cohort_patients_df["follow_up_years"] >= 0]

        fu_map = (
            cohort_patients_df.groupby("group_id")["follow_up_years"]
            .agg(
                median_fu=lambda x: round(x.median(), 1),
                q1_fu    =lambda x: round(x.quantile(0.25), 1),
                q3_fu    =lambda x: round(x.quantile(0.75), 1),
                fu_count ="count",
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
                pd.cause_of_death, pd.gender, pd.ethnicity_id, pd.nationality_id,
                pd.email_address,
                CASE WHEN pdiag.patient_id IS NOT NULL THEN TRUE ELSE FALSE END AS has_diagnosis,
                CASE WHEN pnum.patient_id  IS NOT NULL THEN TRUE ELSE FALSE END AS has_nhs_number
            FROM patient_demographics pd
            INNER JOIN patients p
                ON  p.id = pd.patient_id
               AND p.test    = FALSE
               AND p.control = FALSE
            LEFT JOIN (SELECT DISTINCT patient_id FROM patient_diagnoses) pdiag
                ON pdiag.patient_id = pd.patient_id
            LEFT JOIN (SELECT DISTINCT patient_id FROM patient_numbers) pnum
                ON pnum.patient_id = pd.patient_id
            WHERE pd.source_type = 'RADAR'
        """, conn)
        print(f"  {len(all_demo_df):,} RADAR demographic records loaded for cohorts")

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
                SELECT DISTINCT e1.patient_id
                FROM egfr_below_15 e1
                JOIN egfr_below_15 e2
                    ON  e1.patient_id = e2.patient_id
                    AND e2.date >= e1.date + INTERVAL '28 days'
                WHERE e1.patient_id NOT IN (SELECT patient_id FROM intervening_high)
            )
            SELECT patient_id FROM transplants
            UNION
            SELECT patient_id FROM dialysis
            UNION
            SELECT patient_id FROM egfr_kf
        """, conn)
        # Restrict to the 39,178 cohort patients only (excludes excluded groups)
        kf_patient_ids = set(kf_df["patient_id"]) & all_cohort_pids
        print(f"  {len(kf_patient_ids):,} patients with Kidney Failure events (within cohort patients)")

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
                f"have evidence of KF (transplant, dialysis, or eGFR<15 confirmed ×2 ≥28 days apart). "
                f"Based on RaDaR data — not linked to UKRR."
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
            "name":        "FOLLOW_UP",
            "pct_missing": None,
            "missing":     None,
            "total":       len(fu),
            "required":    False,
            "desc":        f"Median follow-up: {median_fu} yrs (IQR {q1_fu}–{q3_fu} yrs) — based on last activity in results or medications",
        })

        demo_section = {
            "section":   "A",
            "title":     "Overall RaDaR",
            "variables": demo_results,
            "stats": {
                "adults":    adults_total,
                "children":  children_total,
                "median_fu": median_fu,
                "q1_fu":     q1_fu,
                "q3_fu":     q3_fu,
            },
        }
        print(f"  Section A done — {len(demo_results)} variables\n")

        # Pre-build group_id → set(patient_ids) for fast per-cohort demographics filtering
        cohort_pid_map = (
            cohort_patients_df.groupby("group_id")["patient_id"]
            .apply(set)
            .to_dict()
        )

        # Build cohort sections
        cohort_sections = []
        for letter, (_, row) in zip(COHORT_LETTERS, groups_df.iterrows()):
            group_id = int(row["id"])
            db_name  = row["name"]
            closed   = db_name.lower().startswith("z ")

            counts        = counts_map.get(group_id, {})
            patient_count = int(counts.get("patient_count", 0))
            adults        = int(counts.get("adults",        0))
            children      = int(counts.get("children",      0))

            fu_stats  = fu_map.get(group_id, {})
            median_fu = fu_stats.get("median_fu", 0)
            q1_fu     = fu_stats.get("q1_fu",     0)
            q3_fu     = fu_stats.get("q3_fu",     0)
            fu_count  = int(fu_stats.get("fu_count", 0))

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

                elif var_name == "CAUSE_OF_DEATH":
                    if cohort_dec_n > 0:
                        missing = int(is_missing(cohort_deceased["cause_of_death"]).sum())
                        pct     = round(missing / cohort_dec_n * 100, 1)
                    else:
                        missing, pct = 0, 0.0
                    demo_vars.append({
                        "id":          cohort_var_id,
                        "name":        var_name,
                        "pct_missing": pct,
                        "missing":     missing,
                        "total":       cohort_dec_n,
                        "required":    var["required"],
                        "desc":        f"Cause of death — calculated among {cohort_dec_n:,} deceased patients only",
                    })
                    continue

                elif var_name == "EMAIL_ADDRESS":
                    missing_in_demo = int((
                        cohort_demo["email_address"].isna() |
                        cohort_demo["email_address"].isin(DEFAULT_EMAILS)
                    ).sum())

                elif var_name == "DIAGNOSIS":
                    missing_in_demo = int((cohort_demo["has_diagnosis"] == False).sum())

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
                        f"have evidence of KF (transplant, dialysis, or eGFR<15 confirmed ×2 ≥28 days apart). "
                        f"Based on RaDaR data — not linked to UKRR."
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
                    "id": f"{letter}.followup", "name": "FOLLOW_UP",
                    "pct_missing": None, "missing": None, "total": fu_count,
                    "required": False,
                    "desc": f"Median follow-up: {median_fu} yrs (IQR {q1_fu}–{q3_fu} yrs) — based on last activity in results or medications",
                },
            ]

            cohort_sections.append({
                "section": letter, "title": db_name,
                "closed": closed,  "variables": variables,
            })

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
