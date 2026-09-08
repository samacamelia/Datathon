# Test protocol — DQ Compass

Run through this before the presentation. Each step says **what you do** and
**what you must see**. If the screen does not show what is stated here, that is
a bug: note it down rather than improvising in front of the jury.

Allow 25 minutes.

---

## 0. Prepare (2 min)

Open a terminal in the project folder.

```bash
cd "c:/Users/yassi/Desktop/DQ Project"
./.venv/Scripts/python.exe tests/test_dq.py
```

> **Expected:** the last line reads `69/69 tests reussis`.
> If a test fails, fix it before going on — the console rests on it.

Then start the console:

```bash
./.venv/Scripts/python.exe -m streamlit run ui/app.py
```

> **Expected:** the browser opens on `http://localhost:8501` (or 8555 if an
> earlier instance is still up). Sidebar reads “🧭 DQ Compass” with three
> entries only: **Check a file**, **Control rules**, **Change log**.

⚠️ Always `./.venv/Scripts/python.exe`, never a bare `python`: this machine's
global Python has a broken pandas.

---

## 1. Check a known file (4 min)

**You do:** *Check a file* → *Pick a file already here* →
`bis_turnover_demo.csv`.

> **Expected, before running anything:**
> - green banner **“Recognised as: BIS Triennial Survey — OTC derivatives
>   turnover”**, *100 % of the expected columns are present*, *57 918 rows,
>   26 columns*;
> - the list of **15 rules** that apply, each with its plain-English reading;
> - a foldable preview of the first 50 rows.

**You do:** *Run the controls*.

> **Expected:**
> - the large banner reads **“1 control failing”**, in red, *1 of them Blocking
>   or Important*;
> - directly underneath: **DQ09 · Referential integrity — currency leg 2**,
>   *32 rows off out of 57 918*, owner *Referential Management*, and what to do;
> - secondary counters: 15 controls run, 14 clean, 46 rows in exception,
>   0 rules refused.

**What to check:** the failure count is **the first thing you can read**. The
conformity rate appears only later, in the workbook.

**You do:** open the *Control detail* tab.

> **Expected:** a **“What it checks”** column in plain English, such as *“Every
> DER_CURR_LEG2 must exist in reference table ref_devises”*. No rule type
> identifiers, no JSON.

---

## 2. The Excel workbook (3 min)

**You do:** *Download the Excel report*, then open it.

> **Expected, `SUMMARY` sheet:**
> - first tile, very large, on a red background: **1**, labelled
>   `CONTROLS FAILING`;
> - second tile: `of them Blocking / Important`;
> - the conformity rate only **fourth**;
> - the table sorted **failures first**, with a `What it checks` column in
>   plain English.

> **Expected, the six sheets:** `SUMMARY`, `EXCEPTIONS`, `COVERAGE`,
> `EVIDENCE`, `RULES_APPLIED`, `CHANGE_LOG`.

**Worth showing the jury:** the `EVIDENCE` sheet carries the SHA-256 of the
file checked **and** of the catalogue. That is what makes the run replayable.

---

## 3. Write a rule without being a data person (5 min)

This is the step that answers “anyone must be able to use it”.

**You do:** *Control rules* → *New rule*.

> **Expected, step 1:** a list of choices in plain English — *Must never be
> empty*, *Must contain no duplicate*, *Must belong to an allowed list*, *Must
> stay within numeric bounds*… Each choice shows its explanation and a concrete
> example. **No `NOT_NULL` anywhere on screen.**

**You do:** pick *Must stay within numeric bounds*, file `bis_turnover`, column
`turnover_notionnel`, tick `min` = 0.

> **Expected, Summary box:**
> *“Column “turnover_notionnel” must be greater than or equal to 0.”*
> The sentence rewrites itself on every change.

**You do:** try to save **without** filling the name or the remediation action.

> **Expected:** message *“Still needed: the rule name, why the rule exists,
> what to do when it fails”*, and **Save stays greyed out**.

That guard rail was missing before: control `DQ17` in the catalogue was created
with no description, no remediation and a 0.9 % threshold entered by accident.
That is no longer possible.

**You do:** fill the three fields, save.

> **Expected:** green message *“Rule DQ18 created”*, and the rule appears in the
> list with its plain-English sentence.

---

## 4. Editing a rule is one gesture (2 min)

This is what did not work before: the actions sat at the bottom of the page,
behind a dropdown.

**You do:** *Control rules* → **click any row of the table**.

