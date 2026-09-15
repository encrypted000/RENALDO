"""
render_callbacks.py
"""
import logging
from dash import callback, Input, Output, html, ctx
from dashboard.components.summary_cards import build_summary_cards
from dashboard.components.accordion import (
    build_accordion,
    build_accordion_expanded,
    build_accordion_collapsed,
)

logger = logging.getLogger(__name__)


@callback(
    Output("summary-cards",  "children"),
    Output("demo-content",   "children"),
    Output("cohort-content", "children"),
    Input("data-store",      "data"),
    Input("expand-btn",      "n_clicks"),
    Input("collapse-btn",    "n_clicks"),
    Input("cohort-search",   "value"),
)
def render_content(data, _expand, _collapse, search):
    if not data:
        return (
            html.Div(),
            html.Div(),
            html.Div([
                html.Div("⚠", style={"fontSize": "32px", "marginBottom": "12px"}),
                html.Strong("No data found"),
                html.Br(), html.Br(),
                html.Span("Run the analytics script first:"),
                html.Br(),
                html.Code(
                    "python -m analytics.run_all",
                    style={"background": "var(--surface-2)", "padding": "4px 8px",
                           "borderRadius": "4px", "fontSize": "12px"},
                ),
            ], className="state-box"),
        )

    logger.info(f"Rendering — triggered by: {ctx.triggered_id}")

    if ctx.triggered_id == "expand-btn":
        demo, divider, cohorts = build_accordion_expanded(data, search)
    elif ctx.triggered_id == "collapse-btn":
        demo, divider, cohorts = build_accordion_collapsed(data, search)
    else:
        # Default (including a search-box edit) — demographics open, cohorts
        # collapsed except for any cohort the search term matches.
        demo, divider, cohorts = build_accordion(data, search)

    return build_summary_cards(data), demo, html.Div([divider, cohorts])