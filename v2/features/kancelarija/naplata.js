/* Vindex V2 — NAPLATA: tajmer, evidentiranje rada, fakture (F4/F5).
 *
 * Zivi u prostoru KANCELARIJA. Svaki unos se vezuje za predmet, ali naplata
 * je posao kancelarije, ne pravni rad nad predmetom — Dosije zadrzava svojih
 * pet zakljucanih celina i ne dobija sestu zbog naplate.
 *
 * TAJMER MERI STVARNO VREME, NE PROCENU. Zato se stanje uvek cita sa servera
 * (`/billing/timer/aktivan`), nikad iz lokalne promenljive: tajmer pokrenut u
 * jednom pretrazivacu mora biti vidljiv u drugom, a advokat koji zatvori
 * karticu ne sme da izgubi merenje.
 *
 * NEPOZNATO STANJE TAJMERA NIJE „NE RADI". Ako poziv padne, ekran to kaze i
 * NE nudi „Pokreni" — pokretanje drugog tajmera preko postojeceg bi izgubilo
 * prvo merenje.
 */

import { dohvati, posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { ostavi } from "../../platform/obavestenje.js";
import { uUnose, uTajmer, uFakture, dinar, trajanje,
         nedostaciUnosa, uTeloUnosa } from "../../domain/naplata.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

/** Ucitava sve sto naplati treba; svaki izvor pada odvojeno. */
export async function ucitajNaplatu({ signal } = {}) {
  const [t, f, p] = await Promise.allSettled([
    dohvati("/billing/timer/aktivan", { signal }),
    dohvati("/billing/faktura", { signal }),
    dohvati("/api/predmeti", { upit: { view: "summary", limit: 200 }, signal }),
  ]);
  for (const x of [t, f, p]) {
    if (x.status === "rejected" && jePrekid(x.reason)) throw x.reason;
  }
  return {
    tajmer: uTajmer(t.status === "fulfilled" ? t.value : null),
    tajmerPao: t.status === "rejected",
    fakture: f.status === "fulfilled" ? uFakture(f.value) : [],
    faktureP: f.status === "rejected",
    predmeti: p.status === "fulfilled" ? ((p.value && p.value.predmeti) || []) : [],
    predmetiP: p.status === "rejected",
  };
}

/* ── Biracz predmeta ────────────────────────────────────────────────────── */
function biracPredmeta(id, predmeti) {
  const omot = el("div", "v2-polje-unos");
  const lab = el("label", "v2-polje-unos__labela", "Predmet");
  lab.htmlFor = id;
  const sel = el("select", "v2-polje-unos__kontrola");
  sel.id = id;
  const prazna = document.createElement("option");
  prazna.value = "";
  prazna.textContent = predmeti.length ? "Izaberite predmet" : "Nema predmeta";
  sel.appendChild(prazna);
  for (const p of predmeti) {
    if (!p.id) continue;
    const o = document.createElement("option");
    o.value = p.id;
    o.textContent = String(p.naziv || "Predmet bez naziva");
    sel.appendChild(o);
  }
  sel.disabled = !predmeti.length;
  omot.append(lab, sel);
  return { omot, sel };
}

/* ── Tajmer ─────────────────────────────────────────────────────────────── */
function blokTajmera(d, ciklus, osvezi) {
  const b = el("div", "v2-podblok");
  b.appendChild(el("h3", "v2-natkapa", "Tajmer"));

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;

  function javi(t, vrsta) {
    poruka.className = "v2-forma__poruka v2-forma__poruka--" + (vrsta || "greska");
    poruka.textContent = t;
    poruka.hidden = false;
  }

  if (d.tajmerPao || !d.tajmer.poznato) {
    // Nepoznato stanje NIJE „ne radi". Pokretanje drugog tajmera preko
    // postojeceg izgubilo bi prvo merenje, pa se „Pokreni" NE nudi.
    b.appendChild(el("p", "v2-celina__prazno",
      "Stanje tajmera nije poznato. Osvežite stranicu pre nego što pokrenete "
      + "novo merenje — pokretanje preko tajmera koji već radi izgubilo bi prvo."));
    return b;
  }

  if (d.tajmer.radi) {
    const red = el("div", "v2-radnja__red");
    const naziv = (d.predmeti.find(p => p.id === d.tajmer.predmetId) || {}).naziv;
    red.appendChild(el("span", "v2-tajmer__tece",
      "Merenje je u toku" + (naziv ? " — " + naziv : "")));
    const stani = el("button", "v2-dugme v2-dugme--glavno", "Zaustavi i evidentiraj");
    stani.type = "button";
    red.appendChild(stani);
    b.append(red, poruka);
    if (d.tajmer.opis) b.appendChild(el("p", "v2-celina__prazno", d.tajmer.opis));

    ciklus.slusaj(stani, "click", async () => {
      stani.disabled = true;
      stani.textContent = "Zaustavlja se…";
      try {
        const r = await posalji("/billing/timer/stop", {
          telo: { kreiraj_entry: true, tip: "satnica" },
          signal: ciklus.prekidac().signal,
        });
        if (ciklus.ugasen) return;
        const t = r && r.trajanje_s !== undefined ? trajanje(r.trajanje_s) : "";
        ostavi("Merenje je zaustavljeno" + (t ? " — " + t : "") + " i evidentirano.", "uspeh");
        osvezi();
      } catch (err) {
        if (jePrekid(err) || ciklus.ugasen) return;
        stani.disabled = false;
        stani.textContent = "Zaustavi i evidentiraj";
        if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
        javi("Merenje nije zaustavljeno. " + porukaZaKorisnika(err)
           + " Tajmer i dalje radi.");
      }
    });
    return b;
  }

  const bp = biracPredmeta("v2-tajmer-predmet", d.predmeti);
  const red = el("div", "v2-radnja__red");
  const opis = el("input", "v2-polje-unos__kontrola");
  opis.type = "text";
  opis.placeholder = "Na čemu radite (opciono)";
  opis.setAttribute("aria-label", "Opis rada");
  const kreni = el("button", "v2-dugme", "Pokreni merenje");
  kreni.type = "button";
  red.append(opis, kreni);
  b.append(bp.omot, red, poruka);

  ciklus.slusaj(kreni, "click", async () => {
    if (!bp.sel.value) { javi("Izaberite predmet pre pokretanja merenja."); bp.sel.focus(); return; }
    kreni.disabled = true;
    kreni.textContent = "Pokreće se…";
    try {
      await posalji("/billing/timer/start", {
        telo: { predmet_id: bp.sel.value, opis: opis.value.trim() || null },
        signal: ciklus.prekidac().signal,
      });
      if (ciklus.ugasen) return;
      ostavi("Merenje je pokrenuto.", "uspeh");
      osvezi();
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      kreni.disabled = false;
      kreni.textContent = "Pokreni merenje";
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      javi("Merenje nije pokrenuto. " + porukaZaKorisnika(err));
    }
  });
  return b;
}

/* ── Evidentiranje rada ─────────────────────────────────────────────────── */
function blokUnosa(d, ciklus, osvezi) {
  const b = el("div", "v2-podblok");
  b.appendChild(el("h3", "v2-natkapa", "Evidentiraj rad"));

  const bp = biracPredmeta("v2-rad-predmet", d.predmeti);
  const red = el("div", "v2-radnja__red");
  const opis = el("input", "v2-polje-unos__kontrola");
  opis.type = "text";
  opis.id = "v2-rad-opis";
  opis.placeholder = "Šta je urađeno";
  opis.maxLength = 400;
  opis.setAttribute("aria-label", "Opis rada");
  const iznos = el("input", "v2-polje-unos__kontrola v2-radnja__datum");
  iznos.type = "text";
  iznos.id = "v2-rad-iznos";
  iznos.inputMode = "decimal";
  iznos.placeholder = "Iznos (RSD)";
  iznos.setAttribute("aria-label", "Iznos u dinarima");
  const dodaj = el("button", "v2-dugme", "Evidentiraj");
  dodaj.type = "button";
  red.append(opis, iznos, dodaj);

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;
  b.append(bp.omot, red, poruka);

  // Spisak unosa za izabrani predmet — vidi se sta je vec evidentirano.
  const spisak = el("div", "v2-naplata__unosi");
  b.appendChild(spisak);

  async function osveziUnose() {
    if (!bp.sel.value) { spisak.replaceChildren(); return; }
    spisak.replaceChildren(el("p", "v2-celina__prazno", "Učitava se…"));
    try {
      const r = await dohvati("/billing/entries", {
        upit: { predmet_id: bp.sel.value }, signal: ciklus.prekidac().signal,
      });
      if (ciklus.ugasen) return;
      const u = uUnose(r);
      const okvir = document.createDocumentFragment();

      // Tri iznosa, tri imena, nijedan zbir (B2).
      const zbir = el("ul", "v2-naplata");
      for (const [naziv, vrednost, pitanje] of [
        ["Evidentiran rad", u.ukupno, "Koliko je ukupno uneto na ovom predmetu."],
        ["Još nije fakturisano", u.neobracunato, "Šta čeka da uđe u fakturu."],
        ["Obračunato", u.obracunato, "Šta je već ušlo u fakturu."],
      ]) {
        if (vrednost === null) continue;
        const li = el("li", "v2-naplata__red");
        li.appendChild(el("span", "v2-naplata__naziv", naziv));
        li.appendChild(el("span", "v2-naplata__iznos v2-mono", vrednost));
        li.appendChild(el("span", "v2-naplata__pitanje", pitanje));
        zbir.appendChild(li);
      }
      if (zbir.childNodes.length) okvir.appendChild(zbir);

      if (!u.svi.length) {
        okvir.appendChild(el("p", "v2-celina__prazno", "Za ovaj predmet nema evidentiranog rada."));
      } else {
        const ul = el("ul", "v2-lista-tanka");
        for (const x of u.svi) {
          const li = el("li");
          li.appendChild(document.createTextNode(x.opis));
          const meta = el("span", "v2-beleska__datum");
          meta.textContent = " — " + [x.datum, x.iznos,
            x.obracunato ? "fakturisano" : "nije fakturisano"].filter(Boolean).join(" · ");
          li.appendChild(meta);
          ul.appendChild(li);
        }
        okvir.appendChild(ul);
      }

      // Faktura se pravi SAMO od neobracunatog rada — nuditi vec fakturisan
      // unos znacilo bi ponuditi dvostruko naplacivanje istog posla.
      if (u.zaFakturu.length) {
        okvir.appendChild(dugmeFakture(bp.sel, u, d, ciklus, osvezi));
      }
      spisak.replaceChildren(okvir);
    } catch (e) {
      if (jePrekid(e) || ciklus.ugasen) return;
      spisak.replaceChildren(el("p", "v2-celina__prazno",
        "Evidentiran rad nije učitan. " + porukaZaKorisnika(e)
        + " Ovo ne znači da rada nema."));
    }
  }

  ciklus.slusaj(bp.sel, "change", osveziUnose);

  ciklus.slusaj(dodaj, "click", async () => {
    const unos = { predmetId: bp.sel.value, opis: opis.value, iznos: iznos.value };
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
      dodaj.disabled = false;
      dodaj.textContent = "Evidentiraj";
      await osveziUnose();
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      dodaj.disabled = false;
      dodaj.textContent = "Evidentiraj";
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      poruka.className = "v2-forma__poruka v2-forma__poruka--"
        + (err && err.vrsta === VRSTA.MREZA ? "upozorenje" : "greska");
      poruka.textContent = (err && err.vrsta === VRSTA.MREZA)
        ? "Veza je prekinuta pre nego što je stigao odgovor. Rad je možda evidentiran "
          + "— proverite spisak pre nego što pokušate ponovo."
        : "Rad nije evidentiran. " + porukaZaKorisnika(err);
      poruka.hidden = false;
    }
  });

  return b;
}

