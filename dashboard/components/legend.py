from dash import html

LEGEND_ITEMS = [
    ("#00b050", "none",             "0–20% missing"),
    ("#92d050", "none",             "20–40% missing"),
    ("#ffff00", "0.5px solid #ccc", "40–60% missing"),
    ("#ff9900", "none",             "60–80% missing"),
    ("#ff0000", "none",             "80–100% missing"),
]


def create_legend():
    return html.Div([
        html.Span("Completeness key:", className="legend-title"),
        *[
            html.Div([
                html.Div(
                    style={"background": bg, "border": border},
                    className="legend-swatch",
                ),
                html.Span(label),
            ], className="legend-item")
            for bg, border, label in LEGEND_ITEMS
        ],
        html.Div([
            html.Span(
                "Required",
                style={
                    "fontSize":       "10px",
                    "fontWeight":     "600",
                    "background":     "rgba(0,0,0,0.12)",
                    "padding":        "2px 7px",
                    "borderRadius":   "10px",
                    "marginRight":    "5px",
                }
            ),
            html.Span("= Must be collected for every patient",
                      style={"fontSize": "12px"}),
        ], className="legend-item ms-3"),
    ], className="legend-bar")