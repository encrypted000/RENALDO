# RENALDO — Data Completeness Report
### RarE kidNey dAta compLeteness DashbOard
**UK Kidney Association · RaDaR Registry**
**Version:** 1.0 — April 2026
**Dashboard:** [renaldo.onrender.com](https://renaldo.onrender.com)

---

## 1. Background

The **National Registry of Rare Kidney Diseases (RaDaR)** is a national registry collecting longitudinal clinical data on patients with rare and complex kidney conditions across the UK. It is managed by the **UK Kidney Association (UKKA)** and brings together data from renal units across England, Wales, Scotland, and Northern Ireland.

RaDaR currently holds records for over **39,000 patients** across **33 disease cohort groups**. As with any large clinical registry, the quality and completeness of the data varies across sites and cohorts. Poor completeness limits the scientific and clinical value of the registry.

**RENALDO** (RarE kidNey dAta compLeteness DashbOard) was developed to provide a clear, regularly updated view of data completeness across the entire RaDaR dataset — enabling data managers, cohort leads, and the UKKA to quickly identify where data collection requires improvement.

---

## 2. Patient Population

### 2.1 Inclusion Criteria

Only patients meeting **all** of the following criteria are included in the analysis:

| Criterion | Rule |
|-----------|------|
| Source | Demographics record must have `source_type = 'RADAR'` |
| Patient type | `test = FALSE` and `control = FALSE` |
| Group type | Must be enrolled in a group of type `COHORT` |
| Excluded cohorts | Must **not** belong to any of the excluded group IDs (see Section 2.2) |

### 2.2 Excluded Cohorts

The following cohort groups are **excluded** from all calculations. These are either non-standard groups, administrative groups, or cohorts not part of the core RaDaR rare kidney disease dataset:

| Group ID | Reason for Exclusion |
|----------|----------------------|
| 137 | NURTuRE-CKD |
| 149 | NephroS |
| 152 | NaHUS |
| 18, 19 | Administrative / legacy groups |
| 161, 174, 182, 184, 194, 140, 220, 222 | Withdrawn consent / non-standard groups |

### 2.3 Total Patient Count

After applying all inclusion and exclusion criteria, the total analysed population is:

> **N = 39,178 patients**

This is the **denominator** used for all overall (Section A) completeness calculations.

---

## 3. Variables Assessed

### 3.1 Demographic Variables (assessed for all patients)

| ID | Variable | Required | Source |
|----|----------|----------|--------|
| A.1 | First Name | Yes | `patient_demographics.first_name` |
| A.2 | Last Name | Yes | `patient_demographics.last_name` |
| A.3 | Date of Birth | Yes | `patient_demographics.date_of_birth` |
| A.4 | Date of Death | No | `patient_demographics.date_of_death` |
| A.5 | Cause of Death | No | `patient_demographics.cause_of_death` |
| A.6 | Gender | Yes | `patient_demographics.gender` |
| A.7 | Ethnicity | Yes | `patient_demographics.ethnicity_id` |
| A.8 | Nationality | Yes | `patient_demographics.nationality_id` |
| A.9 | Email Address | No | `patient_demographics.email_address` |
| A.10 | Diagnosis | Yes | `patient_diagnoses` table (any record present) |
| A.11 | NHS Number | Yes | `patient_numbers` table (any record present) |

Variables marked **Required** are part of the RaDaR minimum dataset and should be present for every registered patient.

### 3.2 Clinical Summary Rows (not completeness variables)

These rows appear in each section but show **counts rather than % missing**, so they are not included in the completeness score calculation:

| Row | What it shows |
|-----|--------------|
| TOTAL_PATIENTS | Total patients enrolled in that cohort |
| ADULTS | Patients aged ≥ 18 at time of analysis |
| CHILDREN | Patients aged < 18 at time of analysis |
| KIDNEY_FAILURE | Patients with evidence of kidney failure (see Section 5) |
| TRANSPLANT_SINGLE | Patients with exactly one transplant |
| TRANSPLANT_MULTIPLE | Patients with two or more transplants |
| FOLLOW_UP | Median follow-up duration in years (see Section 6) |

---

## 4. Completeness Calculations

### 4.1 Variable-Level % Missing

For each variable and each cohort, the percentage of missing values is calculated as:

$$\text{\% Missing} = \frac{\text{Number of patients with no recorded value}}{\text{Total patients in cohort}} \times 100$$

A value is considered **missing** if it is:
- `NULL` in the database, or
- An empty string after stripping whitespace

**Special cases:**

**Cause of Death** — denominator is restricted to deceased patients only, as it is not meaningful to assess this field for living patients:

$$\text{\% Missing (Cause of Death)} = \frac{\text{Deceased patients with no cause of death recorded}}{\text{Total deceased patients}} \times 100$$

**Email Address** — a list of 46 known placeholder and default email addresses (e.g. `radar@radar.org`, `noemailaddress@radar.radar`) is maintained. Any patient whose email matches one of these placeholders is treated as missing, even though a value technically exists in the database:

$$\text{Missing email} = \text{NULL email} + \text{email} \in \text{placeholder list}$$

**NHS Number** — checked by the presence of any record for that patient in the `patient_numbers` table, not the demographics row itself.

**Diagnosis** — checked by the presence of any record for that patient in the `patient_diagnoses` table.

### 4.2 Colour Coding

Each variable row is colour-coded based on its % missing value:

| Colour | % Missing | Interpretation |
|--------|-----------|----------------|
| Green | 0 – 20% | Good completeness |
| Yellow-green | 20 – 40% | Acceptable |
| Yellow | 40 – 60% | Needs attention |
| Orange | 60 – 80% | Poor |
| Red | 80 – 100% | Critical |

### 4.3 Section-Level % Complete (accordion header)

Each section header displays an overall completeness percentage. This is calculated as:

$$\text{Section \% Complete} = 100 - \frac{\sum_{i=1}^{n} \text{\% Missing}_{i}}{n}$$

Where **n** is the number of variables in that section that **have a % missing value** (i.e. the 11 demographic variables only — TOTAL_PATIENTS, FOLLOW_UP, KF, and Transplant rows are excluded as they carry counts, not completeness figures).

**Example:** If a cohort has 11 demographic variables with % missing values of:
`0, 2, 5, 10, 15, 30, 45, 60, 70, 80, 90`

$$\text{Average \% Missing} = \frac{0+2+5+10+15+30+45+60+70+80+90}{11} = \frac{407}{11} \approx 37\%$$

$$\text{Section \% Complete} = 100 - 37 = \textbf{63\%}$$

> **Note:** This is an unweighted average — every variable contributes equally regardless of how many patients it applies to. It is intended as a quick visual indicator, not a weighted audit score.

---

## 5. Kidney Failure Definition

A patient is classified as having **Kidney Failure (KF)** if they meet **any** of the following criteria, based on data recorded in RaDaR:

| Criterion | Definition |
|-----------|-----------|
| Transplant | Any record in the `transplants` table |
| Dialysis | Any record in the `dialysis` table |
| eGFR < 15 | Two or more eGFR readings below 15 ml/min/1.73m², recorded **≥ 28 days apart**, with **no eGFR ≥ 15** recorded between the first and last low reading |

The eGFR criterion uses observation ID 47 in the `results` table.

**Important:** KF classification is based **solely on RaDaR data** and is **not linked** to the UK Renal Registry (UKRR). Patients who are on dialysis or have had a transplant managed entirely outside of RaDaR-linked units will not be captured.

### 5.1 Transplant Counting

Transplants are counted per patient using `COUNT(DISTINCT date)` from the `transplants` table — i.e. each unique transplant date counts as one transplant. Patients are then split into:

- **Single transplant:** exactly 1 distinct transplant date
- **Multiple transplants:** 2 or more distinct transplant dates

---

## 6. Follow-Up Calculation

Follow-up measures the duration of a patient's active monitoring in RaDaR, expressed in years.

### 6.1 Formula

$$\text{Follow-up (years)} = \frac{\text{End Date} - \text{Enrolment Date}}{365.25}$$

**Enrolment Date** = `group_patients.from_date` for that cohort (the "Recruited On" date visible in the RaDaR front end). If this is null, the earliest cohort membership date across all cohorts is used as a fallback.

**End Date** is determined by the following hierarchy:

```
1. Date of death          (if the patient is deceased)
2. Last activity date     (latest date from results or medications tables)
3. Today's date           (if no activity has ever been recorded)
```

The dashboard reports the **median follow-up** and **interquartile range (IQR)** for each section.

### 6.2 Special Cases

| Situation | How it is handled |
|-----------|------------------|
| Last activity date is **before** enrolment date | Treated as a historical batch data upload — end date set to today |
| Date of death is **before** enrolment date | Genuine data entry error — patient **excluded** from follow-up |
| No enrolment date available | Follow-up cannot be calculated — patient excluded from median |

### 6.3 Known Data Quality Issue

Across the full RaDaR dataset, approximately **18 patients** have a date of death recorded earlier than their enrolment date. This is a data entry error in RaDaR — the death date has been entered incorrectly at the enrolling unit. These patients are excluded from the follow-up calculation and a warning is logged each time the data is regenerated. Correcting these dates in the RaDaR front end would restore these patients to the follow-up analysis automatically.

---

## 7. Dashboard Architecture

### 7.1 Data Pipeline

The dashboard operates on a **static JSON** model — there is no live database connection on the hosted version:

```
1. run_all.py runs locally
      └─ Opens SSH tunnel to RaDaR PostgreSQL database
      └─ Runs all queries (demographics, cohort counts, follow-up, KF, transplants)
      └─ Writes output/completeness.json

2. completeness.json is committed to GitHub

3. Render.com auto-deploys from GitHub
      └─ Dashboard reads completeness.json at startup
      └─ No database credentials required on the server
```

### 7.2 Update Frequency

The dashboard is updated **manually** by running `python -m analytics.run_all` and pushing the resulting JSON file to GitHub. Render redeploys automatically within ~2 minutes of each push.

### 7.3 Technology Stack

| Component | Technology |
|-----------|-----------|
| Dashboard framework | Plotly Dash (Python) |
| UI components | Dash Bootstrap Components (Bootstrap 5) |
| Data processing | pandas |
| Database connection | PostgreSQL via SSH tunnel (psycopg2 + sshtunnel) |
| Hosting | Render.com |
| Version control | GitHub — [encrypted000/RENALDO](https://github.com/encrypted000/RENALDO) |

---

## 8. Limitations

1. **Static data** — the dashboard reflects the state of RaDaR at the time `run_all.py` was last executed. It does not update in real time.

2. **RaDaR-only KF classification** — kidney failure status is derived from RaDaR records only. Patients receiving renal replacement therapy outside RaDaR-linked pathways will be missed.

3. **Unweighted completeness score** — the section % complete is a simple average across variables and does not weight by variable importance or patient count.

4. **Email placeholder list** — the list of placeholder emails is maintained manually. New placeholder addresses added to RaDaR after the last update of this list will not be treated as missing.

5. **Follow-up based on last activity** — follow-up end date is the latest entry in the `results` or `medications` tables. Patients who are alive and enrolled but have had no results or medications recorded will appear to have follow-up ending today, which may overestimate their true active monitoring period.

---

## 9. Glossary

| Term | Definition |
|------|-----------|
| RaDaR | National Registry of Rare Kidney Diseases |
| UKKA | UK Kidney Association |
| RENALDO | RarE kidNey dAta compLeteness DashbOard |
| Completeness | The proportion of expected values that have been recorded |
| % Missing | Patients with no recorded value ÷ total patients × 100 |
| KF | Kidney Failure |
| eGFR | Estimated Glomerular Filtration Rate (measure of kidney function) |
| IQR | Interquartile Range — the range between the 25th and 75th percentile |
| SSH Tunnel | Secure encrypted connection used to access the RaDaR database |
| Source type RADAR | Records entered directly into RaDaR (as opposed to imported from other systems) |

---

*Report prepared by the UK Kidney Association data team. Dashboard source code available at [github.com/encrypted000/RENALDO](https://github.com/encrypted000/RENALDO).*
