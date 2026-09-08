# DQ Compass

A generic, catalogue-driven data quality framework.
MBA-ESG / SG GSC Datathon — September 2026.

The engine knows no column name, no threshold and no file. Everything comes
from the catalogue. Adding a control or a file never requires a line of code.

---

## Getting started

### From a clone

```bash
git clone https://github.com/Yassine-Kamali/dq-compass.git
cd dq-compass
python -m venv .venv
./.venv/Scripts/pip install -r requirements.txt      # Windows
# .venv/bin/pip install -r requirements.txt          # macOS / Linux

./.venv/Scripts/python.exe engine/prepare_bis.py     # unzips and prepares the data
./.venv/Scripts/python.exe tests/test_dq.py          # 69 tests, must end at 69/69
```

Only the 4.8 MB source zip is versioned. `prepare_bis.py` extracts it on first
run and regenerates the 112 MB of prepared data in about fifteen seconds, with
identical SHA-256 fingerprints from one machine to the next.

### Day to day

```bash
./.venv/Scripts/python.exe -m streamlit run ui/app.py       # the console — the normal path
./.venv/Scripts/python.exe tests/test_dq.py                 # 69 tests

# from the command line: one file at a time, the contract is detected
./.venv/Scripts/python.exe reporting/excel_report.py data/prepared/bis_turnover.csv
./.venv/Scripts/python.exe engine/dq_engine.py data/ref/ref_devises.csv
```

> This machine's global Python has a pandas 2.1.4 that is incompatible with its
> numpy 2.5.2: any pandas import fails there. **Always use
> `./.venv/Scripts/python.exe`**, never a bare `python`.

---

## Architecture

Four components, one direction of dependency: nothing points back at the
catalogue.

| # | Component | File | Role |
|---|---|---|---|
| 1 | Catalogue | `catalogue/store.json` | **DEFINES** the controls — single source of truth |
| 2 | Engine | `engine/dq_engine.py` | **RUNS** them, whatever the file |
| 3 | Reporting | `reporting/excel_report.py` | **DELIVERS** the business workbook |
| 4 | Audit | `evidence/<run_id>/` | **PROVES** the run, replayable |

The console (`ui/app.py`) drives the catalogue; it holds no control logic.

### One run, one file — usually a file nobody has seen

The real starting point is someone dropping a file that has never been
described. So the engine reads the columns, matches them against the known
contracts, and if none fits it **profiles the file and proposes a structure**
right where the file was refused — not in a screen of its own.

Reference tables are never something the user supplies. The engine fetches them
itself when a referential integrity control needs one, and fingerprints them
like any other source.

A contract describes a **structure**, not a file: the demonstration extract and
the full file both satisfy the `bis_turnover` contract.

### No jargon in the console

Nobody sees `MATCHES_REGEX` or `{"column": "amount"}`. They read “Must follow a
precise format” and “Column amount must match the format ^[0-9]+$”. That
vocabulary is carried by the **catalogue** (`libelle_metier`,
`question_metier`, `phrase`, `params_libelles`), not by the console code:
adding a rule type is enough to make it usable in plain language.

The editor walks through four steps — what to check, on what, what happens when
it fails, how to name it — and refuses to save while the name, the rationale or
the remediation action is missing. Tolerances are offered in words rather than
as a free numeric field.

### What makes a rule universal

A rule targets either a **column** (`{"column": "amount"}`) or a **role**
(`{"role": "identifier"}`). With a role and a `*` scope, one catalogue row
applies to every described file — including files that do not exist yet.
Describing a new file is enough to bring every cross-file control to bear on it.

### Governance enforced by the tool

- **No deletion.** `delete_control()` raises; the console offers Pause and
  Retire. Audit requires historical runs to stay replayable.
- **Automatic versioning.** Any change to an executable field (rule type,
  settings, scope, threshold, status) bumps the version and updates
  `effective_from`.
- **Change log.** Who, when, which field, before → after, and why. Visible in
  the console and in the `CHANGE_LOG` sheet of the workbook.

---

## The output workbook

`reporting/sorties/DQ_Rapport_<run_id>.xlsx`, six sheets, self-contained:

| Sheet | Contents |
|---|---|
| `SUMMARY` | **Failing controls first and largest**, then the detail: one row per control, its plain-English reading, traffic lights |
| `EXCEPTIONS` | Row-level detail, filterable by rule and severity |
| `COVERAGE` | Dimensions × files, coverage gaps, breakdown by severity |
| `EVIDENCE` | Run ID, SHA-256 of every source and of the catalogue, refused rules |
| `RULES_APPLIED` | Frozen copy of the rules exactly as they ran |
| `CHANGE_LOG` | Catalogue change history |

