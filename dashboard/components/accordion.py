from dash import html
import dash_bootstrap_components as dbc
from dashboard.components.table import build_table


def _section_pct_complete(variables: list) -> int:
    valid = [v for v in variables if v.get("pct_missing") is not None]
    if not valid:
        return 0
    return round(100 - sum(v["pct_missing"] for v in valid) / len(valid))


def _section_header(letter: str, title: str, n_vars: int,
                    pct_complete: int = None, closed: bool = False) -> html.Div:
    closed_badge = html.Span(
        "CLOSED",
        style={
            "fontSize": "11px",
            "background": "rgba(255,255,255,0.2)",
            "padding": "1px 6px",
            "borderRadius": "3px",
            "marginLeft": "6px",
        }
    ) if closed else None

    bar = html.Div([
        html.Div(className="sec-bar-bg", children=[
            html.Div(className="sec-bar-fill",
                     style={"width": f"{pct_complete}%"}),
        ]),
        html.Span(f"{pct_complete}% complete", className="sec-bar-pct"),
    ], className="sec-bar-wrap ms-auto me-3") if pct_complete is not None else html.Div(
        className="ms-auto me-3"
    )

    count_label = f"({n_vars} variables)" if n_vars > 0 else "(coming soon)"

    children = [
        html.Span(letter, className="sec-letter"),
        html.Span(title,  className="sec-title"),
    ]
    if closed_badge:
        children.append(closed_badge)
    children.append(html.Span(f" {count_label}", className="sec-count"))
    children.append(bar)

    return html.Div(children, className="sec-head-inner")


def _coming_soon_body() -> html.Div:
    return html.Div([
        html.Strong("Variables coming soon"),
        html.Div(
            "Data completeness for this cohort will be added in a future update.",
            style={"fontSize": "11px", "marginTop": "4px"},
        ),
    ], style={
        "padding":    "28px 16px",
        "textAlign":  "center",
        "color":      "#6b6b6b",
        "borderTop":  "0.5px solid #e0ddd8",
        "background": "#fafaf8",
    })


def _cohort_divider(n: int) -> html.Div:
    return html.Div([
        html.Div(style={"flex": "1", "height": "1px", "background": "#e2e6ea"}),
        html.Span(f"Cohort Groups ({n})", style={
            "fontSize":      "11px",
            "fontWeight":    "600",
            "color":         "#8a97a8",
            "textTransform": "uppercase",
            "letterSpacing": "0.08em",
            "padding":       "0 12px",
            "whiteSpace":    "nowrap",
        }),
        html.Div(style={"flex": "1", "height": "1px", "background": "#e2e6ea"}),
    ], style={
        "display":    "flex",
        "alignItems": "center",
        "margin":     "28px 0 16px",
    })


def _build_items(data: list, active_all: bool = False, demo_open: bool = False):
    demo_sec  = next((s for s in data if s.get("section") == "A"), None)
    demo_vars = demo_sec.get("variables", []) if demo_sec else []
    pct       = _section_pct_complete(demo_vars) if demo_vars else None

    demo_accordion = dbc.Accordion([
        dbc.AccordionItem(
            children=build_table(demo_vars, "A") if demo_vars else _coming_soon_body(),
            title=_section_header("A", demo_sec.get("title", "Overall RaDaR") if demo_sec else "Overall RaDaR", len(demo_vars), pct),
            item_id="item-A",
        )
    ],
        active_item="item-A" if (active_all or demo_open) else None,
        start_collapsed=not (active_all or demo_open),
        flush=False,
        className="radar-accordion mb-2",
    )

    cohort_items = []
    all_item_ids = []

    for sec in (s for s in data if s.get("section") != "A"):
        letter    = sec["section"]
        variables = sec.get("variables", [])
        pct_c     = _section_pct_complete(variables) if variables else None
        closed    = sec.get("closed", False)
        item_id   = f"item-{letter}"
        all_item_ids.append(item_id)

        cohort_items.append(
            dbc.AccordionItem(
                children=build_table(variables, letter) if variables else _coming_soon_body(),
                title=_section_header(
                    letter,
                    sec["title"],
                    len(variables),
                    pct_c,
                    closed,
                ),
                item_id=item_id,
            )
        )

    cohorts_accordion = dbc.Accordion(
        cohort_items,
        active_item=all_item_ids if active_all else None,
        start_collapsed=not active_all,
        flush=False,
        className="radar-accordion",
    )

    n_cohorts = len([s for s in data if s.get("section") != "A"])
    return demo_accordion, _cohort_divider(n_cohorts), cohorts_accordion


def build_accordion(data: list) -> html.Div:
    """Default — everything collapsed."""
    demo, divider, cohorts = _build_items(data, active_all=False, demo_open=False)
    return html.Div([demo, divider, cohorts])


def build_accordion_expanded(data: list) -> html.Div:
    """Expand all — everything open."""
    demo, divider, cohorts = _build_items(data, active_all=True, demo_open=True)
    return html.Div([demo, divider, cohorts])


def build_accordion_collapsed(data: list) -> html.Div:
    """Collapse all — everything collapsed."""
    demo, divider, cohorts = _build_items(data, active_all=False, demo_open=False)
    return html.Div([demo, divider, cohorts])
