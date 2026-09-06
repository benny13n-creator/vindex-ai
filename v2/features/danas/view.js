/* Vindex V2 — Danas.
 *
 * Danas odgovara na jedno pitanje: STA TRAZI MOJU PAZNJU.
 *
 * Ekran ima najvise dve celine, i one se NE MESAJU:
 *   OBAVEZE     potvrdjene, grupisane po hitnosti
 *   ZA PROVERU  predlozi koje niko nije potvrdio, uvek ispod obaveza
 * Nedavno otvoreni predmeti se pojavljuju SAMO kad nema ni jednog ni drugog.
 *
 * Sto ovde NAMERNO ne postoji, iako bi bilo lako dodati:
 *   - nijedan broj koji nije datum („20 aktivnih predmeta", „7 visokog rizika")
 *   - nijedan grafikon, nijedna kartica, nijedna mreza widgeta
 *   - nijedan „office score" ni bilo kakva ocena
 * Stavka ulazi samo ako ima poslovno relevantan datum. Nivo rizika sam po sebi
 * nije ulaznica.
 *
 * PRAZAN DANAS JE DOBRO STANJE, ne greska i ne prilika za popunjavanje. Kad
 * nema obaveza, prikazuju se nedavno otvoreni predmeti — jer korisnik koji
 * nema rok i dalje ima posao.
 *
 * OBA IZOSTAVLJANJA IZ KAPIJE A SU SADA ZATVORENA:
 *   Stavka vodi u DOSIJE svog predmeta, i to pravo na celinu „Rokovi i
 *   zadaci" (`#celina-rokovi`), a ne na vrh registra. Stavka bez dokazivog
 *   `predmet_id` NE postaje veza — lazan deep link je gori od izostanka veze.
 *
 *   Predlog roka dobija „Potvrdi / Odbij", istu kontrolu koja stoji i u
 *   Dosijeu. Dve implementacije iste pravne radnje znacile bi dve prilike da
 *   se ponasa razlicito.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { ucitajDanas, ucitajNedavnePredmete, DANA_UNAPRED } from "./api.js";
import { kadaTekst } from "../../domain/danas.js";
import { uZapise } from "../../domain/predmeti.js";
import { idiNaPutanju, putanjaZa, idiNa } from "../../platform/router.js";
import { kontrolaOdluke } from "../rokovi/odluka.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

function nevidljivo(t) { return el("span", "v2-nevidljivo", t); }

function danasnjiDatum() {
  const d = new Date();
  const dani = ["nedelja", "ponedeljak", "utorak", "sreda", "četvrtak", "petak", "subota"];
  return `${dani[d.getDay()]}, ${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}.`;
}

/* ── Stavka ───────────────────────────────────────────────────────────── */

/**
 * Otvara predmet stavke, pozicioniran na celinu „Rokovi i zadaci".
 * Hash prezivljava jer ga Dosije cita posle iscrtavanja.
 */
function putanjaStavke(o) {
  return putanjaZa("predmet", o.predmetId) + "#celina-rokovi";
}

function stavka(o, ciklus) {
  const li = el("li", "v2-obaveza");

  const kada = el("span", "v2-obaveza__kada");
  kada.appendChild(nevidljivo("Datum: "));
  kada.appendChild(document.createTextNode(o.datum + (o.vreme ? " " + o.vreme : "")));
  const rel = el("span", "v2-obaveza__rel", kadaTekst(o.razlika));
  kada.appendChild(rel);
  li.appendChild(kada);

  const telo = el("div", "v2-obaveza__telo");

  const naslov = el("p", "v2-obaveza__naslov");
  const vrsta = el("span", "v2-obaveza__vrsta", o.vrstaNaziv);
  naslov.appendChild(vrsta);
  // Razmak mora biti u TEKSTU, ne samo u `margin`. Bez njega citac ekrana
  // spaja kategoriju i opis u jednu rec: „ROKRok za reklamaciju...".
  if (o.predmetId) {
    const veza = el("a", "v2-obaveza__veza", " " + o.opis);
    veza.href = putanjaStavke(o);
    if (ciklus) {
      ciklus.slusaj(veza, "click", (e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        e.preventDefault();
        idiNaPutanju(putanjaStavke(o));
      });
    }
    naslov.appendChild(veza);
  } else {
    // Bez dokazivog predmeta stavka se PRIKAZUJE, ali ne glumi vezu.
    naslov.appendChild(document.createTextNode(" " + o.opis));
  }
  telo.appendChild(naslov);

  const meta = el("p", "v2-obaveza__meta");
  if (o.predmet) {
    const p = el("span", "v2-obaveza__predmet");
    p.appendChild(nevidljivo("Predmet: "));
    p.appendChild(document.createTextNode(o.predmet));
    meta.appendChild(p);
  }
  if (meta.childNodes.length) telo.appendChild(meta);

  li.appendChild(telo);

  // Odluka stoji SAMO uz nepotvrdjen predlog, nikad uz potvrdjenu obavezu
  // ni uz rociste (rociste nije predlog i nema sta da se potvrdjuje).
  if (ciklus && o.klasa === "provera" && o.id) {
    li.appendChild(kontrolaOdluke(o, ciklus));
  }
  return li;
}

