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
            "This page provides an interactive summary of data completeness for key "
            "variables collected within the National Registry of Rare Kidney Diseases "
            "(RaDaR), a UK-wide registry owned and managed by the UK Kidney Association "
            "(UKKA)."
        ),

        html.P(
            "Data completeness has been assessed for each variable across all patients. "
            "A variable is considered missing when no value has been recorded for a "
            "patient for whom that information would be expected. Variables designated "
            "as Required form part of the RaDaR minimum dataset and should be completed "
            "for every patient."
        ),

        html.P(
            "This dashboard presents data completeness for the overall RaDaR cohort and "
            "for each of the 33 active Rare Disease Groups (RDGs). Variables are "
            "colour-coded according to the percentage of missing values: green indicates "
            "high data completeness, while orange and red indicate lower levels of data "
            "completeness. As RaDaR relies on data submitted by participating kidney "
            "units as part of routine clinical practice, variation in completeness is "
            "expected and may reflect differences in local capacity, resourcing, and "
            "clinical priorities, rather than data quality alone."
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