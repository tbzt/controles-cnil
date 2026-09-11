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

État : les cinq scripts et le workflow GitHub Actions qui les enchaîne
sont en place. Deux scripts d'accompagnement : `report.py` (rapport des
changements, journal, `releases.json`) et `verification.py` (trace mensuelle
de vérification).

```bash
python3 pipeline/fetch.py              # récupère ce qui a changé
python3 pipeline/fetch.py --forcer     # retélécharge tout, sans dupliquer un contenu identique
python3 pipeline/fetch.py --hors-ligne # vérifie seulement que data/raw/ correspond au manifeste
python3 pipeline/transform.py          # data/raw/ → data/processed/controles.csv et .json
python3 pipeline/geocode.py            # controles.csv → data/processed/localisations.csv (hors ligne)
python3 pipeline/validate.py           # règles de qualité → data/metadata/quality-report.json ; code 1 si fatal
python3 pipeline/build.py              # → controles.geojson, stats.json, data/metadata/schema.json
python3 pipeline/report.py --avant HEAD   # ce qui a changé depuis le dernier commit (CHANGEMENT=oui|non)
python3 outils/importer-umap.py <export.umap> --adresse-inverse   # ponctuel : surcouche d'adresses depuis uMap
python3 outils/proposer-adresses.py    # ponctuel : sièges via l'annuaire des entreprises (score haut appliqué, moyen à valider)
python3 -m unittest discover -s pipeline/tests -t .
```

## Comment transform.py lit un fichier

1. Décodage : UTF-8 (avec ou sans BOM), sinon Windows-1252.
2. Séparateur point-virgule obligatoire ; en-têtes et valeurs sur plusieurs
   lignes acceptés (vrai parseur CSV) ; colonnes vides d'export Excel
   retirées ; lignes vides ignorées.
3. Chaque en-tête est normalisé (sans accents, minuscules, espaces réduites)
   et cherché dans `mappings/entetes.json`. Un en-tête inconnu arrête tout,
   avec la clé exacte à ajouter. L'ordre des colonnes n'a aucune importance.
4. Les libellés de fondement, de modalité et de pays passent par
   `mappings/fondements.json`, `modalites.json`, `pays.json` ; un libellé
   inconnu arrête tout. Le libellé source est toujours conservé dans une
   colonne `*_source`.
5. Une ligne dont seule la première colonne est remplie est une ligne de
   total : rejetée et listée dans `data/metadata/rejets.json`.
6. Identifiant : `annee-hash8-rang`, où le hachage SHA-1 porte sur le contenu
   source de la ligne et le rang distingue les lignes strictement identiques
   (contrôles multiples d'un même organisme, conservés).

Les drapeaux de la colonne `qualite` disent ce qui a été déduit ou corrigé :
`annee_source_absente`, `modalite_deduite_du_type`, `modalite_non_renseignee`,
`departement_corrige`, `departement_multiple`, `departement_a_preciser`,
`departement_vide`, `departement_invalide`, `pays_deduit`, `pays_vide`,
`organisme_vide`, `organisme_multiligne`, `ville_vide`, `secteur_vide`,
`ligne_dupliquee`.

`fetch.py` ne touche jamais à un fichier existant de `data/raw/` : une
ressource modifiée côté CNIL donne une version de plus dans le manifeste et
un fichier de plus, l'ancien restant en place.

## Comment geocode.py localise un contrôle

Deux localisations par ligne, voir `data/geocoding/README.md` pour les
tables. Le **lieu de l'organisme** est cherché dans l'ordre : alias écrit à
la main, référentiel des communes (département + nom normalisé ; pour les
départements ambigus 20 et 97, tous les départements possibles ; si le
département de la source contredit une ville unique en France, la ville
prime et la ligne reçoit `departement_contredit_par_ville`), surcouche
d'adresses validées, puis centroïde du département, du pays, ou rien. Le
**lieu du contrôle** dépend de la modalité : en ligne, sur pièces et sur
audition se déroulent au siège de la CNIL (précision `institution`) ; sur
place chez l'organisme ; modalité non renseignée (2014-2016) chez
l'organisme avec `lieu_controle_inconnu`.

Précisions possibles : `adresse`, `commune`, `departement`, `pays`,
`institution`, `aucune`. Coordonnées à 4 décimales pour une commune, 6 pour
une adresse. Le rapport `data/metadata/geocodage-rapport.json` compte tout
et liste les villes non résolues.

## Ce que vérifie validate.py

| Règle | Fatal si | Alerte si |
|---|---|---|
| manifeste | un fichier archivé manque dans `data/raw/` | une ressource a disparu de data.gouv.fr |
| structure_source | un fichier brut courant ne se lit pas avec les en-têtes connus | |
| couverture_annees | aucun fichier annuel | une année manque entre la première et la dernière |
| identifiants | doublon ou identifiant mal formé | |
| champs_obligatoires | année, organisme ou secteur vide sur plus de 1 % des lignes | vide sur quelques lignes |
| volume | moins de 100 ou plus de 1 000 contrôles dans une année | écart avec le total officiel CNIL (tableau « depuis 1990 ») |
| annees | année hors de [2014, année courante] | |
| enumerations | fondement, modalité, secteur ou famille hors des valeurs connues | |
| doublons | | lignes strictement identiques (conservées) |
| departements | | code hors référentiel après localisation |
| localisations | pas exactement une localisation par contrôle ; lieu « cnil » avec une modalité sur place | |
| coordonnees | hors bornes, (0, 0), ou point « France » hors de l'emprise de son territoire | |
| geocodage | moins de 95 % des contrôles en France à la commune ou à l'adresse | villes non résolues |
| coherence_temporelle | | RGPD avant 2018, Loi 78 après 2019, directive avant 2018 |
| surcouche | | adresse ou proposition dont l'identifiant n'existe plus |

Le rapport `data/metadata/quality-report.json` ne contient pas
d'horodatage : il ne change que si les constats changent. Le test
`pipeline/tests/test_idempotence.py` relance transformation, localisation et
validation et vérifie qu'aucun fichier produit ne bouge.
