# Données publiées

Tout ce dossier est produit par le pipeline, jamais édité à la main. Le
schéma complet des tables est dans `../metadata/schema.json` (Data Package).

| Fichier | Contenu | Pour qui |
|---|---|---|
| `controles.csv`, `controles.json` | un contrôle par ligne : année, fondement, modalité, organisme, ville et département source, pays, secteur fin, famille, provenance, drapeaux de qualité ; valeurs brutes conservées dans les colonnes `*_source` | tableur, analyse, réutilisation |
| `localisations.csv` | pour chaque contrôle, le lieu de l'organisme et le lieu du contrôle, avec coordonnées WGS84, précision et méthode | SIG, réutilisation |
| `controles.geojson` | un point par contrôle localisé, au lieu de l'organisme, avec les propriétés de filtrage ; une Feature par ligne | le site, QGIS, uMap |
| `stats.json` | effectifs par année, famille, secteur, modalité, fondement, département, région, commune, pays, précision, lieu du contrôle ; croisements par année ; organismes récurrents ; couverture temporelle | le site, analyses rapides |
| `referentiels/` | secteurs, familles, départements, régions | tout le monde |

Conventions : CSV en UTF-8 sans BOM, séparateur virgule, fin de ligne LF ;
JSON en UTF-8 non échappé, clés triées ; coordonnées à 4 décimales pour une
commune, 6 pour une adresse.

Les trois contrôles sans aucune coordonnée (ville absente à la source) sont
dans les CSV mais pas dans le GeoJSON ; `stats.json` les compte
(`couverture.nb_controles` moins `couverture.nb_cartographies`).

Licence : Licence Ouverte / Open Licence 2.0. Mentionner « CNIL, Contrôles
réalisés par la CNIL (data.gouv.fr), normalisation et localisation par le
projet controles-cnil ».
