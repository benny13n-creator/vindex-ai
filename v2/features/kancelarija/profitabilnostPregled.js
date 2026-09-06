/* Vindex V2 — profitabilnost kancelarije (F11), unutar Kancelarija/Portfolio. */

import { dohvati } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika } from "../../platform/errors.js";
import { idiNa, putanjaZa } from "../../platform/router.js";
import { uProfitabilnostPregled } from "../../domain/profitabilnost.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

export async function ucitajProfitabilnostPregled({ signal } = {}) {
  try {
    return { ucitano: true, podaci: uProfitabilnostPregled(await dohvati("/api/profitabilnost/pregled", { signal })) };
  } catch (e) {
    if (jePrekid(e)) throw e;
    return { ucitano: false, greska: e };
  }
}

export function blokProfitabilnostiPregleda(d, ciklus) {
  const b = el("div", "v2-podblok");

  if (!d.ucitano) {
    b.appendChild(el("p", "v2-celina__prazno",
      "Profitabilnost nije učitana. " + porukaZaKorisnika(d.greska)));
    return b;
  }

  const p = d.podaci;
  if (!p.predmeti.length) {
    b.appendChild(el("p", "v2-celina__prazno", "Nema dovoljno naplativih podataka za rang listu."));
    return b;
  }

  const dl = el("dl", "v2-polja");
  const par = (naziv, vrednost) => {
    const d2 = el("div", "v2-polja__par");
    d2.appendChild(el("dt", "v2-polje", naziv));
    d2.appendChild(el("dd", "v2-polja__v v2-mono", vrednost));
    return d2;
  };
  if (p.statistika.naplaceno !== null) dl.appendChild(par("Ukupno naplaćeno", p.statistika.naplaceno));
  if (p.statistika.nefakturisano !== null) dl.appendChild(par("Nefakturisano", p.statistika.nefakturisano));
  b.appendChild(dl);
  b.appendChild(el("p", "v2-meta",
    `${p.statistika.zelenih} profitabilnih · ${p.statistika.zutih} graničnih · ${p.statistika.crvenih} neprofitabilnih`));

  const ul = el("ul", "v2-lista-tanka");
  for (const pr of p.predmeti) {
    const li = el("li");
    const red = el("p", "v2-forma__red");
    if (pr.predmetId) {
      const veza = el("a", "", pr.naziv);
      veza.href = putanjaZa("predmet", pr.predmetId);
      ciklus.slusaj(veza, "click", (e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        e.preventDefault();
        idiNa("predmet", pr.predmetId);
      });
      red.appendChild(veza);
    } else {
      red.appendChild(el("span", "", pr.naziv));
    }
    if (pr.ocenaNaziv !== "—") red.appendChild(el("span", "v2-meta", " · " + pr.ocenaNaziv));
    if (pr.naplaceno !== null) red.appendChild(el("span", "v2-mono", " " + pr.naplaceno));
    li.appendChild(red);
    ul.appendChild(li);
  }
  b.appendChild(ul);

  return b;
}
