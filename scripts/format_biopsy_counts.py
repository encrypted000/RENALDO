"""
format_biopsy_counts.py
Turns the raw "biopsy counts per cohort" query export (aggregate counts only)
into a formatted workbook for discussing small-number suppression.
One-off meeting aid, not part of the app.

Run with: python scripts/format_biopsy_counts.py "<path to export>.xlsx"
Writes <same folder>/<same name>_meeting.xlsx
"""
import sys
from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

# Mirrors the dashboard: cohorts under this size are already hidden.
SMALL_N_THRESHOLD = 20
# Counts from 1 up to this value are flagged as "small" (placeholder — agree with Danny / IG).
SMALL_COUNT_MAX = 4

COUNT_COLUMNS = [
    "native_1", "native_2plus",
    "transplant_1", "transplant_2plus",
    "not_recorded_1", "not_recorded_2plus",
]
REQUIRED_COLUMNS = ["cohort", "patients"] + COUNT_COLUMNS

# ── Colours ──
NAVY       = "0F2D4A"
BLUE_LIGHT = "E8F3FB"
GRAY_TEXT  = "4A5568"
GRAY_MUTED = "9AA3AF"
GRAY_LINE  = "D9DEE5"
AMBER_BG   = "FFF2CC"
AMBER_TEXT = "9C5700"
WHITE      = "FFFFFF"

THIN_BOTTOM = Border(bottom=Side(style="thin", color=GRAY_LINE))
CENTER      = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT        = Alignment(horizontal="left", vertical="center", wrap_text=True)


def _to_int(value) -> int:
    if value is None or str(value).strip() == "":
        return 0
    return int(float(value))


def read_export(path: Path) -> list:
    """Read the query export from the first sheet; finds the header row by its 'cohort' column."""
    ws = load_workbook(path, data_only=True, read_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))

    header_idx = next(
        (i for i, r in enumerate(rows[:10])
         if any(str(c).strip().lower() == "cohort" for c in r if c is not None)),
        None,
    )
    if header_idx is None:
        sys.exit("Could not find a header row with a 'cohort' column in the first 10 rows.")

    headers = [str(c).strip().lower() if c is not None else "" for c in rows[header_idx]]
    missing = [c for c in REQUIRED_COLUMNS if c not in headers]
    if missing:
        sys.exit(f"Export is missing expected columns: {missing}")
    col = {name: headers.index(name) for name in REQUIRED_COLUMNS}

    cohorts = []
    for r in rows[header_idx + 1:]:
        name = r[col["cohort"]]
        if name is None or str(name).strip() == "":
            continue
        rec = {"cohort": str(name).strip(), "patients": _to_int(r[col["patients"]])}
        for c in COUNT_COLUMNS:
            rec[c] = _to_int(r[col[c]])
        rec["shown"] = rec["patients"] >= SMALL_N_THRESHOLD
        rec["small"] = sum(1 for c in COUNT_COLUMNS if 1 <= rec[c] <= SMALL_COUNT_MAX)
        cohorts.append(rec)
    return cohorts


def _header_cell(cell, value, fill=NAVY, color=WHITE):
    cell.value     = value
    cell.font      = Font(bold=True, color=color, size=10)
    cell.fill      = PatternFill("solid", fgColor=fill)
    cell.alignment = CENTER


def build_summary(ws, cohorts: list):
    shown        = [c for c in cohorts if c["shown"]]
    small_cohort = [c for c in shown if c["small"]]
    small_cells  = sum(c["small"] for c in shown)

    ws["A1"] = "Renal biopsy counts per cohort"
    ws["A1"].font = Font(bold=True, size=16, color=NAVY)
    ws["A2"] = f"Small-number check for the RENALDO biopsy metadata · aggregate counts only · {date.today():%d %B %Y}"
    ws["A2"].font = Font(size=10, color=GRAY_TEXT)

    _header_cell(ws["A4"], "Key figures")
    ws["A4"].alignment = LEFT
    _header_cell(ws["B4"], "")
    figures = [
        ("Cohorts in total", len(cohorts)),
        (f"Shown on the dashboard ({SMALL_N_THRESHOLD}+ patients)", len(shown)),
        (f"Already hidden (under {SMALL_N_THRESHOLD} patients)", len(cohorts) - len(shown)),
        (f"Shown cohorts with at least one count of 1–{SMALL_COUNT_MAX}", len(small_cohort)),
        (f"Biopsy counts of 1–{SMALL_COUNT_MAX} that would be public (of all counts shown)",
         f"{small_cells} of {len(shown) * len(COUNT_COLUMNS)}"),
    ]
    for i, (label, value) in enumerate(figures, start=5):
        ws.cell(i, 1, label).alignment = LEFT
        v = ws.cell(i, 2, value)
        v.alignment = Alignment(horizontal="right", vertical="center")
        v.font = Font(bold=True)
        for c in (1, 2):
            ws.cell(i, c).border = THIN_BOTTOM
    if small_cohort:
        for c in (1, 2):
            ws.cell(8, c).fill = PatternFill("solid", fgColor=AMBER_BG)
            ws.cell(9, c).fill = PatternFill("solid", fgColor=AMBER_BG)

    notes_row = 12
    _header_cell(ws.cell(notes_row, 1), "How to read the 'By cohort' sheet")
    ws.cell(notes_row, 1).alignment = LEFT
    _header_cell(ws.cell(notes_row, 2), "")
    notes = [
        "Each patient is counted once per biopsy type: exactly 1 biopsy, or 2 or more (distinct biopsy dates).",
        "Native = NATIVE. Transplant = TRANSPLANT and TIME ZERO TRANSPLANT. Type not recorded = no kidney type entered.",
        f"Amber cells: a count of 1–{SMALL_COUNT_MAX} that would appear on the public dashboard.",
        f"Small counts column: how many of the cohort's six biopsy counts are 1–{SMALL_COUNT_MAX}, "
        "i.e. the number of amber cells in that row (not a number of patients).",
        f"Grey rows: cohorts under {SMALL_N_THRESHOLD} patients, which the dashboard already hides.",
        "Patients can belong to more than one cohort, so cohort figures should not be added together.",
    ]
    for i, note in enumerate(notes, start=notes_row + 1):
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=2)
        cell = ws.cell(i, 1, note)
        cell.alignment = LEFT
        cell.font = Font(size=10, color=GRAY_TEXT)
        ws.row_dimensions[i].height = 30

    q = notes_row + len(notes) + 2
    _header_cell(ws.cell(q, 1), "Decision needed")
    ws.cell(q, 1).alignment = LEFT
    _header_cell(ws.cell(q, 2), "")
    options = [
        "A — Show exact counts, as transplant counts are shown today (no extra code).",
        f"B — Hide counts of 1–{SMALL_COUNT_MAX} as \"<{SMALL_COUNT_MAX + 1}\"; ideally applied to transplant counts too.",
    ]
    for i, opt in enumerate(options, start=q + 1):
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=2)
        cell = ws.cell(i, 1, opt)
        cell.alignment = LEFT
        ws.row_dimensions[i].height = 30

    ws.column_dimensions["A"].width = 70
    ws.column_dimensions["B"].width = 16
    ws.sheet_view.showGridLines = False


