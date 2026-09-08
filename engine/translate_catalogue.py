"""
Translate the catalogue to English.

The brief, the kickoff deck and the jury are English-speaking, so the product
speaks English: business labels, control names, remediation actions, dataset
contracts and column roles. Everything goes through the store, so the change
is journalled like any other.

Column roles are catalogue *data*, not code: a rule targets `{"role":
"identifier"}`. Renaming them means rewriting the controls that use them,
which is done here in the same pass.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from store import CatalogueStore  # noqa: E402

USER = "data.steward"
MOTIF = ("Product language set to English: brief, kickoff deck and jury are "
         "English-speaking. Business labels, control names, remediation "
         "actions and column roles translated in one pass.")

ROLES = {
    "identifiant": "identifier",
    "mesure": "measure",
    "libelle": "label",
    "date_evenement": "event_date",
    "date_technique": "technical_date",
    "contact": "contact",
    "code": "code",
    "cle_primaire": "primary_key",
}

FREQUENCES = {
    "Quotidienne": "Daily", "Hebdomadaire": "Weekly", "Mensuelle": "Monthly",
    "Trimestrielle": "Quarterly", "Annuelle": "Annual", "A la demande": "On demand",
}

TEMPLATES = {
    "NOT_NULL": {
        "libelle_metier": "Must never be empty",
        "question_metier": "Which information must never be missing?",
        "explication": "The control fails when rows carry no value in that column.",
        "exemple_metier": "Every trade must carry an amount.",
        "phrase": "Column “{column}” must be filled in on every row.",
        "phrase_role": "Every “{role}” field must be filled in.",
        "params_libelles": {"column": "Column that must always be filled",
                            "role": "Type of information concerned"},
    },
    "UNIQUE_KEY": {
        "libelle_metier": "Must contain no duplicate",
        "question_metier": "What must be unique in the file?",
        "explication": "The control fails when two rows carry the same value.",
        "exemple_metier": "The same invoice number cannot appear twice.",
        "phrase": "No two rows may share the same “{columns}”.",
        "phrase_role": "“{role}” values must be unique.",
        "params_libelles": {"columns": "Column(s) that identify a row uniquely",
                            "role": "Type of identifier concerned"},
    },
    "IN_DOMAIN": {
        "libelle_metier": "Must belong to an allowed list",
        "question_metier": "Which values are the only ones accepted?",
        "explication": "The control fails as soon as a value falls outside the list.",
        "exemple_metier": "A contract type can only be Permanent, Fixed-term or Intern.",
        "phrase": "Column “{column}” may only contain: {values}.",
        "params_libelles": {"column": "Column to check",
                            "values": "List of allowed values"},
    },
    "RANGE": {
        "libelle_metier": "Must stay within numeric bounds",
        "question_metier": "Between which values must this number stay?",
        "explication": "The control fails when a number falls outside the range. "
                       "Empty cells are ignored.",
        "exemple_metier": "An amount cannot be negative.",
        "phrase": "Column “{column}” must stay between {min} and {max}.",
        "phrase_min": "Column “{column}” must be greater than or equal to {min}.",
        "phrase_max": "Column “{column}” must be less than or equal to {max}.",
        "params_libelles": {"column": "Numeric column to check",
                            "min": "Lowest accepted value",
                            "max": "Highest accepted value"},
    },
    "MATCHES_REGEX": {
        "libelle_metier": "Must follow a precise format",
        "question_metier": "Which format must this information follow?",
        "explication": "The control fails when a value does not match the "
                       "expected format.",
        "exemple_metier": "A currency code is exactly three capital letters, "
                          "such as EUR or USD.",
        "phrase": "Column “{column}” must match the format {pattern}.",
        "params_libelles": {"column": "Column to check",
                            "pattern": "Expected format (regular expression)"},
    },
    "FOREIGN_KEY": {
        "libelle_metier": "Must exist in a reference table",
        "question_metier": "Which code must a reference table recognise?",
        "explication": "The control fails when a code in the file cannot be found "
                       "in the reference table.",
        "exemple_metier": "Every currency quoted must appear in the currency "
                          "reference table.",
        "phrase": "Every “{column}” must exist in reference table “{ref_dataset}”.",
        "params_libelles": {"column": "Column to attach",
                            "ref_dataset": "Reference table to attach it to",
                            "ref_column": "Column of the reference table holding "
                                          "the code"},
    },
    "FRESHNESS": {
        "libelle_metier": "Must be recent enough",
        "question_metier": "How old may the data be?",
        "explication": "The control fails when the most recent record is too old.",
        "exemple_metier": "A file refreshed monthly must not be older than 45 days.",
        "phrase": "The most recent “{column}” must be less than "
                  "{max_lag_days} days old.",
        "params_libelles": {"column": "Date column to watch",
                            "max_lag_days": "Maximum age tolerated, in days"},
    },
    "DATE_ORDER": {
        "libelle_metier": "Must respect chronological order",
        "question_metier": "Which date must come before the other?",
        "explication": "The control fails when the two dates are the wrong way round.",
        "exemple_metier": "A start date always precedes an end date.",
        "phrase": "“{before}” must be on or before “{after}”.",
        "params_libelles": {"before": "Date that must come first",
                            "after": "Date that must come second"},
    },
    "FIELD_EQUALS": {
        "libelle_metier": "Must match another column",
        "question_metier": "Which two columns must carry the same value?",
        "explication": "The control fails when the two columns diverge.",
        "exemple_metier": "The total shown at the foot of the file must equal "
                          "the computed total.",
        "phrase": "“{field_a}” and “{field_b}” must carry the same value.",
        "params_libelles": {"field_a": "First column", "field_b": "Second column"},
    },
    "SUM_RECONCILIATION": {
        "libelle_metier": "Must add up consistently",
        "question_metier": "Which total must match the sum of its parts?",
        "explication": "The control compares a total row against the sum of its "
                       "components and reports the gaps.",
        "exemple_metier": "Revenue for “all regions” must equal the sum of the "
                          "regions.",
        "phrase": "Total “{total_value}” of “{total_column}” must match the sum "
                  "of “{amount}”.",
        "phrase_parties_max": "The sum of “{amount}” must never exceed total "
                              "“{total_value}”.",
        "phrase_couverture_min": "The breakdown of “{amount}” must cover at least "
                                 "{couverture_min_pct} % of total “{total_value}”.",
        "params_libelles": {"amount": "Amount column to add up",
                            "total_column": "Column carrying the total row",
                            "total_value": "Value that marks the total",
                            "group_by": "Dimensions to hold fixed when comparing",
                            "sens": "What counts as an unacceptable gap",
                            "tolerance_pct": "Gap tolerated, in %",
                            "couverture_min_pct": "Minimum coverage required, in %"},
    },
    "COUNT_RECONCILIATION": {
        "libelle_metier": "Must have the right number of rows",
        "question_metier": "Which file must the row count match?",
        "explication": "The control fails when the two files hold different "
                       "numbers of rows.",
        "exemple_metier": "After a transfer, the file received must hold as many "
                          "rows as the file sent.",
        "phrase": "The number of rows must match that of “{ref_dataset}”.",
        "params_libelles": {"ref_dataset": "Reference file",
                            "group_by": "Compare by subset (optional)"},
    },
    "CUSTOM_EXPRESSION": {
        "libelle_metier": "Custom rule",
        "question_metier": "Which condition must hold on every row?",
        "explication": "For technical users only: the condition is written in "
                       "pandas syntax and evaluated row by row.",
        "exemple_metier": "buy_currency != sell_currency",
        "phrase": "Every row must satisfy: {expression}.",
        "params_libelles": {"expression": "Condition to check",
                            "description_metier": "Plain-English reading of the "
                                                  "condition"},
    },
}

CONTROLS = {
    "DQ01": ("Notional amount must be present",
             "Every published observation must carry an amount.",
             "Reject the publication and request a fresh extract from the BIS source."),
    "DQ02": ("Identifiers must be present (cross-file)",
             "Every identifier declared in a file contract must be filled in.",
             "Block the load; the identifier is rebuilt during preparation."),
    "DQ03": ("Notional amount must not be negative",
             "A notional turnover cannot be negative.",
             "Escalate to the Market Data Office; check the sign at the source."),
    "DQ04": ("Reporting basis must be a known code",
             "The basis must be A (gross), B (net) or C (net-net).",
             "Fix the code mapping at ingestion."),
    "DQ05": ("Currency code format",
             "A currency code is three capital letters, or TO1 for the "
             "“all currencies” aggregate.",
             "Normalise the code, or add it to the reference table once arbitrated."),
    "DQ06": ("Survey year within published range",
             "The year must fall inside the period the survey covers.",
             "Extend the upper bound with each new survey wave."),
    "DQ07": ("Primary keys must be unique (cross-file)",
             "No declared primary key may appear twice.",
             "De-duplicate during preparation and log the row that was dropped."),
    "DQ08": ("Referential integrity — currency leg 1",
             "Every currency quoted must exist in the currency reference table.",
             "Data Steward arbitration: enrich the reference table or reject the row."),
    "DQ09": ("Referential integrity — currency leg 2",
             "Every currency quoted must exist in the currency reference table.",
             "Data Steward arbitration: enrich the reference table or reject the row."),
    "DQ10": ("Referential integrity — reporting country",
             "Every reporting country must exist in the country reference table.",
             "Data Steward arbitration: enrich the reference table or reject the row."),
    "DQ11": ("FX legs must differ",
             "An FX trade cannot carry the same currency on both legs.",
             "Check the pair at the source; reclassify as a total if it is an "
             "aggregate."),
    "DQ12": ("Triennial survey freshness",
             "The most recent observation must be less than four years old.",
             "Trigger the load of the next survey wave."),
    "DQ13": ("Country breakdown must not exceed the total",
             "The sum of reporting countries can never exceed the “all zones” "
             "total. Exceeding it signals double counting or an aggregation error.",
             "Blocking: investigate double counting with the Market Data Office "
             "before publication."),
    "DQ14": ("Currency reference must carry a label",
             "Every currency code carries a usable label.",
             "Fill the label from the ISO 4217 source."),
    "DQ15": ("Former 12-month freshness threshold",
             "Annual threshold abandoned: the BIS survey is triennial.",
             "Not applicable — control deprecated on 2026-09-07."),
    "DQ16": ("Country breakdown coverage",
             "The published country breakdown must cover at least 95 % of the "
             "world total. Below that, geographic analysis is not usable.",
             "Document the unpublished jurisdictions in the methodological note "
             "accompanying the release."),
}

DATASETS = {
    "bis_turnover": "BIS Triennial Survey — OTC derivatives turnover (long format)",
    "ref_devises": "Currency reference table",
    "ref_pays": "Reporting and counterparty country reference table",
}

COLONNES = {
    "observation_id": "Composite key of the 14 dimensions plus the year",
    "FREQ": "Series frequency", "DER_TYPE": "Measure type",
    "DER_INSTR": "Instrument", "DER_RISK": "Risk category",
    "DER_REP_CTY": "Reporting country", "DER_SECTOR_CPY": "Counterparty sector",
    "DER_CPC": "Counterparty country", "DER_SECTOR_UDL": "Underlying risk sector",
    "DER_CURR_LEG1": "Currency, leg 1", "DER_CURR_LEG2": "Currency, leg 2",
    "DER_ISSUE_MAT": "Maturity", "DER_RATING": "Rating or settlement",
    "DER_EX_METHOD": "Execution method", "DER_BASIS": "Gross or net basis",
    "Instrument": "Instrument label", "Risk category": "Risk category label",
    "Reporting country": "Reporting country label",
    "Counterparty sector": "Counterparty sector label",
    "Currency leg 1": "Currency label, leg 1",
    "Currency leg 2": "Currency label, leg 2",
    "Execution method": "Execution method label", "Basis": "Basis label",
    "annee": "Year of the triennial survey",
    "date_observation": "End of the observed period",
    "turnover_notionnel": "Notional amount, daily average, USD millions",
    "code_devise": "ISO 4217 currency code, or BIS aggregate",
    "libelle_devise": "Currency name", "type": "REAL or AGGREGATE",
    "code_pays": "BIS country code, or zone aggregate", "libelle_pays": "Country name",
}


def main() -> None:
    st = CatalogueStore()

    for tpl in st.templates:
        traduction = TEMPLATES.get(tpl["template_id"])
        if traduction:
            tpl.update(traduction)
            for cle in ("params_requis", "params_optionnels"):
                tpl[cle] = tpl.get(cle, "")

    # Column roles live in the contracts and in the rules that target them.
    for definition in st.datasets.values():
        for col in definition.get("colonnes", []):
            col["role"] = ROLES.get(col.get("role", ""), col.get("role", ""))
            if col["colonne"] in COLONNES:
                col["description"] = COLONNES[col["colonne"]]
    for nom, libelle in DATASETS.items():
        if st.dataset(nom):
            st.dataset(nom)["libelle"] = libelle

    for control in st.controls:
        changements: dict = {}
        traduction = CONTROLS.get(control["rule_id"])
        if traduction:
            changements.update({"control_name": traduction[0],
                                "description": traduction[1],
                                "remediation_action": traduction[2]})
        if control.get("frequency") in FREQUENCES:
            changements["frequency"] = FREQUENCES[control["frequency"]]

        params = json.loads(control.get("params") or "{}")
        if "role" in params and params["role"] in ROLES:
            params["role"] = ROLES[params["role"]]
            changements["params"] = json.dumps(params, ensure_ascii=False)
        if changements:
            st.update_control(control["rule_id"], changements, USER, MOTIF)

    # The rendered sentence is stored on each control as its readable logic.
    from store import phrase_controle  # noqa: PLC0415
    for control in st.controls:
        control["logic_definition"] = phrase_controle(control, st)

    st._journal("TRADUCTION", "*", "langue", "fr", "en", USER, MOTIF)
    st.save()

    roles = sorted({c["role"] for d in st.datasets.values()
                    for c in d.get("colonnes", [])})
    print(f"Catalogue traduit. Roles en vigueur : {', '.join(roles)}")
    print(f"{len(st.controls)} controles, {len(st.changelog)} entrees de journal.")
    for c in st.controls:
        print(f"  {c['rule_id']:<6} {c['control_name']}")


if __name__ == "__main__":
    main()
