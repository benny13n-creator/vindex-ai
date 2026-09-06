/* Vindex V2 — sabloni dokumenata (D4), domen.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * NEPOPUNJENO POLJE NE NESTAJE — ULAZI U DOKUMENT KAO RUPA
 *
 * Backend zamenjuje nepopunjena polja tekstom „[POLJE — NIJE UNETO]" i taj
 * tekst zavrsi U DOKUMENTU. To NIJE greska nego namerna odluka: bolje
 * vidljiva rupa nego tiho izmisljen podatak.
 *
 * Ali advokat mora znati da ce rupa biti tamo PRE nego sto potrosi poziv i
 * pre nego sto tekst prekopira u podnesak. Zato `nepopunjena()` postoji: ono
 * sto nedostaje se imenuje unapred, po nazivu polja.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * POLJA DOLAZE SA SERVERA. Svaki sablon nosi svoj spisak (`polja`); obrazac
 * se gradi iz njega. Prepisan spisak bi zastario i trazio bi podatke koje
 * sablon ne koristi, ili propustio one koje koristi.
 */

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

/* Kljucevi polja sa servera su ASCII (`cinjenice`, `jmbg_vlastodavca`), jer
 * su imena promenljivih. Prikazati ih doslovno znacilo bi da srpski advokat
 * cita „Cinjenice" i „Jmbg vlastodavca" u pravnom proizvodu. Ovo je ISKLJUCIVO
 * prevod natpisa: nijedan podatak se ne menja, ne dodaje i ne tumaci.
 * Nepoznat kljuc pada na opste pravilo ispod — spisak ne mora biti potpun. */
const NATPISI = Object.freeze({
  ime_tuzitelja: "Ime tužioca",
  adresa_tuzitelja: "Adresa tužioca",
  ime_tuzenog: "Ime tuženog",
  adresa_tuzenog: "Adresa tuženog",
  cinjenice: "Činjenice",
  vrednost_spora_rsd: "Vrednost spora (RSD)",
  ime_stranke: "Ime stranke",
  broj_predmeta: "Broj predmeta",
  naziv_suda: "Naziv suda",
  datum_presude: "Datum presude",
  razlozi_zalbe: "Razlozi žalbe",
  ime_vlastodavca: "Ime vlastodavca",
  jmbg_vlastodavca: "JMBG vlastodavca",
  adresa_vlastodavca: "Adresa vlastodavca",
  ime_poverioca: "Ime poverioca",
  ime_duznika: "Ime dužnika",
  adresa_duznika: "Adresa dužnika",
  iznos_rsd: "Iznos (RSD)",
  osnov_duga: "Osnov duga",
  rok_dana: "Rok (dana)",
  datum: "Datum",
});

/** Naziv polja u recenicu koju advokat cita. */
export function nazivPolja(kljuc) {
  const k = tekst(kljuc);
  if (NATPISI[k]) return NATPISI[k];
  const s = k.replace(/_/g, " ");
  if (!s) return "";
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Polja koja su ocito datum — da obrazac ponudi biranje datuma, ne slobodan tekst. */
export function jeDatum(kljuc) {
  return /(^|_)datum($|_)/.test(tekst(kljuc).toLowerCase());
}

/** Polja koja su ocito iznos. */
export function jeIznos(kljuc) {
  return /(rsd|iznos|vrednost)/.test(tekst(kljuc).toLowerCase());
}

export function uSablon(sirov) {
  const s = sirov || {};
  return {
    id: tekst(s.id),
    naziv: tekst(s.naziv),
    tip: tekst(s.tip),
    opis: tekst(s.opis),
    polja: (Array.isArray(s.polja) ? s.polja : []).map(tekst).filter(Boolean),
  };
}

export function uSablone(sirov) {
  const o = sirov || {};
  return (Array.isArray(o.sabloni) ? o.sabloni : [])
    .map(uSablon)
    // Sablon bez `id` se ne moze naruciti, sablon bez polja nema obrazac.
    .filter(s => s.id && s.naziv);
}

/**
 * Imenuje polja koja ce u dokumentu ostati kao vidljiva rupa. Vraca NAZIVE
 * na jeziku advokata, ne kljuceve.
 */
export function nepopunjena(sablon, vrednosti) {
  const v = vrednosti || {};
  return (sablon && Array.isArray(sablon.polja) ? sablon.polja : [])
    .filter(k => !tekst(v[k]))
    .map(nazivPolja);
}

/** Sve sto server trazi pre poziva. Sablon je obavezan; polja nisu. */
export function nedostaciGenerisanja({ sablonId } = {}) {
  const g = [];
  if (!tekst(sablonId)) g.push("Izaberite šablon.");
  return g;
}

/**
 * Provera pre cuvanja. Server trazi `predmet_id`, `naziv` i `sadrzaj` od bar
 * 10 znakova; bez predmeta dokument nema gde da se sacuva.
 */
export function nedostaciCuvanja({ predmetId, naziv, sadrzaj } = {}) {
  const g = [];
  if (!tekst(predmetId)) g.push("Izaberite predmet u koji se dokument čuva.");
  if (!tekst(naziv)) g.push("Unesite naziv dokumenta.");
  else if (tekst(naziv).length > 200) g.push("Naziv sme imati najviše 200 znakova.");
  if (tekst(sadrzaj).length < 10) g.push("Nema teksta koji bi se sačuvao.");
  return g;
}
