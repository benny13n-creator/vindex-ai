/* Vindex V2 — Danas.
 *
 * Danas odgovara na jedno pitanje: STA TRAZI MOJU PAZNJU.
 *
 * WAVE 2 (Priority Stream + Context Rail) — zamenjuje Wave 1B-ov visok crni
 * "sidro" prostor kompoziciju sa dva dela:
 *
 *   KOMPAKTNO ZAGLAVLJE (crno)  jedna recenica o stanju dana, ne indeks
 *   RADNI PROSTOR (papir)       asimetricne dve kolone:
 *     GLAVNA kolona   JEDAN tok, dva tezinska nivoa (Trazi paznju / Uskoro)
 *     BOCNA traka     Nedavno zavrseno / Nedavno otvoreno / Brifing
 *
 * KLJUCNO PRAVILO: backend bucket NIJE UI sekcija. `/api/workspace` vraca
 * kriticno/danas/za_pregled/predstojece/na_cekanju/zavrseno_nedavno — ovih
 * sest naziva se OVDE spajaju (domain/danas.js::komponujDanas) u DVA
 * korisnicka toka pre nego sto stignu do DOM-a. Nijedan bucket ne postaje
 * sopstvena kartica ni sopstvena sekcija.
 *
 * Sto ovde NAMERNO ne postoji, iako bi bilo lako dodati:
 *   - nijedan broj koji nije direktno objasnjen recenicom ili zbirom redova
 *   - nijedan grafikon, nijedna kartica, nijedna mreza widgeta
 *   - nijedan „office score" ni bilo kakva ocena
 *   - AI tekst pomesan sa determinstickom cinjenicom (Brifing ostaje
 *     zaseban, na-zahtev ekran — v. §9 dole)
 *
 * PRAZAN DAN JE DOBRO STANJE. Kad ni Trazi paznju ni Uskoro nemaju stavki,
 * prikazuje se JEDNA mirna recenica u glavnoj koloni — ne dve-tri "Nema..."
 * poruke. Bocna traka ostaje vidljiva nezavisno od toga (nedavno zavrseno/
 * otvoreno postoje ili ne postoje sami po sebi).
 *
 * DEEP LINK DISCIPLINA (nepromenjena iz ranijih talasa):
 *   Stavka bez dokazivog `predmetId` NE postaje veza.
 *   Rok/rociste vode na `#celina-rokovi` (postojece).
 *   Radna stavka (zadatak) vodi na `#celina-rokovi` (Rokovi i zadaci vec
 *     prikazuje zadatke predmeta); radna stavka (pregled dokumenta) vodi na
 *     `#celina-spisi` (Spisi vec prikazuje dokumenta); radna stavka
 *     (case_action) vodi na KOREN predmeta — Dosije JOS NEMA posvecen
 *     prikaz case_actions, pa lazan anchor ne bi nista pokazao (Wave 2 §6).
 *   "+N" iza Trazi paznju NIKAD nije veza — nema postojeci V2 ekran za sve
 *     cross-case case_actions (Wave 2 §7); "+N" iza Uskoro JESTE veza SAMO
 *     kad je sav preostatak kalendarski (Kalendar vec postoji i vec
 *     prikazuje celu nedelju) — nikad kad preostatak sadrzi zadatke koje
 *     Kalendar ne vlasnistvuje (Wave 2 §8).
 *
 * Predlog roka i dalje dobija „Potvrdi / Odbij", istu kontrolu koja stoji i
 * u Dosijeu — nepromenjeno.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { ucitajPregledDanas, ucitajNedavnePredmete } from "./api.js";
import { kadaTekst, sazetakDana, komponujDanas, nazivRadneVrste } from "../../domain/danas.js";
import { uZapise } from "../../domain/predmeti.js";
import { idiNaPutanju, putanjaZa, idiNa } from "../../platform/router.js";
import { kontrolaOdluke } from "../rokovi/odluka.js";

const TIER1_PRIKAZ = 8;
const TIER2_PRIKAZ = 6;

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

/* ── Postojeca stavka: potvrdjen rok / rociste / predlog (nepromenjeno) ── */

