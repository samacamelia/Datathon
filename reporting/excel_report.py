"""
Excel reporting layer: the business deliverable.

Excel is an OUTPUT, not an input. The workbook is self-contained: a reviewer
opens it without any tool and finds the scorecard, the exceptions, the coverage
of the control plan, the evidence needed to replay the run, the exact rule text
that was executed, and the change journal of the catalogue.

    build_workbook(run_result, store, path) -> pathlib.Path
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "engine"))
from store import (CatalogueStore, libelle_severite,  # noqa: E402
                   libelle_statut, phrase_controle)

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "reporting" / "sorties"

DIMENSIONS_ATTENDUES = ["Completeness", "Validity", "Uniqueness",
                        "Consistency", "Timeliness", "Reconciliation"]

VERT, ROUGE, ORANGE, GRIS = "#1E7B34", "#B3261E", "#B26A00", "#5F6368"
VERT_BG, ROUGE_BG, ORANGE_BG, GRIS_BG = "#E6F4EA", "#FCE8E6", "#FEF7E0", "#F1F3F4"


class _Fmt:
    """Workbook formats, created once."""

    def __init__(self, wb):
        self.titre = wb.add_format({"bold": True, "font_size": 16, "font_color": "#202124"})
        self.sous_titre = wb.add_format({"font_size": 10, "font_color": GRIS})
        self.section = wb.add_format({"bold": True, "font_size": 11, "font_color": "#202124",
                                      "bottom": 1, "border_color": "#DADCE0"})
        self.entete = wb.add_format({
            "bold": True, "font_color": "white", "bg_color": "#37474F",
            "border": 1, "border_color": "#CFD8DC", "text_wrap": True, "valign": "vcenter"})
        self.cell = wb.add_format({"border": 1, "border_color": "#E0E0E0", "valign": "top"})
        self.wrap = wb.add_format({"border": 1, "border_color": "#E0E0E0",
                                   "text_wrap": True, "valign": "top"})
        self.num = wb.add_format({"border": 1, "border_color": "#E0E0E0",
                                  "num_format": "#,##0"})
        self.pct = wb.add_format({"border": 1, "border_color": "#E0E0E0",
                                  "num_format": "0.00"})
        self.pass_ = wb.add_format({"bold": True, "font_color": VERT, "bg_color": VERT_BG,
                                    "border": 1, "border_color": "#E0E0E0", "align": "center"})
        self.fail = wb.add_format({"bold": True, "font_color": ROUGE, "bg_color": ROUGE_BG,
                                   "border": 1, "border_color": "#E0E0E0", "align": "center"})
        self.warn = wb.add_format({"bold": True, "font_color": ORANGE, "bg_color": ORANGE_BG,
                                   "border": 1, "border_color": "#E0E0E0", "align": "center"})
        self.neutre = wb.add_format({"font_color": GRIS, "bg_color": GRIS_BG,
                                     "border": 1, "border_color": "#E0E0E0", "align": "center"})
        self.kpi_val = wb.add_format({"bold": True, "font_size": 22, "align": "center",
                                      "valign": "vcenter", "border": 1,
                                      "border_color": "#DADCE0"})
        # Le KPI d'echec est la seule tuile qui declenche une action : elle est
        # plus grande que les autres et change de couleur selon le resultat.
        self.kpi_alerte = wb.add_format({
            "bold": True, "font_size": 34, "align": "center", "valign": "vcenter",
            "font_color": ROUGE, "bg_color": ROUGE_BG, "border": 2,
            "border_color": "#F2B8B5"})
        self.kpi_ok = wb.add_format({
            "bold": True, "font_size": 34, "align": "center", "valign": "vcenter",
            "font_color": VERT, "bg_color": VERT_BG, "border": 2,
            "border_color": "#A8DAB5"})
        self.kpi_lib_alerte = wb.add_format({
            "bold": True, "font_size": 10, "font_color": ROUGE, "bg_color": ROUGE_BG,
            "align": "center", "valign": "vcenter", "border": 2,
            "border_color": "#F2B8B5"})
        self.kpi_lib_ok = wb.add_format({
            "bold": True, "font_size": 10, "font_color": VERT, "bg_color": VERT_BG,
            "align": "center", "valign": "vcenter", "border": 2,
            "border_color": "#A8DAB5"})
        self.kpi_lib = wb.add_format({"font_size": 9, "font_color": GRIS, "align": "center",
                                      "valign": "vcenter", "border": 1,
                                      "border_color": "#DADCE0"})
        self.cle = wb.add_format({"bold": True, "border": 1, "border_color": "#E0E0E0",
                                  "bg_color": "#F8F9FA"})
        self.mono = wb.add_format({"border": 1, "border_color": "#E0E0E0",
                                   "font_name": "Consolas", "font_size": 9})


def _write_table(ws, fmt: _Fmt, df: pd.DataFrame, start_row: int,
                 widths: dict[str, int] | None = None,
                 wrap_cols: set[str] | None = None) -> int:
    """Write a dataframe as a bordered table with an autofilter. Returns next row."""
    widths, wrap_cols = widths or {}, wrap_cols or set()
    if df.empty:
        ws.write(start_row, 0, "Nothing to report", fmt.cell)
        return start_row + 2

    for c, name in enumerate(df.columns):
        ws.write(start_row, c, name, fmt.entete)
        ws.set_column(c, c, widths.get(name, 16))
    ws.set_row(start_row, 30)

    for r, (_, row) in enumerate(df.iterrows(), start=start_row + 1):
        for c, name in enumerate(df.columns):
            value = row[name]
            if name in ("statut", "Status"):
                style = {"PASS": fmt.pass_, "FAIL": fmt.fail, "ERREUR": fmt.warn}.get(
                    str(value), fmt.neutre)
            elif name in wrap_cols:
                style = fmt.wrap
            elif isinstance(value, (int,)) and not isinstance(value, bool):
                style = fmt.num
            elif isinstance(value, float):
                style = fmt.pct
            else:
                style = fmt.cell
            ws.write(r, c, "" if pd.isna(value) else value, style)

    last = start_row + len(df)
    ws.autofilter(start_row, 0, last, len(df.columns) - 1)
    ws.freeze_panes(start_row + 1, 0)
    return last + 3


def _kpi_band(ws, fmt: _Fmt, row: int, tuiles: list[tuple]) -> int:
    """A row of large KPI tiles, two columns wide each.

    A tile may carry its own pair of formats as a third element, so the tile
    that matters most can be louder than the rest.
    """
    for i, tuile in enumerate(tuiles):
        valeur, libelle = tuile[0], tuile[1]
        f_val, f_lib = tuile[2] if len(tuile) > 2 else (fmt.kpi_val, fmt.kpi_lib)
        c = i * 3
        ws.merge_range(row, c, row + 1, c + 1, valeur, f_val)
        ws.merge_range(row + 2, c, row + 2, c + 1, libelle, f_lib)
    ws.set_row(row, 30)
    ws.set_row(row + 1, 24)
    return row + 5


# --------------------------------------------------------------------------- #
# Sheets
# --------------------------------------------------------------------------- #
def _sheet_synthese(wb, fmt: _Fmt, run, sc: pd.DataFrame,
                    store: CatalogueStore) -> None:
    ws = wb.add_worksheet("SUMMARY")
    ws.hide_gridlines(2)
    ws.write(0, 0, "DQ Compass — data quality scorecard", fmt.titre)
    ws.write(1, 0, f"File: {pathlib.Path(run.fichier).name or '-'}  |  "
                   f"Contract applied: {run.contrat}  |  Run {run.run_id}  |  "
                   f"{run.horodatage}", fmt.sous_titre)

    s = run.summary()
    total = max(s["controles"], 1)
    conformite = 100.0 * s["pass"] / total
    echecs = s["fail"] + s["erreur"]
    critiques = int(((sc["statut"] == "FAIL") & (sc["severity"].isin(
        ["Critical", "High"]))).sum()) if not sc.empty else 0

    # Le nombre d'echecs vient en premier et en gros : c'est la seule chose qui
    # appelle une decision. Le taux de conformite ne fait que rassurer.
    alerte = (fmt.kpi_alerte, fmt.kpi_lib_alerte) if echecs else (
        fmt.kpi_ok, fmt.kpi_lib_ok)
    row = _kpi_band(ws, fmt, 3, [
        (str(echecs), "CONTROLS FAILING", alerte),
        (str(critiques), "of them Blocking / Important",
         alerte if critiques else (fmt.kpi_val, fmt.kpi_lib)),
        (f"{s['exceptions']:,}".replace(",", " "), "Rows to look into"),
        (f"{conformite:.0f}%", "Conformity rate"),
        (str(s["controles"]), "Controls run"),
        (str(s["rejets"]), "Rules refused"),
    ])

    ws.write(row, 0, "Control by control", fmt.section)
    table = sc.copy()
    table.insert(2, "ce_qui_est_verifie",
                 [phrase_controle(store.control(r) or {}, store)
                  for r in table["rule_id"]])
    table["gravite"] = table["severity"].map(libelle_severite)
    table = table.sort_values(
        ["statut", "gravite", "rule_id"],
        key=lambda s: s.map({"FAIL": 0, "ERREUR": 1, "NON_APPLICABLE": 2, "PASS": 3,
                             "Blocking": 0, "Important": 1, "Moderate": 2,
                             "Minor": 3}).fillna(9)
        if s.name in ("statut", "gravite") else s)
    entetes = {
        "rule_id": "Rule", "control_name": "Name",
        "ce_qui_est_verifie": "What it checks", "statut": "Status",
        "gravite": "Severity", "lignes_ko": "Rows off",
        "lignes_testees": "Rows tested", "taux_ko_pct": "Rows off %",
        "kpi_nom": "Indicator", "kpi_valeur": "Value", "seuil_pct": "Tolerance %",
        "dimension": "Dimension", "cible": "Target", "owner": "Owner",
        "frequency": "Frequency", "version": "Version",
        "remediation_action": "What to do",
    }
    table = table[[c for c in entetes if c in table.columns]].rename(columns=entetes)
    _write_table(ws, fmt, table, row + 1,
                 widths={"Name": 38, "What it checks": 62, "Target": 26,
                         "Indicator": 22, "What to do": 55, "Owner": 22},
                 wrap_cols={"What to do", "Name", "What it checks"})


def _sheet_exceptions(wb, fmt: _Fmt, run) -> None:
    ws = wb.add_worksheet("EXCEPTIONS")
    ws.hide_gridlines(2)
    ws.write(0, 0, "Exception report", fmt.titre)
    ws.write(1, 0, f"{len(run.exceptions):,} rows in exception. Filter by rule or severity "
                   f"to work through a batch.".replace(",", " "), fmt.sous_titre)
    exc = run.exceptions.copy()
    if not exc.empty and "index_source" in exc.columns:
        exc = exc.drop(columns=["index_source"])
    exc = exc.rename(columns={
        "rule_id": "Rule", "dataset": "File", "severity": "Severity",
        "identifiant_ligne": "Row identifier", "colonne": "Column",
        "valeur": "Value", "motif": "Reason"})
    _write_table(ws, fmt, exc.head(50000), 3,
                 widths={"Row identifier": 44, "Reason": 52, "Column": 24,
                         "Value": 30, "File": 20},
                 wrap_cols={"Reason"})


def _sheet_couverture(wb, fmt: _Fmt, run, sc: pd.DataFrame, store: CatalogueStore) -> None:
    ws = wb.add_worksheet("COVERAGE")
    ws.hide_gridlines(2)
    ws.write(0, 0, "Control plan coverage", fmt.titre)
    ws.write(1, 0, "What the framework covers, and what it does not cover yet.",
             fmt.sous_titre)

    row = 3
    ws.write(row, 0, "Dimensions x files (number of controls run)", fmt.section)
    row += 1
    if sc.empty:
        pivot = pd.DataFrame()
    else:
        pivot = sc.pivot_table(index="dimension", columns="dataset", values="rule_id",
                               aggfunc="count", fill_value=0)
        for dim in DIMENSIONS_ATTENDUES:
            if dim not in pivot.index:
                pivot.loc[dim] = 0
        pivot = pivot.loc[[d for d in DIMENSIONS_ATTENDUES if d in pivot.index]
                          + [d for d in pivot.index if d not in DIMENSIONS_ATTENDUES]]
        pivot["TOTAL"] = pivot.sum(axis=1)
        pivot = pivot.reset_index()
    row = _write_table(ws, fmt, pivot, row, widths={"dimension": 22})

    ws.write(row, 0, "Coverage gaps", fmt.section)
    row += 1
    trous = []
    couvertes = set(sc["dimension"]) if not sc.empty else set()
    for dim in DIMENSIONS_ATTENDUES:
        if dim not in couvertes:
            trous.append({"Item": dim, "Kind": "Dimension",
                          "Finding": "No live control ran on this dimension"})
    for name in store.datasets:
        if sc.empty or name not in set(sc["dataset"]):
            trous.append({"Item": name, "Kind": "File",
                          "Finding": "Described in the catalogue but not checked in this run"})
    for c in store.controls:
        if c.get("statut") != "Actif":
            trous.append({"Item": c["rule_id"], "Kind": f"Rule {libelle_statut(c['statut'])}",
                          "Finding": f"{c['control_name']} — did not run"})
    row = _write_table(ws, fmt, pd.DataFrame(trous), row,
                       widths={"Item": 26, "Kind": 22, "Finding": 62},
                       wrap_cols={"Finding"})

    ws.write(row, 0, "Breakdown by severity", fmt.section)
    row += 1
    if not sc.empty:
        sev = (sc.groupby(["severity", "statut"]).size().unstack(fill_value=0)
               .reindex(["Critical", "High", "Medium", "Low"]).dropna(how="all")
               .fillna(0).astype(int).reset_index())
    else:
        sev = pd.DataFrame()
    _write_table(ws, fmt, sev, row, widths={"severity": 18})


def _sheet_evidence(wb, fmt: _Fmt, run) -> None:
    ws = wb.add_worksheet("EVIDENCE")
    ws.hide_gridlines(2)
    ws.write(0, 0, "Proof of execution", fmt.titre)
    ws.write(1, 0, "Everything needed to replay this run exactly.",
             fmt.sous_titre)
    ws.set_column(0, 0, 30)
    ws.set_column(1, 1, 78)

    m = run.manifeste
    row = 3
    ws.write(row, 0, "Run identification", fmt.section)
    row += 1
    lignes = [
        ("Run ID", m["run_id"]),
        ("Label", m.get("libelle", "")),
        ("Timestamp", m["horodatage"]),
        ("As-of date", m["as_of"]),
        ("Engine version", m["moteur_version"]),
        ("Catalogue SHA-256", m["catalogue_sha256"]),
        ("Live controls in the catalogue", m["controles_actifs"]),
        ("Total duration (s)", m["duree_totale_s"]),
        ("Python / pandas", f"{m['python']} / {m['pandas']}"),
        ("Host", m["machine"]),
    ]
    for cle, valeur in lignes:
        ws.write(row, 0, cle, fmt.cle)
        ws.write(row, 1, str(valeur), fmt.mono if "SHA" in cle else fmt.cell)
        row += 1

    row += 2
    ws.write(row, 0, "Data source fingerprints", fmt.section)
    row += 1
    sources = pd.DataFrame([
        {"File": k, "Path": v["chemin"], "Rows": v["lignes"],
         "Columns": v["colonnes"], "SHA-256": v["sha256"], "Modified": v["modifie_le"]}
        for k, v in m["sources"].items()])
    row = _write_table(ws, fmt, sources, row,
                       widths={"File": 22, "Path": 40, "SHA-256": 68, "Modified": 22})

    ws.write(row, 0, "Rules refused at validation", fmt.section)
    row += 1
    rejets = pd.DataFrame(run.rejets).rename(columns={
        "rule_id": "Rule", "dataset": "File", "control_name": "Name",
        "motif": "Why it was refused"})
    _write_table(ws, fmt, rejets, row,
                 widths={"Why it was refused": 70, "Name": 34},
                 wrap_cols={"Why it was refused"})


def _sheet_catalogue(wb, fmt: _Fmt, store: CatalogueStore) -> None:
    ws = wb.add_worksheet("RULES_APPLIED")
    ws.hide_gridlines(2)
    ws.write(0, 0, "Control catalogue — version executed", fmt.titre)
    ws.write(1, 0, "Frozen copy of the rules as they ran. This is not a link to the "
                   "live catalogue.", fmt.sous_titre)
    df = pd.DataFrame(store.controls)
    _write_table(ws, fmt, df, 3,
                 widths={"control_name": 36, "description": 55, "params": 60,
                         "logic_definition": 42, "remediation_action": 55,
                         "dataset_scope": 26, "data_element": 24, "owner": 22},
                 wrap_cols={"description", "params", "remediation_action",
                            "logic_definition"})


def _sheet_journal(wb, fmt: _Fmt, store: CatalogueStore) -> None:
    ws = wb.add_worksheet("CHANGE_LOG")
    ws.hide_gridlines(2)
    ws.write(0, 0, "Catalogue change log", fmt.titre)
    ws.write(1, 0, "Who changed what, when, and why. Nothing can be deleted: a rule that "
                   "is withdrawn moves to Paused or Retired.",
             fmt.sous_titre)
    df = pd.DataFrame(store.changelog)
    if not df.empty:
        df = df.iloc[::-1].reset_index(drop=True)
    _write_table(ws, fmt, df, 3,
                 widths={"timestamp": 20, "utilisateur": 16, "action": 15,
                         "champ": 20, "avant": 40, "apres": 40, "motif": 60},
                 wrap_cols={"avant", "apres", "motif"})


# --------------------------------------------------------------------------- #
def build_workbook(run, store: CatalogueStore,
                   path: pathlib.Path | str | None = None) -> pathlib.Path:
    if path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / f"DQ_Rapport_{run.run_id}.xlsx"
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    sc = run.scorecard
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        wb = writer.book
        wb.set_properties({
            "title": f"DQ Compass - rapport {run.run_id}",
            "subject": "Controle qualite des donnees",
            "comments": json.dumps(run.summary(), ensure_ascii=False),
            "created": dt.datetime.now(),
        })
        fmt = _Fmt(wb)
        _sheet_synthese(wb, fmt, run, sc, store)
        _sheet_exceptions(wb, fmt, run)
        _sheet_couverture(wb, fmt, run, sc, store)
        _sheet_evidence(wb, fmt, run)
        _sheet_catalogue(wb, fmt, store)
        _sheet_journal(wb, fmt, store)
    return path


def main() -> int:
    sys.path.insert(0, str(ROOT / "engine"))
    from dq_engine import run_dq  # noqa: PLC0415

    store = CatalogueStore()
    fichier = sys.argv[1] if len(sys.argv) > 1 else "data/prepared/bis_turnover.csv"
    contrat = sys.argv[2] if len(sys.argv) > 2 else None
    run = run_dq(fichier, dataset=contrat, store=store, run_label="Rapport Excel")
    out = build_workbook(run, store)
    print(f"Classeur ecrit : {out}")
    print(f"Synthese       : {run.summary()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
