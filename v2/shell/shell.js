/* Vindex V2 — globalna ljuska.
 *
 * Ljuska nosi jedini mentalni model koji korisnik mora da nauci: cetiri mesta.
 * Ne modul, ne submodul, ne tab, ne panel.
 *
 * ZASTO JE PREPRAVLJENA
 * Prva verzija je bila traka od 60px sa dve reci i delovala je kao zaglavlje
 * sajta, ne kao radno okruzenje. Sada nosi punu visinu reda, vertikalnu podelu
 * izmedju znaka i navigacije, aktivnu liniju po celoj visini, i desnu zonu sa
 * pretragom i nalogom. Bez bocne trake, bez ispune, bez hero-a.
 *
 * PRAVILA KOJA SPROVODI
 *   1. Prostor koji nije izgradjen ILI koji nalog nema — NE POSTOJI. Nema
 *      onemogucene stavke i nema „uskoro".
 *   2. Navigacija su prave <a href> veze: srednji klik i „otvori u novoj
 *      kartici" rade nativno; ruter presrece samo obican klik.
 *   3. Pretraga je akcelerator sa sopstvenom rutom, ne modal i ne zamena za
 *      navigaciju.
 */

import { korisnik, PRIJAVA } from "../platform/auth.js";
import { vidljiviProstori } from "../domain/spaces.js";
import { idiNaPutanju, naPromenu } from "../platform/router.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

/** Obican klik ostaje u aplikaciji; modifikatori se prepustaju pretrazivacu. */
function unutrasnjaVeza(a) {
  a.addEventListener("click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNaPutanju(a.getAttribute("href"));
  });
}

export function montirajLjusku(koren, { izgradjeni, sme, pretraga = true }) {
  koren.replaceChildren();
  koren.dataset.faza = "aplikacija";

  const prostori = vidljiviProstori(izgradjeni, sme);
  const app = el("div", "v2-app");

  const ljuska = el("header", "v2-scena v2-scena--crna v2-ljuska");
  const red = el("div", "v2-scena__unutra v2-ljuska__red");

  // ── Znak ────────────────────────────────────────────────────────────────
  const znakZona = el("div", "v2-ljuska__znak-zona");
  const znak = el("a", "v2-znak", "Vindex");
  znak.href = prostori.length ? prostori[0].putanja : PRIJAVA;
  znak.setAttribute("aria-label", "Vindex — početna");
  unutrasnjaVeza(znak);
  znakZona.appendChild(znak);

  // ── Prostori ────────────────────────────────────────────────────────────
  const nav = el("nav", "v2-nav");
  nav.setAttribute("aria-label", "Glavna navigacija");
  const ul = el("ul", "v2-nav__lista");
  const veze = new Map();
  for (const p of prostori) {
    const li = el("li");
    const a = el("a", "v2-nav__veza", p.naziv);
    a.href = p.putanja;
    a.dataset.prostor = p.kljuc;
    unutrasnjaVeza(a);
    li.appendChild(a);
    ul.appendChild(li);
    veze.set(p.kljuc, a);
  }
  nav.appendChild(ul);

  // ── Desna zona: pretraga + nalog ────────────────────────────────────────
  const desno = el("div", "v2-ljuska__desno");

  if (pretraga) {
    const trazi = el("a", "v2-ljuska__pretraga");
    trazi.href = "/app-v2/pretraga";
    trazi.innerHTML = "";
    trazi.appendChild(el("span", "v2-ljuska__pretraga-tekst", "Pretraži predmete, klijente, spise"));
    const precica = el("kbd", "v2-ljuska__precica", "Ctrl K");
    precica.setAttribute("aria-hidden", "true");   // precica je ubrzanje, ne uputstvo
    trazi.appendChild(precica);
    unutrasnjaVeza(trazi);
    desno.appendChild(trazi);
  }

  const nalog = el("div", "v2-ljuska__nalog");
  const k = korisnik();
  if (k && k.email) {
    const email = el("span", "v2-ljuska__email", k.email);
    email.title = k.email;
    nalog.appendChild(email);
  }
  const izlaz = el("a", "v2-tekst-akcija", "Nalog");
  izlaz.href = PRIJAVA;
  nalog.appendChild(izlaz);
  desno.appendChild(nalog);

  red.append(znakZona, nav, desno);
  ljuska.appendChild(red);

  const glavni = el("main", "v2-scena v2-scena--papir v2-glavni");
  glavni.id = "v2-glavni";

  app.append(ljuska, glavni);
  koren.appendChild(app);

  // Ctrl/Cmd+K — ubrzanje za onoga ko zna; nikad jedini put do pretrage.
  const naTastaturu = (e) => {
    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      idiNaPutanju("/app-v2/pretraga");
    }
  };
  if (pretraga) document.addEventListener("keydown", naTastaturu);

  naPromenu((kljuc) => {
    for (const [k2, a] of veze) {
      const aktivan = k2 === kljuc;
      a.classList.toggle("v2-nav__veza--aktivan", aktivan);
      if (aktivan) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    }
    const p = prostori.find(x => x.kljuc === kljuc);
    document.title = p ? `${p.naziv} · Vindex` : "Vindex";
  });

  return glavni;
}
