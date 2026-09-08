"""
Profile an unknown file and propose a dataset contract for it.

The point of the tool is that someone drops a file nobody has described yet.
Asking that person to hand-write a column contract would defeat it. So the
engine reads the data, guesses a structure, and hands back a proposal the user
only has to correct.

Every guess is deliberately conservative: it is better to propose "string /
label" and let the user promote a column than to silently declare a primary
key that is not one.

    propose_contract(df) -> list[dict]   # one entry per column
"""
from __future__ import annotations

import re

import pandas as pd

# A name that leaves no doubt: the column is an identifier whatever its values
# look like. On a small file one duplicate is enough to push the distinct ratio
# under any threshold, and downgrading the column would hide the very defect
# the controls exist to report.
NOM_IDENTIFIANT_STRICT = re.compile(
    r"(^|_)(id|identifiant|identifier|uuid|guid|siret|siren|isin|ean|sku)($|_)",
    re.IGNORECASE)

# A weaker hint -- "code", "ref", "num" also name plain categories -- so here
# the data has to back the name up.
NOM_IDENTIFIANT = re.compile(
    r"(^|_)(ids|key|code|ref|reference|num|numero|number)($|_)", re.IGNORECASE)
NOM_DATE = re.compile(r"(date|jour|day|time|horodat|timestamp|_dt$|^dt_)",
                      re.IGNORECASE)
NOM_LIBELLE = re.compile(
    r"(libell|label|nom|name|description|commentaire|comment|intitul|titre|title)",
    re.IGNORECASE)

# Above this share of distinct values, a text column is free text rather than
# a closed list of codes. On a small file the ratio is meaningless -- three
# distinct currencies out of six rows is 50% -- so a low absolute count also
# qualifies.
SEUIL_CARDINALITE_CODE = 0.30
MAX_VALEURS_CODE = 60
CODE_SI_MOINS_DE = 15

# A column named like an identifier is proposed as one even when its values
# are dirty. Refusing the role because of duplicates would hide exactly the
# defect the controls exist to find.
SEUIL_QUASI_UNIQUE = 0.85

# A reference table is narrow. A wide business file is not something other
# files point at, so it is never proposed as a foreign key target.
MAX_COLONNES_REFERENTIEL = 6
COUVERTURE_FK_MINIMALE = 0.5


def _est_date(serie: pd.Series) -> bool:
    """True when the column parses as dates, checked on a sample."""
    if pd.api.types.is_datetime64_any_dtype(serie):
        return True
    echantillon = serie.dropna().astype(str).head(200)
    if echantillon.empty:
        return False
    # A bare integer year would parse as a date; that is a number, not a date.
    if echantillon.str.fullmatch(r"\d{1,4}").all():
        return False
    converti = pd.to_datetime(echantillon, errors="coerce", format="mixed")
    return converti.notna().mean() >= 0.9


def _type_colonne(serie: pd.Series, nom: str) -> str:
    if pd.api.types.is_bool_dtype(serie):
        return "string"
    if pd.api.types.is_integer_dtype(serie):
        return "integer"
    if pd.api.types.is_float_dtype(serie):
        # A float column holding only whole numbers is an integer that pandas
        # widened because of missing values.
        valeurs = serie.dropna()
        if not valeurs.empty and (valeurs % 1 == 0).all():
            return "integer"
        return "decimal"
    if _est_date(serie) or NOM_DATE.search(nom):
        return "date" if _est_date(serie) else "string"
    return "string"


def _role_colonne(serie: pd.Series, nom: str, type_col: str,
                  quasi_unique: bool, taux_distinct: float) -> str:
    if type_col == "date":
        return "technical_date" if re.search(r"(maj|update|modif|charg|load|techn)",
                                             nom, re.IGNORECASE) else "event_date"
    identifiant = (NOM_IDENTIFIANT_STRICT.search(nom)
                   or (quasi_unique and NOM_IDENTIFIANT.search(nom)))
    if type_col in ("integer", "decimal"):
        # A numeric column named like a key is an id, not a measure: summing
        # invoice numbers means nothing.
        return "identifier" if identifiant else "measure"
    if identifiant:
        return "identifier"
    if NOM_LIBELLE.search(nom):
        return "label"
    distinct = serie.nunique()
    if distinct <= MAX_VALEURS_CODE and (taux_distinct <= SEUIL_CARDINALITE_CODE
                                         or distinct <= CODE_SI_MOINS_DE):
        return "code"
    return "label"


