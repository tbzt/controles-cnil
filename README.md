# Contrôles CNIL

Carte et analyse des contrôles réalisés par la CNIL depuis 2014, à partir du
jeu de données ouvert [« Contrôles réalisés par la CNIL »](https://www.data.gouv.fr/datasets/controles-realises-par-la-cnil)
publié sur data.gouv.fr.

Application entièrement statique, hébergée sur GitHub Pages, sans base de
données ni serveur applicatif. Les données sont récupérées, normalisées,
localisées et vérifiées par un pipeline Python exécuté par GitHub Actions ;
elles sont versionnées dans ce dépôt et réutilisables sans le site.

## État du projet

Étape 15 sur 18. `pipeline/fetch.py` archive les onze fichiers CSV de la
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
coordonnées, cohérence temporelle…) et arrête tout sur un constat fatal ;
`pipeline/build.py` produit les fichiers lus par le site et par les
réutilisateurs (`controles.geojson`, `stats.json`) et le schéma des tables
(`data/metadata/schema.json`). Le workflow `.github/workflows/actualiser-donnees.yml`
enchaîne le tout chaque lundi et à la demande, ne commite que si les données
ont changé, tague chaque publication (`donnees-AAAA-MM-JJ`) et joint les
fichiers à une Release. Le site est en ligne sur
https://tbzt.github.io/controles-cnil/ : carte, clusters en anneau par
famille, points stylés selon leur précision, popup, bandeau de couverture,
et filtres combinables (période, familles et secteurs fins, fondement,
modalité, région, département, commune, recherche) avec compteur en temps
réel et état dans l'URL, suggestions d'organismes et de communes, filtre
« organisme exact » avec recadrage automatique de la carte, lien « voir les
contrôles de cet organisme » dans la popup, deux commutateurs sur la carte
(« Points / Communes » et « Organisme contrôlé / Lieu du contrôle »), un
encart « Hors de France », un onglet Analyse dont les graphiques suivent
les filtres et posent eux-mêmes des filtres au clic, et un onglet Évolution
(courbes, familles dans le temps, petits multiples cartographiques par
année, comparaison de deux périodes par choroplèthe divergent, lecture en
effectifs ou pour 100 000 habitants), et une page « Données et méthode »
(`donnees.html`) alimentée par les métadonnées du pipeline : source, dates,
transformations, limites de la localisation, constats de qualité,
téléchargements, versions. La finition (étape 16) reste à faire.

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
tel. Sur la carte, le commutateur « Organisme contrôlé / Lieu du contrôle »
choisit lequel des deux lieux est dessiné ; en mode « Lieu du contrôle », les
contrôles à distance sortent du clustering et forment une pastille fixe sur le
siège de la CNIL avec leur nombre, cliquable. Le commutateur « Points /
Communes » remplace les points par un cercle par commune, d'aire
proportionnelle au nombre de contrôles et de la couleur de la famille
dominante : c'est le mode honnête quand la précision est la commune.

## Arborescence

