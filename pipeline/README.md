# Pipeline

Scripts Python 3, bibliothèque standard uniquement, exécutables un par un
dans cet ordre :

1. `fetch.py` : récupère les ressources CSV du jeu de données data.gouv.fr,
   archive toute version nouvelle dans `data/raw/`, met à jour le manifeste.
2. `transform.py` : lit `data/raw/`, applique le mapping d'en-têtes par
   année, produit `data/processed/controles.csv` et `.json`.
3. `geocode.py` : produit `data/processed/localisations.csv` à partir de la
   surcouche validée, du référentiel communes et des alias, hors ligne.
4. `validate.py` : contrôles de qualité, `data/metadata/quality-report.json`,
   code de sortie non nul sur règle fatale.
5. `build.py` : GeoJSON, statistiques, journal des changements.

État : `fetch.py` est écrit et testé ; les autres scripts sont à venir.

```bash
python3 pipeline/fetch.py              # récupère ce qui a changé
python3 pipeline/fetch.py --forcer     # retélécharge tout, sans dupliquer un contenu identique
python3 pipeline/fetch.py --hors-ligne # vérifie seulement que data/raw/ correspond au manifeste
python3 -m unittest discover -s pipeline/tests -t .
```

`fetch.py` ne touche jamais à un fichier existant de `data/raw/` : une
ressource modifiée côté CNIL donne une version de plus dans le manifeste et
un fichier de plus, l'ancien restant en place.
