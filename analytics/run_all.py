"""
run_all.py
----------
Orchestrates the full completeness pipeline: opens a DB tunnel, pulls the
raw data via analytics/pipeline/queries.py, runs it through the pure
calculation modules (analytics/pipeline/follow_up.py, cohort_rules.py),
assembles the per-section JSON, and writes output/completeness.json.

One connection, pre-aggregated queries — much faster than running the
old, now-deleted per-concern scripts separately.
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
    COHORT_LETTERS,
)
from analytics.utils import build_result, missing_mask, logger
from analytics.pipeline import queries, follow_up, cohort_rules


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
        excluded_by_name = queries.fetch_excluded_group_ids_by_name(conn, EXCLUDED_GROUP_NAMES)
        excluded_ids  = set(EXCLUDED_GROUP_IDS) | set(excluded_by_name)
        excluded      = ",".join(str(i) for i in sorted(excluded_ids))
        withdrawn_ids = ",".join(str(i) for i in WITHDRAWN_GROUP_IDS)
        today         = pd.Timestamp.today().normalize()

        # ════════════════════════════════════════════════════════
        # STEP 1 — Pre-aggregate cohort recruitment / diagnosis / withdrawal
        #          dates per patient ONCE (avoids slow full-table joins later)
        # ════════════════════════════════════════════════════════
        print("Pre-aggregating cohort recruitment dates...")
        enrolment_df = queries.fetch_enrolment_dates(conn)
        enrolment_map = enrolment_df.set_index("patient_id")["enrolled"].to_dict()
        print(f"  Cohort recruitment date loaded for {len(enrolment_map):,} patients\n")

        print("Pre-aggregating diagnosis dates...")
        diagnosis_date_df = queries.fetch_diagnosis_dates(conn, excluded)
        diagnosis_date_map = diagnosis_date_df.set_index("patient_id")["diagnosis_date"].to_dict()
        print(f"  Diagnosis date loaded for {len(diagnosis_date_map):,} patients")

        print("Pre-aggregating withdrawal dates...")
        withdrawal_df = queries.fetch_withdrawal_dates(conn, withdrawn_ids)
        withdrawal_date_map = withdrawal_df.set_index("patient_id")["withdrawal_date"].to_dict()
        print(f"  Withdrawal date loaded for {len(withdrawal_date_map):,} patients\n")


        # ════════════════════════════════════════════════════════
        # STEP 2 — Patient Demographics (Section A)
        # ════════════════════════════════════════════════════════
        print("── Section A: Overall RaDaR ──")
        print("  Loading demographics data...")
        demographics = queries.fetch_section_a_demographics(conn, excluded)

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
        demographics["start_date"]      = follow_up.start_date(demographics["diagnosis_date"], demographics["enrolled"])

        # ── Overall follow-up: start date → death or today, withdrawn excluded ──
        overall_pop, overall_stats = follow_up.overall_follow_up(demographics, today)
        bad_overall = int((overall_pop["_years"] < 0).sum())
        if bad_overall:
            print(f"  WARNING: {bad_overall} patients excluded from Overall follow-up — start date after follow-up end (data error)")
            logger.warning(f"Demographics: {bad_overall} patients with start date after Overall follow-up end")
        overall_median_fu, overall_q1_fu, overall_q3_fu = overall_stats["median"], overall_stats["q1"], overall_stats["q3"]

        print(f"  Total patients   : {total:,}")
        print(f"  Deceased         : {deceased_total:,}")
        print(f"  Adults           : {adults_total:,}  |  Children: {children_total:,}")
        if unknown_age:
            print(f"  Unknown age      : {unknown_age:,}")
        print(f"  Median Overall follow-up : {overall_median_fu} yrs (IQR {overall_q1_fu}–{overall_q3_fu}) — {overall_stats['count']:,} patients")

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
                missing = int(missing_mask(demographics[var_col]).sum())
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

        groups_df = queries.fetch_cohort_groups(conn, excluded)
        print(f"  Found {len(groups_df)} cohort groups in database")

        if len(groups_df) > len(COHORT_LETTERS):
            raise ValueError(
                f"DB returned {len(groups_df)} cohorts but only "
                f"{len(COHORT_LETTERS)} letters defined in config/cohorts.py."
            )

        counts_df  = queries.fetch_cohort_counts(conn, excluded)
        counts_map = counts_df.set_index("group_id").to_dict(orient="index")

        print("  Calculating cohort follow-up...")
        cohort_patients_df = queries.fetch_cohort_patients(conn, excluded)

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
        cohort_patients_df["start_date"]      = follow_up.start_date(cohort_patients_df["diagnosis_date"], cohort_patients_df["enrolled"])

        # ── Overall follow-up per cohort: start date → death or today, withdrawn excluded ──
        overall_cohort_df, overall_fu_map = follow_up.overall_follow_up(cohort_patients_df, today, group_col="group_id")
        bad_overall = overall_cohort_df[overall_cohort_df["_years"] < 0].groupby("group_id").size()
        if not bad_overall.empty:
            print(f"  WARNING: {bad_overall.sum()} patients excluded from Overall follow-up across {len(bad_overall)} cohort(s) — start date after follow-up end (data error)")
            logger.warning(f"Cohorts: {bad_overall.sum()} patients with start date after Overall follow-up end: {bad_overall.to_dict()}")

        # ── Load all RADAR demographics for cohort-level completeness ──
        # Section A uses its own excluded-group filter. Cohort sections need
        # their own patients, so we load demographics for all non-test/control
        # patients here.
        print("  Loading demographics for all cohort patients...")
        all_demo_df = queries.fetch_all_cohort_demographics(conn)
        print(f"  {len(all_demo_df):,} RADAR demographic records loaded for cohorts")

        # ── Primary Renal Diagnosis (PRD) per patient per cohort ──
        print("  Loading Primary Renal Diagnosis (PRD) data...")
        prd_df = queries.fetch_primary_renal_diagnoses(conn, excluded)
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
        print("  Calculating Kidney Failure patients...")
        kf_df = queries.fetch_kidney_failure_dates(conn)
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
        pre_krt_pop, pre_krt_stats = follow_up.pre_krt_follow_up(demographics, today)
        pre_krt_median_fu, pre_krt_q1_fu, pre_krt_q3_fu = pre_krt_stats["median"], pre_krt_stats["q1"], pre_krt_stats["q3"]
        print(f"  Overall RaDaR — {pre_krt_stats['count']:,} patients with a valid Follow-up pre-KRT window")

        cohort_patients_df["kf_date"] = cohort_patients_df["patient_id"].map(kf_date_map)
        pre_krt_cohort_df, pre_krt_fu_map = follow_up.pre_krt_follow_up(cohort_patients_df, today, group_col="group_id")

        # ── Biochemistry (creatinine/proteinuria) results, pre-KRT ──
        # Creatinine = observation_id 46. Proteinuria = ACR (1) + PCR (2) combined.
        print("  Loading biochemistry (creatinine/proteinuria) results...")
        creatinine_days_df  = queries.fetch_creatinine_results(conn)
        proteinuria_days_df = queries.fetch_proteinuria_results(conn)

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
        transplant_counts_df = queries.fetch_transplant_counts(conn)
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
            "total":       overall_stats["count"],
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
            "total":       pre_krt_stats["count"],
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

        # Build cohort sections
        cohort_sections = []
        for letter, (_, row) in zip(COHORT_LETTERS, groups_df.iterrows()):
            group_id = int(row["id"])
            db_name  = row["name"]
            closed   = cohort_rules.is_closed_cohort(db_name)
            skip_pre_krt      = cohort_rules.should_skip_pre_krt(db_name)
            skip_biochemistry = cohort_rules.should_skip_biochemistry(db_name)

            counts        = counts_map.get(group_id, {})
            patient_count = int(counts.get("patient_count", 0))
            adults        = int(counts.get("adults",        0))
            children      = int(counts.get("children",      0))

            overall_c = overall_fu_map.get(group_id, {})
            overall_median = overall_c.get("median", 0)
            overall_q1     = overall_c.get("q1",     0)
            overall_q3     = overall_c.get("q3",     0)
            overall_count  = int(overall_c.get("count", 0))

            pre_krt_c = pre_krt_fu_map.get(group_id, {})
            pre_krt_median = pre_krt_c.get("median", 0)
            pre_krt_q1     = pre_krt_c.get("q1",     0)
            pre_krt_q3     = pre_krt_c.get("q3",     0)
            pre_krt_count  = int(pre_krt_c.get("count", 0))

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
                    missing_in_demo = int(missing_mask(cohort_demo[var_col]).sum())

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
