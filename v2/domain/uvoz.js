/* Vindex V2 — uvoz predmeta iz dokumenta (Smart Intake), A7 — domen.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * „PROVERA JE ZAKAZANA" NIJE „NEMA SUKOBA"
 *
 * Finalizovanje uvoza pravi predmet i ZAKAZUJE proveru sukoba interesa; ona
 * se izvrsava posle, kroz dogadjaj. Backend zato vraca `coi_status` sa tri
 * stanja i nijedno od njih NE ZNACI da sukoba nema:
 *
 *   COI_PENDING        — provera je zakazana. Rezultat jos ne postoji.
 *   COI_FAILED         — provera NIJE zakazana. Niko je nece izvrsiti.
 *   COI_NOT_APPLICABLE — nije ni zakazana, jer ime stranke nije poznato.
 *
 * Odsustvo alarma nije dokaz o odsustvu sukoba. Ekran zato nikada ne sme da
 * napise „nema sukoba interesa" posle uvoza — sme samo da kaze u kom je
 * stanju provera.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * POUZDANOST IZVLACENJA SE PRIKAZUJE, NE SAKRIVA. Svaki izvucen podatak nosi
 * svoju pouzdanost i oznaku `needs_review`. Podatak koji trazi pregled ne
 * sme da izgleda isto kao podatak koji ne trazi.
 *
 * ODSUTNA VREDNOST NIJE PRAZAN STRING. Entitet bez vrednosti (`value: null`)
 * znaci da izvlacenje NIJE naslo podatak — ne da je podatak prazan.
 */

export const COI = Object.freeze({
  ZAKAZANA: "COI_PENDING",
  NIJE_ZAKAZANA: "COI_FAILED",
  NEPRIMENLJIVA: "COI_NOT_APPLICABLE",
});

/** Stanja posla koja vise nece da se menjaju sama od sebe. */
export const ZAVRSNA = Object.freeze(["completed", "failed", "awaiting_review"]);

/** Prag ispod koga podatak trazi ljudski pogled, i kad ga server ne oznaci. */
export const PRAG_POUZDANOSTI = 0.7;

const IMENA_ENTITETA = Object.freeze({
  case_number: "Broj predmeta",
  court: "Sud",
  judge: "Sudija",
  plaintiff: "Tužilac",
  defendant: "Tuženi",
  deadline: "Rok",
  amount: "Iznos",
  date: "Datum",
  contract_party: "Ugovorna strana",
  claim_basis: "Osnov zahteva",
});

/* Vrste dokumenata dolaze kao ASCII kljucevi klasifikatora. Srpski advokat
 * ne sme da cita „Court decision" u pravnom proizvodu. Prevod je ISKLJUCIVO
 * natpis — klasifikacija se ne menja. Nepoznat kljuc pada na opste pravilo. */
const IMENA_DOKUMENATA = Object.freeze({
  court_decision: "Sudska odluka",
  judgment: "Presuda",
  lawsuit: "Tužba",
  complaint: "Tužba",
  appeal: "Žalba",
  contract: "Ugovor",
  power_of_attorney: "Punomoćje",
  invoice: "Faktura",
  decision: "Rešenje",
  summons: "Poziv suda",
  notice: "Obaveštenje",
  other: "Ostalo",
  unknown: "Nije prepoznato",
});

export function imeDokumenta(tip) {
  const t = tekst(tip);
  if (IMENA_DOKUMENATA[t]) return IMENA_DOKUMENATA[t];
  const s = t.replace(/_/g, " ");
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : "";
}

const IMENA_STANJA = Object.freeze({
  queued: "U redu za obradu",
  pending: "U redu za obradu",
  processing: "Obrada u toku",
  awaiting_review: "Čeka vaš pregled",
  completed: "Obrađeno",
  failed: "Obrada nije uspela",
  retrying: "Ponovni pokušaj",
});

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

