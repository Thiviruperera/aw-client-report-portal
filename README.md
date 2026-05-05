# AW Client Report Portal

A focused demo of an internal portal that lets a small financial planning team enter quarterly client balances and generate fixed-layout SACS (cashflow) and TCC (net worth) PDF reports — replacing a manual Canva/Word workflow that currently takes a full day per client.

> **Submission context.** This is a technical assessment for an AI Engineer role at Sagan, scoped intentionally tight. The aim is to demonstrate engineering judgment — clean separation of static vs dynamic data, deterministic financial math with tests, and stable PDF layout — not a feature-complete product. See [Assumptions & V1 boundaries](#assumptions--v1-boundaries) for what's deliberately out of scope.

---

## Demo

1. Open the deployed URL.
2. Sign in with the demo password (`demo` by default, or whatever `APP_PASSWORD` is set to).
3. The dashboard shows one seeded client — **Henderson Family**.
4. Click into the client → **Start New Quarterly Report**.
5. The form is prefilled with last-quarter values as helper text. Type any current value (or hit **Use last** to copy from the prior quarter).
6. Submit → preview page shows live-calculated totals → click **Download SACS PDF** or **Download TCC PDF**.

The seeded client has a complete prior-quarter report already, so the prefill, history list, and PDFs all have realistic data on first load.

---

## Architecture at a glance

| Layer | Choice | Why |
|---|---|---|
| Backend | Flask (single file, ~250 LOC) | Server-rendered forms + PDF responses. No API layer needed for this workflow. |
| Templating | Jinja | Same engine for HTML pages and PDF templates — one mental model. |
| Database | SQLite via SQLAlchemy | 6 clients, 1 writer. Zero ops overhead. Two tables (`clients`, `reports`) with JSON columns for nested account/liability/property structure. |
| PDF generation | WeasyPrint | HTML/CSS handles the variable-bubble TCC layout trivially with CSS Grid. ReportLab's coordinate model would have consumed the entire time budget. |
| Frontend | Plain HTML + a tiny CSS file | No JS framework. Form submits → server-rendered preview. Demo readability over interactivity. |
| Deployment | Railway via `nixpacks.toml` | Cairo/Pango/Pango/HarfBuzz declared as system packages so WeasyPrint works in production. |

### Static vs dynamic data separation

The core domain insight from the meeting transcript is that **most client data doesn't change quarter-to-quarter**. The schema reflects that:

- `clients` — household, spouse, account *structure* (which accounts exist), liabilities, properties. Set once during onboarding.
- `reports` — per-quarter snapshot of *balances* against that structure, plus calculated totals stored alongside.

"Last quarter prefill" is a single query: latest `Report` for the client, read its `inputs_json`. New quarters become diffs over the previous one, which is the workflow Maryann described — "we have to keep double checking" becomes "type one number, see the totals update."

### Calculation rules (locked by tests)

All sourced from the PRD acceptance criteria and explicit transcript quotes:

- `excess = inflow − outflow`
- `private_reserve_target = 6 × outflow + insurance_deductibles` (override-able per client)
- `c1_retirement_total` = sum of Client 1 retirement balances; same for Client 2
- `non_retirement_total` = sum of non-retirement balances **excluding** trust *(Rebecca, 24:28)*
- `trust_total` = sum of property Zestimates
- `grand_total = c1_retirement + c2_retirement + non_retirement + trust` *(includes trust)*
- `liabilities_total` = sum of liability balances — **never subtracted from net worth** *(Rebecca, 26:15)*

These rules are unit-tested in [`tests/test_calculations.py`](tests/test_calculations.py) (22 tests). A separate PDF smoke test renders the TCC with 1, 3, and 6 retirement bubbles to lock down the variable-layout problem Rebecca raised at 12:47 ("if we move something… this one gets moved").

---

## Local development

```bash
# 1. Install Python deps
pip install -r requirements.txt

# 2. Install WeasyPrint system deps
#    macOS:    brew install pango
#    Linux:    apt install libpango-1.0-0 libpangoft2-1.0-0
#    Windows:  winget install tschoonj.GTKForWindows

# 3. Seed and run
python seed.py             # creates the demo client + prior-quarter report
python -m flask --app app run

# 4. Run tests
pytest -q
```

Visit <http://127.0.0.1:5000>, sign in with password `demo`.

---

## Deploying to Railway

1. Push this repo to GitHub.
2. On Railway → **New Project → Deploy from GitHub** → select the repo.
3. Add a **Volume** to the service, mounted at `/data`.
4. Set environment variables:

   | Variable | Value |
   |---|---|
   | `APP_PASSWORD` | A real password (not `demo`) |
   | `SECRET_KEY` | Long random string |
   | `DATABASE_URL` | `sqlite:////data/app.db` |
   | `PORT` | (Railway sets automatically) |

5. Deploy. The first boot auto-seeds the demo client if the DB is empty (`_auto_seed_if_empty` in `app.py`).

`nixpacks.toml` declares Cairo, Pango, HarfBuzz, and friends so WeasyPrint runs in the build image.

---

## Project layout

```
fin-report-portal/
├── app.py                  # Flask routes, ~250 LOC
├── models.py               # Client, Report (SQLAlchemy)
├── calculations.py         # Pure functions for SACS/TCC math
├── seed.py                 # Demo Henderson household + prior Q1 report
├── templates/
│   ├── base.html           # Layout shell
│   ├── login.html
│   ├── clients_list.html
│   ├── client_detail.html  # Profile, accounts, liabilities, history
│   ├── report_form.html    # Quarterly data entry, prefilled
│   ├── report_preview.html # Calculated totals + PDF download buttons
│   └── pdf/
│       ├── _base.css       # Shared print styles
│       ├── sacs.html       # Cashflow diagram + reserve target
│       └── tcc.html        # Net worth chart with variable bubbles
├── static/css/app.css
├── tests/
│   ├── test_calculations.py    # 22 tests covering every PRD rule
│   └── test_pdf_smoke.py       # 3 tests: TCC renders with 1, 3, 6 bubbles
├── nixpacks.toml           # Railway build config
├── Procfile
├── runtime.txt             # Python 3.11.9 for Railway (3.14 is pre-release)
└── requirements.txt
```

---

## Assumptions & V1 boundaries

These are stated explicitly because the assessment brief said to call them out instead of guessing:

| Decision | Reason |
|---|---|
| **PDFs are visually inspired by the PRD descriptions, not pixel-matched to the original Canva files** | The original Canva/Word source files weren't provided. The templates use the structural language described in the PRD (green Inflow / red Outflow / blue Private Reserve circles; green client-info pills; gray totals badges). Pixel-matching is a 1–2 hour adjustment once originals are shared. |
| **One shared password instead of per-user auth** | Internal 3-person team. SSO + RBAC + per-user audit log is V2. |
| **No sub-CRUD UI for accounts / liabilities / properties** | Static client data is set in `seed.py`. Editing it would mean another 3 forms; not the highest-leverage thing for a demo. The data shape (JSON columns) supports edit; the UI doesn't ship in V1. |
| **No draft/finalize state machine** | Submitting the form creates a `Report` immediately. Re-submit creates a new one. Immutable archive with SHA256 is V2. |
| **PDFs regenerated from snapshot, not archived** | Reports store the inputs and computed totals as JSON. Re-rendering produces byte-identical output. Makes the demo simpler; a real archive table is trivial to add. |
| **No live totals in the form** | Server renders the preview after submit. One linear flow keeps the Loom narrative tight. Live totals would be ~50 lines of vanilla JS — easy V2 add. |
| **Money stored as integer dollars, not cents** | Source data is whole-dollar (Excel budget worksheet, Pinnacle balances). Avoids cents-conversion confusion. No float math anywhere. |
| **Hard cap of 6 retirement accounts per spouse + 6 non-retirement** | Per PRD note. Variable bubble layout uses 3-column CSS Grid that scales to 4/5/6 columns based on count. Locked by `test_pdf_smoke.py`. |

### Explicitly deferred to V2

- **All API integrations** — RightCapital ("don't trust" — Maryann 49:06), Schwab (advisor login non-shareable — Rebecca 48:14), Pinnacle Bank (secure email), Zillow Zestimate. Deferred *deliberately*, per the PRD's compliance framing — not because they're hard.
- **Plaid** — open question raised by Zaki at 49:28; same compliance concerns as Schwab.
- **Canva export** — Rebecca said the portal itself is the preferred output (13:48); Maryann was open to it (52:42). Deferring matches Rebecca's stated preference.
- **Dropbox auto-save** — mentioned by Maryann (41:23) but not committed. Lightweight to add.
- **Email distribution** — Rebecca said quarterly only; not committed.
- **AI / onboarding agent** — proposed by Zaki at 43:36 as a separate "LEGO brick." Not part of V1.

---

## What I'd build next (V2)

In rough priority order:

1. **Sub-CRUD UI** for accounts / liabilities / properties — small effort, big workflow win once the team starts adding clients beyond the seeded one.
2. **Per-user auth + audit log** — already required for the financial-data nature of the work; deferred only to fit the assessment time budget.
3. **PDF archive with SHA256** — a `generated_pdf` table storing the rendered bytes. Makes "re-download Q1" guaranteed-immutable.
4. **Pixel-match the original Canva templates** — 1–2 hours once originals are shared.
5. **Live totals in the form** — ~50 lines of vanilla JS, no framework.
6. **Plaid integration for non-Schwab balances** — biggest workflow unlock for V2 since it eliminates the email-Pinnacle-Bank step entirely.

---

## Manual QA checklist

Run before any submission:

- [ ] `pytest -q` → 25 passed
- [ ] Login with the demo password works; wrong password shows the error.
- [ ] Dashboard shows Henderson Family with last report = `2026-Q1`, net worth = `$2,416,200`.
- [ ] Client detail shows 3 + 2 + 3 accounts (retirement c1, retirement c2, non-retirement) + 1 trust + 2 liabilities.
- [ ] Start New Quarterly Report → form prefills last-quarter values as `Last quarter: $X` helper text.
- [ ] Submit empty form → red error card lists every missing field.
- [ ] Fill form → preview page shows correct totals (math should match by-hand for at least one row).
- [ ] Download SACS PDF → page 1 has Inflow/Outflow/Reserve diagram, page 2 has reserve-vs-target + cashflow math.
- [ ] Download TCC PDF → all sections present, Grand Total at bottom, layout fits one page.
- [ ] Re-download a past report's PDFs → same content, no errors.
- [ ] Sign out → all routes redirect to login.

---

## Loom walkthrough outline (under 2 minutes)

1. **0:00–0:15 — Problem.** Educated Freedom spends a full day per client preparing two reports — SACS cashflow and TCC net worth — by pulling balances from four sources and assembling in Canva and Word. PRD asks to take this from a day to under an hour.
2. **0:15–0:30 — Decisions.** Flask + WeasyPrint on Railway. Flask because it's a forms-and-PDFs app, not an API. WeasyPrint because the variable TCC bubble layout is a CSS Grid problem, not a coordinate problem. Pure-function calculation service tested against the PRD rules.
3. **0:30–0:55 — Workflow.** Seeded Henderson client → static profile → Start New Quarterly Report → form prefilled with last-quarter values → fill in → submit.
4. **0:55–1:30 — Preview + PDFs.** Preview shows calculated totals. Point at the four PRD rules (trust included in grand total but not non-retirement; liabilities never subtracted). Download both PDFs.
5. **1:30–2:00 — Assumptions and V2.** I don't have the Canva files, so visuals are structural not pixel-exact. Auth is shared password. RightCapital, Schwab, Plaid, Canva export are V2 — deliberately, because the PRD calls out compliance constraints. README has the full list. This is a focused demo, not a production build.
