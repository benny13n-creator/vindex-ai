/* Vindex V2 — domen ekrana Danas.
 *
 * ── ZASTO SE OBAVEZE NE CITAJU IZ KALENDARA ──────────────────────────────
 *
 * `/api/kalendar/pregled` je jedini agregat datiranih dogadjaja, ali za rokove
 * izvedene iz `predmet_hronologija` vraca SAMO `{vaznost, dogadjaj}`. Nema
 * `id`, nema `akter`, nema stanje odluke.
 *
 * Izmereno na produkciji (2026-09-05, vlasnicki nalog): sva tri nadolazeca
 * „kriticna roka" imaju `akter = "Pipeline (AI)"` i `stanje_odluke =
 * UNCONFIRMED`. Kroz kalendar bi se advokatu prikazali kao gotove obaveze sa
 * uzvicnikom — tvrdnja da ima kritican rok koji nijedan covek nije potvrdio.
 *
 * Zato je izvor obaveza `/api/rokovi/kandidati`, koji nosi `stanje_odluke`.
 * Kalendar se koristi za DVE stvari koje kandidati nemaju: rocista (zaseban
 * objekat iz tabele `rocista`, sopstveni status) i naziv predmeta.
 *
 * Kalendarski dogadjaji tipa `rok_dokument`/`napomena` se NAMERNO odbacuju —
 * to su isti redovi koje kandidati vec vracaju, samo bez stanja odluke.
 * Bez tog odbacivanja svaka obaveza bi se pojavila dvaput.
 *
 * ── STA NE ULAZI U DANAS ──────────────────────────────────────────────────
 *
 * Odbijen predlog (`REJECTED`) se ne prikazuje: covek se vec izjasnio, pa to
 * vise ne trazi paznju. Nije obrisan i ostaje u istoriji rokova — Danas
 * jednostavno nije istorija.
 *
 * Nivo rizika sam po sebi nije ulaznica. Stavka ulazi jer ima datum.
 *
 * Cist modul: bez DOM-a, bez mreze, bez stanja.
 */

const DAN_MS = 86400000;

/** Automatski proizvodjaci roka. Korisnik ne vidi ovaj niz, samo posledicu. */
const AUTOMATSKI_AKTERI = ["pipeline", "ai", "sistem", "auto"];

export const STANJE = Object.freeze({
  POTVRDJEN: "CONFIRMED",
  NEPOTVRDJEN: "UNCONFIRMED",
  ODBIJEN: "REJECTED",
});

function uDan(iso) {
  if (!iso) return null;
  const d = new Date(String(iso).slice(0, 10) + "T00:00:00");
  return Number.isNaN(d.getTime()) ? null : d;
}

function danasDan() {
  const n = new Date();
  return new Date(n.getFullYear(), n.getMonth(), n.getDate());
}

/** Razlika u danima; negativno = proslo. */
export function razlikaDana(iso, sada = danasDan()) {
  const d = uDan(iso);
  if (!d) return null;
  return Math.round((d.getTime() - sada.getTime()) / DAN_MS);
}

export function grupa(razlika) {
  if (razlika === null) return null;
  if (razlika < 0) return "isteklo";
  if (razlika === 0) return "danas";
  if (razlika === 1) return "sutra";
  if (razlika <= 7) return "nedelja";
  return null;                      // dalje od 7 dana ne trazi paznju danas
}

export const GRUPE = Object.freeze([
  { kljuc: "isteklo", naziv: "Isteklo" },
  { kljuc: "danas", naziv: "Danas" },
  { kljuc: "sutra", naziv: "Sutra" },
  { kljuc: "nedelja", naziv: "Narednih 7 dana" },
]);

/** Vreme izrazeno onako kako ga advokat izgovara, ne kao broj dana od epohe. */
export function kadaTekst(razlika) {
  if (razlika === null) return "";
  if (razlika === 0) return "danas";
  if (razlika === 1) return "sutra";
  if (razlika === -1) return "juče";
  if (razlika < 0) {
    const n = Math.abs(razlika);
    return n === 1 ? "pre 1 dan" : `pre ${n} dana`;
  }
  return razlika === 1 ? "za 1 dan" : `za ${razlika} dana`;
}

export function datumTekst(iso) {
  const d = uDan(iso);
  if (!d) return "—";
  const dan = String(d.getDate()).padStart(2, "0");
  const mes = String(d.getMonth() + 1).padStart(2, "0");
  return `${dan}.${mes}.${d.getFullYear()}.`;
}

