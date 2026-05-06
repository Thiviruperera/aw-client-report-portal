# AW Client Report Portal

An internal portal for a small financial planning team to enter quarterly client balances and generate polished SACS (cashflow) and TCC (net worth) PDF reports — replacing a manual Canva/Word workflow.

---

## What it does

The team currently spends a full day per client pulling balances from Pinnacle Bank, Charles Schwab, and Zillow and assembling two fixed-format reports in Canva and Word. This portal reduces that to a structured data-entry form and a single click.

**Core workflow:**

1. Client profiles store static data once — household info, both spouses, account structure, liabilities, and properties.
2. Each quarter, the team opens a client, clicks **Start New Quarterly Report**, and enters current balances. Last-quarter values appear as helper text; unchanged fields can be copied with one click.
3. The server runs all calculations automatically and renders a preview.
4. SACS and TCC PDFs are generated on demand and can be re-downloaded from report history at any time.

---

## Quick start

```bash
# 1. Install Python deps
pip install -r requirements.txt

# 2. Install WeasyPrint system deps
#    macOS:    brew install pango
#    Linux:    apt install libpango-1.0-0 libpangoft2-1.0-0
#    Windows:  winget install tschoonj.GTKForWindows

# 3. Seed the demo client and run
python seed.py             # creates Henderson Family + 2026-Q1 report
python -m flask --app app run
```

Visit <http://127.0.0.1:5000> and sign in with password `demo`.

---

## Architecture

| Layer | Choice | Why |
|---|---|---|
| Backend | Flask (~300 LOC, single file) | Server-rendered forms and PDF responses — no API layer needed for this workflow. |
| Templating | Jinja | One template engine for both HTML pages and PDF templates. |
| Database | SQLite via SQLAlchemy | Two tables (`clients`, `reports`) with JSON columns for nested account/liability/property structure. Scales to the 6–12 client range without ops overhead. |
| PDF generation | WeasyPrint | The variable-bubble TCC layout is a CSS Grid problem. WeasyPrint renders HTML/CSS to PDF, handling dynamic account counts trivially where a coordinate-based library would require manual positioning. |
| Frontend | Plain HTML + CSS | No JS framework. Form submits → server-rendered preview. |
| Deployment | Railway via Dockerfile | `python:3.11-slim` + `apt-get install` places Cairo/Pango/HarfBuzz at standard `/usr/lib` paths so WeasyPrint's `cffi.dlopen()` finds them without any `LD_LIBRARY_PATH` configuration. |

### Static vs dynamic data

Most client data does not change quarter to quarter. The schema reflects this cleanly:

- **`clients`** — household, spouse info, account *structure* (which accounts exist), liabilities, properties. Entered once at onboarding.
- **`reports`** — per-quarter snapshot of *balances* plus computed totals, stored alongside inputs as JSON.

Last-quarter prefill is a single query: fetch the latest `Report` for a client, read its `inputs_json`. Each quarter becomes a diff over the previous one.

### Calculation rules

All rules are sourced directly from the PRD acceptance criteria and transcript quotes. They are enforced in `calculations.py` and locked by unit tests.

| Rule | Formula |
|---|---|
| SACS excess | `inflow − outflow` |
| Private Reserve Target | `6 × monthly outflow + insurance deductibles` (per-client override supported) |
| Client 1 retirement total | Sum of all Client 1 retirement account balances |
| Client 2 retirement total | Sum of all Client 2 retirement account balances |
| Non-retirement total | Sum of non-retirement accounts — **trust excluded** *(Rebecca, 24:28)* |
| Trust total | Sum of property Zestimates |
| Grand total net worth | C1 retirement + C2 retirement + non-retirement + trust |
| Liabilities total | Sum of liability balances — **never subtracted from net worth** *(Rebecca, 26:15)* |

---

## Testing

```bash
pytest -q        # 29 tests, all passing
```

| Suite | What it covers |
|---|---|
| `tests/test_calculations.py` | 22 tests — every PRD calculation rule, including edge cases: trust excluded from non-retirement, liabilities never subtracted, private reserve override vs formula, single-client (no spouse) totals. |
| `tests/test_pdf_smoke.py` | 3 tests — TCC PDF renders successfully with 1, 3, and 6 retirement account bubbles, confirming the variable-layout CSS Grid solution is stable. |
| `tests/test_routes.py` | 4 tests — report delete route: successful deletion + redirect, auth guard, 404 on missing ID, isolation (only the targeted report is removed). |

