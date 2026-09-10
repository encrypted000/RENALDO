from dash import html

LEGEND_ITEMS = [
    ("var(--status-1-dot)", "0–20% missing"),
    ("var(--status-2-dot)", "20–40% missing"),
    ("var(--status-3-dot)", "40–60% missing"),
    ("var(--status-4-dot)", "60–80% missing"),
    ("var(--status-5-dot)", "80–100% missing"),
]


def create_legend():
    return html.Div([
        html.Span("Completeness key:", className="legend-title"),
        *[
            html.Div([
                html.Div(style={"background": dot}, className="legend-swatch"),
                html.Span(label),
            ], className="legend-item")
            for dot, label in LEGEND_ITEMS
        ],
        html.Div([
            html.Span("REQ", className="req-badge"),
            html.Span("= Must be collected for every patient"),
        ], className="legend-item ms-3"),
    ], className="legend-bar")