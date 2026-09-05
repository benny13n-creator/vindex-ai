/* Vindex V2 — citanje spisa.
 *
 * Spis se cita u punoj sirini za citanje (72ch), a ne u panelu sa strane i ne
 * u modalu. Pravni tekst se cita u redovima, ne u prozorcicu.
 *
 * URL je `/app-v2/predmet/<id>?spis=<dokId>` — deep link radi, `back` vraca u
 * Dosije, a lepljiva traka i dalje kaze u kom ste predmetu. Citac NIJE
 * poseban prostor: dokument bez predmeta nema smisla.
 *
 * STO OVDE NEMA:
 *   - nema „AI sazetka" umesto teksta. Prikazuje se ono sto u bazi stoji.
 *   - nema tvrdnje da je dokument prazan kad ga samo nismo dobili: backend
 *     razlikuje `dostupan:false` (teksta nema) od pada poziva, i ta razlika
 *     se korisniku KAZE, jer „prazan dokument" i „nismo uspeli da ga
 *     ucitamo" vode u dve razlicite radnje.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { dohvati } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { putanjaPreuzimanja } from "./api.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

/** Tekst u pasuse. Prazan red deli pasus; jedan prelom ostaje prelom. */
function uPasuse(tekst) {
  const okvir = document.createDocumentFragment();
  const delovi = String(tekst || "").replace(/\r\n/g, "\n").split(/\n{2,}/);
  for (const d of delovi) {
    const t = d.trim();
    if (!t) continue;
    const p = el("p", "v2-citac__pasus");
    const redovi = t.split("\n");
    redovi.forEach((r, i) => {
      if (i) p.appendChild(document.createElement("br"));
      p.appendChild(document.createTextNode(r));
    });
    okvir.appendChild(p);
  }
  if (!okvir.childNodes.length) okvir.appendChild(el("p", "v2-citac__pasus", ""));
  return okvir;
}

export function montirajCitac(kontejner, kontekst, { predmetId, spisId, nazadNaDosije }) {
  const ciklus = napraviCiklus();

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--predmet");
  const sadrzaj = el("div", "v2-citac");
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  unutra.appendChild(sadrzaj);
  kontejner.appendChild(unutra);

  sadrzaj.appendChild(el("p", "v2-celina__prazno", "Spis se učitava…"));

  (async () => {
    const prekidac = ciklus.prekidac();
    let d;
    try {
      d = await dohvati(
        `/api/predmeti/${encodeURIComponent(predmetId)}/dokumenti/${encodeURIComponent(spisId)}/preview`,
        { signal: prekidac.signal });
    } catch (e) {
      if (jePrekid(e) || ciklus.ugasen) return;
      if (e && e.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      const p = el("div", "v2-poruka v2-poruka--greska");
      p.appendChild(el("p", "v2-poruka__naslov", "Spis nije učitan"));
      p.appendChild(el("p", "v2-poruka__telo",
        porukaZaKorisnika(e) + " Ovo ne znači da je spis prazan niti da je izgubljen."));
      const nazad = el("button", "v2-dugme", "Nazad na Dosije");
      nazad.type = "button";
      ciklus.slusaj(nazad, "click", nazadNaDosije);
      p.appendChild(nazad);
      sadrzaj.replaceChildren(p);
      return;
    }
    if (ciklus.ugasen) return;

    const okvir = document.createDocumentFragment();

    const zaglavlje = el("header", "v2-citac__zaglavlje");
    const nazad = el("button", "v2-tekst-akcija v2-citac__nazad", "← Nazad na Dosije");
    nazad.type = "button";
    ciklus.slusaj(nazad, "click", nazadNaDosije);
    zaglavlje.appendChild(nazad);

    const h1 = el("h1", "v2-naslov v2-citac__naziv", d.naziv_fajla || "Spis");
    zaglavlje.appendChild(h1);

    const linija = el("p", "v2-citac__linija");
    if (d.velicina_kb) linija.appendChild(el("span", "v2-mono", `${d.velicina_kb} KB`));
    if (d.status) linija.appendChild(el("span", "", String(d.status)));
    const preuzmi = el("a", "v2-tekst-veza", "Preuzmi original");
    preuzmi.href = putanjaPreuzimanja(predmetId, spisId);
    linija.appendChild(preuzmi);
    zaglavlje.appendChild(linija);
    okvir.appendChild(zaglavlje);

    if (d.dostupan && String(d.tekst || "").trim()) {
      const telo = el("article", "v2-citac__telo");
      telo.appendChild(uPasuse(d.tekst));
      okvir.appendChild(telo);
    } else {
      // `dostupan:false` je TVRDNJA BACKENDA da teksta nema, ne nasa pretpostavka.
      const p = el("div", "v2-poruka");
      p.appendChild(el("p", "v2-poruka__naslov", "Tekst ovog spisa nije sačuvan"));
      p.appendChild(el("p", "v2-poruka__telo",
        "Original možete preuzeti gore. Tekst se čuva tek od trenutka kada je spis obrađen — "
        + "stariji spisi ga mogu nemati."));
      okvir.appendChild(p);
    }

    sadrzaj.replaceChildren(okvir);
    sadrzaj.focus();
    document.title = (d.naziv_fajla || "Spis") + " · Vindex";
  })();

  return ciklus;
}
