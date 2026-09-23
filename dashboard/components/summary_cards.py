from dash import html


def build_summary_cards(data: list):
    all_vars       = [v for sec in data for v in sec.get("variables", [])]
    total_patients = max((v.get("total", 0) for v in all_vars), default=0)

    demo_sec  = next((s for s in data if s.get("section") == "A"), {})
    stats     = demo_sec.get("stats", {})
    adults    = stats.get("adults",    0)
    children  = stats.get("children",  0)

    def stat(label, value, sub, cls=""):
        return html.Div([
            html.Div(label, className="card-label"),
            html.Div(value, className="card-value"),
            html.Div(sub,   className="card-sub"),
        ], className=f"stat-group {cls}".strip())

    return html.Div([
        stat("Total patients", f"{total_patients:,}", "RaDaR patients, excluding test & control", "primary"),
        stat("Adults",         f"{adults:,}",         "patients aged ≥ 18"),
        stat("Children",       f"{children:,}",       "patients aged < 18"),
    ], className="stat-strip")
