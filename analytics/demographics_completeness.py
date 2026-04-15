"""
demographics_completeness.py
-----------------------------
Calculates data completeness for patient demographics variables.
Reads from:  patient_demographics, patient_diagnoses, patient_numbers, patients
Writes to:   output/completeness.json
Run with:    python -m analytics.demographics_completeness
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
from analytics.utils import calc_pct_missing, calc_pct_missing_email, build_result, logger


def is_missing(series: pd.Series) -> pd.Series:
    """Returns a boolean mask — True where value is NULL or empty/whitespace string."""
    return (
        series.isna() |
        (series.astype(str).str.strip() == "")
    )


def run():
    print("Opening SSH tunnel...")
    tunnel = get_tunnel()
    tunnel.start()
    print(f"Tunnel open on local port: {tunnel.local_bind_port}")

    conn = None
    try:
        conn = get_connection()
        print("Connected to PostgreSQL!")

        # ── Load all data in one query ──
        print("Loading data...")
        demographics = pd.read_sql("""
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
            INNER JOIN group_patients gp
                ON  gp.patient_id = pd.patient_id
               AND  gp.group_id   = 123
            LEFT JOIN (SELECT DISTINCT patient_id FROM patient_diagnoses) pdiag
                ON pdiag.patient_id = pd.patient_id
            LEFT JOIN (SELECT DISTINCT patient_id FROM patient_numbers) pnum
                ON pnum.patient_id = pd.patient_id
            WHERE pd.source_type = 'RADAR'
        """, conn)

        total          = len(demographics)
        deceased       = demographics[demographics["date_of_death"].notna()]
        deceased_total = len(deceased)

        # ── Adult / child split based on date_of_birth ──
        today = pd.Timestamp.today().normalize()
        dob   = pd.to_datetime(demographics["date_of_birth"], errors="coerce")
        age   = (today - dob).dt.days / 365.25
        adults_total   = int((age >= 18).sum())
        children_total = int((age <  18).sum())
        unknown_age    = int(age.isna().sum())

        # ── Median (IQR) years of follow-up ──
        # Enrolment  = patients.created_date
        # Last activity = latest of results.date or medications.created_date
        # End date   = date_of_death (deceased) OR last activity OR today
        print("Calculating follow-up...")
        followup_df = pd.read_sql("""
            SELECT
                p.id                                             AS patient_id,
                p.created_date                                   AS enrolled,
                pd.date_of_death,
                MAX(r.date::date)                                AS last_result,
                MAX(m.created_date::date)                        AS last_medication
            FROM patients p
            INNER JOIN group_patients gp
                ON  gp.patient_id = p.id
               AND  gp.group_id   = 123
            LEFT JOIN patient_demographics pd
                ON  pd.patient_id = p.id
               AND  pd.source_type = 'RADAR'
            LEFT JOIN results r
                ON  r.patient_id = p.id
            LEFT JOIN medications m
                ON  m.patient_id = p.id
            WHERE (p.test    IS NULL OR p.test    = FALSE)
              AND (p.control IS NULL OR p.control = FALSE)
            GROUP BY p.id, p.created_date, pd.date_of_death
        """, conn)

        followup_df["enrolled"]        = pd.to_datetime(followup_df["enrolled"],        errors="coerce")
        followup_df["date_of_death"]   = pd.to_datetime(followup_df["date_of_death"],   errors="coerce")
        followup_df["last_result"]     = pd.to_datetime(followup_df["last_result"],      errors="coerce")
        followup_df["last_medication"] = pd.to_datetime(followup_df["last_medication"],  errors="coerce")

        # Last known activity = latest of results or medications
        followup_df["last_activity"] = followup_df[["last_result", "last_medication"]].max(axis=1)

        # End date: death date if deceased, else last activity, else today
        followup_df["end_date"] = followup_df["date_of_death"].fillna(
            followup_df["last_activity"].fillna(today)
        )

        followup_df["follow_up_years"] = (
            (followup_df["end_date"] - followup_df["enrolled"]).dt.days / 365.25
        )

        # Drop patients with no enrolment date or negative follow-up
        fu = followup_df["follow_up_years"].dropna()
        fu = fu[fu >= 0]

        median_fu = round(fu.median(), 1)
        q1_fu     = round(fu.quantile(0.25), 1)
        q3_fu     = round(fu.quantile(0.75), 1)

        print(f"Total RADAR patients  : {total:,}")
        print(f"Deceased patients     : {deceased_total:,} ({round(deceased_total/total*100,1)}%)")
        print(f"Adults (≥18)          : {adults_total:,}")
        print(f"Children (<18)        : {children_total:,}")
        if unknown_age:
            print(f"Unknown age (no DOB)  : {unknown_age:,}")
        print(f"Median follow-up      : {median_fu} yrs (IQR {q1_fu}–{q3_fu})")
        print("\nCalculating completeness...")

        results = []

        for var in DEMOGRAPHICS_VARIABLES:
            var_name = var["name"]
            var_col  = var["column"]

            # ── EMAIL: null OR known placeholder/default email ──
            if var_name == "EMAIL_ADDRESS":
                missing = int((
                    demographics["email_address"].isna() |
                    demographics["email_address"].isin(DEFAULT_EMAILS)
                ).sum())
                result = build_result(var, missing, total)

            # ── DATE_OF_DEATH: informational only ──
            # Living patients correctly have no death date — not missing data.
            # We just record how many patients are deceased as informational.
            elif var_name == "DATE_OF_DEATH":
                result = build_result(var, 0, total)
                result["pct_missing"] = None
                result["missing"]     = deceased_total
                result["total"]       = total
                result["desc"]        = (
                    f"Date of death — {deceased_total:,} of {total:,} patients "
                    f"({round(deceased_total/total*100,1)}%) have a recorded death date"
                )
                print(f"  [ℹ] DATE_OF_DEATH: {deceased_total:,} deceased — informational only")
                logger.info(f"DATE_OF_DEATH: {deceased_total} deceased of {total}")
                results.append(result)
                continue

            # ── CAUSE_OF_DEATH: calculated among deceased patients only ──
            # Denominator = deceased patients, not all patients.
            # A living patient with no cause of death is correct, not missing.
            elif var_name == "CAUSE_OF_DEATH":
                missing = int(is_missing(deceased["cause_of_death"]).sum())
                pct     = round(missing / deceased_total * 100, 1) if deceased_total > 0 else 0.0
                result  = build_result(var, missing, deceased_total)
                result["pct_missing"] = pct
                result["desc"]        = (
                    f"Cause of death — calculated among {deceased_total:,} "
                    f"deceased patients only"
                )
                status = "✓" if pct < 10 else "!" if pct < 50 else "✗"
                print(f"  [{status}] CAUSE_OF_DEATH: {pct}% missing among "
                      f"{deceased_total:,} deceased ({missing:,} missing)")
                logger.info(f"CAUSE_OF_DEATH: {pct}% missing among {deceased_total} deceased")
                results.append(result)
                continue

            # ── DIAGNOSIS: patient must exist in patient_diagnoses ──
            elif var_name == "DIAGNOSIS":
                missing = int((demographics["has_diagnosis"] == False).sum())
                result  = build_result(var, missing, total)

            # ── NHS_NUMBER: patient must exist in patient_numbers ──
            elif var_name == "NHS_NUMBER":
                missing = int((demographics["has_nhs_number"] == False).sum())
                result  = build_result(var, missing, total)

            # ── All other fields: NULL or empty string ──
            else:
                missing = int(is_missing(demographics[var_col]).sum())
                result  = build_result(var, missing, total)

            # ── Print status and append ──
            pct    = result["pct_missing"]
            status = "✓" if pct < 10 else "!" if pct < 50 else "✗"
            print(f"  [{status}] {var_name}: {pct}% missing ({missing:,}/{total:,})")
            logger.info(f"{var_name}: {pct}% missing ({missing}/{total})")
            results.append(result)

        # ── Append follow-up as an informational variable row ──
        results.append({
            "id":          "A.12",
            "name":        "FOLLOW_UP",
            "pct_missing": None,
            "missing":     None,
            "total":       len(fu),
            "required":    False,
            "desc":        f"Median follow-up: {median_fu} yrs (IQR {q1_fu}–{q3_fu} yrs) — based on last activity in results or medications",
        })
        print(f"  [ℹ] FOLLOW_UP: median {median_fu} yrs (IQR {q1_fu}–{q3_fu})")

        # ── Save JSON — preserve existing cohort sections ──
        os.makedirs("output", exist_ok=True)
        json_path = "output/completeness.json"

        if os.path.exists(json_path):
            with open(json_path) as f:
                existing = json.load(f)
            cohort_sections = [s for s in existing if s.get("section") != "A"]
        else:
            cohort_sections = []

        demo_section = {
            "section":   "A",
            "title":     "Patient Demographics",
            "variables": results,
            "stats": {
                "adults":        adults_total,
                "children":      children_total,
                "median_fu":     median_fu,
                "q1_fu":         q1_fu,
                "q3_fu":         q3_fu,
            },
        }

        output = [demo_section] + cohort_sections

        with open(json_path, "w") as f:
            json.dump(output, f, indent=2)

        print(f"\nDone! output/completeness.json written.")
        print(f"Variables checked: {len(results)}")
        logger.info("completeness.json written successfully")

    except Exception as e:
        print(f"Error: {e}")
        logger.error(f"Error: {e}")
        raise

    finally:
        if conn:
            conn.close()
        tunnel.stop()
        print("Connection closed. Tunnel closed.")
        logger.info("Connection and tunnel closed")


if __name__ == "__main__":
    run()