/* ── Izrada fakture ─────────────────────────────────────────────────────── */
function dugmeFakture(sel, u, d, ciklus, osvezi) {
  const omot = el("div", "v2-radnja");
  const naziv = (d.predmeti.find(p => p.id === sel.value) || {}).naziv || "";
  omot.appendChild(el("p", "v2-celina__prazno",
    `${u.zaFakturu.length} ${u.zaFakturu.length === 1 ? "stavka" : "stavki"} čeka fakturu `
    + `(${u.neobracunato || "—"}).`));

  const red = el("div", "v2-radnja__red");
  const klijent = el("input", "v2-polje-unos__kontrola");
  klijent.type = "text";
  klijent.placeholder = "Naziv klijenta za fakturu";
  klijent.setAttribute("aria-label", "Naziv klijenta za fakturu");
  const napravi = el("button", "v2-dugme v2-dugme--glavno", "Napravi fakturu");
  napravi.type = "button";
  red.append(klijent, napravi);

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;
  omot.append(red, poruka);

  ciklus.slusaj(napravi, "click", async () => {
    const kn = klijent.value.trim();
    if (!kn) {
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = "Naziv klijenta je obavezan na fakturi.";
      poruka.hidden = false;
      klijent.focus();
      return;
    }
    napravi.disabled = true;
    napravi.textContent = "Izrađuje se…";
    poruka.hidden = true;
    try {
      await posalji("/billing/faktura", {
        telo: {
          predmet_id: sel.value,
          entry_ids: u.zaFakturu.map(x => x.id),
          klijent_naziv: kn,
        },
        signal: ciklus.prekidac().signal,
      });
      if (ciklus.ugasen) return;
      ostavi("Faktura je napravljena.", "uspeh");
      osvezi();
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      napravi.disabled = false;
      napravi.textContent = "Napravi fakturu";
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      poruka.className = "v2-forma__poruka v2-forma__poruka--"
        + (err && err.vrsta === VRSTA.MREZA ? "upozorenje" : "greska");
      poruka.textContent = (err && err.vrsta === VRSTA.MREZA)
        ? "Veza je prekinuta pre nego što je stigao odgovor. Faktura je možda "
          + "napravljena — proverite spisak faktura pre nego što pokušate ponovo."
        : "Faktura nije napravljena. " + porukaZaKorisnika(err);
      poruka.hidden = false;
    }
  });
  return omot;
}

