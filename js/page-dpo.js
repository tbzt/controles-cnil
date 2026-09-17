/* Page DPO : tout vient de deux agrégats produits par le pipeline
   (stats-dpo.json, dpo-communes.json) et des référentiels déjà servis pour
   les contrôles (contours départementaux, départements). Aucune ligne
   individuelle d'organisme n'est chargée par le navigateur.

   Trois lectures de la carte par département : pour 1 000 sièges de
   personnes morales (défaut, dénominateur SIRENE), pour 100 000 habitants,
   effectifs. Un sélecteur de section NAF et un commutateur interne/externe
   filtrent le numérateur ; le dénominateur SIRENE suit la section. */

import { Map as CarteMapLibre, NavigationControl, AttributionControl, Popup } from "../vendor/maplibre-gl.mjs";
import { barresHorizontales, barresEmpilees, barresMensuelles, legende, nombre, pourcentage } from "./graphiques/svg.js";
import { preparerContours, carteDepartements, echelleSequentielle, melanger } from "./graphiques/carte-svg.js";
import { choisirStyle, ATTRIBUTION } from "./carte/fond.js";
import { date } from "./donnees.js";

const $ = (id) => document.getElementById(id);
const MOUVEMENT_REDUIT = matchMedia("(prefers-reduced-motion: reduce)").matches;
const TYPES = [
  { code: "personne_physique", libelle: "DPO interne (personne physique)", couleur: "var(--serie-1)" },
  { code: "personne_morale", libelle: "DPO externe (personne morale)", couleur: "var(--serie-4)" },
];
const MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"];

