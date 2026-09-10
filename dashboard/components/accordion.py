from dash import html
import dash_bootstrap_components as dbc
from dashboard.components.table import build_table


SMALL_N_THRESHOLD = 20  # suppress cohorts with fewer patients than this


def _patient_count(variables: list) -> int:
    total_var = next((v for v in variables if v.get("name") == "TOTAL_PATIENTS"), None)
    return total_var.get("total", 0) if total_var else 0


def _section_pct_complete(variables: list) -> int:
    valid = [v for v in variables if v.get("pct_missing") is not None]
    if not valid:
        return 0
    return round(100 - sum(v["pct_missing"] for v in valid) / len(valid))


def _section_header(letter: str, title: str, n_vars: int,
                    pct_complete: int = None, closed: bool = False,
                    small_n: bool = False) -> html.Div:
    closed_badge = html.Span("CLOSED", className="status-badge closed") if closed else None

    bar = html.Div([
        html.Div(className="sec-bar-bg", children=[
            html.Div(className="sec-bar-fill",
                     style={"width": f"{pct_complete}%"}),
        ]),
        html.Span(f"{pct_complete}% complete", className="sec-bar-pct"),
    ], className="sec-bar-wrap ms-auto me-3") if pct_complete is not None else html.Div(
        className="ms-auto me-3"
    )

    count_label = "(low N)" if small_n else (f"({n_vars} variables)" if n_vars > 0 else "(coming soon)")

    children = [
        html.Span(letter, className="sec-letter"),
        html.Span(title,  className="sec-title"),
    ]
    if closed_badge:
        children.append(closed_badge)
    if small_n:
        children.append(_small_n_badge())
    children.append(html.Span(f" {count_label}", className="sec-count"))
    children.append(bar)

    return html.Div(children, className="sec-head-inner")


def _coming_soon_body() -> html.Div:
    return html.Div([
        html.Strong("Variables coming soon"),
        html.P("Data completeness for this cohort will be added in a future update."),
    ], className="empty-state")


def _small_n_body() -> html.Div:
    return html.Div([
        html.Strong(f"Cohort has fewer than {SMALL_N_THRESHOLD} patients"),
        html.P(
            "To protect patient confidentiality, detailed completeness data is not "
            "shown for cohorts this small."
        ),
    ], className="empty-state low-n")


def _small_n_badge() -> html.Span:
    return html.Span("LOW N", className="status-badge low-n")


def _biochemistry_body(sec: dict, small_n: bool) -> html.Div:
    if small_n:
        return _small_n_body()

    biochem = sec.get("biochemistry")
    if not biochem:
        return html.Div([
            html.Strong("Biochemistry metadata coming soon"),
            html.P("Creatinine and proteinuria counts pre-KRT for this cohort will be added in a future update."),
        ], className="empty-state")

    blocks = []
    for key, label in (("creatinine", "Creatinine"), ("proteinuria", "Proteinuria")):
        stat = biochem.get(key)
        if not stat:
            continue
        count   = stat.get("count", 0)
        total   = stat.get("total", 0)
        n_results = stat.get("total_results", 0)
        median  = stat.get("median_per_patient", 0)
        q1      = stat.get("q1_per_patient", 0)
        q3      = stat.get("q3_per_patient", 0)

        if total == 0:
            lines = [html.Div("No patients recorded in this cohort", className="biochem-line")]
        else:
            pct = round(count / total * 100, 1)
            lines = [
                html.Div(f"{count:,} / {total:,} patients ({pct}%) had at least one result pre-KRT", className="biochem-line"),
                html.Div(f"{n_results:,} total results recorded pre-KRT across the cohort", className="biochem-line"),
                html.Div(f"Median {median} results per patient (IQR {q1}–{q3}) among patients with a result", className="biochem-line"),
            ]
            timing = stat.get("time_to_krt")
            if timing and timing.get("count"):
                lines.append(html.Div(
                    f"Median {timing['median']} yrs (IQR {timing['q1']}–{timing['q3']} yrs) "
                    f"from first result to KRT or the current date",
                    className="biochem-line",
                ))

        blocks.append(
            html.Div([
                html.Div(label, className="biochem-label"),
                *lines,
            ], className="biochem-block")
        )

    return html.Div(blocks, style={"padding": "6px 16px 14px"})


def _biochemistry_dropdown(sec: dict, letter: str, small_n: bool) -> dbc.Accordion:
    return dbc.Accordion([
        dbc.AccordionItem(
            children=_biochemistry_body(sec, small_n),
            title="Biochemistry Metadata Prior to Kidney Replacement Therapy",
            item_id=f"item-{letter}-biochem",
        )
    ],
        active_item=None,
        start_collapsed=True,
        flush=False,
        className="radar-accordion-sub",
    )


def _cohort_divider(n: int) -> html.Div:
    return html.Div([
        html.Div(className="section-divider-line"),
        html.Span(f"Cohort Groups ({n})", className="section-divider-label"),
        html.Div(className="section-divider-line"),
    ], className="section-divider")


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
        variables = sec.get("variables", [])
        n_patients = _patient_count(variables)
        small_n    = n_patients < SMALL_N_THRESHOLD

        letter  = sec["section"]
        # Overall % complete is a single rolled-up figure across all variables —
        # unlike the per-variable counts in the table, it doesn't reveal small
        # numbers, so it's shown even for suppressed (low N) cohorts.
        pct_c   = _section_pct_complete(variables) if variables else None
        closed  = sec.get("closed", False)
        item_id = f"item-{letter}"
        all_item_ids.append(item_id)

        if small_n:
            body = _small_n_body()
        elif variables:
            body = build_table(variables, letter)
        else:
            body = _coming_soon_body()

        if sec.get("biochemistry") is not None:
            body = html.Div([body, _biochemistry_dropdown(sec, letter, small_n)])

        cohort_items.append(
            dbc.AccordionItem(
                children=body,
                title=_section_header(
                    letter,
                    sec["title"],
                    len(variables),
                    pct_c,
                    closed,
                    small_n,
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

    n_cohorts = len(cohort_items)
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
