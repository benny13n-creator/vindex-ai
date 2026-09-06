/* Vindex V2 — NAŠI STAVOVI (`/app-v2/znanje/stavovi`) (D9).
 *
 * Treće pitanje u prostoru ZNANJE: ne "šta kaže propis" ili "šta je sud
 * presudio", nego "šta je NAŠA firma već zaključila o ovome". Interni
 * korpus, po firmi (backend namespace-uje po user_id).
 *
 * PRETRAGA_NEUSPESNA (Z017.2): pad pretrage se NIKAD ne prikazuje kao
 * "nemamo stav o ovome" — to bi bila tvrdnja o SADRŽAJU firminog znanja
 * izvedena iz pretrage koja se nije ni izvršila.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { dohvati, posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { idiNa, putanjaZa } from "../../platform/router.js";
import { ostavi } from "../../platform/obavestenje.js";
import { uPretragu, nedostaciStava } from "../../domain/interniStavovi.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

export function montirajStavove(kontejner, kontekst) {
  const ciklus = napraviCiklus();
  const zaceto = kontekst || {};

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--predmet");

  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Naši stavovi");
  h1.id = "v2-naslov-stavovi";
  zaglavlje.appendChild(h1);
  zaglavlje.appendChild(el("p", "v2-podnaslov",
    "Interni pravni stavovi firme — pretražuje se ono što je vaša kancelarija "
    + "već zaključila, ne opšte znanje modela ni javna sudska praksa."));
  unutra.appendChild(zaglavlje);

  const izbor = el("nav", "v2-prekidac");
  izbor.setAttribute("aria-label", "Šta pitate");
  const kaPropisima = el("a", "v2-prekidac__stavka", "Propisi");
  kaPropisima.href = putanjaZa("znanje");
  ciklus.slusaj(kaPropisima, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("znanje");
  });
  const kaPraksi = el("a", "v2-prekidac__stavka", "Praksa");
  kaPraksi.href = putanjaZa("znanje", "praksa");
  ciklus.slusaj(kaPraksi, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("znanje", "praksa");
  });
  const ovde = el("span", "v2-prekidac__stavka v2-prekidac__stavka--aktivna", "Naši stavovi");
  ovde.setAttribute("aria-current", "page");
  izbor.append(kaPropisima, kaPraksi, ovde);
  unutra.appendChild(izbor);

  // ── Pretraga ──
  const forma = el("form", "v2-forma v2-znanje__forma");
  forma.noValidate = true;
  const labU = el("label", "v2-polje-unos__labela", "Pitanje");
  labU.htmlFor = "v2-stavovi-upit";
  const upit = el("input", "v2-polje-unos__kontrola");
  upit.id = "v2-stavovi-upit";
  upit.type = "search";
  upit.placeholder = "Npr. raskid ugovora zbog promenjenih okolnosti";
  upit.value = zaceto.upit || "";
  const radnje = el("div", "v2-forma__radnje");
  const trazi = el("button", "v2-dugme v2-dugme--glavno", "Pretraži naše stavove");
  trazi.type = "submit";
  radnje.appendChild(trazi);
  forma.append(labU, upit, radnje);
  unutra.appendChild(forma);

  const sadrzaj = el("div", "v2-znanje");
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  sadrzaj.setAttribute("aria-labelledby", "v2-naslov-stavovi");
  unutra.appendChild(sadrzaj);

  // ── Dodavanje novog stava ──
  const dodajForma = el("form", "v2-forma v2-podblok");
  dodajForma.noValidate = true;
  dodajForma.appendChild(el("h3", "v2-natkapa", "Dodaj novi stav"));
  const naslovPolje = el("input");
  naslovPolje.placeholder = "Naslov";
  naslovPolje.setAttribute("aria-label", "Naslov stava");
  const tekstPolje = el("textarea");
  tekstPolje.placeholder = "Tekst stava (najmanje 30 znakova).";
  tekstPolje.rows = 4;
  const dodajDugme = el("button", "v2-dugme", "Sačuvaj stav");
  dodajDugme.type = "submit";
  const dodajPoruka = el("div", "v2-forma__poruka");
  dodajPoruka.setAttribute("role", "alert");
  dodajPoruka.hidden = true;
  dodajForma.append(naslovPolje, tekstPolje, dodajDugme, dodajPoruka);
  unutra.appendChild(dodajForma);

  kontejner.appendChild(unutra);
  document.title = "Naši stavovi · Vindex";
  upit.focus();

  function prazno() {
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
      "Unesite pitanje da pretražite interne stavove firme."));
  }

  function iscrtaj(r) {
    if (r.pretragaNeuspesna) {
      const p = el("div", "v2-poruka v2-poruka--greska");
      p.appendChild(el("p", "v2-poruka__naslov", "Pretraga nije izvršena"));
      p.appendChild(el("p", "v2-poruka__telo",
        "Pretraga internih stavova trenutno nije dostupna. Ovo NE znači da firma "
        + "nema stav o ovome — znači da nije provereno. Pokušajte ponovo."));
      sadrzaj.replaceChildren(p);
      return;
    }
    if (!r.rezultati.length) {
      sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
        "Pretraga je izvršena i nije pronašla nijedan interni stav o ovome."));
      return;
    }
    const okvir = document.createDocumentFragment();
    okvir.appendChild(el("p", "v2-reg__broj",
      r.ukupno === 1 ? "1 stav" : `${r.rezultati.length} od ${r.ukupno} stavova`));
    const ul = el("ul", "v2-lista-tanka");
    for (const s of r.rezultati) {
      const li = el("li");
      li.appendChild(el("p", "", s.naslov));
      if (s.tekst) li.appendChild(el("p", "v2-proza", s.tekst));
      ul.appendChild(li);
    }
    okvir.appendChild(ul);
    sadrzaj.replaceChildren(okvir);
  }

  prazno();

  let radi = false;
  ciklus.slusaj(forma, "submit", async (e) => {
    e.preventDefault();
    if (radi || !upit.value.trim()) { if (!upit.value.trim()) prazno(); return; }
    radi = true;
    trazi.disabled = true;
    sadrzaj.setAttribute("aria-busy", "true");
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno", "Pretraga u toku…"));
    const prekidac = ciklus.prekidac();
    try {
      const r = await posalji("/interni-stavovi/pretraga", {
        telo: { upit: upit.value.trim() }, signal: prekidac.signal,
      });
      if (ciklus.ugasen) return;
      iscrtaj(uPretragu(r));
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      const p = el("div", "v2-poruka v2-poruka--greska");
      p.appendChild(el("p", "v2-poruka__naslov", "Pretraga nije izvršena"));
      p.appendChild(el("p", "v2-poruka__telo", porukaZaKorisnika(err)));
      sadrzaj.replaceChildren(p);
    } finally {
      radi = false;
      trazi.disabled = false;
      sadrzaj.setAttribute("aria-busy", "false");
    }
  });

  ciklus.slusaj(dodajForma, "submit", async (e) => {
    e.preventDefault();
    const greske = nedostaciStava(naslovPolje.value, tekstPolje.value);
    if (greske.length) {
      dodajPoruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      dodajPoruka.textContent = greske.join(" ");
      dodajPoruka.hidden = false;
      return;
    }
    dodajDugme.disabled = true;
    dodajDugme.textContent = "Čuva se…";
    dodajPoruka.hidden = true;
    try {
      await posalji("/interni-stavovi/dodaj", {
        telo: { naslov: naslovPolje.value.trim(), tekst: tekstPolje.value.trim() },
        signal: ciklus.prekidac().signal,
      });
      if (ciklus.ugasen) return;
      naslovPolje.value = "";
      tekstPolje.value = "";
      ostavi("Stav je sačuvan.", "uspeh");
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      dodajPoruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      dodajPoruka.textContent = "Stav nije sačuvan. " + porukaZaKorisnika(err);
      dodajPoruka.hidden = false;
    } finally {
      dodajDugme.disabled = false;
      dodajDugme.textContent = "Sačuvaj stav";
    }
  });

  ciklus.kontekst = () => ({ upit: upit.value });
  return ciklus;
}
