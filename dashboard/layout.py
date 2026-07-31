from dash import html, dcc
import dash_bootstrap_components as dbc
from dashboard.components.header import create_header
from dashboard.components.legend import create_legend


def _divider(label: str) -> html.Div:
    return html.Div([
        html.Div(style={"flex": "1", "height": "1px", "background": "#e2e6ea"}),
        html.Span(label, style={
            "fontSize": "11px", "fontWeight": "600",
            "color": "#8a97a8", "textTransform": "uppercase",
            "letterSpacing": "0.08em", "whiteSpace": "nowrap",
            "padding": "0 12px",
        }),
        html.Div(style={"flex": "1", "height": "1px", "background": "#e2e6ea"}),
    ], style={"display": "flex", "alignItems": "center", "margin": "28px 0 16px"})


def _description_box() -> html.Div:
    return html.Div([

        html.P([
            "This page provides an interactive summary of data completeness for key "
            "variables collected within the National Registry of Rare Kidney Diseases "
            "(RaDaR), a UK-wide registry owned and managed by the UK Kidney Association "
            "(UKKA).",
        ], style={"marginBottom": "10px"}),

        html.P([
            "Data completeness has been assessed for each variable across all patients. "
            "A variable is considered missing when no value has been recorded for a "
            "patient for whom that information would be expected. Variables designated "
            "as Required form part of the RaDaR minimum dataset and should be completed "
            "for every patient.",
        ], style={"marginBottom": "10px"}),

        html.P([
            "This dashboard presents data completeness for the overall RaDaR cohort and "
            "for each of the 33 active Rare Disease Groups (RDGs). Variables are "
            "colour-coded according to the percentage of missing values: green indicates "
            "high data completeness, while orange and red indicate lower levels of data "
            "completeness. As RaDaR relies on data submitted by participating kidney "
            "units as part of routine clinical practice, variation in completeness is "
            "expected and may reflect differences in local capacity, resourcing, and "
            "clinical priorities, rather than data quality alone.",
        ]),

    ], style={
        "background":   "#ffffff",
        "border":       "1px solid #e2e6ea",
        "borderLeft":   "4px solid #1a6fa8",
        "borderRadius": "10px",
        "padding":      "18px 20px",
        "marginBottom": "24px",
        "fontSize":     "13px",
        "color":        "#4a5568",
        "lineHeight":   "1.7",
        "boxShadow":    "0 1px 3px rgba(0,0,0,0.06)",
    })


def create_layout():
    return html.Div([

        create_header(),

        html.Div([

            html.Div(
                html.Span(id="refresh-time", className="refresh-time"),
                className="mt-3 mb-3",
            ),

            _description_box(),

            html.Div(id="summary-cards", className="mb-3"),

            create_legend(),

            _divider("Overall RaDaR"),

            html.Div(id="accordion-content", className="mt-2"),

            html.Div([
                html.Strong("RaDaR Data Completeness Dashboard"),
                " · UK Kidney Association · ",
                "Completeness calculated for RADAR source records only, "
                "excluding test and control patients. "
                "Death-related fields calculated among deceased patients only.",
            ], className="footer mt-5 mb-4"),

        ], className="main"),

        dcc.Store(id="data-store"),

    ], id="page-wrapper")