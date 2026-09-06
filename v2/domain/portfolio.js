/* Vindex V2 — Portfolio kancelarije (F9), domenski sloj.
 *
 * "Sve je pod kontrolom" u summary polju NIJE izmisljena tvrdnja -- backend
 * (routers/portfolio.py) je racuna iz stvarnih brojeva (0 rokova u 7 dana I
 * 0 neaktivnih predmeta). Ovaj sloj ne dodaje sopstvenu procenu, samo
 * prenosi izracunato.
 */

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

function uRok(sirov) {
  const r = sirov || {};
  return {
    predmetId: tekst(r.predmet_id),
    predmetNaziv: tekst(r.predmet_naziv) || "Nepoznat predmet",
    dogadjaj: tekst(r.dogadjaj),
    datum: tekst(r.datum_iso),
    vaznost: tekst(r.vaznost),
  };
}

export function uPortfolio(sirov) {
  const o = sirov || {};
  return {
    ukupnoPredmeta: Number.isFinite(o.ukupno_predmeta) ? o.ukupno_predmeta : 0,
    ukupnoAktivnih: Number.isFinite(o.ukupno_aktivnih) ? o.ukupno_aktivnih : 0,
    poStatusu: o.po_statusu && typeof o.po_statusu === "object" ? o.po_statusu : {},
    rokovi7: Array.isArray(o.rokovi_7_dana) ? o.rokovi_7_dana.map(uRok) : [],
    hitniRokovi: Array.isArray(o.hitni_rokovi) ? o.hitni_rokovi.map(uRok) : [],
    neaktivni: Array.isArray(o.neaktivni_30_dana) ? o.neaktivni_30_dana.map(n => ({
      predmetId: tekst(n && n.predmet_id),
      naziv: tekst(n && n.naziv) || "Predmet bez naziva",
      poslednjaIzmena: tekst(n && n.poslednja_izmena),
    })) : [],
    summary: tekst(o.summary),
  };
}