/**
 * Klasa B stoji ISPOD svih potvrdjenih obaveza i nosi mirniju gramatiku.
 * Predlog ne sme izgledati hitnije od stvarnog roka samo zato sto ga je
 * napravio sistem — zato razliku nosi polozaj i rec, a ne jaca boja.
 */
function proveraBlok(stavke, ciklus) {
  const sek = el("section", "v2-grupa v2-provera");
  sek.appendChild(el("h2", "v2-natkapa v2-grupa__naslov", "Za proveru"));
  sek.appendChild(el("p", "v2-provera__uvod",
    "Sistem je predložio ove rokove. Nisu potvrđeni i ne predstavljaju evidentiranu obavezu."));
  const ul = el("ul", "v2-grupa__lista");
  for (const o of stavke) ul.appendChild(stavka(o, ciklus));
  sek.appendChild(ul);
  return sek;
}

function grupaBlok(g, ciklus) {
  const sek = el("section", "v2-grupa");
  sek.dataset.grupa = g.kljuc;
  const h = el("h2", "v2-natkapa v2-grupa__naslov", g.naziv);
  sek.appendChild(h);
  const ul = el("ul", "v2-grupa__lista");
  for (const o of g.stavke) ul.appendChild(stavka(o, ciklus));
  sek.appendChild(ul);
  return sek;
}

function skelet() {
  const okvir = el("div", "v2-skelet");
  for (let i = 0; i < 4; i++) {
    const r = el("div", "v2-skelet__red");
    r.appendChild(el("span", "v2-skelet__traka v2-skelet__traka--uska"));
    r.appendChild(el("span", "v2-skelet__traka v2-skelet__traka--siroka"));
    okvir.appendChild(r);
  }
  return okvir;
}

function poruka({ naslov, telo, greska }) {
  const p = el("div", greska ? "v2-poruka v2-poruka--greska" : "v2-poruka");
  p.appendChild(el("p", "v2-poruka__naslov", naslov));
  if (telo) p.appendChild(el("p", "v2-poruka__telo", telo));
  return p;
}

/* ── Montiranje ───────────────────────────────────────────────────────── */