def profile_column(serie: pd.Series, nom: str) -> dict:
    total = len(serie)
    non_nuls = int(serie.notna().sum())
    distinct = int(serie.nunique(dropna=True))
    taux_distinct = distinct / non_nuls if non_nuls else 0.0
    complet = non_nuls == total
    unique = non_nuls > 0 and distinct == non_nuls

    quasi_unique = non_nuls > 0 and taux_distinct >= SEUIL_QUASI_UNIQUE
    type_col = _type_colonne(serie, nom)
    role = _role_colonne(serie, nom, type_col, quasi_unique, taux_distinct)

    # An identifier that is not clean is the interesting case: say so, so the
    # user can mark it as the key and let the controls report the defect,
    # instead of the profiler silently downgrading the column.
    alerte = ""
    if role == "identifier" and not (unique and complet):
        details = []
        if not complet:
            details.append(f"{total - non_nuls} empty value(s)")
        if not unique:
            details.append(f"{non_nuls - distinct} duplicate(s)")
        alerte = ("Looks like an identifier but contains "
                  + " and ".join(details)
                  + ". Mark it as the key so the controls report it.")

    exemples = serie.dropna().astype(str).unique()[:3]
    return {
        "colonne": nom,
        "type": type_col,
        "role": role,
        # A primary key must be both unique and complete. Anything else is a
        # candidate the user may promote, never an automatic decision.
        "cle_primaire": "OUI" if (unique and complet and role == "identifier") else "NON",
        "obligatoire": "OUI" if complet else "NON",
        "description": "",
        "fk_dataset": "",
        "fk_colonne": "",
        "_lignes": total,
        "_taux_remplissage": round(100.0 * non_nuls / total, 2) if total else 0.0,
        "_valeurs_distinctes": distinct,
        "_exemples": ", ".join(exemples),
        "_alerte": alerte,
    }


def propose_contract(df: pd.DataFrame) -> list[dict]:
    """Propose one contract entry per column of the file."""
    return [profile_column(df[c], str(c)) for c in df.columns]


def suggest_foreign_keys(df: pd.DataFrame, store, load) -> list[dict]:
    """Suggest reference tables this file's columns could be attached to.

    A candidate is kept only when the values actually land in the target, so a
    column that merely shares a name is not proposed. Wide business files are
    excluded outright: a reference table is narrow.
    """
    cibles: dict[str, tuple[str, str]] = {}
    for nom_ds, definition in store.datasets.items():
        colonnes = definition.get("colonnes", [])
        if len(colonnes) > MAX_COLONNES_REFERENTIEL:
            continue
        for col in colonnes:
            if str(col.get("cle_primaire", "")).upper() == "OUI":
                cibles.setdefault(col["colonne"], (nom_ds, col["colonne"]))

    suggestions = []
    for nom in df.columns:
        cible = cibles.get(str(nom))
        if cible is None:
            continue
        nom_ds, col_ref = cible
        try:
            reference = load(nom_ds)
        except Exception:  # noqa: BLE001 - une suggestion ne doit jamais bloquer
            continue
        valides = set(reference[col_ref].dropna().astype(str))
        presentes = df[nom].dropna().astype(str)
        if presentes.empty:
            continue
        couverture = presentes.isin(valides).mean()
        if couverture >= COUVERTURE_FK_MINIMALE:
            suggestions.append({"colonne": str(nom), "fk_dataset": nom_ds,
                                "fk_colonne": col_ref,
                                "couverture": round(100.0 * couverture, 1)})
    return suggestions


def clean_contract(colonnes: list[dict]) -> list[dict]:
    """Drop the profiling-only fields before the contract is stored."""
    champs = ["colonne", "type", "role", "cle_primaire", "obligatoire",
              "description", "fk_dataset", "fk_colonne"]
    return [{k: str(c.get(k, "") or "") for k in champs} for c in colonnes]
