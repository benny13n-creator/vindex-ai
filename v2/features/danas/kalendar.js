/* Vindex V2 — KALENDAR (`/app-v2/danas/kalendar`).
 *
 * Danas odgovara na „sta trazi moju paznju"; kalendar na „sta me ceka".
 * Dva pitanja nad ISTIM izvorima, pa kalendar ne uvodi drugi pojam roka:
 * potvrdjen rok je i ovde potvrdjen, kandidat je i ovde kandidat.
 *
 * KANDIDATI SE NE PRIKAZUJU. Nepotvrdjen predlog nije termin i ne sme da
 * zauzme mesto u planu dana — advokat koji vidi predlog u kalendaru moze da
 * poveruje da je obaveza zakazana. Predlozi ostaju u Danas, gde postoji
 * kontrola da se o njima odluci.
 *
 * NEMA MREZE OD 30 KVADRATA. Prazan dan se ne prikazuje: mreza praznih
 * polja nije plan nego ukras, a advokat sa tri rocista u mesecu treba da
 * vidi tri reda, ne trideset.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { dohvati } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { idiNa, putanjaZa, idiNaPutanju } from "../../platform/router.js";
import { sastaviKalendar, kadaTekst } from "../../domain/danas.js";

/** Prozori koje advokat stvarno bira. Backend dozvoljava do 365 dana. */
const PROZORI = [
  { dana: 30, naziv: "30 dana" },
  { dana: 90, naziv: "3 meseca" },
  { dana: 180, naziv: "6 meseci" },
];

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

function isoDatum(d) {
  return d.toISOString().slice(0, 10);
}