> **Expected:** a panel appears **immediately under the table**, naming the
> selected rule, showing what it checks, its severity, its owner and its
> version, with four buttons: **Edit this rule**, **Pause**, **Put back live**,
> **Delete**.
> Before you click a row, those buttons are absent and the console says
> *“Click a row above to edit it, pause it, or put it back live.”*

**You do:** *Edit this rule*, change something, save.

> **Expected:** the version increments, and the change shows up in *Change log*.

---

## 5. The validator refuses an absurd rule (2 min)

**You do:** *New rule* → *Must stay within numeric bounds* → column
**`DER_BASIS`** (a text column).

> **Expected:** red box *“The validator refuses this rule: RANGE needs a
> numeric column; 'DER_BASIS' is declared as 'string'”*, Save greyed out.

**The point:** the refusal happens **before** any execution. A badly defined
rule cannot break a run in progress.

---

## 6. Deletion is refused (1 min)

**You do:** select a rule → **Delete**.

> **Expected:** an error explaining that reports already issued must stay
> explainable, pointing at *Pause*.

**You do:** *Pause*, then go to *Change log*.

> **Expected:** at the top of the log, a timestamped line under your name,
> action `MODIFICATION`, field `statut`, `Actif` → `Suspendu`, with your
> reason. A second `VERSION` line shows the version going up.

**Remember to put the rule back live** before the demo.

---

## 7. An unknown file — the strong sequence (6 min)

This is what proves the framework is generic. A test file is ready:
`data/exemples/inventaire.csv`, unrelated to the BIS data.

**You do:** *Check a file* → *Drop a file* → drop
`data/exemples/inventaire.csv`.

> **Expected:** an orange banner *“This file is new. The closest known
> structure is Currency reference table at 33 % of its expected columns, under
> the 70 % threshold.”*
> Then, on the same screen, **Describe this file** with a table the engine
> filled in by itself:
>
> | Column | Type | Role | Identifier key | Reference table |
> |---|---|---|---|---|
> | article_id | string | identifier | ☐ | |
> | libelle | string | label | ☐ | |
> | code_devise | string | code | ☐ | ref_devises |
> | quantite | integer | measure | ☐ | |
> | prix_unitaire | decimal | measure | ☐ | |
> | date_inventaire | date | event_date | ☐ | |
>
> And a warning above it: *“**article_id** — Looks like an identifier but
> contains 1 empty value and 1 duplicate. Mark it as the key so the controls
> report it.”*

**What to point out:** nobody typed any of that. The engine read the file. It
inferred that `prix_unitaire` is a decimal and `quantite` an integer, that
`date_inventaire` is a date, that `code_devise` matches the currency reference
table — and it did **not** claim `article_id` is a clean key, because it is not.

**You do:** tick **Identifier key** on `article_id`, then *Save this
description*.

> **Expected:** *“Inventaire described with 6 columns. 2 rule(s) already apply
> to it — none of them had to be written.”*

Those two rules are `DQ02` (identifiers must be present) and `DQ07` (primary
keys must be unique). They target a **role**, not a column name, so they reach
every file that gets described.

**You do:** run the controls on the same file.

> **Expected:**
> - **2 controls failing**;
> - `DQ02`: 1 row off out of 6 — the empty identifier;
> - `DQ07`: 2 rows off out of 6 — `ART-002` appearing twice;
> - 3 rows in exception in total.

**The line to say to the jury:** *“No rule written, no line of code changed, a
file fully under control.”*

---

## 8. Reproducibility (2 min)

**You do:** run the same file again.

> **Expected:** identical results, identical SHA-256 in the `EVIDENCE` sheet,
> but a different `run_id`.

Every run left a folder under `evidence/`. Open the last one:

```bash
ls evidence/ | tail -1
```

> **Expected:** six files — `manifest.json`, `catalogue_snapshot.json`,
> `results.json`, `rejets.json`, `exceptions.csv`, `execution.log`.

`catalogue_snapshot.json` is a **frozen copy** of the rules as they ran, not a
link to the live catalogue: that is what lets you explain a report from three
months ago even though the rules have changed since.

---

## Before the presentation

- [ ] `69/69 tests reussis`
- [ ] Any rule you paused in step 6 put back live
- [ ] The `inventaire` contract **removed from the catalogue** if you want to
      replay step 7 live — otherwise the file will already be recognised
- [ ] A screenshot of each step, as a fallback if the live demo fails
- [ ] The stray `data/entrees/DQ_Rapport_*.xlsx` dropped by accident during
      earlier trials: delete it, it clutters the file picker

To put the catalogue back to its starting state:

```bash
git checkout catalogue/store.json
```

> ⚠️ This discards **all** your rule changes, including any you meant to keep.
> Check with `git diff --stat` first.
