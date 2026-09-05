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
 * ═══ ZASTO JE KLASA B DANAS PRAZNA ═══════════════════════════════════════
 *
 * Da bi red iz `predmet_hronologija` usao u klasu B, mora se DOKAZATI da je
 * predlog roka. Backend to trenutno ne moze:
 *
 *   - `predmet_hronologija` nema nijednu kolonu za VRSTU reda. Kalendarski
 *     klasifikator (`_klasifikuj_dogadjaj`) pogadja iz teksta i ima catch-all
 *     `return "rok_dokument"` — pa „Kraj zaposlenja tuzioca kod tuzenog",
 *     istorijska cinjenica predmeta, postaje „rok".
 *   - `izvor` je kolona provenijencije predvidjena tacno za ovo, ali je
 *     `LEGACY_UNKNOWN` na SVIH 55 redova u celoj tabeli, u svim kancelarijama.
 *   - `akter` je slobodan tekst („Genome (AI)", „DOO Alfa Trejd"). Pogadjanje
 *     po njemu je tacno ono sto se ovde ne sme raditi.
 *
 * Merena posledica pogadjanja: pri prozoru od 365 dana kroz kandidate prolazi
 * 47 redova, od kojih su 2 predlozi roka a 45 istorijske cinjenice predmeta.
 * Danas bi postao arhiva.
 *
 * Zato je odluka FAIL-CLOSED: red koji se ne moze dokazati NE ULAZI. Vindex o
 * njemu ne tvrdi nista — ni da je obaveza, ni da nije. Broj takvih redova se
 * vraca kao `nedokazivo` radi dijagnostike; korisniku se ne prikazuje, jer
 * nedostatak podatkovnog ugovora nije njegov problem.
 *
 * Cist modul: bez DOM-a, bez mreze, bez stanja.
 */

const DAN_MS = 86400000;

export const STANJE = Object.freeze({
  POTVRDJEN: "CONFIRMED",
  NEPOTVRDJEN: "UNCONFIRMED",
  ODBIJEN: "REJECTED",
});

/**
 * Vrednosti `predmet_hronologija.izvor` koje DOKAZUJU da je red predlog roka
 * koji je napravio sistem.
 *
 * Namerno prazna. Popunjava se tek kada backend pocne da upisuje provenijenciju
 * koja to razlikuje. Dodavanje vrednosti ovde je proizvodna odluka, ne
 * implementaciona — zato stoji na jednom vidljivom mestu.
 */
export const IZVOR_DOKAZUJE_PREDLOG = [];

export function dokazanoPredlog(red) {
  const izvor = String((red && red.izvor) || "").trim().toUpperCase();
  if (!izvor) return false;
  return IZVOR_DOKAZUJE_PREDLOG.includes(izvor);
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

  // ── Klasa A ────────────────────────────────────────────────────────────
  const potvrdjeni = redovi
    .filter(r => (r || {}).stanje_odluke === STANJE.POTVRDJEN)
    .map(r => uObavezu(r, imena, sada));

  const rocista = dogadjaji
    .filter(e => e && e.tip === "rociste")
    .map(e => uRociste(e, sada));

  const obaveze = potvrdjeni.concat(rocista)
    .filter(x => x.grupa !== null)
    .sort((a, b) => (a.datumIso === b.datumIso
      ? (a.vreme || "").localeCompare(b.vreme || "")
      : (a.datumIso < b.datumIso ? -1 : 1)));

  // ── Klasa B ────────────────────────────────────────────────────────────
  // Odbijen predlog ne ulazi: covek se izjasnio, to vise ne trazi paznju.
  const otvoreni = redovi.filter(r => (r || {}).stanje_odluke !== STANJE.POTVRDJEN
                                   && (r || {}).stanje_odluke !== STANJE.ODBIJEN);
  const dokazani = otvoreni.filter(dokazanoPredlog);

  const zaProveru = dokazani
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
    // Redovi koje ugovor ne moze da razvrsta. Dijagnostika za vlasnika,
    // NE prikazuje se korisniku.
    nedokazivo: otvoreni.length - dokazani.length,
  };
}