```
index.html                                                l'application : carte, analyse, évolution (onglets)
donnees.html                                              sources, licence, méthode, limites, téléchargements, versions
css/  js/                                                 interface, vanilla, sans build
vendor/                                                   MapLibre GL JS épinglé, modules ES (voir vendor/VERSIONS.md)
data/raw/                fichiers CNIL bruts, immuables, ajout seul
data/processed/          données normalisées, localisations, GeoJSON, statistiques
data/geocoding/          surcouche d'adresses validées, alias, corrections
data/referentiels-source/ référentiels externes versionnés (communes, contours départementaux)
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

## Actualisation automatique

Le workflow « Actualiser les données » tourne chaque lundi à 06:00 UTC et se
lance aussi à la main depuis l'onglet Actions (case « forcer » pour tout
retélécharger). Il exécute les cinq scripts puis les tests, écrit un rapport
des changements dans le résumé du job, et :

- si les données ont changé : commit « Données : date — résumé », tag
  `donnees-AAAA-MM-JJ`, Release avec les CSV, le GeoJSON, les statistiques et
  le schéma, entrée dans `data/metadata/CHANGELOG-DATA.md` et `releases.json` ;
- sinon : rien, sauf une trace mensuelle dans
  `data/metadata/derniere-verification.json` (un commit par mois au plus,
  pour que GitHub ne désactive pas le planning et pour afficher la date de
  dernière vérification) ;
- en cas de constat fatal de la validation ou de test en échec : le job
  échoue, rien n'est commité, le site continue de servir la version
  précédente.

Chaque tag est un instantané complet : `git checkout donnees-2026-09-11`
reproduit les données et le site de cette date.

## Exécuter localement

```bash
python3 -m unittest discover -s pipeline/tests -t .
python3 -m http.server 8000
```

Le site se sert ensuite depuis http://localhost:8000/ (il lit
`data/processed/` par `fetch()`, donc un serveur local est nécessaire, pas
l'ouverture directe du fichier).

## Comment le site est construit

Aucun build : HTML, CSS et modules ES natifs, MapLibre GL JS vendorisé.

- `css/tokens.css` est la seule source des couleurs (dont les seize couleurs
  de famille, lues aussi par le JavaScript), des tailles et des rythmes ;
  `base.css`, `composants.css` et `carte.css` ne contiennent aucune valeur
  brute. Thème clair et sombre ; mouvement annulé si l'utilisateur le demande.
- `js/donnees.js` charge `data/processed/` ; avec `?version=donnees-AAAA-MM-JJ`
  il lit la même arborescence à ce tag, servie par raw.githubusercontent.com.
- `js/carte/fond.js` : style vectoriel OpenFreeMap « positron », repli sur les
  tuiles raster OpenStreetMap si le style ne répond pas. Le thème sombre
  inverse le fond clair plutôt que de charger un second style.
- `js/carte/source.js` : un GeoJSON, clustering natif avec sous-totaux par
  famille. C'est le seul module à changer pour passer à PMTiles.
- `js/carte/couches.js` : points (couleur de famille, contour selon la
  précision) et clusters en anneau (un SVG par cluster, arcs proportionnels
  aux familles, taille en racine du total).
- `js/etat.js` : l'état des filtres, sérialisé dans le hash de l'URL
  (`#annees=2019-2023&famille=sante_social&modalite=en_ligne&region=11&q=carrefour`),
  et un magasin minimal auquel les vues s'abonnent.
- `js/filtres.js` : fonctions pures ; `filtrer(contrôles, état)` et les
  effectifs de chaque facette sous les autres filtres. Tout se recalcule à
  chaque changement, sans index : quelques millisecondes pour 3 600 lignes.
- `js/vues/panneau-filtres.js` : les contrôles du panneau (double curseur,
  familles cliquables, secteurs fins, puces, sélecteurs en cascade,
  recherche avec suggestions au clavier et à la souris). La carte reçoit le
  tableau filtré par `setData`, ce qui reclusterise ; les compteurs et les
  facettes se mettent à jour en même temps. Deux filtres textuels
  distincts : `q`, recherche libre où tous les mots doivent apparaître, et
  `organisme`, nom exact normalisé posé par une suggestion ou depuis une
  popup, qui recadre la carte sur ses contrôles.
- `js/carte/communes.js` : agrégation de la sélection par commune (point
  moyen des contrôles, famille dominante) et couches de cercles ;
  `js/carte/cnil.js` : la pastille du siège de la CNIL ;
  `js/vues/barre-outils.js` : les deux commutateurs ;
  `js/vues/encart-etranger.js` : les organismes étrangers par pays.
- `js/graphiques/svg.js` : quatre primitives SVG sans bibliothèque (barres
  verticales, horizontales, empilées, légende) ; `js/vues/analyse.js` : la
  vue Analyse, recalculée depuis la sélection à chaque changement d'état,
  avec la rupture de nomenclature 2018 dessinée sur les graphiques par
  famille. Les vues sont des onglets d'une seule page (`#vue=analyse`),
  pour partager les filtres et l'URL.
- `js/graphiques/carte-svg.js` : choroplèthes par département en SVG
  (contours simplifiés projetés une fois, échelles séquentielle et
  divergente en racine) ; `js/vues/evolution.js` : la vue Évolution. Pas
  d'animation : la source n'a que l'année, donc petits multiples (une carte
  par année, même échelle) et comparaison de deux périodes en moyenne
  annuelle. La période du panneau sert de période B.
- `js/carte/popup.js`, `js/app.js` : fiche d'un contrôle, bandeau de
  couverture, panneau repliable sur mobile, branchement de l'état.
- `donnees.html`, `js/page-donnees.js`, `css/page.css` : la page Données,
  dont chaque date et chaque chiffre vient de `data/metadata/` (manifeste,
  rapport qualité, rapport de géocodage, versions, dernière vérification)
  pour qu'elle ne puisse pas se désynchroniser des données.

## Licences

- Code : MIT, voir `LICENSE`.
- Données source : CNIL, [Licence Ouverte / Open Licence 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence).
- Données transformées : Licence Ouverte 2.0, avec mention de la source CNIL
  et de ce dépôt.
- Fond de carte : © contributeurs [OpenStreetMap](https://www.openstreetmap.org/copyright).
