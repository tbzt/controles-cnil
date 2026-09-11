"""Étape 2 : transformer les fichiers bruts en une table normalisée.

Lit la version courante de chaque ressource annuelle de `data/raw/` (d'après
le manifeste), reconnaît les colonnes par leur en-tête normalisé (jamais par
leur position), normalise les valeurs et produit :

- `data/processed/controles.csv` et `data/processed/controles.json` : une
  ligne par contrôle, champs `*_source` bruts et champs dérivés ;
- un résumé sur la sortie standard.

Le script s'arrête (code 1) dès qu'une décision humaine est nécessaire :
en-tête inconnu, libellé de fondement, de modalité ou de pays inconnu,
encodage ou séparateur inattendu, colonne sans en-tête mais avec des valeurs,
année de la colonne « Année » différente de celle du fichier.

Usage :
    python3 pipeline/transform.py
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.commun import (  # noqa: E402
    METADATA,
    PROCESSED,
    RACINE,
    RAW,
    cle_normalisee,
    ecrire_json,
    ecrire_texte,
    erreur_fatale,
    journal,
    lire_json,
    nettoyer_espaces,
    normaliser_nom,
)

MAPPINGS = RACINE / "pipeline" / "mappings"
SECTEURS_CSV = PROCESSED / "referentiels" / "secteurs.csv"
ORGANISMES_ALIAS_CSV = PROCESSED / "referentiels" / "organismes-alias.csv"
SORTIE_CSV = PROCESSED / "controles.csv"
SORTIE_JSON = PROCESSED / "controles.json"

ENCODAGES = ("utf-8-sig", "cp1252")
CHAMPS_OBLIGATOIRES = ("type", "organisme", "ville", "departement", "secteur")

COLONNES = [
    "id", "annee",
    "fondement", "fondement_source",
    "modalite", "modalite_source",
    "organisme", "organisme_norm", "organisme_cle",
    "ville_source",
    "departement", "departement_source",
    "pays", "pays_source",
    "secteur", "famille", "secteur_source",
    "source_fichier", "source_ligne",
    "qualite",
]

DEPARTEMENT_VALIDE = re.compile(r"^(0[1-9]|[1-8]\d|9[0-5]|2A|2B|97[1-6])$")

# Clé de rapprochement des organismes : formes juridiques et suffixes de
# domaine retirés, puis table d'alias écrite à la main.
FORMES_JURIDIQUES = re.compile(r"\b(SAS|SA|SARL|SASU|EURL|SNC|SCI|SE|GIE|SCOP|SEM|SCA|SCS|SELARL|SELAS|SAEM|EPIC|GIP|S A S U|S A S|S A R L|S A)\b")
DOMAINE_FIN = re.compile(r"\s(FR|COM|ORG|NET|EU|IO|CO|INFO|GOUV FR)$")
DOMAINE_DEBUT = re.compile(r"^(HTTPS?\s)?(WWW\s)+")


def cle_organisme(organisme_norm: str, alias: dict | None = None) -> str:
    """Clé de rapprochement : nom normalisé sans forme juridique ni suffixe de
    domaine, puis alias manuel. « CDISCOUNT FR », « CDISCOUNT COM » et
    « CDISCOUNT » partagent la clé CDISCOUNT ; « FACEBOOK IRELAND » rejoint
    FACEBOOK par la table d'alias."""
    n = DOMAINE_DEBUT.sub("", organisme_norm)
    n = FORMES_JURIDIQUES.sub(" ", n)
    n = re.sub(r"\s+", " ", n).strip()
    while True:
        m = DOMAINE_FIN.search(n)
        if not m or " " not in n:
            break
        n = n[:m.start()].strip()
    if alias and n in alias:
        n = alias[n]
    return n or organisme_norm


# ------------------------------------------------------------ lecture ---

def decoder(octets: bytes, nom: str) -> str:
    """Essaie les encodages connus dans l'ordre ; le premier qui décode sans
    erreur gagne (cp1252 accepte presque tout, d'où son rang final)."""
    for encodage in ENCODAGES:
        try:
            return octets.decode(encodage)
        except UnicodeDecodeError:
            continue
    erreur_fatale(f"{nom} : aucun des encodages {ENCODAGES} ne décode ce fichier")


def detecter_separateur(texte: str, nom: str) -> str:
    """Le point-virgule est attendu ; tout autre séparateur majoritaire est
    une modification de structure, donc fatal."""
    extrait = texte[:4000]
    if extrait.count(";") >= max(1, extrait.count(",")):
        return ";"
    erreur_fatale(f"{nom} : séparateur inattendu (virgule majoritaire, point-virgule attendu)")


