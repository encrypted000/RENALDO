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
    Output("summary-cards",     "children"),
    Output("accordion-content", "children"),
    Input("data-store",         "data"),
    Input("expand-btn",         "n_clicks"),
    Input("collapse-btn",       "n_clicks"),
)
def render_content(data, _expand, _collapse):
    if not data:
        return (
            html.Div(),
            html.Div([
                html.Div("⚠", style={"fontSize": "32px", "marginBottom": "12px"}),
                html.Strong("No data found"),
                html.Br(), html.Br(),
                html.Span("Run the analytics script first:"),
                html.Br(),
                html.Code(
                    "python -m analytics.demographics_completeness",
                    style={"background": "#f0efe9", "padding": "4px 8px",
                           "borderRadius": "4px", "fontSize": "12px"},
                ),
            ], className="state-box"),
        )

    logger.info(f"Rendering — triggered by: {ctx.triggered_id}")

    if ctx.triggered_id == "expand-btn":
        return build_summary_cards(data), build_accordion_expanded(data)

    if ctx.triggered_id == "collapse-btn":
        return build_summary_cards(data), build_accordion_collapsed(data)

    # Default — demographics open, cohorts collapsed
    return build_summary_cards(data), build_accordion(data)