"""
queries.py
----------
All SQL against the RaDaR database lives here — one function per query,
each taking an open DB connection (+ params where needed) and returning a
DataFrame. No calculation logic beyond date parsing/tz-normalisation, which
travels with the query since it's about correctly interpreting what the
database returned, not business logic.

This is the module to check first for anything DB-access-shaped: table
names, join conditions, what counts as "excluded", what RaDaR columns mean.
"""
import pandas as pd


def fetch_excluded_group_ids_by_name(conn, names: list) -> list:
    """Resolve cohort names (e.g. "Data Completeness") to their group IDs."""
    df = pd.read_sql(
        "SELECT id FROM groups WHERE type = 'COHORT' AND LOWER(name) = ANY(%(names)s)",
        conn,
        params={"names": [n.lower() for n in names]},
    )
    return df["id"].tolist()


def fetch_enrolment_dates(conn) -> pd.DataFrame:
    """
    patient_id -> earliest cohort recruitment date. group_patients.from_date
    where group type = COHORT is the "Recruited On" date shown on the RaDaR
    front end; falls back to created_date. A patient may be in multiple
    cohorts, so this takes the earliest across all of them.
    """
    df = pd.read_sql("""
        SELECT gp.patient_id, MIN(COALESCE(gp.from_date::date, gp.created_date::date)) AS enrolled
        FROM group_patients gp
        JOIN groups g ON g.id = gp.group_id
        WHERE g.type = 'COHORT'
        GROUP BY gp.patient_id
    """, conn)
    df["enrolled"] = pd.to_datetime(df["enrolled"], errors="coerce")
    return df


def fetch_diagnosis_dates(conn, excluded_csv: str) -> pd.DataFrame:
    """
    patient_id -> earliest primary renal diagnosis date. Strict match: the
    patient's primary diagnosis must be tied to a cohort they actually
    belong to (diagnosis_id AND group_id both match), restricted to active
    membership and an active diagnosis record. A looser match (just "is this
    diagnosis primary somewhere") over-counts.
    """
    df = pd.read_sql(f"""
        WITH base AS (
            SELECT gp.patient_id, gp.group_id
            FROM group_patients gp
            JOIN groups g ON g.id = gp.group_id AND g.type = 'COHORT'
            JOIN patients p ON p.id = gp.patient_id AND p.test = FALSE AND p.control = FALSE
            WHERE gp.group_id NOT IN ({excluded_csv})
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
    df["diagnosis_date"] = pd.to_datetime(df["diagnosis_date"], errors="coerce")
    return df


def fetch_withdrawal_dates(conn, withdrawn_csv: str) -> pd.DataFrame:
    """patient_id -> earliest date they entered a withdrawn-consent group."""
    df = pd.read_sql(f"""
        SELECT patient_id, MIN(from_date)::date AS withdrawal_date
        FROM group_patients
        WHERE group_id IN ({withdrawn_csv})
        GROUP BY patient_id
    """, conn)
    df["withdrawal_date"] = pd.to_datetime(df["withdrawal_date"], errors="coerce")
    return df


def fetch_section_a_demographics(conn, excluded_csv: str) -> pd.DataFrame:
    """
    One row per patient enrolled in any non-excluded cohort. LEFT JOIN
    patient_demographics — a patient with NO RADAR demographics row must
    still appear (with NULL fields) so they're counted as missing, not
    silently dropped from total/numerator alike.
    """
    return pd.read_sql(f"""
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
            WHERE gp2.group_id NOT IN ({excluded_csv})
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


def fetch_cohort_groups(conn, excluded_csv: str) -> pd.DataFrame:
    """All non-excluded COHORT groups, alphabetical (case-insensitive)."""
    return pd.read_sql(f"""
        SELECT id, name
        FROM groups
        WHERE type = 'COHORT'
          AND id NOT IN ({excluded_csv})
        ORDER BY LOWER(name)
    """, conn)


def fetch_cohort_counts(conn, excluded_csv: str) -> pd.DataFrame:
    """Per-cohort total/adult/child patient counts, one query for all cohorts."""
    return pd.read_sql(f"""
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
        WHERE gp.group_id NOT IN ({excluded_csv})
        GROUP BY gp.group_id
    """, conn)


def fetch_cohort_patients(conn, excluded_csv: str) -> pd.DataFrame:
    """
    One row per (cohort, patient) membership — the base population for all
    per-cohort follow-up calculations. "enrolled" is that specific cohort's
    from_date (falls back to created_date), i.e. cohort entry for that
    membership, not a patient-wide earliest-across-cohorts date.
    """
    return pd.read_sql(f"""
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
        WHERE gp.group_id NOT IN ({excluded_csv})
    """, conn)


def fetch_all_cohort_demographics(conn) -> pd.DataFrame:
    """
    RADAR demographics for every non-test/control patient — used for
    cohort-level completeness (Section A uses fetch_section_a_demographics
    instead, scoped to its own excluded-group filter).
    """
    return pd.read_sql("""
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


def fetch_primary_renal_diagnoses(conn, excluded_csv: str) -> pd.DataFrame:
    """
    (patient_id, group_id) pairs where the patient has a Primary Renal
    Diagnosis recorded against that specific cohort — a diagnosis_id
    matching a group_diagnoses row with type='PRIMARY' for that group.
    """
    return pd.read_sql(f"""
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
        WHERE gp.group_id NOT IN ({excluded_csv})
    """, conn)


def fetch_kidney_failure_dates(conn) -> pd.DataFrame:
    """
    patient_id -> earliest Kidney Failure (KF/KRT) date: transplant date,
    dialysis from_date, or eGFR<15 confirmed twice >=28 days apart with no
    recovery (eGFR>=15) in between. Based on RaDaR data only — not linked
    to UKRR.
    """
    df = pd.read_sql("""
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
            -- KF confirmation date = date of the 2nd qualifying reading (>=28 days after the 1st)
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
    # this pipeline, so downstream comparisons don't mix aware/naive timestamps.
    df["kf_date"] = pd.to_datetime(df["kf_date"], errors="coerce", utc=True).dt.tz_localize(None)
    return df


def fetch_creatinine_results(conn) -> pd.DataFrame:
    """One row per patient per day with a recorded creatinine result (observation_id 46)."""
    df = pd.read_sql("""
        SELECT DISTINCT patient_id, date::date AS result_date
        FROM results
        WHERE observation_id = 46
          AND value IS NOT NULL
          AND value::text <> ''
    """, conn)
    df["result_date"] = pd.to_datetime(df["result_date"], errors="coerce")
    return df


def fetch_proteinuria_results(conn) -> pd.DataFrame:
    """One row per patient per day with a recorded ACR (1) or PCR (2) result."""
    df = pd.read_sql("""
        SELECT DISTINCT patient_id, date::date AS result_date
        FROM results
        WHERE observation_id IN (1, 2)
          AND value IS NOT NULL
          AND value::text <> ''
    """, conn)
    df["result_date"] = pd.to_datetime(df["result_date"], errors="coerce")
    return df


def fetch_transplant_counts(conn) -> pd.DataFrame:
    """patient_id -> number of distinct transplant dates recorded."""
    return pd.read_sql("""
        SELECT patient_id, COUNT(DISTINCT date) AS transplant_count
        FROM transplants
        GROUP BY patient_id
    """, conn)
