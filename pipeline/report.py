"""Rapport des changements entre l'état précédent et l'état produit.

    python3 pipeline/report.py --avant <dossier> [--resume <fichier>] [--tag donnees-AAAA-MM-JJ]

`<dossier>` contient les copies d'avant exécution de `controles.csv`,
`localisations.csv`, `manifest.json` et `quality-report.json` (le workflow
les copie avant de lancer le pipeline ; en local, `--avant HEAD` les lit
depuis le dernier commit).

Écrit, seulement si les données ont changé :
- une entrée en tête de `data/metadata/CHANGELOG-DATA.md` ;
- une entrée dans `data/metadata/releases.json` (tag, date, résumé) ;
et toujours, si `--resume` est donné, le rapport en Markdown dans ce fichier
(le résumé du job GitHub Actions). Code de sortie 0 dans tous les cas ; la
sortie standard se termine par `CHANGEMENT=oui` ou `CHANGEMENT=non`, lue par
le workflow.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.commun import METADATA, PROCESSED, RACINE, ecrire_json, ecrire_texte, journal, lire_json  # noqa: E402

CHANGELOG = METADATA / "CHANGELOG-DATA.md"
RELEASES = METADATA / "releases.json"
FICHIERS = {
    "controles.csv": PROCESSED / "controles.csv",
    "localisations.csv": PROCESSED / "localisations.csv",
    "manifest.json": METADATA / "manifest.json",
    "quality-report.json": METADATA / "quality-report.json",
}


def lire_csv_texte(texte: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(texte, newline="")))


def etat_depuis(dossier: str) -> dict:
    """Contenu des fichiers d'avant : depuis un dossier, ou depuis git (`HEAD`)."""
    etat = {}
    for nom, chemin in FICHIERS.items():
        if dossier == "HEAD":
            rel = chemin.relative_to(RACINE).as_posix()
            r = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=RACINE, capture_output=True, text=True)
            etat[nom] = r.stdout if r.returncode == 0 else ""
        else:
            p = Path(dossier) / nom
            etat[nom] = p.read_text(encoding="utf-8") if p.exists() else ""
    return etat


def etat_actuel() -> dict:
    return {nom: (chemin.read_text(encoding="utf-8") if chemin.exists() else "") for nom, chemin in FICHIERS.items()}


def comparer(avant: dict, apres: dict) -> dict:
    """Différences structurées entre deux états."""
    c_avant = {r["id"]: r for r in lire_csv_texte(avant["controles.csv"])} if avant["controles.csv"] else {}
    c_apres = {r["id"]: r for r in lire_csv_texte(apres["controles.csv"])} if apres["controles.csv"] else {}
    ajoutes = sorted(set(c_apres) - set(c_avant))
    retires = sorted(set(c_avant) - set(c_apres))
    par_annee = lambda ids, src: dict(sorted(Counter(src[i]["annee"] for i in ids).items()))  # noqa: E731

    m_avant = json.loads(avant["manifest.json"]) if avant["manifest.json"] else {}
    m_apres = json.loads(apres["manifest.json"]) if apres["manifest.json"] else {}
    r_avant = m_avant.get("ressources", {})
    r_apres = m_apres.get("ressources", {})
    ressources_nouvelles = [r_apres[k]["titre"] for k in r_apres if k not in r_avant]
    ressources_modifiees = [r_apres[k]["titre"] for k in r_apres if k in r_avant and len(r_apres[k].get("versions", [])) > len(r_avant[k].get("versions", []))]
    ressources_disparues = [r_apres[k]["titre"] for k in r_apres if r_apres[k].get("disparue_le") and not r_avant.get(k, {}).get("disparue_le")]

    def libelles(rows, champ):
        return {r[champ] for r in rows if r.get(champ)}
    nouveaux_libelles = {}
    for champ in ("secteur_source", "fondement_source", "modalite_source", "pays_source"):
        nouveaux = sorted(libelles(c_apres.values(), champ) - libelles(c_avant.values(), champ))
        if nouveaux and c_avant:
            nouveaux_libelles[champ] = nouveaux

    l_apres = lire_csv_texte(apres["localisations.csv"]) if apres["localisations.csv"] else []
    l_avant = lire_csv_texte(avant["localisations.csv"]) if avant["localisations.csv"] else []
    precision = lambda rows: dict(sorted(Counter(r["org_precision"] for r in rows).items()))  # noqa: E731
    q_apres = json.loads(apres["quality-report.json"]) if apres["quality-report.json"] else {}

    donnees_changees = bool(ajoutes or retires or ressources_nouvelles or ressources_modifiees or ressources_disparues
                            or avant["localisations.csv"] != apres["localisations.csv"])
    return {
        "donnees_changees": donnees_changees,
        "controles": {"avant": len(c_avant), "apres": len(c_apres), "ajoutes": len(ajoutes), "retires": len(retires),
                      "ajoutes_par_annee": par_annee(ajoutes, c_apres), "retires_par_annee": par_annee(retires, c_avant)},
        "ressources": {"nouvelles": ressources_nouvelles, "modifiees": ressources_modifiees, "disparues": ressources_disparues},
        "nouveaux_libelles": nouveaux_libelles,
        "localisation": {"avant": precision(l_avant), "apres": precision(l_apres)},
        "qualite": {"resultat": q_apres.get("resultat"), "fatal": q_apres.get("nb_fatal"), "alerte": q_apres.get("nb_alerte"),
                    "alertes": [c["message"] for c in q_apres.get("constats", []) if c["niveau"] == "alerte"]},
    }


