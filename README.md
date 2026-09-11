# Contrôles CNIL

Carte et analyse des contrôles réalisés par la CNIL depuis 2014, à partir du
jeu de données ouvert [« Contrôles réalisés par la CNIL »](https://www.data.gouv.fr/datasets/controles-realises-par-la-cnil)
publié sur data.gouv.fr.

Application entièrement statique, hébergée sur GitHub Pages, sans base de
données ni serveur applicatif. Les données sont récupérées, normalisées,
localisées et vérifiées par un pipeline Python exécuté par GitHub Actions ;
elles sont versionnées dans ce dépôt et réutilisables sans le site.

## État du projet

Étape 6 sur 18. `pipeline/fetch.py` archive les onze fichiers CSV de la
CNIL dans `data/raw/` avec leur empreinte ; `pipeline/transform.py` les
normalise en une table unique de 3 617 contrôles
(`data/processed/controles.csv` et `.json`), avec identifiants stables,
valeurs brutes conservées, drapeaux de qualité, et secteurs harmonisés en
seize familles comparables sur toute la période ; `pipeline/geocode.py`
localise chaque contrôle hors ligne (`data/processed/localisations.csv`),
avec deux lieux par contrôle : à l'adresse pour 2639 contrôles (2 288
hérités de la carte uMap, 351 sièges trouvés automatiquement dans
l'annuaire des entreprises avec un score haut), à la commune pour le reste
des contrôles en France ; 212 propositions à score moyen attendent une
validation dans `data/geocoding/propositions.csv` ; `pipeline/validate.py`
applique quinze règles de qualité (structure, volumes, énumérations,
coordonnées, cohérence temporelle…) et arrête tout sur un constat fatal.
La génération du GeoJSON et des statistiques (étape 7), le workflow GitHub
Actions (étape 8) et le site restent à faire.

## Ce que contiennent les données source, et ce qu'elles ne contiennent pas

- Une liste par année, de 2014 à 2023, d'environ 350 contrôles chacune :
  organisme contrôlé, fondement juridique, modalité (depuis 2017), ville,
  département, pays (depuis 2021), secteur d'activité.
- Pas d'adresse, pas de date dans l'année, pas d'identifiant.
- Un format physique différent chaque année (encodage, en-têtes, ordre des
  colonnes) et une nomenclature des secteurs refondue en 2018.

Le pipeline conserve chaque fichier brut sans modification, produit une
version normalisée documentée, et sépare les données de la CNIL de la
localisation qui en est déduite, avec pour chaque point sa précision et sa
méthode.

## Localisation : deux lieux par contrôle

- **Lieu du contrôle** : dérivé de la modalité. Les contrôles en ligne, sur
  pièces et sur audition se déroulent dans les locaux de la CNIL et y sont
  situés ; les contrôles sur place sont situés chez l'organisme.
- **Lieu de l'organisme** : la commune indiquée par la CNIL, précisée à
  l'adresse du siège ou d'un établissement quand elle a pu être établie et
  validée.

Aucune position n'est inventée : un point situé à la commune est rendu comme
tel.

## Arborescence

```
index.html  analyse.html  evolution.html  donnees.html   pages du site (à venir)
css/  js/                                                 interface, vanilla, sans build
vendor/                                                   MapLibre GL JS épinglé, modules ES (voir vendor/VERSIONS.md)
data/raw/                fichiers CNIL bruts, immuables, ajout seul
data/processed/          données normalisées, localisations, GeoJSON, statistiques
data/geocoding/          surcouche d'adresses validées, alias, corrections
data/referentiels-source/ référentiels externes versionnés (communes…)
data/metadata/           manifeste, schéma, rapport qualité, versions, journal
pipeline/                scripts Python (bibliothèque standard uniquement) et tests
outils/                  scripts d'usage ponctuel
.github/workflows/       actualisation des données, tests
```

`data/README.md` détaille les trois niveaux de données.

## Principes

1. Le fichier brut de la CNIL n'est jamais modifié.
2. Toute transformation est reproductible : même entrée, mêmes octets en
   sortie ; aucun horodatage dans les fichiers de données.
3. Le pipeline échoue explicitement quand la structure de la source change,
   plutôt que de produire une transformation douteuse.
4. Le site ne calcule rien qui ne soit reproductible hors navigateur.
5. Aucune dépendance à installer : Python 3 standard côté pipeline, HTML,
   CSS et JavaScript natifs côté site.

## Exécuter localement

```bash
python3 -m unittest discover -s pipeline/tests -t .
python3 -m http.server 8000
```

Le site se sert ensuite depuis http://localhost:8000/ (il lit
`data/processed/` par `fetch()`, donc un serveur local est nécessaire, pas
l'ouverture directe du fichier).

## Licences

- Code : MIT, voir `LICENSE`.
- Données source : CNIL, [Licence Ouverte / Open Licence 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence).
- Données transformées : Licence Ouverte 2.0, avec mention de la source CNIL
  et de ce dépôt.
- Fond de carte : © contributeurs [OpenStreetMap](https://www.openstreetmap.org/copyright).