function echapper(texte) {
  return String(texte ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function decimal(v, n = 1) {
  return Number(v).toFixed(n).replace(".", ",");
}

function moisLisible(cle) {
  const [a, m] = cle.split("-");
  return `${MOIS[Number(m) - 1]} ${a}`;
}

async function json(url) {
  const r = await fetch(url, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${url} : ${r.status}`);
  return r.json();
}

function couleursTokens() {
  const s = getComputedStyle(document.documentElement);
  const lire = (n) => s.getPropertyValue(n).trim();
  return { vide: lire("--surface-2"), plein: lire("--accent"), alerte: lire("--alerte"),
           cat: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => lire(`--cat-${i}`) || lire("--accent")), autre: lire("--fam-autres") };
}

function message(texte) {
  const el = $("message");
  el.textContent = texte;
  el.hidden = !texte;
}

/* Titre court d'une structure mutualisée (les raisons sociales sont longues). */
function court(nom, max = 44) {
  const n = String(nom);
  return n.length > max ? n.slice(0, max - 1).trimEnd() + "…" : n;
}

/* ------------------------------------------------------------ démarrage -- */

async function demarrer() {
  let stats, communes, contours, departements;
  try {
    [stats, communes, contours, departements] = await Promise.all([
      json("data/processed/dpo/stats-dpo.json"),
      json("data/processed/dpo/dpo-communes.json"),
      json("data/referentiels-source/contours-departements.geojson").then(preparerContours),
      json("data/processed/referentiels/departements.json").then((d) => d.departements),
    ]);
  } catch (erreur) {
    message(`Les données n'ont pas pu être chargées (${erreur.message}).`);
    return;
  }
  const c = stats.couverture;
  const sections = stats.libelles.sections;
  const nomsDept = Object.fromEntries(departements.map((d) => [d.code, d.nom]));
  const tok = couleursTokens();

  /* En-tête. */
  $("d-snapshot").textContent = date(c.snapshot);
  $("d-total").textContent = nombre(c.nb_designations);
  $("d-sirene").textContent = c.sirene ? `${date(c.sirene.date_stock)} · ${nombre(c.sirene.sieges_pm)} sièges de personnes morales` : "absent";
  $("d-snapshots").textContent = `${c.nb_snapshots} (depuis le ${date(c.snapshot)})`;
  $("l-sirene").textContent = c.sirene ? date(c.sirene.date_stock) : "(absent)";
  $("l-sans-siren").textContent = `${nombre(c.nb_sans_siren)} lignes, ${pourcentage(c.nb_sans_siren / c.nb_designations)}`;
  document.title = `Délégués à la protection des données · ${nombre(c.nb_designations)} désignations au ${date(c.snapshot)}`;

  /* Tuiles. */
  const externes = stats.par_type.personne_morale || 0;
  const tauxFrance = c.sirene ? (1000 * c.nb_france) / c.sirene.sieges_pm : null;
  const tuiles = [
    [nombre(c.nb_designations), "désignations en vigueur"],
    [nombre(c.nb_france), "organismes établis en France"],
    [tauxFrance == null ? "—" : decimal(tauxFrance), "pour 1 000 sièges de personnes morales"],
    [pourcentage(externes / c.nb_designations), "de DPO externes (personnes morales)"],
    [nombre(c.nb_structures_designees), "structures externes distinctes"],
    [pourcentage(c.nb_sans_siren / c.nb_designations), "de lignes sans SIREN"],
  ];
  $("tuiles").innerHTML = tuiles.map(([v, l]) => `<div class="tuile"><span class="tuile__valeur num">${v}</span><span class="tuile__libelle">${l}</span></div>`).join("");

  rendreTaux(stats, contours, nomsDept, tok);
  rendreCommunes(communes, stats, tok);
  rendreRythme(stats);
  rendreFlux(stats);
  rendreMutualisation(stats, contours, nomsDept, tok);
  rendreCouverture(stats, contours, tok);
  rendreInterneExterne(stats, sections);
  rendreSections(stats, sections);
  rendreEtranger(stats);

  const rethemer = () => {
    const t = couleursTokens();
    rendreTaux(stats, contours, nomsDept, t);
    rendreMutualisation(stats, contours, nomsDept, t);
    rendreCouverture(stats, contours, t);
  };
  new MutationObserver(rethemer).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", rethemer);
}

/* ----------------------------------------------------- taux par dept ----- */

let etatTaux = { section: "", type: "tous", lecture: "taux", departement: "" };

function valeurDept(d, etat) {
  /* Numérateur selon section et type ; dénominateur selon section. */
  let n, pm, sieges;
  if (etat.section) {
    const s = d.par_section[etat.section];
    n = s ? s.n : 0; pm = s ? s.personne_morale : 0; sieges = s ? s.sieges_pm : 0;
  } else {
    n = d.total; pm = d.personne_morale; sieges = d.sieges_pm;
  }
  const num = etat.type === "personne_morale" ? pm : etat.type === "personne_physique" ? n - pm : n;
  if (etat.lecture === "effectifs") return { valeur: num, num, sieges };
  if (etat.lecture === "population") return { valeur: d.population ? (num / d.population) * 100000 : 0, num, sieges };
  return { valeur: sieges ? (num / sieges) * 1000 : 0, num, sieges };
}

function formaterLecture(v, lecture) {
  if (lecture === "effectifs") return `${nombre(Math.round(v))} désignation${v > 1 ? "s" : ""}`;
  if (lecture === "population") return `${decimal(v)} pour 100 000 hab.`;
  return `${decimal(v)} pour 1 000 sièges`;
}

function rendreTaux(stats, contours, nomsDept, tok) {
  const sections = stats.libelles.sections;
  const select = $("c-section");
  if (!select.options.length) {
    select.innerHTML = `<option value="">Toutes les sections</option>` + Object.entries(sections).map(([k, v]) => `<option value="${k}">${k} · ${echapper(v)}</option>`).join("");
    select.addEventListener("change", () => { etatTaux.section = select.value; rendreTaux(stats, contours, nomsDept, couleursTokens()); });
    $("s-taux").addEventListener("click", (e) => {
      const t = e.target.closest("[data-type]");
      const l = e.target.closest("[data-lecture]");
      const d = e.target.closest("[data-departement]");
      if (t) etatTaux.type = t.dataset.type;
      if (l) etatTaux.lecture = l.dataset.lecture;
      if (d) etatTaux.departement = etatTaux.departement === d.dataset.departement ? "" : d.dataset.departement;
      if (t || l || d) rendreTaux(stats, contours, nomsDept, couleursTokens());
    });
  }
  for (const b of $("s-taux").querySelectorAll("[data-type]")) b.setAttribute("aria-pressed", String(b.dataset.type === etatTaux.type));
  for (const b of $("s-taux").querySelectorAll("[data-lecture]")) b.setAttribute("aria-pressed", String(b.dataset.lecture === etatTaux.lecture));
  const sansSirene = !stats.couverture.sirene;
  const boutonTaux = $("s-taux").querySelector('[data-lecture="taux"]');
  boutonTaux.disabled = sansSirene;
  if (sansSirene && etatTaux.lecture === "taux") etatTaux.lecture = "effectifs";

  const valeurs = {}, detail = {};
  for (const [code, d] of Object.entries(stats.departements)) {
    const r = valeurDept(d, etatTaux);
    valeurs[code] = r.valeur;
    detail[code] = r;
  }
  const metropole = Object.keys(contours.chemins);
  const max = Math.max(1e-9, ...metropole.map((c) => valeurs[c] || 0));
  const echelle = echelleSequentielle(max, tok.vide, tok.plein);
  const formater = (v, code) => `${formaterLecture(v, etatTaux.lecture)} (${nombre(detail[code]?.num || 0)} désignation${(detail[code]?.num || 0) > 1 ? "s" : ""})`;
  $("c-carte").innerHTML = carteDepartements({ contours, valeurs, couleur: echelle, formater, titre: "Taux de désignation par département" });
  if (etatTaux.departement) $("c-carte").querySelector(`[data-departement="${etatTaux.departement}"]`)?.classList.add("carte-svg__departement--actif");
  $("c-echelle").innerHTML = `<span>0</span><span class="echelle__barre" style="background:linear-gradient(90deg,${tok.vide},${tok.plein})"></span><span>${formaterLecture(max, etatTaux.lecture)}</span><span class="discret">· échelle en racine carrée</span>`;

  /* Détail : le département cliqué, sinon la France. */
  const sectionLib = etatTaux.section ? `${etatTaux.section} · ${sections[etatTaux.section]}` : "toutes sections";
  const code = etatTaux.departement;
  const d = code ? stats.departements[code] : null;
  if (!d) {
    const tries = Object.entries(valeurs).filter(([c]) => nomsDept[c]).sort((a, b) => b[1] - a[1]);
    const ligne = ([c, v]) => `<tr><td><button type="button" class="lien" data-departement="${c}">${echapper(nomsDept[c])}</button> <span class="discret">(${c})</span></td><td class="num">${formaterLecture(v, etatTaux.lecture)}</td></tr>`;
    $("c-detail").innerHTML = `<h3>France · ${echapper(sectionLib)}</h3>
      <p class="discret">Cliquer un département sur la carte ou dans la liste.</p>
      <p class="etiquette">Les plus hauts</p><table>${tries.slice(0, 5).map(ligne).join("")}</table>
      <p class="etiquette">Les plus bas</p><table>${tries.slice(-5).reverse().map(ligne).join("")}</table>`;
  } else {
    const r = detail[code];
    const parSection = Object.entries(d.par_section).sort((a, b) => b[1].n - a[1].n).slice(0, 6);
    $("c-detail").innerHTML = `<h3>${echapper(d.nom)} <span class="discret">(${code})</span></h3>
      <span class="grand num">${formaterLecture(r.valeur, etatTaux.lecture)}</span>
      <span class="discret">${echapper(sectionLib)} · ${nombre(r.num)} désignation${r.num > 1 ? "s" : ""}${r.sieges ? ` pour ${nombre(r.sieges)} sièges de personnes morales` : ""}</span>
      <table>
        <tr><td>Désignations, toutes sections</td><td class="num">${nombre(d.total)}</td></tr>
        <tr><td>dont DPO externes</td><td class="num">${nombre(d.personne_morale)} · ${pourcentage(d.personne_morale / (d.total || 1))}</td></tr>
        ${d.structure_dominante ? `<tr><td>Structure externe la plus désignée</td><td class="num">${echapper(court(d.structure_dominante.nom, 34))} · ${pourcentage(d.structure_dominante.part_externes)}</td></tr>` : ""}
        ${stats.couverture_communes[code] ? `<tr><td>Communes ayant déclaré</td><td class="num">${nombre(stats.couverture_communes[code].declarantes)} / ${nombre(stats.couverture_communes[code].communes)} · ${pourcentage(stats.couverture_communes[code].taux || 0)}</td></tr>` : ""}
      </table>
      <p class="etiquette">Sections les plus représentées</p>
      <table>${parSection.map(([s, v]) => `<tr><td>${s} · ${echapper(sections[s])}</td><td class="num">${nombre(v.n)}${v.taux != null ? ` <span class="discret">· ${decimal(v.taux)} ‰</span>` : ""}</td></tr>`).join("")}</table>
      <p><button type="button" class="lien" data-departement="${code}">Revenir à la France</button></p>`;
  }

  /* Tableau complet, outre-mer compris. */
  const lignes = Object.entries(stats.departements).sort((a, b) => (valeurs[b[0]] || 0) - (valeurs[a[0]] || 0));
  $("c-tableau").innerHTML = `<div class="tableau"><table>
    <thead><tr><th>Département</th><th>Désignations</th><th>dont externes</th><th>Sièges PM (SIRENE)</th><th>Lecture courante</th><th>Sur la carte</th></tr></thead>
    <tbody>${lignes.map(([code, d]) => `<tr><td><button type="button" class="lien" data-departement="${code}">${echapper(d.nom)}</button> <span class="discret">(${code})</span></td>
      <td class="num">${nombre(detail[code].num)}</td><td class="num">${nombre(etatTaux.section ? (d.par_section[etatTaux.section]?.personne_morale || 0) : d.personne_morale)}</td>
      <td class="num">${nombre(detail[code].sieges)}</td><td class="num">${formaterLecture(valeurs[code], etatTaux.lecture)}</td><td>${contours.chemins[code] ? "oui" : "non"}</td></tr>`).join("")}</tbody></table></div>`;
}

/* ----------------------------------------------------- communes (MapLibre) */

async function rendreCommunes(communes, stats, tok) {
  const champs = communes._champs;
  const features = communes.communes.map((l) => {
    const c = Object.fromEntries(champs.map((k, i) => [k, l[i]]));
    return { type: "Feature", geometry: { type: "Point", coordinates: [c.lon, c.lat] },
             properties: { code: c.code_insee, commune: c.commune, departement: c.departement, n: c.designations, pm: c.personne_morale,
                           sieges: c.sieges_pm, taux: c.sieges_pm ? (1000 * c.designations) / c.sieges_pm : null } };
  });
  const maxN = Math.max(1, ...features.map((f) => f.properties.n));
  /* Rayon en racine (aire proportionnelle), borné pour rester lisible. */
  const rayon = (n) => Math.max(2.5, Math.min(40, 2.5 + 32 * Math.sqrt(n / maxN)));
  const tauxRef = 60; /* ‰ : au-delà, couleur pleine ; la médiane des communes est bien plus basse */
  $("m-echelle").innerHTML = `<span>0 ‰</span><span class="echelle__barre" style="background:linear-gradient(90deg,${tok.vide},${tok.plein})"></span><span>${tauxRef} ‰ et plus</span><span class="discret">· gris : pas de siège SIRENE (dénominateur nul)</span>`;

  const { style, repli } = await choisirStyle();
  const map = new CarteMapLibre({ container: "m-carte", style, center: [2.6, 46.6], zoom: 5, minZoom: 4, maxZoom: 14, attributionControl: false, cooperativeGestures: true });
  map.addControl(new NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new AttributionControl({ compact: true, customAttribution: ATTRIBUTION.replace("controles-realises-par-la-cnil", "organismes-ayant-designe-un-e-delegue-e-a-la-protection-des-donnees-dpd-dpo") }), "bottom-right");
  if (repli) message("Fond de carte vectoriel indisponible : affichage des tuiles OpenStreetMap.");
  map.on("load", () => {
    map.addSource("communes", { type: "geojson", data: { type: "FeatureCollection", features } });
    map.addLayer({
      id: "communes-cercles", type: "circle", source: "communes",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, ["*", 0.5, ["case", ["has", "n"], ["min", 40, ["+", 2.5, ["*", 32, ["sqrt", ["/", ["get", "n"], maxN]]]]], 3]],
                          9, ["min", 60, ["+", 3, ["*", 48, ["sqrt", ["/", ["get", "n"], maxN]]]]]],
        "circle-color": ["case", ["==", ["get", "taux"], null], tok.autre,
                         ["interpolate", ["linear"], ["sqrt", ["min", tauxRef, ["get", "taux"]]], 0, tok.vide, Math.sqrt(tauxRef), tok.plein]],
        "circle-opacity": 0.78,
        "circle-stroke-color": getComputedStyle(document.documentElement).getPropertyValue("--point-contour").trim() || "#fff",
        "circle-stroke-width": 0.8,
      },
    });
    const popup = new Popup({ closeButton: true, maxWidth: "300px", offset: 8 });
    map.on("click", "communes-cercles", (e) => {
      const p = e.features[0].properties;
      popup.setLngLat(e.features[0].geometry.coordinates).setHTML(`<article class="fiche">
        <h3 class="fiche__organisme">${echapper(p.commune)} <span class="discret">(${echapper(p.departement)})</span></h3>
        <p class="fiche__ligne"><b class="num">${nombre(p.n)}</b> désignation${p.n > 1 ? "s" : ""}, dont <b class="num">${nombre(p.pm)}</b> DPO externe${p.pm > 1 ? "s" : ""}</p>
        <p class="fiche__ligne">${p.sieges ? `<b class="num">${decimal(p.taux)} ‰</b> des ${nombre(p.sieges)} sièges de personnes morales` : "aucun siège de personne morale dans le stock SIRENE"}</p>
      </article>`).addTo(map);
    });
    map.on("mouseenter", "communes-cercles", () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", "communes-cercles", () => { map.getCanvas().style.cursor = ""; });
    void rayon; void MOUVEMENT_REDUIT;
  });
  map.on("error", (e) => { if (e?.error?.message) console.warn("MapLibre :", e.error.message); });
}

/* ----------------------------------------------------- rythme ------------ */

let depuis = "2018-05";

function rendreRythme(stats) {
  if (!$("s-rythme").dataset.pret) {
    $("s-rythme").dataset.pret = "1";
    $("s-rythme").addEventListener("click", (e) => {
      const b = e.target.closest("[data-depuis]");
      if (!b) return;
      depuis = b.dataset.depuis;
      rendreRythme(stats);
    });
  }
  for (const b of $("s-rythme").querySelectorAll("[data-depuis]")) b.setAttribute("aria-pressed", String(b.dataset.depuis === depuis));
  const colonnes = stats.par_mois.filter((m) => m.mois >= depuis).map((m) => ({ cle: m.mois, libelle: moisLisible(m.mois), parts: { personne_physique: m.personne_physique, personne_morale: m.personne_morale } }));
  const total = colonnes.reduce((s, c) => s + c.parts.personne_physique + c.parts.personne_morale, 0);
  const moyenne = colonnes.length ? total / colonnes.length : 0;
  $("r-svg").innerHTML = barresMensuelles({ colonnes, categories: TYPES });
  $("r-legende").innerHTML = legende(TYPES) + `<p class="discret" style="font-size:var(--t-2)">${nombre(total)} désignations sur ${colonnes.length} mois, soit ${nombre(Math.round(moyenne))} par mois en moyenne ; le premier mois affiché commence le ${moisLisible(depuis)} et le dernier mois est incomplet.</p>`;
}

/* ----------------------------------------------------- flux -------------- */

function rendreFlux(stats) {
  const flux = stats.flux || [];
  if (!flux.length) {
    $("f-contenu").innerHTML = `<p class="discret">Une seule publication archivée pour l'instant (celle du ${date(stats.couverture.snapshot)}). Dès la suivante, cette section montrera combien de désignations sont apparues, ont disparu ou ont été remplacées entre les deux, ce que le fichier de la CNIL ne permet pas de savoir autrement.</p>`;
    return;
  }
  const colonnes = flux.map((f) => ({ cle: f.publication, libelle: date(f.publication), parts: { nouvelles: f.nouvelles, modifiees: f.modifiees } }));
  const categories = [{ code: "nouvelles", libelle: "Nouvelles", couleur: "var(--serie-1)" }, { code: "modifiees", libelle: "Remplacées", couleur: "var(--serie-3)" }];
  $("f-contenu").innerHTML = barresEmpilees({ colonnes, categories, dataCle: "publication", hauteur: 200 }) + legende(categories)
    + `<div class="tableau" style="margin-top:var(--e-3)"><table><thead><tr><th>De</th><th>À</th><th>Nouvelles</th><th>Retirées</th><th>Remplacées</th><th>Solde</th><th>Total</th></tr></thead>
       <tbody>${flux.map((f) => `<tr><td>${date(f.publication_precedente)}</td><td>${date(f.publication)}</td><td class="num">+${nombre(f.nouvelles)}</td><td class="num">−${nombre(f.retirees)}</td><td class="num">${nombre(f.modifiees)}</td><td class="num">${f.solde > 0 ? "+" : ""}${nombre(f.solde)}</td><td class="num">${nombre(f.total)}</td></tr>`).join("")}</tbody></table></div>`;
}

/* ----------------------------------------------------- mutualisation ----- */

function rendreMutualisation(stats, contours, nomsDept, tok) {
  const externes = stats.nb_externes;
  const dix = stats.structures[9];
  $("mu-note").textContent = `${pourcentage((stats.par_type.personne_morale || 0) / stats.couverture.nb_designations)} des DPO sont des personnes morales (cabinets, groupements, structures publiques mutualisées) : ${nombre(externes)} désignations pour ${nombre(stats.couverture.nb_structures_designees)} structures distinctes ; les dix premières en couvrent ${dix ? pourcentage(dix.part_cumulee) : "—"}.`;

  /* Carte : une couleur par structure dominante parmi les plus fréquentes. */
  const dominantes = {};
  for (const [code, d] of Object.entries(stats.departements)) if (d.structure_dominante) dominantes[code] = d.structure_dominante;
  const frequence = {};
  for (const s of Object.values(dominantes)) frequence[s.cle] = (frequence[s.cle] || 0) + 1;
  const principales = Object.entries(frequence).sort((a, b) => b[1] - a[1]).slice(0, tok.cat.length).map(([cle]) => cle);
  const couleurDe = (cle) => { const i = principales.indexOf(cle); return i >= 0 ? tok.cat[i] : tok.autre; };
  const libelleDe = {};
  for (const s of Object.values(dominantes)) libelleDe[s.cle] = s.nom;
  const valeurs = {};
  for (const code of Object.keys(contours.chemins)) valeurs[code] = dominantes[code] ? dominantes[code].cle : "";
  const couleur = (cle) => (cle ? couleurDe(cle) : tok.vide);
  const formater = (cle, code) => (cle ? `${court(libelleDe[cle], 60)} : ${nombre(dominantes[code].n)} désignations, ${pourcentage(dominantes[code].part_externes)} des DPO externes du département` : "aucun DPO externe");
  $("mu-carte").innerHTML = carteDepartements({ contours, valeurs, couleur, formater, titre: "Structure externe la plus désignée par département" });
  $("mu-legende").innerHTML = legende(principales.map((cle) => ({ code: cle, libelle: `${court(libelleDe[cle], 48)} (${frequence[cle]} dép.)`, couleur: couleurDe(cle) })).concat([{ code: "autre", libelle: "autre structure", couleur: tok.autre }]));

  /* Tableau des structures. */
  $("mu-tableau").innerHTML = `<div class="tableau"><table>
    <thead><tr><th>Structure désignée</th><th>Désignations</th><th>Part</th><th>Cumul</th><th>Section dominante</th><th>Dép.</th></tr></thead>
    <tbody>${stats.structures.map((s) => `<tr><td title="${echapper(s.nom)}">${echapper(court(s.nom, 46))}</td><td class="num">${nombre(s.n)}</td><td class="num">${pourcentage(s.part_externes)}</td><td class="num">${pourcentage(s.part_cumulee)}</td><td>${s.section_dominante ? `${s.section_dominante} · ${echapper(stats.libelles.sections[s.section_dominante] || "")}` : ""}</td><td class="num" title="${s.departements_principaux.map((c) => nomsDept[c] || c).join(", ")}">${nombre(s.nb_departements)}</td></tr>`).join("")}</tbody></table></div>
    <p class="discret" style="font-size:var(--t-2)">Les centres de gestion de la fonction publique territoriale sont comptés ensemble : leur nom est identique d'un département à l'autre.</p>`;
}

/* ----------------------------------------------------- couverture communes */

function rendreCouverture(stats, contours, tok) {
  const cc = stats.couverture_communes;
  const valeurs = {};
  for (const [code, v] of Object.entries(cc)) valeurs[code] = v.taux || 0;
  const couleur = (v) => melanger(tok.vide, tok.plein, v);
  const formater = (v, code) => cc[code] ? `${pourcentage(v)} : ${nombre(cc[code].declarantes)} communes sur ${nombre(cc[code].communes)}` : "—";
  $("cc-carte").innerHTML = carteDepartements({ contours, valeurs, couleur, formater, titre: "Part des communes ayant déclaré un DPO" });
  $("cc-echelle").innerHTML = `<span>0 %</span><span class="echelle__barre" style="background:linear-gradient(90deg,${tok.vide},${tok.plein})"></span><span>100 %</span>`;
  const total = Object.values(cc).reduce((a, v) => a + v.communes, 0), decl = Object.values(cc).reduce((a, v) => a + v.declarantes, 0);
  const tries = Object.entries(cc).filter(([, v]) => v.taux != null).sort((a, b) => b[1].taux - a[1].taux);
  $("cc-note").innerHTML = `${nombre(decl)} communes sur ${nombre(total)} (${pourcentage(decl / total)}). Les mieux couvertes : ${tries.slice(0, 3).map(([c, v]) => `${echapper(stats.departements[c]?.nom || c)} (${pourcentage(v.taux)})`).join(", ")} ; les moins : ${tries.slice(-3).reverse().map(([c, v]) => `${echapper(stats.departements[c]?.nom || c)} (${pourcentage(v.taux)})`).join(", ")}. Un DPO mutualisé désigné par un centre de gestion ou un syndicat numérique apparaît sous le nom de chaque commune : cette carte mesure la déclaration, pas la présence d'un DPO propre.`;
}

/* ----------------------------------------------------- interne / externe - */

function rendreInterneExterne(stats, sections) {
  const parSection = Object.entries(stats.par_section_type).sort((a, b) => (b[1].personne_physique || 0) + (b[1].personne_morale || 0) - (a[1].personne_physique || 0) - (a[1].personne_morale || 0));
  const colonnes = parSection.map(([s, v]) => ({ cle: s, libelle: s, parts: { personne_physique: v.personne_physique || 0, personne_morale: v.personne_morale || 0 } }));
  $("ie-svg").innerHTML = barresEmpilees({ colonnes, categories: TYPES, parts: true, dataCle: "section", hauteur: 220 });
  $("ie-legende").innerHTML = legende(TYPES) + `<p class="discret" style="font-size:var(--t-2)">De gauche à droite, les sections les plus représentées : ${parSection.slice(0, 5).map(([s]) => `${s} ${echapper(sections[s])}`).join(", ")}…</p>`;
  const annees = Object.entries(stats.par_annee).map(([a, v]) => ({ cle: a, libelle: a, parts: { personne_physique: v.personne_physique || 0, personne_morale: v.personne_morale || 0 } }));
  $("ie-annees-svg").innerHTML = barresEmpilees({ colonnes: annees, categories: TYPES, parts: true, hauteur: 200 });
}

/* ----------------------------------------------------- taux par section -- */

function rendreSections(stats, sections) {
  const items = Object.entries(stats.par_section).filter(([, v]) => v.taux != null && v.sieges_pm >= 100)
    .sort((a, b) => b[1].taux - a[1].taux)
    .map(([s, v]) => ({ cle: s, libelle: `${s} · ${court(sections[s], 26)}`, valeur: Math.round(v.taux * 10) / 10, couleur: "var(--accent)" }));
  if (!items.length) {
    $("se-svg").innerHTML = `<p class="discret">Taux non calculés : agrégat SIRENE absent.</p>`;
    return;
  }
  /* barresHorizontales affiche valeur et part ; ici la part n'a pas de sens, le total est omis. */
  $("se-svg").innerHTML = barresHorizontales({ items, total: 0, dataCle: "section", largeur: 720 })
    + `<p class="discret" style="font-size:var(--t-2)">Désignations pour 1 000 sièges de personnes morales de la section, France entière ; sections de moins de 100 sièges omises. L'administration publique (O) dépasse 500 ‰ : la désignation y est obligatoire, et un même DPO mutualisé compte pour chaque organisme qui le désigne.</p>`;
}

/* ----------------------------------------------------- hors de France ---- */

function rendreEtranger(stats) {
  const liste = stats.par_pays.filter((p) => p.pays !== "?");
  const sansPays = stats.par_pays.find((p) => p.pays === "?")?.n || 0;
  const total = liste.reduce((s, p) => s + p.n, 0);
  $("et-note").textContent = `${nombre(total)} organismes établis hors de France ont désigné un DPO auprès de la CNIL ; ${nombre(sansPays)} lignes n'ont pas de pays renseigné.`;
  const noms = new Intl.DisplayNames(["fr"], { type: "region" });
  const nom = (code) => { try { return noms.of(code); } catch (_) { return code; } };
  $("et-liste").innerHTML = `<div class="tableau"><table><tbody>${liste.slice(0, 20).map((p) => `<tr><td>${echapper(nom(p.pays))}</td><td class="num">${nombre(p.n)}</td></tr>`).join("")}${liste.length > 20 ? `<tr><td class="discret">${liste.length - 20} autres pays</td><td class="num">${nombre(liste.slice(20).reduce((s, p) => s + p.n, 0))}</td></tr>` : ""}</tbody></table></div>`;
}

demarrer();