def lire_table(octets: bytes, nom: str) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """Renvoie (en-têtes nettoyés, [(ligne physique de début, valeurs brutes)]).

    Les colonnes sans en-tête et sans aucune valeur (résidus d'export Excel)
    sont retirées ; une colonne sans en-tête mais avec des valeurs est fatale.
    Les lignes entièrement vides sont ignorées.
    """
    texte = decoder(octets, nom)
    separateur = detecter_separateur(texte, nom)
    lecteur = csv.reader(io.StringIO(texte, newline=""), delimiter=separateur, quotechar='"')
    try:
        entetes_bruts = next(lecteur)
    except StopIteration:
        erreur_fatale(f"{nom} : fichier vide")
    entetes_bruts = [nettoyer_espaces(h) for h in entetes_bruts]
    lignes = []
    ligne_precedente = lecteur.line_num
    for valeurs in lecteur:
        debut = ligne_precedente + 1
        ligne_precedente = lecteur.line_num
        valeurs = [v.strip() for v in valeurs]
        if any(valeurs):
            lignes.append((debut, valeurs))
    largeur = max([len(entetes_bruts)] + [len(v) for _, v in lignes])
    entetes_bruts += [""] * (largeur - len(entetes_bruts))
    lignes = [(d, v + [""] * (largeur - len(v))) for d, v in lignes]

    garder = []
    for i, entete in enumerate(entetes_bruts):
        a_des_valeurs = any(v[i] for _, v in lignes)
        if entete:
            garder.append(i)
        elif a_des_valeurs:
            erreur_fatale(f"{nom} : la colonne n° {i + 1} n'a pas d'en-tête mais contient des valeurs")
    return [entetes_bruts[i] for i in garder], [(d, [v[i] for i in garder]) for d, v in lignes]


def reconnaitre_colonnes(entetes: list[str], mapping: dict, nom: str) -> list[str]:
    """Associe chaque en-tête à un champ canonique. Inconnu ou en double :
    fatal, avec la liste exacte à ajouter dans entetes.json."""
    champs, inconnus = [], []
    for entete in entetes:
        cle = cle_normalisee(entete)
        champ = mapping.get(cle)
        if champ is None:
            inconnus.append(f"« {entete} » (clé « {cle} »)")
        champs.append(champ)
    if inconnus:
        erreur_fatale(f"{nom} : en-têtes non reconnus : " + ", ".join(inconnus)
                      + ". Ajoutez-les dans pipeline/mappings/entetes.json après vérification du fichier.")
    doublons = [c for c, n in Counter(champs).items() if n > 1]
    if doublons:
        erreur_fatale(f"{nom} : plusieurs colonnes désignent le même champ : {doublons}")
    manquants = [c for c in CHAMPS_OBLIGATOIRES if c not in champs]
    if manquants:
        erreur_fatale(f"{nom} : champs obligatoires absents : {manquants}")
    return champs


# ---------------------------------------------------- normalisation ---

def normaliser_departement(brut: str) -> tuple[str, list[str]]:
    """Forme canonique du code département quand elle est déductible sans
    la ville ; sinon la valeur brute et un drapeau."""
    d = brut.strip().upper()
    drapeaux = []
    if not d:
        return "", ["departement_vide"]
    if re.fullmatch(r"\d", d):
        d = "0" + d
        drapeaux.append("departement_corrige")
    if "-" in d:
        d = d.split("-", 1)[0].strip()
        drapeaux.append("departement_multiple")
    if d in ("20", "97", "98"):
        drapeaux.append("departement_a_preciser")
        return d, drapeaux
    if not DEPARTEMENT_VALIDE.fullmatch(d):
        drapeaux.append("departement_invalide")
    return d, drapeaux


def est_ligne_parasite(ligne: dict) -> bool:
    """Ligne de total ou de compteur : rien d'autre que la première colonne."""
    return not any(ligne.get(c) for c in ("organisme", "ville", "departement", "secteur", "modalite", "pays"))


def identifiant(annee: int, ligne: dict, rang: int) -> str:
    """`annee-hash8-rang` : le hachage décrit le contenu source (après
    nettoyage des espaces), le rang distingue les lignes identiques."""
    base = "|".join([str(annee)] + [ligne.get(c, "") for c in
                    ("type", "modalite", "organisme", "ville", "departement", "pays", "secteur")])
    return f"{annee}-{hashlib.sha1(base.encode('utf-8')).hexdigest()[:8]}-{rang}"


