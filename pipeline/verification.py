"""Trace de la dernière vérification de la source, au plus une fois par mois.

    python3 pipeline/verification.py [--date AAAA-MM-JJ] [--changement oui|non]

Écrit `data/metadata/derniere-verification.json` si le mois a changé depuis
la dernière trace, ou si les données ont changé. C'est l'exception assumée à
la règle « aucun commit sans changement de données » : GitHub désactive les
workflows planifiés d'un dépôt public sans commit depuis 60 jours, et une
source qui ne change qu'une fois par an éteindrait le planning. Douze
micro-commits par an entretiennent le planning et documentent, sur la page
Données, à quand remonte la dernière vérification.

Sortie standard : `VERIFICATION=ecrite` ou `VERIFICATION=inchangee`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.commun import METADATA, ecrire_json, lire_json  # noqa: E402

FICHIER = METADATA / "derniere-verification.json"


def doit_ecrire(precedent: dict | None, date: str, changement: bool) -> bool:
    if changement or not precedent:
        return True
    return precedent.get("derniere_verification", "")[:7] != date[:7]


def main(argv=None) -> int:
    parseur = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parseur.add_argument("--date", default=dt.date.today().isoformat())
    parseur.add_argument("--changement", choices=("oui", "non"), default="non")
    args = parseur.parse_args(argv)
    precedent = lire_json(FICHIER)
    if doit_ecrire(precedent, args.date, args.changement == "oui"):
        contenu = {
            "_commentaire": "Date de la dernière exécution du workflow d'actualisation ayant écrit ce fichier : au plus une fois par mois sans changement, et à chaque changement de données.",
            "derniere_verification": args.date,
            "derniere_publication_donnees": args.date if args.changement == "oui" else (precedent or {}).get("derniere_publication_donnees"),
        }
        ecrire_json(FICHIER, contenu)
        print("VERIFICATION=ecrite")
    else:
        print("VERIFICATION=inchangee")
    return 0


if __name__ == "__main__":
    sys.exit(main())