function putanjaStavke(o) {
  return putanjaZa("predmet", o.predmetId) + "#celina-rokovi";
}

function stavka(o, ciklus) {
  const li = el("li", "v2-obaveza" + (o.klasa === "provera" ? " v2-obaveza--provera" : ""));
  if (o.grupa) li.dataset.grupa = o.grupa;

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

/* ── Nova stavka: case_action / zadatak / pregled dokumenta (/api/workspace) ── */

function putanjaRadne(o) {
  const koren = putanjaZa("predmet", o.predmetId);
  return o.anchor ? `${koren}#celina-${o.anchor}` : koren;
}

function radnaStavka(o, ciklus) {
  const li = el("li", "v2-radna-stavka" + (o.hitno ? " v2-radna-stavka--hitno" : ""));

  const kada = el("span", "v2-radna-stavka__kada");
  kada.appendChild(nevidljivo("Kada: "));
  kada.appendChild(document.createTextNode(o.kada || (o.hitno ? "Kritično" : "—")));
  li.appendChild(kada);

  const telo = el("div", "v2-obaveza__telo");
  const naslov = el("p", "v2-obaveza__naslov");
  naslov.appendChild(el("span", "v2-radna-stavka__vrsta", nazivRadneVrste(o.vrsta)));
  if (o.predmetId) {
    const veza = el("a", "v2-radna-stavka__veza", " " + o.naslov);
    veza.href = putanjaRadne(o);
    if (ciklus) {
      ciklus.slusaj(veza, "click", (e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        e.preventDefault();
        idiNaPutanju(putanjaRadne(o));
      });
    }
    naslov.appendChild(veza);
  } else {
    naslov.appendChild(document.createTextNode(" " + o.naslov));
  }
  telo.appendChild(naslov);

  if (o.predmet) {
    const meta = el("p", "v2-obaveza__meta");
    const p = el("span", "v2-obaveza__predmet");
    p.appendChild(nevidljivo("Predmet: "));
    p.appendChild(document.createTextNode(o.predmet));
    meta.appendChild(p);
    telo.appendChild(meta);
  }
  li.appendChild(telo);
  return li;
}

function redToka(o, ciklus) {
  return o.klasa ? stavka(o, ciklus) : radnaStavka(o, ciklus);
}

/* ── Preostalo iza odsecanja: nikad tiho, nikad lazna veza ── */

function preostaloTier1(ukupno, prikazano) {
  const preostalo = ukupno - prikazano;
  if (preostalo <= 0) return null;
  // Nema postojeci V2 ekran za sve cross-case case_actions (Wave 2 §7):
  // obavezno obican tekst, nikad izmisljena navigacija.
  return el("p", "v2-danas-preostalo", `+${preostalo} dodatnih stavki`);
}

function preostaloTier2(ukupno, prikazano, kalendarskihUkupno, ciklus) {
  const preostalo = ukupno - prikazano;
  if (preostalo <= 0) return null;
  const prikazanoKalendarsko = Math.min(prikazano, kalendarskihUkupno);
  const preostaloKalendarsko = kalendarskihUkupno - prikazanoKalendarsko;
  // Veza SAMO kad je BAS SVE preostalo kalendarsko (rok/rociste) — Kalendar
  // ne vlasnistvuje zadatke ni case_actions (Wave 2 §8).
  if (preostaloKalendarsko === preostalo) {
    const a = el("a", "v2-danas-preostalo v2-danas-preostalo--veza", `+${preostalo} u kalendaru`);
    a.href = putanjaZa("danas", "kalendar");
    ciklus.slusaj(a, "click", (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
      e.preventDefault();
      idiNa("danas", "kalendar");
    });
    return a;
  }
  return el("p", "v2-danas-preostalo", `+${preostalo} dodatnih stavki narednih dana`);
}

/* ── Tok (Trazi paznju / Uskoro) ── */

function tokBlok(naslov, stavke, prikaz, preostaloEl, ciklus) {
  const sek = el("section", "v2-grupa");
  sek.appendChild(el("h2", "v2-natkapa v2-grupa__naslov", naslov));
  const ul = el("ul", "v2-grupa__lista");
  for (const o of stavke.slice(0, prikaz)) ul.appendChild(redToka(o, ciklus));
  sek.appendChild(ul);
  if (preostaloEl) sek.appendChild(preostaloEl);
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

  // ── Kompaktno zaglavlje: crna scena, isti par klasa koji nosi ljusku. ───
  // Za razliku od Wave 1B, ovo NIJE indeks sa jednom stavkom po grupi — to
  // je bio broj-po-grupi ("koliko"), sad je to JEDNA recenica ("sta").
  const glava = el("div", "v2-scena v2-scena--crna");
  const glavaUnutra = el("div", "v2-scena__unutra v2-scena__unutra--danas v2-danas-glava");
  const glavaRed = el("div", "v2-danas-glava__red");
  const h1 = el("h1", "v2-naslov", "Danas");
  h1.id = "v2-naslov-danas";
  glavaRed.appendChild(h1);
  glavaRed.appendChild(el("p", "v2-zaglavlje__datum v2-mono", danasnjiDatum()));
  glavaUnutra.appendChild(glavaRed);
  const sazetak = el("p", "v2-danas-glava__sazetak");
  glavaUnutra.appendChild(sazetak);
  glava.appendChild(glavaUnutra);

  // ── Radni prostor: papir, asimetricne dve kolone. ───────────────────────
  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--danas v2-danas-radna");

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

  const radni = el("div", "v2-danas-radni");
  const glavna = el("div", "v2-danas-radni__glavna");
  glavna.id = "v2-danas-sadrzaj";
  glavna.tabIndex = -1;
  glavna.setAttribute("aria-live", "polite");
  glavna.setAttribute("aria-labelledby", "v2-naslov-danas");
  const rail = el("aside", "v2-danas-radni__rail");
  rail.setAttribute("aria-label", "Kontekst");
  radni.append(glavna, rail);
  unutra.appendChild(radni);

  kontejner.appendChild(glava);
  kontejner.appendChild(unutra);

  let generacija = 0;

  function upozorenjeIzvora(k) {
    if (k.nedostupno) {
      const p = el("div", "v2-upozorenje");
      p.setAttribute("role", "status");
      p.textContent = "Deo stavki trenutno nije dostupan ili nije u potpunosti proveren. Ovo nije potpun spisak.";
      return p;
    }
    if (k.odseceno) {
      const p = el("div", "v2-upozorenje");
      p.setAttribute("role", "status");
      p.textContent = "Prikazan je samo početak spiska jer obaveza ima previše.";
      return p;
    }
    return null;
  }

  /**
   * Nedavno otvoreni predmeti. U Wave 2 ovo je STALNA stavka bocne trake,
   * ne fallback koji se pojavljuje samo kad glavni tok nema sadrzaja —
   * kontekst i paznja su nezavisne informacije (Wave 2 §9B).
   *
   * Ovo NIJE „nedavno korisceni": registar je uredjen po `created_at`, pa je
   * i naziv takav. Radije tacan naziv nego lepsa nedokaziva tvrdnja.
   */
  async function nedavniPredmeti(okvir) {
    try {
      const sirovi = await ucitajNedavnePredmete({});
      if (ciklus.ugasen || !sirovi.length) return;
      const sek = el("section");
      sek.appendChild(el("h2", "v2-natkapa", "Nedavno otvoreno"));
      const ul = el("ul");
      for (const z of uZapise(sirovi)) {
        const li = el("li", "v2-danas-rail__red");
        if (z.id) {
          const veza = el("a", "v2-danas-rail__veza", z.naziv);
          veza.href = putanjaZa("predmet", z.id);
          ciklus.slusaj(veza, "click", (e) => {
            if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
            e.preventDefault();
            idiNaPutanju(putanjaZa("predmet", z.id));
          });
          li.appendChild(veza);
        } else {
          li.appendChild(document.createTextNode(z.naziv));
        }
        ul.appendChild(li);
      }
      sek.appendChild(ul);
      okvir.appendChild(sek);
    } catch (e) {
      // Nedavni predmeti su dodatak; njihov pad ne sme da promeni glavnu poruku.
      if (!jePrekid(e)) { /* tiho */ }
    }
  }

  function iscrtajZavrseno(okvir, zavrseno) {
    if (!zavrseno || !zavrseno.length) return;
    const sek = el("section");
    sek.appendChild(el("h2", "v2-natkapa", "Nedavno završeno"));
    const ul = el("ul");
    for (const z of zavrseno.slice(0, 4)) {
      const li = el("li", "v2-danas-rail__red");
      const naziv = z.predmet ? `${z.naslov} — ${z.predmet}` : z.naslov;
      li.appendChild(document.createTextNode(naziv));
      ul.appendChild(li);
    }
    sek.appendChild(ul);
    okvir.appendChild(sek);
  }

  function iscrtajBrifingVezu(okvir) {
    const a = el("a", "v2-danas-rail__brifing", "Jutarnji brifing →");
    a.href = putanjaZa("danas", "brifing");
    ciklus.slusaj(a, "click", (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
      e.preventDefault();
      idiNa("danas", "brifing");
    });
    okvir.appendChild(a);
  }

  async function ucitaj() {
    const moja = ++generacija;
    const prekidacSig = ciklus.prekidac();
    glavna.setAttribute("aria-busy", "true");
    glavna.replaceChildren(skelet());
    rail.replaceChildren();

    try {
      const izvori = await ucitajPregledDanas({ signal: prekidacSig.signal });
      if (moja !== generacija || ciklus.ugasen) return;
      glavna.setAttribute("aria-busy", "false");

      const k = komponujDanas(izvori);
      sazetak.textContent = sazetakDana(k.tier1.length, k.prvoRocisteDanasVreme);

      const okvir = document.createDocumentFragment();
      const upoz = upozorenjeIzvora(k);
      if (upoz) okvir.appendChild(upoz);

      if (!k.tier1.length && !k.tier2.length) {
        okvir.appendChild(el("div", "v2-danas-prazno-mirno",
          "Trenutno nema stavki koje zahtevaju pažnju ni predstojećih obaveza."));
      } else {
        if (k.tier1.length) {
          okvir.appendChild(tokBlok("Traži pažnju", k.tier1, TIER1_PRIKAZ,
            preostaloTier1(k.tier1.length, Math.min(k.tier1.length, TIER1_PRIKAZ)), ciklus));
        }
        if (k.tier2.length) {
          okvir.appendChild(tokBlok("Uskoro", k.tier2, TIER2_PRIKAZ,
            preostaloTier2(k.tier2.length, Math.min(k.tier2.length, TIER2_PRIKAZ),
                           k.tier2KalendarskihUkupno, ciklus), ciklus));
        }
      }
      glavna.replaceChildren(okvir);

      const railOkvir = document.createDocumentFragment();
      iscrtajZavrseno(railOkvir, k.zavrsenoNedavno);
      rail.appendChild(railOkvir);
      await nedavniPredmeti(rail);
      if (moja === generacija && !ciklus.ugasen) iscrtajBrifingVezu(rail);
    } catch (e) {
      if (jePrekid(e) || ciklus.ugasen || moja !== generacija) return;
      glavna.setAttribute("aria-busy", "false");
      if (e && e.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      sazetak.textContent = "Stanje dana trenutno nije dostupno.";
      // Pad NIKAD ne sme izgledati kao „nemate obaveza".
      glavna.replaceChildren(poruka({
        naslov: "Obaveze trenutno nisu dostupne",
        telo: porukaZaKorisnika(e) + " Ovo ne znači da obaveza nema.",
        greska: true,
      }));
      // Kontekst (nedavno zavrseno/otvoreno) i dalje ima smisla i kad glavni
      // tok padne — to su nezavisni pozivi.
      await nedavniPredmeti(rail);
      if (moja === generacija && !ciklus.ugasen) iscrtajBrifingVezu(rail);
    }
  }

  ucitaj();
  return ciklus;
}
