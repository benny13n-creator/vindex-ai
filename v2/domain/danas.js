/* Vindex V2 — domen ekrana Danas.
 *
 * ═══ DVE SEMANTICKE KLASE, KOJE SE NIKAD NE MESAJU ════════════════════════
 *
 *   A. OBAVEZA   stvarno evidentirana poslovna obaveza
 *                -> rociste (tabela `rocista`, sopstveni objekat i status)
 *                -> rok cije je stanje odluke CONFIRMED
 *
 *   B. ZA PROVERU  trazi konkretnu reakciju, ali NIJE potvrdjena obaveza
 *                -> predlog roka koji je sistem napravio i niko nije potvrdio
 *
 * Nepotvrdjen predlog se NIKAD ne sme naci u istom redu i istom vizuelnom
 * statusu kao potvrdjena obaveza, i ne sme izgledati hitnije od nje.
 *
 * ═══ ODAKLE DOLAZI ODLUKA (migracija 129) ════════════════════════════════
 *
 * Tri eksplicitna signala, tri odvojene uloge. Nijedan ne preuzima tudju —
 * to je greska koju su FAZE 6.1-6.4.1 vec platile dvaput (`akter`, pa `izvor`):
 *
 *     izvor    KAKO je red nastao          provenijencija (migracija 127)
 *     vrsta    STA red jeste               migracija 129
 *     stanje   GDE je u zivotnom ciklusu   migracija 129
 *
 * `vrsta` je JEDINI dozvoljen odgovor na pitanje „je li ovo rok". Pogadjanje
 * po tekstu je zabranjeno i ima razlog: `_klasifikuj_dogadjaj` u kalendaru ima
 * catch-all `return "rok_dokument"`, pa „Kraj zaposlenja tuzioca kod tuzenog"
 * — istorijska cinjenica predmeta — izlazi kao ROK. Mereno: u prozoru od 365
 * dana 45 od 47 redova su cinjenice, ne rokovi.
 *
 * Red bez izjavljene `vrsta` NE ULAZI ni u jednu klasu. Vindex o njemu ne
 * tvrdi nista — ni da je obaveza, ni da nije. To je fail-closed po projektu,
 * a ne privremeno stanje: zateceni redovi se NIKAD ne klasifikuju retroaktivno.
 *
  * Cist modul: bez DOM-a, bez mreze, bez stanja.
 */

const DAN_MS = 86400000;

/** `predmet_hronologija.vrsta` — migracija 129. */
export const VRSTA = Object.freeze({
  ROK: "rok",
  ROCISTE: "rociste",
  ZADATAK: "zadatak",
  DOGADJAJ: "dogadjaj",
});

/** `predmet_hronologija.stanje` — migracija 129. */
export const STANJE = Object.freeze({
  KANDIDAT: "kandidat",
  POTVRDJEN: "potvrdjen",
  ODBIJEN: "odbijen",
  IZVRSEN: "izvrsen",
  OTKAZAN: "otkazan",
});

/** Stanja u kojima rok vise ne trazi paznju i ne sme u aktivni Danas. */
export const STANJA_RAZRESENA = Object.freeze([
  STANJE.ODBIJEN, STANJE.IZVRSEN, STANJE.OTKAZAN,
]);

/** Prevod stanja odluke (audit trag) u domensko stanje — za legacy redove
 *  koji imaju odluku ali jos nemaju kolonu `stanje`. */
const ODLUKA_U_STANJE = Object.freeze({
  CONFIRMED: STANJE.POTVRDJEN,
  REJECTED: STANJE.ODBIJEN,
  UNCONFIRMED: STANJE.KANDIDAT,
});

/** Je li red rok — po IZJAVI, nikad po pogadjanju. */
export function jeRok(red) {
  return String((red && red.vrsta) || "").trim().toLowerCase() === VRSTA.ROK;
}

