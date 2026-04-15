"""
data_callbacks.py
------------------
Handles loading completeness.json and populating the data store.
Triggered on page load and when the Refresh button is clicked.
"""

import json
import os
import logging
from datetime import datetime

from dash import callback, Input, Output

logger = logging.getLogger(__name__)


def _load_json() -> list | None:
    """Load completeness.json from the output folder."""
    path = "output/completeness.json"
    if not os.path.exists(path):
        logger.warning(f"completeness.json not found at {path}")
        return None
    with open(path) as f:
        return json.load(f)


def _total_patients(data: list) -> str:
    """Extract max patient total from all variables."""
    all_vars = [v for sec in data for v in sec.get("variables", [])]
    total = max((v.get("total", 0) for v in all_vars), default=0)
    return f"{total:,}"


@callback(
    Output("data-store",         "data"),
    Output("last-updated",       "children"),
    Output("total-patients-hdr", "children"),
    Output("refresh-time",       "children"),
    Input("refresh-btn",         "n_clicks"),
    prevent_initial_call=False,
)
def load_data(_n_clicks):
    data = _load_json()
    if not data:
        return None, "No data found", "—", "Run: python -m analytics.demographics_completeness"
    now       = datetime.now().strftime("%d/%m/%Y %H:%M")
    total_str = _total_patients(data)
    return data, now, total_str, f"Last loaded: {now}"
