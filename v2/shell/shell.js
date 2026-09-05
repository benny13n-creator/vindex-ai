/* Vindex V2 — globalna ljuska.
 *
 * Ljuska nosi JEDINI mentalni model koji korisnik mora da nauci: cetiri mesta.
 * Ne modul, ne submodul, ne tab, ne panel.
 *
 * PRAVILA KOJA OVAJ FAJL SPROVODI
 *
 *   1. Prostor koji nije izgradjen ILI koji nalog nema — NE POSTOJI u
 *      navigaciji. Nema onemogucene stavke i nema „uskoro". Onemoguceni
 *      meni je obecanje koje proizvod ne moze da odrzi, a korisnika tera da
 *      uci mapu proizvoda umesto da radi.
 *
 *   2. Nema bocne trake kao primarne globalne navigacije.
 *
 *   3. Nema polja za globalnu pretragu dok globalna pretraga ne postoji.
 *      Vidljivo polje koje ne pretrazuje je gore od njegovog izostanka.
 *
 *   4. Aktivni prostor se oznacava linijom i `aria-current`, ne ispunom.
 *
 * Navigacija su prave `<a href>` veze: srednji klik, „otvori u novoj kartici"
 * i citac ekrana rade bez ijedne linije dodatnog koda. Ruter presrece obican
 * klik i menja prikaz bez ponovnog ucitavanja dokumenta.
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

export function montirajLjusku(koren, { izgradjeni, sme }) {
  koren.replaceChildren();
  koren.dataset.faza = "aplikacija";

  const prostori = vidljiviProstori(izgradjeni, sme);

  const app = el("div", "v2-app");

  // ── Crna scena: puna sirina, sadrzaj u meri ─────────────────────────────
  const ljuska = el("header", "v2-scena v2-scena--crna v2-ljuska");
  const red = el("div", "v2-scena__unutra v2-ljuska__red");

  const znak = el("a", "v2-znak", "Vindex");
  znak.href = prostori.length ? prostori[0].putanja : PRIJAVA;
  znak.setAttribute("aria-label", "Vindex — početna");

  const nav = el("nav", "v2-nav");
  nav.setAttribute("aria-label", "Glavna navigacija");
  const ul = el("ul", "v2-nav__lista");
  const veze = new Map();
  for (const p of prostori) {
    const li = el("li");
    const a = el("a", "v2-nav__veza", p.naziv);
    a.href = p.putanja;
    a.dataset.prostor = p.kljuc;
    li.appendChild(a);
    ul.appendChild(li);
    veze.set(p.kljuc, a);
  }
  nav.appendChild(ul);

  const nalog = el("div", "v2-ljuska__nalog");
  const k = korisnik();
  if (k && k.email) {
    const email = el("span", "v2-ljuska__email", k.email);
    email.title = k.email;
    nalog.appendChild(email);
  }
  const veza = el("a", "v2-tekst-akcija", "Nalog");
  veza.href = PRIJAVA;
  nalog.appendChild(veza);

  red.append(znak, nav, nalog);
  ljuska.appendChild(red);

  // ── Papir scena: puna sirina, ekran se montira unutra ───────────────────
  const glavni = el("main", "v2-scena v2-scena--papir v2-glavni");
  glavni.id = "v2-glavni";

  app.append(ljuska, glavni);
  koren.appendChild(app);

  // Obican klik ostaje u aplikaciji; Ctrl/Cmd/srednji klik prepustamo
  // pretrazivacu, jer korisnik tada namerno trazi novu karticu.
  nav.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-prostor]");
    if (!a) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNaPutanju(a.getAttribute("href"));
  });
  znak.addEventListener("click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNaPutanju(znak.getAttribute("href"));
  });

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
