# RaDaR Data Completeness Dashboard

Interactive dashboard showing data completeness for the Rare Disease Registry (RaDaR),
managed by the UK Kidney Association.

## Project Structure

```
RaDaR_completeness/
  app.py                              ← starts the Dash app
  config/
    settings.py                       ← SSH tunnel + DB connection
    demographics.py                   ← demographics variable definitions
  analytics/
    utils.py                          ← shared calculation functions
    demographics_completeness.py      ← calculates completeness, writes JSON
  dashboard/
    __init__.py                       ← creates the Dash app
    layout.py                         ← assembles the full page
    components/
      header.py                       ← page header
      legend.py                       ← colour key
      summary_cards.py                ← 4 metric cards
      table.py                        ← colour-coded data table
      accordion.py                    ← collapsible sections
    callbacks/
      data_callbacks.py               ← load + refresh data
      render_callbacks.py             ← render content from store
    assets/
      style.css                       ← all CSS
  tests/
    test_analytics.py                 ← unit tests for calculations
    test_connection.py                ← DB connection tests
  output/
    completeness.json                 ← generated, never edit manually
  logs/
    radar.log                         ← application logs
```

## Setup

### 1. Environment variables (run once)
```
setx RADAR_DB_HOST "localhost"
setx RADAR_DB_PORT "5432"
setx RADAR_DB_NAME "radar"
setx RADAR_DB_USER "radar_ro"
setx RADAR_DB_PASS "your_password"
setx RADAR_SSH_HOST "db.radar.nhs.uk"
setx RADAR_SSH_PORT "22"
setx RADAR_SSH_USER "bidhanp"
setx RADAR_SSH_KEY "C:\Users\bidhan.pant\.ssh\id_rsa"
```
Close and reopen your terminal after running these.

### 2. Install dependencies
```
pip install -r requirements.txt
```

### 3. Run analytics (generates the data)
```
python -m analytics.demographics_completeness
```

### 4. Start the dashboard
```
python app.py
```
Open your browser at: http://localhost:8050

## Daily Usage

```
# Step 1 — refresh data from database
python -m analytics.demographics_completeness

# Step 2 — start dashboard
python app.py
```

Or just click "Refresh data" in the dashboard to reload from the last generated JSON.

## Running Tests

```
# Unit tests (no DB needed)
python -m pytest tests/test_analytics.py -v

# Connection tests (requires DB access)
python -m pytest tests/test_connection.py -v

# All tests
python -m pytest tests/ -v
```

## Adding a New Cohort

1. Add variable definitions to `config/cohorts.py` (create this file)
2. Create `analytics/cohort_completeness.py` for the calculation
3. The dashboard accordion automatically picks up new sections from `completeness.json`

## Data Rules

- Only `source_type = 'RADAR'` records are included
- Patients where `test = TRUE` or `control = TRUE` are excluded
- Email completeness excludes a list of known placeholder emails (see `config/demographics.py`)
- NHS number completeness checks `patient_numbers` table
- Diagnosis completeness checks `patient_diagnoses` table
