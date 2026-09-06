/* Vindex V2 — poređenje dokumenata unutar predmeta (C7), domenski sloj.
 *
 * Backend (`routers/cross_doc.py::cross_doc_predmet`) vec validira citate
 * (`_validate_konflikti_citati`) -- konflikt bez verbatim citata iz izvornog
 * dokumenta se ne vraca. Ovaj sloj samo prevodi vec proveren rezultat u
 * citljiv oblik, ne dodaje sopstvenu proveru.
 */

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

export function uPoredjenje(sirov) {
  const o = sirov || {};
  return {
    pitanje: tekst(o.pravno_pitanje),
    brojDokumenata: Number.isFinite(o.broj_dokumenata) ? o.broj_dokumenata : 0,
    nazivi: Array.isArray(o.nazivi) ? o.nazivi.map(tekst).filter(Boolean) : [],
    rezime: tekst(o.rezime),
    konflikti: Array.isArray(o.konflikti) ? o.konflikti.map(k => ({
      opis: tekst(k && (k.opis || k.konflikt)),
      citat: tekst(k && k.citat),
      dokument: tekst(k && k.dokument),
    })).filter(k => k.opis) : [],
    slicnosti: Array.isArray(o.slicnosti) ? o.slicnosti.map(tekst).filter(Boolean) : [],
    preporuke: Array.isArray(o.preporuke) ? o.preporuke.map(p => ({
      tekst: tekst(p && (p.tekst || p.preporuka)),
      prioritet: Number.isFinite(p && p.prioritet) ? p.prioritet : null,
    })).filter(p => p.tekst) : [],
    zakljucak: tekst(o.pravni_zakljucak),
    // `null` znaci "nema upozorenja", NE prazan string -- odsustvo upozorenja
    // je informacija (nijedan dokument nije skracen), ne izostanak podatka.
    upozorenjeSkracenja: o.upozorenje_skracenja == null ? null : tekst(o.upozorenje_skracenja),
  };
}

export function validanBrojDokumenata(brojOznacenih) {
  return brojOznacenih >= 2 && brojOznacenih <= 5;
}
