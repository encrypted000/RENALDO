"""
bands.py
Single source of truth for the 5-tier RAG completeness scale, shared by the
per-variable table cells (table.py) and the collapsed cohort-row bars
(accordion.py) — one place to retune thresholds so the two can never drift
out of sync with the legend (legend.py).
"""

BANDS = [
    (20,  "var(--status-1-bg)", "var(--status-1-fg)", "var(--status-1-dot)"),  # 0–20% missing
    (40,  "var(--status-2-bg)", "var(--status-2-fg)", "var(--status-2-dot)"),  # 20–40%
    (60,  "var(--status-3-bg)", "var(--status-3-fg)", "var(--status-3-dot)"),  # 40–60%
    (80,  "var(--status-4-bg)", "var(--status-4-fg)", "var(--status-4-dot)"),  # 60–80%
    (101, "var(--status-5-bg)", "var(--status-5-fg)", "var(--status-5-dot)"),  # 80–100%
]


def band_for_pct_missing(pct_missing):
    """Return (bg, fg, dot) CSS var strings for a % missing value, or None."""
    if pct_missing is None:
        return None
    for ceiling, bg, fg, dot in BANDS:
        if pct_missing < ceiling:
            return bg, fg, dot
    return BANDS[-1][1], BANDS[-1][2], BANDS[-1][3]
