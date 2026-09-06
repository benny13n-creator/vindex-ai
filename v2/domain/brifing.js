/* Vindex V2 — jutarnji brifing (H5), domen.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * MODEL NIJE AUTORITET NAD STANJEM IZVORA
 *
 * `ai_briefing` je tekst koji je napisao model. Backend uz njega vraca
 * MASINSKI proverive zastavice: `rokovi_dostupni`, `rocista_dostupna`,
 * `predmeti_dostupni`, `akcije_dostupne`. One su istina o tome sta je
 * procitano; recenica u tekstu nije.
 *
 * Zato ekran NIKAD ne izvodi „nema rokova" iz teksta. Ako je izvor pao,
 * odsustvo se ne sme prikazati kao nalaz — to je tacno onaj kvar koji je
 * vec jednom bio blocker (N5, B-U-001: brifing je tvrdio odsustvo iz palog
 * upita).
 * ─────────────────────────────────────────────────────────────────────────
 *
 * ZASTAVICA MORA BITI IZRICITO `true`. Odsutna zastavica znaci „ne znam",
 * a ne „procitano je" — fail-closed.
 */

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

function ceoBroj(v) {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

/** Imenovani izvori brifinga i njihova ljudska imena. */
export const IZVORI = Object.freeze([
  { kljuc: "rokovi_dostupni", naziv: "rokovi" },
  { kljuc: "rocista_dostupna", naziv: "ročišta" },
  { kljuc: "predmeti_dostupni", naziv: "predmeti" },
  { kljuc: "akcije_dostupne", naziv: "predložene radnje" },
]);

export function uBrifing(sirov) {
  const o = sirov || {};
  const s = o.statistike || {};

  // Izricito `true`. Sve ostalo (odsutno, `"true"`, `1`) je „ne znam".
  const nedostupni = IZVORI.filter(x => o[x.kljuc] !== true).map(x => x.naziv);

  return {
    datum: tekst(o.datum),
    tekstBrifinga: tekst(o.ai_briefing),
    // Tekst je upotrebljiv samo dok su SVI izvori o kojima govori procitani.
    // Delimicni brifing se prikazuje, ali sa izricitom ogradom iznad.
    potpun: nedostupni.length === 0,
    nedostupni,
    statistike: {
      aktivnihPredmeta: ceoBroj(s.aktivnih_predmeta),
      rokovaNedelja: ceoBroj(s.rokova_ove_nedelje),
      rokovaHitnih: ceoBroj(s.rokova_hitnih),
      rokovaPropustenih: ceoBroj(s.rokova_propustenih),
      rocistaDanas: ceoBroj(s.rocista_danas),
      rocistaSedmica: ceoBroj(s.rocista_sedmica),
      rocistaPropustenih: ceoBroj(s.rocista_propustenih),
    },
    hitniRokovi: uStavke(o.rokovi_hitni),
    propusteniRokovi: uStavke(o.rokovi_propusteni),
    rocistaDanas: uStavke(o.rocista_danas),
    propustenaRocista: uStavke(o.rocista_propustena),
    generisano: tekst(o.generisano_u),
  };
}

function uStavke(niz) {
  return (Array.isArray(niz) ? niz : [])
    .map(x => {
      const r = x || {};
      return {
        id: tekst(r.id),
        opis: tekst(r.dogadjaj || r.naziv || r.opis || r.sud),
        datum: tekst(r.datum_iso || r.datum),
        predmetId: tekst(r.predmet_id),
        predmet: tekst(r.predmet_naziv || r.predmet),
      };
    })
    .filter(x => x.opis || x.datum);
}

/**
 * Broj koji se sme prikazati kao nalaz. Kad izvor nije procitan, broj NIJE
 * nula nego nepoznat — `Number(undefined)` bi ovde dao 0 i time tvrdio da
 * rokova nema.
 */
export function brojIzvora(vrednost, dostupno) {
  return dostupno === true ? vrednost : null;
}

/**
 * Deli `**podebljano**` na delove za bezbedno iscrtavanje. Nikad se ne
 * koristi `innerHTML`: tekst dolazi od modela i ne sme da unese oznake.
 */
export function delovi(red) {
  const s = String(red == null ? "" : red);
  const out = [];
  const re = /\*\*([^*]+)\*\*/g;
  let i = 0, m;
  while ((m = re.exec(s)) !== null) {
    if (m.index > i) out.push({ jak: false, t: s.slice(i, m.index) });
    out.push({ jak: true, t: m[1] });
    i = m.index + m[0].length;
  }
  if (i < s.length) out.push({ jak: false, t: s.slice(i) });
  // Bez filtera praznih delova: nijedna grana ne moze da ga proizvede —
  // `[^*]+` trazi bar jedan znak, a oba iseka su cuvana poredjenjem duzina.
  // Nedostizna odbrana bi citaocu sugerisala zastitu koje nema.
  return out;
}