export function montirajKalendar(kontejner, kontekst) {
  const ciklus = napraviCiklus();
  const zaceto = kontekst || {};
  let dana = PROZORI.some(p => p.dana === zaceto.dana) ? zaceto.dana : 30;

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--registar");

  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Kalendar");
  h1.id = "v2-naslov-kalendar";
  zaglavlje.appendChild(h1);
  const brojac = el("p", "v2-reg__broj");
  zaglavlje.appendChild(brojac);
  zaglavlje.appendChild(el("p", "v2-podnaslov",
    "Potvrđene obaveze i zakazana ročišta. Nepotvrđeni predlozi se ovde ne "
    + "prikazuju — o njima se odlučuje u Danas."));
  unutra.appendChild(zaglavlje);

  // ── Prekidac Danas / Kalendar ──
  const prekidac = el("nav", "v2-prekidac");
  prekidac.setAttribute("aria-label", "Pregled vremena");
  const kaDanas = el("a", "v2-prekidac__stavka", "Danas");
  kaDanas.href = putanjaZa("danas");
  ciklus.slusaj(kaDanas, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("danas");
  });
  const ovde = el("span", "v2-prekidac__stavka v2-prekidac__stavka--aktivna", "Kalendar");
  ovde.setAttribute("aria-current", "page");
  const kaBrifingu = el("a", "v2-prekidac__stavka", "Brifing");
  kaBrifingu.href = putanjaZa("danas", "brifing");
  ciklus.slusaj(kaBrifingu, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("danas", "brifing");
  });
  prekidac.append(kaDanas, ovde, kaBrifingu);
  unutra.appendChild(prekidac);

  // ── Izbor prozora ──
  const izbor = el("div", "v2-reg__alat");
  const grupa = el("div", "v2-radnja__red");
  grupa.setAttribute("role", "group");
  grupa.setAttribute("aria-label", "Koliko unapred");
  const dugmad = new Map();
  for (const p of PROZORI) {
    const d = el("button", "v2-dugme", p.naziv);
    d.type = "button";
    ciklus.slusaj(d, "click", () => { if (dana !== p.dana) { dana = p.dana; ucitaj(); } });
    dugmad.set(p.dana, d);
    grupa.appendChild(d);
  }
  izbor.appendChild(grupa);
  unutra.appendChild(izbor);

  const sadrzaj = el("div", "v2-kalendar");
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  sadrzaj.setAttribute("aria-labelledby", "v2-naslov-kalendar");
  unutra.appendChild(sadrzaj);
  kontejner.appendChild(unutra);
  document.title = "Kalendar · Vindex";

  function osveziIzbor() {
    for (const [d, dugme] of dugmad) {
      const akt = d === dana;
      dugme.classList.toggle("v2-dugme--glavno", akt);
      dugme.setAttribute("aria-pressed", akt ? "true" : "false");
    }
  }

  function stavkaRed(x) {
    const li = el("li", "v2-kal__stavka");
    if (x.vreme) li.appendChild(el("span", "v2-kal__vreme v2-mono", x.vreme));
    const telo = el("div", "v2-kal__telo");
    const naslov = el("p", "v2-kal__naslov");
    naslov.appendChild(el("span", "v2-obaveza__vrsta", x.vrstaNaziv));
    // Razmak mora biti u TEKSTU, ne samo u `margin` — citac ekrana bi inace
    // spojio kategoriju i opis u jednu rec.
    if (x.predmetId) {
      const veza = el("a", "v2-obaveza__veza", " " + x.opis);
      veza.href = putanjaZa("predmet", x.predmetId) + "#celina-rokovi";
      ciklus.slusaj(veza, "click", (e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        e.preventDefault();
        idiNaPutanju(putanjaZa("predmet", x.predmetId) + "#celina-rokovi");
      });
      naslov.appendChild(veza);
    } else {
      naslov.appendChild(document.createTextNode(" " + x.opis));
    }
    telo.appendChild(naslov);
    if (x.predmet) telo.appendChild(el("p", "v2-obaveza__meta", x.predmet));
    li.appendChild(telo);
    return li;
  }

  /* Predlog koji nestane bez traga je gori od predloga u kalendaru: advokat
   * ne bi znao da li odluka ceka na nekoliko rokova ili ni na jednom. Zato se
   * broj saopstava i vodi TAMO gde se o njemu odlucuje. */
  function redPredloga(n) {
    const p = el("p", "v2-celina__prazno");
    p.appendChild(document.createTextNode(
      (n === 1 ? "Još 1 predlog roka čeka odluku" : `Još ${n} predloga rokova čeka odluku`)
      + " i zato nije prikazan kao termin. "));
    const a = el("a", "v2-veza", "Odlučite u Danas");
    a.href = putanjaZa("danas");
    ciklus.slusaj(a, "click", (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
      e.preventDefault();
      idiNa("danas");
    });
    p.appendChild(a);
    p.appendChild(document.createTextNode("."));
    return p;
  }

  function iscrtaj(k) {
    brojac.textContent = k.ukupno === 1 ? "1 stavka" : `${k.ukupno} stavki`;
    if (!k.meseci.length) {
      const prazno = document.createDocumentFragment();
      prazno.appendChild(el("p", "v2-celina__prazno",
        "U ovom periodu nema potvrđenih obaveza ni zakazanih ročišta."
        + (k.nedokazivo ? ` (${k.nedokazivo} zapisa nije izjavljeno kao rok i zato se ne prikazuje.)` : "")));
      if (k.predlozi) prazno.appendChild(redPredloga(k.predlozi));
      sadrzaj.replaceChildren(prazno);
      return;
    }
    const okvir = document.createDocumentFragment();
    for (const m of k.meseci) {
      const sek = el("section", "v2-kal__mesec");
      sek.appendChild(el("h2", "v2-natkapa v2-kal__mesec-naslov", m.naziv));
      for (const d of m.dani) {
        const dan = el("div", "v2-kal__dan");
        if (d.proslo) dan.dataset.proslo = "1";
        dan.appendChild(el("h3", "v2-kal__dan-naslov", d.naslov));
        const ul = el("ul", "v2-kal__lista");
        for (const x of d.stavke) ul.appendChild(stavkaRed(x));
        dan.appendChild(ul);
        sek.appendChild(dan);
      }
      okvir.appendChild(sek);
    }
    if (k.predlozi) okvir.appendChild(redPredloga(k.predlozi));
    if (k.nedokazivo) {
      // Fail-closed se SAOPSTAVA, ne precutkuje: advokat mora znati da
      // postoje zapisi koje sistem nije smeo da proglasi rokom.
      okvir.appendChild(el("p", "v2-celina__prazno",
        `${k.nedokazivo} zapisa u hronologiji nije izjavljeno kao rok i zato se `
        + "ovde ne prikazuje."));
    }
    sadrzaj.replaceChildren(okvir);
  }

  async function ucitaj() {
    osveziIzbor();
    sadrzaj.setAttribute("aria-busy", "true");
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno", "Učitava se…"));

    const danas = new Date();
    const kraj = new Date(danas.getTime() + dana * 86400000);
    const prekidac = ciklus.prekidac();

    // Dva izvora, `allSettled`: pad jednog ne sme da isprazni kalendar.
    const [k, c] = await Promise.allSettled([
      dohvati("/api/rokovi/kandidati", { upit: { dana }, signal: prekidac.signal }),
      dohvati("/api/kalendar/pregled",
              { upit: { od: isoDatum(danas), do: isoDatum(kraj) }, signal: prekidac.signal }),
    ]);
    for (const x of [k, c]) {
      if (x.status === "rejected" && jePrekid(x.reason)) return;
    }
    if (ciklus.ugasen) return;
    sadrzaj.setAttribute("aria-busy", "false");

    if (k.status === "rejected" && c.status === "rejected") {
      const e = k.reason;
      if (e && e.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      const p = el("div", "v2-poruka v2-poruka--greska");
      p.appendChild(el("p", "v2-poruka__naslov", "Kalendar nije učitan"));
      p.appendChild(el("p", "v2-poruka__telo",
        porukaZaKorisnika(e) + " Prazan kalendar bi ovde bio netačan — "
        + "ne zaključujte da obaveza nema."));
      sadrzaj.replaceChildren(p);
      return;
    }

    iscrtaj(sastaviKalendar({
      kandidati: k.status === "fulfilled" ? k.value : {},
      kalendar: c.status === "fulfilled" ? c.value : {},
    }));

    // Delimican pad se saopstava — kalendar je nepotpun, a ne prazan.
    if (k.status === "rejected" || c.status === "rejected") {
      sadrzaj.appendChild(el("p", "v2-celina__prazno",
        k.status === "rejected"
          ? "Rokovi nisu učitani — prikazana su samo ročišta."
          : "Ročišta nisu učitana — prikazani su samo rokovi."));
    }
  }

  ciklus.kontekst = () => ({ dana });

  ucitaj();
  return ciklus;
}
