/* Vindex V2 — globalna pretraga.
 *
 * Pretraga je UBRZANJE, ne zamena za navigaciju. Zato ima sopstvenu rutu
 * (`/app-v2/pretraga`), a ne modal: rezultat se moze podeliti, `back` radi,
 * i korisnik se posle otvaranja rezultata vraca tamo gde je bio.
 *
 * PRIKAZUJU SE SAMO KATEGORIJE KOJE BACKEND STVARNO PRETRAZUJE.
 * `/api/search` vraca `predmeti`, `klijenti`, `dokumenti`, `hronologija`,
 * `beleske`, `zadaci`, `billing`. Propisi i sudska praksa se NE prikazuju
 * ovde — njih ovaj endpoint ne pretrazuje, a lazna kategorija je gore od
 * njenog izostanka.
 *
 * Klik vodi na TACAN objekat gde je dokaziv (predmet -> Dosije), a gde nije —
 * na najuzi dokaziv kontekst. Nikad na lazan deep link.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { dohvati } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { idiNa, putanjaZa } from "../../platform/router.js";

const DEBOUNCE_MS = 300;
const NAJMANJE = 2;

/** Redosled i poslovna imena kategorija koje endpoint stvarno vraca. */
const KATEGORIJE = [
  { kljuc: "predmeti", naziv: "Predmeti", otvara: "predmet" },
  { kljuc: "klijenti", naziv: "Klijenti" },
  { kljuc: "dokumenti", naziv: "Spisi" },
  { kljuc: "hronologija", naziv: "Hronologija" },
  { kljuc: "beleske", naziv: "Beleške" },
  { kljuc: "zadaci", naziv: "Zadaci" },
  { kljuc: "billing", naziv: "Naplata" },
];

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

function upitIzURL() {
  try { return new URLSearchParams(window.location.search).get("q") || ""; }
  catch (e) { return ""; }
}

