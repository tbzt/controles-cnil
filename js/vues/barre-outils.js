/* Barre d'outils de la carte : deux commutateurs, mode de rendu et lieu
   cartographié. Publie dans le magasin ; se met à jour depuis l'état. */

const $ = (id) => document.getElementById(id);

export function creerBarreOutils(magasin) {
  const conteneur = $("barre-outils");
  conteneur.innerHTML = `
    <div class="segments" role="group" aria-label="Rendu">
      <button type="button" class="segment" data-mode="points" aria-pressed="true">Points</button>
      <button type="button" class="segment" data-mode="communes" aria-pressed="false">Communes</button>
    </div>
    <div class="segments" role="group" aria-label="Lieu cartographié">
      <button type="button" class="segment" data-lieu="organisme" aria-pressed="true" title="Chaque contrôle est placé chez l'organisme contrôlé">Organisme contrôlé</button>
      <button type="button" class="segment" data-lieu="controle" aria-pressed="false" title="Les contrôles à distance sont regroupés au siège de la CNIL">Lieu du contrôle</button>
    </div>`;
  conteneur.addEventListener("click", (e) => {
    const b = e.target.closest(".segment");
    if (!b) return;
    if (b.dataset.mode) magasin.modifier({ mode: b.dataset.mode });
    if (b.dataset.lieu) magasin.modifier({ lieu: b.dataset.lieu });
  });
  return {
    rendre(etat) {
      for (const b of conteneur.querySelectorAll("[data-mode]")) b.setAttribute("aria-pressed", String(b.dataset.mode === etat.mode));
      for (const b of conteneur.querySelectorAll("[data-lieu]")) b.setAttribute("aria-pressed", String(b.dataset.lieu === etat.lieu));
    },
  };
}
