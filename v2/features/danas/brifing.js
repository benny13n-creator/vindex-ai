/* Vindex V2 — jutarnji brifing (`/app-v2/danas/brifing`), H5.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * BRIFING SE TRAZI, NE DESAVA SE SAM
 *
 * `/api/briefing/daily` zove model i trosi kvotu (`UsageService.consume`),
 * uz granicu od 10 poziva na minut. Ekran koji bi ga povlacio pri svakom
 * otvaranju Danas trosio bi advokatov plan bez njegove odluke. Zato je ovde
 * DUGME, i zato pise da se brifing pravi.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * MODEL NIJE AUTORITET NAD STANJEM IZVORA. Uz tekst backend vraca masinski
 * proverive zastavice o tome koji su izvori procitani. Brojevi se prikazuju
 * IZ ZASTAVICA, ne iz teksta; a kad izvor nije procitan, njegov broj se ne
 * prikazuje kao nula nego se imenuje kao nepoznat.
 *
 * TEKST MODELA JE OZNACEN KAO TEKST MODELA. Advokat mora znati koja je
 * recenica racun, a koja prepricavanje.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { dohvati } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { idiNa, putanjaZa, idiNaPutanju } from "../../platform/router.js";
import { uBrifing, delovi } from "../../domain/brifing.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

export function montirajBrifing(kontejner, kontekst) {
  const ciklus = napraviCiklus();
  const zaceto = kontekst || {};
  let podaci = zaceto.podaci || null;

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--tekst");

  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Jutarnji brifing");
  h1.id = "v2-naslov-brifing";
  zaglavlje.appendChild(h1);
  zaglavlje.appendChild(el("p", "v2-podnaslov",
    "Pregled dana sastavljen iz vaših predmeta, rokova i ročišta. "
    + "Brojevi su računati; prateći tekst piše model i tako je označen."));
  unutra.appendChild(zaglavlje);

  // ── Prekidac ──
  const prekidac = el("nav", "v2-prekidac");
  prekidac.setAttribute("aria-label", "Pregled vremena");
  const kaDanas = el("a", "v2-prekidac__stavka", "Danas");
  kaDanas.href = putanjaZa("danas");
  ciklus.slusaj(kaDanas, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("danas");
  });
  const kaKalendaru = el("a", "v2-prekidac__stavka", "Kalendar");
  kaKalendaru.href = putanjaZa("danas", "kalendar");
  ciklus.slusaj(kaKalendaru, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("danas", "kalendar");
  });
  const ovde = el("span", "v2-prekidac__stavka v2-prekidac__stavka--aktivna", "Brifing");
  ovde.setAttribute("aria-current", "page");
  prekidac.append(kaDanas, kaKalendaru, ovde);
  unutra.appendChild(prekidac);

  const alat = el("div", "v2-reg__alat");
  const dugme = el("button", "v2-dugme v2-dugme--glavno", "Napravi brifing");
  dugme.type = "button";
  alat.appendChild(dugme);
  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;
  alat.appendChild(poruka);
  unutra.appendChild(alat);

  const sadrzaj = el("div", "v2-brifing");
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  sadrzaj.setAttribute("aria-labelledby", "v2-naslov-brifing");
  unutra.appendChild(sadrzaj);
  kontejner.appendChild(unutra);
  document.title = "Jutarnji brifing · Vindex";

  function javi(t, vrsta) {
    poruka.className = "v2-forma__poruka v2-forma__poruka--" + (vrsta || "greska");
    poruka.textContent = t;
    poruka.hidden = false;
  }

  function brojka(oznaka, vrednost, dostupno) {
    const d = el("div", "v2-brifing__broj");
    d.appendChild(el("span", "v2-brifing__oznaka", oznaka));
    // Kad izvor nije procitan, broj se NE prikazuje kao nula. „0 rokova"
    // iz palog upita je tvrdnja o odsustvu koju niko nije proverio.
    if (!dostupno || vrednost === null) {
      d.appendChild(el("span", "v2-brifing__vrednost v2-brifing__vrednost--nepoznato",
        "nije očitano"));
    } else {
      d.appendChild(el("span", "v2-brifing__vrednost v2-mono", String(vrednost)));
    }
    return d;
  }

  function spisak(naslov, stavke) {
    if (!stavke.length) return null;
    const b = el("div", "v2-podblok");
    b.appendChild(el("h3", "v2-natkapa", naslov));
    const ul = el("ul", "v2-lista-tanka");
    for (const x of stavke) {
      const li = el("li");
      if (x.predmetId) {
        const a = el("a", "v2-brifing__veza", x.opis || "Bez opisa");
        a.href = putanjaZa("predmet", x.predmetId) + "#celina-rokovi";
        ciklus.slusaj(a, "click", (e) => {
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
          e.preventDefault();
          idiNaPutanju(putanjaZa("predmet", x.predmetId) + "#celina-rokovi");
        });
        li.appendChild(a);
      } else {
        li.appendChild(document.createTextNode(x.opis || "Bez opisa"));
      }
      if (x.datum) li.appendChild(el("span", "v2-beleska__datum", " — " + x.datum));
      ul.appendChild(li);
    }
    b.appendChild(ul);
    return b;
  }

  function iscrtaj(d) {
    const okvir = document.createDocumentFragment();

    // Ograda IZNAD svega: ako izvor nije procitan, ni brojevi ni tekst ne
    // smeju da se citaju kao potpun pregled dana.
    if (!d.potpun) {
      const og = el("div", "v2-poruka v2-poruka--upozorenje");
      og.setAttribute("role", "alert");
      og.appendChild(el("p", "v2-poruka__naslov", "Brifing je nepotpun"));
      og.appendChild(el("p", "v2-poruka__telo",
        "Nije očitano: " + d.nedostupni.join(", ")
        + ". Ono što nedostaje ne znači da ga nema — znači da nije pročitano. "
        + "Ne donosite odluke o odsustvu obaveza iz ovog pregleda."));
      okvir.appendChild(og);
    }

    const s = d.statistike;
    const dostupno = (naziv) => !d.nedostupni.includes(naziv);
    const mreza = el("div", "v2-brifing__brojevi");
    mreza.appendChild(brojka("Aktivnih predmeta", s.aktivnihPredmeta, dostupno("predmeti")));
    mreza.appendChild(brojka("Hitnih rokova", s.rokovaHitnih, dostupno("rokovi")));
    mreza.appendChild(brojka("Rokova ove nedelje", s.rokovaNedelja, dostupno("rokovi")));
    mreza.appendChild(brojka("Propuštenih rokova", s.rokovaPropustenih, dostupno("rokovi")));
    mreza.appendChild(brojka("Ročišta danas", s.rocistaDanas, dostupno("ročišta")));
    mreza.appendChild(brojka("Ročišta ove nedelje", s.rocistaSedmica, dostupno("ročišta")));
    okvir.appendChild(mreza);

    for (const [naslov, lista] of [
      ["Hitni rokovi", d.hitniRokovi],
      ["Propušteni rokovi", d.propusteniRokovi],
      ["Ročišta danas", d.rocistaDanas],
      ["Propuštena ročišta", d.propustenaRocista],
    ]) {
      const b = spisak(naslov, lista);
      if (b) okvir.appendChild(b);
    }

    if (d.tekstBrifinga) {
      const sek = el("section", "v2-brifing__tekst");
      // Tekst modela se IMENUJE kao tekst modela. Advokat mora znati koja je
      // recenica racun, a koja prepricavanje.
      sek.appendChild(el("h2", "v2-natkapa", "Sažetak — sastavio model"));
      for (const red of d.tekstBrifinga.replace(/\r\n/g, "\n").split(/\n{2,}/)) {
        const t = red.trim();
        if (!t) continue;
        const p = el("p", "v2-znanje__pasus");
        t.split("\n").forEach((linija, i) => {
          if (i) p.appendChild(document.createElement("br"));
          // Nikad `innerHTML`: tekst dolazi od modela.
          for (const deo of delovi(linija)) {
            if (deo.jak) p.appendChild(el("strong", "", deo.t));
            else p.appendChild(document.createTextNode(deo.t));
          }
        });
        sek.appendChild(p);
      }
      okvir.appendChild(sek);
    }

    if (d.datum) {
      okvir.appendChild(el("p", "v2-celina__prazno", "Brifing za " + d.datum + "."));
    }

    sadrzaj.replaceChildren(okvir);
  }

  async function napravi() {
    dugme.disabled = true;
    dugme.textContent = "Brifing se pravi…";
    poruka.hidden = true;
    sadrzaj.setAttribute("aria-busy", "true");
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
      "Brifing se pravi. Ovo može potrajati nekoliko sekundi."));
    try {
      const r = await dohvati("/api/briefing/daily",
                              { signal: ciklus.prekidac().signal });
      if (ciklus.ugasen) return;
      podaci = uBrifing(r);
      sadrzaj.setAttribute("aria-busy", "false");
      iscrtaj(podaci);
      sadrzaj.focus();
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      sadrzaj.setAttribute("aria-busy", "false");
      sadrzaj.replaceChildren();
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      if (err && err.vrsta === VRSTA.ZABRANJENO) {
        javi("Vaš plan ne uključuje jutarnji brifing.", "upozorenje");
        return;
      }
      if (err && err.status === 429) {
        javi("Dostigli ste granicu broja brifinga za ovaj minut. "
           + "Sačekajte i pokušajte ponovo — ovo nije kvar.", "upozorenje");
        return;
      }
      // Prazan ekran ovde bi se procitao kao „danas nema nicega".
      javi("Brifing nije napravljen. " + porukaZaKorisnika(err)
         + " Ovo ne znači da danas nema obaveza — otvorite Danas.");
    } finally {
      if (!ciklus.ugasen) {
        dugme.disabled = false;
        dugme.textContent = podaci ? "Napravi ponovo" : "Napravi brifing";
      }
    }
  }

  ciklus.slusaj(dugme, "click", napravi);

  if (podaci) {
    // Vracanje na ekran ne trosi nov poziv: prikazuje se vec napravljen
    // brifing, uz datum kad je napravljen.
    iscrtaj(podaci);
    dugme.textContent = "Napravi ponovo";
  } else {
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
      "Brifing se pravi na zahtev jer troši deo vašeg plana. "
      + "Pritisnite „Napravi brifing”."));
  }

  ciklus.kontekst = () => ({ podaci });

  return ciklus;
}
