/* Vindex V2 — Predmeti, pogled.
 *
 * Prvi sadrzaj ekrana je REGISTAR. Nema pozdravne poruke, nema slogana, nema
 * statisticke table. Advokat otvara Predmete da nadje predmet.
 *
 * SVESNO IZOSTAVLJENO U GATE V1 (Z015 §24, §25):
 *   - otvaranje predmeta: Dosije jos ne postoji, pa red NIJE klikabilan.
 *     Kontrola koja izgleda kao akcija a nema ishod je gora od njenog izostanka.
 *   - „Nov predmet": tok kreiranja nije autorizovan u ovom talasu, pa dugmeta nema.
 * Oba su zabelezena kao odlozeni funkcionalni elementi, ne kao previd.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { ucitajStranu, PO_STRANI } from "./api.js";
import { napraviStanje, novaGeneracija, jeAktuelna, STANJE } from "./state.js";
import { idiNa, putanjaZa } from "../../platform/router.js";

const DEBOUNCE_MS = 300;

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

function nevidljivo(tekst) {
  return el("span", "v2-nevidljivo", tekst);
}

/* ── Iscrtavanje ────────────────────────────────────────────────────────── */

function zaglavljeKolona() {
  const z = el("div", "v2-reg__zaglavlje");
  z.setAttribute("aria-hidden", "true");   // svaki red nosi sopstvene labele
  for (const naziv of ["Naziv predmeta", "Broj", "Vrsta", "Stanje", "Izmenjeno"]) {
    z.appendChild(el("span", "v2-polje", naziv));
  }
  return z;
}

function red(zapis) {
  const li = el("li", "v2-reg__red");

  // Red vodi u DOSIJE tog predmeta. Prava <a href> veza: srednji klik i
  // „otvori u novoj kartici" rade nativno, citac ekrana dobija ime, a
  // tastatura radi bez ijedne linije dodatnog koda.
  const veza = el("a", "v2-reg__veza", zapis.naziv);
  veza.href = putanjaZa("predmet", zapis.id);
  veza.addEventListener("click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("predmet", zapis.id);
  });
  const naziv = el("span", "v2-reg__naziv");
  naziv.appendChild(veza);
  li.appendChild(naziv);

  const meta = el("span", "v2-reg__meta");

  const broj = el("span", "v2-reg__broj-predmeta");
  broj.appendChild(nevidljivo("Broj predmeta: "));
  broj.appendChild(document.createTextNode(zapis.broj || "—"));
  meta.appendChild(broj);

  const vrsta = el("span", "v2-reg__vrsta");
  vrsta.appendChild(nevidljivo("Vrsta: "));
  vrsta.appendChild(document.createTextNode(zapis.vrsta || "—"));
  meta.appendChild(vrsta);

  const stanje = el("span", "v2-reg__stanje");
  stanje.dataset.stanje = zapis.stanjeKlasa;
  stanje.appendChild(nevidljivo("Stanje: "));
  stanje.appendChild(document.createTextNode(zapis.stanje));
  meta.appendChild(stanje);

  const dat = el("span", "v2-reg__datum");
  dat.appendChild(nevidljivo("Izmenjeno: "));
  dat.appendChild(document.createTextNode(zapis.izmenjeno));
  meta.appendChild(dat);

  li.appendChild(meta);
  return li;
}

