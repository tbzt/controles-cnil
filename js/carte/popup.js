/* Contenu de la popup d'un contrôle. */

import { majuscules } from "../donnees.js";

function echapper(texte) {
  return String(texte ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function contenuPopup(p, libelles, familles, couleurs, departements, nbMemeOrganisme = 1) {
  const famille = familles.find((f) => f.code === p.famille);
  const fondement = libelles.fondements[p.fondement] || p.fondement;
  const modalite = p.modalite === "non_renseignee" ? "modalité non publiée" : (libelles.modalites[p.modalite] || p.modalite).toLowerCase();
  const nomDepartement = departements?.[p.departement];
  const lieu = p.pays === "FR"
    ? `${echapper(p.commune)}${nomDepartement ? ` (${echapper(nomDepartement)})` : p.departement ? ` (${echapper(p.departement)})` : ""}`
    : `${echapper(p.commune || "")}${p.commune ? ", " : ""}${echapper(libelles.pays[p.pays] || p.pays)}`;
  const precision = libelles.precisions[p.precision] || p.precision;
  const aDistance = p.lieu_controle === "cnil";

  return `<article class="fiche">
    <h3 class="fiche__organisme">${echapper(majuscules(p.organisme))}</h3>
    <p class="fiche__ligne"><b class="num">${p.annee}</b> · ${echapper(fondement)} · ${echapper(modalite)}</p>
    <p class="fiche__famille" style="--couleur:${couleurs[p.famille] || couleurs.autres}">${echapper(famille?.libelle || p.famille)}</p>
    <p class="fiche__ligne">${lieu}</p>
    ${nbMemeOrganisme > 1 ? `<p class="fiche__ligne"><button type="button" class="lien" data-organisme="${echapper(p._on)}">Voir les ${nbMemeOrganisme} contrôles de cet organisme</button></p>` : ""}
    <p class="fiche__note">Organisme situé ${echapper(precision)}.${aDistance ? " Contrôle réalisé dans les locaux de la CNIL." : ""} <span class="fiche__id" title="Identifiant du contrôle dans les données">${echapper(p.id)}</span></p>
  </article>`;
}
