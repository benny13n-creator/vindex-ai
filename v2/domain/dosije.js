/* Vindex V2 — domen Dosijea.
 *
 * Predmet se ne otvara u tablu nego u DOSIJE: jedan predmet, jedna radna
 * povrsina, pet imenovanih celina — Stanje, Hronologija, Analiza predmeta,
 * Spisi, Rokovi i zadaci. To nisu tabovi i ne skrivaju jedna drugu.
 *
 * Ceo Dosije dolazi iz JEDNOG poziva `/api/predmeti/{id}`, koji vraca
 * `{predmet, dokumenti, hronologija, beleske, istorija, komentari,
 *   klijenti_linked}`. Zato ekran nema sedam mreznih poziva ni sedam stanja
 * ucitavanja — ima jedno.
 *
 * Sto ovaj modul NIKAD ne radi:
 *   - ne izmislja pravnu sigurnost; polje kojeg nema ne prikazuje se
 *   - ne pogadja vrstu zapisa hronologije (vidi domain/danas.js)
 *   - ne prikazuje interne identifikatore korisniku
 *
 * Cist modul: bez DOM-a, bez mreze, bez stanja.
 */

import { nazivStanja, klasaStanja, nazivVrste, datum } from "./labels.js";
import { ocistiNaslov, datumTekst, razlikaDana, kadaTekst } from "./danas.js";
import { jeRok, stanjeZapisa, STANJE } from "./danas.js";

/** Celine Dosijea, redom. Imena su ono sto korisnik vidi. */
export const CELINE = Object.freeze([
  { kljuc: "stanje", naziv: "Stanje" },
  { kljuc: "hronologija", naziv: "Hronologija" },
  { kljuc: "analiza", naziv: "Analiza predmeta" },
  { kljuc: "spisi", naziv: "Spisi" },
  { kljuc: "rokovi", naziv: "Rokovi i zadaci" },
]);

/** Kratka imena za sidrenu traku — puna imena ostaju na naslovima celina. */
export const SIDRA = Object.freeze([
  { kljuc: "stanje", naziv: "Stanje" },
  { kljuc: "hronologija", naziv: "Hronologija" },
  { kljuc: "analiza", naziv: "Analiza" },
  { kljuc: "spisi", naziv: "Spisi" },
  { kljuc: "rokovi", naziv: "Rokovi" },
]);

function tekst(v) {
  const s = String(v == null ? "" : v).trim();
  return s;
}

/** Iznos u dinarima onako kako ga advokat cita, ne kao sirov broj. */
export function iznos(v) {
  const n = Number(v);
  if (!Number.isFinite(n) || n <= 0) return "";
  return n.toLocaleString("sr-RS", { maximumFractionDigits: 2 }) + " RSD";
}

/**
 * Zaglavlje predmeta — samo ono sto ima poslovnu vrednost i sto podaci
 * stvarno nose. Prazno polje se NE prikazuje: prazan red je tvrdnja da
 * podatak postoji a nije popunjen, a to nije uvek istina.
 */
export function uZaglavlje(sirov) {
  const p = sirov || {};
  const stranke = [tekst(p.tuzilac), tekst(p.tuzeni)].filter(Boolean);
  return {
    id: p.id || "",
    naziv: tekst(p.naziv) || "Predmet bez naziva",
    broj: tekst(p.broj_predmeta),
    vrsta: nazivVrste(p.tip),
    stanje: nazivStanja(p.status),
    stanjeKlasa: klasaStanja(p.status),
    tuzilac: tekst(p.tuzilac),
    tuzeni: tekst(p.tuzeni),
    stranke,
    vrednost: iznos(p.vrednost_spora),
    opis: tekst(p.opis),
    otvoren: datum(p.created_at),
    izmenjen: datum(p.updated_at),
  };
}

/** Polja zaglavlja u redosledu prikaza; prazna ispadaju. */
export function poljaZaglavlja(z) {
  return [
    { naziv: "Broj predmeta", vrednost: z.broj, mono: true },
    { naziv: "Vrsta", vrednost: z.vrsta },
    { naziv: "Tužilac", vrednost: z.tuzilac },
    { naziv: "Tuženi", vrednost: z.tuzeni },
    { naziv: "Vrednost spora", vrednost: z.vrednost, mono: true },
    { naziv: "Otvoren", vrednost: z.otvoren, mono: true },
  ].filter(x => x.vrednost);
}

/** Klijenti povezani sa predmetom. `klijent` NIJE `stranka` — ne spajati. */
export function uKlijente(niz) {
  return (niz || []).map(k => ({
    id: (k && (k.id || k.klijent_id)) || "",
    naziv: tekst(k && (k.firma || k.naziv || k.ime)) || "Klijent bez naziva",
    uloga: tekst(k && k.uloga),
  })).filter(x => x.naziv);
}