/**
 * Domensko stanje reda. Prednost ima kolona `stanje`; kada je prazna, pada na
 * model potvrde, pa se zateceno ponasanje ne menja. Bez oba — `null`, i nista
 * se ne tvrdi.
 */
export function stanjeZapisa(red) {
  const s = String((red && red.stanje) || "").trim().toLowerCase();
  if (Object.values(STANJE).includes(s)) return s;
  const o = String((red && red.stanje_odluke) || "").trim().toUpperCase();
  return ODLUKA_U_STANJE[o] || null;
}

export function jeRazresen(red) {
  return STANJA_RAZRESENA.includes(stanjeZapisa(red));
}

function uDan(iso) {
  if (!iso) return null;
  const d = new Date(String(iso).slice(0, 10) + "T00:00:00");
  return Number.isNaN(d.getTime()) ? null : d;
}

function danasDan() {
  const n = new Date();
  return new Date(n.getFullYear(), n.getMonth(), n.getDate());
}

export function razlikaDana(iso, sada = danasDan()) {
  const d = uDan(iso);
  if (!d) return null;
  return Math.round((d.getTime() - sada.getTime()) / DAN_MS);
}

/* ── Grupe obaveza ──────────────────────────────────────────────────────
 * Redosled je poslovni prioritet, ne kalendarski: propusteno prvo.
 * Sve dalje od 7 dana ne trazi paznju DANAS i ne ulazi.
 */
export function grupa(razlika) {
  if (razlika === null) return null;
  if (razlika < 0) return "propusteno";
  if (razlika === 0) return "danas";
  if (razlika === 1) return "sutra";
  if (razlika <= 7) return "nedelja";
  return null;
}

export const GRUPE = Object.freeze([
  { kljuc: "propusteno", naziv: "Propušteno" },
  { kljuc: "danas", naziv: "Danas" },
  { kljuc: "sutra", naziv: "Sutra" },
  { kljuc: "nedelja", naziv: "Narednih 7 dana" },
]);

export function kadaTekst(razlika) {
  if (razlika === null) return "";
  if (razlika === 0) return "danas";
  if (razlika === 1) return "sutra";
  if (razlika === -1) return "juče";
  if (razlika < 0) {
    const n = Math.abs(razlika);
    return n === 1 ? "pre 1 dan" : `pre ${n} dana`;
  }
  return `za ${razlika} dana`;
}

export function datumTekst(iso) {
  const d = uDan(iso);
  if (!d) return "—";
  const dan = String(d.getDate()).padStart(2, "0");
  const mes = String(d.getMonth() + 1).padStart(2, "0");
  return `${dan}.${mes}.${d.getFullYear()}.`;
}

/** Server salje naslov sa ukrasnim emojijem; emoji je prezentacija, ne podatak. */
export function ocistiNaslov(tekst) {
  return String(tekst || "")
    .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{2B00}-\u{2BFF}]/gu, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function osnovno(iso, sada) {
  const razlika = razlikaDana(iso, sada);
  return { datumIso: iso, datum: datumTekst(iso), razlika, grupa: grupa(razlika) };
}

/** Klasa A — potvrdjen rok iz hronologije. */
export function uObavezu(sirov, imena = {}, sada = danasDan()) {
  const r = sirov || {};
  return {
    klasa: "obaveza",
    id: r.id || "",
    vrsta: "rok",
    vrstaNaziv: "Rok",
    opis: ocistiNaslov(r.dogadjaj) || "Rok bez opisa",
    predmetId: r.predmet_id || "",
    predmet: imena[r.predmet_id] || "",
    vreme: "",
    ...osnovno(r.datum_iso || r.datum || "", sada),
  };
}

/** Klasa A — rociste. Zaseban objekat; model potvrde se na njega ne primenjuje. */
export function uRociste(sirov, sada = danasDan()) {
  const e = sirov || {};
  const d = e.detalji || {};
  const mesto = [d.sud, d.sudnica].filter(Boolean).join(", ");
  return {
    klasa: "obaveza",
    id: d.id || "",
    vrsta: "rociste",
    vrstaNaziv: "Ročište",
    opis: mesto || "Ročište",
    predmetId: e.predmet_id || "",
    predmet: e.predmet_naziv || "",
    vreme: e.vreme || "",
    ...osnovno(e.datum || "", sada),
  };
}

