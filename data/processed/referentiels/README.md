# Référentiels

| Fichier | Contenu | Origine | Mise à jour |
|---|---|---|---|
| `secteurs.csv` | les 43 libellés de secteur écrits par la CNIL entre 2014 et 2023 → secteur fin harmonisé → famille | établi à la main | à compléter quand `transform.py` signale un libellé inconnu |
| `familles.json` | les 16 familles comparables sur 2014-2023, leur libellé et leur ordre d'affichage | décision éditoriale du 11 septembre 2026 | rarement |
| `departements.json` | 101 départements : code, nom, région | geo.api.gouv.fr, extrait du 11 septembre 2026 | rarement |
| `regions.json` | 18 régions : code, nom | geo.api.gouv.fr, extrait du 11 septembre 2026 | rarement |
| `organismes-alias.csv` | variante de nom normalisé → clé de rapprochement, avec la raison (intitulé de ministère, filiale, ancien nom, graphie) ; s'ajoute aux règles automatiques de `transform.py` (formes juridiques et suffixes de domaine retirés) | à la main, quand la liste des organismes récurrents montre un doublon |

Le référentiel des communes (35 014 lignes, 2,6 Mo) est dans
`data/referentiels-source/communes.json` et se régénère avec
`python3 outils/extraire-communes.py`.

## Pourquoi deux niveaux de secteur

La CNIL a changé de nomenclature en 2018 : « Santé/social » est devenu
« Santé » et « Social », « Police/justice/sécurité » est devenu « Régalien »,
« Education/culture/sport » a été éclaté. Le **secteur fin** conserve la
finesse publiée (donc n'est comparable qu'à partir de 2018 pour les secteurs
éclatés) ; la **famille** regroupe à un niveau stable sur toute la période.
Les libellés fins issus de l'ancienne nomenclature sont suffixés
« (nomenclature 2014-2018) » pour que la rupture reste visible.

Choix discutables, assumés : Tourisme est rangé dans Commerce ; Jeux dans
Éducation, culture et sport ; Nouvelles technologies dans
Télécommunications ; Statistiques et enquêtes publiques et Finances
publiques dans État et régalien ; Économie et Cookies dans Commerce ;
Particulier et les trois lignes sans secteur dans Autres.

Les contours départementaux simplifiés utilisés par la vue Évolution sont
dans `data/referentiels-source/contours-departements.geojson` (source :
gregoiredavid/france-geojson, données OpenStreetMap sous ODbL, métropole et
Corse) ; ceux des cinq départements d'outre-mer, pour les encarts de la
carte, dans `contours-outre-mer.geojson`, même source. `departements.json` porte aussi la population de chaque département,
somme des populations communales du référentiel.
