/* Point d'entrée : charge les données, construit la carte, branche les filtres.

   Flux : état (hash de l'URL) → filtrer(contrôles) → un tableau filtré →
   la carte (setData, qui reclusterise), le compteur, les facettes, l'encart
   hors de France. Deux réglages d'affichage viennent s'ajouter aux filtres :
   le mode (points ou communes) et le lieu cartographié (organisme ou lieu du
   contrôle). */

import { Map as CarteMapLibre, NavigationControl, ScaleControl, AttributionControl, Popup, LngLatBounds } from "../vendor/maplibre-gl.mjs";
import { chargerDonnees, baseDonnees, nombre, date } from "./donnees.js";
import { choisirStyle, ATTRIBUTION } from "./carte/fond.js";
import { definitionSource, ID_SOURCE } from "./carte/source.js";
import { ajouterCouchePoints, actualiserCouleurs, couleursFamilles, gererClusters, ID_POINTS } from "./carte/couches.js";
import { agregerCommunes, ajouterCouchesCommunes, afficherCommunes, actualiserCouleursCommunes, ID_SOURCE_COMMUNES, ID_CERCLES } from "./carte/communes.js";
import { creerPastilleCnil } from "./carte/cnil.js";
import { contenuPopup } from "./carte/popup.js";
import { lireHash, creerMagasin, estVide } from "./etat.js";
import { preparer, filtrer } from "./filtres.js";
import { creerPanneauFiltres } from "./vues/panneau-filtres.js";
import { creerBarreOutils } from "./vues/barre-outils.js";
import { creerEncartEtranger } from "./vues/encart-etranger.js";
import { creerVueAnalyse } from "./vues/analyse.js";

const VUE_FRANCE = { center: [2.6, 46.6], zoom: 5.3 };
const MODALITES_CNIL = ["en_ligne", "sur_pieces", "sur_audition"];

const $ = (id) => document.getElementById(id);

