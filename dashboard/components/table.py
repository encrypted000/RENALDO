from dash import dash_table


# ── Completeness bands (RAG — red/amber/green audit convention) ──
# Colour tokens live in style.css (--status-N-*) so the palette stays in one
# place and can be retuned without touching this file.

_BANDS = [
    (20,  "var(--status-1-bg)", "var(--status-1-fg)"),  # 0–20% missing
    (40,  "var(--status-2-bg)", "var(--status-2-fg)"),  # 20–40%
    (60,  "var(--status-3-bg)", "var(--status-3-fg)"),  # 40–60%
    (80,  "var(--status-4-bg)", "var(--status-4-fg)"),  # 60–80%
    (101, "var(--status-5-bg)", "var(--status-5-fg)"),  # 80–100%
]


def _band(pct):
    if pct is None:
        return None
    for ceiling, bg, fg in _BANDS:
        if pct < ceiling:
            return bg, fg
    return _BANDS[-1][1], _BANDS[-1][2]


# ── Column definitions ──

COLUMNS = [
    {"name": "",              "id": "req"},
    {"name": "ID",            "id": "id"},
    {"name": "% Missing",     "id": "pct_missing"},
    {"name": "Variable",      "id": "name"},
    {"name": "Missing/Total", "id": "counts"},
    {"name": "Description",   "id": "desc"},
]


# Percentage widths that sum to 100% — the table always fits its container
# exactly, so a long description wraps onto more lines instead of forcing
# the whole table into a horizontally-scrolling strip.
COLUMN_WIDTHS = [
    {"if": {"column_id": "req"},         "width": "6%",  "textAlign": "center"},
    {"if": {"column_id": "id"},          "width": "7%",  "fontFamily": "var(--font-mono)", "fontSize": "11px", "color": "var(--text-3)"},
    {"if": {"column_id": "pct_missing"}, "width": "9%",  "textAlign": "center"},
    {"if": {"column_id": "name"},        "width": "16%", "fontWeight": "600", "color": "var(--text)"},
    {"if": {"column_id": "counts"},      "width": "13%", "fontSize": "11.5px", "color": "var(--text-2)"},
    {"if": {"column_id": "desc"},        "width": "49%"},
]

REQ_BADGE_STYLE = {
    "if": {"column_id": "req", "filter_query": '{req} = "REQ"'},
    "backgroundColor": "var(--accent-lt)",
    "color":           "var(--accent-dk)",
    "fontWeight":      "700",
    "fontSize":        "10px",
    "letterSpacing":   "0.03em",
    "borderRadius":    "4px",
}


def build_table(variables: list, section_id: str):
    """
    Build a DataTable for one accordion section. The % Missing cell carries
    the RAG completeness colour as a coloured chip — the row itself stays
    neutral so a dense table of 10+ variables stays readable rather than
    turning into a wall of saturated colour.

    Args:
        variables:  list of variable dicts from completeness.json
        section_id: unique string used as the table component id

    Returns:
        dash_table.DataTable
    """
    rows = []
    style_conditions = [REQ_BADGE_STYLE]

    for i, v in enumerate(variables):
        pct     = v.get("pct_missing")
        missing = v.get("missing", 0)
        total   = v.get("total", 0)

        if isinstance(missing, int) and isinstance(total, int):
            counts_label = f"{missing:,} / {total:,}"
        elif isinstance(total, int) and total > 0:
            counts_label = f"{total:,} patients"
        else:
            counts_label = "—"

        rows.append({
            "req":         "REQ" if v.get("required") else "",
            "id":          v.get("id", ""),
            "pct_missing": f"{pct:.1f}%" if pct is not None else "—",
            "name":        v.get("name", ""),
            "counts":      counts_label,
            "desc":        v.get("desc", ""),
        })

        band = _band(pct)
        if band:
            bg, fg = band
            style_conditions.append({
                "if": {"row_index": i, "column_id": "pct_missing"},
                "backgroundColor": bg,
                "color":           fg,
                "fontWeight":      "700",
                "borderRadius":    "4px",
            })
        else:
            style_conditions.append({
                "if": {"row_index": i, "column_id": "pct_missing"},
                "color": "var(--text-3)",
            })

    return dash_table.DataTable(
        id=f"table-{section_id}",
        columns=COLUMNS,
        data=rows,
        style_table={"width": "100%"},
        style_header={
            "backgroundColor":  "var(--surface-2)",
            "fontWeight":       "600",
            "fontSize":         "10.5px",
            "color":            "var(--text-3)",
            "border":           "none",
            "borderBottom":     "1px solid var(--border)",
            "textTransform":    "uppercase",
            "letterSpacing":    "0.05em",
            "padding":          "6px 12px",
            "whiteSpace":       "normal",
        },
        style_cell={
            "fontSize":        "12.5px",
            "padding":         "7px 12px",
            "border":          "none",
            "borderBottom":    "1px solid var(--border)",
            "fontFamily":      "var(--font)",
            "textAlign":       "left",
            "backgroundColor": "var(--surface)",
            "whiteSpace":      "normal",
            "height":          "auto",
            "overflowWrap":    "break-word",
        },
        style_data_conditional=style_conditions,
        style_cell_conditional=COLUMN_WIDTHS,
        page_action="none",
        sort_action="native",
    )
