# RENALDO
### RarE kidNey dAta compLeteness DashbOard

> An interactive data completeness monitoring dashboard for the [RaDaR](https://www.radar.nhs.uk) (Rare Disease Registry) — managed by the **UK Kidney Association**.

🔗 **Live dashboard:** [renaldo.onrender.com](https://renaldo.onrender.com)

---

## What is RENALDO?

RENALDO monitors the quality and completeness of patient data across **33 rare kidney disease cohorts** in the RaDaR registry. It helps data managers and clinicians quickly identify where data collection needs improvement — using colour-coded completeness scores across all key variables.

### Key Features

- **Overall RaDaR view** — demographics completeness across all 39,000+ patients
- **33 cohort sections** — per-cohort breakdown including adults, children, follow-up
- **Kidney Failure metrics** — patients with evidence of KF (transplant, dialysis, or eGFR < 15)
- **Transplant tracking** — single vs multiple transplant patients
- **Colour-coded tables** — instant visual identification of data gaps
- **Static JSON deployment** — no live DB connection required to view

---

## Dashboard Preview

| Colour | Meaning |
|--------|---------|
| 🟢 Green | 0–20% missing — good |
| 🟡 Yellow-green | 20–40% missing — acceptable |
| 🟡 Yellow | 40–60% missing — needs attention |
| 🟠 Orange | 60–80% missing — poor |
| 🔴 Red | 80–100% missing — critical |

---

## Project Structure

```
RENALDO/
├── app.py                          ← Dash app entry point
├── requirements.txt
├── output/
│   └── completeness.json           ← generated data (never edit manually)
├── analytics/
│   ├── run_all.py                  ← main script — runs everything in one go
│   ├── demographics_completeness.py
│   ├── cohorts_completeness.py
│   └── utils.py
├── config/
│   ├── settings.py                 ← SSH tunnel + DB connection (uses env vars)
│   ├── demographics.py             ← demographics variable definitions
│   └── cohorts.py                  ← excluded group IDs + cohort letters
├── dashboard/
│   ├── __init__.py
│   ├── layout.py
│   ├── assets/
│   │   └── style.css
│   ├── components/
│   │   ├── accordion.py
│   │   ├── header.py
│   │   ├── legend.py
│   │   ├── summary_cards.py
│   │   └── table.py
│   └── callbacks/
│       ├── data_callbacks.py
│       └── render_callbacks.py
└── tests/
    ├── test_analytics.py
    └── test_connection.py
```

---

## Local Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set environment variables
The analytics pipeline connects to RaDaR via SSH tunnel. Set these once:
```bash
setx RADAR_SSH_HOST "your_ssh_host"
setx RADAR_SSH_PORT "22"
setx RADAR_SSH_USER "your_username"
setx RADAR_SSH_KEY "C:\path\to\your\id_rsa"
setx RADAR_DB_PORT "5432"
setx RADAR_DB_NAME "radar"
setx RADAR_DB_USER "your_db_user"
setx RADAR_DB_PASS "your_db_password"
```
Close and reopen your terminal after setting these.

### 3. Generate the data
```bash
python -m analytics.run_all
```
This opens an SSH tunnel, queries the database, and writes `output/completeness.json`.

### 4. Start the dashboard
```bash
python app.py
```
Open: [http://localhost:8050](http://localhost:8050)

---

## Updating the Live Dashboard

The hosted dashboard reads from `output/completeness.json`. To update it:

```bash
# Step 1 — refresh data from database
python -m analytics.run_all

# Step 2 — push to GitHub (Render auto-redeploys)
git add output/completeness.json
git commit -m "Update completeness data"
git push
```

---

## Data Rules

| Rule | Detail |
|------|--------|
| Source | Only `source_type = 'RADAR'` records |
| Excluded patients | `test = TRUE` or `control = TRUE` |
| Excluded cohorts | NURTuRE-CKD, NephroS, NaHUS, withdrawn consent, and other non-standard groups |
| Email completeness | Excludes known placeholder/default emails |
| NHS number | Checked against `patient_numbers` table |
| Diagnosis | Checked against `patient_diagnoses` table |
| Kidney Failure | Transplant OR dialysis OR eGFR < 15 confirmed twice ≥ 28 days apart |
| Follow-up | Enrolment to last activity (results/medications) or date of death |
| Enrolment date | `group_patients.from_date` (matches "Recruited On" in RaDaR front end) |

---

## Running Tests

```bash
# Unit tests — no DB needed
python -m pytest tests/test_analytics.py -v

# Connection tests — requires DB access
python -m pytest tests/test_connection.py -v
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Dashboard | [Plotly Dash](https://dash.plotly.com/) |
| UI components | [Dash Bootstrap Components](https://dash-bootstrap-components.opensource.faculty.ai/) |
| Data processing | [pandas](https://pandas.pydata.org/) |
| Database | PostgreSQL via SSH tunnel (psycopg2 + sshtunnel) |
| Hosting | [Render](https://render.com) |

---

## Organisation

**UK Kidney Association** — [ukkidney.org](https://ukkidney.org)

RaDaR is a national registry for rare kidney diseases, collecting longitudinal data on patients across the UK.