function skelet(koliko) {
  const okvir = el("div", "v2-skelet");
  for (let i = 0; i < koliko; i++) {
    const r = el("div", "v2-skelet__red");
    r.appendChild(el("span", "v2-skelet__traka v2-skelet__traka--siroka"));
    r.appendChild(el("span", "v2-skelet__traka v2-skelet__traka--uska"));
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

/* ── Montiranje ─────────────────────────────────────────────────────────── */

export function montirajPredmete(kontejner, kontekst) {
  const ciklus = napraviCiklus();
  const s = napraviStanje(PO_STRANI);

  // Kontekst prezivljava odlazak u drugi prostor i povratak: korisnik koji je
  // trazio „kalibracija" na trecoj strani zatice tacno to, a ne prazan registar.
  // Bez ovoga bi svaki prelazak na Danas i natrag ponistio njegov rad.
  if (kontekst) {
    if (typeof kontekst.upit === "string") s.upit = kontekst.upit;
    if (Number.isFinite(kontekst.offset)) s.offset = kontekst.offset;
    if (Number.isFinite(kontekst.limit) && kontekst.limit > 0) s.limit = kontekst.limit;
  }

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--registar");

  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Predmeti");
  h1.id = "v2-naslov-predmeti";
  zaglavlje.appendChild(h1);
  const brojac = el("p", "v2-reg__broj");
  brojac.id = "v2-brojac";
  zaglavlje.appendChild(brojac);
  unutra.appendChild(zaglavlje);

  const sekcija = el("section", "v2-registar");
  sekcija.setAttribute("aria-labelledby", "v2-naslov-predmeti");

  // ── Pretraga (registarska, ne globalna) ──
  const alat = el("div", "v2-reg__alat");
  const forma = el("form", "v2-trazi");
  forma.setAttribute("role", "search");
  const labela = el("label", "v2-nevidljivo", "Pretraži predmete po nazivu");
  labela.htmlFor = "v2-trazi-polje";
  const polje = el("input", "v2-trazi__polje");
  polje.id = "v2-trazi-polje";
  polje.type = "search";
  polje.name = "q";
  polje.autocomplete = "off";
  polje.placeholder = "Pretraži predmete";
  polje.value = s.upit;
  const ocisti = el("button", "v2-trazi__ocisti", "Poništi");
  ocisti.type = "button";
  ocisti.hidden = true;
  forma.append(labela, polje, ocisti);
  alat.appendChild(forma);
  sekcija.appendChild(alat);

  // ── Sadrzaj ──
  const sadrzaj = el("div", "v2-reg__sadrzaj");
  sadrzaj.id = "v2-reg-sadrzaj";
  sadrzaj.tabIndex = -1;                       // cilj fokusa posle promene strane
  sadrzaj.setAttribute("aria-live", "polite");
  sekcija.appendChild(sadrzaj);

  // ── Stranicenje ──
  const str = el("nav", "v2-str");
  str.setAttribute("aria-label", "Stranice registra");
  const prethodna = el("button", "v2-dugme", "Prethodna");
  prethodna.type = "button";
  const sledeca = el("button", "v2-dugme", "Sledeća");
  sledeca.type = "button";
  const polozaj = el("p", "v2-str__polozaj");
  str.append(prethodna, sledeca, polozaj);
  sekcija.appendChild(str);

  unutra.appendChild(sekcija);
  kontejner.appendChild(unutra);

  /* ── Iscrtavanje po stanju ─────────────────────────────────────────── */

  function iscrtaj() {
    sadrzaj.setAttribute("aria-busy", s.status === STANJE.UCITAVANJE ? "true" : "false");
    ocisti.hidden = s.upit.trim() === "";

    if (s.status === STANJE.UCITAVANJE) {
      sadrzaj.replaceChildren(skelet(8));
      // Brojac i stranicenje se ne brisu ako vec postoji strana: brisanje bi
      // pomerilo raspored pri svakoj promeni strane, a korisnik bi izgubio
      // mesto na kome je bio. Dugmad su onemogucena dok traje ucitavanje.
      if (s.strana) {
        str.hidden = false;
        prethodna.disabled = true;
        sledeca.disabled = true;
      } else {
        brojac.textContent = "";
        str.hidden = true;
      }
      return;
    }

    if (s.status === STANJE.GRESKA) {
      const naslov = s.greska && s.greska.vrsta === VRSTA.MREZA
        ? "Nema veze sa serverom"
        : "Registar trenutno nije dostupan";
      sadrzaj.replaceChildren(poruka({
        naslov,
        telo: porukaZaKorisnika(s.greska),
        greska: true,
      }));
      brojac.textContent = "";
      str.hidden = true;
      return;
    }

    if (s.status === STANJE.PRAZNO) {
      const imaUpit = s.upit.trim() !== "";
      sadrzaj.replaceChildren(poruka({
        naslov: imaUpit ? "Nema predmeta za ovu pretragu." : "Još nema predmeta.",
        telo: imaUpit ? "Proverite unos ili poništite pretragu." : "",
      }));
      brojac.textContent = "0 predmeta";
      str.hidden = true;
      return;
    }

    const p = s.strana;
    const lista = el("ul", "v2-reg__lista");
    for (const z of p.zapisi) lista.appendChild(red(z));

    const okvir = document.createDocumentFragment();
    okvir.appendChild(zaglavljeKolona());
    okvir.appendChild(lista);
    sadrzaj.replaceChildren(okvir);

    brojac.textContent = p.ukupno === 1 ? "1 predmet" : `${p.ukupno} predmeta`;

    const viseStrana = p.imaPrethodnu || p.imaSledecu;
    str.hidden = !viseStrana;
    prethodna.disabled = !p.imaPrethodnu;
    sledeca.disabled = !p.imaSledecu;
    polozaj.textContent = `${p.prvi}–${p.poslednji} od ${p.ukupno}`;
  }

  /* ── Ucitavanje ────────────────────────────────────────────────────── */

  async function ucitaj({ pomeriFokus = false } = {}) {
    const { broj, signal } = novaGeneracija(s);
    s.status = STANJE.UCITAVANJE;
    s.greska = null;
    iscrtaj();

    try {
      const strana = await ucitajStranu({ upitTeksta: s.upit, offset: s.offset, limit: s.limit, signal });
      if (!jeAktuelna(s, broj) || ciklus.ugasen) return;   // zastareo odgovor — cutke odbaciti
      // Server je vlasnik ugovora o strani: `/api/predmeti` limit skracuje na
      // [1,500]. Ako klijent zadrzi svoj trazeni broj, sledeci offset se racuna
      // po velicini strane koja nikad nije stigla — i stranicenje preskoci
      // zapise. Usvaja se ono sto je server stvarno vratio.
      if (Number.isFinite(strana.limit) && strana.limit > 0) s.limit = strana.limit;
      if (Number.isFinite(strana.offset)) s.offset = strana.offset;
      s.strana = strana;
      s.status = strana.zapisi.length === 0 ? STANJE.PRAZNO : STANJE.SPREMNO;
      iscrtaj();
      if (pomeriFokus) sadrzaj.focus({ preventScroll: false });
    } catch (e) {
      if (jePrekid(e) || ciklus.ugasen) return;
      if (!jeAktuelna(s, broj)) return;
      // Istekla sesija nije greska ekrana nego ceo tok od pocetka.
      if (e && e.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      s.greska = e;
      s.status = STANJE.GRESKA;
      iscrtaj();
    }
  }

  /* ── Dogadjaji ─────────────────────────────────────────────────────── */

  let tajmer = 0;
  function zakaziPretragu(vrednost) {
    window.clearTimeout(tajmer);
    tajmer = window.setTimeout(() => {
      if (vrednost.trim() === s.upit.trim()) return;   // isti upit — bez novog poziva
      s.upit = vrednost;
      s.offset = 0;                                     // nova pretraga pocinje od prve strane
      ucitaj();
    }, DEBOUNCE_MS);
    ciklus.dodaj(() => window.clearTimeout(tajmer));
  }

  ciklus.slusaj(polje, "input", (e) => zakaziPretragu(e.target.value));

  ciklus.slusaj(forma, "submit", (e) => {
    e.preventDefault();                                  // Enter ne sme da ucita dokument ponovo
    window.clearTimeout(tajmer);
    if (polje.value.trim() === s.upit.trim()) return;
    s.upit = polje.value;
    s.offset = 0;
    ucitaj();
  });

  ciklus.slusaj(ocisti, "click", () => {
    window.clearTimeout(tajmer);
    polje.value = "";
    polje.focus();
    if (s.upit === "") return;
    s.upit = "";
    s.offset = 0;
    ucitaj();
  });

  ciklus.slusaj(prethodna, "click", () => {
    if (!s.strana || !s.strana.imaPrethodnu) return;
    s.offset = Math.max(0, s.offset - s.limit);
    ucitaj({ pomeriFokus: true });
  });

  ciklus.slusaj(sledeca, "click", () => {
    if (!s.strana || !s.strana.imaSledecu) return;
    s.offset = s.offset + s.limit;
    ucitaj({ pomeriFokus: true });
  });

  ciklus.dodaj(() => { if (s.prekidac) s.prekidac.abort(); });

  // Ruter ovo cita pri napustanju ekrana i vraca pri sledecem montiranju.
  ciklus.kontekst = () => ({ upit: s.upit, offset: s.offset, limit: s.limit });

  ucitaj();
  return ciklus;
}
