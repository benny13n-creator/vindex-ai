/* Vindex V2 — prostor ZNANJE (pravno istrazivanje).
 *
 * OVO NIJE CHAT. Nema mehurica, nema avatara, nema „kucam…" animacije. Advokat
 * ovde ne razgovara sa asistentom nego postavlja pravno pitanje i dobija
 * odgovor koji mora da moze da PROVERI. Zato je povrsina: pitanje, odgovor u
 * sirini za citanje, i izvori — uvek vidljivi, nikad sakriveni iza „prikaži
 * detalje".
 *
 * OGRADE IDU IZNAD ODGOVORA, NE ISPOD.
 * Ako pretraga korpusa nije uspela ili deo izvora nije proveren, to advokat
 * mora da procita PRE teksta, a ne posle njega. Ograda ispod odgovora se ne
 * cita — ta greska je vec jednom platena time sto je pad Pinecone upita
 * izgledao kao tvrdnja o zakonu.
 *
 * ODGOVOR SE NE KESIRA I NE PONAVLJA IZ ISTORIJE EKRANA kao da je nov. Svako
 * pitanje trosi kredit i pravi nov zapis; lazno „vec odgovoreno" bi sakrilo
 * da odgovor mozda vise ne vazi.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { sastaviOdgovor } from "../../domain/znanje.js";
import { idiNa, putanjaZa, idiNaPutanju } from "../../platform/router.js";

const NAJMANJE = 3;
const NAJVISE = 2000;

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

/** Tekst u pasuse; prelom se cuva, HTML se NIKAD ne interpretira. */
function uPasuse(tekst, klasa) {
  const okvir = document.createDocumentFragment();
  for (const deo of String(tekst || "").replace(/\r\n/g, "\n").split(/\n{2,}/)) {
    const t = deo.trim();
    if (!t) continue;
    const p = el("p", klasa);
    t.split("\n").forEach((r, i) => {
      if (i) p.appendChild(document.createElement("br"));
      p.appendChild(document.createTextNode(r));
    });
    okvir.appendChild(p);
  }
  return okvir;
}

function blokUpozorenja(u) {
  const d = el("div", "v2-ograda v2-ograda--" + u.kljuc);
  d.setAttribute("role", "alert");
  d.appendChild(el("p", "v2-ograda__naslov", u.naslov));
  d.appendChild(el("p", "v2-ograda__telo", u.telo));
  return d;
}

function blokIzvora(izvori) {
  const s = el("section", "v2-izvori");
  s.appendChild(el("h3", "v2-natkapa", `Izvori · ${izvori.length}`));
  const ul = el("ul", "v2-izvori__lista");
  for (const i of izvori) {
    const li = el("li", "v2-izvori__red");
    li.appendChild(el("span", "v2-izvori__zakon", i.zakon));
    // `i.clan` je vec normalizovan u domenu i sadrzi rec „clan" — ne dodaje se opet.
    if (i.clan) li.appendChild(el("span", "v2-izvori__clan", i.clan));
    ul.appendChild(li);
  }
  s.appendChild(ul);
  return s;
}

function blokCinjenica(cinjenice) {
  const s = el("section", "v2-cinjenice");
  s.appendChild(el("h3", "v2-natkapa", "Šta dokument navodi"));
  // Formulacija je namerna: dokument NAVODI, sistem ne UTVRĐUJE.
  s.appendChild(el("p", "v2-cinjenice__uvod",
    "Ovo su navodi iz spisa predmeta, ne utvrđene činjenice."));
  const ul = el("ul", "v2-lista-tanka");
  for (const c of cinjenice) {
    const li = el("li");
    li.appendChild(document.createTextNode(c.tekst));
    if (c.izvor) li.appendChild(el("span", "v2-cinjenice__izvor", " — " + c.izvor));
    ul.appendChild(li);
  }
  s.appendChild(ul);
  return s;
}

