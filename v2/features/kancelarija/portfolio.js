/* Vindex V2 — Portfolio kancelarije (F9), unutar Kancelarija.
 *
 * Ucitava se ODVOJENO od jezgra (isti obrazac kao Naplata/Tim) -- pad ovog
 * dela ne sme da obori ostatak Kancelarije.
 */

import { dohvati } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika } from "../../platform/errors.js";
import { idiNa, putanjaZa } from "../../platform/router.js";
import { uPortfolio } from "../../domain/portfolio.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

function rokRed(r, ciklus) {
  const li = el("li");
  const red = el("p", "v2-forma__red");
  const veza = el("a", "", r.predmetNaziv);
  veza.href = putanjaZa("predmet", r.predmetId) + "#celina-rokovi";
  ciklus.slusaj(veza, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("predmet", r.predmetId);
  });
  red.appendChild(veza);
  red.appendChild(el("span", "v2-meta", " · " + r.dogadjaj + " · " + r.datum));
  li.appendChild(red);
  return li;
}

export async function ucitajPortfolio({ signal } = {}) {
  try {
    return { ucitano: true, portfolio: uPortfolio(await dohvati("/portfolio/dashboard", { signal })) };
  } catch (e) {
    if (jePrekid(e)) throw e;
    return { ucitano: false, greska: e };
  }
}

export function sadrzajPortfolia(d, ciklus) {
  const okvir = document.createDocumentFragment();
  if (!d.ucitano) {
    const p = el("div", "v2-poruka v2-poruka--greska");
    p.appendChild(el("p", "v2-poruka__naslov", "Portfolio nije učitan"));
    p.appendChild(el("p", "v2-poruka__telo", porukaZaKorisnika(d.greska) + " Ovo ne znači da nema predmeta."));
    okvir.appendChild(p);
    return okvir;
  }

  const p = d.portfolio;
  if (p.summary) okvir.appendChild(el("p", "v2-proza", p.summary));

  const dl = el("dl", "v2-polja");
  const par = (naziv, vrednost) => {
    const d2 = el("div", "v2-polja__par");
    d2.appendChild(el("dt", "v2-polje", naziv));
    d2.appendChild(el("dd", "v2-polja__v v2-mono", vrednost));
    return d2;
  };
  dl.appendChild(par("Aktivnih predmeta", String(p.ukupnoAktivnih)));
  dl.appendChild(par("Ukupno predmeta", String(p.ukupnoPredmeta)));
  okvir.appendChild(dl);

  if (p.hitniRokovi.length) {
    okvir.appendChild(el("h3", "v2-natkapa", "Hitni rokovi"));
    const ul = el("ul", "v2-lista-tanka");
    for (const r of p.hitniRokovi) ul.appendChild(rokRed(r, ciklus));
    okvir.appendChild(ul);
  }

  if (p.neaktivni.length) {
    okvir.appendChild(el("h3", "v2-natkapa", "Bez aktivnosti 30+ dana"));
    const ul = el("ul", "v2-lista-tanka");
    for (const n of p.neaktivni) {
      const li = el("li");
      const veza = el("a", "", n.naziv);
      veza.href = putanjaZa("predmet", n.predmetId);
      ciklus.slusaj(veza, "click", (e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        e.preventDefault();
        idiNa("predmet", n.predmetId);
      });
      li.appendChild(veza);
      if (n.poslednjaIzmena) li.appendChild(el("span", "v2-meta", " · poslednja izmena " + n.poslednjaIzmena));
      ul.appendChild(li);
    }
    okvir.appendChild(ul);
  }

  return okvir;
}
