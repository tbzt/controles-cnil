/* Pastille du siège de la CNIL.

   En mode « lieu du contrôle », les contrôles en ligne, sur pièces et sur
   audition ne sont pas clusterisés avec les autres : ils se sont tous
   déroulés au 3 place de Fontenoy, et un cluster de mille points posé sur un
   immeuble ne dirait rien de vrai. Une pastille fixe porte leur nombre et
   explique la convention. */

import { Marker, Popup } from "../../vendor/maplibre-gl.mjs";

export function creerPastilleCnil(map, lieu, surFiltrer) {
  const element = document.createElement("button");
  element.type = "button";
  element.className = "pastille-cnil";
  /* Ancrée à gauche et décalée : la pastille se lit à côté du point, sans
     recouvrir le cluster parisien qui partage la même position au zoom national. */
  const marqueur = new Marker({ element, anchor: "left", offset: [28, 0] }).setLngLat([lieu.lon, lieu.lat]);
  const popup = new Popup({ closeButton: true, maxWidth: "320px", offset: 24 });
  let n = 0;

  element.addEventListener("click", () => {
    popup.setLngLat([lieu.lon, lieu.lat]).setHTML(`<article class="fiche">
      <h3 class="fiche__organisme">${n.toLocaleString("fr-FR")} contrôles réalisés depuis la CNIL</h3>
      <p class="fiche__ligne">${lieu.nom}, ${lieu.adresse}</p>
      <p class="fiche__ligne">Contrôles en ligne, sur pièces et sur audition : ils se déroulent dans les locaux de la CNIL, pas chez l'organisme. Ils ne sont donc pas placés sur la carte dans ce mode.</p>
      <p class="fiche__ligne"><button type="button" class="lien" data-action="filtrer-cnil">Ne garder que ces contrôles</button></p>
    </article>`).addTo(map);
  });
  map.getContainer().addEventListener("click", (e) => {
    if (e.target.closest("[data-action='filtrer-cnil']")) { popup.remove(); surFiltrer?.(); }
  });

  return {
    montrer(nombre) {
      n = nombre;
      element.innerHTML = `<span class="pastille-cnil__n">${nombre.toLocaleString("fr-FR")}</span><span class="pastille-cnil__l">à la CNIL</span>`;
      element.setAttribute("aria-label", `${nombre} contrôles réalisés dans les locaux de la CNIL, détails`);
      element.hidden = nombre === 0;
      if (!marqueur._map) marqueur.addTo(map);
    },
    cacher() {
      popup.remove();
      if (marqueur._map) marqueur.remove();
    },
  };
}
