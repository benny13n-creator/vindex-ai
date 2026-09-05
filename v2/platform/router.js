/* Vindex V2 — ruter (History API).
 *
 * Ruter zna samo za PROSTORE. Ne zna za objekte i radnje unutar njih — to je
 * posao ekrana. Time se dubina navigacije drzi na modelu
 * PROSTOR -> OBJEKAT -> RADNJA, umesto da ruter postane stablo tabova.
 *
 * Sve rute su prave putanje, pa `<a href>` radi nativno: srednji klik i
 * „otvori u novoj kartici" ne traze nijednu liniju koda. Obican klik ruter
 * presrece i menja prikaz bez ponovnog ucitavanja dokumenta.
 *
 * Kontekst se cuva izmedju prelazaka: ekran koji se napusta moze da ostavi
 * svoje stanje, a isti ekran ga pri povratku zatice. Bez toga bi korisnik
 * posle svakog prelaska iznova gradio pretragu, stranu i poziciju.
 */

export const KOREN = "/app-v2";

const ekrani = new Map();          // kljuc -> montiraj(el, kontekst)
let tekuci = null;                 // { kljuc, ciklus }
let kontejner = null;
let podrazumevani = null;
const slusaoci = [];
const konteksti = new Map();       // kljuc -> proizvoljno stanje ekrana

/** @param {(el:HTMLElement, kontekst:object)=>{ugasi:Function, kontekst?:Function}} montiraj */
export function registruj(kljuc, montiraj) {
  ekrani.set(kljuc, montiraj);
  if (!podrazumevani) podrazumevani = kljuc;
}

export function postaviPodrazumevani(kljuc) {
  podrazumevani = kljuc;
}

export function naPromenu(fn) {
  slusaoci.push(fn);
  if (tekuci) fn(tekuci.kljuc);
}

function kljucIzPutanje(putanja) {
  const p = String(putanja || "").replace(/\/+$/, "");
  if (p === KOREN || p === "") return podrazumevani;
  const zadnji = p.slice(KOREN.length + 1);
  return ekrani.has(zadnji) ? zadnji : null;
}

export function putanjaZa(kljuc) {
  return `${KOREN}/${kljuc}`;
}

function primeni() {
  let kljuc = kljucIzPutanje(window.location.pathname);

  // Nepoznata putanja -> kanonsko razresenje na podrazumevani prostor,
  // bez ponovnog ucitavanja dokumenta.
  if (!kljuc) {
    kljuc = podrazumevani;
    window.history.replaceState({}, "", putanjaZa(kljuc));
  } else if (window.location.pathname.replace(/\/+$/, "") === KOREN) {
    window.history.replaceState({}, "", putanjaZa(kljuc));
  }

  if (tekuci && tekuci.kljuc === kljuc) return;

  if (tekuci) {
    // Ekran koji odlazi ostavlja svoj kontekst da bi ga zatekao pri povratku.
    if (typeof tekuci.ciklus.kontekst === "function") {
      try { konteksti.set(tekuci.kljuc, tekuci.ciklus.kontekst()); } catch (e) { /* nebitno */ }
    }
    tekuci.ciklus.ugasi();
    tekuci = null;
  }
  kontejner.replaceChildren();

  const montiraj = ekrani.get(kljuc);
  if (!montiraj) return;
  tekuci = { kljuc, ciklus: montiraj(kontejner, konteksti.get(kljuc) || null) };
  for (const fn of slusaoci) fn(kljuc);
}

export function pokreni(el) {
  kontejner = el;
  window.addEventListener("popstate", primeni);
  primeni();
}

export function idiNaPutanju(putanja) {
  const p = String(putanja || "");
  if (window.location.pathname === p) return;
  window.history.pushState({}, "", p);
  primeni();
}

export function idiNa(kljuc) {
  idiNaPutanju(putanjaZa(kljuc));
}

/** Samo za testove. */
export function _resetuj() {
  if (tekuci) tekuci.ciklus.ugasi();
  tekuci = null; kontejner = null; podrazumevani = null;
  ekrani.clear(); konteksti.clear(); slusaoci.length = 0;
}
