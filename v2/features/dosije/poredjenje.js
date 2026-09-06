/* Vindex V2 — poređenje dokumenata unutar Dosijea (C7).
 *
 * Zasebna radnja u Spisima, ne modal preko celog ekrana: advokat bira 2-5
 * spisa iz VEĆ VIDLJIVE liste, ne iz posebnog dijaloga koji ponavlja istu
 * listu. Rezultat ostaje na istoj strani, ispod forme.
 */

import { posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { uPoredjenje, validanBrojDokumenata } from "../../domain/poredjenje.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

function prikaziRezultat(kontejner, p) {
  kontejner.replaceChildren();
  const okvir = el("div", "v2-podblok");
  okvir.appendChild(el("h3", "v2-natkapa", "Poređenje: " + p.nazivi.join(" · ")));

  if (p.rezime) okvir.appendChild(el("p", "v2-proza", p.rezime));

  if (p.konflikti.length) {
    okvir.appendChild(el("h4", "v2-natkapa", "Konflikti"));
    const ul = el("ul", "v2-lista-tanka");
    for (const k of p.konflikti) {
      const li = el("li");
      li.appendChild(el("p", "", k.opis));
      if (k.citat) li.appendChild(el("p", "v2-mono v2-meta", "„" + k.citat + "”" + (k.dokument ? " — " + k.dokument : "")));
      ul.appendChild(li);
    }
    okvir.appendChild(ul);
  } else {
    okvir.appendChild(el("p", "v2-celina__prazno", "Nisu pronađeni konflikti između odabranih dokumenata."));
  }

  if (p.slicnosti.length) {
    okvir.appendChild(el("h4", "v2-natkapa", "Sličnosti"));
    const ul = el("ul", "v2-lista-tanka");
    for (const sl of p.slicnosti) ul.appendChild(el("li", "", sl));
    okvir.appendChild(ul);
  }

  if (p.preporuke.length) {
    okvir.appendChild(el("h4", "v2-natkapa", "Preporuke"));
    const ul = el("ul", "v2-lista-tanka");
    for (const pr of p.preporuke) ul.appendChild(el("li", "", pr.tekst));
    okvir.appendChild(ul);
  }

  if (p.zakljucak) {
    okvir.appendChild(el("h4", "v2-natkapa", "Pravni zaključak"));
    okvir.appendChild(el("p", "v2-proza", p.zakljucak));
  }

  if (p.upozorenjeSkracenja) {
    okvir.appendChild(el("p", "v2-forma__poruka v2-forma__poruka--upozorenje", p.upozorenjeSkracenja));
  }

  kontejner.appendChild(okvir);
}

/** Vraca element forme. `spisi` = [{id, naziv}], najmanje 2 stavke potrebne
 * pozivaocu da uopste prikaze ovaj blok (manje od 2 spisa = nema sta da se
 * poredi, pozivalac odlucuje da li da uopste montira). */
export function blokPoredjenja(predmetId, spisi, ciklus) {
  const b = el("div", "v2-podblok");
  b.appendChild(el("h3", "v2-natkapa", "Uporedi dokumenta"));

  const listaOznaka = el("div", "v2-forma__redovi");
  const boksovi = [];
  for (const sp of spisi) {
    const red = el("label", "v2-forma__red");
    const cb = el("input");
    cb.type = "checkbox";
    cb.value = sp.id;
    red.appendChild(cb);
    red.appendChild(document.createTextNode(" " + sp.naziv));
    listaOznaka.appendChild(red);
    boksovi.push(cb);
  }
  b.appendChild(listaOznaka);

  const pitanje = el("textarea");
  pitanje.placeholder = "Pravno pitanje ili tema poređenja (npr. „Da li se ugovori razlikuju u pogledu roka raskida?”)";
  pitanje.rows = 2;
  b.appendChild(pitanje);

  const dugme = el("button", "v2-dugme", "Uporedi");
  dugme.type = "button";
  b.appendChild(dugme);

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;
  b.appendChild(poruka);

  const rezultatMesto = el("div");
  b.appendChild(rezultatMesto);

  ciklus.slusaj(dugme, "click", async () => {
    const oznaceni = boksovi.filter(cb => cb.checked).map(cb => cb.value);
    if (!validanBrojDokumenata(oznaceni.length)) {
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = "Izaberite 2 do 5 dokumenata.";
      poruka.hidden = false;
      return;
    }
    if (pitanje.value.trim().length < 10) {
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = "Pravno pitanje mora imati najmanje 10 znakova.";
      poruka.hidden = false;
      return;
    }
    dugme.disabled = true;
    dugme.textContent = "Poredi se…";
    poruka.hidden = true;
    try {
      const r = await posalji("/api/analiza/cross-doc/predmet", {
        telo: { predmet_id: predmetId, dokument_ids: oznaceni, pravno_pitanje: pitanje.value.trim() },
        signal: ciklus.prekidac().signal,
      });
      if (ciklus.ugasen) return;
      prikaziRezultat(rezultatMesto, uPoredjenje(r));
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = "Poređenje nije uspelo. " + porukaZaKorisnika(err);
      poruka.hidden = false;
    } finally {
      dugme.disabled = false;
      dugme.textContent = "Uporedi";
    }
  });

  return b;
}