---

## Results on the real data

BIS Triennial Survey, OTC derivatives turnover — 77,992 raw rows,
**425,371 observations** once pivoted to long format.

Full run: **6.7 s**, Excel report and reference table loading included.
15 controls apply to the `bis_turnover` contract, across 6 dimensions,
13 pass / 2 fail.

Both failures are genuine business findings:

- **DQ03** — 2 negative notional turnovers out of 425,371. Escalated to the
  Market Data Office.
- **DQ09** — 32 rows carrying `CLS` as the leg-2 currency. `CLS` is a
  settlement mechanism, not a currency: Data Steward arbitration, either enrich
  the reference table or reject the rows.

### Two calibrations worth telling

The first run produced two failures for the wrong reasons. The corrections are
recorded in the change log (`engine/apply_calibration.py`):

**DQ05 — 22,063 false positives.** The format `^[A-Z]{3}$` rejected `TO1`,
which is the official BIS aggregate code. 100 % of the exceptions came from the
rule, not from the data. A valid format has to admit the aggregate.

**DQ13 — a reconciliation control measuring the wrong thing.** Across 1,024
aggregates, 781 have a country sum *below* the world total, 243 are equal, and
**none exceeds it**. The gap is structural — the BIS total includes
jurisdictions that are not published individually. The control was split:

- `DQ13` (Reconciliation, Blocking) — the country sum may **never exceed** the
  total. Exceeding it would mean double counting. → 0 exceptions.
- `DQ16` (Completeness, Moderate) — the published breakdown must cover ≥ 95 %
  of the total. → 14 aggregates below the threshold, median coverage 99.90 %.

Same arithmetic, two dimensions, two owners, two remediations.

---

## Demonstration sequence

1. **Drop a file** (90 s) — *Check a file* → `bis_turnover_demo.csv`. The
   console announces “Recognised as: BIS Triennial Survey, 100 % of the
   expected columns”, lists the applicable rules, then runs. **The number of
   failing controls comes first and largest**, followed by who has to do what.
2. **The workbook** (90 s) — download the report. Same hierarchy: failures
   first, every rule rendered in plain English, then exceptions, coverage and
   evidence. This is what the business receives.
3. **Write a rule without being a data person** (2 min) — *Control rules* →
   *New rule*. You pick “Must never be empty”, never `NOT_NULL`. The summary
   writes the sentence as you go. The save button stays disabled while the
   remediation action is missing: an orphan rule cannot be produced.
4. **The validator** (1 min) — pick “Must stay within numeric bounds” on
   `DER_BASIS`, a text column. Refused immediately, with a clear message,
   before execution. A malformed rule never breaks a run.
5. **Deletion refused** (30 s) — select a rule, click Delete. The tool explains
   that reports already issued must stay explainable, and points at *Pause*.
6. **An unknown file** (2 min) — drop `data/exemples/inventaire.csv`. The
   console says it is new, reads it, and **proposes a structure**: types,
   roles, which column looks like the key, which column matches a reference
   table. It flags that `article_id` looks like an identifier but carries an
   empty value and a duplicate. Tick it as the key, save, run: two cross-file
   rules catch both defects. No rule written, no code changed.
7. **Reproducibility** (30 s) — run the same file again. Identical
   fingerprints, identical results, a different `run_id`.

---

## Layout

```
catalogue/store.json          source of truth (rule types, contracts, controls, log)
engine/store.py               CRUD, versioning, audit log, plain-English rendering
engine/dq_engine.py           validator, 12 executors, runner, evidence pack
engine/profiling.py           profiles an unknown file, proposes its contract
engine/prepare_bis.py         data and reference table preparation
engine/bootstrap_store.py     catalogue initialisation
engine/apply_calibration.py   calibrations recorded in the change log
engine/add_libelles_metier.py plain-language layer for the rule types
engine/translate_catalogue.py catalogue translation to English
engine/fusion_contrats.py     merge of redundant contracts
reporting/excel_report.py     six-sheet workbook
ui/app.py                     Streamlit console, three screens
tests/test_dq.py              69 tests, no external dependency
docs/GUIDE_TEST.md            step-by-step test protocol
data/raw/                     original BIS source (zip)
data/prepared/                long format plus demonstration extract
data/ref/                     currency and country reference tables
data/exemples/                unknown file used to demonstrate profiling
data/entrees/                 files dropped through the console
evidence/<run_id>/            proof of execution
reporting/sorties/            generated workbooks
```
