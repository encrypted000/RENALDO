"""
cohorts_completeness.py
-----------------------
Calculates data completeness for each of the 33 RaDaR cohort groups.
All cohort names come directly from the database — nothing is hardcoded.
Reads from:  groups, group_patients, patients
Writes to:   output/completeness.json  (appends cohort sections after section A)
Run with:    python -m analytics.cohorts_completeness
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
from config.cohorts import EXCLUDED_GROUP_IDS, COHORT_LETTERS
from analytics.utils import logger


def run():
    print("Opening SSH tunnel...")
    tunnel = get_tunnel()
    tunnel.start()
    print(f"Tunnel open on local port: {tunnel.local_bind_port}")

    conn = None
    try:
        conn = get_connection()
        print("Connected to PostgreSQL!")

        excluded = ",".join(str(i) for i in EXCLUDED_GROUP_IDS)

        # ── Fetch all cohort groups from DB, sorted alphabetically (case-insensitive) ──
        print("Loading cohort groups from database...")
        groups_df = pd.read_sql(f"""
            SELECT id, name
            FROM groups
            WHERE type = 'COHORT'
              AND id NOT IN ({excluded})
            ORDER BY LOWER(name)
        """, conn)
        print(f"Found {len(groups_df)} cohort groups in database")

        if len(groups_df) > len(COHORT_LETTERS):
            raise ValueError(
                f"DB returned {len(groups_df)} cohorts but only "
                f"{len(COHORT_LETTERS)} letters are defined in config. "
                f"Add more letters to config/cohorts.py COHORT_LETTERS."
            )

        # ── Fetch patient counts per cohort — total, adults, children ──
        print("Counting patients per cohort...")
        counts_df = pd.read_sql(f"""
            SELECT
                gp.group_id,
                COUNT(DISTINCT gp.patient_id)                                   AS patient_count,
                COUNT(DISTINCT CASE
                    WHEN DATE_PART('year', AGE(pd.date_of_birth)) >= 18
                    THEN gp.patient_id END)                                      AS adults,
                COUNT(DISTINCT CASE
                    WHEN DATE_PART('year', AGE(pd.date_of_birth)) < 18
                    THEN gp.patient_id END)                                      AS children
            FROM group_patients gp
            JOIN patients p
                ON  p.id = gp.patient_id
               AND p.test    = FALSE
               AND p.control = FALSE
            LEFT JOIN patient_demographics pd
                ON  pd.patient_id = gp.patient_id
               AND  pd.source_type = 'RADAR'
            WHERE gp.group_id NOT IN ({excluded})
            GROUP BY gp.group_id
        """, conn)

        counts_map = counts_df.set_index("group_id").to_dict(orient="index")

        # ── Fetch follow-up data per patient per cohort ──
        print("Calculating follow-up per cohort...")
        followup_df = pd.read_sql(f"""
            SELECT
                gp.group_id,
                p.created_date,
                pd.date_of_death,
                MAX(r.date::date)         AS last_result,
                MAX(m.created_date::date) AS last_medication
            FROM group_patients gp
            JOIN patients p
                ON  p.id = gp.patient_id
               AND p.test    = FALSE
               AND p.control = FALSE
            LEFT JOIN patient_demographics pd
                ON  pd.patient_id = gp.patient_id
               AND  pd.source_type = 'RADAR'
            LEFT JOIN results r
                ON  r.patient_id = gp.patient_id
            LEFT JOIN medications m
                ON  m.patient_id = gp.patient_id
            WHERE gp.group_id NOT IN ({excluded})
            GROUP BY gp.group_id, p.id, p.created_date, pd.date_of_death
        """, conn)

        today = pd.Timestamp.today().normalize()
        followup_df["created_date"]    = pd.to_datetime(followup_df["created_date"],    errors="coerce")
        followup_df["date_of_death"]   = pd.to_datetime(followup_df["date_of_death"],   errors="coerce")
        followup_df["last_result"]     = pd.to_datetime(followup_df["last_result"],      errors="coerce")
        followup_df["last_medication"] = pd.to_datetime(followup_df["last_medication"],  errors="coerce")

        followup_df["last_activity"] = followup_df[["last_result", "last_medication"]].max(axis=1)
        followup_df["end_date"]      = followup_df["date_of_death"].fillna(
            followup_df["last_activity"].fillna(today)
        )
        followup_df["follow_up_years"] = (
            (followup_df["end_date"] - followup_df["created_date"]).dt.days / 365.25
        )
        # Keep only valid rows
        followup_df = followup_df[followup_df["follow_up_years"] >= 0]

        # Group by cohort → median, Q1, Q3
        fu_map = (
            followup_df.groupby("group_id")["follow_up_years"]
            .agg(
                median_fu=lambda x: round(x.median(), 1),
                q1_fu    =lambda x: round(x.quantile(0.25), 1),
                q3_fu    =lambda x: round(x.quantile(0.75), 1),
                fu_count ="count",
            )
            .to_dict(orient="index")
        )

        # ── Assign letters and build sections ──
        # Closed cohorts are identified by a leading "z " prefix in the DB name
        # (RaDaR convention for cohorts no longer recruiting).
        sections = []

        for letter, (_, row) in zip(COHORT_LETTERS, groups_df.iterrows()):
            group_id      = int(row["id"])
            db_name       = row["name"]
            closed        = db_name.lower().startswith("z ")

            counts        = counts_map.get(group_id, {})
            patient_count = int(counts.get("patient_count", 0))
            adults        = int(counts.get("adults",        0))
            children      = int(counts.get("children",      0))

            fu        = fu_map.get(group_id, {})
            median_fu = fu.get("median_fu", 0)
            q1_fu     = fu.get("q1_fu",     0)
            q3_fu     = fu.get("q3_fu",     0)
            fu_count  = int(fu.get("fu_count", 0))

            variables = [
                {
                    "id":          f"{letter}.total",
                    "name":        "TOTAL_PATIENTS",
                    "pct_missing": None,
                    "missing":     None,
                    "total":       patient_count,
                    "required":    False,
                    "desc":        "Total patients enrolled in this cohort (test and control patients excluded)",
                },
                {
                    "id":          f"{letter}.adults",
                    "name":        "ADULTS",
                    "pct_missing": None,
                    "missing":     None,
                    "total":       adults,
                    "required":    False,
                    "desc":        "Patients aged 18 or over",
                },
                {
                    "id":          f"{letter}.children",
                    "name":        "CHILDREN",
                    "pct_missing": None,
                    "missing":     None,
                    "total":       children,
                    "required":    False,
                    "desc":        "Patients aged under 18",
                },
                {
                    "id":          f"{letter}.followup",
                    "name":        "FOLLOW_UP",
                    "pct_missing": None,
                    "missing":     None,
                    "total":       fu_count,
                    "required":    False,
                    "desc":        f"Median follow-up: {median_fu} yrs (IQR {q1_fu}–{q3_fu} yrs) — based on last activity in results or medications",
                },
            ]

            sections.append({
                "section":   letter,
                "title":     db_name,
                "closed":    closed,
                "variables": variables,
            })

            closed_tag = " [CLOSED]" if closed else ""
            print(f"  {letter:>2}  {db_name[:50]:<50}  {patient_count:>5} total  {adults:>5} adults  {children:>4} children{closed_tag}")
            logger.info(f"{letter} {db_name}: {patient_count} total, {adults} adults, {children} children")

        # ── Merge with existing completeness.json ──
        os.makedirs("output", exist_ok=True)
        json_path = "output/completeness.json"

        if os.path.exists(json_path):
            with open(json_path) as f:
                existing = json.load(f)
            demographics = [s for s in existing if s.get("section") == "A"]
        else:
            demographics = []

        output = demographics + sections

        with open(json_path, "w") as f:
            json.dump(output, f, indent=2)

        print(f"\nDone! {len(sections)} cohort sections written to {json_path}")
        logger.info(f"cohorts_completeness: {len(sections)} sections written")

    except Exception as e:
        print(f"Error: {e}")
        logger.error(f"Error in cohorts_completeness: {e}")
        raise

    finally:
        if conn:
            conn.close()
        tunnel.stop()
        print("Connection closed. Tunnel closed.")
        logger.info("Connection and tunnel closed")


if __name__ == "__main__":
    run()
