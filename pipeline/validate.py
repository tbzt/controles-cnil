"""Étape 6 : contrôles de qualité sur les données produites.

Lit `data/processed/` et `data/metadata/`, applique une liste de règles et
écrit `data/metadata/quality-report.json`. Deux niveaux :

- **fatal** : le script se termine avec le code 1 ; dans GitHub Actions rien
  n'est commité et le site continue de servir la version précédente ;
- **alerte** : consigné dans le rapport, visible sur la page Données, mais la
  publication continue.

Le rapport ne contient aucun horodatage : deux exécutions sur les mêmes
données produisent le même fichier. Les règles sont des fonctions courtes,
une par sujet, listées dans `REGLES` ; en ajouter une revient à écrire une
fonction qui renvoie ses constats.

Usage :
    python3 pipeline/validate.py
"""

from __future__ import annotations

import csv
import datetime as dt
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import transform  # noqa: E402
from pipeline.commun import GEOCODING, METADATA, PROCESSED, RACINE, RAW, ecrire_json, journal, lire_json  # noqa: E402

RAPPORT = METADATA / "quality-report.json"
ID_VALIDE = re.compile(r"^20\d\d-[0-9a-f]{8}-\d+$")
FONDEMENTS = {"loi78", "rgpd", "directive_police_justice", "rgpd_ou_directive", "videoprotection"}
MODALITES = {"sur_place", "en_ligne", "sur_pieces", "sur_audition", "non_renseignee"}
PRECISIONS = {"adresse", "commune", "departement", "pays", "institution", "aucune"}
SEUIL_CHAMPS_OBLIGATOIRES = 0.99
SEUIL_GEOCODAGE_FRANCE = 0.95
ECART_TOTAL_OFFICIEL = 0.05
VOLUME_MIN, VOLUME_MAX = 100, 1000

# Emprises (lon_min, lat_min, lon_max, lat_max) : métropole avec la Corse, puis outre-mer par département.
EMPRISES = {
    "metropole": (-5.5, 41.0, 10.0, 51.5),
    "971": (-62.0, 15.8, -60.9, 16.6), "972": (-61.3, 14.3, -60.7, 15.0), "973": (-55.0, 2.0, -51.5, 6.0),
    "974": (55.1, -21.5, 56.0, -20.8), "976": (44.9, -13.1, 45.4, -12.6),
}


# ------------------------------------------------------------ outils ---

class Constat:
    def __init__(self, regle: str, niveau: str, message: str, mesure=None):
        self.regle, self.niveau, self.message, self.mesure = regle, niveau, message, mesure

    def dict(self):
        d = {"regle": self.regle, "niveau": self.niveau, "message": self.message}
        if self.mesure is not None:
            d["mesure"] = self.mesure
        return d


def ok(regle, message, mesure=None):
    return Constat(regle, "ok", message, mesure)


def alerte(regle, message, mesure=None):
    return Constat(regle, "alerte", message, mesure)


def fatal(regle, message, mesure=None):
    return Constat(regle, "fatal", message, mesure)