/* ── Spisak faktura ─────────────────────────────────────────────────────── */
function blokFaktura(d) {
  const b = el("div", "v2-podblok");
  b.appendChild(el("h3", "v2-natkapa", "Fakture"));
  if (d.faktureP) {
    b.appendChild(el("p", "v2-celina__prazno",
      "Spisak faktura nije učitan. Ovo ne znači da faktura nema."));
    return b;
  }
  if (!d.fakture.length) {
    b.appendChild(el("p", "v2-celina__prazno", "Još nema izdatih faktura."));
    return b;
  }
  const ul = el("ul", "v2-klijenti");
  for (const f of d.fakture.slice(0, 20)) {
    const li = el("li", "v2-klijenti__red");
    li.appendChild(el("span", "v2-klijenti__naziv", f.broj + (f.klijent ? " · " + f.klijent : "")));
    const meta = el("span", "v2-klijenti__meta");
    if (f.iznos) meta.appendChild(el("span", "v2-mono", f.iznos));
    if (f.datum) meta.appendChild(el("span", "", f.datum));
    // „placena" je jedina vrednost koja znaci da je novac stigao.
    meta.appendChild(el("span", "", f.placena ? "plaćena" : "nije plaćena"));
    li.appendChild(meta);
    ul.appendChild(li);
  }
  b.appendChild(ul);
  return b;
}

/** Sve zajedno — ubacuje se u celinu „Naplata" prostora Kancelarija. */
export function blokoviNaplate(d, ciklus, osvezi) {
  const okvir = document.createDocumentFragment();
  okvir.appendChild(blokTajmera(d, ciklus, osvezi));
  okvir.appendChild(blokUnosa(d, ciklus, osvezi));
  okvir.appendChild(blokFaktura(d));
  return okvir;
}
