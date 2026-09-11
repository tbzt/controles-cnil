# Données

Trois niveaux, du brut au publié.

| Dossier | Contenu | Modifié par |
|---|---|---|
| `raw/` | Fichiers tels que téléchargés depuis data.gouv.fr, une version par empreinte SHA-256, jamais modifiés ni supprimés | `pipeline/fetch.py` uniquement |
| `processed/` | Données normalisées (`controles.csv`, `controles.json`), localisations (`localisations.csv`), GeoJSON, statistiques précalculées, référentiels | le pipeline uniquement |
| `geocoding/` | Surcouche d'adresses validées, propositions automatiques en attente, alias de villes, corrections de départements | à la main et par `outils/` |
| `referentiels-source/` | Référentiels externes versionnés et datés (communes de geo.api.gouv.fr) | à la main, une fois par an |
| `metadata/` | Manifeste des ressources, schéma des tables, rapport qualité, liste des versions, journal des changements | le pipeline |

Le schéma des tables publiées sera décrit dans `metadata/schema.json` au
format Table Schema.