export function montirajPretragu(kontejner, kontekst) {
  const ciklus = napraviCiklus();
  let generacija = 0;
  let upit = (kontekst && typeof kontekst.upit === "string") ? kontekst.upit : upitIzURL();

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--registar");

  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Pretraga");
  h1.id = "v2-naslov-pretraga";
  zaglavlje.appendChild(h1);
  unutra.appendChild(zaglavlje);

  const forma = el("form", "v2-trazi v2-trazi--veliko");
  forma.setAttribute("role", "search");
  const labela = el("label", "v2-nevidljivo", "Pretraži predmete, klijente, spise");
  labela.htmlFor = "v2-pretraga-polje";
  const polje = el("input", "v2-trazi__polje");
  polje.id = "v2-pretraga-polje";
  polje.type = "search";
  polje.name = "q";
  polje.autocomplete = "off";
  polje.placeholder = "Pretraži predmete, klijente, spise";
  polje.value = upit;
  const ocisti = el("button", "v2-trazi__ocisti", "Poništi");
  ocisti.type = "button";
  ocisti.hidden = upit.trim() === "";
  forma.append(labela, polje, ocisti);
  unutra.appendChild(forma);

  const sadrzaj = el("div", "v2-pretraga");
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  sadrzaj.setAttribute("aria-labelledby", "v2-naslov-pretraga");
  unutra.appendChild(sadrzaj);
  kontejner.appendChild(unutra);

  polje.focus();

  function uputstvo() {
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
      `Unesite najmanje ${NAJMANJE} znaka. Pretražuju se predmeti, klijenti, spisi, hronologija, beleške, zadaci i naplata.`));
  }

  function stavka(kat, x) {
    const naziv = String((x && (x.naziv || x.opis || x.tekst)) || "").trim() || "Bez naziva";
    const pregled = String((x && (x.preview || x.meta)) || "").trim();

    if (kat.otvara && x && x.id) {
      const li = el("li", "v2-rez__red");
      const a = el("a", "v2-rez__veza", naziv);
      a.href = putanjaZa(kat.otvara, x.id);
      ciklus.slusaj(a, "click", (e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        e.preventDefault();
        idiNa(kat.otvara, x.id);
      });
      li.appendChild(a);
      if (pregled) li.appendChild(el("span", "v2-rez__pregled", pregled));
      return li;
    }
    // Bez dokazivog odredista rezultat se prikazuje, ali NE glumi vezu.
    const li = el("li", "v2-rez__red v2-rez__red--bez-veze");
    li.appendChild(el("span", "v2-rez__naziv", naziv));
    if (pregled) li.appendChild(el("span", "v2-rez__pregled", pregled));
    return li;
  }

  async function trazi() {
    const q = upit.trim();
    ocisti.hidden = q === "";
    if (q.length < NAJMANJE) { uputstvo(); return; }

    const moja = ++generacija;
    const prekidac = ciklus.prekidac();
    sadrzaj.setAttribute("aria-busy", "true");
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno", "Pretraga…"));

    let d;
    try {
      d = await dohvati("/api/search", { upit: { q }, signal: prekidac.signal });
    } catch (e) {
      if (jePrekid(e) || ciklus.ugasen || moja !== generacija) return;
      if (e && e.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      const p = el("div", "v2-poruka v2-poruka--greska");
      p.appendChild(el("p", "v2-poruka__naslov", "Pretraga trenutno nije dostupna"));
      p.appendChild(el("p", "v2-poruka__telo", porukaZaKorisnika(e) + " Ovo ne znači da rezultata nema."));
      sadrzaj.replaceChildren(p);
      sadrzaj.setAttribute("aria-busy", "false");
      return;
    }
    if (ciklus.ugasen || moja !== generacija) return;
    sadrzaj.setAttribute("aria-busy", "false");

    const okvir = document.createDocumentFragment();
    let ukupno = 0;
    for (const kat of KATEGORIJE) {
      const niz = Array.isArray(d[kat.kljuc]) ? d[kat.kljuc] : [];
      if (!niz.length) continue;
      ukupno += niz.length;
      const sek = el("section", "v2-rez");
      const h = el("h2", "v2-natkapa v2-rez__naslov", `${kat.naziv} · ${niz.length}`);
      sek.appendChild(h);
      const ul = el("ul", "v2-rez__lista");
      for (const x of niz) ul.appendChild(stavka(kat, x));
      sek.appendChild(ul);
      okvir.appendChild(sek);
    }
    if (!ukupno) {
      sadrzaj.replaceChildren(el("p", "v2-celina__prazno", `Nema rezultata za „${q}".`));
      return;
    }
    sadrzaj.replaceChildren(okvir);
  }

  let tajmer = 0;
  function zakazi(v) {
    window.clearTimeout(tajmer);
    tajmer = window.setTimeout(() => {
      if (v.trim() === upit.trim()) return;
      upit = v;
      try {
        const u = new URL(window.location.href);
        if (upit.trim()) u.searchParams.set("q", upit.trim());
        else u.searchParams.delete("q");
        window.history.replaceState({}, "", u.pathname + u.search);
      } catch (e) { /* URL nije kriticna funkcija pretrage */ }
      trazi();
    }, DEBOUNCE_MS);
    ciklus.dodaj(() => window.clearTimeout(tajmer));
  }

  ciklus.slusaj(polje, "input", (e) => zakazi(e.target.value));
  ciklus.slusaj(forma, "submit", (e) => {
    e.preventDefault();
    window.clearTimeout(tajmer);
    if (polje.value.trim() === upit.trim()) return;
    upit = polje.value;
    trazi();
  });
  ciklus.slusaj(ocisti, "click", () => {
    window.clearTimeout(tajmer);
    polje.value = "";
    polje.focus();
    if (!upit) return;
    upit = "";
    uputstvo();
  });

  ciklus.kontekst = () => ({ upit });

  if (upit.trim().length >= NAJMANJE) trazi(); else uputstvo();
  return ciklus;
}
