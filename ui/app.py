"""
DQ Compass — control catalogue console.

Three screens: Check a file, Control rules, Change log.

Three decisions shape the whole interface:

1. ONE FILE AT A TIME, AND IT IS USUALLY UNKNOWN. The real starting point is
   someone dropping a file nobody has described. So describing a file happens
   right where it is refused, not in a screen of its own, and the engine
   proposes the structure it reads in the data. Reference tables are never
   something the user supplies: the engine fetches them itself.

2. NO JARGON. Nobody sees a template_id or a settings dictionary. They read
   "Must never be empty" and "Column amount must be filled in on every row".
   That vocabulary lives in the CATALOGUE, not here: adding a rule type is
   enough to make it usable in plain language, with no change to this file.

3. FAILURES FIRST. The count of failing controls is the only number that
   triggers a decision, so it comes first and largest.

    streamlit run ui/app.py
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import sys

import pandas as pd
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "reporting"))

from dq_engine import (ContratIntrouvable, DatasetLoader, charger_fichier,  # noqa: E402
                       detecter_contrat, run_dq, validate_control)
from excel_report import build_workbook  # noqa: E402
from profiling import (clean_contract, propose_contract,  # noqa: E402
                       suggest_foreign_keys)
from store import (SEVERITES, SEVERITES_AIDE, STATUTS, CatalogueStore,  # noqa: E402
                   libelle_severite, libelle_statut, phrase_controle)

st.set_page_config(page_title="DQ Compass", page_icon="🧭", layout="wide")

INBOX = ROOT / "data" / "entrees"
BROWSABLE = [ROOT / "data" / "entrees", ROOT / "data" / "prepared",
             ROOT / "data" / "ref", ROOT / "data" / "exemples"]

DOT_STATUS = {"Actif": "🟢", "Suspendu": "🟠", "Deprecie": "⚪"}
DOT_RUN = {"PASS": "🟢", "FAIL": "🔴", "ERREUR": "🟠", "NON_APPLICABLE": "⚪"}

COLUMN_TYPES = ["string", "integer", "decimal", "date"]
COLUMN_ROLES = ["identifier", "code", "measure", "label", "event_date",
                "technical_date"]

# Tolerances offered in plain words. A free numeric field stays available but
# is no longer the default path: that is what produced a stray 0.9 % threshold.
TOLERANCES = {
    "No gap tolerated": 0.0,
    "Up to 1 % of rows": 1.0,
    "Up to 5 % of rows": 5.0,
    "Up to 10 % of rows": 10.0,
}

FREQUENCIES = ["Daily", "Weekly", "Monthly", "Quarterly", "Annual", "On demand"]

# Settings that name a column of the file: offer a list, never free text.
PARAM_COLUMN = {"column", "field_a", "field_b", "before", "after", "amount",
                "total_column"}
PARAM_NUMBER = {"min", "max", "max_lag_days", "tolerance_pct", "couverture_min_pct"}

DETECTION_THRESHOLD = 0.7


# --------------------------------------------------------------------------- #
# Shared state
# --------------------------------------------------------------------------- #
def get_store(force: bool = False) -> CatalogueStore:
    if force or "store" not in st.session_state:
        st.session_state.store = CatalogueStore()
    return st.session_state.store


def commit(store: CatalogueStore, message: str) -> None:
    store.save()
    get_store(force=True)
    st.session_state["flash"] = message


def show_flash() -> None:
    if message := st.session_state.pop("flash", None):
        st.success(message)


def display_name(store: CatalogueStore, dataset: str) -> str:
    ds = store.dataset(dataset)
    return ds["libelle"] if ds else dataset


def scope_datasets(store: CatalogueStore, scope: str) -> list[str]:
    scope = (scope or "").strip()
    if scope in ("", "*"):
        return list(store.datasets)
    return [s.strip() for s in scope.split(",") if s.strip() in store.datasets]


def scope_columns(store: CatalogueStore, scope: str) -> list[str]:
    names: list[str] = []
    for ds in scope_datasets(store, scope):
        for c in store.columns_of(ds):
            if c["colonne"] not in names:
                names.append(c["colonne"])
    return names


def available_roles(store: CatalogueStore) -> list[str]:
    roles = {c.get("role", "") for ds in store.datasets
             for c in store.columns_of(ds) if c.get("role")}
    return sorted(roles | {"primary_key"})


def template_params(tpl: dict) -> tuple[list[list[str]], list[str]]:
    def split(text: str) -> list[list[str]]:
        out = []
        for part in str(text or "").split(","):
            part = part.strip()
            if part:
                out.append([a.strip() for a in part.split("|") if a.strip()])
        return out
    return (split(tpl.get("params_requis", "")),
            [a for g in split(tpl.get("params_optionnels", "")) for a in g])


def param_label(tpl: dict, name: str) -> str:
    return tpl.get("params_libelles", {}).get(name, name)


# --------------------------------------------------------------------------- #
# Screen 1 — Check a file
# --------------------------------------------------------------------------- #
def browsable_files() -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    for folder in BROWSABLE:
        if folder.exists():
            found += sorted(p for p in folder.iterdir()
                            if p.suffix.lower() in {".csv", ".xlsx", ".xls", ".xlsm"})
    return found


def suggest_technical_name(path: pathlib.Path) -> str:
    stem = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")
    return stem or "new_file"


def describe_file(store: CatalogueStore, user: str, df: pd.DataFrame,
                  path: pathlib.Path) -> None:
    """Declare the contract of an unknown file, from a proposal the engine reads
    in the data. This is the whole point of the tool, so it happens here rather
    than in a screen of its own."""
    st.markdown("#### Describe this file")
    st.caption("The engine read the file and proposes the structure below. "
               "Correct what is wrong — you only have to be right about the "
               "identifier and the roles.")

    proposal = propose_contract(df)
    loader = DatasetLoader(store)
    for fk in suggest_foreign_keys(df, store, loader.load):
        for col in proposal:
            if col["colonne"] == fk["colonne"]:
                col["fk_dataset"] = fk["fk_dataset"]
                col["fk_colonne"] = fk["fk_colonne"]

    alerts = [c for c in proposal if c.get("_alerte")]
    for col in alerts:
        st.warning(f"**{col['colonne']}** — {col['_alerte']}")

    c1, c2 = st.columns(2)
    with c1:
        technical = st.text_input("Short name", suggest_technical_name(path),
                                  help="Used internally. Lower case, no spaces.")
        business = st.text_input("Business name", path.stem.replace("_", " ").title())
    with c2:
        owner = st.text_input("Who owns this file?", "Data Steward")
        try:
            source = str(path.relative_to(ROOT)).replace("\\", "/")
        except ValueError:
            source = str(path).replace("\\", "/")
        st.text_input("Reference path", source, disabled=True)

    editable = pd.DataFrame([{
        "Column": c["colonne"],
        "Type": c["type"],
        "Role": c["role"],
        "Identifier key": c["cle_primaire"] == "OUI",
        "Always filled": c["obligatoire"] == "OUI",
        "Reference table": c["fk_dataset"],
        "Reference column": c["fk_colonne"],
        "Filled %": c["_taux_remplissage"],
        "Distinct": c["_valeurs_distinctes"],
        "Examples": c["_exemples"],
    } for c in proposal])

    edited = st.data_editor(
        editable, width='stretch', hide_index=True, num_rows="fixed",
        key="contract_editor",
        column_config={
            "Column": st.column_config.TextColumn(disabled=True, width="medium"),
            "Type": st.column_config.SelectboxColumn(options=COLUMN_TYPES,
                                                     required=True),
            "Role": st.column_config.SelectboxColumn(
                options=COLUMN_ROLES, required=True,
                help="Cross-file rules target a role, not a column name."),
            "Identifier key": st.column_config.CheckboxColumn(
                help="Uniqueness checks run on the columns ticked here."),
            "Always filled": st.column_config.CheckboxColumn(),
            "Reference table": st.column_config.SelectboxColumn(
                options=[""] + list(store.datasets)),
            "Reference column": st.column_config.TextColumn(),
            "Filled %": st.column_config.NumberColumn(disabled=True, format="%.1f %%"),
            "Distinct": st.column_config.NumberColumn(disabled=True),
            "Examples": st.column_config.TextColumn(disabled=True, width="medium"),
        })

    keys = [r["Column"] for _, r in edited.iterrows() if r["Identifier key"]]
    st.caption(f"Identifier key: {', '.join(keys) if keys else 'none ticked yet'}")

    problems = []
    if not technical.strip():
        problems.append("a short name")
    if technical.strip() in store.datasets:
        problems.append(f"a short name that is not already taken "
                        f"(“{technical}” exists)")
    if problems:
        st.warning("Still needed: " + ", ".join(problems) + ".")

    if st.button("Save this description", type="primary", disabled=bool(problems)):
        columns = clean_contract([{
            "colonne": r["Column"], "type": r["Type"], "role": r["Role"],
            "cle_primaire": "OUI" if r["Identifier key"] else "NON",
            "obligatoire": "OUI" if r["Always filled"] else "NON",
            "description": "",
            "fk_dataset": r["Reference table"], "fk_colonne": r["Reference column"],
        } for _, r in edited.iterrows()])
        store.upsert_dataset(technical.strip(), {
            "libelle": business.strip() or technical.strip(), "source": source,
            "proprietaire": owner.strip(), "colonnes": columns},
            user, "File described from the check screen")
        applicable = len(store.active_controls(technical.strip()))
        commit(store, f"“{business or technical}” described with {len(columns)} "
                      f"columns. {applicable} rule(s) already apply to it — "
                      f"none of them had to be written.")
        st.rerun()


def result_banner(run) -> None:
    """The failure count first and largest: it is the only number that asks for
    a decision. The conformity rate only reassures."""
    s = run.summary()
    failures, errors = s["fail"], s["erreur"]
    sc = run.scorecard
    blocking = int(((sc["statut"] == "FAIL") & (sc["severity"].isin(
        ["Critical", "High"]))).sum()) if not sc.empty else 0

    if failures or errors:
        colour, background, border = "#B3261E", "#FCE8E6", "#F2B8B5"
        title = f"{failures} control{'s' if failures != 1 else ''} failing"
        if errors:
            title += f" · {errors} technical error{'s' if errors > 1 else ''}"
        rows = f"{s['exceptions']:,} row(s) to look into".replace(",", " ")
        subtitle = (f"{blocking} of them Blocking or Important — {rows}"
                    if blocking else rows)
    else:
        colour, background, border = "#1E7B34", "#E6F4EA", "#A8DAB5"
        title = "No control failing"
        subtitle = f"{s['controles']} control(s) passed with no gap"

    st.markdown(
        f"""<div style="background:{background};border:2px solid {border};
        border-radius:12px;padding:22px 26px;margin:6px 0 18px 0;">
        <div style="font-size:46px;font-weight:700;color:{colour};
        line-height:1.05;">{title}</div>
        <div style="font-size:15px;color:{colour};opacity:.85;margin-top:6px;">
        {subtitle}</div></div>""",
        unsafe_allow_html=True)

    if failures or errors:
        for _, r in sc[sc["statut"].isin(["FAIL", "ERREUR"])].iterrows():
            st.markdown(
                f"**{r['rule_id']} · {r['control_name']}** — "
                f"{libelle_severite(r['severity'])}  \n"
                f"{r['lignes_ko']:,} row(s) off out of {r['lignes_testees']:,} "
                f"· owner: {r['owner']}  \n"
                f"→ *{r['remediation_action'] or 'No remediation action defined.'}*"
                .replace(",", " "))

    c = st.columns(4)
    c[0].metric("Controls run", s["controles"])
    c[1].metric("Clean", s["pass"])
    c[2].metric("Rows in exception", f"{s['exceptions']:,}".replace(",", " "))
    c[3].metric("Rules refused", s["rejets"],
                help="Rules found malformed and set aside before execution.")


def screen_check(store: CatalogueStore, user: str) -> None:
    st.header("Check a file")
    st.caption("Drop a file. If the system has never seen it, it reads the file "
               "and proposes a description. Reference tables are loaded on their "
               "own — you never have to supply them.")
    show_flash()

    tab_drop, tab_pick = st.tabs(["📎 Drop a file", "📂 Pick a file already here"])
    path: pathlib.Path | None = None

    with tab_drop:
        dropped = st.file_uploader("CSV or Excel file",
                                   type=["csv", "xlsx", "xls", "xlsm"])
        if dropped is not None:
            INBOX.mkdir(parents=True, exist_ok=True)
            path = INBOX / dropped.name
            path.write_bytes(dropped.getbuffer())
            st.caption(f"Saved to `data/entrees/{dropped.name}`")

    with tab_pick:
        files = browsable_files()
        if files:
            picked = st.selectbox(
                "File", files, index=None, placeholder="Choose a file…",
                format_func=lambda p: f"{p.name}  ({p.stat().st_size / 1e6:.1f} MB)")
            if picked is not None:
                path = picked
        else:
            st.info("No file found under `data/`.")

    if path is None:
        st.stop()

    try:
        df = charger_fichier(path)
    except (ValueError, FileNotFoundError) as exc:
        st.error(f"Cannot read this file: {exc}")
        st.stop()

    candidates = detecter_contrat(df.columns, store)
    best, score = candidates[0] if candidates else (None, 0.0)
    recognised = score >= DETECTION_THRESHOLD

    st.divider()
    if recognised:
        left, right = st.columns([2, 1])
        with left:
            st.success(f"**Recognised as: {display_name(store, best)}**  \n"
                       f"{score:.0%} of the expected columns are present. "
                       f"{len(df):,} rows, {len(df.columns)} columns."
                       .replace(",", " "))
        with right:
            options = [n for n, _ in candidates]
            contract = st.selectbox(
                "Treat this file as", options, index=options.index(best),
                format_func=lambda n: f"{display_name(store, n)} "
                                      f"({dict(candidates)[n]:.0%})")
    else:
        st.warning(
            f"**This file is new.** The closest known structure is "
            f"“{display_name(store, best) if best else '—'}” at {score:.0%} of "
            f"its expected columns, under the {DETECTION_THRESHOLD:.0%} "
            f"threshold. Describe it below and the rules will apply.")
        describe_file(store, user, df, path)
        st.stop()

    with st.expander(f"Preview — {len(df):,} rows".replace(",", " ")):
        st.dataframe(df.head(50), width='stretch', hide_index=True)

    applicable = store.active_controls(contract)
    with st.expander(f"{len(applicable)} rule(s) apply to this file", expanded=True):
        st.dataframe(pd.DataFrame({
            "Rule": [c["rule_id"] for c in applicable],
            "Name": [c["control_name"] for c in applicable],
            "What it checks": [phrase_controle(c, store) for c in applicable],
            "Severity": [libelle_severite(c["severity"]) for c in applicable],
        }), width='stretch', hide_index=True)

    label = st.text_input("Run label (appears in the report)",
                          f"Check of {path.name}")
    if st.button("▶️ Run the controls", type="primary", width='stretch'):
        with st.spinner("Running…"):
            try:
                run = run_dq(path, dataset=contract, store=store, run_label=label)
            except ContratIntrouvable as exc:
                st.error(str(exc))
                st.stop()
            workbook = build_workbook(run, store)
        st.session_state["last_run"] = run
        st.session_state["last_workbook"] = workbook

    run = st.session_state.get("last_run")
    if run is None:
        return

    st.divider()
    st.subheader(f"Result — {pathlib.Path(run.fichier).name}")
    result_banner(run)

    workbook = st.session_state.get("last_workbook")
    if workbook and pathlib.Path(workbook).exists():
        st.download_button(
            "⬇️ Download the Excel report", type="primary",
            data=pathlib.Path(workbook).read_bytes(),
            file_name=pathlib.Path(workbook).name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    t1, t2, t3, t4 = st.tabs(["Control detail", "Rows in exception",
                              "Rules refused", "Technical log"])
    with t1:
        sc = run.scorecard
        st.dataframe(pd.DataFrame({
            "": sc["statut"].map(DOT_RUN),
            "Rule": sc["rule_id"],
            "Name": sc["control_name"],
            "What it checks": [phrase_controle(store.control(r) or {}, store)
                               for r in sc["rule_id"]],
            "Severity": sc["severity"].map(libelle_severite),
            "Rows off": sc["lignes_ko"],
            "Rows tested": sc["lignes_testees"],
            "Indicator": sc["kpi_nom"] + ": " + sc["kpi_valeur"].astype(str),
            "Owner": sc["owner"],
        }), width='stretch', hide_index=True)
    with t2:
        st.dataframe(run.exceptions.head(2000).rename(columns={
            "rule_id": "Rule", "dataset": "File", "severity": "Severity",
            "index_source": "Row #", "identifiant_ligne": "Row identifier",
            "colonne": "Column", "valeur": "Value", "motif": "Reason"}),
            width='stretch', hide_index=True)
        st.caption(f"{len(run.exceptions):,} exception(s) — first 2 000 shown. "
                   "The Excel report carries the full detail.".replace(",", " "))
    with t3:
        st.dataframe(pd.DataFrame(run.rejets).rename(columns={
            "rule_id": "Rule", "dataset": "File", "control_name": "Name",
            "motif": "Why it was refused"}), width='stretch', hide_index=True)
        st.caption("Rules set aside by the validator before execution: a "
                   "malformed rule never breaks a run.")
    with t4:
        st.code("\n".join(run.journal), language="text")
    st.caption(f"Evidence pack: `{run.evidence_path}`")


# --------------------------------------------------------------------------- #
# Screen 2 — Control rules
# --------------------------------------------------------------------------- #
def param_widget(name: str, tpl: dict, store: CatalogueStore, scope: str,
                 value, key: str):
    label = param_label(tpl, name)
    columns = scope_columns(store, scope)

    if name == "role":
        options = available_roles(store)
        return st.selectbox(label, options,
                            index=options.index(value) if value in options else 0,
                            key=key,
                            help="The rule applies to every column carrying this "
                                 "role, in every file in scope — including files "
                                 "described later.")
    if name in PARAM_COLUMN and columns:
        return st.selectbox(label, columns,
                            index=columns.index(value) if value in columns else None,
                            placeholder="Choose a column…", key=key)
    if name in PARAM_NUMBER:
        return st.number_input(label, value=float(value) if value is not None else 0.0,
                               step=1.0, key=key)
    if name == "values":
        raw = st.text_input(
            label, key=key, placeholder="Permanent, Fixed-term, Intern",
            value=", ".join(str(v) for v in value) if isinstance(value, list)
            else (value or ""),
            help="Separate the values with commas.")
        return [v.strip() for v in raw.split(",") if v.strip()]
    if name in ("columns", "group_by"):
        default = value if isinstance(value, list) else []
        return st.multiselect(label, columns,
                              default=[c for c in default if c in columns], key=key)
    if name == "ref_dataset":
        options = list(store.datasets)
        return st.selectbox(label, options,
                            index=options.index(value) if value in options else None,
                            placeholder="Choose a reference table…",
                            format_func=lambda n: display_name(store, n), key=key)
    if name == "ref_column":
        ref = st.session_state.get("param_ref_dataset")
        options = [c["colonne"] for c in store.columns_of(ref)] if ref else []
        if not options:
            return st.text_input(label, value=value or "", key=key)
        return st.selectbox(label, options,
                            index=options.index(value) if value in options else 0,
                            key=key)
    if name == "sens":
        options = {"parties_max": "Parts must not exceed the total",
                   "couverture_min": "Parts must cover a minimum of the total",
                   "bilateral": "Any gap counts, in either direction"}
        keys = list(options)
        return st.selectbox(label, keys,
                            index=keys.index(value) if value in keys else 0,
                            format_func=lambda k: options[k], key=key)
    return st.text_input(label, value="" if value is None else str(value), key=key)


def rule_editor(store: CatalogueStore, user: str, control: dict | None) -> None:
    creating = control is None
    control = control or {}
    st.subheader("New control rule" if creating
                 else f"Editing {control['rule_id']} · "
                      f"version {control.get('version', 1)}")

    st.markdown("#### 1. What do you want to check?")
    simple = [t for t in store.templates if t.get("niveau", "simple") == "simple"]
    advanced = [t for t in store.templates if t.get("niveau") == "avance"]

    current = control.get("template")
    show_advanced = st.toggle(
        "Show advanced rule types",
        value=any(t["template_id"] == current for t in advanced),
        help="Reconciliations and custom conditions. For data profiles.")
    offered = simple + advanced if show_advanced else simple

    def label_of(t: dict) -> str:
        return t.get("libelle_metier", t["template_id"])

    index = next((i for i, t in enumerate(offered)
                  if t["template_id"] == current), 0)
    tpl = st.radio("Rule type", offered, index=index, format_func=label_of,
                   key="edit_template", label_visibility="collapsed")
    st.info(f"**{label_of(tpl)}** — {tpl.get('explication', '')}  \n"
            f"*Example: {tpl.get('exemple_metier', '—')}*")

    st.markdown(f"#### 2. {tpl.get('question_metier', 'On what data?')}")
    datasets = list(store.datasets)
    default_scope = control.get("dataset_scope", datasets[0] if datasets else "*")
    every = st.checkbox(
        "Apply to every file, present and future", value=default_scope.strip() == "*",
        help="Combine with a role target and the rule spreads to new files on "
             "its own.")
    if every:
        scope = "*"
    else:
        chosen = st.multiselect(
            "Files in scope", datasets,
            default=[d for d in default_scope.split(",") if d.strip() in datasets]
            or datasets[:1],
            format_func=lambda n: display_name(store, n))
        scope = ",".join(chosen)

    current_params: dict = {}
    if control.get("params") and control.get("template") == tpl["template_id"]:
        try:
            current_params = json.loads(control["params"])
        except json.JSONDecodeError:
            current_params = {}

    required, optional = template_params(tpl)
    params: dict = {}
    for group in required:
        if len(group) == 1:
            name = group[0]
        else:
            labels = {g: param_label(tpl, g) for g in group}
            default = next((a for a in group if a in current_params), group[0])
            name = st.radio("How should the target be named?", group,
                            index=group.index(default), horizontal=True,
                            format_func=lambda g: labels[g],
                            key=f"choice_{'_'.join(group)}")
        value = param_widget(name, tpl, store, scope, current_params.get(name),
                             f"param_{name}")
        if value not in (None, "", []):
            params[name] = value

    if optional:
        with st.expander("Further settings",
                         expanded=any(o in current_params for o in optional)):
            for name in optional:
                if st.checkbox(param_label(tpl, name), value=name in current_params,
                               key=f"opt_{name}"):
                    value = param_widget(name, tpl, store, scope,
                                         current_params.get(name), f"param_{name}")
                    if value not in (None, "", []):
                        params[name] = value

    st.markdown("#### 3. What happens when it fails?")
    c1, c2 = st.columns(2)
    with c1:
        severity = st.selectbox(
            "Severity", SEVERITES, format_func=libelle_severite,
            index=SEVERITES.index(control["severity"])
            if control.get("severity") in SEVERITES else 2)
        st.caption(SEVERITES_AIDE.get(severity, ""))

        current_threshold = float(control.get("seuil_tolerance_pct") or 0)
        labels = list(TOLERANCES) + ["Custom threshold"]
        default_tol = next((i for i, k in enumerate(TOLERANCES)
                            if TOLERANCES[k] == current_threshold), len(labels) - 1)
        choice = st.selectbox("Tolerance before failing", labels, index=default_tol,
                              help="Share of rows allowed to be off before the "
                                   "control is declared failing.")
        threshold = (st.number_input("Custom threshold (%)", value=current_threshold,
                                     min_value=0.0, max_value=100.0, step=0.5)
                     if choice == "Custom threshold" else TOLERANCES[choice])
    with c2:
        owner = st.text_input("Who has to act?", control.get("owner", "Data Steward"))
        frequency = st.selectbox(
            "How often should this run?", FREQUENCIES,
            index=FREQUENCIES.index(control["frequency"])
            if control.get("frequency") in FREQUENCIES else 3)
    remediation = st.text_area(
        "What should that person do?", height=80,
        value=control.get("remediation_action", ""),
        placeholder="Fix the file at the source and request a fresh extract.")

    st.markdown("#### 4. Name the rule")
    sentence = phrase_controle({"template": tpl["template_id"],
                                "params": json.dumps(params, ensure_ascii=False)},
                               store)
    c3, c4 = st.columns(2)
    with c3:
        name = st.text_input("Rule name", control.get("control_name", ""),
                             placeholder="Notional amount must be present")
    with c4:
        description = st.text_area(
            "Why this rule exists", height=68,
            value=control.get("description", ""),
            placeholder="A trade with no amount cannot be used downstream.")
    reason = st.text_input("Reason for saving (kept in the change log)",
                           placeholder="Requested by the 8 September quality board")

    st.markdown("##### Summary")
    st.markdown(
        f"""<div style="background:#F1F3F4;border-left:4px solid #37474F;
        border-radius:6px;padding:14px 18px;font-size:16px;">{sentence}<br>
        <span style="font-size:13px;color:#5F6368;">
        {libelle_severite(severity)} · tolerance {threshold:g} % ·
        {owner} acts · runs {frequency.lower()}</span></div>""",
        unsafe_allow_html=True)
    with st.expander("Technical detail"):
        st.code(json.dumps({"template": tpl["template_id"], "params": params,
                            "dataset_scope": scope}, ensure_ascii=False, indent=2),
                language="json")

    candidate = {
        "rule_id": control.get("rule_id", store.next_rule_id()),
        "control_name": name.strip(), "control_type": tpl["dimension"],
        "description": description.strip(), "template": tpl["template_id"],
        "params": json.dumps(params, ensure_ascii=False),
        "logic_definition": sentence, "dataset_scope": scope,
        "data_element": ", ".join(str(v) for k, v in params.items()
                                  if k in PARAM_COLUMN | {"role"}),
        "seuil_tolerance_pct": threshold, "severity": severity,
        "frequency": frequency, "owner": owner.strip(),
        "output_type": control.get("output_type", "Exception report"),
        "kpi": tpl.get("kpi_produit", ""), "remediation_action": remediation.strip(),
    }

    missing = []
    if not name.strip():
        missing.append("the rule name")
    if not description.strip():
        missing.append("why the rule exists")
    if not remediation.strip():
        missing.append("what to do when it fails")
    targets = scope_datasets(store, scope)
    if not targets:
        missing.append("at least one file in scope")

    errors = [f"{display_name(store, ds)}: {err}"
              for ds in targets for err in validate_control(candidate, store, ds)]

    if missing:
        st.warning("Still needed: " + ", ".join(missing) + ".")
    if errors:
        st.error("The validator refuses this rule:\n\n"
                 + "\n".join(f"- {e}" for e in errors))
    if not missing and not errors:
        st.success(f"Valid on {len(targets)} file(s): "
                   + ", ".join(display_name(store, d) for d in targets))

    if st.button("Save the rule", type="primary", disabled=bool(missing or errors)):
        if creating:
            created = store.add_control(candidate, user,
                                        reason or "Created from the console")
            commit(store, f"Rule {created['rule_id']} created.")
        else:
            store.update_control(control["rule_id"], candidate, user,
                                 reason or "Edited from the console")
            commit(store, f"Rule {control['rule_id']} updated "
                          f"(version {store.control(control['rule_id'])['version']}).")
        st.session_state.pop("editing", None)
        st.rerun()


def rule_actions(store: CatalogueStore, user: str, rule_id: str) -> None:
    """Actions sit directly under the selected row, not at the bottom of the
    page: selecting a rule and acting on it must be one gesture."""
    ctrl = store.control(rule_id)
    if ctrl is None:
        return
    with st.container(border=True):
        st.markdown(f"### {ctrl['rule_id']} · {ctrl['control_name']}")
        st.markdown(f"{phrase_controle(ctrl, store)}  \n"
                    f"*{ctrl['description'] or 'No rationale recorded.'}*  \n"
                    f"{libelle_severite(ctrl['severity'])} · "
                    f"tolerance {float(ctrl['seuil_tolerance_pct'] or 0):g} % · "
                    f"{ctrl['owner']} acts · version {ctrl['version']} · "
                    f"{libelle_statut(ctrl['statut'])}")

        reason = st.text_input("Reason (kept in the change log)", key="action_reason")
        a1, a2, a3, a4 = st.columns(4)
        if a1.button("✏️ Edit this rule", type="primary", width='stretch'):
            st.session_state["editing"] = rule_id
            st.rerun()
        if a2.button("⏸️ Pause", width='stretch', disabled=ctrl["statut"] == "Suspendu"):
            store.set_statut(rule_id, "Suspendu", user, reason or "Paused")
            commit(store, f"{rule_id} paused — it will no longer run.")
            st.rerun()
        if a3.button("▶️ Put back live", width='stretch',
                     disabled=ctrl["statut"] == "Actif"):
            store.set_statut(rule_id, "Actif", user, reason or "Put back live")
            commit(store, f"{rule_id} is live again.")
            st.rerun()
        if a4.button("🗑️ Delete", width='stretch'):
            st.error("**Deleting is not possible.** Reports already issued must "
                     "stay explainable; removing a rule would make their results "
                     "impossible to read. Use **Pause** — the rule stops running "
                     "and its definition is kept.")


def screen_rules(store: CatalogueStore, user: str) -> None:
    st.header("Control rules")
    show_flash()

    if "editing" in st.session_state:
        if st.button("← Back to the list"):
            st.session_state.pop("editing")
            st.rerun()
        rid = st.session_state["editing"]
        rule_editor(store, user, store.control(rid) if rid else None)
        return

    top_left, top_right = st.columns([1, 3])
    with top_left:
        if st.button("➕ New rule", type="primary", width='stretch'):
            st.session_state["editing"] = None
            st.rerun()
    with top_right:
        st.caption("Select a row to edit or pause a rule.")

    df = pd.DataFrame(store.controls)
    f1, f2, f3 = st.columns([1, 1, 2])
    by_severity = f1.multiselect("Severity", SEVERITES, format_func=libelle_severite)
    by_status = f2.multiselect("Status", STATUTS, default=["Actif"],
                               format_func=libelle_statut)
    search = f3.text_input("Search", placeholder="a word from the name or the rule…")

    view = df.copy()
    if by_severity:
        view = view[view["severity"].isin(by_severity)]
    if by_status:
        view = view[view["statut"].isin(by_status)]
    if search:
        view = view[view.astype(str).apply(
            lambda r: search.lower() in " ".join(r).lower(), axis=1)]
    view = view.reset_index(drop=True)

    st.caption(f"{len(view)} rule(s) shown out of {len(df)} — "
               f"{len(store.active_controls())} live")

    selection = st.dataframe(pd.DataFrame({
        "": view["statut"].map(DOT_STATUS),
        "Rule": view["rule_id"],
        "Name": view["control_name"],
        "What it checks": [phrase_controle(c, store)
                           for c in view.to_dict("records")],
        "Severity": view["severity"].map(libelle_severite),
        "Tolerance": view["seuil_tolerance_pct"].map(
            lambda v: f"{float(v or 0):g} %"),
        "Owner": view["owner"],
        "Status": view["statut"].map(libelle_statut),
        "Version": view["version"],
    }), width='stretch', hide_index=True, on_select="rerun",
        selection_mode="single-row", key="rules_table")

    rows = selection.selection.rows if selection and selection.selection else []
    if rows:
        rule_actions(store, user, view.iloc[rows[0]]["rule_id"])
    else:
        st.info("Click a row above to edit it, pause it, or put it back live.")


# --------------------------------------------------------------------------- #
# Screen 3 — Change log
# --------------------------------------------------------------------------- #
def screen_log(store: CatalogueStore) -> None:
    st.header("Change log")
    st.caption("Who changed what, when, and why. Nothing can be erased.")
    df = pd.DataFrame(store.changelog)
    if df.empty:
        st.info("The log is empty.")
        return
    st.dataframe(pd.DataFrame({
        "When": df["timestamp"], "Who": df["utilisateur"],
        "Action": df["action"], "Rule": df["rule_id"], "Field": df["champ"],
        "Before": df["avant"], "After": df["apres"], "Reason": df["motif"],
    }).iloc[::-1], width='stretch', hide_index=True)


# --------------------------------------------------------------------------- #
def main() -> None:
    store = get_store()
    with st.sidebar:
        st.title("🧭 DQ Compass")
        st.caption("Data quality controls")
        user = st.text_input("Your name", "data.steward",
                             help="Identifies you in the change log.")
        page = st.radio("Go to", ["Check a file", "Control rules", "Change log"])
        st.divider()
        st.metric("Live rules", len(store.active_controls()))
        st.metric("Files described", len(store.datasets))
        if st.button("🔄 Reload the catalogue"):
            get_store(force=True)
            st.rerun()
        st.caption(f"{dt.date.today():%d %b %Y}")

    if page == "Check a file":
        screen_check(store, user)
    elif page == "Control rules":
        screen_rules(store, user)
    else:
        screen_log(store)


main()
