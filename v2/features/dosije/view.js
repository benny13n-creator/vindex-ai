/* Vindex V2 — DOSIJE.
 *
 * Jedan predmet. Jedna kontinuirana radna povrsina. Pet imenovanih celina.
 *
 * ZASTO OVO NISU TABOVI
 * Tab skriva ostatak predmeta i tera advokata da pamti gde je sta. Ovde su sve
 * celine na istoj povrsini, a lepljiva traka je SIDRO — pokazuje gde ste i
 * vodi vas kroz isti predmet, bez menjanja stanja stranice.
 *
 * SVE IZ JEDNOG POZIVA
 * `/api/predmeti/{id}` vec nosi predmet, spise, hronologiju i klijente, pa
 * ekran ima jedno stanje ucitavanja umesto sedam.
 *
 * STO OVDE NEMA
 *   - nijedan izmisljen procenat pravne sigurnosti
 *   - nijedna ocena bez objasnjenja
 *   - nijedno prazno polje koje tvrdi da podatak postoji
 *   - nijedna mrtva kontrola
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { idiNa, putanjaZa, idiNaPutanju } from "../../platform/router.js";
import { SIDRA } from "../../domain/dosije.js";
import { ucitajDosije, putanjaPreuzimanja } from "./api.js";
import { elementPoruke, ostavi } from "../../platform/obavestenje.js";
import { posalji } from "../../platform/http.js";
import { kontrolaOdluke } from "../rokovi/odluka.js";
import { uZadatke, uRocista, uBeleske } from "../../domain/dosije.js";
import { obrazacZadatka, obrazacRocista, obrazacBeleske,
         kontrolaBrisanjaSpisa, kontrolaBrisanjaNapomene } from "./radnje.js";
import { kontrolaIzmene } from "./izmena.js";
import { kontrolaBrisanjaPredmeta } from "./brisanje.js";
import { ucitajNaplatuPredmeta, sadrzajNaplate } from "./naplata.js";
import { ucitajSaradnjuPredmeta, sadrzajSaradnje } from "./saradnja.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}
function nevidljivo(t) { return el("span", "v2-nevidljivo", t); }

function naslovCeline(kljuc, naziv) {
  const h = el("h2", "v2-celina__naslov", naziv);
  h.id = "celina-" + kljuc;
  return h;
}

function celina(kljuc, naziv) {
  const s = el("section", "v2-celina");
  s.dataset.celina = kljuc;
  s.setAttribute("aria-labelledby", "celina-" + kljuc);
  s.appendChild(naslovCeline(kljuc, naziv));
  return s;
}

function prazno(tekst) {
  return el("p", "v2-celina__prazno", tekst);
}

/* ── Stanje ─────────────────────────────────────────────────────────────── */

