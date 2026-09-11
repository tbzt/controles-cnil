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

Les scripts sont à écrire (étapes 1 à 7 du plan). Tests :
`python3 -m unittest discover -s pipeline/tests -t .`