export function montirajDanas(kontejner) {
  const ciklus = napraviCiklus();
  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--danas");

  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Danas");
  h1.id = "v2-naslov-danas";
  zaglavlje.appendChild(h1);
  zaglavlje.appendChild(el("p", "v2-zaglavlje__datum v2-mono", danasnjiDatum()));
  unutra.appendChild(zaglavlje);

  // Prekidac ka kalendaru: „sta trazi paznju" i „sta me ceka" su dva pitanja
  // nad istim izvorima, pa dele prostor.
  const prekidac = el("nav", "v2-prekidac");
  prekidac.setAttribute("aria-label", "Pregled vremena");
  const ovde = el("span", "v2-prekidac__stavka v2-prekidac__stavka--aktivna", "Danas");
  ovde.setAttribute("aria-current", "page");
  const kaKalendaru = el("a", "v2-prekidac__stavka", "Kalendar");
  kaKalendaru.href = putanjaZa("danas", "kalendar");
  ciklus.slusaj(kaKalendaru, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("danas", "kalendar");
  });
  const kaBrifingu = el("a", "v2-prekidac__stavka", "Brifing");
  kaBrifingu.href = putanjaZa("danas", "brifing");
  ciklus.slusaj(kaBrifingu, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("danas", "brifing");
  });
  const kaObavestenjima = el("a", "v2-prekidac__stavka", "Obaveštenja");
  kaObavestenjima.href = putanjaZa("danas", "obavestenja");
  ciklus.slusaj(kaObavestenjima, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("danas", "obavestenja");
  });
  prekidac.append(ovde, kaKalendaru, kaBrifingu, kaObavestenjima);
  unutra.appendChild(prekidac);

  const sadrzaj = el("div", "v2-danas");
  sadrzaj.id = "v2-danas-sadrzaj";
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  sadrzaj.setAttribute("aria-labelledby", "v2-naslov-danas");
  unutra.appendChild(sadrzaj);

  kontejner.appendChild(unutra);

  let generacija = 0;

  function upozorenjeIzvora(pregled) {
    if (!pregled.degradirano && !pregled.odseceno) return null;
    const p = el("div", "v2-upozorenje");
    p.setAttribute("role", "status");
    p.textContent = pregled.degradirano
      ? "Deo obaveza trenutno nije dostupan. Ovo nije potpun spisak."
      : "Prikazan je samo početak spiska jer obaveza ima previše.";
    return p;
  }

  /**
   * Nedavno otvoreni predmeti. Vlasnicki model ih dozvoljava „posebno kada
   * nema obaveza" — dakle ne samo tada. Prikazuju se uvek, ispod obaveza:
   * advokat cija je jedina obaveza istekla pre 82 dana i dalje ima posao, a
   * prazna donja polovina ekrana nije ni odmor ni informacija.
   *
   * Ovo NIJE „nedavno korisceni": registar je uredjen po `created_at`, pa je
   * i naziv takav. Radije tacan naziv nego lepsa nedokaziva tvrdnja.
   */
  async function nedavni(okvir) {
    try {
      const sirovi = await ucitajNedavnePredmete({});
      if (ciklus.ugasen || !sirovi.length) return;
      const sek = el("section", "v2-nedavni");
      sek.appendChild(el("h2", "v2-natkapa", "Nedavno otvoreni predmeti"));
      const ul = el("ul", "v2-nedavni__lista");
      for (const z of uZapise(sirovi)) {
        const li = el("li", "v2-nedavni__red");
        li.appendChild(el("span", "v2-nedavni__naziv", z.naziv));
        const m = el("span", "v2-nedavni__meta");
        m.appendChild(nevidljivo("Stanje: "));
        m.appendChild(document.createTextNode(z.stanje));
        li.appendChild(m);
        ul.appendChild(li);
      }
      sek.appendChild(ul);
      okvir.appendChild(sek);
    } catch (e) {
      // Nedavni predmeti su dodatak; njihov pad ne sme da promeni glavnu poruku.
      if (!jePrekid(e)) { /* tiho */ }
    }
  }

  async function ucitaj() {
    const moja = ++generacija;
    const prekidac = ciklus.prekidac();
    sadrzaj.setAttribute("aria-busy", "true");
    sadrzaj.replaceChildren(skelet());

    try {
      const pregled = await ucitajDanas({ signal: prekidac.signal });
      if (moja !== generacija || ciklus.ugasen) return;
      sadrzaj.setAttribute("aria-busy", "false");

      const okvir = document.createDocumentFragment();
      const upoz = upozorenjeIzvora(pregled);
      if (upoz) okvir.appendChild(upoz);

      for (const g of pregled.grupe) okvir.appendChild(grupaBlok(g, ciklus));
      if (pregled.zaProveru.length) okvir.appendChild(proveraBlok(pregled.zaProveru, ciklus));

      if (pregled.ukupno === 0) {
        okvir.appendChild(poruka({
          naslov: "Nema obaveza koje trenutno traže postupanje.",
        }));
      }
      sadrzaj.replaceChildren(okvir);

      // Nedavni predmeti su FALLBACK, ne treci blok. Danas ostaje povrsina
      // paznje; kada paznje ima, ne dodaje se pocetni portal ispod nje.
      if (pregled.ukupno === 0) await nedavni(sadrzaj);
    } catch (e) {
      if (jePrekid(e) || ciklus.ugasen || moja !== generacija) return;
      sadrzaj.setAttribute("aria-busy", "false");
      if (e && e.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      // Pad NIKAD ne sme izgledati kao „nemate obaveza".
      sadrzaj.replaceChildren(poruka({
        naslov: "Obaveze trenutno nisu dostupne",
        telo: porukaZaKorisnika(e) + " Ovo ne znači da obaveza nema.",
        greska: true,
      }));
    }
  }

  ucitaj();
  return ciklus;
}