def build_by_cohort(ws, cohorts: list):
    ws["A1"] = "Patients with renal biopsies, by cohort"
    ws["A1"].font = Font(bold=True, size=14, color=NAVY)
    ws["A2"] = (f"Amber = count of 1–{SMALL_COUNT_MAX} that would be public · "
                f"grey = cohort under {SMALL_N_THRESHOLD} patients, already hidden")
    ws["A2"].font = Font(size=10, color=GRAY_TEXT)

    # Two-row header: groups on row 3, "1 / 2+" on row 4
    single_cols = [(1, "Cohort"), (2, "Patients"), (9, "Dashboard"), (10, "Small counts")]
    for c, label in single_cols:
        _header_cell(ws.cell(3, c), label)
        ws.merge_cells(start_row=3, start_column=c, end_row=4, end_column=c)
    ws.cell(3, 1).alignment = LEFT

    for start, label in [(3, "Native"), (5, "Transplant"), (7, "Type not recorded")]:
        _header_cell(ws.cell(3, start), label)
        ws.merge_cells(start_row=3, start_column=start, end_row=3, end_column=start + 1)
        _header_cell(ws.cell(4, start),     "1 biopsy",    fill=BLUE_LIGHT, color=NAVY)
        _header_cell(ws.cell(4, start + 1), "2+ biopsies", fill=BLUE_LIGHT, color=NAVY)
    ws.row_dimensions[3].height = 20
    ws.row_dimensions[4].height = 20

    amber_fill = PatternFill("solid", fgColor=AMBER_BG)
    for r, rec in enumerate(cohorts, start=5):
        values = [rec["cohort"], rec["patients"]] + [rec[c] for c in COUNT_COLUMNS] + [
            "Shown" if rec["shown"] else f"Hidden (under {SMALL_N_THRESHOLD})",
            rec["small"] if rec["shown"] else "—",
        ]
        for c, value in enumerate(values, start=1):
            cell = ws.cell(r, c, value)
            cell.border = THIN_BOTTOM
            cell.alignment = LEFT if c == 1 else CENTER
            if isinstance(value, int):
                cell.number_format = "#,##0"
            if not rec["shown"]:
                cell.font = Font(color=GRAY_MUTED, italic=(c == 9))

        if rec["shown"]:
            for c in range(3, 9):
                if 1 <= ws.cell(r, c).value <= SMALL_COUNT_MAX:
                    ws.cell(r, c).fill = amber_fill
                    ws.cell(r, c).font = Font(bold=True, color=AMBER_TEXT)
            if rec["small"]:
                ws.cell(r, 10).font = Font(bold=True, color=AMBER_TEXT)

    last = 4 + len(cohorts)
    ws.freeze_panes = "B5"
    ws.auto_filter.ref = f"A4:J{last}"
    ws.column_dimensions["A"].width = 46
    for letter in "BCDEFGH":
        ws.column_dimensions[letter].width = 14
    ws.column_dimensions["I"].width = 19
    ws.column_dimensions["J"].width = 15
    ws.sheet_view.showGridLines = False

    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth  = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "3:4"


def main():
    if len(sys.argv) != 2:
        sys.exit('Usage: python scripts/format_biopsy_counts.py "<path to export>.xlsx"')
    src = Path(sys.argv[1].strip('"'))
    dst = src.with_name(f"{src.stem}_meeting.xlsx")

    cohorts = read_export(src)
    if not cohorts:
        sys.exit("No cohort rows found under the header.")

    wb = Workbook()
    build_summary(wb.active, cohorts)
    wb.active.title = "Summary"
    build_by_cohort(wb.create_sheet("By cohort"), cohorts)
    wb.save(dst)
    print(f"Written: {dst}")


if __name__ == "__main__":
    main()