function automatski(akter) {
  const a = String(akter || "").toLowerCase();
  return AUTOMATSKI_AKTERI.some(x => a.includes(x));
}

/**
 * Server salje naslov sa ukrasnim emojijem („⚠️ Rociste zakazano").
 * V2 ga skida: emoji nije podatak nego prezentacija koju je izabrao drugi sloj,
 * a vizuelni kanon ne koristi ukrasne znakove kao nosioce znacenja.
 */
export function ocistiNaslov(tekst) {
  return String(tekst || "")
    .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{2B00}-\u{2BFF}]/gu, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

/** Rok/obaveza iz `/api/rokovi/kandidati`. */
export function uObavezu(sirov, imenaPredmeta = {}, sada = danasDan()) {
  const r = sirov || {};
  const iso = r.datum_iso || r.datum || "";
  const razlika = razlikaDana(iso, sada);
  const stanje = r.stanje_odluke || STANJE.NEPOTVRDJEN;
  return {
    id: r.id || "",
    vrsta: "rok",
    vrstaNaziv: "Rok",
    opis: ocistiNaslov(r.dogadjaj) || "Rok bez opisa",
    predmetId: r.predmet_id || "",
    predmet: imenaPredmeta[r.predmet_id] || "",
    datumIso: iso,
    datum: datumTekst(iso),
    razlika,
    grupa: grupa(razlika),
    potvrdjen: stanje === STANJE.POTVRDJEN,
    nepotvrdjen: stanje === STANJE.NEPOTVRDJEN,
    odbijen: stanje === STANJE.ODBIJEN,
    automatski: automatski(r.akter),
  };
}

/** Rociste iz `/api/kalendar/pregled` (tabela `rocista`, sopstveni status). */
export function uRociste(sirov, sada = danasDan()) {
  const e = sirov || {};
  const iso = e.datum || "";
  const razlika = razlikaDana(iso, sada);
  const d = e.detalji || {};
  const mesto = [d.sud, d.sudnica].filter(Boolean).join(", ");
  return {
    id: d.id || "",
    vrsta: "rociste",
    vrstaNaziv: "Ročište",
    opis: mesto || "Ročište",
    predmetId: e.predmet_id || "",
    predmet: e.predmet_naziv || "",
    datumIso: iso,
    datum: datumTekst(iso),
    vreme: e.vreme || "",
    razlika,
    grupa: grupa(razlika),
    // Rociste nije AI predlog nego zakazan dogadjaj — model potvrde se na
    // njega ne primenjuje i ne sme se glumiti.
    potvrdjen: true,
    nepotvrdjen: false,
    odbijen: false,
    automatski: false,
  };
}

/** Mapa predmet_id -> naziv, izvedena iz kalendara (kandidati je nemaju). */
export function imenaIzKalendara(dogadjaji) {
  const m = {};
  for (const e of dogadjaji || []) {
    if (e && e.predmet_id && e.predmet_naziv) m[e.predmet_id] = e.predmet_naziv;
  }
  return m;
}

/**
 * Sastavlja ekran Danas iz dva izvora.
 * @returns {{grupe: Array, ukupno: number, degradirano: boolean, odseceno: boolean}}
 */
export function sastavi({ kandidati, kalendar }, sada = danasDan()) {
  const k = kandidati || {};
  const c = kalendar || {};
  const dogadjaji = Array.isArray(c.dogadjaji) ? c.dogadjaji : [];
  const imena = imenaIzKalendara(dogadjaji);

  const obaveze = (Array.isArray(k.rokovi) ? k.rokovi : [])
    .map(x => uObavezu(x, imena, sada))
    .filter(x => !x.odbijen && x.grupa !== null);

  const rocista = dogadjaji
    .filter(e => e && e.tip === "rociste")
    .map(x => uRociste(x, sada))
    .filter(x => x.grupa !== null);

  const sve = obaveze.concat(rocista).sort((a, b) => {
    if (a.datumIso !== b.datumIso) return a.datumIso < b.datumIso ? -1 : 1;
    return (a.vreme || "").localeCompare(b.vreme || "");
  });

  const grupe = GRUPE
    .map(g => ({ ...g, stavke: sve.filter(x => x.grupa === g.kljuc) }))
    .filter(g => g.stavke.length > 0);

  return {
    grupe,
    ukupno: sve.length,
    // Delimican izvor NIKAD ne sme izgledati kao prazan ekran (§31).
    degradirano: Boolean((c.degraded_sources || []).length) || Boolean(c.__palo) || Boolean(k.__palo),
    odseceno: Boolean(k.odseceno) || Boolean(c.truncated),
  };
}