All tests use isolated SQLite databases via `tmp_path`; the production database is never touched during a test run.

---

## Deploying to Railway

1. Push this repo to GitHub.
2. Railway → **New Project → Deploy from GitHub** → select the repo.
3. Add a **Volume** to the service, mounted at `/data`.
4. Set environment variables:

   | Variable | Value |
   |---|---|
   | `APP_PASSWORD` | The team's shared login password |
   | `SECRET_KEY` | A long random string |
   | `DATABASE_URL` | `sqlite:////data/app.db` |
   | `PORT` | Set automatically by Railway |

5. Deploy. On first boot, `_auto_seed_if_empty` in `app.py` creates the Henderson Family demo client and a sample Q1 report if the database is empty.

The `Dockerfile` installs Cairo, Pango, HarfBuzz, GDK-Pixbuf, and libffi via `apt-get` so WeasyPrint's native dependencies are at standard system paths.

---

## Project layout

```
fin-report-portal/
├── app.py                  # Flask app — all routes (~300 LOC)
├── models.py               # Client, Report (SQLAlchemy)
├── calculations.py         # Pure functions for SACS/TCC math
├── seed.py                 # Demo Henderson household + 2026-Q1 report
├── clean_db.py             # One-off utility: remove reports below $1M net worth
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── clients_list.html
│   ├── client_detail.html  # Profile, accounts, liabilities, report history + delete
│   ├── report_form.html    # Quarterly data entry with last-quarter prefill
│   ├── report_preview.html # Calculated totals + PDF download buttons
│   └── pdf/
│       ├── _base.css       # Shared print styles
│       ├── sacs.html       # Cashflow diagram — 2 pages
│       └── tcc.html        # Net worth chart with variable account bubbles
├── static/css/app.css
├── tests/
│   ├── conftest.py             # Sets SKIP_AUTOSEED for test isolation
│   ├── test_calculations.py    # 22 calculation unit tests
│   ├── test_pdf_smoke.py       # PDF render smoke tests (1, 3, 6 bubbles)
│   └── test_routes.py          # Route tests (delete, auth, 404)
├── Dockerfile
└── requirements.txt
```

---

## V1 scope decisions

| Decision | Rationale |
|---|---|
| **PDF visuals match the PRD's structural language, not the original Canva files** | The original Canva and Word source files were not available. Templates implement the described layout: green Inflow circle, red Outflow circle, blue Private Reserve, green client info pills, sectioned TCC with trust and liabilities. Visual alignment to the originals is a straightforward adjustment once files are shared. |
| **Shared password authentication** | The team is three people using the portal internally. Per-user auth, SSO, and audit logging are V2 additions. |
| **Account structure is read-only in the UI** | Accounts, liabilities, and properties are defined in the client record and displayed on the detail page. The data model (JSON columns) fully supports editing; the edit forms are a V2 item. |
| **No draft/finalize flow** | Submitting the quarterly form creates a `Report` record immediately. The form can be re-submitted; each submission creates a new versioned report. |
| **PDFs generated on demand from stored snapshots** | `inputs_json` and `calculated_json` are stored on each report. Re-rendering produces byte-identical output, so re-downloading a prior quarter always returns the correct PDF. |
| **No live totals during data entry** | Calculated totals appear on the preview page after submission. |
| **Money stored as integer dollars** | Source data is whole-dollar amounts (expense worksheets, bank statements). No float arithmetic anywhere in the calculation layer. |
| **Variable TCC bubble count capped at 6 per section** | Per PRD specification. CSS Grid scales from 2 to 6 columns based on account count; smoke-tested at 1, 3, and 6 bubbles. |

---

## V2 roadmap

In priority order:

1. **Account / liability / property edit forms** — the data model is already structured for it; add three standard CRUD pages.
2. **Per-user authentication and audit log** — replace shared password with user accounts; log who generated each report.
3. **PDF archive** — store rendered PDF bytes alongside the JSON snapshot; add SHA256 verification for re-downloads.
4. **Live totals during data entry** — ~50 lines of vanilla JS; no framework required.
5. **Canva export** — use the Canva API to push generated report data into the team's workspace for last-minute visual adjustments.
6. **Data integrations** — Plaid for bank account balances, Zillow API for Zestimates. RightCapital and Schwab require compliance review before automated access (raised explicitly in the discovery call).
