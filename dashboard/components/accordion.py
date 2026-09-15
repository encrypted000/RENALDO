from dash import html
import dash_bootstrap_components as dbc
from dashboard.components.table import build_table
from dashboard.components.bands import band_for_pct_missing


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

    if pct_complete is not None:
        # The bar stores "% complete"; the shared band lookup is keyed on
        # "% missing" (same convention the per-variable table cells use),
        # so convert before matching — this is the one place that has to
        # stay consistent with table.py's usage of the same shared bands.
        band = band_for_pct_missing(100 - pct_complete)
        fill_color = band[2] if band else "var(--accent)"   # dot — visible at 5px height
        text_color = band[1] if band else "var(--text-3)"   # fg — readable as text
        bar = html.Div([
            html.Div(className="sec-bar-bg", children=[
                html.Div(className="sec-bar-fill",
                         style={"width": f"{pct_complete}%", "background": fill_color}),
            ]),
            html.Span(f"{pct_complete}% complete", className="sec-bar-pct",
                      style={"color": text_color}),
        ], className="sec-bar-wrap ms-auto me-3")
    else:
        bar = html.Div(className="ms-auto me-3")

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


def _biochem_cell(stat: dict, field: str) -> str:
    if not stat or not stat.get("total"):
        return "—"

    if field == "coverage":
        count, total = stat.get("count", 0), stat.get("total", 0)
        pct = round(count / total * 100, 1) if total else 0
        return f"{count:,} / {total:,} ({pct}%)"

    if field == "n_results":
        return f"{stat.get('total_results', 0):,}"

    if field == "per_patient":
        return (
            f"{stat.get('median_per_patient', 0)} "
            f"(IQR {stat.get('q1_per_patient', 0)}–{stat.get('q3_per_patient', 0)})"
        )

    if field == "time_to_krt":
        timing = stat.get("time_to_krt")
        if not timing or not timing.get("count"):
            return "—"
        return f"{timing['median']} yrs (IQR {timing['q1']}–{timing['q3']})"

    return "—"


_BIOCHEM_ROWS = [
    ("Patients with ≥1 result pre-KRT",              "coverage"),
    ("Total results recorded pre-KRT",                     "n_results"),
    ("Results per patient (median, IQR)",                  "per_patient"),
    ("Yrs from first result to KRT/today (median, IQR)",   "time_to_krt"),
]


def _biochemistry_body(sec: dict, small_n: bool) -> html.Div:
    if small_n:
        return _small_n_body()

    biochem = sec.get("biochemistry")
    if not biochem:
        return html.Div([
            html.Strong("Biochemistry metadata coming soon"),
            html.P("Creatinine and proteinuria counts pre-KRT for this cohort will be added in a future update."),
        ], className="empty-state")

    creat = biochem.get("creatinine")
    prot  = biochem.get("proteinuria")

    table = html.Table([
        html.Thead(html.Tr([
            html.Th(""),
            html.Th("Creatinine"),
            html.Th("Proteinuria"),
        ])),
        html.Tbody([
            html.Tr([
                html.Td(label, className="biochem-row-label"),
                html.Td(_biochem_cell(creat, field)),
                html.Td(_biochem_cell(prot, field)),
            ])
            for label, field in _BIOCHEM_ROWS
        ]),
    ], className="biochem-table")

    return html.Div(table, style={"padding": "6px 16px 14px"})


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


def _section_divider(label: str) -> html.Div:
    return html.Div([
        html.Div(className="section-divider-line"),
        html.Span(label, className="section-divider-label"),
        html.Div(className="section-divider-line"),
    ], className="section-divider")


def _cohort_matches(sec: dict, query: str) -> tuple:
    """
    (title_match, variable_match) for one cohort against a lowercased,
    stripped search query — matches on cohort title or a variable's ID/name
    only, not free-text descriptions.
    """
    title_match = query in sec.get("title", "").lower()
    variable_match = any(
        query in str(v.get("id", "")).lower() or query in str(v.get("name", "")).lower()
        for v in sec.get("variables", [])
    )
    return title_match, variable_match


def _build_items(data: list, active_all: bool = False, demo_open: bool = False,
                  search: str = None):
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

    query = (search or "").strip().lower()

    cohort_items    = []
    all_item_ids    = []
    variable_matches = []   # matched only via a variable, not the title — auto-expand these
    n_total_cohorts = 0

    for sec in (s for s in data if s.get("section") != "A"):
        n_total_cohorts += 1
        letter  = sec["section"]
        item_id = f"item-{letter}"

        if query:
            title_match, variable_match = _cohort_matches(sec, query)
            if not (title_match or variable_match):
                continue
            if variable_match and not title_match:
                variable_matches.append(item_id)

        variables  = sec.get("variables", [])
        n_patients = _patient_count(variables)
        small_n    = n_patients < SMALL_N_THRESHOLD

        # Overall % complete is a single rolled-up figure across all variables —
        # unlike the per-variable counts in the table, it doesn't reveal small
        # numbers, so it's shown even for suppressed (low N) cohorts.
        pct_c   = _section_pct_complete(variables) if variables else None
        closed  = sec.get("closed", False)
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

    if query:
        # A variable-name match means the researcher is hunting for a specific
        # field, not just the cohort — open it automatically. A title-only
        # match keeps whatever expand/collapse state is already active.
        active_items = list(dict.fromkeys(
            (all_item_ids if active_all else []) + variable_matches
        ))
    else:
        active_items = all_item_ids if active_all else None

    n_cohorts = len(cohort_items)

    if query and not cohort_items:
        cohorts_accordion = html.Div([
            html.Strong("No matching cohorts"),
            html.P(f'Nothing matches "{search.strip()}" — try a cohort name (e.g. "IgA") '
                   f'or a variable name (e.g. "NHS_NUMBER").'),
        ], className="empty-state")
    else:
        cohorts_accordion = dbc.Accordion(
            cohort_items,
            active_item=active_items,
            start_collapsed=not (active_all or (query and active_items)),
            flush=False,
            className="radar-accordion",
        )

    label = f"Cohort Groups ({n_cohorts} of {n_total_cohorts})" if query else f"Cohort Groups ({n_cohorts})"
    return demo_accordion, _section_divider(label), cohorts_accordion


def build_accordion(data: list, search: str = None):
    """Default — everything collapsed unless matched by a search term."""
    return _build_items(data, active_all=False, demo_open=False, search=search)


def build_accordion_expanded(data: list, search: str = None):
    """Expand all — everything open."""
    return _build_items(data, active_all=True, demo_open=True, search=search)


def build_accordion_collapsed(data: list, search: str = None):
    """Collapse all — everything collapsed."""
    return _build_items(data, active_all=False, demo_open=False, search=search)
