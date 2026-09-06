/* Vindex V2 — profitabilnost predmeta (B20), unutar Dosije/Naplata. */

import { dohvati } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika } from "../../platform/errors.js";
import { uProfitabilnostPredmeta } from "../../domain/profitabilnost.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

export async function ucitajProfitabilnostPredmeta(predmetId, { signal } = {}) {
  try {
    return { ucitano: true, podaci: uProfitabilnostPredmeta(await dohvati(
      `/api/profitabilnost/predmet/${encodeURIComponent(predmetId)}`, { signal })) };
  } catch (e) {
    if (jePrekid(e)) throw e;
    return { ucitano: false, greska: e };
  }
}

export function blokProfitabilnostiPredmeta(d) {
  const b = el("div", "v2-podblok");
  b.appendChild(el("h3", "v2-natkapa", "Profitabilnost predmeta"));

  if (!d.ucitano) {
    b.appendChild(el("p", "v2-celina__prazno",
      "Profitabilnost nije učitana. " + porukaZaKorisnika(d.greska)));
    return b;
  }

  const p = d.podaci;
  const dl = el("dl", "v2-polja");
  const par = (naziv, vrednost) => {
    const d2 = el("div", "v2-polja__par");
    d2.appendChild(el("dt", "v2-polje", naziv));
    d2.appendChild(el("dd", "v2-polja__v v2-mono", vrednost));
    return d2;
  };
  if (p.ocenaNaziv !== "—") dl.appendChild(par("Ocena", p.ocenaNaziv));
  if (p.finansije.naplaceno !== null) dl.appendChild(par("Naplaćeno", p.finansije.naplaceno));
  if (p.finansije.nefakturisano !== null) dl.appendChild(par("Nefakturisano", p.finansije.nefakturisano));
  if (p.finansije.naplativostProcenat !== null) dl.appendChild(par("Naplativost", p.finansije.naplativostProcenat + "%"));
  if (p.finansije.satnica !== null) dl.appendChild(par("Efektivna satnica", p.finansije.satnica));
  b.appendChild(dl);

  if (p.aiPreporuka) {
    b.appendChild(el("h4", "v2-natkapa", "AI preporuka"));
    b.appendChild(el("p", "v2-meta", "Predlog modela nad izračunatim brojevima gore — subjektivna procena, ne finansijski savet."));
    b.appendChild(el("p", "v2-proza", p.aiPreporuka));
  }

  return b;
}