function sekcijaStanje(d, ciklus, predmetId, radnje) {
  const s = celina("stanje", "Stanje");

  if (d.polja.length) {
    const dl = el("dl", "v2-polja");
    for (const p of d.polja) {
      // Naziv i vrednost su JEDAN par u jednoj celiji mreze. Kao dve odvojene
      // celije, `auto-fit` ih je razbacivao u razlicite kolone, pa je labela
      // stajala levo a vrednost dve kolone dalje, a podvlaka ispod vrednosti
      // izgledala kao da pripada susednom polju.
      const par = el("div", "v2-polja__par");
      par.appendChild(el("dt", "v2-polje", p.naziv));
      par.appendChild(el("dd", p.mono ? "v2-polja__v v2-mono" : "v2-polja__v", p.vrednost));
      dl.appendChild(par);
    }
    s.appendChild(dl);
  }

  if (d.klijenti.length) {
    const blok = el("div", "v2-podblok");
    blok.appendChild(el("h3", "v2-natkapa", "Klijenti"));
    const ul = el("ul", "v2-lista-tanka");
    for (const k of d.klijenti) {
      const li = el("li");
      li.appendChild(el("span", "", k.naziv));
      if (k.uloga) li.appendChild(el("span", "v2-meta", " · " + k.uloga));
      ul.appendChild(li);
    }
    blok.appendChild(ul);
    s.appendChild(blok);
  }

  if (d.zaglavlje.opis) {
    const blok = el("div", "v2-podblok");
    blok.appendChild(el("h3", "v2-natkapa", "Opis"));
    blok.appendChild(el("p", "v2-proza", d.zaglavlje.opis));
    s.appendChild(blok);
  }

  if (!d.polja.length && !d.klijenti.length && !d.zaglavlje.opis) {
    s.appendChild(prazno("Za ovaj predmet još nisu uneti podaci o strankama, sudu ni broju predmeta."));
  }
  // ── Beleske ──
  // Beleska je radna napomena o predmetu — pripada „Stanju", ne hronologiji
  // (hronologija je ono sto se DESILO) i ne dobija sestu celinu.
  const bBel = el("div", "v2-podblok");
  bBel.appendChild(el("h3", "v2-natkapa", "Beleške"));
  if (!d.beleske.length) {
    bBel.appendChild(prazno("Nema beleški za ovaj predmet."));
  } else {
    const ulB = el("ul", "v2-lista-tanka");
    for (const b of d.beleske) {
      const liB = el("li", "v2-beleska");
      liB.appendChild(document.createTextNode(b.tekst));
      if (b.datumPoznat) liB.appendChild(el("span", "v2-beleska__datum", " — " + b.datum));
      // Napomena se moze i ukloniti — inace bi jedini nacin da se ispravi
      // pogresno zapisana napomena bio da se doda jos jedna ispod nje.
      if (radnje && radnje.osvezi && b.id) {
        liB.appendChild(kontrolaBrisanjaNapomene(predmetId, b, ciklus, radnje.osvezi));
      }
      ulB.appendChild(liB);
    }
    bBel.appendChild(ulB);
  }
  if (radnje && radnje.osvezi) {
    bBel.appendChild(obrazacBeleske(predmetId, ciklus, radnje.osvezi));
  }
  s.appendChild(bBel);

  // Izmena podataka stoji na dnu „Stanja" — advokat ispravlja ime tuzenog
  // gledajuci ostatak predmeta, ne u praznom obrascu na drugoj strani.
  // D7: pravno pitanje U KONTEKSTU ovog predmeta. Radnja polazi ODAVDE, pa
  // Znanje ne dobija birač predmeta — predmet je već izabran time što je
  // advokat otvorio njegov Dosije.
  {
    const put = putanjaZa("znanje") + "?predmet=" + encodeURIComponent(predmetId);
    const pitaj = el("a", "v2-dugme", "Pitaj o ovom predmetu");
    pitaj.href = put;
    ciklus.slusaj(pitaj, "click", (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
      e.preventDefault();
      idiNaPutanju(put);
    });
    const red = el("div", "v2-forma__radnje");
    red.appendChild(pitaj);
    s.appendChild(red);
  }

  if (radnje && radnje.osvezi && d.sirovi) {
    s.appendChild(kontrolaIzmene(predmetId, d.sirovi, ciklus, radnje.osvezi));
    // Brisanje stoji NA DNU celine, odvojeno od izmene i vizuelno drugacije:
    // nepovratna radnja ne sme da stoji uz svakodnevnu.
    s.appendChild(kontrolaBrisanjaPredmeta(predmetId, d.zaglavlje.naziv, ciklus));
  }

  return s;
}

/* ── Hronologija ────────────────────────────────────────────────────────── */

