from dash import html, dcc
import dash_bootstrap_components as dbc
from dashboard.components.header import create_header
from dashboard.components.legend import create_legend


def _divider(label: str) -> html.Div:
    return html.Div([
        html.Div(className="section-divider-line"),
        html.Span(label, className="section-divider-label"),
        html.Div(className="section-divider-line"),
    ], className="section-divider")


def _description_box() -> html.Div:
    return html.Div([

        html.P(
            "The National Registry of Rare Kidney Disease (RaDaR) is a UK-wide registry "
            "owned and managed by the UK Kidney Association (UKKA)."
        ),

        html.P([
            html.Strong("RENALDO"),
            " has been developed to help everyone with an interest in RaDaR's real-world "
            "data better understand the scope, characteristics and completeness of KEY "
            "information held within the registry. The dashboard provides an interactive "
            "overview of selected data fields collected within RaDaR.",
        ]),

        html.P("The dashboard includes:", className="info-box-lead"),

        html.Ul([
            html.Li("An overview of selected data fields and their completeness across the registry."),
            html.Li("Summary information about all active Rare Disease Groups (RDGs)."),
            html.Li("Visual summaries of the availability and completeness of key demographic, "
                    "clinical and outcome data."),
        ], className="info-box-list"),

        html.P(
            "Data completeness is assessed by considering whether information expected to be "
            "recorded for a participant is present within the registry. Variables identified "
            "as required (REQ) form part of the RaDaR minimum dataset and are expected to be "
            "completed for all participants."
        ),

        html.P(
            "As RaDaR relies on information submitted by participating centres as part of "
            "routine clinical practice, differences in data availability and completeness are "
            "expected. These variations may reflect local priorities, capacity and resources, "
            "rather than data quality alone."
        ),

        html.P(
            "RENALDO aims to provide a transparent and accessible overview of the data held "
            "within RaDaR, helping users understand the registry's strengths, coverage and "
            "potential applications for research."
        ),

    ], className="info-box")


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

            html.Div(id="demo-content", className="mt-2"),

            # Static so the search box keeps focus while typing — only the
            # label text (with the match count) is updated by the callback.
            html.Div([
                html.Div(className="section-divider-line"),
                html.Span("Cohort Groups", id="cohort-divider-label", className="section-divider-label"),
                html.Div(className="section-divider-line"),
            ], className="section-divider"),

            html.Div([
                dcc.Input(
                    id="cohort-search",
                    type="search",
                    value="",
                    placeholder="Search cohorts or variables, e.g. IgA",
                    className="cohort-search-input",
                    debounce=False,
                    autoComplete="off",
                    spellCheck=False,
                ),
            ], className="cohort-search-wrap"),

            html.Div(id="cohort-content", className="mt-2"),

            html.Div([
                html.Strong("RaDaR Data Completeness Dashboard"),
                " is maintained by the UK Kidney Association.",
                html.Br(),
                "Completeness is calculated from RADAR source records only, excluding test and "
                "control patients; death-related fields are calculated among deceased patients only.",
            ], className="footer mt-5 mb-4"),

        ], className="main"),

        dcc.Store(id="data-store"),

    ], id="page-wrapper")