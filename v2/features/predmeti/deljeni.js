/* Vindex V2 — predmeti deljeni SA mnom (B18, drugi kraj saradnje).
 *
 * `v2/features/dosije/saradnja.js` pokriva VLASNIKOVU stranu (dodaj/ukloni
 * saradnika na sopstvenom predmetu). Ovo je SARADNIKOVA strana: pre ovog
 * fajla, korisnik kome je predmet deljen NIJE IMAO NAČIN da ga uopšte
 * pronađe u V2 -- backend (`GET /api/saradnja/moji-predmeti`) je postojao,
 * ali ništa u V2 ga nije pozivalo. Bez ovoga saradnja je bila upravljiva
 * SAMO sa vlasnikove strane -- pozvani kolega nije imao gde da vidi šta mu
 * je dodeljeno.
 *
 * Namerno ODVOJEN, malen blok u Predmeti registru (ne nova celina/prostor):
 * za većinu naloga ova lista je prazna (nema saradnje), pa stalna praznina
 * ne zaslužuje sopstvenu navigacionu stavku.
 */

import { dohvati } from "../../platform/http.js";
import { jePrekid } from "../../platform/errors.js";
import { putanjaZa, idiNaPutanju } from "../../platform/router.js";
import { nazivUloge } from "../../domain/saradnja.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

export function uDeljenPredmet(sirov) {
  const p = sirov || {};
  return {
    id: tekst(p.predmet_id),
    naziv: tekst(p.naziv) || "Predmet bez naziva",
    ulogaNaziv: nazivUloge(p.uloga),
  };
}

export async function ucitajDeljenePredmete({ signal } = {}) {
  try {
    const r = await dohvati("/api/saradnja/moji-predmeti", { signal });
    const lista = Array.isArray(r && r.predmeti) ? r.predmeti : [];
    return { ucitano: true, predmeti: lista.map(uDeljenPredmet).filter(p => p.id) };
  } catch (e) {
    if (jePrekid(e)) throw e;
    // Sekundaran blok: pad ne sme da obori registar, samo se tiho izostavlja
    // (isti princip kao Naplata/Saradnja u Dosijeu -- v. te module za precedent).
    return { ucitano: false, predmeti: [] };
  }
}

/** Vraca `null` kad nema sta da se prikaze -- pozivalac tada nista ne dodaje. */
export function sekcijaDeljenihPredmeta(d, ciklus) {
  if (!d || !d.ucitano || !d.predmeti.length) return null;

  const s = el("section", "v2-podblok");
  s.appendChild(el("h2", "v2-natkapa", "Predmeti u kojima sarađujem"));
  const ul = el("ul", "v2-lista-tanka");
  for (const p of d.predmeti) {
    const li = el("li");
    const veza = el("a", "", p.naziv);
    veza.href = putanjaZa("predmet", p.id);
    ciklus.slusaj(veza, "click", (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
      e.preventDefault();
      idiNaPutanju(veza.href);
    });
    li.appendChild(veza);
    li.appendChild(el("span", "v2-meta", " · " + p.ulogaNaziv));
    ul.appendChild(li);
  }
  s.appendChild(ul);
  return s;
}
