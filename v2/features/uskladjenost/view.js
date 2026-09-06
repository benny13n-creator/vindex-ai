/* Vindex V2 — prostor USKLAĐENOST (digitalna imovina).
 *
 * Pet analiza, jedan ekran. Sve dele isti ugovor sa serverom, pa bi pet
 * skoro istih ekrana bilo pet mesta na kojima se ista ograda moze zaboraviti.
 *
 * Izbor analize menja PITANJE na koje se odgovara, a ne raspored ekrana:
 * advokat bira „da li je ovo uskladjeno", ne „koji modul da pokrenem".
 *
 * OGRADA STOJI IZNAD REZULTATA i nije uslovna — vidi `domain/uskladjenost.js`
 * za razlog. Ove rute ne vracaju izvore, pa se poreklo zakljucka ne moze
 * prikazati ni kad je zakljucak tacan.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { ANALIZE, analizaPoKljucu, uNalaz } from "../../domain/uskladjenost.js";
import { uSkorIzvestaj } from "../../domain/skorIzvestaj.js";
import { uUgovorAnalizu } from "../../domain/ugovorAnaliza.js";
import { blokWalletProvenance, blokSourceOfFundsDossier } from "./dodatne.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

function uPasuse(t, klasa) {
  const okvir = document.createDocumentFragment();
  for (const deo of String(t || "").replace(/\r\n/g, "\n").split(/\n{2,}/)) {
    const s = deo.trim();
    if (!s) continue;
    const p = el("p", klasa);
    s.split("\n").forEach((r, i) => {
      if (i) p.appendChild(document.createElement("br"));
      p.appendChild(document.createTextNode(r));
    });
    okvir.appendChild(p);
  }
  return okvir;
}

export function montirajUskladjenost(kontejner, kontekst) {
  const ciklus = napraviCiklus();
  const zaceto = kontekst || {};
  let izabrana = analizaPoKljucu(zaceto.analiza) || ANALIZE[0];

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--predmet");

  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Usklađenost");
  h1.id = "v2-naslov-uskladjenost";
  zaglavlje.appendChild(h1);
  zaglavlje.appendChild(el("p", "v2-podnaslov",
    "Digitalna imovina: Zakon o digitalnoj imovini i MiCA. Analize su polazna tačka "
    + "istraživanja, ne regulatorno mišljenje."));
  unutra.appendChild(zaglavlje);

  // ── Izbor analize: pitanja, ne nazivi modula ────────────────────────────
  const izbor = el("div", "v2-izbor");
  izbor.setAttribute("role", "group");
  izbor.setAttribute("aria-label", "Šta želite da proverite");
  const dugmad = new Map();
  for (const a of ANALIZE) {
    const d = el("button", "v2-izbor__stavka");
    d.type = "button";
    d.appendChild(el("span", "v2-izbor__pitanje", a.pitanje));
    d.appendChild(el("span", "v2-izbor__naziv", a.naziv));
    ciklus.slusaj(d, "click", () => postavi(a));
    dugmad.set(a.kljuc, d);
    izbor.appendChild(d);
  }
  unutra.appendChild(izbor);

  // ── Unos ────────────────────────────────────────────────────────────────
  const forma = el("form", "v2-forma v2-znanje__forma");
  forma.noValidate = true;
  const lab = el("label", "v2-polje-unos__labela", izabrana.labela);
  lab.htmlFor = "v2-uskl-tekst";
  const polje = el("textarea", "v2-polje-unos__kontrola v2-znanje__polje");
  polje.id = "v2-uskl-tekst";
  polje.name = "tekst";
  polje.rows = 5;
  polje.value = zaceto.tekst || "";
  const pomoc = el("p", "v2-polje-unos__pomoc", izabrana.pomoc);
  const radnje = el("div", "v2-forma__radnje");
  const dugme = el("button", "v2-dugme v2-dugme--glavno", "Pokreni analizu");
  dugme.type = "submit";
  radnje.appendChild(dugme);
  forma.append(lab, polje, pomoc, radnje);
  unutra.appendChild(forma);

  const sadrzaj = el("div", "v2-uskl");
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  sadrzaj.setAttribute("aria-labelledby", "v2-naslov-uskladjenost");
  unutra.appendChild(sadrzaj);

  // G7/G8 (Z017.2 execution queue #6) -- van ANALIZE kataloga, drugaciji
  // ugovor (adresa umesto teksta; PDF umesto JSON-a). V2 nepostojanje je
  // bio jedini razlog odsustva -- oba backend-a su vec radila.
  unutra.appendChild(blokWalletProvenance(ciklus));
  unutra.appendChild(blokSourceOfFundsDossier(ciklus));
  kontejner.appendChild(unutra);
  document.title = "Usklađenost · Vindex";

  let radi = false;

  function postavi(a) {
    izabrana = a;
    lab.textContent = a.labela;
    pomoc.textContent = a.pomoc;
    for (const [k, d] of dugmad) {
      const akt = k === a.kljuc;
      d.classList.toggle("v2-izbor__stavka--aktivna", akt);
      d.setAttribute("aria-pressed", akt ? "true" : "false");
    }
    prazno();
    polje.focus();
  }

  function prazno() {
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
      `Unesite tekst i pokrenite analizu. Najmanje ${izabrana.najmanje} znakova.`));
  }

  function ogradaElement(n) {
    const imaIzvore = Array.isArray(n.ograda.izvori) && n.ograda.izvori.length > 0;
    const o = el("div", "v2-ograda" + (imaIzvore ? " v2-ograda--sa-izvorima" : " v2-ograda--bez-izvora"));
    o.setAttribute("role", "alert");
    o.appendChild(el("p", "v2-ograda__naslov", n.ograda.naslov));
    o.appendChild(el("p", "v2-ograda__telo", n.ograda.telo));
    if (imaIzvore) {
      const ul = el("ul", "v2-ograda__izvori");
      for (const izv of n.ograda.izvori) {
        const li = el("li", "v2-mono");
        li.textContent = izv.izvor + (izv.odlomak ? " — " + izv.odlomak : "");
        ul.appendChild(li);
      }
      o.appendChild(ul);
    }
    return o;
  }

  function skorRed(naziv, vrednost) {
    const par = el("div", "v2-polja__par");
    par.appendChild(el("dt", "v2-polje", naziv));
    par.appendChild(el("dd", "v2-polja__v v2-mono", vrednost));
    return par;
  }

  /** Z017.2 -- oblik "skor" (aml/due-diligence). Backend nikad nije vracao
   * `rezultat` za ove -- ovo je stvaran prikaz strukturiranih podataka, ne
   * text-only fallback koji je ranije uvek pisao "odgovor nije stigao u
   * ocekivanom obliku". */
  function iscrtajSkor(sirov) {
    const p = uSkorIzvestaj(sirov, izabrana);
    const okvir = document.createDocumentFragment();
    okvir.appendChild(ogradaElement(uNalaz(sirov)));

    const s = el("section", "v2-uskl__nalaz");
    s.appendChild(el("h2", "v2-natkapa", izabrana.naziv));

    if (p.ukupno === null && !p.kategorije.length) {
      s.appendChild(el("p", "v2-celina__prazno",
        "Analiza je izvršena, ali odgovor nije stigao u očekivanom obliku. "
        + "Ovo nije nalaz da je sve usklađeno."));
      okvir.appendChild(s);
      sadrzaj.replaceChildren(okvir);
      return;
    }

    if (p.ukupno !== null) {
      const dl = el("dl", "v2-polja");
      dl.appendChild(skorRed("Ukupno", p.ukupno + "/100"));
      if (p.nivo) dl.appendChild(skorRed("Nivo", p.nivo));
      s.appendChild(dl);
    }

    if (p.kategorije.length) {
      const ul = el("ul", "v2-lista-tanka");
      for (const k of p.kategorije) {
        const li = el("li");
        const red = el("p", "v2-forma__red");
        red.appendChild(el("span", "", k.naziv));
        if (k.skor !== null) red.appendChild(el("span", "v2-mono", ` ${k.skor}/${k.max ?? "?"}`));
        if (k.status) red.appendChild(el("span", "v2-meta", " · " + k.status));
        li.appendChild(red);
        if (k.komentar) li.appendChild(el("p", "v2-meta", k.komentar));
        ul.appendChild(li);
      }
      s.appendChild(ul);
    }

    if (p.kriticniNedostaci.length) {
      s.appendChild(el("h3", "v2-natkapa", "Kritični nedostaci"));
      const ul = el("ul", "v2-lista-tanka");
      for (const n of p.kriticniNedostaci) ul.appendChild(el("li", "", n));
      s.appendChild(ul);
    }

    if (p.preporuke.length) {
      s.appendChild(el("h3", "v2-natkapa", "Preporuke"));
      const ul = el("ul", "v2-lista-tanka");
      for (const pr of p.preporuke) ul.appendChild(el("li", "", pr));
      s.appendChild(ul);
    }

    okvir.appendChild(s);
    sadrzaj.replaceChildren(okvir);
  }

  /** Z017.2 -- oblik "ugovor" (G5, F12 Smart Contract Legal Analyzer). */
  function iscrtajUgovor(sirov) {
    const a = uUgovorAnalizu(sirov);
    const okvir = document.createDocumentFragment();
    okvir.appendChild(ogradaElement(uNalaz(sirov)));

    const s = el("section", "v2-uskl__nalaz");
    s.appendChild(el("h2", "v2-natkapa", izabrana.naziv));

    const dl = el("dl", "v2-polja");
    if (a.nazivUgovora) dl.appendChild(skorRed("Ugovor", a.nazivUgovora));
    if (a.solidityVerzija) dl.appendChild(skorRed("Solidity", a.solidityVerzija));
    dl.appendChild(skorRed("Proxy obrazac", a.jeProxy ? "da" : "ne"));
    if (a.amlNivoRizika) dl.appendChild(skorRed("AML rizik", a.amlNivoRizika));
    s.appendChild(dl);
    if (a.amlObrazlozenje) s.appendChild(el("p", "v2-meta", a.amlObrazlozenje));

    if (a.rizici.length) {
      s.appendChild(el("h3", "v2-natkapa", "Pravni rizici"));
      const ul = el("ul", "v2-lista-tanka");
      for (const r of a.rizici) {
        const li = el("li");
        const red = el("p", "v2-forma__red");
        red.appendChild(el("span", "", r.rizik));
        if (r.ozbiljnost) red.appendChild(el("span", "v2-meta", " · " + r.ozbiljnost));
        li.appendChild(red);
        if (r.obrazlozenje) li.appendChild(el("p", "v2-meta", r.obrazlozenje));
        ul.appendChild(li);
      }
      s.appendChild(ul);
    } else {
      s.appendChild(el("p", "v2-celina__prazno", "Nisu identifikovani konkretni pravni rizici."));
    }

    if (a.klasifikacijaTokena.length) {
      s.appendChild(el("h3", "v2-natkapa", "Klasifikacija tokena"));
      const ul = el("ul", "v2-lista-tanka");
      for (const k of a.klasifikacijaTokena) {
        const li = el("li");
        li.appendChild(el("span", "", k.kategorija));
        if (k.status) li.appendChild(el("span", "v2-meta", " · " + k.status));
        ul.appendChild(li);
      }
      s.appendChild(ul);
    }

    okvir.appendChild(s);
    sadrzaj.replaceChildren(okvir);
  }

  function iscrtaj(n) {
    const okvir = document.createDocumentFragment();
    okvir.appendChild(ogradaElement(n));

    const s = el("section", "v2-uskl__nalaz");
    s.appendChild(el("h2", "v2-natkapa", izabrana.naziv));
    if (n.prazan) {
      // Prazan rezultat NIJE „nema nalaza" — to je odgovor koji nismo razumeli.
      s.appendChild(el("p", "v2-celina__prazno",
        "Analiza je izvršena, ali odgovor nije stigao u očekivanom obliku. "
        + "Ovo nije nalaz da je sve usklađeno."));
    } else {
      s.appendChild(uPasuse(n.telo, "v2-znanje__pasus"));
    }
    okvir.appendChild(s);
    sadrzaj.replaceChildren(okvir);
  }

  ciklus.slusaj(forma, "submit", async (e) => {
    e.preventDefault();
    if (radi) return;
    const t = polje.value.trim();
    if (t.length < izabrana.najmanje) {
      // Serverska granica se postuje na klijentu: 422 koji je korisnik mogao
      // da izbegne nije informacija, nego prepreka.
      sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
        `Potrebno je najmanje ${izabrana.najmanje} znakova; uneto je ${t.length}.`));
      polje.focus();
      return;
    }

    radi = true;
    dugme.disabled = true;
    dugme.textContent = "Analiza u toku…";
    sadrzaj.setAttribute("aria-busy", "true");
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno", "Analiza u toku. Ovo može potrajati."));

    const prekidac = ciklus.prekidac();
    let sirov;
    try {
      // Z017.2 OTKRIVENI KVAR: "ugovor" ocekuje solidity_source, ne tekst --
      // svaki pokusaj je ranije vracao 422 pre nego sto bi handler bio pozvan.
      sirov = await posalji(izabrana.putanja, {
        telo: { [izabrana.poljeTela || "tekst"]: t }, signal: prekidac.signal,
      });
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      radi = false;
      dugme.disabled = false;
      dugme.textContent = "Pokreni analizu";
      sadrzaj.setAttribute("aria-busy", "false");
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      const d = el("div", "v2-poruka v2-poruka--greska");
      d.appendChild(el("p", "v2-poruka__naslov", "Analiza nije izvršena"));
      d.appendChild(el("p", "v2-poruka__telo",
        porukaZaKorisnika(err) + " Izostanak nalaza NIJE nalaz da je sve usklađeno."));
      sadrzaj.replaceChildren(d);
      return;
    }
    if (ciklus.ugasen) return;

    radi = false;
    dugme.disabled = false;
    dugme.textContent = "Pokreni analizu";
    sadrzaj.setAttribute("aria-busy", "false");
    if (izabrana.oblik === "skor") iscrtajSkor(sirov);
    else if (izabrana.oblik === "ugovor") iscrtajUgovor(sirov);
    else iscrtaj(uNalaz(sirov));
    sadrzaj.focus();
  });

  ciklus.kontekst = () => ({ analiza: izabrana.kljuc, tekst: polje.value });

  postavi(izabrana);
  return ciklus;
}
