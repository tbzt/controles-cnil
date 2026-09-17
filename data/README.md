# Données

Trois niveaux, du brut au publié.

| Dossier | Contenu | Modifié par |
|---|---|---|
| `raw/` | Fichiers tels que téléchargés depuis data.gouv.fr, une version par empreinte SHA-256, jamais modifiés ni supprimés ; `raw/dpo/` archive chaque publication mensuelle du jeu DPO | `pipeline/fetch.py` uniquement |
| `processed/` | Données normalisées (`controles.csv`, `controles.json`), localisations (`localisations.csv`), GeoJSON, statistiques précalculées, référentiels ; `processed/dpo/` : organismes ayant désigné un DPO sans colonne de contact, agrégats, flux entre publications | le pipeline uniquement |
| `geocoding/` | Surcouche d'adresses validées, propositions automatiques en attente, alias de villes, corrections de départements | à la main et par `outils/` |
| `referentiels-source/` | Référentiels externes versionnés et datés (communes de geo.api.gouv.fr, contours, agrégat SIRENE des sièges par commune et section NAF) | à la main une fois par an ; SIRENE par le workflow trimestriel |
| `metadata/` | Manifeste des ressources, schéma des tables, rapport qualité, liste des versions, journal des changements | le pipeline |

Le schéma des tables publiées sera décrit dans `metadata/schema.json` au
format Table Schema.
