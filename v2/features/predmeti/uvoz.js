/* Vindex V2 — uvoz predmeta iz dokumenta (`/app-v2/predmeti/uvoz`), A7.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * PREDMET NASTAJE IZ DOKUMENTA, ALI NE BEZ ADVOKATA
 *
 * Dokument se otprema, sistem izvlaci podatke, a advokat ih PREGLEDA i tek
 * onda pravi predmet. Nijedan podatak se ne upisuje u predmet dok advokat ne
 * potvrdi ko je njegov klijent — jer od toga zavisi provera sukoba interesa.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * „PROVERA JE ZAKAZANA" NIJE „NEMA SUKOBA". Finalizovanje ZAKAZUJE proveru
 * sukoba; rezultat stize kasnije. Ovaj ekran nikada ne pise „nema sukoba" —
 * pise u kom je stanju provera, i kad provera NIJE zakazana (`COI_FAILED`)
 * to je glasno upozorenje, ne fusnota.
 *
 * OBRADA JE ASINHRONA. Otpremanje vraca 202 i posao ide u red; ekran prati
 * stanje i NE tvrdi da je gotovo dok server to ne kaze. Prekid pracenja
 * (odlazak sa ekrana) ne otkazuje posao — to se kaze.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { dohvati, posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { ostavi } from "../../platform/obavestenje.js";
import { idiNa, putanjaZa, idiNaPutanju } from "../../platform/router.js";
import { uPosao, uPoslove, uIshodUvoza, nedostaciUvoza } from "../../domain/uvoz.js";

/** Koliko cesto se pita za stanje posla. Obrada traje desetinama sekundi. */
const RAZMAK_MS = 3000;
/** Gornja granica cekanja: posle ovoga se KAZE da se ne ceka vise. */
const NAJDUZE_MS = 5 * 60 * 1000;

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