function echapper(texte) {
  return String(texte ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function message(texte, alerte = false) {
  const el = $("message");
  el.textContent = texte;
  el.classList.toggle("message--alerte", alerte);
  el.hidden = !texte;
}

function remplirCouverture(d) {
  const c = d.stats.couverture;
  const morceaux = [
    `<span><b class="num">${c.annee_min}</b> → <b class="num">${c.annee_max}</b></span>`,
    `<span><b class="num">${nombre(c.nb_controles)}</b> contrôles</span>`,
    `<span>dernière publication CNIL : <b>${date(c.derniere_publication_source)}</b></span>`,
  ];
  if (d.verification?.derniere_verification) {
    morceaux.push(`<span>vérifié le <b>${date(d.verification.derniere_verification)}</b></span>`);
  }
  if (d.version) morceaux.push(`<span class="discret">version archivée</span>`);
  $("couverture").innerHTML = morceaux.join("");
}

function installerPanneauMobile() {
  const panneau = $("panneau");
  const bouton = $("bouton-replier");
  const basculer = (replie) => {
    panneau.dataset.replie = String(replie);
    bouton.setAttribute("aria-expanded", String(!replie));
    bouton.setAttribute("aria-label", replie ? "Déplier le panneau" : "Replier le panneau");
  };
  bouton.addEventListener("click", () => basculer(panneau.dataset.replie !== "true"));
  if (matchMedia("(max-width: 767px)").matches) basculer(true);
}

async function lireReferentiels() {
  const base = baseDonnees();
  const [dep, reg] = await Promise.all([
    fetch(base + "processed/referentiels/departements.json").then((r) => r.json()),
    fetch(base + "processed/referentiels/regions.json").then((r) => r.json()),
  ]);
  return { departements: dep.departements, regions: reg.regions };
}

function popupCommune(p, familles, couleurs) {
  const repartition = Object.entries(JSON.parse(p.familles)).sort((a, b) => b[1] - a[1]).slice(0, 6);
  const lib = Object.fromEntries(familles.map((f) => [f.code, f.libelle]));
  return `<article class="fiche">
    <h3 class="fiche__organisme">${echapper(p.commune)} <span class="discret">(${echapper(p.departement)})</span></h3>
    <p class="fiche__ligne"><b class="num">${nombre(p.n)}</b> contrôle${p.n > 1 ? "s" : ""} dans la sélection</p>
    <ul class="fiche__repartition">${repartition.map(([code, n]) => `<li><span class="fiche__famille" style="--couleur:${couleurs[code] || couleurs.autres}">${echapper(lib[code] || code)}</span><span class="num">${nombre(n)}</span></li>`).join("")}</ul>
    <p class="fiche__ligne"><button type="button" class="lien" data-commune="${p.code_insee}" data-departement="${p.departement}">Ne garder que cette commune</button></p>
  </article>`;
}

async function demarrer() {
  installerPanneauMobile();
  let d, ref;
  try {
    [d, ref] = await Promise.all([chargerDonnees(), lireReferentiels()]);
  } catch (erreur) {
    message(`Les données n'ont pas pu être chargées (${erreur.message}).`, true);
    return;
  }
  const nomsDepartements = Object.fromEntries(ref.departements.map((x) => [x.code, x.nom]));
  const annees = d.stats.couverture.annees;
  const features = preparer(d.geojson.features);
  let couleurs = couleursFamilles(d.familles);
  remplirCouverture(d);

  const nbParOrganisme = new Map();
  for (const f of features) nbParOrganisme.set(f.properties._on, (nbParOrganisme.get(f.properties._on) || 0) + 1);

  /* État, panneau, barre d'outils, encart. */
  let map = null;
  let selection = [];        /* les contrôles retenus par les filtres */
  let selectionCarte = [];   /* ceux qui vont sur la carte (hors pastille CNIL) */
  const recadrer = () => {
    if (!map || !selectionCarte.length) return;
    const bornes = new LngLatBounds();
    for (const f of selectionCarte) bornes.extend(f.geometry.coordinates);
    map.fitBounds(bornes, { padding: 60, maxZoom: 15, duration: 600 });
  };
  const magasin = creerMagasin(lireHash(annees), annees);
  const panneau = creerPanneauFiltres({
    magasin, features, annees, familles: d.familles, libelles: d.libelles,
    departements: ref.departements, regions: ref.regions, communes: d.stats.par_commune, couleurs,
    surRecadrer: recadrer,
  });
  const barre = creerBarreOutils(magasin);
  const encart = creerEncartEtranger(d.libelles);
  const analyse = creerVueAnalyse({ features, annees, familles: d.familles, libelles: d.libelles, magasin, obtenirCouleurs: () => couleurs });
  $("onglets").addEventListener("click", (e) => {
    const b = e.target.closest("[data-vue]");
    if (b && !b.disabled) magasin.modifier({ vue: b.dataset.vue });
  });
  let vuePrecedente = null;
  function afficherVue(etat) {
    for (const b of $("onglets").querySelectorAll("[data-vue]")) b.setAttribute("aria-selected", String(b.dataset.vue === etat.vue));
    $("vue-carte").hidden = etat.vue !== "carte";
    $("vue-analyse").hidden = etat.vue !== "analyse";
    if (etat.vue === "analyse") analyse.rendre(selection, etat, estVide(etat, annees));
    if (etat.vue === "carte" && vuePrecedente !== "carte") map?.resize();
    vuePrecedente = etat.vue;
  }

  /* Carte. */
  const { style, repli } = await choisirStyle();
  map = new CarteMapLibre({
    container: "carte", style, ...VUE_FRANCE, minZoom: 3, maxZoom: 19,
    attributionControl: false, cooperativeGestures: matchMedia("(max-width: 767px)").matches,
  });
  map.addControl(new NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new ScaleControl({ unit: "metric" }), "bottom-right");
  map.addControl(new AttributionControl({ compact: true, customAttribution: ATTRIBUTION }), "bottom-right");
  if (repli) message("Fond de carte vectoriel indisponible : affichage des tuiles OpenStreetMap.", true);
  document.querySelector(".maplibregl-ctrl-attrib")?.removeAttribute("open");

  let clusters = null;
  let pastille = null;
  let organismePrecedent = magasin.etat.organisme;

  function rendrePanneau(etat) {
    panneau.rendre(etat, selection.length, features.length, estVide(etat, annees));
    barre.rendre(etat);
    encart.rendre(selection);
    afficherVue(etat);
    $("section-precision").hidden = etat.mode !== "points";
    $("section-communes").hidden = etat.mode !== "communes";
    $("note-lieu").textContent = etat.lieu === "controle"
      ? "Les contrôles à distance (en ligne, sur pièces, sur audition) sont regroupés sur le siège de la CNIL, où ils se déroulent ; seuls les contrôles sur place sont placés chez l'organisme."
      : "Les points sont situés chez l'organisme contrôlé. Les contrôles en ligne, sur pièces et sur audition se déroulent dans les locaux de la CNIL ; la popup le précise.";
  }

  function appliquer(etat) {
    selection = filtrer(features, etat);
    const aDistance = etat.lieu === "controle" ? selection.filter((f) => f.properties.lieu_controle === "cnil") : [];
    selectionCarte = etat.lieu === "controle" ? selection.filter((f) => f.properties.lieu_controle !== "cnil") : selection;
    rendrePanneau(etat);
    if (!map.getSource(ID_SOURCE)) return;

    const modePoints = etat.mode === "points";
    clusters.activer(modePoints);
    map.setLayoutProperty(ID_POINTS, "visibility", modePoints ? "visible" : "none");
    afficherCommunes(map, !modePoints);
    if (modePoints) {
      clusters.toutRedessiner();
      map.getSource(ID_SOURCE).setData({ type: "FeatureCollection", features: selectionCarte });
    } else {
      map.getSource(ID_SOURCE_COMMUNES).setData(agregerCommunes(selectionCarte, d.familles));
    }
    if (etat.lieu === "controle") pastille.montrer(aDistance.length); else pastille.cacher();

    if (etat.organisme && etat.organisme !== organismePrecedent) recadrer();
    organismePrecedent = etat.organisme;
  }
  magasin.abonner(appliquer);
  selection = filtrer(features, magasin.etat);
  selectionCarte = selection;
  rendrePanneau(magasin.etat);

  map.on("load", () => {
    map.addSource(ID_SOURCE, definitionSource({ type: "FeatureCollection", features: [] }, d.familles));
    ajouterCouchePoints(map, couleurs);
    ajouterCouchesCommunes(map, couleurs);
    clusters = gererClusters(map, d.familles, () => couleurs);
    pastille = creerPastilleCnil(map, d.stats.lieux.cnil, () => magasin.modifier({ modalite: new Set(MODALITES_CNIL) }));
    appliquer(magasin.etat);

    const popup = new Popup({ closeButton: true, maxWidth: "320px", offset: 10 });
    map.on("click", ID_POINTS, (e) => {
      const f = e.features[0];
      popup.setLngLat(f.geometry.coordinates)
        .setHTML(contenuPopup(f.properties, d.libelles, d.familles, couleurs, nomsDepartements, nbParOrganisme.get(f.properties._on) || 1))
        .addTo(map);
    });
    map.on("click", ID_CERCLES, (e) => {
      const f = e.features[0];
      popup.setLngLat(f.geometry.coordinates).setHTML(popupCommune(f.properties, d.familles, couleurs)).addTo(map);
    });
    for (const id of [ID_POINTS, ID_CERCLES]) {
      map.on("mouseenter", id, () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", id, () => { map.getCanvas().style.cursor = ""; });
    }
    /* Liens des popups : organisme, commune. */
    $("carte").addEventListener("click", (e) => {
      const org = e.target.closest("[data-organisme]");
      const com = e.target.closest("[data-commune]");
      if (org) { popup.remove(); magasin.modifier({ organisme: org.dataset.organisme, q: "" }); }
      if (com) { popup.remove(); magasin.modifier({ departement: com.dataset.departement, commune: com.dataset.commune, region: "" }); }
    });
    if (magasin.etat.organisme) recadrer();

    const rethemer = () => {
      couleurs = couleursFamilles(d.familles);
      actualiserCouleurs(map, couleurs);
      actualiserCouleursCommunes(map, couleurs);
      rendrePanneau(magasin.etat);
      clusters.toutRedessiner();
    };
    new MutationObserver(rethemer).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", rethemer);
  });

  addEventListener("hashchange", () => magasin.modifier(lireHash(annees)));
  addEventListener("pageshow", () => rendrePanneau(magasin.etat));

  map.on("error", (e) => { if (e?.error?.message) console.warn("MapLibre :", e.error.message); });
}

demarrer();
