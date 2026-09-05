/* Vindex V2 — domen SUDSKE PRAKSE.
 *
 * Praksa zivi u prostoru ZNANJE, kao druga stvar koju advokat moze da pita:
 * „sta kaze propis" (RAG nad zakonima) i „sta je sud vec presudio". To NISU
 * dva prostora nego dva pitanja u istom.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * ODLUKA NIJE ODGOVOR
 *
 * `/api/praksa/search` vraca STVARNE odluke iz korpusa — broj, sud, datum i
 * tekst izreke. To nije model koji nesto tvrdi, nego dokument koji postoji.
 * Zato se ovde NE dodaje nikakva ograda o pouzdanosti modela: ogradjivati
 * doslovan citat presude znacilo bi tvrditi da je i on generisan.
 *
 * Ono sto se NE SME izgubiti je CITAT: `citat_format` je jedini oblik u kome
 * advokat odluku moze da upotrebi u podnesku. Ako ga backend ne posalje,
 * sastavlja se iz sud/broj/datum — ali samo od delova koji stvarno postoje,
 * nikad sa izmisljenim „nepoznat sud".
 * ─────────────────────────────────────────────────────────────────────────
 *
 * Cist modul: bez DOM-a, bez mreze, bez stanja.
 */

/** Oblasti koje backend prihvata. Nista van ovog spiska se ne salje. */
export const OBLASTI = Object.freeze(["Građanska", "Zaštita prava", "Upravna", "Krivična"]);

function tekst(v) {
  return String(v == null ? "" : v).trim();
}


/**
 * Uklanja nedovrsen rep iz citata koji je server sastavio bez datuma.
 * Ostavlja sve sto stvarno postoji; nista se ne dopunjuje.
 */
export function ocistiCitat(s) {
  return String(s || "")
    .replace(/,?\s*od\s*\.?\s*$/i, "")   // „…, od ." / „…, od"
    .replace(/[\s,;]+$/, "")
    .trim();
}

/** Datum odluke u obliku koji advokat prepisuje. */
function datumOdluke(iso) {
  const s = tekst(iso);
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  return m ? `${m[3]}.${m[2]}.${m[1]}.` : s;
}

/**
 * Jedna odluka.
 *
 * `score` se NE prikazuje: kosinusna slicnost prema upitu ne govori nista o
 * pravnoj vrednosti presude, a broj pored citata bi se citao kao ocena.
 */
export function uOdluku(sirov) {
  const d = sirov || {};
  const broj = tekst(d.decision_number);
  const sud = tekst(d.court);
  const datum = tekst(d.decision_date);
  // `citat_format` sa servera moze doci nedovrsen kada odluci nedostaje datum
  // („Ustavni sud, Уж-1/2021, od ."). Takav rep se ODSECA, ne popunjava —
  // izmisljen datum u citatu presude je najgora moguca greska ovog ekrana.
  const citat = ocistiCitat(tekst(d.citat_format))
    || [sud, broj, datum ? "od " + datumOdluke(datum) : ""].filter(Boolean).join(", ");
  return {
    broj,
    sud,
    oblast: tekst(d.matter),
    datum: datum ? datumOdluke(datum) : "",
    datumIso: datum,
    izreka: tekst(d.izreka_preview) || tekst(d.izreka_full),
    izrekaCela: tekst(d.izreka_full),
    obrazlozenje: tekst(d.obrazlozenje_full),
    citat,
    // Odluka bez broja se ne moze citirati; prikazuje se, ali se ne nudi
    // kao izvor koji advokat sme da prepise u podnesak.
    citljiva: Boolean(broj),
  };
}

/** Rezultat pretrage. Prazan rezultat NIJE greska i ne prikazuje se kao pad. */
export function uRezultat(sirov) {
  const o = sirov || {};
  const odluke = Array.isArray(o.decisions) ? o.decisions.map(uOdluku) : [];
  return {
    odluke,
    ukupno: Number.isFinite(o.total) ? o.total : odluke.length,
    strana: Number.isFinite(o.page) ? o.page : 1,
    limit: Number.isFinite(o.limit) ? o.limit : odluke.length,
  };
}

/**
 * Telo pretrage. Prazan filter se NE salje kao prazan string — backend bi ga
 * odbio sa 400, a korisnik bi dobio gresku koju nije napravio.
 */
export function uUpit({ upit, oblast, sud, odGodine, doGodine, limit = 10, offset = 0 } = {}) {
  const telo = { limit, offset };
  const q = tekst(upit);
  if (q) telo.query = q;
  if (OBLASTI.includes(tekst(oblast))) telo.matter = tekst(oblast);
  if (tekst(sud)) telo.court = tekst(sud);
  const od = Number(odGodine), doG = Number(doGodine);
  if (Number.isInteger(od) && od > 1900) telo.year_from = od;
  if (Number.isInteger(doG) && doG > 1900) telo.year_to = doG;
  return telo;
}

/** Sta nedostaje da pretraga ima smisla. Prazan niz = moze. */
export function nedostaciUpita(unos) {
  const telo = uUpit(unos);
  // Bar jedan kriterijum mora postojati; pretraga bez ijednog filtera vraca
  // korpus u proizvoljnom redosledu, sto nije odgovor ni na sta.
  const imaKriterijum = Boolean(telo.query || telo.matter || telo.court
                                || telo.year_from || telo.year_to);
  return imaKriterijum ? [] : ["Unesite pojam ili izaberite bar jedan filter."];
}