export function montirajUvoz(kontejner) {
  const ciklus = napraviCiklus();
  let posao = null;
  let jobId = "";
  let pracenjeOd = 0;
  let tajmer = null;

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--tekst");

  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Uvoz iz dokumenta");
  h1.id = "v2-naslov-uvoz";
  zaglavlje.appendChild(h1);
  zaglavlje.appendChild(el("p", "v2-podnaslov",
    "Otpremite presudu, tužbu ili ugovor. Sistem izvlači podatke, vi ih "
    + "pregledate, i tek onda nastaje predmet."));
  unutra.appendChild(zaglavlje);

  const prekidac = el("nav", "v2-prekidac");
  prekidac.setAttribute("aria-label", "Kako otvarate predmet");
  const kaRucno = el("a", "v2-prekidac__stavka", "Ručno");
  kaRucno.href = putanjaZa("predmeti", "nov");
  ciklus.slusaj(kaRucno, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("predmeti", "nov");
  });
  const ovde = el("span", "v2-prekidac__stavka v2-prekidac__stavka--aktivna", "Iz dokumenta");
  ovde.setAttribute("aria-current", "page");
  prekidac.append(kaRucno, ovde);
  unutra.appendChild(prekidac);

  // ── Otpremanje ──
  const forma = el("form", "v2-forma");
  forma.noValidate = true;
  const omot = el("div", "v2-polje-unos");
  const lab = el("label", "v2-polje-unos__labela", "Dokument");
  lab.htmlFor = "v2-uvoz-fajl";
  const fajl = el("input", "v2-polje-unos__kontrola");
  fajl.type = "file";
  fajl.id = "v2-uvoz-fajl";
  // Samo ono sto server stvarno prima: ponuditi vrstu koju odbija znaci
  // kontrolu koja pada tek posle otpremanja.
  fajl.accept = ".pdf,.png,.jpg,.jpeg,.docx";
  fajl.multiple = true;
  const pomoc = el("p", "v2-polje-unos__pomoc",
    "PDF, slika ili DOCX. Obrada traje do minut i teče na serveru — možete "
    + "otići sa ekrana, posao se ne prekida.");
  omot.append(lab, fajl, pomoc);

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;

  const radnje = el("div", "v2-forma__radnje");
  const dugme = el("button", "v2-dugme v2-dugme--glavno", "Otpremi i obradi");
  dugme.type = "submit";
  radnje.appendChild(dugme);
  forma.append(omot, poruka, radnje);
  unutra.appendChild(forma);

  const sadrzaj = el("div", "v2-uvoz");
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  sadrzaj.setAttribute("aria-labelledby", "v2-naslov-uvoz");
  unutra.appendChild(sadrzaj);
  kontejner.appendChild(unutra);
  document.title = "Uvoz iz dokumenta · Vindex";

  ciklus.dodaj(() => { if (tajmer) clearTimeout(tajmer); });

  function javi(t, vrsta) {
    poruka.className = "v2-forma__poruka v2-forma__poruka--" + (vrsta || "greska");
    poruka.textContent = t;
    poruka.hidden = false;
  }

  /* ── Prikaz posla ─────────────────────────────────────────────────────── */
  function redEntiteta(e) {
    const li = el("li", "v2-uvoz__entitet");
    if (e.trebaPregled) li.dataset.pregled = "1";
    li.appendChild(el("span", "v2-uvoz__polje", e.naziv));

    // Odsutna vrednost se IMENUJE kao odsutna, ne prikazuje kao prazno polje.
    if (e.nadjen) {
      li.appendChild(el("span", "v2-uvoz__vrednost", " " + e.vrednost));
    } else {
      // Recenica mora biti gramaticna bez obzira na rod naziva polja
      // („Iznos nije pronađeno" nije srpski).
      li.appendChild(el("span", "v2-uvoz__vrednost v2-uvoz__vrednost--nema",
        " — podatak nije pronađen u dokumentu"));
    }
    if (e.pouzdanost !== null) {
      li.appendChild(el("span", "v2-uvoz__pouzdanost v2-mono",
        " " + Math.round(e.pouzdanost * 100) + "%"));
    }
    if (e.ispravljen) li.appendChild(el("span", "v2-znak", "ispravljeno"));

    // Ispravka je tu gde je i podatak — advokat ne trazi zaseban ekran.
    if (e.id) li.appendChild(kontrolaIspravke(e));
    return li;
  }

  function kontrolaIspravke(e) {
    const omotI = el("span", "v2-uvoz__ispravka");
    const otvori = el("button", "v2-tekst-akcija", "Ispravi");
    otvori.type = "button";
    otvori.setAttribute("aria-label", "Ispravi polje " + e.naziv);
    omotI.appendChild(otvori);

    ciklus.slusaj(otvori, "click", () => {
      if (omotI.querySelector("form")) return;
      otvori.hidden = true;
      const f = el("form", "v2-forma v2-uvoz__forma-ispravke");
      f.noValidate = true;
      const red = el("div", "v2-radnja__red");
      const unos = el("input", "v2-polje-unos__kontrola");
      unos.type = "text";
      unos.value = e.vrednost || "";
      unos.setAttribute("aria-label", "Nova vrednost za " + e.naziv);
      const cuvaj = el("button", "v2-dugme", "Sačuvaj");
      cuvaj.type = "submit";
      const odustani = el("button", "v2-dugme v2-dugme--tiho", "Odustani");
      odustani.type = "button";
      red.append(unos, cuvaj, odustani);
      const p2 = el("div", "v2-forma__poruka");
      p2.setAttribute("role", "alert");
      p2.hidden = true;
      f.append(red, p2);
      omotI.appendChild(f);
      unos.focus();

      ciklus.slusaj(odustani, "click", () => {
        f.remove(); otvori.hidden = false; otvori.focus();
      });

      ciklus.slusaj(f, "submit", async (ev) => {
        ev.preventDefault();
        const v = unos.value.trim();
        if (!v) {
          p2.className = "v2-forma__poruka v2-forma__poruka--greska";
          p2.textContent = "Unesite vrednost. Prazno polje se ne čuva kao ispravka.";
          p2.hidden = false;
          return;
        }
        cuvaj.disabled = true;
        cuvaj.textContent = "Čuva se…";
        try {
          await posalji(`/api/smart-intake/entities/${encodeURIComponent(e.id)}/correct`, {
            telo: { corrected_value: v }, signal: ciklus.prekidac().signal,
          });
          if (ciklus.ugasen) return;
          ostavi("Podatak je ispravljen.", "uspeh");
          await osveziPosao();
        } catch (err) {
          if (jePrekid(err) || ciklus.ugasen) return;
          cuvaj.disabled = false;
          cuvaj.textContent = "Sačuvaj";
          if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
          p2.className = "v2-forma__poruka v2-forma__poruka--greska";
          p2.textContent = "Ispravka nije sačuvana. " + porukaZaKorisnika(err);
          p2.hidden = false;
        }
      });
    });
    return omotI;
  }

  function blokFinalizovanja(p) {
    const b = el("div", "v2-podblok");
    b.appendChild(el("h3", "v2-natkapa", "Napravi predmet"));

    if (p.predmetId) {
      const gotov = el("p", "v2-celina__prazno");
      gotov.appendChild(document.createTextNode("Iz ovog dokumenta je već napravljen predmet. "));
      const a = el("a", "v2-tekst-akcija", "Otvori predmet");
      a.href = putanjaZa("predmet", p.predmetId);
      ciklus.slusaj(a, "click", (e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        e.preventDefault();
        idiNaPutanju(putanjaZa("predmet", p.predmetId));
      });
      gotov.appendChild(a);
      b.appendChild(gotov);
      return b;
    }

    const f = el("form", "v2-forma");
    f.noValidate = true;

    // Ko je NAS klijent odlucuje provera sukoba interesa — zato je to izbor
    // advokata, a ne pretpostavka sistema.
    const omotS = el("div", "v2-polje-unos");
    const labS = el("label", "v2-polje-unos__labela", "Koja strana je vaš klijent");
    labS.htmlFor = "v2-uvoz-strana";
    const strana = el("select", "v2-polje-unos__kontrola");
    strana.id = "v2-uvoz-strana";
    const prazna = document.createElement("option");
    prazna.value = "";
    prazna.textContent = "Izaberite stranu";
    strana.appendChild(prazna);
    for (const e of p.stranke) {
      const o = document.createElement("option");
      o.value = e.tip;
      o.textContent = e.naziv + (e.nadjen ? " — " + e.vrednost
          : " — nije pronađen u dokumentu");
      strana.appendChild(o);
    }
    if (!p.stranke.length) {
      for (const [v, t] of [["plaintiff", "Tužilac"], ["defendant", "Tuženi"]]) {
        const o = document.createElement("option");
        o.value = v;
        o.textContent = t + " — nije pronađeno u dokumentu";
        strana.appendChild(o);
      }
    }
    const pomocS = el("p", "v2-polje-unos__pomoc",
      "Od ovoga zavisi provera sukoba interesa — sistem ne pogađa ko je vaš klijent.");
    omotS.append(labS, strana, pomocS);

    const omotN = el("div", "v2-polje-unos");
    const labN = el("label", "v2-polje-unos__labela", "Naziv predmeta (opciono)");
    labN.htmlFor = "v2-uvoz-naziv";
    const naziv = el("input", "v2-polje-unos__kontrola");
    naziv.id = "v2-uvoz-naziv";
    naziv.type = "text";
    naziv.maxLength = 200;
    omotN.append(labN, naziv);

    const p3 = el("div", "v2-forma__poruka");
    p3.setAttribute("role", "alert");
    p3.hidden = true;
    const r3 = el("div", "v2-forma__radnje");
    const napravi = el("button", "v2-dugme v2-dugme--glavno", "Napravi predmet");
    napravi.type = "submit";
    r3.appendChild(napravi);
    f.append(omotS, omotN, p3, r3);
    b.appendChild(f);

    ciklus.slusaj(f, "submit", async (ev) => {
      ev.preventDefault();
      const g = nedostaciUvoza({ strana: strana.value, naziv: naziv.value });
      if (g.length) {
        p3.className = "v2-forma__poruka v2-forma__poruka--greska";
        p3.textContent = g.join(" ");
        p3.hidden = false;
        return;
      }
      napravi.disabled = true;
      napravi.textContent = "Pravi se…";
      p3.hidden = true;
      try {
        const telo = { klijent_strana: strana.value };
        if (naziv.value.trim()) telo.naziv = naziv.value.trim();
        const r = await posalji(
          `/api/smart-intake/jobs/${encodeURIComponent(p.id)}/finalize`,
          { telo, signal: ciklus.prekidac().signal });
        if (ciklus.ugasen) return;
        prikaziIshod(uIshodUvoza(r));
      } catch (err) {
        if (jePrekid(err) || ciklus.ugasen) return;
        napravi.disabled = false;
        napravi.textContent = "Napravi predmet";
        if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
        p3.className = "v2-forma__poruka v2-forma__poruka--"
          + (err && err.vrsta === VRSTA.MREZA ? "upozorenje" : "greska");
        p3.textContent = (err && err.vrsta === VRSTA.MREZA)
          // Mrezni kvar pri upisu NIJE dokaz da predmet nije napravljen.
          ? "Veza je prekinuta pre nego što je stigao odgovor. Predmet je možda "
            + "napravljen — proverite registar pre nego što pokušate ponovo."
          : "Predmet nije napravljen. " + porukaZaKorisnika(err);
        p3.hidden = false;
      }
    });

    return b;
  }

  function prikaziIshod(i) {
    const okvir = document.createDocumentFragment();

    // ── Stanje provere sukoba: NIKAD „nema sukoba" ──
    const coi = el("div", "v2-ograda");
    coi.setAttribute("role", "alert");
    coi.dataset.coi = i.coi;
    if (i.coiOtkazala) {
      coi.className = "v2-ograda v2-ograda--nacrt";
      coi.appendChild(el("p", "v2-ograda__naslov",
        "Provera sukoba interesa NIJE zakazana"));
      coi.appendChild(el("p", "v2-ograda__telo",
        "Predmet je napravljen, ali provera sukoba nije pokrenuta i niko je "
        + "neće izvršiti. Pokrenite je ručno pre nego što preduzmete bilo šta "
        + "u ovom predmetu."));
    } else if (i.coiZakazana) {
      coi.className = "v2-ograda";
      coi.appendChild(el("p", "v2-ograda__naslov", "Provera sukoba interesa je zakazana"));
      coi.appendChild(el("p", "v2-ograda__telo",
        "Provera se izvršava u pozadini i rezultat još ne postoji. "
        + "Odsustvo upozorenja u ovom trenutku NE znači da sukoba nema."));
    } else {
      coi.className = "v2-ograda v2-ograda--nacrt";
      coi.appendChild(el("p", "v2-ograda__naslov", "Provera sukoba interesa nije pokrenuta"));
      coi.appendChild(el("p", "v2-ograda__telo",
        "Ime stranke nije bilo poznato, pa provera nije ni zakazana. "
        + "Unesite stranke u predmet i pokrenite proveru."));
    }
    okvir.appendChild(coi);

    const s = el("section", "v2-uvoz__ishod");
    s.appendChild(el("h2", "v2-natkapa", "Predmet je napravljen"));
    if (i.naziv) s.appendChild(el("p", "v2-uvoz__naziv", i.naziv));

    const dl = el("ul", "v2-lista-tanka");
    function stavka(t) { dl.appendChild(el("li", "", t)); }

    if (i.klijentNesiguran) {
      stavka(`Klijent NIJE povezan: pronađeno je ${i.klijentKandidata} `
        + "klijenata sa istim imenom, a sistem ne bira između njih. "
        + "Povežite klijenta ručno u predmetu.");
    } else if (i.klijentDodat) {
      stavka("Klijent je povezan sa predmetom.");
    } else {
      stavka("Klijent nije povezan — ime stranke nije bilo poznato.");
    }

    if (i.rokDodat) {
      stavka("Rok iz dokumenta je unet u predmet.");
    } else if (i.rokRazlog) {
      // „nije dodat" ne razlikuje „nema roka" od „rok nije dokazan" — razlog
      // je informacija koju advokat mora da vidi.
      stavka("Rok NIJE unet: " + i.rokRazlog);
    } else {
      stavka("Rok nije unet — u dokumentu nije pronađen rok.");
    }

    stavka(i.dokumentPovezan
      ? "Dokument je priložen uz predmet."
      : "Dokument NIJE priložen uz predmet.");
    s.appendChild(dl);

    if (i.predmetId) {
      const a = el("a", "v2-dugme v2-dugme--glavno", "Otvori predmet");
      a.href = putanjaZa("predmet", i.predmetId);
      ciklus.slusaj(a, "click", (e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        e.preventDefault();
        idiNaPutanju(putanjaZa("predmet", i.predmetId));
      });
      const red = el("div", "v2-forma__radnje");
      red.appendChild(a);
      s.appendChild(red);
    }
    okvir.appendChild(s);
    sadrzaj.replaceChildren(okvir);
    sadrzaj.focus();
  }

  function iscrtaj(p) {
    const okvir = document.createDocumentFragment();

    const glava = el("section", "v2-uvoz__glava");
    glava.appendChild(el("h2", "v2-natkapa", p.fajl || "Dokument"));
    const st = el("p", "v2-uvoz__stanje");
    st.dataset.status = p.status;
    st.textContent = p.stanjeTekst;
    glava.appendChild(st);

    if (p.pao) {
      const g = el("div", "v2-poruka v2-poruka--greska");
      g.appendChild(el("p", "v2-poruka__naslov", "Dokument nije obrađen"));
      g.appendChild(el("p", "v2-poruka__telo",
        (p.greska ? p.greska + " " : "")
        + "Predmet iz ovog dokumenta nije napravljen. Možete ga otpremiti "
        + "ponovo ili otvoriti predmet ručno."));
      glava.appendChild(g);
      okvir.appendChild(glava);
      sadrzaj.replaceChildren(okvir);
      return;
    }

    if (!p.zavrsen) {
      glava.appendChild(el("p", "v2-celina__prazno",
        "Obrada teče na serveru. Ovaj ekran prati stanje; posao se nastavlja "
        + "i ako odete sa ekrana."));
      okvir.appendChild(glava);
      sadrzaj.replaceChildren(okvir);
      return;
    }

    if (p.dokument.tip) {
      const d = el("p", "v2-uvoz__tip");
      d.appendChild(document.createTextNode("Prepoznato kao: " + (p.dokument.tipNaziv || p.dokument.tip)));
      if (p.dokument.pouzdanost !== null) {
        d.appendChild(el("span", "v2-uvoz__pouzdanost v2-mono",
          " " + Math.round(p.dokument.pouzdanost * 100) + "%"));
      }
      glava.appendChild(d);
      if (p.dokument.ocr) {
        glava.appendChild(el("p", "v2-celina__prazno",
          "Tekst je pročitan sa slike (OCR) — proverite izvučene podatke pažljivije."));
      }
      if (p.dokument.mozeBitiZastareo) {
        glava.appendChild(el("p", "v2-celina__prazno",
          "Prepoznavanje vrste dokumenta može biti zastarelo."));
      }
    }
    okvir.appendChild(glava);

    const b = el("div", "v2-podblok");
    b.appendChild(el("h3", "v2-natkapa", "Izvučeni podaci"));
    if (!p.entiteti.length) {
      b.appendChild(el("p", "v2-celina__prazno",
        "Iz dokumenta nije izvučen nijedan podatak. Predmet možete otvoriti "
        + "ručno i priložiti dokument."));
    } else {
      if (p.zaPregled.length) {
        // Broj se KAZE: advokat mora znati koliko podataka traži njegov pogled
        // pre nego što napravi predmet.
        b.appendChild(el("p", "v2-poruka v2-poruka--upozorenje",
          p.zaPregled.length === 1
            ? "1 podatak traži vaš pregled pre nego što napravite predmet."
            : `${p.zaPregled.length} podataka traži vaš pregled pre nego što napravite predmet.`));
      }
      const ul = el("ul", "v2-uvoz__lista");
      for (const e of p.entiteti) ul.appendChild(redEntiteta(e));
      b.appendChild(ul);
    }
    okvir.appendChild(b);

    okvir.appendChild(blokFinalizovanja(p));
    sadrzaj.replaceChildren(okvir);
  }

  /* ── Pracenje posla ───────────────────────────────────────────────────── */
  async function osveziPosao() {
    if (!jobId) return;
    try {
      const r = await dohvati(`/api/smart-intake/jobs/${encodeURIComponent(jobId)}`,
                              { signal: ciklus.prekidac().signal });
      if (ciklus.ugasen) return;
      posao = uPosao(r);
      iscrtaj(posao);
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      const g = el("div", "v2-poruka v2-poruka--greska");
      g.appendChild(el("p", "v2-poruka__naslov", "Stanje obrade nije učitano"));
      g.appendChild(el("p", "v2-poruka__telo",
        porukaZaKorisnika(err)
        + " Posao se možda i dalje obrađuje — ne otpremajte dokument ponovo "
        + "dok ne proverite."));
      sadrzaj.replaceChildren(g);
    }
  }

  function zakaziPracenje() {
    if (tajmer) clearTimeout(tajmer);
    tajmer = setTimeout(async () => {
      if (ciklus.ugasen) return;
      await osveziPosao();
      if (ciklus.ugasen) return;
      if (posao && posao.zavrsen) return;
      if (Date.now() - pracenjeOd > NAJDUZE_MS) {
        // Cekanje se NE produzava u beskraj tiho: kaze se da ekran vise ne
        // prati, a posao i dalje tece.
        sadrzaj.appendChild(el("p", "v2-celina__prazno",
          "Obrada traje duže nego obično. Ovaj ekran više ne prati stanje — "
          + "posao i dalje teče na serveru. Osvežite stranicu kasnije."));
        return;
      }
      zakaziPracenje();
    }, RAZMAK_MS);
    ciklus.dodaj(() => { if (tajmer) clearTimeout(tajmer); });
  }

  ciklus.slusaj(forma, "submit", async (e) => {
    e.preventDefault();
    const fajlovi = fajl.files;
    if (!fajlovi || !fajlovi.length) {
      javi("Izaberite bar jedan dokument.");
      return;
    }
    dugme.disabled = true;
    dugme.textContent = "Otprema se…";
    poruka.hidden = true;
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno", "Dokument se otprema…"));

    const podaci = new FormData();
    for (const f of fajlovi) podaci.append("files", f, f.name);

    let r;
    try {
      r = await posalji("/api/smart-intake/documents",
                        { telo: podaci, signal: ciklus.prekidac().signal });
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      dugme.disabled = false;
      dugme.textContent = "Otpremi i obradi";
      sadrzaj.replaceChildren();
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      if (err && err.status === 429) {
        javi("Dostigli ste granicu otpremanja za ovaj minut. Sačekajte i "
           + "pokušajte ponovo — ovo nije kvar.", "upozorenje");
        return;
      }
      javi("Dokument nije otpremljen. " + porukaZaKorisnika(err));
      return;
    }
    if (ciklus.ugasen) return;

    dugme.disabled = false;
    dugme.textContent = "Otpremi i obradi";
    const u = uPoslove(r);
    if (u.nastavlja && u.preostali.length) {
      // Prekinut batch se NE precutkuje.
      javi(`Primljeno je ${u.poslovi.length} od ${u.ukupno} dokumenata. Nisu `
        + "primljeni: " + u.preostali.join(", ")
        + ". Otpremite ih ponovo — nisu izgubljeni, ali nisu ni obrađeni.",
        "upozorenje");
    }
    if (!u.poslovi.length || !u.poslovi[0].id) {
      sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
        "Server je primio zahtev, ali nije vratio posao za praćenje. "
        + "Proverite registar pre ponovnog otpremanja."));
      return;
    }
    // Prati se PRVI posao; ostali teku i vide se posle osvezavanja.
    jobId = u.poslovi[0].id;
    pracenjeOd = Date.now();
    if (u.poslovi.length > 1) {
      ostavi(`Otpremljeno je ${u.poslovi.length} dokumenata. Prati se prvi.`, "uspeh");
    }
    await osveziPosao();
    if (posao && !posao.zavrsen) zakaziPracenje();
  });

  sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
    "Otpremite dokument da biste videli šta je iz njega izvučeno."));

  return ciklus;
}
