/* Vindex V2 — domen NAPLATE (evidentiran rad, tajmer, fakture).
 *
 * Naplata je posao KANCELARIJE, ne pravni rad nad predmetom — zato zivi u
 * prostoru Kancelarija, iako se svaki unos vezuje za predmet. Dosije zadrzava
 * svojih pet zakljucanih celina.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * TRI IZNOSA KOJI SE NIKAD NE SABIRAJU (B2, `6bf80708`)
 *
 *   uneseno       evidentiran rad, ukupno
 *   obracunato    rad koji je usao u fakturu
 *   neobracunato  rad koji ceka fakturu
 *
 * Mesecni izvestaj je nekad sabirao NEOBRACUNAT rad kao `fakturisano_rsd`, pa
 * je kancelarija verovala da je izdala racune koje nije. Zato ova tri iznosa
 * imaju tri imena, tri recenice i nijedan zbir.
 *
 * FAKTURA SE PRAVI SAMO OD NEOBRACUNATOG RADA. Ponuditi vec fakturisan unos
 * znacilo bi ponuditi dvostruko naplacivanje istog posla klijentu.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * Cist modul: bez DOM-a, bez mreze, bez stanja.
 */

import { datum as datumTekst } from "./labels.js";

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

function broj(v) {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Iznos u dinarima. `null` kad iznosa nema — odsutno NIJE nula. */
export function dinar(v) {
  const n = broj(v);
  if (n === null) return null;
  return n.toLocaleString("sr-RS", { maximumFractionDigits: 0 }) + " RSD";
}

/** Trajanje iz sekundi u oblik koji se cita, ne u decimalni sat. */
export function trajanje(sekundi) {
  const s = broj(sekundi);
  if (s === null || s < 0) return "";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h && m) return `${h} h ${m} min`;
  if (h) return `${h} h`;
  return `${m} min`;
}

/** Jedan unos rada. */
export function uUnos(sirov) {
  const e = sirov || {};
  return {
    id: e.id || "",
    predmetId: tekst(e.predmet_id),
    opis: tekst(e.opis) || "Bez opisa",
    iznos: dinar(e.iznos_rsd),
    iznosBroj: broj(e.iznos_rsd),
    datum: datumTekst(e.datum || e.created_at),
    // `obracunato` je jedina stvar koja odlucuje sme li unos u novu fakturu.
    obracunato: Boolean(e.obracunato),
  };
}

/**
 * Unosi rada za predmet, razdvojeni po tome da li su vec fakturisani.
 * Zbirovi dolaze SA SERVERA kad ih posalje; ne racunaju se ovde, da se dve
 * strane ne bi razisle.
 */
export function uUnose(sirov) {
  const o = sirov || {};
  const svi = (Array.isArray(o.entries) ? o.entries : []).map(uUnos);
  return {
    svi,
    zaFakturu: svi.filter(u => !u.obracunato && u.iznosBroj !== null && u.iznosBroj > 0),
    ukupno: dinar(o.ukupno_rsd),
    obracunato: dinar(o.obracunato_rsd),
    neobracunato: dinar(o.neobracunato_rsd),
    sati: broj(o.ukupno_h),
  };
}

/** Stanje tajmera. Odsutan odgovor NIJE „ne radi" — to je nepoznato stanje. */
export function uTajmer(sirov) {
  if (!sirov || typeof sirov !== "object") {
    return { poznato: false, radi: false, predmetId: "", opis: "", od: "" };
  }
  const t = sirov.timer || {};
  return {
    poznato: true,
    radi: sirov.aktivan === true,
    predmetId: tekst(t.predmet_id),
    opis: tekst(t.opis),
    od: tekst(t.pocetak || t.created_at),
  };
}

/** Faktura u obliku za spisak. */
export function uFakturu(sirov) {
  const f = sirov || {};
  const stanje = tekst(f.status).toLowerCase();
  return {
    id: f.id || "",
    broj: tekst(f.broj_fakture || f.broj) || "Bez broja",
    klijent: tekst(f.klijent_naziv),
    iznos: dinar(f.iznos_sa_pdv != null ? f.iznos_sa_pdv : f.iznos),
    datum: datumTekst(f.datum_fakture || f.created_at),
    stanje,
    // „placena" je jedina vrednost koja znaci da je novac stigao. Sve ostalo
    // je i dalje potrazivanje — i tako se prikazuje.
    placena: stanje === "placena",
  };
}

export function uFakture(sirov) {
  const niz = (sirov && sirov.fakture) || [];
  return Array.isArray(niz) ? niz.map(uFakturu) : [];
}

/** Sta nedostaje da se unos rada moze sacuvati. */
export function nedostaciUnosa({ predmetId, opis, iznos } = {}) {
  const g = [];
  if (!tekst(predmetId)) g.push("Izaberite predmet.");
  if (tekst(opis).length < 1) g.push("Opis rada je obavezan.");
  const n = broj(String(iznos || "").replace(/\s/g, "").replace(/\./g, "").replace(",", "."));
  if (n === null || n <= 0) g.push("Iznos mora biti broj veći od nule.");
  return g;
}

/** Telo za `POST /billing/entries`. */
export function uTeloUnosa({ predmetId, opis, iznos, datum } = {}) {
  const n = Number(String(iznos || "").replace(/\s/g, "").replace(/\./g, "").replace(",", "."));
  const telo = {
    predmet_id: tekst(predmetId),
    opis: tekst(opis),
    tip: "tarifa",
    iznos_rsd: Number.isFinite(n) ? n : 0,
  };
  if (tekst(datum)) telo.datum = tekst(datum);
  return telo;
}
