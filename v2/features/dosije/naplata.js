/* Vindex V2 — naplata JEDNOG predmeta, unutar Dosijea (B16).
 *
 * ─────────────────────────────────────────────────────────────────────────
 * ZASTO JE OVO U DOSIJEU, A NE SAMO U KANCELARIJI
 *
 * Kancelarija odgovara na „koliko sam ovog meseca zaradio i sta jos nije
 * fakturisano" — pitanje nad SVIM predmetima. Dosije odgovara na „koliko je
 * rada ulozeno u OVAJ predmet". To je drugo pitanje i postavlja se na drugom
 * mestu: dok advokat gleda predmet, ne dok gleda kancelariju.
 *
 * Zato ovde NEMA biraca predmeta. Predmet je vec izabran time sto je Dosije
 * otvoren; birac bi bio prilika da se rad evidentira na pogresan predmet.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * TAJMER JE JEDAN PO ADVOKATU, NE PO PREDMETU. Backend dozvoljava tacno
 * jedno aktivno merenje (migracija 084, UNIQUE(user_id) WHERE aktivan) i na
 * drugi pokusaj vraca 409. To NIJE greska aplikacije nego stanje o kome
 * advokat mora znati: merenje vec tece, i to mozda na drugom predmetu.
 * Prikaz zato imenuje predmet na kome merenje tece.
 *
 * ODSUTAN IZNOS NIJE NULA. `dinar()` cuva razliku izmedju „nema unetog
 * iznosa" i „0 RSD" — sabirati nepoznato kao nulu znacilo bi reci advokatu
 * da na predmetu nema duga.
 */

