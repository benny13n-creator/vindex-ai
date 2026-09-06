/* Vindex V2 — Firm Health Index (F10), unutar Kancelarija.
 *
 * Ucitava se ODVOJENO, isti razlog kao Portfolio/Naplata. `403` (bez prava)
 * je legitimno stanje, ne greska -- prikazuje se kao "nedostupno", ne kao
 * pad ucitavanja.
 */

import { dohvati } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { uHealthIndex } from "../../domain/firmHealthIndex.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

export async function ucitajZdravljeFirme({ signal } = {}) {
  try {
    return { stanje: "ucitano", zdravlje: uHealthIndex(await dohvati("/api/firm/health-index", { signal })) };
  } catch (e) {
    if (jePrekid(e)) throw e;
    if (e && e.vrsta === VRSTA.ZABRANJENO) return { stanje: "nema_pravo" };
    return { stanje: "palo", greska: e };
  }
}

export function sadrzajZdravljaFirme(d, ciklus) {
  const okvir = document.createDocumentFragment();

  if (d.stanje === "nema_pravo") {
    okvir.appendChild(el("p", "v2-celina__prazno", "Ova funkcija nije dostupna za vaš nalog."));
    return okvir;
  }
  if (d.stanje === "palo") {
    const p = el("div", "v2-poruka v2-poruka--greska");
    p.appendChild(el("p", "v2-poruka__naslov", "Zdravlje kancelarije nije učitano"));
    p.appendChild(el("p", "v2-poruka__telo", porukaZaKorisnika(d.greska)));
    okvir.appendChild(p);
    return okvir;
  }

  const z = d.zdravlje;
  if (z.izKesa) {
    okvir.appendChild(el("p", "v2-forma__poruka v2-forma__poruka--upozorenje",
      "Prikazana je poslednja izračunata ocena, ne trenutno stanje. Osvežite za novo računanje."));
  }

  const dl = el("dl", "v2-polja");
  const par = (naziv, vrednost) => {
    const d2 = el("div", "v2-polja__par");
    d2.appendChild(el("dt", "v2-polje", naziv));
    d2.appendChild(el("dd", "v2-polja__v v2-mono", vrednost));
    return d2;
  };
  if (z.skor !== null) dl.appendChild(par("Skor", z.skor + "/100"));
  if (z.ocena) dl.appendChild(par("Ocena", z.ocena));
  okvir.appendChild(dl);

  if (z.chiefPartner) okvir.appendChild(el("p", "v2-proza", z.chiefPartner));

  if (z.komponente.length) {
    okvir.appendChild(el("h3", "v2-natkapa", "Komponente"));
    const ul = el("ul", "v2-lista-tanka");
    for (const k of z.komponente) {
      const li = el("li");
      const red = el("p", "v2-forma__red");
      red.appendChild(el("span", "", k.naziv));
      if (k.skor !== null) red.appendChild(el("span", "v2-mono", ` ${k.skor}/${k.max ?? "?"}`));
      li.appendChild(red);
      ul.appendChild(li);
    }
    okvir.appendChild(ul);
  }

  if (z.upozorenja.length) {
    okvir.appendChild(el("h3", "v2-natkapa", "Upozorenja"));
    const ul = el("ul", "v2-lista-tanka");
    for (const u of z.upozorenja) ul.appendChild(el("li", "", u));
    okvir.appendChild(ul);
  }

  if (z.institucionalniRizici.length) {
    okvir.appendChild(el("h3", "v2-natkapa", "Institucionalni rizici"));
    const ul = el("ul", "v2-lista-tanka");
    for (const r of z.institucionalniRizici) {
      const li = el("li");
      li.appendChild(el("p", "", r.naslov));
      if (r.opis) li.appendChild(el("p", "v2-meta", r.opis));
      ul.appendChild(li);
    }
    okvir.appendChild(ul);
  }

  return okvir;
}
