# Géocodage : tables éditées à la main

Ces fichiers sont les seuls endroits où une position géographique est
décidée par un humain. `pipeline/geocode.py` les lit ; il n'appelle jamais
le réseau.

| Fichier | Rôle | Qui l'édite |
|---|---|---|
| `alias-villes.csv` | ville telle qu'écrite par la CNIL → code INSEE (ou pays). Clé : `departement_source` + ville normalisée ; `*` en département vaut pour tous | à la main, quand `geocodage-rapport.json` liste une ville non résolue |
| `surcouche.csv` | adresse précise d'un organisme, par identifiant de contrôle ; seules les lignes `statut = valide` sont prises | à la main, ou par import de la carte uMap (étape 5) |
| `lieux-institution.json` | le siège de la CNIL, lieu des contrôles en ligne, sur pièces et sur audition | rarement |
| `pays-centroides.json` | un point par pays pour les organismes hors de France | quand un nouveau pays apparaît dans `pipeline/mappings/pays.json` |

## Colonnes de `alias-villes.csv`

- `departement_source`, `ville_source` : valeurs brutes de la CNIL (la ville
  est comparée après normalisation : accents, tirets, casse, SAINT → ST).
- `code_insee` : commune cible, vérifiée dans `communes.json`.
- `pays` : code ISO à la place d'un code INSEE quand la « ville » est en
  fait à l'étranger (« LONDRES », « SAN FRANCISCO (USA) » avant 2021).
- `precision` : `commune` en général ; `departement` quand la source désigne
  un territoire plus large qu'une commune (« Yvelines », « Sambre Avesnois »,
  « Ile-de-la-Réunion »), auquel cas le chef-lieu est retenu et le point
  reçoit le drapeau `localisation_approximative`.
- `commentaire` : pourquoi l'alias existe (commune fusionnée ou renommée,
  faute de frappe, quartier, aéroport, département erroné à la source).

## Colonnes de `surcouche.csv`

`id` (identifiant du contrôle), `adresse`, `lon`, `lat` (WGS84, 6 décimales),
`code_insee`, `precision` (`adresse`), `methode`, `source` (d'où vient
l'adresse), `statut` (`valide`, `a_verifier`, `impossible`), `commentaire`.

Méthodes : `umap_adresse` (adresse et point issus de la carte uMap),
`umap_coordonnees` (point uMap sans libellé), `umap_coordonnees+adresse_inverse`
(point uMap, libellé retrouvé par géocodage inverse BAN à l'import),
`siege_auto` (siège trouvé automatiquement dans l'annuaire des entreprises,
score haut), `manuel` (saisie à la main).

Seules les lignes `valide` sont appliquées par `geocode.py`. L'import uMap
marque `a_verifier` tout point situé à plus de 30 km de la commune indiquée
par la CNIL : le commentaire donne la distance et la commune. Pour valider
une telle ligne, passer son statut à `valide` et renseigner `code_insee`.

## Import depuis la carte uMap

```bash
python3 outils/importer-umap.py data/referentiels-source/umap-export-2026-09-11.umap --adresse-inverse
```

Rapport dans `data/metadata/import-umap-rapport.json` : objets écartés (au
siège de la CNIL), appariés, non appariés, contrôles restés sans adresse par
année. Une ligne validée à la main (source autre que la carte uMap) n'est
jamais écrasée par une relance de l'import.
