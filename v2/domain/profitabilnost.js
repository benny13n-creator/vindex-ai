/* Vindex V2 — profitabilnost predmeta (B20) i kancelarije (F11), domenski
 * sloj. Deli `case_profitability` VIEW izmedju predmet-nivoa (B20,
 * routers/profitabilnost.py::profitabilnost_predmeta) i kancelarija-nivoa
 * (F11, ::profitabilnost_pregled) -- oba vracaju istu "ocena" (zelena/
 * zuta/crvena) koja se OVDE dobija tekstualnim nazivom, ne samo bojom
 * (§42: no hue-only semantics).
 */
import { dinar } from "./naplata.js";

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

const OCENA_NAZIVI = { zelena: "Profitabilan", zuta: "Granično", crvena: "Neprofitabilan" };

export function nazivOcene(sirovo) {
  const k = tekst(sirovo).toLowerCase();
  return OCENA_NAZIVI[k] || "—";
}

function uFinansije(sirov) {
  const f = sirov || {};
  return {
    naplaceno: dinar(f.ukupno_naplaceno_rsd),
    fakturisano: dinar(f.fakturisano_rsd),
    nefakturisano: dinar(f.nefakturisano_rsd),
    naplativostProcenat: Number.isFinite(f.naplativost_procenat) ? f.naplativost_procenat : null,
    ukupnoSati: Number.isFinite(f.ukupno_sati) ? f.ukupno_sati : null,
    satnica: dinar(f.satnica_rsd),
    brojUnosa: Number.isFinite(f.broj_unosa) ? f.broj_unosa : 0,
  };
}

export function uProfitabilnostPredmeta(sirov) {
  const o = sirov || {};
  return {
    naziv: tekst(o.predmet_naziv) || "Predmet bez naziva",
    ocena: tekst(o.ocena),
    ocenaNaziv: nazivOcene(o.ocena),
    finansije: uFinansije(o.finansije),
    aiPreporuka: tekst(o.ai_preporuka),
  };
}

export function uProfitabilnostPregled(sirov) {
  const o = sirov || {};
  const st = o.statistika || {};
  return {
    predmeti: (Array.isArray(o.predmeti) ? o.predmeti : []).map(p => ({
      predmetId: tekst(p && p.predmet_id),
      naziv: tekst(p && p.predmet_naziv) || "Predmet bez naziva",
      ocena: tekst(p && p.ocena),
      ocenaNaziv: nazivOcene(p && p.ocena),
      naplaceno: dinar(p && p.ukupno_naplaceno_rsd),
      nefakturisano: dinar(p && p.nefakturisano_rsd),
      naplativostProcenat: Number.isFinite(p && p.naplativost_procenat) ? p.naplativost_procenat : null,
    })),
    ukupnoPredmeta: Number.isFinite(o.ukupno_predmeta) ? o.ukupno_predmeta : 0,
    statistika: {
      naplaceno: dinar(st.ukupno_naplaceno_rsd),
      nefakturisano: dinar(st.ukupno_nefakturisano),
      prosecnaSatnica: dinar(st.prosecna_satnica),
      zelenih: Number.isFinite(st.zelenih) ? st.zelenih : 0,
      zutih: Number.isFinite(st.zutih) ? st.zutih : 0,
      crvenih: Number.isFinite(st.crvenih) ? st.crvenih : 0,
    },
  };
}
