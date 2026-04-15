from dash import html
import dash_bootstrap_components as dbc


def build_summary_cards(data: list):
    all_vars       = [v for sec in data for v in sec.get("variables", [])]
    total_patients = max((v.get("total", 0) for v in all_vars), default=0)
    complete_vars  = sum(1 for v in all_vars
                        if v.get("pct_missing") is not None and v["pct_missing"] < 20)
    partial_vars   = sum(1 for v in all_vars
                        if v.get("pct_missing") is not None
                        and 20 <= v["pct_missing"] < 60)
    attention_vars = sum(1 for v in all_vars
                        if v.get("pct_missing") is not None and v["pct_missing"] >= 60)

    demo_sec  = next((s for s in data if s.get("section") == "A"), {})
    stats     = demo_sec.get("stats", {})
    adults    = stats.get("adults",    0)
    children  = stats.get("children",  0)
    def card(label, value, sub, cls, icon):
        return dbc.Col(dbc.Card([
            html.Div(icon, className="card-icon"),
            html.Div(label, className="card-label"),
            html.Div(value, className="card-value"),
            html.Div(sub,   className="card-sub"),
        ], className=f"summary-card {cls}"), width=2)

    return dbc.Row([
        card("Total patients",     f"{total_patients:,}",
             "RaDaR · excl. test & control", "highlight", "👥"),
        card("Adults",             f"{adults:,}",
             "patients aged ≥ 18",           "s-info",    "🧑"),
        card("Children",           f"{children:,}",
             "patients aged < 18",           "s-info",    "🧒"),
        card("Fully complete",     str(complete_vars),
             "variables < 20% missing",      "s-success", "✓"),
        card("Partially complete", str(partial_vars),
             "variables 20–60% missing",     "s-warning",  "!"),
        card("Need attention",     str(attention_vars),
             "variables > 60% missing",      "s-danger",   "⚠"),
    ], className="g-3")