function sekcijaHronologija(d) {
  const s = celina("hronologija", "Hronologija");
  if (!d.hronologija.length) {
    s.appendChild(prazno("Nema zabeleženih događaja."));
    return s;
  }
  const ul = el("ul", "v2-hron");
  for (const h of d.hronologija) {
    const li = el("li", "v2-hron__red");
    if (h.kritican) li.dataset.vaznost = "kritican";

    const dat = el("span", "v2-hron__datum v2-mono");
    dat.appendChild(nevidljivo("Datum: "));
    dat.appendChild(document.createTextNode(h.datum));
    li.appendChild(dat);

    const telo = el("div", "v2-hron__telo");
    telo.appendChild(el("p", "v2-hron__dogadjaj", h.dogadjaj));
    const meta = el("p", "v2-hron__meta");
    if (h.akter) meta.appendChild(el("span", "", h.akter));
    if (h.dokument) meta.appendChild(el("span", "", h.dokument));
    if (h.jeRok) meta.appendChild(el("span", "v2-hron__oznaka", "rok"));
    if (meta.childNodes.length) telo.appendChild(meta);
    li.appendChild(telo);
    ul.appendChild(li);
  }
  s.appendChild(ul);
  return s;
}

/* ── Analiza predmeta ───────────────────────────────────────────────────── */

function sekcijaAnaliza(d) {
  const s = celina("analiza", "Analiza predmeta");

  if (d.spremnostPala) {
    s.appendChild(prazno("Ocena spremnosti trenutno nije dostupna. Ovo ne znači da problema nema."));
    return s;
  }
  if (!d.spremnost) {
    s.appendChild(prazno("Za ovaj predmet još nema izvedene analize."));
    return s;
  }

  const p = el("p", "v2-analiza__stanje");
  p.appendChild(el("span", "v2-polje", "Spremnost"));
  p.appendChild(document.createTextNode(" " + d.spremnost.status));
  s.appendChild(p);

  if (d.spremnost.razlozi.length) {
    const ul = el("ul", "v2-lista-tanka");
    for (const r of d.spremnost.razlozi) ul.appendChild(el("li", "", r));
    s.appendChild(ul);
  } else {
    s.appendChild(prazno("Nema otvorenih primedbi na spremnost predmeta."));
  }
  return s;
}

/* ── Spisi ──────────────────────────────────────────────────────────────── */

/**
 * Otpremanje spisa stoji UZ spisak spisa, ne u modalu i ne na posebnoj strani:
 * advokat vidi sta vec ima dok dodaje novo.
 *
 * Backend vraca `original_preserved:false` kada je OCR/analiza uspela ali
 * upis originala u skladiste nije. To se KAZE — advokat cija potpisana
 * originalna verzija nije sacuvana ne sme da vidi isti ekran kao onaj cija
 * jeste. Isto vazi za `mozda_duplikat`.
 */