import { dohvati, posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { ostavi } from "../../platform/obavestenje.js";
import { uUnose, uTajmer, trajanje, nedostaciUnosa, uTeloUnosa } from "../../domain/naplata.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

/** Ucitava SAMO ono sto se tice ovog predmeta, plus stanje tajmera. */
export async function ucitajNaplatuPredmeta(predmetId, { signal } = {}) {
  const [u, t] = await Promise.allSettled([
    dohvati("/billing/entries", { upit: { predmet_id: predmetId }, signal }),
    dohvati("/billing/timer/aktivan", { signal }),
  ]);
  for (const x of [u, t]) {
    if (x.status === "rejected" && jePrekid(x.reason)) throw x.reason;
  }
  return {
    unosi: u.status === "fulfilled" ? uUnose(u.value) : null,
    unosiPali: u.status === "rejected",
    unosiGreska: u.status === "rejected" ? u.reason : null,
    tajmer: t.status === "fulfilled" ? uTajmer(t.value) : null,
    tajmerPao: t.status === "rejected",
  };
}

function iznosRed(naziv, vrednost) {
  const r = el("div", "v2-naplata__stavka");
  r.appendChild(el("span", "v2-naplata__oznaka", naziv));
  r.appendChild(el("span", "v2-naplata__iznos v2-mono", vrednost));
  return r;
}

/* ── Sazetak ────────────────────────────────────────────────────────────── */
function blokSazetka(u) {
  const b = el("div", "v2-podblok");
  b.appendChild(el("h3", "v2-natkapa", "Evidentiran rad"));
  const g = el("div", "v2-naplata__zbir");
  // Tri iznosa se drze RAZDVOJENA: „ukupno" nije „naplaceno", a
  // „neobracunato" je jedini broj koji govori sta jos treba fakturisati.
  g.appendChild(iznosRed("Ukupno", u.ukupno));
  g.appendChild(iznosRed("Obračunato", u.obracunato));
  g.appendChild(iznosRed("Nije obračunato", u.neobracunato));
  if (u.sati !== null) g.appendChild(iznosRed("Sati", String(u.sati)));
  b.appendChild(g);
  return b;
}

/* ── Spisak unosa ───────────────────────────────────────────────────────── */
function blokSpiska(u) {
  const b = el("div", "v2-podblok");
  if (!u.svi.length) {
    b.appendChild(el("p", "v2-celina__prazno",
      "Na ovom predmetu još nije evidentiran rad."));
    return b;
  }
  const ul = el("ul", "v2-lista-tanka");
  for (const x of u.svi) {
    const li = el("li", "v2-naplata__unos");
    li.appendChild(document.createTextNode(x.opis));
    const meta = el("span", "v2-naplata__meta");
    if (x.datum) meta.appendChild(el("span", "", x.datum));
    meta.appendChild(el("span", "v2-mono", x.iznos));
    // „Obračunato" se PISE samo kad jeste; odsustvo oznake ne tvrdi suprotno
    // jer bi „nije obračunato" na nepoznatom stanju bilo tvrdnja bez pokrica.
    if (x.obracunato === true) meta.appendChild(el("span", "v2-znak", "obračunato"));
    li.appendChild(meta);
    ul.appendChild(li);
  }
  b.appendChild(ul);
  return b;
}

/* ── Tajmer ─────────────────────────────────────────────────────────────── */
function blokTajmera(d, predmetId, naziv, ciklus, osvezi) {
  const b = el("div", "v2-podblok");
  b.appendChild(el("h3", "v2-natkapa", "Merenje vremena"));

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;
  function javi(t, vrsta) {
    poruka.className = "v2-forma__poruka v2-forma__poruka--" + (vrsta || "greska");
    poruka.textContent = t;
    poruka.hidden = false;
  }

  // Nepoznato stanje NIJE „ne radi". Pokretanje drugog merenja preko
  // postojeceg izgubilo bi prvo, pa se „Pokreni" tada NE nudi.
  if (d.tajmerPao || !d.tajmer || !d.tajmer.poznato) {
    b.appendChild(el("p", "v2-celina__prazno",
      "Stanje merenja nije poznato. Osvežite Dosije pre nego što pokrenete "
      + "novo merenje — pokretanje preko merenja koje već teče izgubilo bi prvo."));
    return b;
  }

  const t = d.tajmer;
  if (t.radi) {
    const naOvom = t.predmetId === predmetId;
    const stanje = el("p", "v2-naplata__tajmer");
    stanje.appendChild(document.createTextNode(
      naOvom ? "Merenje teče na ovom predmetu."
             : "Merenje teče na drugom predmetu."));
    b.appendChild(stanje);
    if (t.opis) b.appendChild(el("p", "v2-celina__prazno", t.opis));

    if (naOvom) {
      const stop = el("button", "v2-dugme v2-dugme--glavno", "Zaustavi i evidentiraj");
      stop.type = "button";
      ciklus.slusaj(stop, "click", async () => {
        stop.disabled = true;
        stop.textContent = "Zaustavlja se…";
        try {
          const r = await posalji("/billing/timer/stop", {
            telo: { kreiraj_entry: true, tip: "satnica" },
            signal: ciklus.prekidac().signal,
          });
          if (ciklus.ugasen) return;
          const tr = r && r.trajanje_s !== undefined ? trajanje(r.trajanje_s) : "";
          ostavi("Merenje je zaustavljeno" + (tr ? " — " + tr : "")
                 + " i rad je evidentiran.", "uspeh");
          osvezi();
        } catch (err) {
          if (jePrekid(err) || ciklus.ugasen) return;
          stop.disabled = false;
          stop.textContent = "Zaustavi i evidentiraj";
          if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
          javi("Merenje nije zaustavljeno. " + porukaZaKorisnika(err)
             + " Merenje i dalje teče.");
        }
      });
      b.append(stop, poruka);
    } else {
      // Ne nudi se „zaustavi" za tudji predmet iz ovog Dosijea: advokat bi
      // zaustavio merenje koje ne vidi i izgubio bi kontekst gde je bilo.
      b.appendChild(el("p", "v2-celina__prazno",
        "Zaustavite ga u Kancelariji da biste ovde pokrenuli novo."));
      b.appendChild(poruka);
    }
    return b;
  }

  const red = el("div", "v2-radnja__red");
  const opis = el("input", "v2-polje-unos__kontrola");
  opis.type = "text";
  opis.id = "v2-dos-tajmer-opis";
  opis.placeholder = "Šta se radi (opciono)";
  opis.setAttribute("aria-label", "Opis rada koji se meri");
  const kreni = el("button", "v2-dugme", "Pokreni merenje");
  kreni.type = "button";
  red.append(opis, kreni);
  b.append(red, poruka);

  ciklus.slusaj(kreni, "click", async () => {
    kreni.disabled = true;
    kreni.textContent = "Pokreće se…";
    poruka.hidden = true;
    try {
      await posalji("/billing/timer/start", {
        telo: { predmet_id: predmetId, opis: opis.value.trim() || null },
        signal: ciklus.prekidac().signal,
      });
      if (ciklus.ugasen) return;
      ostavi("Merenje je pokrenuto na predmetu „" + naziv + "”.", "uspeh");
      osvezi();
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      kreni.disabled = false;
      kreni.textContent = "Pokreni merenje";
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      // 409 nije kvar: tacno jedno merenje po advokatu je pravilo, ne greska.
      if (err && err.status === 409) {
        javi("Merenje već teče — jedno merenje po advokatu. Zaustavite "
             + "postojeće pre nego što pokrenete novo.", "upozorenje");
        osvezi();
        return;
      }
      javi("Merenje nije pokrenuto. " + porukaZaKorisnika(err));
    }
  });
  return b;
}

/* ── Evidentiranje rada ─────────────────────────────────────────────────── */
function blokUnosa(predmetId, ciklus, osvezi) {
  const b = el("div", "v2-podblok");
  b.appendChild(el("h3", "v2-natkapa", "Evidentiraj rad"));

  const red = el("div", "v2-radnja__red");
  const opis = el("input", "v2-polje-unos__kontrola");
  opis.type = "text";
  opis.id = "v2-dos-rad-opis";
  opis.placeholder = "Opis rada";
  opis.setAttribute("aria-label", "Opis rada");
  const iznos = el("input", "v2-polje-unos__kontrola v2-polje-unos__kontrola--usko");
  iznos.type = "text";
  iznos.inputMode = "numeric";
  iznos.id = "v2-dos-rad-iznos";
  iznos.placeholder = "RSD";
  iznos.setAttribute("aria-label", "Iznos u dinarima");
  const dodaj = el("button", "v2-dugme", "Evidentiraj");
  dodaj.type = "button";
  red.append(opis, iznos, dodaj);

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;
  b.append(red, poruka);

  ciklus.slusaj(dodaj, "click", async () => {
    const unos = { predmetId, opis: opis.value, iznos: iznos.value };
    const g = nedostaciUnosa(unos);
    if (g.length) {
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = g.join(" ");
      poruka.hidden = false;
      return;
    }
    dodaj.disabled = true;
    dodaj.textContent = "Čuva se…";
    poruka.hidden = true;
    try {
      await posalji("/billing/entries", {
        telo: uTeloUnosa(unos), signal: ciklus.prekidac().signal,
      });
      if (ciklus.ugasen) return;
      opis.value = "";
      iznos.value = "";
      ostavi("Rad je evidentiran.", "uspeh");
      osvezi();
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      dodaj.disabled = false;
      dodaj.textContent = "Evidentiraj";
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      poruka.className = "v2-forma__poruka v2-forma__poruka--"
        + (err && err.vrsta === VRSTA.MREZA ? "upozorenje" : "greska");
      poruka.textContent = (err && err.vrsta === VRSTA.MREZA)
        // Mrezni kvar pri upisu NIJE dokaz da se nista nije upisalo.
        ? "Veza je prekinuta pre nego što je stigao odgovor. Rad je možda "
          + "evidentiran — osvežite Dosije pre nego što pokušate ponovo."
        : "Rad nije evidentiran. " + porukaZaKorisnika(err);
      poruka.hidden = false;
    }
  });
  return b;
}

/* ── Celina ─────────────────────────────────────────────────────────────── */
export function sadrzajNaplate(d, predmetId, naziv, ciklus, osvezi) {
  const okvir = document.createDocumentFragment();

  if (d.unosiPali) {
    // Prazan spisak bi ovde tvrdio da na predmetu nema evidentiranog rada.
    const p = el("div", "v2-poruka v2-poruka--greska");
    p.appendChild(el("p", "v2-poruka__naslov", "Evidencija rada nije učitana"));
    p.appendChild(el("p", "v2-poruka__telo",
      porukaZaKorisnika(d.unosiGreska)
      + " Ne zaključujte da na predmetu nema evidentiranog rada."));
    okvir.appendChild(p);
  } else if (d.unosi) {
    // Zbir se prikazuje SAMO kad ima sta da se zbroji. Cetiri nule iznad
    // recenice „jos nije evidentiran rad" nisu merenje nego sum, a
    // „Ukupno 0 RSD" se lako cita kao tvrdnja da klijent nista ne duguje —
    // a o dugu ovaj ekran ne zna nista.
    if (d.unosi.svi.length) okvir.appendChild(blokSazetka(d.unosi));
    okvir.appendChild(blokSpiska(d.unosi));
  }

  okvir.appendChild(blokTajmera(d, predmetId, naziv, ciklus, osvezi));
  okvir.appendChild(blokUnosa(predmetId, ciklus, osvezi));
  return okvir;
}
