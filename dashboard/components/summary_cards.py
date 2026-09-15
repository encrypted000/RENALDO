from dash import html
import dash_bootstrap_components as dbc


def build_summary_cards(data: list):
    all_vars       = [v for sec in data for v in sec.get("variables", [])]
    total_patients = max((v.get("total", 0) for v in all_vars), default=0)

    demo_sec  = next((s for s in data if s.get("section") == "A"), {})
    stats     = demo_sec.get("stats", {})
    adults    = stats.get("adults",    0)
    children  = stats.get("children",  0)
    def card(label, value, sub, cls=""):
        return dbc.Col(dbc.Card([
            html.Div(label, className="card-label"),
            html.Div(value, className="card-value"),
            html.Div(sub,   className="card-sub"),
        ], className=f"summary-card {cls}".strip()), xs=6, sm=4, lg=4)

    return dbc.Row([
        card("Total patients", f"{total_patients:,}", "RaDaR patients, excluding test & control", "highlight"),
        card("Adults",         f"{adults:,}",         "patients aged ≥ 18"),
        card("Children",       f"{children:,}",       "patients aged < 18"),
    ], className="g-2")