def en_markdown(diff: dict, date: str, tag: str | None) -> str:
    lignes = [f"## {date}" + (f" — `{tag}`" if tag else ""), ""]
    if not diff["donnees_changees"]:
        lignes.append("Aucun changement de données. Vérification effectuée, rien à publier.")
    else:
        c = diff["controles"]
        lignes.append(f"- Contrôles : {c['avant']} → {c['apres']} ({c['ajoutes']} ajoutés, {c['retires']} retirés).")
        if c["ajoutes_par_annee"]:
            lignes.append("  - ajoutés par année : " + ", ".join(f"{a} : {n}" for a, n in c["ajoutes_par_annee"].items()))
        if c["retires_par_annee"]:
            lignes.append("  - retirés par année : " + ", ".join(f"{a} : {n}" for a, n in c["retires_par_annee"].items()))
        r = diff["ressources"]
        if r["nouvelles"]:
            lignes.append("- Ressources nouvelles sur data.gouv.fr : " + " ; ".join(r["nouvelles"]))
        if r["modifiees"]:
            lignes.append("- Ressources remplacées en place (nouvelle version archivée, l'ancienne conservée) : " + " ; ".join(r["modifiees"]))
        if r["disparues"]:
            lignes.append("- Ressources disparues de data.gouv.fr (archives conservées) : " + " ; ".join(r["disparues"]))
        for champ, valeurs in diff["nouveaux_libelles"].items():
            lignes.append(f"- Nouveaux libellés `{champ}` : " + " ; ".join(valeurs))
        lignes.append("- Localisation de l'organisme, par précision : " + ", ".join(f"{k} {v}" for k, v in diff["localisation"]["apres"].items()))
    q = diff["qualite"]
    lignes.append(f"- Qualité : {q['resultat']} ({q['fatal']} fatal, {q['alerte']} alerte)." if q["resultat"] else "- Qualité : rapport absent.")
    for a in q["alertes"]:
        lignes.append(f"  - {a}")
    return "\n".join(lignes) + "\n"


def main(argv=None) -> int:
    parseur = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parseur.add_argument("--avant", default="HEAD", help="dossier des copies d'avant, ou HEAD (défaut)")
    parseur.add_argument("--resume", help="fichier Markdown où écrire le rapport (résumé du job)")
    parseur.add_argument("--tag", help="tag git de la publication, si les données ont changé")
    parseur.add_argument("--date", default=dt.date.today().isoformat())
    args = parseur.parse_args(argv)

    diff = comparer(etat_depuis(args.avant), etat_actuel())
    texte = en_markdown(diff, args.date, args.tag if diff["donnees_changees"] else None)
    print(texte)
    if args.resume:
        Path(args.resume).parent.mkdir(parents=True, exist_ok=True)
        with open(args.resume, "a", encoding="utf-8") as f:
            f.write("# Actualisation des données\n\n" + texte)

    if diff["donnees_changees"]:
        existant = CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.exists() else "# Journal des changements de données\n\nGénéré par `pipeline/report.py` à chaque publication.\n\n"
        entete, _, corps = existant.partition("\n## ")
        ecrire_texte(CHANGELOG, entete.rstrip("\n") + "\n\n" + texte + ("\n## " + corps if corps else ""))
        releases = lire_json(RELEASES, {"releases": []}) or {"releases": []}
        entree = {"tag": args.tag, "date": args.date, "controles": diff["controles"]["apres"],
                  "annee_max": max((r["annee"] for r in lire_csv_texte(FICHIERS["controles.csv"].read_text(encoding="utf-8"))), default=None),
                  "resume": f"{diff['controles']['ajoutes']} ajoutés, {diff['controles']['retires']} retirés"}
        if not any(e.get("tag") == args.tag and args.tag for e in releases["releases"]):
            releases["releases"].insert(0, entree)
        ecrire_json(RELEASES, releases)
        journal(f"journal et releases.json mis à jour ({CHANGELOG.name}, {RELEASES.name})")
    print("CHANGEMENT=" + ("oui" if diff["donnees_changees"] else "non"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
