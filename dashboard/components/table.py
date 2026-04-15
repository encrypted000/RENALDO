from dash import dash_table


# ── Colour helpers ──

def _row_bg(pct) -> str:
    """Background colour based on % missing — QUOD thresholds."""
    if pct is None: return "#f8f9fb"
    if pct < 20:    return "#00b050"  # Green:       0–20%
    if pct < 40:    return "#92d050"  # Yellow-green: 20–40%
    if pct < 60:    return "#ffff00"  # Yellow:       40–60%
    if pct < 80:    return "#ff9900"  # Orange:       60–80%
    return "#ff0000"                  # Red:          80–100%


def _row_fg(pct) -> str:
    """Text colour for readability on each background."""
    if pct is None: return "#8a97a8"
    if pct < 20:    return "#ffffff"
    if pct < 40:    return "#1a4a00"
    if pct < 60:    return "#4a4a00"
    if pct < 80:    return "#4a2500"
    return "#ffffff"


# ── Column definitions ──

COLUMNS = [
    {"name": "",              "id": "req"},
    {"name": "ID",            "id": "id"},
    {"name": "% Missing",     "id": "pct_missing"},
    {"name": "Variable",      "id": "name"},
    {"name": "Missing/Total", "id": "counts"},
    {"name": "Description",   "id": "desc"},
]

COLUMN_WIDTHS = [
    {"if": {"column_id": "req"},         "width": "40px",  "textAlign": "center"},
    {"if": {"column_id": "id"},          "width": "60px",  "fontFamily": "Consolas, monospace", "fontSize": "11px"},
    {"if": {"column_id": "pct_missing"}, "width": "90px",  "textAlign": "center", "fontWeight": "600"},
    {"if": {"column_id": "name"},        "width": "200px", "fontWeight": "600"},
    {"if": {"column_id": "counts"},      "width": "140px", "fontSize": "11px"},
]


def build_table(variables: list, section_id: str):
    """
    Build a colour-coded DataTable for one accordion section.

    Args:
        variables:  list of variable dicts from completeness.json
        section_id: unique string used as the table component id

    Returns:
        dash_table.DataTable
    """
    rows = []
    style_conditions = []

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

        style_conditions.append({
            "if": {"row_index": i},
            "backgroundColor": _row_bg(pct),
            "color":           _row_fg(pct),
        })

    return dash_table.DataTable(
        id=f"table-{section_id}",
        columns=COLUMNS,
        data=rows,
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor":  "#f9f8f6",
            "fontWeight":       "600",
            "fontSize":         "11px",
            "color":            "#6b6b6b",
            "border":           "none",
            "borderBottom":     "1px solid #e0ddd8",
            "textTransform":    "uppercase",
            "letterSpacing":    "0.03em",
            "padding":          "6px 10px",
        },
        style_cell={
            "fontSize":    "12px",
            "padding":     "5px 10px",
            "border":      "none",
            "borderBottom":"0.5px solid rgba(0,0,0,0.04)",
            "fontFamily":  "'Segoe UI', system-ui, sans-serif",
            "textAlign":   "left",
        },
        style_data_conditional=style_conditions,
        style_cell_conditional=COLUMN_WIDTHS,
        page_action="none",
        sort_action="native",
    )