def transformer_fichier(octets: bytes, nom: str, annee: int, tables: dict) -> tuple[list[dict], list[dict]]:
    """Transforme un fichier brut. Renvoie (enregistrements, lignes rejetées)."""
    entetes, lignes = lire_table(octets, nom)
    champs = reconnaitre_colonnes(entetes, tables["entetes"], nom)
    fondements, modalites, pays_map = tables["fondements"], tables["modalites"], tables["pays"]
    secteurs = tables.get("secteurs")

    enregistrements, rejets = [], []
    compteur_hash: Counter = Counter()
    for debut, brutes in lignes:
        valeurs = [nettoyer_espaces(v) for v in brutes]
        ligne = dict(zip(champs, valeurs))
        if est_ligne_parasite(ligne):
            rejets.append({"source_fichier": nom, "source_ligne": debut, "contenu": valeurs,
                           "motif": "ligne parasite (total ou compteur)"})
            continue
        drapeaux = []

        if "annee" in ligne:
            if ligne["annee"] and ligne["annee"] != str(annee):
                erreur_fatale(f"{nom} ligne {debut} : colonne Année = {ligne['annee']!r} mais fichier {annee}")
        else:
            drapeaux.append("annee_source_absente")

        # Fondement, et modalité implicite pour 2014-2016.
        cle_type = cle_normalisee(ligne["type"])
        regle = fondements.get(cle_type)
        if regle is None:
            erreur_fatale(f"{nom} ligne {debut} : type de contrôle inconnu « {ligne['type']} ». "
                          "Ajoutez-le dans pipeline/mappings/fondements.json.")
        fondement = regle["fondement"]

        modalite_source = ligne.get("modalite", "")
        if "modalite" in ligne and modalite_source:
            modalite = modalites.get(cle_normalisee(modalite_source))
            if modalite is None:
                erreur_fatale(f"{nom} ligne {debut} : modalité inconnue « {modalite_source} ». "
                              "Ajoutez-la dans pipeline/mappings/modalites.json.")
        elif regle.get("modalite_implicite"):
            modalite = regle["modalite_implicite"]
            drapeaux.append("modalite_deduite_du_type")
        else:
            modalite = "non_renseignee"
            drapeaux.append("modalite_non_renseignee")

        organisme = ligne["organisme"]
        organisme_norm = normaliser_nom(organisme)
        organisme_cle = cle_organisme(organisme_norm, tables.get("organismes_alias"))
        if not organisme:
            drapeaux.append("organisme_vide")
        if organisme_cle != organisme_norm:
            drapeaux.append("organisme_rapproche")
        if "\n" in brutes[champs.index("organisme")]:
            drapeaux.append("organisme_multiligne")

        departement, dr = normaliser_departement(ligne["departement"])
        drapeaux += dr
        if not ligne["ville"]:
            drapeaux.append("ville_vide")

        pays_source = ligne.get("pays", "")
        if "pays" in ligne:
            if pays_source:
                pays = pays_map.get(cle_normalisee(pays_source))
                if pays is None:
                    erreur_fatale(f"{nom} ligne {debut} : pays inconnu « {pays_source} ». "
                                  "Ajoutez-le dans pipeline/mappings/pays.json.")
            else:
                pays = "FR"
                drapeaux.append("pays_vide")
        else:
            pays = "FR"
            drapeaux.append("pays_deduit")

        secteur_source = ligne["secteur"]
        if not secteur_source:
            drapeaux.append("secteur_vide")
        secteur = famille = ""
        if secteurs is not None:
            corresp = secteurs.get(cle_normalisee(secteur_source))
            if corresp is None:
                erreur_fatale(f"{nom} ligne {debut} : secteur inconnu « {secteur_source} ». "
                              f"Ajoutez-le dans {SECTEURS_CSV.relative_to(RACINE)}.")
            secteur, famille = corresp

        cle_hash = identifiant(annee, ligne, 0)[:-2]
        compteur_hash[cle_hash] += 1
        rang = compteur_hash[cle_hash]
        if rang > 1:
            drapeaux.append("ligne_dupliquee")

        enregistrements.append({
            "id": f"{cle_hash}-{rang}",
            "annee": annee,
            "fondement": fondement, "fondement_source": ligne["type"],
            "modalite": modalite, "modalite_source": modalite_source,
            "organisme": organisme, "organisme_norm": organisme_norm, "organisme_cle": organisme_cle,
            "ville_source": ligne["ville"],
            "departement": departement, "departement_source": ligne["departement"],
            "pays": pays, "pays_source": pays_source,
            "secteur": secteur, "famille": famille, "secteur_source": secteur_source,
            "source_fichier": nom, "source_ligne": debut,
            "qualite": drapeaux,
        })
    return enregistrements, rejets


