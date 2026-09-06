/* Vindex V2 — sabloni dokumenata (`/app-v2/predmeti/sabloni`), D4.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * OVDE SE POPUNJAVA OBRAZAC, NE OPISUJE SLUCAJ
 *
 * Akt i Podnesak polaze od slobodnog opisa. Sablon polazi od IMENOVANIH
 * polja koja server propisuje po sablonu: ime tuzitelja, adresa tuzenog,
 * vrednost spora. To je druga vrsta posla i zato je treci ekran, a ne treca
 * opcija u istom padajucem spisku.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * NEPOPUNJENO POLJE ULAZI U DOKUMENT KAO VIDLJIVA RUPA. Backend na mesto
 * praznog polja upisuje „[POLJE — NIJE UNETO]" i taj tekst ostaje u
 * dokumentu. To je namerno — bolje vidljiva rupa nego izmisljen podatak — ali
 * advokat to mora znati PRE nego sto potrosi poziv. Zato ekran nabraja
 * nepopunjena polja pre generisanja, po nazivu.
 *
 * CUVANJE IDE U NAPOMENE PREDMETA. `/sacuvaj` upisuje u `predmet_beleske`,
 * pa se sacuvan dokument pojavljuje u Dosijeu medju napomenama. Ekran to
 * KAZE, da advokat zna gde da ga trazi.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { dohvati, posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { ostavi } from "../../platform/obavestenje.js";
import { idiNa, putanjaZa } from "../../platform/router.js";
import { uSablone, nazivPolja, jeDatum, jeIznos, nepopunjena,
         nedostaciGenerisanja, nedostaciCuvanja } from "../../domain/sabloni.js";

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

export function montirajSablone(kontejner, kontekst) {
  const ciklus = napraviCiklus();
  const zaceto = kontekst || {};
  let sabloni = [];
  let predmeti = [];
  let unosi = new Map();
  let tekuciTekst = "";

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--tekst");

  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Šabloni");
  h1.id = "v2-naslov-sabloni";
  zaglavlje.appendChild(h1);
  zaglavlje.appendChild(el("p", "v2-podnaslov",
    "Dokument iz obrasca: popunite imenovana polja koja šablon traži. "
    + "Prazno polje ostaje u dokumentu kao vidljiva rupa, ne izmišlja se."));
  unutra.appendChild(zaglavlje);

  const prekidac = el("nav", "v2-prekidac");
  prekidac.setAttribute("aria-label", "Šta pravite");
  const kaAktu = el("a", "v2-prekidac__stavka", "Akt");
  kaAktu.href = putanjaZa("predmeti", "akt");
  ciklus.slusaj(kaAktu, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("predmeti", "akt");
  });
  const kaPodnesku = el("a", "v2-prekidac__stavka", "Podnesak sudu");
  kaPodnesku.href = putanjaZa("predmeti", "podnesak");
  ciklus.slusaj(kaPodnesku, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("predmeti", "podnesak");
  });
  const ovde = el("span", "v2-prekidac__stavka v2-prekidac__stavka--aktivna", "Šabloni");
  ovde.setAttribute("aria-current", "page");
  prekidac.append(kaAktu, kaPodnesku, ovde);
  unutra.appendChild(prekidac);

  const forma = el("form", "v2-forma");
  forma.noValidate = true;

  const omotSablon = el("div", "v2-polje-unos");
  const labSablon = el("label", "v2-polje-unos__labela", "Šablon");
  labSablon.htmlFor = "v2-sab-izbor";
  const izbor = el("select", "v2-polje-unos__kontrola");
  izbor.id = "v2-sab-izbor";
  izbor.disabled = true;
  const pomocSablon = el("p", "v2-polje-unos__pomoc", "Katalog se učitava…");
  omotSablon.append(labSablon, izbor, pomocSablon);

  const polja = el("div", "v2-sablon__polja");

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;

  const radnje = el("div", "v2-forma__radnje");
  const dugme = el("button", "v2-dugme v2-dugme--glavno", "Napravi dokument");
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

  forma.append(omotSablon, polja, poruka, radnje);
  unutra.appendChild(forma);

  const sadrzaj = el("div", "v2-akt");
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  unutra.appendChild(sadrzaj);
  kontejner.appendChild(unutra);
  document.title = "Šabloni · Vindex";

  function javi(t, vrstaPoruke) {
    poruka.className = "v2-forma__poruka v2-forma__poruka--" + (vrstaPoruke || "greska");
    poruka.textContent = t;
    poruka.hidden = false;
  }

  function izabrani() {
    return sabloni.find(s => s.id === izbor.value) || null;
  }

  /** Obrazac se gradi IZ SABLONA: polja propisuje server, ne ovaj fajl. */
  function iscrtajPolja() {
    const s = izabrani();
    unosi = new Map();
    polja.replaceChildren();
    if (!s) return;

    if (s.opis) polja.appendChild(el("p", "v2-polje-unos__pomoc", s.opis));

    if (!s.polja.length) {
      polja.appendChild(el("p", "v2-celina__prazno",
        "Ovaj šablon ne traži dodatna polja."));
      return;
    }

    for (const k of s.polja) {
      const omot = el("div", "v2-polje-unos");
      const lab = el("label", "v2-polje-unos__labela", nazivPolja(k));
      lab.htmlFor = "v2-sab-p-" + k;
      const u = el("input", "v2-polje-unos__kontrola");
      u.id = "v2-sab-p-" + k;
      u.name = k;
      if (jeDatum(k)) {
        u.type = "date";
      } else if (jeIznos(k)) {
        u.type = "text";
        u.inputMode = "numeric";
      } else {
        u.type = "text";
      }
      const prethodno = (zaceto.polja || {})[k];
      if (prethodno) u.value = prethodno;
      unosi.set(k, u);
      omot.append(lab, u);
      polja.appendChild(omot);
    }
  }

  function vrednosti() {
    const v = {};
    for (const [k, u] of unosi) v[k] = u.value.trim();
    return v;
  }

  // ── Katalozi ──
  (async () => {
    const p = ciklus.prekidac();
    const [s, pr] = await Promise.allSettled([
      dohvati("/api/doc-templates/lista", { signal: p.signal }),
      dohvati("/api/predmeti", { upit: { view: "summary", limit: 200 }, signal: p.signal }),
    ]);
    for (const x of [s, pr]) {
      if (x.status === "rejected" && jePrekid(x.reason)) return;
    }
    if (ciklus.ugasen) return;

    if (s.status === "rejected") {
      if (s.reason && s.reason.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      pomocSablon.textContent = "";
      javi("Katalog šablona nije učitan. " + porukaZaKorisnika(s.reason)
         + " Bez njega se dokument ne može napraviti.", "greska");
      return;
    }
    sabloni = uSablone(s.value);
    if (!sabloni.length) {
      pomocSablon.textContent = "";
      javi("Server trenutno ne nudi nijedan šablon.", "upozorenje");
      return;
    }
    for (const x of sabloni) {
      const o = document.createElement("option");
      o.value = x.id;
      o.textContent = x.naziv;
      izbor.appendChild(o);
    }
    if (zaceto.sablonId && sabloni.some(x => x.id === zaceto.sablonId)) {
      izbor.value = zaceto.sablonId;
    }
    izbor.disabled = false;
    dugme.disabled = false;
    pomocSablon.textContent = `${sabloni.length} šablona.`;
    iscrtajPolja();

    // Predmeti su DOPUNA: potrebni su samo za cuvanje, ne za generisanje.
    predmeti = pr.status === "fulfilled" ? ((pr.value && pr.value.predmeti) || []) : [];
  })();

  ciklus.slusaj(izbor, "change", () => {
    iscrtajPolja();
    poruka.hidden = true;
  });

  /* ── Cuvanje u predmet ────────────────────────────────────────────────── */
  function kontrolaCuvanja(naslov) {
    const omot = el("div", "v2-sablon__cuvanje");
    const otvori = el("button", "v2-dugme", "Sačuvaj uz predmet");
    otvori.type = "button";
    omot.appendChild(otvori);

    ciklus.slusaj(otvori, "click", () => {
      if (omot.querySelector(".v2-forma")) return;
      otvori.hidden = true;

      const f = el("form", "v2-forma");
      f.noValidate = true;

      const omotP = el("div", "v2-polje-unos");
      const labP = el("label", "v2-polje-unos__labela", "Predmet");
      labP.htmlFor = "v2-sab-predmet";
      const sel = el("select", "v2-polje-unos__kontrola");
      sel.id = "v2-sab-predmet";
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
      omotP.append(labP, sel);

      const omotN = el("div", "v2-polje-unos");
      const labN = el("label", "v2-polje-unos__labela", "Naziv dokumenta");
      labN.htmlFor = "v2-sab-naziv";
      const nazivU = el("input", "v2-polje-unos__kontrola");
      nazivU.id = "v2-sab-naziv";
      nazivU.type = "text";
      nazivU.maxLength = 200;
      nazivU.value = naslov;
      omotN.append(labN, nazivU);

      // Advokat mora znati GDE dokument zavrsava.
      const gde = el("p", "v2-polje-unos__pomoc",
        "Dokument se čuva kao napomena uz predmet i vidljiv je u Dosijeu, "
        + "u odeljku Beleške.");

      const p2 = el("div", "v2-forma__poruka");
      p2.setAttribute("role", "alert");
      p2.hidden = true;

      const r2 = el("div", "v2-forma__radnje");
      const cuvaj = el("button", "v2-dugme v2-dugme--glavno", "Sačuvaj");
      cuvaj.type = "submit";
      const odustani = el("button", "v2-dugme v2-dugme--tiho", "Odustani");
      odustani.type = "button";
      r2.append(cuvaj, odustani);

      f.append(omotP, omotN, gde, p2, r2);
      omot.appendChild(f);
      sel.focus();

      ciklus.slusaj(odustani, "click", () => {
        f.remove(); otvori.hidden = false; otvori.focus();
      });

      ciklus.slusaj(f, "submit", async (e) => {
        e.preventDefault();
        const ulaz = { predmetId: sel.value, naziv: nazivU.value, sadrzaj: tekuciTekst };
        const g = nedostaciCuvanja(ulaz);
        if (g.length) {
          p2.className = "v2-forma__poruka v2-forma__poruka--greska";
          p2.textContent = g.join(" ");
          p2.hidden = false;
          return;
        }
        cuvaj.disabled = true;
        cuvaj.textContent = "Čuva se…";
        p2.hidden = true;
        try {
          await posalji("/api/doc-templates/sacuvaj", {
            telo: { predmet_id: ulaz.predmetId, naziv: ulaz.naziv.trim(),
                    sadrzaj: tekuciTekst, sablon_id: izbor.value },
            signal: ciklus.prekidac().signal,
          });
          if (ciklus.ugasen) return;
          ostavi("Dokument je sačuvan uz predmet, u Beleškama.", "uspeh");
          f.remove();
          otvori.hidden = false;
        } catch (err) {
          if (jePrekid(err) || ciklus.ugasen) return;
          cuvaj.disabled = false;
          cuvaj.textContent = "Sačuvaj";
          if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
          p2.className = "v2-forma__poruka v2-forma__poruka--"
            + (err && err.vrsta === VRSTA.MREZA ? "upozorenje" : "greska");
          p2.textContent = (err && err.vrsta === VRSTA.MREZA)
            // Mrezni kvar pri upisu NIJE dokaz da se nista nije upisalo.
            ? "Veza je prekinuta pre nego što je stigao odgovor. Dokument je "
              + "možda sačuvan — proverite Beleške predmeta pre nego što "
              + "pokušate ponovo."
            : "Dokument nije sačuvan. " + porukaZaKorisnika(err);
          p2.hidden = false;
        }
      });
    });

    return omot;
  }

  let radi = false;
  ciklus.slusaj(forma, "submit", async (e) => {
    e.preventDefault();
    if (radi) return;
    const s = izabrani();
    const g = nedostaciGenerisanja({ sablonId: izbor.value });
    if (g.length) { javi(g.join(" ")); return; }

    const v = vrednosti();
    const rupe = nepopunjena(s, v);

    radi = true;
    dugme.disabled = true;
    dugme.textContent = "Dokument se izrađuje…";
    poruka.hidden = true;
    sadrzaj.setAttribute("aria-busy", "true");
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
      "Dokument se izrađuje. Ovo može potrajati nekoliko sekundi."));

    let d;
    try {
      d = await posalji("/api/doc-templates/generisi", {
        telo: { sablon_id: izbor.value, polja: v },
        signal: ciklus.prekidac().signal,
      });
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      radi = false;
      dugme.disabled = false;
      dugme.textContent = "Napravi dokument";
      sadrzaj.setAttribute("aria-busy", "false");
      sadrzaj.replaceChildren();
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      if (err && err.vrsta === VRSTA.ZABRANJENO) {
        javi("Vaš plan ne uključuje izradu dokumenata iz šablona.", "upozorenje");
        return;
      }
      if (err && err.status === 429) {
        javi("Dostigli ste granicu izrade dokumenata za ovaj minut. "
           + "Sačekajte i pokušajte ponovo — ovo nije kvar.", "upozorenje");
        return;
      }
      if (err && err.status === 502) {
        javi("Izrada dokumenta trenutno nije dostupna. Pokušajte kasnije — "
           + "ovo ne znači da je šablon neispravan.", "upozorenje");
        return;
      }
      javi("Dokument nije izrađen. " + porukaZaKorisnika(err));
      return;
    }
    if (ciklus.ugasen) return;

    radi = false;
    dugme.disabled = false;
    dugme.textContent = "Napravi dokument";
    sadrzaj.setAttribute("aria-busy", "false");

    tekuciTekst = String((d && (d.sadrzaj || d.tekst)) || "").trim();
    if (!tekuciTekst) {
      sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
        "Server je odgovorio, ali dokument nije stigao u očekivanom obliku."));
      return;
    }

    const okvir = document.createDocumentFragment();

    const og = el("div", "v2-ograda v2-ograda--nacrt");
    og.setAttribute("role", "alert");
    og.appendChild(el("p", "v2-ograda__naslov", "Ovo je nacrt, ne gotov dokument"));
    og.appendChild(el("p", "v2-ograda__telo",
      "Proverite stranke, datume, iznose i pravni osnov pre upotrebe. "
      + "Dokument nije proveren u odnosu na spise predmeta."));
    okvir.appendChild(og);

    // Rupe se imenuju NAKON generisanja takodje — advokat gleda tekst i mora
    // odmah znati sta u njemu nedostaje.
    if (rupe.length) {
      const r = el("p", "v2-poruka v2-poruka--upozorenje",
        "U dokumentu su ostale vidljive rupe jer ova polja nisu popunjena: "
        + rupe.join(", ") + ".");
      okvir.appendChild(r);
    }

    const sek = el("section", "v2-akt__telo");
    sek.appendChild(el("h2", "v2-natkapa",
      (d && d.naziv) || (s && s.naziv) || "Dokument"));
    sek.appendChild(uPasuse(tekuciTekst, "v2-znanje__pasus"));
    okvir.appendChild(sek);

    okvir.appendChild(kontrolaCuvanja((d && d.naziv) || (s && s.naziv) || "Dokument"));

    sadrzaj.replaceChildren(okvir);
    sadrzaj.focus();
  });

  // Nepopunjena polja se najavljuju PRE poziva, dok se jos moze ispraviti.
  ciklus.slusaj(polja, "input", () => {
    const s = izabrani();
    if (!s) return;
    const rupe = nepopunjena(s, vrednosti());
    if (!rupe.length) { poruka.hidden = true; return; }
    javi("Nepopunjeno: " + rupe.join(", ")
       + ". Ova polja će u dokumentu ostati kao vidljive rupe.", "upozorenje");
  });

  ciklus.kontekst = () => ({ sablonId: izbor.value, polja: vrednosti() });

  return ciklus;
}
