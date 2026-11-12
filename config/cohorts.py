# ── Cohort Group Configuration ──
# Group IDs to exclude from the cohort list (non-standard / admin groups).
EXCLUDED_GROUP_IDS = (184, 137, 149, 152, 18, 194, 19, 161, 182, 174, 140, 220, 222)

# Cohort names (matched case-insensitively) to exclude in addition to
# EXCLUDED_GROUP_IDS — resolved to a group ID at runtime since the ID isn't
# tracked here. "Data Completeness" is an internal QA cohort, not a patient
# disease cohort, and is excluded from the public dashboard entirely (UKKA
# decision, Sept 2026) — including from the Section A "Overall RaDaR" totals.
EXCLUDED_GROUP_NAMES = (
    "Data Completeness", "z CLOSED Dent Disease and Lowe Syndrome"
)

# Group IDs representing withdrawn consent. Patients in these groups are
# excluded from follow-up calculations (Overall follow up / Follow up pre KRT)
# but are otherwise unaffected — these IDs are also in EXCLUDED_GROUP_IDS so
# the groups themselves never appear as cohort sections.
WITHDRAWN_GROUP_IDS = (152, 182)

# Cohorts (matched case-insensitively) that do not get a "Follow up pre KRT"
# field, per UKKA decision Sept 2026 — these are post-KRT/transplant cohorts
# where a pre-KRT follow-up window doesn't apply.
NO_PRE_KRT_FOLLOWUP_COHORTS = (
    "CMV Post Transplant",
    "BK Nephropathy",
)

# Cohorts (matched case-insensitively) with no Biochemistry Metadata section,
# per UKKA decision Sept 2026.
NO_BIOCHEMISTRY_COHORTS = (
    "CMV Post Transplant",
    "BK Nephropathy",
)

# Renal biopsy rows, reviewed cohort by cohort with UKKA (Nov 2026).
# Matched case-insensitively. Excluded figures are left out of
# completeness.json entirely, not just hidden in the UI, because the whole
# JSON is public (committed to GitHub and sent to the browser).
#   NO_BIOPSY_COHORTS: no biopsy rows at all.
#   BIOPSY_TRANSPLANT_ONLY_COHORTS: transplant biopsies only, native left out.
NO_BIOPSY_COHORTS = (
    "APRT Deficiency",
    "Calciphylaxis",
    "Early onset Hypertension",
    "Inherited Renal Cancer Syndromes",
    "Mitochondrial Renal Disease",
    "Pure Red Cell Aplasia",
    "Retroperitoneal Fibrosis",
    "Tuberous Sclerosis",
)

BIOPSY_TRANSPLANT_ONLY_COHORTS = (
    "Autosomal Dominant Polycystic Kidney Disease",
    "Autosomal Recessive Polycystic Kidney Disease/Nephronophthisis/Ciliopathy",
    "Congenital Anomalies of the Kidneys and Urinary Tracts",
    "Cystinosis",
    "Cystinuria",
    "Fibromuscular Dysplasia",
    "HNF1b Mutations",
)

# Letter sequence assigned to cohorts B–AH (one per DB cohort, in DB sort order).
# Section A is reserved for Patient Demographics.
COHORT_LETTERS = [
    "B",  "C",  "D",  "E",  "F",  "G",  "H",  "I",  "J",  "K",
    "L",  "M",  "N",  "O",  "P",  "Q",  "R",  "S",  "T",  "U",
    "V",  "W",  "X",  "Y",  "Z",  "AA", "AB", "AC", "AD", "AE",
    "AF", "AG", "AH", "AI",
]
