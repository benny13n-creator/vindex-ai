/* Vindex V2 — obavestenja (`/app-v2/danas/obavestenja`), H7.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * ZAPAZANJA SISTEMA, NE ROKOVI
 *
 * Obavestenja su ono sto je sistem PRIMETIO o predmetima: predmet bez
 * aktivnosti 30 dana, rok koji se priblizava, rociste. To NIJE ista stvar
 * kao potvrdjena obaveza u Danas — zato stoji kao poseban pogled istog
 * prostora, a ne kao jos jedan spisak rokova.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * PRAZAN SPISAK NIJE ISTO STO I NEPROCITAN. `/notifications` na gresku vraca
 * 200 sa praznim nizom. Ekran zato gleda `procitano_uspesno` i, kad citanje
 * nije dokazano uspelo, kaze „nije procitano" umesto „nemate obavestenja".
 *
 * OZNACAVANJE PROCITANIM SALJE SVE ID-JEVE GRUPE. Backend spaja vise
 * obavestenja istog tipa u jedan red; oznaciti samo predstavnika ostavilo bi
 * ostale neprocitane, a spisak bi IZGLEDAO procitano (F21).
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { dohvati, posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { ostavi } from "../../platform/obavestenje.js";
import { idiNa, putanjaZa, idiNaPutanju } from "../../platform/router.js";
import { uObavestenja, idZaOznacavanje } from "../../domain/obavestenja.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

export function montirajObavestenja(kontejner) {
  const ciklus = napraviCiklus();

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--danas");

  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Obaveštenja");
  h1.id = "v2-naslov-obavestenja";
  zaglavlje.appendChild(h1);
  const brojac = el("p", "v2-reg__broj");
  zaglavlje.appendChild(brojac);
  zaglavlje.appendChild(el("p", "v2-podnaslov",
    "Šta je sistem primetio o vašim predmetima. Ovo nisu potvrđene obaveze — "
    + "one su u Danas."));
  unutra.appendChild(zaglavlje);

  const prekidac = el("nav", "v2-prekidac");
  prekidac.setAttribute("aria-label", "Pregled vremena");
  for (const [naziv, param] of [["Danas", null], ["Kalendar", "kalendar"],
                                ["Brifing", "brifing"]]) {
    const a = el("a", "v2-prekidac__stavka", naziv);
    a.href = param ? putanjaZa("danas", param) : putanjaZa("danas");
    ciklus.slusaj(a, "click", (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
      e.preventDefault();
      if (param) idiNa("danas", param); else idiNa("danas");
    });
    prekidac.appendChild(a);
  }
  const ovde = el("span", "v2-prekidac__stavka v2-prekidac__stavka--aktivna", "Obaveštenja");
  ovde.setAttribute("aria-current", "page");
  prekidac.appendChild(ovde);
  unutra.appendChild(prekidac);

  const alat = el("div", "v2-reg__alat");
  const sve = el("button", "v2-dugme", "Označi sve pročitanim");
  sve.type = "button";
  sve.hidden = true;
  alat.appendChild(sve);
  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;
  alat.appendChild(poruka);
  unutra.appendChild(alat);

  const sadrzaj = el("div", "v2-obavestenja");
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  sadrzaj.setAttribute("aria-labelledby", "v2-naslov-obavestenja");
  unutra.appendChild(sadrzaj);
  kontejner.appendChild(unutra);
  document.title = "Obaveštenja · Vindex";

  let stanje = null;

  function javi(t, vrsta) {
    poruka.className = "v2-forma__poruka v2-forma__poruka--" + (vrsta || "greska");
    poruka.textContent = t;
    poruka.hidden = false;
  }

  function red(x) {
    const li = el("li", "v2-obavestenje-red");
    li.dataset.prioritet = x.prioritet;
    if (!x.procitano) li.dataset.neprocitano = "1";

    const glava = el("p", "v2-obavestenje-red__naslov");
    if (x.predmetId) {
      const a = el("a", "v2-obavestenje-red__veza", x.naslov || "Bez naslova");
      a.href = putanjaZa("predmet", x.predmetId);
      ciklus.slusaj(a, "click", (e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        e.preventDefault();
        idiNaPutanju(putanjaZa("predmet", x.predmetId));
      });
      glava.appendChild(a);
    } else {
      glava.appendChild(document.createTextNode(x.naslov || "Bez naslova"));
    }
    // Naslov grupe sa servera vec pocinje brojem („3 × Rok za 7 dana"), pa se
    // broj ne dopisuje jos jednom.
    if (x.koliko && !/^\s*\d+\s*[×x]/.test(x.naslov)) {
      glava.appendChild(el("span", "v2-obavestenje-red__broj", ` ${x.koliko} stavki`));
    }
    li.appendChild(glava);

    if (x.poruka) li.appendChild(el("p", "v2-obavestenje-red__telo", x.poruka));
    if (x.kada) {
      li.appendChild(el("p", "v2-obavestenje-red__kada", x.kada.slice(0, 10)));
    }
    return li;
  }

  function iscrtaj(d) {
    // Kad citanje nije DOKAZANO uspelo, prazan spisak se ne prikazuje kao
    // odsustvo obavestenja.
    if (!d.procitanoUspesno) {
      brojac.textContent = "";
      sve.hidden = true;
      const p = el("div", "v2-poruka v2-poruka--greska");
      p.appendChild(el("p", "v2-poruka__naslov", "Obaveštenja nisu pročitana"));
      p.appendChild(el("p", "v2-poruka__telo",
        "Server je odgovorio, ali spisak nije pročitan. Prazan spisak bi ovde "
        + "bio netačan — ne zaključujte da obaveštenja nema."));
      sadrzaj.replaceChildren(p);
      return;
    }

    const n = d.neprocitani.length;
    brojac.textContent = n === 0
      ? `${d.svi.length} ${d.svi.length === 1 ? "obaveštenje" : "obaveštenja"}, sva pročitana`
      : `${n} ${n === 1 ? "nepročitano" : "nepročitanih"} od ${d.svi.length}`;
    sve.hidden = n === 0;

    if (!d.svi.length) {
      sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
        "Nema obaveštenja. Sistem nije primetio ništa što traži vašu pažnju."));
      return;
    }
    const ul = el("ul", "v2-obavestenja__lista");
    for (const x of d.svi) ul.appendChild(red(x));
    sadrzaj.replaceChildren(ul);
  }

  async function ucitaj() {
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno", "Učitava se…"));
    try {
      const r = await dohvati("/notifications",
                              { signal: ciklus.prekidac().signal });
      if (ciklus.ugasen) return;
      stanje = uObavestenja(r);
      iscrtaj(stanje);
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      const p = el("div", "v2-poruka v2-poruka--greska");
      p.appendChild(el("p", "v2-poruka__naslov", "Obaveštenja nisu učitana"));
      p.appendChild(el("p", "v2-poruka__telo",
        porukaZaKorisnika(err) + " Ne zaključujte da obaveštenja nema."));
      sadrzaj.replaceChildren(p);
    }
  }

  ciklus.slusaj(sve, "click", async () => {
    if (!stanje) return;
    const ids = idZaOznacavanje(stanje.neprocitani);
    sve.disabled = true;
    sve.textContent = "Označava se…";
    poruka.hidden = true;
    try {
      // Grupa nosi SVE svoje id-jeve: oznaciti samo predstavnika ostavilo bi
      // ostale neprocitane, a spisak bi izgledao procitano (F21).
      // Preko 50 id-jeva server odbija, pa se tada koristi `read-all`.
      if (ids.length && ids.length <= 50) {
        await posalji("/notifications/read-group", {
          metod: "PATCH", telo: { ids }, signal: ciklus.prekidac().signal,
        });
      } else {
        await posalji("/notifications/read-all", {
          metod: "PATCH", telo: {}, signal: ciklus.prekidac().signal,
        });
      }
      if (ciklus.ugasen) return;
      ostavi("Obaveštenja su označena pročitanim.", "uspeh");
      await ucitaj();
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      javi("Obaveštenja nisu označena pročitanim. " + porukaZaKorisnika(err));
    } finally {
      if (!ciklus.ugasen) {
        sve.disabled = false;
        sve.textContent = "Označi sve pročitanim";
      }
    }
  });

  ucitaj();
  return ciklus;
}
