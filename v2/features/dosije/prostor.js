/* Vindex V2 — objekat PREDMET i radnje u njemu.
 *
 * Ruter zna za `/app-v2/predmet/<id>`. Sve dublje je posao ovog modula, jer
 * je to RADNJA nad objektom, ne nov prostor:
 *
 *   /app-v2/predmet/<id>            -> Dosije
 *   /app-v2/predmet/<id>?spis=<dok> -> citanje jednog spisa iz tog predmeta
 *
 * Radnja je u upitu, a ne u putanji, iz jednog razloga: dokument BEZ predmeta
 * nema smisla, pa ne sme dobiti sopstvenu putanju koja bi to sugerisala.
 * Deep link i dalje radi, `back` i `napred` rade, i veza se moze podeliti.
 *
 * Ruter ne remontira ekran kad se promeni samo upit (putanja je ista), pa
 * prelazak radnje ide kroz ovaj modul — ukljucujuci `popstate`, da `back`
 * iz citaca vrati Dosije umesto da ostavi zatecen ekran.
 */

import { montirajDosije } from "./view.js";
import { montirajCitac } from "./citac.js";

function spisIzURL() {
  try { return new URLSearchParams(window.location.search).get("spis") || null; }
  catch (e) { return null; }
}

export function montirajPredmetProstor(kontejner, kontekst, predmetId) {
  let dete = null;
  let ugasen = false;
  const svi = kontekst || {};

  function ocisti() {
    if (!dete) return;
    if (typeof dete.kontekst === "function") {
      try { svi[dete._kljuc] = dete.kontekst(); } catch (e) { /* nebitno */ }
    }
    dete.ugasi();
    dete = null;
  }

  function nazadNaDosije() {
    const p = window.location.pathname;
    window.history.pushState({}, "", p);
    prikazi();
  }

  function otvoriSpis(spisId) {
    const p = window.location.pathname + "?spis=" + encodeURIComponent(spisId);
    window.history.pushState({}, "", p);
    prikazi();
  }

  function prikazi() {
    if (ugasen) return;
    ocisti();
    kontejner.replaceChildren();
    const spisId = spisIzURL();
    if (spisId) {
      dete = montirajCitac(kontejner, svi.citac || null,
                           { predmetId, spisId, nazadNaDosije });
      dete._kljuc = "citac";
    } else {
      // `osvezi` postoji zato sto se posle otpremanja spisa Dosije mora
      // ponovo procitati sa servera: prikazati novi spis iz lokalnog stanja
      // znacilo bi tvrditi nesto o bazi bez dokaza da je tamo stigao.
      dete = montirajDosije(kontejner, svi.dosije || null, predmetId,
                            { otvoriSpis, osvezi: () => prikazi() });
      dete._kljuc = "dosije";
    }
  }

  // `back` iz citaca menja samo upit -- ruter to ne vidi kao promenu ekrana.
  const naPop = () => prikazi();
  window.addEventListener("popstate", naPop);

  prikazi();

  return {
    ugasi() {
      ugasen = true;
      window.removeEventListener("popstate", naPop);
      ocisti();
    },
    kontekst: () => svi,
  };
}