# --------------------------------------------------------- entrées ---

def charger_tables() -> dict:
    tables = {
        "entetes": lire_json(MAPPINGS / "entetes.json")["entetes"],
        "fondements": lire_json(MAPPINGS / "fondements.json")["fondements"],
        "modalites": lire_json(MAPPINGS / "modalites.json")["modalites"],
        "pays": lire_json(MAPPINGS / "pays.json")["pays"],
        "secteurs": None,
        "organismes_alias": {},
    }
    if ORGANISMES_ALIAS_CSV.exists():
        with open(ORGANISMES_ALIAS_CSV, encoding="utf-8", newline="") as f:
            tables["organismes_alias"] = {r["organisme_norm"]: r["organisme_cle"] for r in csv.DictReader(f)}
    if SECTEURS_CSV.exists():
        with open(SECTEURS_CSV, encoding="utf-8", newline="") as f:
            tables["secteurs"] = {cle_normalisee(r["secteur_source"]): (r["secteur"], r["famille"])
                                  for r in csv.DictReader(f)}
    return tables


def fichiers_courants(manifeste: dict) -> list[tuple[int, Path]]:
    """Dernière version archivée de chaque ressource annuelle, triée par année."""
    resultat = []
    for entree in manifeste.get("ressources", {}).values():
        if not entree.get("dossier", "").isdigit() or not entree.get("versions"):
            continue
        resultat.append((int(entree["dossier"]), RAW / entree["versions"][-1]["fichier"]))
    doublons = [a for a, n in Counter(a for a, _ in resultat).items() if n > 1]
    if doublons:
        erreur_fatale(f"plusieurs ressources CSV pour une même année : {doublons}")
    return sorted(resultat)


# --------------------------------------------------------- sorties ---

def ecrire_sorties(enregistrements: list[dict]) -> bool:
    """Écrit CSV et JSON ; renvoie True si au moins un fichier a changé."""
    enregistrements.sort(key=lambda e: (e["annee"], e["source_ligne"], e["id"]))
    tampon = io.StringIO()
    ecrivain = csv.DictWriter(tampon, fieldnames=COLONNES, lineterminator="\n")
    ecrivain.writeheader()
    for e in enregistrements:
        ligne = dict(e)
        ligne["qualite"] = "|".join(e["qualite"])
        ecrivain.writerow(ligne)
    a = ecrire_texte(SORTIE_CSV, tampon.getvalue())
    b = ecrire_json(SORTIE_JSON, enregistrements)
    return a or b


def main(argv=None) -> int:
    manifeste = lire_json(METADATA / "manifest.json")
    if not manifeste:
        erreur_fatale("manifeste absent : lancez d'abord pipeline/fetch.py")
    tables = charger_tables()
    if tables["secteurs"] is None:
        journal(f"avertissement : {SECTEURS_CSV.relative_to(RACINE)} absent, colonnes secteur et famille laissées vides")

    tous, rejets = [], []
    for annee, chemin in fichiers_courants(manifeste):
        enregistrements, rej = transformer_fichier(chemin.read_bytes(), chemin.name, annee, tables)
        journal(f"{annee} : {len(enregistrements)} contrôles, {len(rej)} ligne(s) rejetée(s) ← {chemin.name}")
        tous += enregistrements
        rejets += rej
    for r in rejets:
        journal(f"rejet {r['source_fichier']} ligne {r['source_ligne']} : {r['motif']} → {r['contenu'][:3]}")
    drapeaux = Counter(d for e in tous for d in e["qualite"])
    journal(f"total : {len(tous)} contrôles ; drapeaux : " + ", ".join(f"{k}={v}" for k, v in sorted(drapeaux.items())))
    change = ecrire_sorties(tous)
    change = ecrire_json(METADATA / "rejets.json", rejets) or change
    journal(("mis à jour" if change else "inchangés") + f" : {SORTIE_CSV.relative_to(RACINE)}, {SORTIE_JSON.relative_to(RACINE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