/** Klasa B — predlog roka koji niko nije potvrdio. */
export function uProveru(sirov, imena = {}, sada = danasDan()) {
  const r = sirov || {};
  return {
    klasa: "provera",
    id: r.id || "",
    vrsta: "predlog",
    vrstaNaziv: "Predlog roka",
    opis: ocistiNaslov(r.dogadjaj) || "Predlog bez opisa",
    predmetId: r.predmet_id || "",
    predmet: imena[r.predmet_id] || "",
    vreme: "",
    ...osnovno(r.datum_iso || r.datum || "", sada),
  };
}

export function imenaIzKalendara(dogadjaji) {
  const m = {};
  for (const e of dogadjaji || []) {
    if (e && e.predmet_id && e.predmet_naziv) m[e.predmet_id] = e.predmet_naziv;
  }
  return m;
}

/**
 * Sastavlja Danas.
 * @returns {{grupe, obaveza, zaProveru, ukupno, degradirano, odseceno, nedokazivo}}
 */
export function sastavi({ kandidati, kalendar }, sada = danasDan()) {
  const k = kandidati || {};
  const c = kalendar || {};
  const dogadjaji = Array.isArray(c.dogadjaji) ? c.dogadjaji : [];
  const imena = imenaIzKalendara(dogadjaji);
  const redovi = Array.isArray(k.rokovi) ? k.rokovi : [];

  // Samo redovi koji su IZJAVILI da su rok ulaze u bilo koju klasu.
  const rokovi = redovi.filter(jeRok);
  // Sve ostalo se ne klasifikuje — ni kao obaveza, ni kao predlog.
  const nedokazivo = redovi.length - rokovi.length;

  // Razresen rok (odbijen / izvrsen / otkazan) ne trazi vise paznju.
  const aktivni = rokovi.filter(r => !jeRazresen(r));

  // ── Klasa A: potvrdjena obaveza ────────────────────────────────────────
  const potvrdjeni = aktivni
    .filter(r => stanjeZapisa(r) === STANJE.POTVRDJEN)
    .map(r => uObavezu(r, imena, sada));

  const rocista = dogadjaji
    .filter(e => e && e.tip === "rociste")
    .map(e => uRociste(e, sada));

  const obaveze = potvrdjeni.concat(rocista)
    .filter(x => x.grupa !== null)
    .sort((a, b) => (a.datumIso === b.datumIso
      ? (a.vreme || "").localeCompare(b.vreme || "")
      : (a.datumIso < b.datumIso ? -1 : 1)));

  // ── Klasa B: kandidat ──────────────────────────────────────────────────
  const zaProveru = aktivni
    .filter(r => stanjeZapisa(r) === STANJE.KANDIDAT)
    .map(r => uProveru(r, imena, sada))
    .filter(x => x.razlika !== null)
    .sort((a, b) => (a.datumIso < b.datumIso ? -1 : 1));

  const grupe = GRUPE
    .map(g => ({ ...g, stavke: obaveze.filter(x => x.grupa === g.kljuc) }))
    .filter(g => g.stavke.length > 0);

  return {
    grupe,
    obaveza: obaveze.length,
    zaProveru,
    ukupno: obaveze.length + zaProveru.length,
    degradirano: Boolean((c.degraded_sources || []).length) || Boolean(c.__palo) || Boolean(k.__palo),
    odseceno: Boolean(k.odseceno) || Boolean(c.truncated),
    // Redovi koji nisu izjavili `vrsta`. Dijagnostika za vlasnika, korisniku
    // se NE prikazuje — nedostatak podatkovnog ugovora nije njegov problem.
    nedokazivo,
  };
}
