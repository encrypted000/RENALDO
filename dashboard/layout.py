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
            "This page provides an interactive summary of data completeness for variables "
            "collected in the ",
            html.Strong("The National Registry of Rare Kidney Diseases (RaDaR)"),
            ", a national registry for patients with rare kidney diseases in the UK, "
            "managed by ",
            html.Strong("The UK Kidney Association (UKKA)"),
            ". RaDaR brings together clinical data from renal units across the UK to "
            "support research, clinical audit, and the improvement of care for patients "
            "with rare and complex kidney conditions.",
        ], style={"marginBottom": "10px"}),

        html.P([
            "Data completeness has been calculated for each variable across all patients "
            "currently registered in RaDaR. A variable is considered missing if it has "
            "not been recorded for a patient where it would be expected. For example, ",
            html.Em("cause of death"),
            " is only assessed among patients with a recorded date of death. "
            "Variables marked ",
            html.Span("Required", style={
                "fontSize":     "10px",
                "fontWeight":   "600",
                "background":   "rgba(0,0,0,0.1)",
                "padding":      "1px 6px",
                "borderRadius": "10px",
            }),
            " are those that must be collected for every registered patient "
            "as part of the RaDaR minimum dataset.",
        ], style={"marginBottom": "10px"}),

        html.P([
            "The following sections cover ",
            html.Strong("Overall RaDaR"),
            " and all ",
            html.Strong("33 disease cohort groups"),
            " currently active in RaDaR. "
            "Each variable is colour-coded by the percentage of missing values — "
            "green indicates good completeness, while orange and red highlight variables "
            "where data collection requires attention.",
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