function broj(v) {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function imeEntiteta(tip) {
  const t = tekst(tip);
  if (IMENA_ENTITETA[t]) return IMENA_ENTITETA[t];
  const s = t.replace(/_/g, " ");
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : "";
}

export function imeStanja(status) {
  const s = tekst(status).toLowerCase();
  return IMENA_STANJA[s] || (s ? s : "Nepoznato stanje");
}

export function uEntitet(sirov) {
  const e = sirov || {};
  const v = e.value === null || e.value === undefined ? null : tekst(e.value);
  const p = broj(e.confidence);
  return {
    id: tekst(e.entity_id),
    tip: tekst(e.entity_type),
    naziv: imeEntiteta(e.entity_type),
    // `null` = izvlacenje NIJE naslo podatak. Prazan string bi tvrdio da je
    // podatak nadjen i da je prazan.
    vrednost: v || null,
    nadjen: !!v,
    pouzdanost: p,
    // Trazi pregled ako to server kaze ILI ako je pouzdanost ispod praga ILI
    // ako podatak uopste nije nadjen — fail-closed u sva tri smera.
    trebaPregled: e.needs_review === true || !v
      || (p !== null && p < PRAG_POUZDANOSTI),
    ispravljen: e.corrected === true,
  };
}

export function uPosao(sirov) {
  const o = sirov || {};
  const j = o.job || {};
  const d = o.dokument || {};
  const entiteti = (Array.isArray(o.entiteti) ? o.entiteti : []).map(uEntitet);
  const status = tekst(j.status).toLowerCase();
  return {
    id: tekst(j.id),
    status,
    stanjeTekst: imeStanja(status),
    zavrsen: ZAVRSNA.includes(status),
    uspesan: status === "completed",
    pao: status === "failed",
    cekaPregled: status === "awaiting_review",
    greska: tekst(j.last_error),
    fajl: tekst(j.original_filename),
    predmetId: tekst(j.predmet_id),
    pokusaja: broj(j.attempts),
    dokument: {
      tip: tekst(d.tip),
      tipNaziv: imeDokumenta(d.tip),
      pouzdanost: broj(d.tip_pouzdanost),
      ocr: d.ocr_koriscen === true,
      mozeBitiZastareo: d.tip_moze_biti_zastareo === true,
      napomena: tekst(d.napomena),
    },
    entiteti,
    zaPregled: entiteti.filter(e => e.trebaPregled),
    stranke: entiteti.filter(e => e.tip === "plaintiff" || e.tip === "defendant"),
  };
}

export function uPoslove(sirov) {
  const o = sirov || {};
  return {
    poslovi: (Array.isArray(o.rezultati) ? o.rezultati : [])
      .map(r => ({
        id: tekst(r && (r.job_id || r.id)),
        fajl: tekst(r && (r.filename || r.original_filename)),
        greska: tekst(r && r.greska),
      }))
      .filter(x => x.id || x.greska),
    ukupno: broj(o.ukupno),
    // Prekinut batch se NE precutkuje: fajlovi koji nisu ni zapoceti moraju
    // biti imenovani, inace advokat misli da su svi primljeni.
    nastavlja: o.nastavlja === true,
    preostali: (Array.isArray(o.preostali_fajlovi) ? o.preostali_fajlovi : [])
      .map(tekst).filter(Boolean),
  };
}

/**
 * Ishod finalizovanja. NIJEDNO polje ne sme da se procita kao „nema sukoba".
 */
export function uIshodUvoza(sirov) {
  const o = sirov || {};
  const coi = tekst(o.coi_status) || COI.NEPRIMENLJIVA;
  return {
    uspeh: o.ok === true,
    predmetId: tekst(o.predmet_id),
    naziv: tekst(o.naziv),
    coi,
    // Jedina istina koju ekran sme da izvede: da li je provera ZAKAZANA.
    coiZakazana: coi === COI.ZAKAZANA,
    coiOtkazala: coi === COI.NIJE_ZAKAZANA,
    coiNeprimenljiva: coi === COI.NEPRIMENLJIVA,
    klijentDodat: o.klijent_dodat === true,
    // Dva istoimena klijenta se NIKAD ne pogadjaju — server to izricito kaze.
    klijentNesiguran: o.klijent_nesiguran === true,
    klijentKandidata: (Array.isArray(o.klijent_kandidati) ? o.klijent_kandidati : []).length,
    rokDodat: o.rok_dodat === true,
    // `rok_dodat: false` ne razlikuje „dokument nema rok" od „rok nije
    // dovoljno dokazan". Razlog je zaseban podatak i prikazuje se.
    rokRazlog: tekst(o.rok_preskocen_razlog),
    dokumentPovezan: o.dokument_povezan === true,
  };
}

/** Provera pre finalizovanja. */
export function nedostaciUvoza({ strana, naziv } = {}) {
  const g = [];
  const s = tekst(strana);
  if (!s) {
    g.push("Izaberite koja strana je vaš klijent.");
  } else if (s !== "plaintiff" && s !== "defendant") {
    g.push("Strana mora biti tužilac ili tuženi.");
  }
  if (tekst(naziv).length > 200) {
    g.push("Naziv predmeta sme imati najviše 200 znakova.");
  }
  return g;
}
