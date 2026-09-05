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
  kontejner.appendChild(unutra);

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

  function iscrtaj(n) {
    const okvir = document.createDocumentFragment();

    // Ograda IZNAD nalaza. Stalna, ne uslovna.
    const o = el("div", "v2-ograda v2-ograda--bez-izvora");
    o.setAttribute("role", "alert");
    o.appendChild(el("p", "v2-ograda__naslov", n.ograda.naslov));
    o.appendChild(el("p", "v2-ograda__telo", n.ograda.telo));
    okvir.appendChild(o);

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
      sirov = await posalji(izabrana.putanja, { telo: { tekst: t }, signal: prekidac.signal });
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
    iscrtaj(uNalaz(sirov));
    sadrzaj.focus();
  });

  ciklus.kontekst = () => ({ analiza: izabrana.kljuc, tekst: polje.value });

  postavi(izabrana);
  return ciklus;
}