function otpremanje(predmetId, ciklus, naUspeh) {
  const okvir = el("div", "v2-otpremi");

  const lab = el("label", "v2-otpremi__labela", "Dodaj spis");
  const uslovi = el("p", "v2-otpremi__uslovi", "PDF, DOCX, DOC, JPG ili PNG. Najviše 10 MB.");
  lab.htmlFor = "v2-spis-fajl";
  const unos = el("input", "v2-otpremi__polje");
  unos.type = "file";
  unos.id = "v2-spis-fajl";
  unos.name = "file";
  // TACNO ono sto backend prihvata (`_ALLOWED_SUFFIXES` u api.py). Ponuditi
  // .txt ili .rtf znacilo bi pustiti advokata da izabere fajl koji ce server
  // odbiti sa 415 — kontrola koja obecava vise nego sto ispunjava.
  unos.accept = ".pdf,.docx,.doc,.jpg,.jpeg,.png";

  const dugme = el("button", "v2-dugme", "Otpremi");
  dugme.type = "button";
  dugme.disabled = true;

  const stanje = el("p", "v2-otpremi__stanje");
  stanje.setAttribute("role", "status");
  stanje.hidden = true;

  const red = el("div", "v2-otpremi__red");
  red.append(unos, dugme);
  okvir.append(lab, uslovi, red, stanje);

  function javi(tekst, vrsta) {
    stanje.className = "v2-otpremi__stanje v2-otpremi__stanje--" + (vrsta || "info");
    stanje.textContent = tekst;
    stanje.hidden = false;
  }

  ciklus.slusaj(unos, "change", () => {
    dugme.disabled = !(unos.files && unos.files.length);
    stanje.hidden = true;
  });

  let radi = false;
  ciklus.slusaj(dugme, "click", async () => {
    if (radi || !unos.files || !unos.files.length) return;
    const fajl = unos.files[0];
    radi = true;
    dugme.disabled = true;
    unos.disabled = true;
    // Analiza spisa traje; ekran to kaze umesto da izgleda zamrznuto.
    javi(`„${fajl.name}" se otprema i analizira. Ovo može potrajati.`, "info");

    const telo = new FormData();
    telo.append("file", fajl, fajl.name);

    let odg;
    try {
      odg = await posalji(`/api/predmeti/${encodeURIComponent(predmetId)}/upload`,
                          { telo, signal: ciklus.prekidac().signal });
    } catch (e) {
      if (jePrekid(e) || ciklus.ugasen) return;
      radi = false;
      unos.disabled = false;
      dugme.disabled = false;
      if (e && e.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      if (e && e.vrsta === VRSTA.MREZA) {
        javi("Veza je prekinuta pre nego što je stigao odgovor. Spis je možda otpremljen — "
           + "osvežite Dosije pre nego što pokušate ponovo.", "upozorenje");
        return;
      }
      javi("Spis nije otpremljen. " + porukaZaKorisnika(e), "greska");
      return;
    }
    if (ciklus.ugasen) return;

    const upozorenja = [];
    if (odg && odg.original_preserved === false) {
      upozorenja.push("Originalni fajl NIJE sačuvan u skladištu — sačuvan je samo izdvojen tekst. "
                    + "Zadržite svoju kopiju.");
    }
    if (odg && odg.mozda_duplikat) {
      upozorenja.push("Isti sadržaj već postoji u ovom predmetu.");
    }
    radi = false;
    unos.value = "";
    unos.disabled = false;
    dugme.disabled = true;

    if (typeof naUspeh === "function") {
      // Dosije se ponovo cita, pa bi poruka nestala sa starim DOM-om.
      // Zato ide kroz jednokratno obavestenje i preziveti ponovno iscrtavanje —
      // upozorenje da original NIJE sacuvan ne sme da se izgubi u osvezavanju.
      ostavi(upozorenja.length ? upozorenja.join(" ") : "Spis je otpremljen i analiziran.",
             upozorenja.length ? "upozorenje" : "uspeh");
      naUspeh();
      return;
    }
    javi(upozorenja.length ? upozorenja.join(" ") : "Spis je otpremljen i analiziran.",
         upozorenja.length ? "upozorenje" : "uspeh");
  });

  return okvir;
}

function sekcijaSpisi(d, predmetId, ciklus, radnje) {
  const s = celina("spisi", "Spisi");
  if (!d.spisi.length) {
    s.appendChild(prazno("U ovom predmetu još nema spisa."));
    s.appendChild(otpremanje(predmetId, ciklus, radnje && radnje.osvezi));
    return s;
  }
  const ul = el("ul", "v2-spisi");
  for (const f of d.spisi) {
    const li = el("li", "v2-spisi__red");

    // Naziv otvara CITANJE spisa. Preuzimanje je zasebna, tiha radnja:
    // advokat najcesce hoce da PROCITA, a ne da skine fajl.
    const naziv = el("span", "v2-spisi__naziv");
    if (radnje && radnje.otvoriSpis) {
      const veza = el("button", "v2-spisi__otvori", f.naziv);
      veza.type = "button";
      ciklus.slusaj(veza, "click", () => radnje.otvoriSpis(f.id));
      naziv.appendChild(veza);
    } else {
      naziv.textContent = f.naziv;
    }
    li.appendChild(naziv);

    const meta = el("span", "v2-spisi__meta");
    meta.appendChild(el("span", "v2-mono", f.dodat));
    meta.appendChild(el("span", "", f.analiziran ? "analiziran" : "nije analiziran"));
    li.appendChild(meta);

    // Kontrola postoji SAMO ako original stvarno postoji u skladistu.
    const akcije = el("span", "v2-spisi__akcije");
    if (f.imaOriginal) {
      const a = el("a", "v2-tekst-veza", "Preuzmi");
      a.href = putanjaPreuzimanja(predmetId, f.id);
      a.setAttribute("aria-label", "Preuzmi spis " + f.naziv);
      akcije.appendChild(a);
    } else {
      akcije.appendChild(el("span", "v2-meta", "original nije sačuvan"));
    }
    // Brisanje spisa je nepovratno i uklanja i vektore — trazi potvrdu u dva
    // koraka koja IMENUJE spis. Vidi `radnje.js`.
    if (radnje && radnje.osvezi && f.id) {
      akcije.appendChild(kontrolaBrisanjaSpisa(predmetId, f, ciklus, radnje.osvezi));
    }
    li.appendChild(akcije);
    ul.appendChild(li);
  }
  s.appendChild(ul);
  s.appendChild(otpremanje(predmetId, ciklus, radnje && radnje.osvezi));
  return s;
}

/* ── Rokovi i zadaci ────────────────────────────────────────────────────── */

function rokRed(r, ciklus) {
  const li = el("li", "v2-rok__red");
  if (r.proslo) li.dataset.proslo = "1";
  const kada = el("span", "v2-rok__kada v2-mono");
  kada.appendChild(nevidljivo("Datum: "));
  kada.appendChild(document.createTextNode(r.datum));
  kada.appendChild(el("span", "v2-rok__rel", r.kada));
  li.appendChild(kada);
  const opis = el("span", "v2-rok__opis", r.opis);
  li.appendChild(opis);
  // Odluka stoji SAMO uz nepotvrdjen predlog. Potvrdjena obaveza nema sta da
  // se „potvrdjuje" drugi put, a ponudjena kontrola bi to sugerisala.
  if (ciklus) li.appendChild(kontrolaOdluke(r, ciklus));
  return li;
}

function sekcijaRokovi(d, ciklus, predmetId, radnje, sada) {
  const s = celina("rokovi", "Rokovi i zadaci");
  const r = d.rokovi;
  // Odsustvo ROKOVA se saopstava, ali NE prekida celinu: rocista i zadaci su
  // zasebne stvari i moraju se videti (i moci dodati) i kad rokova nema.
  // Rani izlaz je ovde jednom vec sakrio oba obrasca — predmet bez rokova
  // nije predmet bez posla.
  if (!r.obaveze.length && !r.zaProveru.length) {
    s.appendChild(prazno("Za ovaj predmet nema evidentiranih rokova."));
  }
  if (r.obaveze.length) {
    const b = el("div", "v2-podblok");
    b.appendChild(el("h3", "v2-natkapa", "Obaveze"));
    const ul = el("ul", "v2-rok");
    for (const x of r.obaveze) ul.appendChild(rokRed(x));
    b.appendChild(ul);
    s.appendChild(b);
  }
  if (r.zaProveru.length) {
    const b = el("div", "v2-podblok v2-podblok--provera");
    b.appendChild(el("h3", "v2-natkapa", "Za proveru"));
    b.appendChild(el("p", "v2-provera__uvod",
      "Sistem je predložio ove rokove. Nisu potvrđeni i ne predstavljaju evidentiranu obavezu."));
    const ul = el("ul", "v2-rok");
    for (const x of r.zaProveru) ul.appendChild(rokRed(x, ciklus));
    b.appendChild(ul);
    s.appendChild(b);
  }
  // ── Rocista ──
  // Rociste NIJE rok: to je zakazan termin pred sudom, ne pravna posledica.
  // Zato ima svoj podblok i nikad se ne mesa sa obavezama.
  const ro = uRocista(d.rocista, sada);
  const bRoc = el("div", "v2-podblok");
  bRoc.appendChild(el("h3", "v2-natkapa", "Ročišta"));
  if (d.rocistaPala) {
    bRoc.appendChild(prazno("Ročišta nisu učitana. Ovo ne znači da ih nema."));
  } else if (!ro.redovi.length) {
    bRoc.appendChild(prazno("Nema zakazanih ročišta."));
  } else {
    const ulR = el("ul", "v2-rok");
    for (const x of ro.redovi) {
      const liR = el("li", "v2-rok__red");
      if (x.proslo) liR.dataset.proslo = "1";
      const kadaR = el("span", "v2-rok__kada v2-mono");
      kadaR.appendChild(nevidljivo("Datum: "));
      kadaR.appendChild(document.createTextNode(x.datum + (x.vreme ? " " + x.vreme : "")));
      kadaR.appendChild(el("span", "v2-rok__rel", x.kada));
      liR.appendChild(kadaR);
      liR.appendChild(el("span", "v2-rok__opis", x.mesto || x.sud));
      ulR.appendChild(liR);
    }
    bRoc.appendChild(ulR);
  }
  if (radnje && radnje.osvezi) bRoc.appendChild(obrazacRocista(predmetId, ciklus, radnje.osvezi));
  s.appendChild(bRoc);

  // ── Zadaci ──
  // Zadatak je posao koji je advokat sam sebi zadao — ne rok i ne rociste.
  const za = uZadatke(d.zadaci, sada);
  const bZad = el("div", "v2-podblok");
  bZad.appendChild(el("h3", "v2-natkapa", "Zadaci"));
  if (d.zadaciPali) {
    bZad.appendChild(prazno("Zadaci nisu učitani. Ovo ne znači da ih nema."));
  } else if (!za.otvoreni.length && !za.zavrseni.length) {
    bZad.appendChild(prazno("Nema zadataka za ovaj predmet."));
  } else {
    const ulZ = el("ul", "v2-rok");
    for (const x of za.otvoreni) {
      const liZ = el("li", "v2-rok__red");
      if (x.proslo) liZ.dataset.proslo = "1";
      const kadaZ = el("span", "v2-rok__kada v2-mono");
      kadaZ.appendChild(nevidljivo("Rok: "));
      kadaZ.appendChild(document.createTextNode(x.datum || "—"));
      if (x.kada) kadaZ.appendChild(el("span", "v2-rok__rel", x.kada));
      liZ.appendChild(kadaZ);
      liZ.appendChild(el("span", "v2-rok__opis", x.naziv));
      ulZ.appendChild(liZ);
    }
    bZad.appendChild(ulZ);
    // Zavrsen zadatak se NE BRISE sa ekrana — on je dokaz da je posao uradjen.
    if (za.zavrseni.length) {
      bZad.appendChild(el("p", "v2-celina__prazno",
        za.zavrseni.length === 1 ? "1 završen zadatak."
                                 : za.zavrseni.length + " završenih zadataka."));
    }
  }
  if (radnje && radnje.osvezi) bZad.appendChild(obrazacZadatka(predmetId, ciklus, radnje.osvezi));
  s.appendChild(bZad);

  return s;
}

/* ── Montiranje ─────────────────────────────────────────────────────────── */

export function montirajDosije(kontejner, kontekst, predmetId, radnje) {
  const ciklus = napraviCiklus();

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--predmet");
  const sadrzaj = el("div", "v2-dosije");
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  unutra.appendChild(sadrzaj);
  kontejner.appendChild(unutra);

  if (!predmetId) {
    sadrzaj.appendChild(el("p", "v2-poruka__naslov", "Predmet nije naveden."));
    return ciklus;
  }

  sadrzaj.appendChild(el("p", "v2-celina__prazno", "Učitavanje predmeta…"));

  (async () => {
    const prekidac = ciklus.prekidac();
    let d;
    try {
      d = await ucitajDosije(predmetId, { signal: prekidac.signal });
    } catch (e) {
      if (jePrekid(e) || ciklus.ugasen) return;
      if (e && e.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      const p = el("div", "v2-poruka v2-poruka--greska");
      p.appendChild(el("p", "v2-poruka__naslov",
        e && e.vrsta === VRSTA.NEMA ? "Predmet nije pronađen" : "Predmet trenutno nije dostupan"));
      p.appendChild(el("p", "v2-poruka__telo", porukaZaKorisnika(e)));
      sadrzaj.replaceChildren(p);
      return;
    }
    if (ciklus.ugasen) return;

    document.title = `${d.zaglavlje.naziv} · Vindex`;

    // ── Lepljiva kontekstualna traka ──────────────────────────────────────
    const traka = el("div", "v2-predmet-traka");
    const trakaUnutra = el("div", "v2-scena__unutra v2-scena__unutra--predmet v2-predmet-traka__red");

    const nazad = el("a", "v2-predmet-traka__nazad", "← Predmeti");
    nazad.href = "/app-v2/predmeti";
    ciklus.slusaj(nazad, "click", (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
      e.preventDefault();
      idiNa("predmeti");
    });
    trakaUnutra.appendChild(nazad);

    const ime = el("span", "v2-predmet-traka__naziv", d.zaglavlje.naziv);
    ime.title = d.zaglavlje.naziv;
    trakaUnutra.appendChild(ime);

    const sidra = el("nav", "v2-predmet-traka__sidra");
    sidra.setAttribute("aria-label", "Celine predmeta");
    const veze = new Map();
    for (const c of SIDRA) {
      const a = el("a", "v2-sidro", c.naziv);
      a.href = "#celina-" + c.kljuc;
      a.dataset.celina = c.kljuc;
      veze.set(c.kljuc, a);
      sidra.appendChild(a);
    }
    trakaUnutra.appendChild(sidra);
    traka.appendChild(trakaUnutra);

    // ── Zaglavlje predmeta ────────────────────────────────────────────────
    const zaglavlje = el("header", "v2-dosije__zaglavlje");
    const h1 = el("h1", "v2-naslov v2-dosije__naziv", d.zaglavlje.naziv);
    zaglavlje.appendChild(h1);
    const linija = el("p", "v2-dosije__linija");
    if (d.zaglavlje.broj) linija.appendChild(el("span", "v2-mono", d.zaglavlje.broj));
    if (d.zaglavlje.vrsta) linija.appendChild(el("span", "v2-dosije__vrsta", d.zaglavlje.vrsta));
    const st = el("span", "v2-dosije__stanje", d.zaglavlje.stanje);
    st.dataset.stanje = d.zaglavlje.stanjeKlasa;
    linija.appendChild(st);
    zaglavlje.appendChild(linija);

    const okvir = document.createDocumentFragment();
    okvir.appendChild(zaglavlje);
    // Ishod radnje koja je zavrsila ovde (npr. dopuna posle otvaranja predmeta)
    // stoji odmah ispod naziva, ne kao prolazan oblacic koji korisnik propusti.
    const izPrethodne = elementPoruke();
    if (izPrethodne) okvir.appendChild(izPrethodne);
    const cStanje = sekcijaStanje(d, ciklus, predmetId, radnje);
    okvir.appendChild(cStanje);
    okvir.appendChild(sekcijaHronologija(d));
    okvir.appendChild(sekcijaAnaliza(d));
    okvir.appendChild(sekcijaSpisi(d, predmetId, ciklus, radnje));
    okvir.appendChild(sekcijaRokovi(d, ciklus, predmetId, radnje, new Date()));

    // Naplata se ucitava ODVOJENO i POSLE jezgra: Dosije ne sme da ceka na
    // billing da bi prikazao predmet, a pad naplate ne sme da obori Dosije.
    // Do odgovora stoji izricito „ucitava se" — prazna celina bi tvrdila da
    // na predmetu nema evidentiranog rada.
    const cNap = celina("naplata", "Naplata");
    cNap.appendChild(prazno("Učitava se…"));
    okvir.appendChild(cNap);
    sadrzaj.replaceChildren(okvir);

    (async () => {
      let n;
      try {
        n = await ucitajNaplatuPredmeta(predmetId, { signal: ciklus.prekidac().signal });
      } catch (e) {
        if (jePrekid(e) || ciklus.ugasen) return;
        n = { unosi: null, unosiPali: true, unosiGreska: e,
              tajmer: null, tajmerPao: true };
      }
      if (ciklus.ugasen) return;
      cNap.replaceChildren(naslovCeline("naplata", "Naplata"));
      cNap.appendChild(sadrzajNaplate(n, predmetId, d.zaglavlje.naziv,
                                      ciklus, radnje && radnje.osvezi
                                        ? radnje.osvezi : () => {}));
    })();

    // Saradnja (B18) se ucitava ODVOJENO, isti razlog kao Naplata iznad, uz
    // jednu razliku: kad korisnik NIJE vlasnik predmeta, `sadrzajSaradnje`
    // vraca `null` i ovde se NISTA ne dodaje -- nema flash-a praznog bloka
    // za retku, admin-tipa radnju koju vecina otvaranja Dosijea nece ni
    // koristiti.
    (async () => {
      let s;
      try {
        s = await ucitajSaradnjuPredmeta(predmetId, { signal: ciklus.prekidac().signal });
      } catch (e) {
        if (jePrekid(e) || ciklus.ugasen) return;
        return; // sekundarna radnja -- ne dodaj gresku u Stanje zbog nje
      }
      if (ciklus.ugasen) return;
      const blok = sadrzajSaradnje(s, predmetId, ciklus,
        radnje && radnje.osvezi ? radnje.osvezi : () => {});
      if (blok) cStanje.appendChild(blok);
    })();

    // Traka ide IZNAD sadrzaja, unutar iste papir scene.
    unutra.parentElement.insertBefore(traka, unutra);
    ciklus.dodaj(() => traka.remove());

    // Dolazak iz Danas nosi `#celina-rokovi`: klik na obavezu mora da spusti
    // advokata TACNO na rokove tog predmeta, ne na vrh Dosijea. Pretrazivac
    // to ne moze sam jer je sadrzaj iscrtan posle promene putanje.
    // Nepoznato sidro se tiho ignorise — nikad se ne skace nasumicno.
    if (window.location.hash) {
      const cilj = sadrzaj.querySelector(
        "#" + CSS.escape(window.location.hash.slice(1)));
      if (cilj) cilj.scrollIntoView({ block: "start" });
    }

    // ── Sidra prate poziciju ──────────────────────────────────────────────
    const celine = Array.from(sadrzaj.querySelectorAll(".v2-celina"));
    if ("IntersectionObserver" in window && celine.length) {
      const obs = new IntersectionObserver((unosi) => {
        const vidljivi = unosi.filter(u => u.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (!vidljivi) return;
        const kljuc = vidljivi.target.dataset.celina;
        for (const [k, a] of veze) {
          const akt = k === kljuc;
          a.classList.toggle("v2-sidro--aktivan", akt);
          if (akt) a.setAttribute("aria-current", "true");
          else a.removeAttribute("aria-current");
        }
      }, { rootMargin: "-96px 0px -70% 0px", threshold: 0 });
      for (const c of celine) obs.observe(c);
      ciklus.dodaj(() => obs.disconnect());
    }
  })();

  return ciklus;
}
