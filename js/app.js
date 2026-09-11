/* Point d'entrée : charge les données, construit la carte, remplit le panneau. */

import { Map as CarteMapLibre, NavigationControl, ScaleControl, AttributionControl, Popup } from "../vendor/maplibre-gl.mjs";
import { chargerDonnees, nombre, date } from "./donnees.js";
import { choisirStyle, ATTRIBUTION } from "./carte/fond.js";
import { definitionSource, ID_SOURCE } from "./carte/source.js";
import { ajouterCouchePoints, actualiserCouleurs, couleursFamilles, gererClusters, ID_POINTS } from "./carte/couches.js";
import { contenuPopup } from "./carte/popup.js";

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

function remplirLegende(d, couleurs) {
  const ul = $("legende-familles");
  ul.innerHTML = d.familles
    .filter((f) => d.stats.par_famille[f.code])
    .map((f) => `<li class="legende__item" style="--couleur:${couleurs[f.code]}">
      <span class="legende__pastille" aria-hidden="true"></span>
      <span class="legende__nom">${f.libelle}</span>
      <span class="legende__n num">${nombre(d.stats.par_famille[f.code])}</span>
    </li>`).join("");
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

async function demarrer() {
  installerPanneauMobile();
  let d;
  try {
    d = await chargerDonnees();
  } catch (erreur) {
    message(`Les données n'ont pas pu être chargées (${erreur.message}).`, true);
    return;
  }
  const departements = {};
  try {
    const ref = await (await fetch("data/processed/referentiels/departements.json")).json();
    for (const dep of ref.departements) departements[dep.code] = dep.nom;
  } catch (_) { /* facultatif */ }

  let couleurs = couleursFamilles(d.familles);
  remplirCouverture(d);
  remplirLegende(d, couleurs);

  const { style, repli } = await choisirStyle();
  const map = new CarteMapLibre({
    container: "carte",
    style,
    ...VUE_FRANCE,
    minZoom: 3,
    maxZoom: 19,
    attributionControl: false,
    cooperativeGestures: matchMedia("(max-width: 767px)").matches,
  });
  map.addControl(new NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new ScaleControl({ unit: "metric" }), "bottom-right");
  map.addControl(new AttributionControl({ compact: true, customAttribution: ATTRIBUTION }), "bottom-right");
  if (repli) message("Fond de carte vectoriel indisponible : affichage des tuiles OpenStreetMap.", true);
  /* MapLibre ouvre l'attribution compacte au premier affichage ; on la referme,
     le bouton (i) reste disponible. */
  document.querySelector(".maplibregl-ctrl-attrib")?.removeAttribute("open");

  map.on("load", () => {
    map.addSource(ID_SOURCE, definitionSource(d.geojson, d.familles));
    ajouterCouchePoints(map, couleurs);
    const clusters = gererClusters(map, d.familles, () => couleurs);

    const popup = new Popup({ closeButton: true, maxWidth: "320px", offset: 10 });
    map.on("click", ID_POINTS, (e) => {
      const f = e.features[0];
      popup.setLngLat(f.geometry.coordinates).setHTML(contenuPopup(f.properties, d.libelles, d.familles, couleurs, departements)).addTo(map);
    });
    map.on("mouseenter", ID_POINTS, () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", ID_POINTS, () => { map.getCanvas().style.cursor = ""; });

    /* Le thème peut changer pendant la visite : les couleurs de famille sont relues. */
    const observateur = new MutationObserver(() => {
      couleurs = couleursFamilles(d.familles);
      actualiserCouleurs(map, couleurs);
      remplirLegende(d, couleurs);
      clusters.toutRedessiner();
    });
    observateur.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
      couleurs = couleursFamilles(d.familles);
      actualiserCouleurs(map, couleurs);
      remplirLegende(d, couleurs);
      clusters.toutRedessiner();
    });
  });

  map.on("error", (e) => {
    if (e?.error?.message) console.warn("MapLibre :", e.error.message);
  });
}

demarrer();