def lire_csv(chemin: Path) -> list[dict]:
    if not chemin.exists():
        return []
    with open(chemin, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def dans(emprise, lon, lat) -> bool:
    return emprise[0] <= lon <= emprise[2] and emprise[1] <= lat <= emprise[3]


def totaux_officiels(chemin: Path | None) -> dict[int, int]:
    """Lit le tableau CNIL « nombre de contrôles depuis 1990 » : ligne
    « Contrôles réalisés », une colonne par année (la première occurrence
    d'une année dupliquée est retenue)."""
    if not chemin or not chemin.exists():
        return {}
    octets = chemin.read_bytes()
    texte = octets.decode("utf-8-sig") if octets[:3] == b"\xef\xbb\xbf" else octets.decode("utf-8", errors="replace")
    lignes = list(csv.reader(texte.splitlines(), delimiter=";"))
    if not lignes:
        return {}
    annees = [c.strip() for c in lignes[0]]
    totaux = {}
    for ligne in lignes[1:]:
        if ligne and ligne[0].strip().lower().startswith("contrôles réalisés"):
            for annee, valeur in zip(annees[1:], ligne[1:]):
                if annee.isdigit() and valeur.strip().isdigit() and int(annee) not in totaux:
                    totaux[int(annee)] = int(valeur)
    return totaux


# ------------------------------------------------------------- règles ---

def regle_structure_source(ctx) -> list[Constat]:
    """Chaque fichier brut courant se lit avec les en-têtes connus."""
    constats = []
    tables = ctx["tables_transform"]
    for annee, chemin in ctx["fichiers_courants"]:
        if not chemin.exists():
            constats.append(fatal("structure_source", f"{chemin.name} absent de data/raw/"))
            continue
        try:
            entetes, _ = transform.lire_table(chemin.read_bytes(), chemin.name)
            transform.reconnaitre_colonnes(entetes, tables["entetes"], chemin.name)
        except SystemExit:
            constats.append(fatal("structure_source", f"{annee} : structure non reconnue ({chemin.name}), voir le message de transform.py"))
    if not constats:
        constats.append(ok("structure_source", f"{len(ctx['fichiers_courants'])} fichiers bruts reconnus"))
    return constats


def regle_couverture_annees(ctx) -> list[Constat]:
    annees = sorted(a for a, _ in ctx["fichiers_courants"])
    if not annees:
        return [fatal("couverture_annees", "aucun fichier annuel dans le manifeste")]
    manquantes = [a for a in range(annees[0], annees[-1] + 1) if a not in annees]
    if manquantes:
        return [alerte("couverture_annees", f"années absentes entre {annees[0]} et {annees[-1]} : {manquantes}", manquantes)]
    return [ok("couverture_annees", f"{annees[0]} → {annees[-1]} sans trou", [annees[0], annees[-1]])]


def regle_identifiants(ctx) -> list[Constat]:
    ids = [r["id"] for r in ctx["controles"]]
    constats = []
    if len(ids) != len(set(ids)):
        constats.append(fatal("identifiants", f"{len(ids) - len(set(ids))} identifiants en double"))
    mal_formes = [i for i in ids if not ID_VALIDE.match(i)]
    if mal_formes:
        constats.append(fatal("identifiants", f"identifiants mal formés : {mal_formes[:5]}"))
    return constats or [ok("identifiants", f"{len(ids)} identifiants uniques et bien formés", len(ids))]


def regle_champs_obligatoires(ctx) -> list[Constat]:
    constats = []
    n = len(ctx["controles"])
    for champ in ("annee", "organisme", "secteur_source"):
        vides = sum(1 for r in ctx["controles"] if not r[champ])
        taux = 1 - vides / n if n else 0
        if taux < SEUIL_CHAMPS_OBLIGATOIRES:
            constats.append(fatal("champs_obligatoires", f"{champ} vide sur {vides} lignes ({1 - taux:.1%})", vides))
        elif vides:
            constats.append(alerte("champs_obligatoires", f"{champ} vide sur {vides} lignes", vides))
    return constats or [ok("champs_obligatoires", "année, organisme et secteur toujours renseignés")]


def regle_volume(ctx) -> list[Constat]:
    constats = []
    par_annee = Counter(int(r["annee"]) for r in ctx["controles"])
    for annee, n in sorted(par_annee.items()):
        if not VOLUME_MIN <= n <= VOLUME_MAX:
            constats.append(fatal("volume", f"{annee} : {n} contrôles, hors de la plage attendue [{VOLUME_MIN}, {VOLUME_MAX}]", n))
    officiels = ctx["totaux_officiels"]
    ecarts = {}
    for annee, n in sorted(par_annee.items()):
        if annee in officiels and officiels[annee]:
            ecart = (n - officiels[annee]) / officiels[annee]
            if abs(ecart) > ECART_TOTAL_OFFICIEL:
                constats.append(alerte("volume", f"{annee} : {n} lignes contre {officiels[annee]} annoncées par la CNIL ({ecart:+.1%})", {"lignes": n, "officiel": officiels[annee]}))
            elif n != officiels[annee]:
                ecarts[annee] = {"lignes": n, "officiel": officiels[annee]}
    if ecarts and not any(c.niveau != "ok" for c in constats):
        constats.append(alerte("volume", f"écarts minimes avec les totaux officiels : {ecarts}", ecarts))
    if not any(c.niveau != "ok" for c in constats):
        constats.append(ok("volume", f"{sum(par_annee.values())} contrôles, volumes annuels plausibles et conformes aux totaux CNIL", dict(sorted(par_annee.items()))))
    return constats


def regle_annees(ctx) -> list[Constat]:
    courante = ctx["annee_courante"]
    hors = sorted({int(r["annee"]) for r in ctx["controles"] if not 2014 <= int(r["annee"]) <= courante})
    if hors:
        return [fatal("annees", f"années hors de [2014, {courante}] : {hors}", hors)]
    return [ok("annees", f"toutes les années dans [2014, {courante}]")]


def regle_enumerations(ctx) -> list[Constat]:
    constats = []
    inconnus_f = sorted({r["fondement"] for r in ctx["controles"]} - FONDEMENTS)
    inconnus_m = sorted({r["modalite"] for r in ctx["controles"]} - MODALITES)
    if inconnus_f:
        constats.append(fatal("enumerations", f"fondements inconnus : {inconnus_f}"))
    if inconnus_m:
        constats.append(fatal("enumerations", f"modalités inconnues : {inconnus_m}"))
    secteurs_connus = {s["secteur_source"] for s in ctx["secteurs"]}
    familles = {f["code"] for f in ctx["familles"]}
    inconnus_s = sorted({r["secteur_source"] for r in ctx["controles"]} - secteurs_connus)
    if inconnus_s:
        constats.append(fatal("enumerations", f"libellés de secteur absents de secteurs.csv : {inconnus_s}"))
    sans_famille = sorted({r["famille"] for r in ctx["controles"]} - familles)
    if sans_famille:
        constats.append(fatal("enumerations", f"familles absentes de familles.json : {sans_famille}"))
    return constats or [ok("enumerations", "fondements, modalités, secteurs et familles dans les valeurs connues")]


def regle_doublons(ctx) -> list[Constat]:
    n = sum(1 for r in ctx["controles"] if "ligne_dupliquee" in r["qualite"].split("|"))
    if n:
        return [alerte("doublons", f"{n} lignes strictement identiques à une autre de la même année (conservées, rang > 1)", n)]
    return [ok("doublons", "aucune ligne dupliquée")]


def regle_departements(ctx) -> list[Constat]:
    codes = {d["code"] for d in ctx["departements"]}
    invalides = Counter(l["departement"] for l in ctx["localisations"] if l["departement"] and l["departement"] not in codes)
    a_preciser = sum(1 for r in ctx["controles"] if "departement_a_preciser" in r["qualite"].split("|"))
    constats = []
    if invalides:
        constats.append(alerte("departements", f"codes département hors référentiel après localisation : {dict(invalides)}", dict(invalides)))
    if a_preciser:
        constats.append(ok("departements", f"{a_preciser} codes 20/97 précisés par la ville", a_preciser))
    return constats or [ok("departements", "tous les codes département dans le référentiel")]


def regle_coordonnees(ctx) -> list[Constat]:
    constats = []
    hors_bornes, hors_france, zero = [], [], []
    for l in ctx["localisations"]:
        for lon_s, lat_s, precision in ((l["org_lon"], l["org_lat"], l["org_precision"]), (l["ctrl_lon"], l["ctrl_lat"], l["ctrl_precision"])):
            if not lon_s:
                continue
            lon, lat = float(lon_s), float(lat_s)
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                hors_bornes.append(l["id"])
            if lon == 0 and lat == 0:
                zero.append(l["id"])
            if l["pays"] == "FR" and precision in ("commune", "adresse", "institution"):
                # Le siège de la CNIL (précision institution) est en métropole quel que soit le département de l'organisme.
                outre_mer = precision != "institution" and l["departement"].startswith("97")
                emprise = EMPRISES.get(l["departement"], EMPRISES["metropole"]) if outre_mer else EMPRISES["metropole"]
                if not dans(emprise, lon, lat):
                    hors_france.append(l["id"])
    if hors_bornes:
        constats.append(fatal("coordonnees", f"coordonnées hors bornes : {hors_bornes[:5]}", len(hors_bornes)))
    if zero:
        constats.append(fatal("coordonnees", f"coordonnées (0, 0) : {zero[:5]}", len(zero)))
    if hors_france:
        constats.append(fatal("coordonnees", f"points « France » hors de l'emprise attendue : {hors_france[:5]}", len(hors_france)))
    precisions_inconnues = sorted({l["org_precision"] for l in ctx["localisations"]} | {l["ctrl_precision"] for l in ctx["localisations"]})
    precisions_inconnues = [p for p in precisions_inconnues if p not in PRECISIONS]
    if precisions_inconnues:
        constats.append(fatal("coordonnees", f"précisions inconnues : {precisions_inconnues}"))
    return constats or [ok("coordonnees", "toutes les coordonnées dans les bornes et dans l'emprise de leur territoire")]


def regle_geocodage(ctx) -> list[Constat]:
    france = [l for l in ctx["localisations"] if l["pays"] == "FR"]
    if not france:
        return [fatal("geocodage", "aucun contrôle localisé en France")]
    precis = sum(1 for l in france if l["org_precision"] in ("commune", "adresse"))
    taux = precis / len(france)
    par_precision = dict(sorted(Counter(l["org_precision"] for l in ctx["localisations"]).items()))
    if taux < SEUIL_GEOCODAGE_FRANCE:
        return [fatal("geocodage", f"seulement {taux:.1%} des contrôles en France à la commune ou à l'adresse (seuil {SEUIL_GEOCODAGE_FRANCE:.0%})", par_precision)]
    constats = [ok("geocodage", f"{taux:.1%} des contrôles en France à la commune ou à l'adresse", par_precision)]
    non_resolues = ctx["geocodage_rapport"].get("villes_non_resolues", [])
    reelles = [v for v in non_resolues if v.get("ville_source")]
    if reelles:
        constats.append(alerte("geocodage", f"{len(reelles)} villes non résolues, à ajouter dans alias-villes.csv : "
                               + " ; ".join(f"{v['departement_source']} {v['ville_source']}" for v in reelles[:10]), len(reelles)))
    return constats


def regle_coherence_temporelle(ctx) -> list[Constat]:
    constats = []
    regles = (
        ("rgpd", lambda a: a < 2018, "RGPD avant 2018"),
        ("rgpd_ou_directive", lambda a: a != 2018, "« RGPD ou directive » hors 2018"),
        ("directive_police_justice", lambda a: a < 2018, "directive police-justice avant 2018"),
        ("loi78", lambda a: a > 2019, "Loi 78 après 2019"),
    )
    for fondement, test, libelle in regles:
        n = sum(1 for r in ctx["controles"] if r["fondement"] == fondement and test(int(r["annee"])))
        if n:
            constats.append(alerte("coherence_temporelle", f"{n} contrôles « {libelle} »", n))
    return constats or [ok("coherence_temporelle", "fondements cohérents avec les années")]


def regle_localisations_completes(ctx) -> list[Constat]:
    ids_c = {r["id"] for r in ctx["controles"]}
    ids_l = {l["id"] for l in ctx["localisations"]}
    if ids_c != ids_l:
        return [fatal("localisations", f"localisations.csv ne correspond pas à controles.csv : {len(ids_c - ids_l)} manquantes, {len(ids_l - ids_c)} en trop")]
    incoherents = [l["id"] for l in ctx["localisations"] if l["ctrl_lieu"] == "cnil" and ctx["modalites"][l["id"]] not in ("en_ligne", "sur_pieces", "sur_audition")]
    if incoherents:
        return [fatal("localisations", f"lieu du contrôle « cnil » avec une modalité incompatible : {incoherents[:5]}")]
    return [ok("localisations", "une localisation par contrôle, lieux du contrôle cohérents avec les modalités")]


def regle_surcouche(ctx) -> list[Constat]:
    ids = {r["id"] for r in ctx["controles"]}
    constats = []
    for nom, lignes in (("surcouche.csv", ctx["surcouche"]), ("propositions.csv", ctx["propositions"])):
        orphelines = [l["id"] for l in lignes if l["id"] not in ids]
        if orphelines:
            constats.append(alerte("surcouche", f"{nom} : {len(orphelines)} lignes dont l'identifiant n'existe plus (source CNIL révisée ?) : {orphelines[:5]}", len(orphelines)))
        statuts = {l.get("statut", "") for l in lignes}
        inconnus = sorted(statuts - {"valide", "a_verifier", "impossible", "refusee", ""})
        if inconnus:
            constats.append(alerte("surcouche", f"{nom} : statuts inconnus {inconnus}"))
    return constats or [ok("surcouche", "surcouche et propositions rattachées à des contrôles existants")]


def regle_manifeste(ctx) -> list[Constat]:
    manquants = [v["fichier"] for e in ctx["manifeste"].get("ressources", {}).values() for v in e.get("versions", []) if not (RAW / v["fichier"]).exists()]
    if manquants:
        return [fatal("manifeste", f"fichiers du manifeste absents de data/raw/ : {manquants[:5]}")]
    disparues = [e["titre"] for e in ctx["manifeste"].get("ressources", {}).values() if e.get("disparue_le")]
    if disparues:
        return [alerte("manifeste", f"ressources disparues de data.gouv.fr (archives conservées) : {disparues}")]
    return [ok("manifeste", "toutes les versions archivées sont présentes")]


REGLES = [
    regle_manifeste, regle_structure_source, regle_couverture_annees, regle_identifiants,
    regle_champs_obligatoires, regle_volume, regle_annees, regle_enumerations, regle_doublons,
    regle_departements, regle_localisations_completes, regle_coordonnees, regle_geocodage,
    regle_coherence_temporelle, regle_surcouche,
]


# --------------------------------------------------------- exécution ---

def charger_contexte(annee_courante: int | None = None) -> dict:
    manifeste = lire_json(METADATA / "manifest.json", {}) or {}
    controles = lire_csv(PROCESSED / "controles.csv")
    localisations = lire_csv(PROCESSED / "localisations.csv")
    tableau_1990 = next((RAW / e["versions"][-1]["fichier"] for e in manifeste.get("ressources", {}).values()
                         if e.get("dossier") == "nombre-controles-1990" and e.get("versions")), None)
    return {
        "annee_courante": annee_courante or dt.date.today().year,
        "manifeste": manifeste,
        "fichiers_courants": transform.fichiers_courants(manifeste) if manifeste else [],
        "tables_transform": transform.charger_tables(),
        "controles": controles,
        "localisations": localisations,
        "modalites": {r["id"]: r["modalite"] for r in controles},
        "secteurs": lire_csv(PROCESSED / "referentiels" / "secteurs.csv"),
        "familles": (lire_json(PROCESSED / "referentiels" / "familles.json") or {}).get("familles", []),
        "departements": (lire_json(PROCESSED / "referentiels" / "departements.json") or {}).get("departements", []),
        "surcouche": lire_csv(GEOCODING / "surcouche.csv"),
        "propositions": lire_csv(GEOCODING / "propositions.csv"),
        "geocodage_rapport": lire_json(METADATA / "geocodage-rapport.json", {}) or {},
        "totaux_officiels": totaux_officiels(tableau_1990),
    }


def valider(ctx: dict) -> list[Constat]:
    constats = []
    for regle in REGLES:
        constats += regle(ctx)
    return constats


def rapport(constats: list[Constat]) -> dict:
    return {
        "resultat": "fatal" if any(c.niveau == "fatal" for c in constats) else ("alerte" if any(c.niveau == "alerte" for c in constats) else "ok"),
        "nb_fatal": sum(1 for c in constats if c.niveau == "fatal"),
        "nb_alerte": sum(1 for c in constats if c.niveau == "alerte"),
        "nb_ok": sum(1 for c in constats if c.niveau == "ok"),
        "constats": [c.dict() for c in constats],
    }


def main(argv=None) -> int:
    ctx = charger_contexte()
    if not ctx["controles"] or not ctx["localisations"]:
        journal("ERREUR FATALE : controles.csv ou localisations.csv absent ; lancez transform.py puis geocode.py")
        return 1
    constats = valider(ctx)
    for c in constats:
        journal(f"{c.niveau.upper():6s} {c.regle:22s} {c.message}")
    r = rapport(constats)
    change = ecrire_json(RAPPORT, r)
    journal(f"résultat : {r['resultat']} ({r['nb_fatal']} fatal, {r['nb_alerte']} alerte, {r['nb_ok']} ok) ; rapport "
            + ("mis à jour" if change else "inchangé") + f" : {RAPPORT.relative_to(RACINE)}")
    return 1 if r["resultat"] == "fatal" else 0


if __name__ == "__main__":
    sys.exit(main())
