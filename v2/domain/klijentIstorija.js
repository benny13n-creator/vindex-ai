/* Vindex V2 — istorija (timeline) klijenta (E6), domenski sloj.
 *
 * Prethodna sesija je pogresno zakljucila da E6 nema backend, jer je
 * trazila "timeline" u routers/intelligence_timeline.py (zivot PREDMETA,
 * ne klijenta -- drugi capability pod slicnim imenom). Stvaran backend:
 * klijenti/router.py::get_timeline (GET /klijenti/{id}/timeline) --
 * agregira klijent_komunikacija + predmet-otvoren/zatvoren dogadjaje,
 * tenant-izolovan (_verify_owns_klijent), grupisano po godini.
 *
 * NE prikazuje se backend-ovo `ikona` polje (emoji) -- vlasnicki kanon
 * zabranjuje generic ikone; tip dogadjaja se cita kao TEKST (v. `nazivTipa`).
 */

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

const TIP_LABELS = {
  poziv: "Poziv", email: "Email", sastanak: "Sastanak",
  whatsapp: "WhatsApp", viber: "Viber", beleska: "Beleška",
  predmet_otvoren: "Predmet otvoren", predmet_zatvoren: "Predmet zatvoren",
};

export function nazivTipa(sirovo) {
  const k = tekst(sirovo).toLowerCase();
  return TIP_LABELS[k] || tekst(sirovo) || "Događaj";
}

function uDogadjaj(sirov) {
  const e = sirov || {};
  return {
    tip: tekst(e.tip),
    nazivTipa: nazivTipa(e.tip),
    datum: tekst(e.datum),
    opis: tekst(e.opis),
    izvor: tekst(e.izvor),
  };
}

export function uIstorijuKlijenta(sirov) {
  const o = sirov || {};
  const dogadjaji = (Array.isArray(o.timeline) ? o.timeline : []).map(uDogadjaj).filter(d => d.datum);
  const poGodini = o.by_year && typeof o.by_year === "object" ? o.by_year : {};
  return {
    dogadjaji,
    godine: Object.keys(poGodini).sort((a, b) => b.localeCompare(a)),
    ukupno: Number.isFinite(o.ukupno) ? o.ukupno : dogadjaji.length,
  };
}
