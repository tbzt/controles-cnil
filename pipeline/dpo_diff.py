"""Étape 24 : flux de désignations entre deux publications successives.

La CNIL ne publie que les désignations en vigueur : une désignation retirée
disparaît du fichier, une re-désignation écrase la date. Le seul moyen de
voir les retraits et remplacements est de comparer deux snapshots archivés
par `fetch.py --jeu dpo`. Ce script recalcule toute la série depuis
l'ensemble des versions du manifeste (`manifest-dpo.json`), dans l'ordre de
publication, et écrit `data/processed/dpo/flux-mensuels.csv` : une ligne
par couple de publications consécutives.

Clé d'un organisme : le SIREN quand il existe, sinon le nom normalisé et le
code postal. Pour chaque clé, l'ensemble des désignations (date, type de
DPO, structure désignée) est comparé :
- `nouvelles` : clés absentes de la publication précédente ;
- `retirees` : clés absentes de la publication courante ;
- `modifiees` : clés présentes des deux côtés avec un ensemble différent
  (re-désignation, changement de DPO interne ↔ externe, autre structure).

Recalculer la série entière à chaque exécution garantit qu'une relance ne
change rien (les fichiers bruts sont immuables). Avec un seul snapshot, le
fichier n'a qu'un en-tête.

Usage :
    python3 pipeline/dpo_diff.py
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import dpo  # noqa: E402
from pipeline.commun import METADATA, PROCESSED, RACINE, RAW, ecrire_texte, journal, lire_json  # noqa: E402

MANIFESTE = METADATA / "manifest-dpo.json"
SORTIE = PROCESSED / "dpo" / "flux-mensuels.csv"
COLONNES = ["publication_precedente", "publication", "total_precedent", "total", "nouvelles", "retirees", "modifiees", "solde"]


def versions_archivees(manifeste: dict) -> list[dict]:
    """Toutes les versions CSV, dans l'ordre de publication."""
    versions = []
    for entree in manifeste.get("ressources", {}).values():
        if entree.get("format") != "csv":
            continue
        for v in entree.get("versions", []):
            versions.append({"fichier": RAW / v["fichier"], "publie_le": (v.get("publie_le") or v.get("last_modified_source") or "")[:10]})
    return sorted(versions, key=lambda v: v["publie_le"])


def cle_organisme(ligne: dict) -> str:
    return ligne["siren"] or f"{ligne['nom_norm']}|{ligne['code_postal']}"


def empreinte(fichier: Path, tables: dict) -> dict[str, frozenset]:
    """{clé d'organisme → ensemble des désignations} pour un fichier brut."""
    entete, lignes = dpo.lire_brut(fichier)
    noms = [dpo.ENTETES[h] for h in entete]
    index: dict[str, set] = {}
    for l in lignes:
        e = dpo.transformer_ligne(dict(zip(noms, l)), "", tables)
        index.setdefault(cle_organisme(e), set()).add((e["date_designation"], e["type_dpo"], e["nom_designe_norm"]))
    return {k: frozenset(v) for k, v in index.items()}


def comparer(avant: dict[str, frozenset], apres: dict[str, frozenset]) -> dict:
    nouvelles = sum(1 for k in apres if k not in avant)
    retirees = sum(1 for k in avant if k not in apres)
    modifiees = sum(1 for k in apres if k in avant and avant[k] != apres[k])
    return {"nouvelles": nouvelles, "retirees": retirees, "modifiees": modifiees, "solde": nouvelles - retirees}


def serie(versions: list[dict], tables: dict) -> list[dict]:
    lignes = []
    precedent = None
    for v in versions:
        courant = empreinte(v["fichier"], tables)
        if precedent is not None:
            c = comparer(precedent["empreinte"], courant)
            lignes.append({"publication_precedente": precedent["publie_le"], "publication": v["publie_le"],
                           "total_precedent": len(precedent["empreinte"]), "total": len(courant), **c})
            journal(f"{precedent['publie_le']} → {v['publie_le']} : +{c['nouvelles']} −{c['retirees']} ~{c['modifiees']}")
        precedent = {"publie_le": v["publie_le"], "empreinte": courant}
    return lignes


def ecrire(lignes: list[dict]) -> bool:
    tampon = io.StringIO(newline="")
    w = csv.DictWriter(tampon, fieldnames=COLONNES, lineterminator="\n")
    w.writeheader()
    w.writerows(lignes)
    return ecrire_texte(SORTIE, tampon.getvalue())


def main(argv=None) -> int:
    manifeste = lire_json(MANIFESTE, {}) or {}
    versions = versions_archivees(manifeste)
    if not versions:
        journal("aucune version DPO archivée ; rien à comparer")
        return 0
    manquantes = [v["fichier"].name for v in versions if not v["fichier"].exists()]
    if manquantes:
        journal(f"ERREUR FATALE : fichiers bruts absents : {manquantes}")
        return 1
    tables = dpo.charger_tables()
    lignes = serie(versions, tables) if len(versions) > 1 else []
    change = ecrire(lignes)
    journal(f"{len(versions)} snapshot(s), {len(lignes)} couple(s) comparé(s) ; " + ("mis à jour" if change else "inchangé") + f" : {SORTIE.relative_to(RACINE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