/** Spis. Naziv se ne sece; interni identifikatori se ne prikazuju. */
export function uSpis(sirov) {
  const d = sirov || {};
  return {
    id: d.id || "",
    naziv: tekst(d.naziv_fajla) || "Spis bez naziva",
    dodat: datum(d.created_at),
    analiziran: Boolean(d.klasifikovan_at),
    status: tekst(d.status),
    imaOriginal: Boolean(tekst(d.storage_path)),
    redniBroj: Number.isFinite(d.redni_broj) ? d.redni_broj : null,
  };
}

/**
 * Zapis hronologije. Vrsta se NE pogadja — prikazuje se samo ono sto je
 * izjavljeno (migracija 129). Neizjavljen red je i dalje dogadjaj u
 * hronologiji; on samo NIJE rok.
 */
export function uZapisHronologije(sirov) {
  const h = sirov || {};
  const iso = h.datum_iso || h.datum || "";
  return {
    id: h.id || "",
    datum: datumTekst(iso),
    datumIso: iso,
    dogadjaj: ocistiNaslov(h.dogadjaj) || "Događaj bez opisa",
    akter: tekst(h.akter),
    dokument: tekst(h.dokument_naziv),
    vaznost: tekst(h.vaznost),
    kritican: tekst(h.vaznost).toLowerCase().startsWith("krit"),
    jeRok: jeRok(h),
  };
}

/** Hronologija, najnovije prvo. */
export function uHronologiju(niz) {
  return (niz || [])
    .map(uZapisHronologije)
    .sort((a, b) => (a.datumIso < b.datumIso ? 1 : a.datumIso > b.datumIso ? -1 : 0));
}

/**
 * Rokovi predmeta iz hronologije. Ista pravila kao Danas: samo izjavljen rok,
 * razresen ne ulazi u aktivne, kandidat je odvojen od potvrdjene obaveze.
 */
export function uRokove(niz, sada) {
  const rokovi = (niz || []).filter(jeRok);
  const aktivni = rokovi.filter(r => {
    const s = stanjeZapisa(r);
    return s !== STANJE.ODBIJEN && s !== STANJE.IZVRSEN && s !== STANJE.OTKAZAN;
  });
  const mapiraj = (r) => {
    const iso = r.datum_iso || r.datum || "";
    const razlika = razlikaDana(iso, sada);
    return {
      id: r.id || "",
      opis: ocistiNaslov(r.dogadjaj) || "Rok bez opisa",
      datum: datumTekst(iso),
      datumIso: iso,
      razlika,
      kada: kadaTekst(razlika),
      proslo: razlika !== null && razlika < 0,
    };
  };
  const sort = (a, b) => (a.datumIso < b.datumIso ? -1 : 1);
  return {
    obaveze: aktivni.filter(r => stanjeZapisa(r) === STANJE.POTVRDJEN).map(mapiraj).sort(sort),
    zaProveru: aktivni.filter(r => stanjeZapisa(r) === STANJE.KANDIDAT).map(mapiraj).sort(sort),
    razreseni: rokovi.length - aktivni.length,
    nedokazivo: (niz || []).length - rokovi.length,
  };
}

/**
 * Spremnost predmeta iz `/api/predmeti/{id}/health`.
 * Prikazuje se SAMO ako backend vrati status — nikad izmisljen procenat.
 */
export function uSpremnost(sirov) {
  const h = sirov || {};
  const status = tekst(h.status);
  if (!status) return null;
  return {
    status,
    razlozi: (h.razlozi || []).map(tekst).filter(Boolean),
    // `score` se namerno NE prikazuje kao broj: ocena bez objasnjenja je
    // tacno ono sto vlasnicki kanon zabranjuje. Razlozi jesu upotrebljivi.
  };
}

/** Sastavlja ceo Dosije iz jednog odgovora. */
export function sastaviDosije(odgovor, spremnostSirova, sada) {
  const o = odgovor || {};
  const hron = o.hronologija || [];
  return {
    zaglavlje: uZaglavlje(o.predmet),
    polja: poljaZaglavlja(uZaglavlje(o.predmet)),
    klijenti: uKlijente(o.klijenti_linked),
    spisi: (o.dokumenti || []).map(uSpis),
    hronologija: uHronologiju(hron),
    rokovi: uRokove(hron, sada),
    beleske: (o.beleske || []).length,
    spremnost: uSpremnost(spremnostSirova),
  };
}