export function montirajZnanje(kontejner, kontekst) {
  const ciklus = napraviCiklus();
  const zaceto = kontekst || {};

  // ── Predmet iz upita (D7) ──
  // Pitanje se moze vezati za predmet: `/app-v2/znanje?predmet=<id>`. Radnja
  // se pokrece iz Dosijea, pa nema biraca predmeta — predmet je vec izabran
  // time sto je advokat dosao odande.
  let vezaniPredmet = "";
  try {
    vezaniPredmet = new URLSearchParams(window.location.search).get("predmet") || "";
  } catch (e) { vezaniPredmet = ""; }

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--predmet");

  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Znanje");
  h1.id = "v2-naslov-znanje";
  zaglavlje.appendChild(h1);
  zaglavlje.appendChild(el("p", "v2-podnaslov",
    "Pravno istraživanje po propisima Republike Srbije. Odgovor uvek dolazi sa izvorima "
    + "koje možete proveriti."));
  unutra.appendChild(zaglavlje);

  // Prebacivanje izmedju dva pitanja istog prostora. Nije tab bar: obe strane
  // su prave rute i mogu se podeliti.
  const prekidac = el("nav", "v2-prekidac");
  prekidac.setAttribute("aria-label", "Šta pitate");
  const ovde = el("span", "v2-prekidac__stavka v2-prekidac__stavka--aktivna", "Propisi");
  ovde.setAttribute("aria-current", "page");
  const kaPraksi = el("a", "v2-prekidac__stavka", "Sudska praksa");
  kaPraksi.href = putanjaZa("znanje", "praksa");
  ciklus.slusaj(kaPraksi, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("znanje", "praksa");
  });
  const kaRokovima = el("a", "v2-prekidac__stavka", "Rokovi");
  kaRokovima.href = putanjaZa("znanje", "rokovi");
  ciklus.slusaj(kaRokovima, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("znanje", "rokovi");
  });
  prekidac.append(ovde, kaPraksi, kaRokovima);
  unutra.appendChild(prekidac);

  // Kad je pitanje vezano za predmet, to MORA biti vidljivo pre kucanja:
  // advokat inace ne zna da salje sadrzaj predmeta u upit.
  if (vezaniPredmet) {
    const traka = el("div", "v2-znanje__vezano");
    traka.appendChild(el("span", "v2-znanje__vezano-tekst",
      "Pitanje se postavlja u kontekstu otvorenog predmeta."));
    const kaPredmetu = el("a", "v2-tekst-akcija", "Otvori predmet");
    kaPredmetu.href = putanjaZa("predmet", vezaniPredmet);
    ciklus.slusaj(kaPredmetu, "click", (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
      e.preventDefault();
      idiNaPutanju(putanjaZa("predmet", vezaniPredmet));
    });
    // Natpis NE sme da pocinje sa „Pitaj": pored dugmeta „Pitaj" ispod, dva
    // dugmeta koja pocinju istom recju su zamka pri brzom pogledu.
    const odveži = el("button", "v2-tekst-akcija", "Ukloni predmet iz pitanja");
    odveži.type = "button";
    ciklus.slusaj(odveži, "click", () => {
      vezaniPredmet = "";
      traka.remove();
      // Putanja se ciscenjem upita usklađuje sa stanjem: podeljena veza ne
      // sme da vodi u ekran koji tvrdi drugaciji kontekst.
      try { window.history.replaceState({}, "", putanjaZa("znanje")); }
      catch (e) { /* nebitno */ }
    });
    traka.append(kaPredmetu, odveži);
    unutra.appendChild(traka);
  }

  const forma = el("form", "v2-forma v2-znanje__forma");
  forma.noValidate = true;
  const lab = el("label", "v2-polje-unos__labela", "Pravno pitanje");
  lab.htmlFor = "v2-znanje-pitanje";
  const polje = el("textarea", "v2-polje-unos__kontrola v2-znanje__polje");
  polje.id = "v2-znanje-pitanje";
  polje.name = "pitanje";
  polje.rows = 3;
  polje.maxLength = NAJVISE;
  polje.placeholder = "Npr. Koji je rok za žalbu na presudu u parničnom postupku?";
  polje.value = zaceto.pitanje || "";
  const pomoc = el("p", "v2-polje-unos__pomoc",
    "Ctrl+Enter šalje pitanje. Svako pitanje troši jedan kredit.");
  const radnje = el("div", "v2-forma__radnje");
  const posalji_dugme = el("button", "v2-dugme v2-dugme--glavno", "Pitaj");
  posalji_dugme.type = "submit";
  radnje.appendChild(posalji_dugme);
  forma.append(lab, polje, pomoc, radnje);
  unutra.appendChild(forma);

  const sadrzaj = el("div", "v2-znanje");
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  sadrzaj.setAttribute("aria-labelledby", "v2-naslov-znanje");
  unutra.appendChild(sadrzaj);
  kontejner.appendChild(unutra);
  polje.focus();
  document.title = "Znanje · Vindex";

  let poslednji = zaceto.odgovor || null;
  let radi = false;

  function prazno() {
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
      "Postavite pitanje. Vindex pretražuje zakonski korpus i, ako ste u predmetu, "
      + "njegove spise — pa navodi šta je našao i šta nije."));
  }

  function iscrtaj(o, pitanje) {
    const okvir = document.createDocumentFragment();

    const p = el("section", "v2-znanje__pitanje");
    p.appendChild(el("h2", "v2-natkapa", "Pitanje"));
    p.appendChild(el("p", "v2-znanje__pitanje-tekst", pitanje));
    okvir.appendChild(p);

    // D7: kontekst predmeta se ubacuje FAIL-CLOSED. Kad je tražen a nije
    // pročitan, advokat to mora znati — inače čita opšti odgovor kao odgovor
    // o svom predmetu.
    if (o.kontekstPredmeta === false) {
      const up = el("div", "v2-poruka v2-poruka--upozorenje");
      up.setAttribute("role", "alert");
      up.appendChild(el("p", "v2-poruka__naslov", "Spisi predmeta nisu ušli u pitanje"));
      up.appendChild(el("p", "v2-poruka__telo",
        "Odgovor je opšti — nije zasnovan na beleškama ovog predmeta. "
        + "Ovo se dešava kada predmet nije dostupan ili je u postupku brisanja."));
      okvir.appendChild(up);
    } else if (o.kontekstPredmeta === true) {
      okvir.appendChild(el("p", "v2-celina__prazno",
        "Uz zakonski korpus, u pitanje su ušle i beleške ovog predmeta."));
    }

    // Ograde IZNAD odgovora — advokat ih mora videti pre teksta.
    for (const u of o.upozorenja) okvir.appendChild(blokUpozorenja(u));

    // Statusna potvrda (N3/AUTH-001) kaze da li je odredba DOSLOVNO potvrdjena
    // u bazi ili je tekst parafraziran. Backend je stavlja u sredinu odgovora,
    // gde je niko ne procita; ovde stoji uz ograde, iznad teksta.
    if (o.potvrda && !o.potvrda.doslovno) {
      okvir.appendChild(blokUpozorenja({
        kljuc: "nije-doslovno",
        naslov: "Tekst odredbe nije doslovno potvrđen",
        telo: o.potvrda.poruka + " Pre citiranja proverite tačan tekst u „Službenom glasniku“.",
      }));
    }

    const a = el("section", "v2-znanje__odgovor");
    const zagl = el("div", "v2-znanje__zaglavlje-odgovora");
    zagl.appendChild(el("h2", "v2-natkapa", "Odgovor"));
    if (o.sigurnost) {
      const sig = el("span", "v2-sigurnost", o.sigurnost.naziv);
      sig.dataset.nivo = o.sigurnost.klasa;
      zagl.appendChild(sig);
    }
    a.appendChild(zagl);

    // Agent vraca STRUKTURISAN dokument („--- BRZA PROCENA", „--- PRAVNI
    // ZAKLJUČAK", „--- CITAT ZAKONA [RAG]"…). Odeljci se iscrtavaju kao
    // odeljci; ravno iscrtavanje bi te crte pretvorilo u smece na ekranu i
    // izgubilo jedinu strukturu koju odgovor ima. Sadrzaj se NE menja.
    if (o.odeljci && o.odeljci.length > 1) {
      for (const d of o.odeljci) {
        const blok = el("div", "v2-znanje__odeljak");
        if (d.naslov) blok.appendChild(el("h3", "v2-natkapa", d.naslov));
        blok.appendChild(uPasuse(d.telo, "v2-znanje__pasus"));
        a.appendChild(blok);
      }
    } else {
      a.appendChild(uPasuse(o.tekst, "v2-znanje__pasus"));
    }
    okvir.appendChild(a);

    if (o.cinjenice.length) okvir.appendChild(blokCinjenica(o.cinjenice));
    if (o.izvori.length) okvir.appendChild(blokIzvora(o.izvori));

    okvir.appendChild(el("p", "v2-znanje__odricanje",
      "Odgovor je pomoć u istraživanju, ne pravni savet. Proverite navedene odredbe "
      + "pre nego što ih upotrebite u podnesku."));

    sadrzaj.replaceChildren(okvir);
  }

  if (poslednji && zaceto.postavljeno) iscrtaj(poslednji, zaceto.postavljeno);
  else prazno();

  async function pitaj() {
    if (radi) return;
    const q = polje.value.trim();
    if (q.length < NAJMANJE) {
      sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
        `Pitanje mora imati najmanje ${NAJMANJE} znaka.`));
      polje.focus();
      return;
    }

    radi = true;
    posalji_dugme.disabled = true;
    posalji_dugme.textContent = "Traži…";
    sadrzaj.setAttribute("aria-busy", "true");
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
      "Pretražuju se propisi. Ovo može potrajati nekoliko sekundi."));

    const prekidac = ciklus.prekidac();
    let sirov;
    try {
      const telo = { pitanje: q };
      if (vezaniPredmet) telo.predmet_id = vezaniPredmet;
      sirov = await posalji("/api/pitanje", { telo, signal: prekidac.signal });
    } catch (e) {
      if (jePrekid(e) || ciklus.ugasen) return;
      radi = false;
      posalji_dugme.disabled = false;
      posalji_dugme.textContent = "Pitaj";
      sadrzaj.setAttribute("aria-busy", "false");
      if (e && e.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      const d = el("div", "v2-poruka v2-poruka--greska");
      d.appendChild(el("p", "v2-poruka__naslov",
        e && e.vrsta === VRSTA.ZABRANJENO
          ? "Ovaj nalog nema pristup pravnom istraživanju"
          : "Pitanje nije obrađeno"));
      d.appendChild(el("p", "v2-poruka__telo",
        porukaZaKorisnika(e) + " Odsustvo odgovora nije odgovor — ne zaključujte ništa iz njega."));
      sadrzaj.replaceChildren(d);
      return;
    }
    if (ciklus.ugasen) return;

    radi = false;
    posalji_dugme.disabled = false;
    posalji_dugme.textContent = "Pitaj";
    sadrzaj.setAttribute("aria-busy", "false");

    poslednji = sastaviOdgovor(sirov);
    zaceto.postavljeno = q;
    iscrtaj(poslednji, q);
    sadrzaj.focus();
  }

  ciklus.slusaj(forma, "submit", (e) => { e.preventDefault(); pitaj(); });
  ciklus.slusaj(polje, "keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); pitaj(); }
  });

  ciklus.kontekst = () => ({
    pitanje: polje.value, odgovor: poslednji, postavljeno: zaceto.postavljeno,
  });

  return ciklus;
}
