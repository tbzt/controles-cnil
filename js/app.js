/* Point d'entrée : charge les données, construit la carte, branche les filtres.

   Flux : état (hash de l'URL) → filtrer(contrôles) → un tableau filtré →
   la carte (setData, qui reclusterise), le compteur et les facettes. */

import { Map as CarteMapLibre, NavigationControl, ScaleControl, AttributionControl, Popup, LngLatBounds } from "../vendor/maplibre-gl.mjs";
import { chargerDonnees, baseDonnees, nombre, date } from "./donnees.js";
import { choisirStyle, ATTRIBUTION } from "./carte/fond.js";
import { definitionSource, ID_SOURCE } from "./carte/source.js";
import { ajouterCouchePoints, actualiserCouleurs, couleursFamilles, gererClusters, ID_POINTS } from "./carte/couches.js";
import { contenuPopup } from "./carte/popup.js";
import { lireHash, creerMagasin, estVide } from "./etat.js";
import { preparer, filtrer } from "./filtres.js";
import { creerPanneauFiltres } from "./vues/panneau-filtres.js";

const VUE_FRANCE = { center: [2.6, 46.6], zoom: 5.3 };

const $ = (id) => document.getElementById(id);

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

  /* Effectif par organisme (nom normalisé), pour le lien de la popup. */
  const nbParOrganisme = new Map();
  for (const f of features) nbParOrganisme.set(f.properties._on, (nbParOrganisme.get(f.properties._on) || 0) + 1);

  /* État et panneau. */
  let map = null;
  let selection = [];
  const recadrer = () => {
    if (!map || !selection.length) return;
    const bornes = new LngLatBounds();
    for (const f of selection) bornes.extend(f.geometry.coordinates);
    map.fitBounds(bornes, { padding: 60, maxZoom: 15, duration: 600 });
  };
  const magasin = creerMagasin(lireHash(annees), annees);
  const panneau = creerPanneauFiltres({
    magasin, features, annees, familles: d.familles, libelles: d.libelles,
    departements: ref.departements, regions: ref.regions, communes: d.stats.par_commune, couleurs,
    surRecadrer: recadrer,
  });

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
  selection = filtrer(features, magasin.etat);
  let organismePrecedent = magasin.etat.organisme;

  function appliquer(etat) {
    selection = filtrer(features, etat);
    panneau.rendre(etat, selection.length, features.length, estVide(etat, annees));
    if (map.getSource(ID_SOURCE)) {
      clusters?.toutRedessiner();
      map.getSource(ID_SOURCE).setData({ type: "FeatureCollection", features: selection });
    }
    /* Choisir un organisme recadre la carte sur ses contrôles. */
    if (etat.organisme && etat.organisme !== organismePrecedent) recadrer();
    organismePrecedent = etat.organisme;
  }
  magasin.abonner(appliquer);
  panneau.rendre(magasin.etat, selection.length, features.length, estVide(magasin.etat, annees));

  map.on("load", () => {
    map.addSource(ID_SOURCE, definitionSource({ type: "FeatureCollection", features: selection }, d.familles));
    ajouterCouchePoints(map, couleurs);
    clusters = gererClusters(map, d.familles, () => couleurs);

    const popup = new Popup({ closeButton: true, maxWidth: "320px", offset: 10 });
    map.on("click", ID_POINTS, (e) => {
      const f = e.features[0];
      popup.setLngLat(f.geometry.coordinates)
        .setHTML(contenuPopup(f.properties, d.libelles, d.familles, couleurs, nomsDepartements, nbParOrganisme.get(f.properties._on) || 1))
        .addTo(map);
    });
    /* Lien « voir les contrôles de cet organisme » dans la popup. */
    $("carte").addEventListener("click", (e) => {
      const bouton = e.target.closest("[data-organisme]");
      if (!bouton) return;
      popup.remove();
      magasin.modifier({ organisme: bouton.dataset.organisme, q: "" });
    });
    if (magasin.etat.organisme) recadrer();
    map.on("mouseenter", ID_POINTS, () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", ID_POINTS, () => { map.getCanvas().style.cursor = ""; });

    const rethemer = () => {
      couleurs = couleursFamilles(d.familles);
      actualiserCouleurs(map, couleurs);
      panneau.rendre(magasin.etat, selection.length, features.length, estVide(magasin.etat, annees));
      clusters.toutRedessiner();
    };
    new MutationObserver(rethemer).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", rethemer);
  });

  /* Le hash peut changer par navigation (bouton précédent) : on relit l'état.
     Et le navigateur restaure parfois le texte du champ de recherche après le
     premier rendu : on rend à nouveau à l'affichage de la page. */
  addEventListener("hashchange", () => magasin.modifier(lireHash(annees)));
  addEventListener("pageshow", () => panneau.rendre(magasin.etat, selection.length, features.length, estVide(magasin.etat, annees)));

  map.on("error", (e) => { if (e?.error?.message) console.warn("MapLibre :", e.error.message); });
}

demarrer();
