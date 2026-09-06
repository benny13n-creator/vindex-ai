/* Vindex V2 — tarife kancelarije (`/app-v2/kancelarija/tarife`), F8.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * ADVOKATSKA TARIFA NIJE MOJ BROJ — DOK JE NE PROMENIM
 *
 * Backend razlikuje dve stvari i ovaj ekran ih NE SME spojiti:
 *
 *   AKS iznos        — iznos iz Advokatske tarife (bodovi × vrednost boda).
 *                      To je propisana vrednost, ne moja odluka.
 *   Moja izmena      — sopstveni iznos koji sam postavio umesto AKS-a.
 *                      `is_custom: true`.
 *
 * Ako se prikaze samo jedan broj, advokat ne moze da zna da li gleda ono sto
 * propisuje tarifa ili ono sto je sam nekada uneo — a razlika je ono na sta
 * se poziva pred klijentom i pred sudom. Zato se AKS iznos prikazuje UVEK, a
 * sopstvena izmena se imenuje kao izmena.
 *
 * Vracanje na AKS je ODVOJENA radnja (PUT bez `iznos` i bez `naziv`), i
 * server na nju vraca 404 ako sopstvene izmene nema — sto ovde nije kvar
 * nego stanje: nema sta da se vrati.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * SATNICA IMA PODRAZUMEVANU VREDNOST, I TO SE KAZE. `source: "default"`
 * znaci da satnica NIJE moja odluka nego pretpostavka sistema; prikazati je
 * kao moju znacilo bi da advokat naplacuje po broju koji nikada nije izabrao.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { dohvati, posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { ostavi } from "../../platform/obavestenje.js";
import { idiNa, putanjaZa } from "../../platform/router.js";
import { uSatnicu, uStavkeTarife, nedostaciIznosa } from "../../domain/tarife.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

function celina(kljuc, naziv) {
  const s = el("section", "v2-celina");
  s.dataset.celina = kljuc;
  const h = el("h2", "v2-celina__naslov", naziv);
  h.id = "celina-" + kljuc;
  s.setAttribute("aria-labelledby", h.id);
  s.appendChild(h);
  return s;
}

async function ucitaj({ signal } = {}) {
  const [s, t] = await Promise.allSettled([
    dohvati("/api/tarife/moja-satnica", { signal }),
    dohvati("/api/tarife/stavke", { signal }),
  ]);
  for (const x of [s, t]) {
    if (x.status === "rejected" && jePrekid(x.reason)) throw x.reason;
  }
  return {
    satnica: s.status === "fulfilled" ? uSatnicu(s.value) : null,
    satnicaGreska: s.status === "rejected" ? s.reason : null,
    stavke: t.status === "fulfilled" ? uStavkeTarife(t.value) : null,
    stavkeGreska: t.status === "rejected" ? t.reason : null,
  };
}

export function montirajTarife(kontejner) {
  const ciklus = napraviCiklus();

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--predmet");
  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Tarife");
  h1.id = "v2-naslov-tarife";
  zaglavlje.appendChild(h1);
  zaglavlje.appendChild(el("p", "v2-podnaslov",
    "Vaša satnica i Advokatska tarifa. Iznos iz tarife se prikazuje uvek — "
    + "vaša izmena stoji uz njega, ne umesto njega."));
  unutra.appendChild(zaglavlje);

  const prekidac = el("nav", "v2-prekidac");
  prekidac.setAttribute("aria-label", "Kancelarija");
  const kaKanc = el("a", "v2-prekidac__stavka", "Kancelarija");
  kaKanc.href = putanjaZa("kancelarija");
  ciklus.slusaj(kaKanc, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("kancelarija");
  });
  const kaFin = el("a", "v2-prekidac__stavka", "Finansije");
  kaFin.href = putanjaZa("kancelarija", "finansije");
  ciklus.slusaj(kaFin, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("kancelarija", "finansije");
  });
  const ovde = el("span", "v2-prekidac__stavka v2-prekidac__stavka--aktivna", "Tarife");
  ovde.setAttribute("aria-current", "page");
  prekidac.append(kaKanc, kaFin, ovde);
  unutra.appendChild(prekidac);

  const sadrzaj = el("div", "v2-kancelarija");
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  sadrzaj.setAttribute("aria-labelledby", "v2-naslov-tarife");
  unutra.appendChild(sadrzaj);
  kontejner.appendChild(unutra);
  document.title = "Tarife · Vindex";

  function nijeUcitano(sta, err) {
    const p = el("div", "v2-poruka v2-poruka--greska");
    p.appendChild(el("p", "v2-poruka__naslov", sta + " nije učitano"));
    p.appendChild(el("p", "v2-poruka__telo", porukaZaKorisnika(err)));
    return p;
  }

  /* ── Satnica ─────────────────────────────────────────────────────────── */
  function sekcijaSatnice(d) {
    const s = celina("satnica", "Satnica");
    if (!d.satnica) { s.appendChild(nijeUcitano("Satnica", d.satnicaGreska)); return s; }
    const t = d.satnica;

    const red = el("p", "v2-tarifa__satnica");
    red.appendChild(el("span", "v2-mono v2-tarifa__iznos", t.iznos));
    red.appendChild(document.createTextNode(" po satu"));
    s.appendChild(red);

    // Podrazumevana satnica NIJE moja odluka i to se kaze.
    s.appendChild(el("p", "v2-celina__prazno", t.sopstvena
      ? "Vaša satnica."
      : "Podrazumevana vrednost sistema — niste je postavili. "
        + "Rad po satu se do izmene obračunava po ovom iznosu."));

    const forma = el("form", "v2-forma");
    forma.noValidate = true;
    const red2 = el("div", "v2-radnja__red");
    const unos = el("input", "v2-polje-unos__kontrola v2-polje-unos__kontrola--usko");
    unos.type = "text";
    unos.inputMode = "numeric";
    unos.id = "v2-satnica";
    unos.value = t.iznosBroj === null ? "" : String(t.iznosBroj);
    unos.setAttribute("aria-label", "Nova satnica u dinarima");
    const cuvaj = el("button", "v2-dugme", "Sačuvaj satnicu");
    cuvaj.type = "submit";
    red2.append(unos, cuvaj);
    const poruka = el("div", "v2-forma__poruka");
    poruka.setAttribute("role", "alert");
    poruka.hidden = true;
    forma.append(red2, poruka);
    s.appendChild(forma);

    ciklus.slusaj(forma, "submit", async (e) => {
      e.preventDefault();
      const g = nedostaciIznosa(unos.value);
      if (g.length) {
        poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
        poruka.textContent = g.join(" ");
        poruka.hidden = false;
        return;
      }
      cuvaj.disabled = true;
      cuvaj.textContent = "Čuva se…";
      poruka.hidden = true;
      try {
        await posalji("/api/tarife/moja-satnica", {
          metod: "PUT",
          telo: { tarifa_po_satu: Number(unos.value.replace(/\s/g, "").replace(",", ".")) },
          signal: ciklus.prekidac().signal,
        });
        if (ciklus.ugasen) return;
        ostavi("Satnica je sačuvana.", "uspeh");
        ucitajIPrikazi();
      } catch (err) {
        if (jePrekid(err) || ciklus.ugasen) return;
        cuvaj.disabled = false;
        cuvaj.textContent = "Sačuvaj satnicu";
        if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
        poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
        poruka.textContent = "Satnica nije sačuvana. " + porukaZaKorisnika(err);
        poruka.hidden = false;
      }
    });
    return s;
  }

  /* ── Stavke Advokatske tarife ────────────────────────────────────────── */
  function sekcijaStavki(d) {
    const s = celina("stavke", "Advokatska tarifa");
    if (!d.stavke) { s.appendChild(nijeUcitano("Advokatska tarifa", d.stavkeGreska)); return s; }
    const st = d.stavke;

    if (!st.svi.length) {
      s.appendChild(el("p", "v2-celina__prazno", "Tarifa nije učitana."));
      return s;
    }

    const zbir = st.mojih === 1
      ? "1 stavka ima vašu izmenu."
      : `${st.mojih} stavki ima vašu izmenu.`;
    s.appendChild(el("p", "v2-celina__prazno",
      `${st.svi.length} stavki. ${st.mojih ? zbir : "Nijedna stavka nema vašu izmenu — sve su po Advokatskoj tarifi."}`));

    const ul = el("ul", "v2-fin__lista");
    for (const x of st.svi) {
      const li = el("li", "v2-tarifa__stavka");
      if (x.moja) li.dataset.moja = "1";

      const glava = el("div", "v2-fin__glava");
      const ime = el("span", "v2-tarifa__naziv");
      ime.appendChild(el("span", "v2-mono v2-tarifa__sifra", x.sifra));
      ime.appendChild(document.createTextNode(" " + x.naziv));
      glava.appendChild(ime);
      glava.appendChild(el("span", "v2-fin__iznos v2-mono", " " + x.iznos));
      li.appendChild(glava);

      // AKS iznos se prikazuje UVEK. Kad postoji sopstvena izmena, oba broja
      // stoje jedan uz drugi — advokat mora videti od cega je odstupio.
      const meta = el("p", "v2-tarifa__meta");
      if (x.moja) {
        meta.appendChild(el("span", "v2-znak", "vaša izmena"));
        meta.appendChild(document.createTextNode(
          " · po Advokatskoj tarifi " + x.aks));
      } else {
        meta.appendChild(document.createTextNode("po Advokatskoj tarifi"));
      }
      if (x.bodovi !== null) {
        meta.appendChild(document.createTextNode(` · ${x.bodovi} bodova`));
      }
      li.appendChild(meta);

      li.appendChild(kontrolaIzmene(x));
      ul.appendChild(li);
    }
    s.appendChild(ul);
    return s;
  }

  function kontrolaIzmene(x) {
    const omot = el("div", "v2-tarifa__radnja");
    const otvori = el("button", "v2-tekst-akcija", x.moja ? "Izmeni" : "Postavi svoj iznos");
    otvori.type = "button";
    otvori.setAttribute("aria-label",
      (x.moja ? "Izmeni iznos za " : "Postavi svoj iznos za ") + x.sifra);
    omot.appendChild(otvori);

    ciklus.slusaj(otvori, "click", () => {
      if (omot.querySelector(".v2-forma")) return;
      otvori.hidden = true;

      const forma = el("form", "v2-forma");
      forma.noValidate = true;
      const red = el("div", "v2-radnja__red");
      const unos = el("input", "v2-polje-unos__kontrola v2-polje-unos__kontrola--usko");
      unos.type = "text";
      unos.inputMode = "numeric";
      unos.value = x.iznosBroj === null ? "" : String(x.iznosBroj);
      unos.setAttribute("aria-label", "Iznos za " + x.sifra);
      const cuvaj = el("button", "v2-dugme", "Sačuvaj");
      cuvaj.type = "submit";
      const odustani = el("button", "v2-dugme v2-dugme--tiho", "Odustani");
      odustani.type = "button";
      red.append(unos, cuvaj, odustani);

      const poruka = el("div", "v2-forma__poruka");
      poruka.setAttribute("role", "alert");
      poruka.hidden = true;
      forma.append(red, poruka);

      // Vracanje na AKS je ODVOJENA radnja i nudi se samo kad ima sta da se
      // vrati — inace bi dugme obecavalo nesto sto server odbija sa 404.
      if (x.moja) {
        const vrati = el("button", "v2-tekst-akcija", "Vrati na Advokatsku tarifu");
        vrati.type = "button";
        red.appendChild(vrati);
        ciklus.slusaj(vrati, "click", async () => {
          vrati.disabled = true;
          try {
            await posalji(`/api/tarife/stavke/${encodeURIComponent(x.sifra)}`, {
              metod: "PUT", telo: {}, signal: ciklus.prekidac().signal,
            });
            if (ciklus.ugasen) return;
            ostavi(`Stavka ${x.sifra} je vraćena na Advokatsku tarifu.`, "uspeh");
            ucitajIPrikazi();
          } catch (err) {
            if (jePrekid(err) || ciklus.ugasen) return;
            vrati.disabled = false;
            if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
            poruka.className = "v2-forma__poruka v2-forma__poruka--"
              + (err && err.status === 404 ? "upozorenje" : "greska");
            // 404 ovde nije kvar: nema sopstvene izmene koju bi trebalo vratiti.
            poruka.textContent = err && err.status === 404
              ? "Nemate sopstvenu izmenu ove stavke — nema šta da se vrati."
              : "Stavka nije vraćena. " + porukaZaKorisnika(err);
            poruka.hidden = false;
          }
        });
      }

      omot.appendChild(forma);
      unos.focus();

      ciklus.slusaj(odustani, "click", () => {
        forma.remove(); otvori.hidden = false; otvori.focus();
      });

      ciklus.slusaj(forma, "submit", async (e) => {
        e.preventDefault();
        const g = nedostaciIznosa(unos.value);
        if (g.length) {
          poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
          poruka.textContent = g.join(" ");
          poruka.hidden = false;
          return;
        }
        cuvaj.disabled = true;
        cuvaj.textContent = "Čuva se…";
        poruka.hidden = true;
        try {
          await posalji(`/api/tarife/stavke/${encodeURIComponent(x.sifra)}`, {
            metod: "PUT",
            telo: { iznos: Number(unos.value.replace(/\s/g, "").replace(",", ".")) },
            signal: ciklus.prekidac().signal,
          });
          if (ciklus.ugasen) return;
          ostavi(`Iznos za ${x.sifra} je sačuvan.`, "uspeh");
          ucitajIPrikazi();
        } catch (err) {
          if (jePrekid(err) || ciklus.ugasen) return;
          cuvaj.disabled = false;
          cuvaj.textContent = "Sačuvaj";
          if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
          poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
          poruka.textContent = "Iznos nije sačuvan. " + porukaZaKorisnika(err);
          poruka.hidden = false;
        }
      });
    });

    return omot;
  }

  async function ucitajIPrikazi() {
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno", "Učitava se…"));
    let d;
    try {
      d = await ucitaj({ signal: ciklus.prekidac().signal });
    } catch (e) {
      if (jePrekid(e) || ciklus.ugasen) return;
      if (e && e.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      sadrzaj.replaceChildren(nijeUcitano("Tarife", e));
      return;
    }
    if (ciklus.ugasen) return;
    const okvir = document.createDocumentFragment();
    okvir.appendChild(sekcijaSatnice(d));
    okvir.appendChild(sekcijaStavki(d));
    sadrzaj.replaceChildren(okvir);
  }

  ucitajIPrikazi();
  return ciklus;
}
