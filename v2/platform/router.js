/* Vindex V2 — ruter (History API).
 *
 * U Wave 1 postoji tacno jedan ekran, pa ruter namerno nema ni ugnjezdene rute
 * ni parametre ni cuvare. Ono sto ima je jedina stvar zbog koje ruter uopste
 * postoji ovako rano: da `/app-v2` i `/app-v2/predmeti` budu ISTA aplikacija,
 * da osvezavanje i deep link rade, i da izmena putanje ne izaziva ponovno
 * ucitavanje dokumenta.
 *
 * Ne pravi se ovde apstrakcija za rute koje jos ne postoje.
 */

export const KOREN = "/app-v2";

const ekrani = new Map();
let tekuci = null;      // { kljuc, ciklus }
let ciljKontejner = null;

/** @param {string} kljuc  @param {(el:HTMLElement)=>{ugasi:()=>void}} montiraj */
export function registruj(kljuc, montiraj) {
  ekrani.set(kljuc, montiraj);
}

function kljucIzPutanje(putanja) {
  const p = putanja.replace(/\/+$/, "") || KOREN;
  if (p === KOREN) return "predmeti";              // koren se razresava na Predmeti
  if (p === KOREN + "/predmeti") return "predmeti";
  return null;
}

export function putanjaZa(kljuc) {
  return kljuc === "predmeti" ? KOREN + "/predmeti" : KOREN;
}

function primeni(zamena) {
  const kljuc = kljucIzPutanje(window.location.pathname);

  if (!kljuc) {
    // Nepoznata child putanja -> kanonsko razresenje na Predmeti, bez
    // ponovnog ucitavanja dokumenta.
    window.history.replaceState({}, "", putanjaZa("predmeti"));
    return primeni(true);
  }

  // Koren bez eksplicitne child putanje dobija kanonsku putanju u traci,
  // takodje bez reload-a.
  if (window.location.pathname.replace(/\/+$/, "") === KOREN) {
    window.history.replaceState({}, "", putanjaZa(kljuc));
  }

  if (tekuci && tekuci.kljuc === kljuc && !zamena) return;

  if (tekuci) { tekuci.ciklus.ugasi(); tekuci = null; }
  ciljKontejner.replaceChildren();

  const montiraj = ekrani.get(kljuc);
  if (!montiraj) return;
  tekuci = { kljuc, ciklus: montiraj(ciljKontejner) };
}

export function pokreni(kontejner) {
  ciljKontejner = kontejner;
  window.addEventListener("popstate", () => primeni(false));
  primeni(false);
}

export function idiNa(kljuc) {
  const p = putanjaZa(kljuc);
  if (window.location.pathname === p) return;
  window.history.pushState({}, "", p);
  primeni(false);
}

/** Samo za testove — vraca ruter u pocetno stanje. */
export function _resetuj() {
  if (tekuci) tekuci.ciklus.ugasi();
  tekuci = null;
  ciljKontejner = null;
  ekrani.clear();
}
