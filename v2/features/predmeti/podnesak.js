/* Vindex V2 — Podnesak sudu (`/app-v2/predmeti/podnesak`), D5.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * PODNESAK NIJE ISTO STO I AKT
 *
 * „Napravi akt" pravi ugovor ili nacrt na osnovu opisa. Podnesak ide SUDU:
 * ima zaglavlje sa sudom, procesni tip (tuzba, zalba, prigovor) i posledicu
 * koja se meri rokovima. Zato ima svoj ekran, svoj katalog tipova i svoju
 * ogradu — a ne dodatnu opciju u padajucem spisku pored ugovora o radu.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * KATALOZI DOLAZE SA SERVERA. Tipovi (`/api/podnesak/types`) i sudovi
 * (`/api/courts`) se ne prepisuju u frontend: spisak koji ovde zastari nudio
 * bi tip koji server odbija, i to bi se videlo tek posle klika — posle
 * skupog poziva, ne pre njega.
 *
 * OGRADA JE JACA NEGO KOD AKTA. Nacrt podneska koji izgleda kao gotov
 * podnesak moze da bude predat sudu. Ograda stoji IZNAD teksta i imenuje
 * tacno ono sto sistem NIJE proverio: rokove, nadleznost, takse i spise.
 *
 * SUD JE OPCION ALI SE NE IZMISLJA. Ako sud nije izabran, zaglavlje ostaje
 * prazno i to se kaze — popuniti ga pretpostavkom znacilo bi podnesak
 * adresiran na sud koji advokat nije izabrao.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { dohvati, posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { idiNa, putanjaZa } from "../../platform/router.js";
import { uTipovePodneska, uSudove, nedostaciPodneska,
         MIN_OPIS_PODNESAK } from "../../domain/podnesak.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

function uPasuse(t, klasa) {
  const okvir = document.createDocumentFragment();
  for (const deo of String(t || "").replace(/\r\n/g, "\n").split(/\n{2,}/)) {
    const s = deo.trim();
    if (!s) continue;
    const p = el("p", klasa);
    s.split("\n").forEach((r, i) => {
      if (i) p.appendChild(document.createElement("br"));
      p.appendChild(document.createTextNode(r));
    });
    okvir.appendChild(p);
  }
  return okvir;
}

export function montirajPodnesak(kontejner, kontekst) {
  const ciklus = napraviCiklus();
  const zaceto = kontekst || {};
  let tipovi = [];
  let sudovi = [];

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--tekst");

  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Podnesak sudu");
  h1.id = "v2-naslov-podnesak";
  zaglavlje.appendChild(h1);
  zaglavlje.appendChild(el("p", "v2-podnaslov",
    "Nacrt procesnog podneska na osnovu vašeg opisa. Rezultat je polazni "
    + "tekst koji vi proveravate i potpisujete."));
  unutra.appendChild(zaglavlje);

  // ── Prekidac Akt / Podnesak ──
  const prekidac = el("nav", "v2-prekidac");
  prekidac.setAttribute("aria-label", "Šta pravite");
  const kaAktu = el("a", "v2-prekidac__stavka", "Akt");
  kaAktu.href = putanjaZa("predmeti", "akt");
  ciklus.slusaj(kaAktu, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("predmeti", "akt");
  });
  const ovde = el("span", "v2-prekidac__stavka v2-prekidac__stavka--aktivna", "Podnesak sudu");
  ovde.setAttribute("aria-current", "page");
  const kaSablonima = el("a", "v2-prekidac__stavka", "Šabloni");
  kaSablonima.href = putanjaZa("predmeti", "sabloni");
  ciklus.slusaj(kaSablonima, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("predmeti", "sabloni");
  });
  prekidac.append(kaAktu, ovde, kaSablonima);
  unutra.appendChild(prekidac);

  const forma = el("form", "v2-forma");
  forma.noValidate = true;

  // ── Tip podneska ──
  const omotTip = el("div", "v2-polje-unos");
  const labTip = el("label", "v2-polje-unos__labela", "Vrsta podneska");
  labTip.htmlFor = "v2-pod-tip";
  const tip = el("select", "v2-polje-unos__kontrola");
  tip.id = "v2-pod-tip";
  tip.disabled = true;
  const pomocTip = el("p", "v2-polje-unos__pomoc", "Katalog se učitava…");
  omotTip.append(labTip, tip, pomocTip);

  // ── Sud ──
  const omotSud = el("div", "v2-polje-unos");
  const labSud = el("label", "v2-polje-unos__labela", "Sud (opciono)");
  labSud.htmlFor = "v2-pod-sud";
  const sud = el("select", "v2-polje-unos__kontrola");
  sud.id = "v2-pod-sud";
  sud.disabled = true;
  const pomocSud = el("p", "v2-polje-unos__pomoc",
    "Ako ne izaberete sud, zaglavlje ostaje prazno — nadležnost se ne pretpostavlja.");
  omotSud.append(labSud, sud, pomocSud);

  // ── Opis ──
  const omotOpis = el("div", "v2-polje-unos");
  const labOpis = el("label", "v2-polje-unos__labela", "Opis slučaja");
  labOpis.htmlFor = "v2-pod-opis";
  const opis = el("textarea", "v2-polje-unos__kontrola");
  opis.id = "v2-pod-opis";
  opis.rows = 8;
  opis.maxLength = 5000;
  opis.value = zaceto.opis || "";
  const pomocOpis = el("p", "v2-polje-unos__pomoc",
    `Stranke, činjenice, datumi i zahtev. Najmanje ${MIN_OPIS_PODNESAK} znakova.`);
  pomocOpis.id = "v2-pod-opis-pomoc";
  opis.setAttribute("aria-describedby", pomocOpis.id);
  omotOpis.append(labOpis, opis, pomocOpis);

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;

  const radnje = el("div", "v2-forma__radnje");
  const dugme = el("button", "v2-dugme v2-dugme--glavno", "Napravi nacrt podneska");
  dugme.type = "submit";
  dugme.disabled = true;
  const nazad = el("a", "v2-dugme v2-dugme--tiho", "Nazad na Predmete");
  nazad.href = putanjaZa("predmeti");
  ciklus.slusaj(nazad, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("predmeti");
  });
  radnje.append(dugme, nazad);

  forma.append(omotTip, omotSud, omotOpis, poruka, radnje);
  unutra.appendChild(forma);

  const sadrzaj = el("div", "v2-akt");
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  unutra.appendChild(sadrzaj);
  kontejner.appendChild(unutra);
  document.title = "Podnesak sudu · Vindex";

  function javi(t, vrstaPoruke) {
    poruka.className = "v2-forma__poruka v2-forma__poruka--" + (vrstaPoruke || "greska");
    poruka.textContent = t;
    poruka.hidden = false;
  }

  // ── Katalozi ──
  (async () => {
    const p = ciklus.prekidac();
    const [t, s] = await Promise.allSettled([
      dohvati("/api/podnesak/types", { signal: p.signal }),
      dohvati("/api/courts", { signal: p.signal }),
    ]);
    for (const x of [t, s]) {
      if (x.status === "rejected" && jePrekid(x.reason)) return;
    }
    if (ciklus.ugasen) return;

    if (t.status === "rejected") {
      if (t.reason && t.reason.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      pomocTip.textContent = "";
      // Bez kataloga se podnesak NE moze naruciti — i to se kaze, umesto da
      // se ponudi prazan spisak koji izgleda kao „nema takvih podnesaka".
      javi("Katalog vrsta podnesaka nije učitan. " + porukaZaKorisnika(t.reason)
         + " Bez njega se nacrt ne može naručiti.", "greska");
      return;
    }
    tipovi = uTipovePodneska(t.value);
    if (!tipovi.length) {
      pomocTip.textContent = "";
      javi("Server trenutno ne nudi nijednu vrstu podneska.", "upozorenje");
      return;
    }
    for (const x of tipovi) {
      const o = document.createElement("option");
      o.value = x.tip;
      o.textContent = x.naziv;
      tip.appendChild(o);
    }
    if (zaceto.tip && tipovi.some(x => x.tip === zaceto.tip)) tip.value = zaceto.tip;
    tip.disabled = false;
    dugme.disabled = false;
    pomocTip.textContent = `${tipovi.length} vrsta podnesaka.`;

    // Sudovi su DOPUNA: bez njih se podnesak i dalje moze naruciti, samo bez
    // zaglavlja. Zato njihov pad ne blokira dugme.
    const prazna = document.createElement("option");
    prazna.value = "";
    prazna.textContent = "— bez zaglavlja suda —";
    sud.appendChild(prazna);
    if (s.status === "rejected") {
      pomocSud.textContent = "Katalog sudova nije učitan — zaglavlje suda "
        + "ostaje prazno. Ovo ne znači da sud ne postoji.";
      sud.disabled = false;
      return;
    }
    sudovi = uSudove(s.value);
    for (const g of sudovi) {
      const grupa = document.createElement("optgroup");
      grupa.label = g.grupa;
      for (const x of g.sudovi) {
        const o = document.createElement("option");
        o.value = x.naziv;
        o.textContent = x.naziv;
        o.dataset.adresa = x.adresa;
        grupa.appendChild(o);
      }
      sud.appendChild(grupa);
    }
    sud.disabled = false;
    const ukupno = sudovi.reduce((n, g) => n + g.sudovi.length, 0);
    pomocSud.textContent = `${ukupno} sudova. Ako ne izaberete sud, zaglavlje `
      + "ostaje prazno — nadležnost se ne pretpostavlja.";
  })();

  let radi = false;
  ciklus.slusaj(forma, "submit", async (e) => {
    e.preventDefault();
    if (radi) return;

    const ulaz = { tip: tip.value, opis: opis.value };
    const g = nedostaciPodneska(ulaz);
    if (g.length) { javi(g.join(" ")); opis.focus(); return; }

    const izabraniSud = sud.selectedOptions && sud.selectedOptions[0];
    const telo = { tip: ulaz.tip, opis: opis.value.trim() };
    if (sud.value) {
      telo.sud_naziv = sud.value;
      const a = izabraniSud && izabraniSud.dataset ? izabraniSud.dataset.adresa : "";
      if (a) telo.sud_adresa = a;
    }

    radi = true;
    dugme.disabled = true;
    dugme.textContent = "Nacrt se izrađuje…";
    poruka.hidden = true;
    sadrzaj.setAttribute("aria-busy", "true");
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
      "Nacrt podneska se izrađuje. Ovo traje duže nego obično jer se tekst "
      + "proverava u odnosu na propise."));

    let d;
    try {
      d = await posalji("/api/podnesak",
                        { telo, signal: ciklus.prekidac().signal });
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      radi = false;
      dugme.disabled = false;
      dugme.textContent = "Napravi nacrt podneska";
      sadrzaj.setAttribute("aria-busy", "false");
      sadrzaj.replaceChildren();
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      if (err && err.vrsta === VRSTA.ZABRANJENO) {
        javi("Vaš plan ne uključuje izradu podnesaka.", "upozorenje");
        return;
      }
      if (err && err.status === 429) {
        javi("Dostigli ste granicu broja podnesaka za ovaj minut. "
           + "Sačekajte i pokušajte ponovo — ovo nije kvar.", "upozorenje");
        return;
      }
      javi("Nacrt podneska nije izrađen. " + porukaZaKorisnika(err));
      return;
    }
    if (ciklus.ugasen) return;

    radi = false;
    dugme.disabled = false;
    dugme.textContent = "Napravi nacrt podneska";
    sadrzaj.setAttribute("aria-busy", "false");

    const tekst = String((d && (d.odgovor || d.tekst)) || "").trim();
    if (!tekst) {
      sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
        "Server je odgovorio, ali nacrt nije stigao u očekivanom obliku. "
        + "Ovo ne znači da podnesak nije potreban."));
      return;
    }

    const okvir = document.createDocumentFragment();

    // Ograda IZNAD teksta i jaca nego kod akta: ovaj tekst moze zavrsiti
    // pred sudom. Imenuje se TACNO ono sto sistem nije proverio.
    const og = el("div", "v2-ograda v2-ograda--nacrt");
    og.setAttribute("role", "alert");
    og.appendChild(el("p", "v2-ograda__naslov", "Ovo je nacrt, ne podnesak spreman za predaju"));
    og.appendChild(el("p", "v2-ograda__telo",
      "Sistem NIJE proverio: rok za podnošenje, stvarnu i mesnu nadležnost, "
      + "sudske takse, ni spise ovog predmeta. Proverite stranke, datume, "
      + "iznose i pravni osnov, i potpišite tek posle toga."));
    okvir.appendChild(og);

    const sek = el("section", "v2-akt__telo");
    const izabran = tipovi.find(x => x.tip === tip.value);
    sek.appendChild(el("h2", "v2-natkapa",
      (d && d.naziv) || (izabran && izabran.naziv) || "Nacrt podneska"));
    if (telo.sud_naziv) {
      sek.appendChild(el("p", "v2-podnesak__sud", telo.sud_naziv));
    } else {
      sek.appendChild(el("p", "v2-podnesak__sud v2-podnesak__sud--prazan",
        "Sud nije izabran — zaglavlje morate popuniti sami."));
    }
    sek.appendChild(uPasuse(tekst, "v2-znanje__pasus"));
    okvir.appendChild(sek);

    sadrzaj.replaceChildren(okvir);
    sadrzaj.focus();
  });

  ciklus.kontekst = () => ({ tip: tip.value, opis: opis.value });

  return ciklus;
}
