/* Vindex V2 — Napravi akt (nacrt podneska ili ugovora).
 *
 * RADNJA u prostoru PREDMETI (`/app-v2/predmeti/akt`). Nacrt je skoro uvek
 * posao NAD predmetom, pa stoji uz registar predmeta, a ne u zasebnom
 * „modulu za dokumente". Predmet je opcion: advokat pravi ugovor i pre nego
 * sto predmet postoji.
 *
 * VRSTE AKATA DOLAZE SA SERVERA (`/api/nacrt/types`), NE IZ KODA.
 * Katalog se menja bez izmene frontenda, a spisak koji bi ovde bio prepisan
 * ubrzo bi nudio vrstu koju server vise ne zna — kontrolu koja pada tek
 * posle klika.
 *
 * NACRT NIJE AKT. Rezultat je polazni tekst koji advokat mora da proceni,
 * dopuni i potpise. To ekran KAZE, i to iznad teksta, jer nacrt koji izgleda
 * kao gotov podnesak je najskuplja moguca greska ovog ekrana.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { dohvati, posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { idiNa, putanjaZa } from "../../platform/router.js";

const NAJMANJE_OPIS = 10;

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

export function montirajAkt(kontejner, kontekst) {
  const ciklus = napraviCiklus();
  const zaceto = kontekst || {};

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--predmet");

  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Napravi akt");
  h1.id = "v2-naslov-akt";
  zaglavlje.appendChild(h1);
  zaglavlje.appendChild(el("p", "v2-podnaslov",
    "Nacrt podneska ili ugovora na osnovu vašeg opisa. Rezultat je polazni tekst, ne gotov akt."));
  unutra.appendChild(zaglavlje);

  const forma = el("form", "v2-forma");
  forma.noValidate = true;

  // ── Vrsta akta ──
  const omotVrsta = el("div", "v2-polje-unos");
  const labVrsta = el("label", "v2-polje-unos__labela", "Vrsta akta");
  labVrsta.htmlFor = "v2-akt-vrsta";
  const vrsta = el("select", "v2-polje-unos__kontrola");
  vrsta.id = "v2-akt-vrsta";
  vrsta.name = "vrsta";
  vrsta.disabled = true;
  const pomocVrsta = el("p", "v2-polje-unos__pomoc", "Katalog se učitava…");
  omotVrsta.append(labVrsta, vrsta, pomocVrsta);

  // ── Opis ──
  const omotOpis = el("div", "v2-polje-unos");
  const labOpis = el("label", "v2-polje-unos__labela", "Opis");
  labOpis.htmlFor = "v2-akt-opis";
  const opis = el("textarea", "v2-polje-unos__kontrola");
  opis.id = "v2-akt-opis";
  opis.name = "opis";
  opis.rows = 6;
  opis.maxLength = 5000;
  opis.value = zaceto.opis || "";
  const pomocOpis = el("p", "v2-polje-unos__pomoc", "");
  pomocOpis.id = "v2-akt-opis-pomoc";
  opis.setAttribute("aria-describedby", pomocOpis.id);
  omotOpis.append(labOpis, opis, pomocOpis);

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;

  const radnje = el("div", "v2-forma__radnje");
  const dugme = el("button", "v2-dugme v2-dugme--glavno", "Napravi nacrt");
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

  forma.append(omotVrsta, omotOpis, poruka, radnje);
  unutra.appendChild(forma);

  const sadrzaj = el("div", "v2-akt");
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  unutra.appendChild(sadrzaj);
  kontejner.appendChild(unutra);
  document.title = "Napravi akt · Vindex";

  let tipovi = [];

  function javi(tekst, vrstaPoruke) {
    poruka.className = "v2-forma__poruka v2-forma__poruka--" + (vrstaPoruke || "greska");
    poruka.textContent = tekst;
    poruka.hidden = false;
  }

  function osveziPomoc() {
    const t = tipovi.find(x => x.vrsta === vrsta.value);
    pomocOpis.textContent = (t && t.opis_hint)
      ? t.opis_hint
      : "Opišite strane, predmet i bitne uslove. Najmanje 10 znakova.";
  }

  // ── Katalog vrsta sa servera ──
  (async () => {
    const prekidac = ciklus.prekidac();
    let d;
    try {
      d = await dohvati("/api/nacrt/types", { signal: prekidac.signal });
    } catch (e) {
      if (jePrekid(e) || ciklus.ugasen) return;
      if (e && e.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      pomocVrsta.textContent = "";
      javi("Katalog vrsta akata nije učitan. " + porukaZaKorisnika(e)
         + " Bez njega se nacrt ne može naručiti.", "greska");
      return;
    }
    if (ciklus.ugasen) return;

    tipovi = Array.isArray(d && d.tipovi) ? d.tipovi : [];
    if (!tipovi.length) {
      pomocVrsta.textContent = "";
      javi("Server trenutno ne nudi nijednu vrstu akta.", "upozorenje");
      return;
    }
    for (const t of tipovi) {
      const o = document.createElement("option");
      o.value = t.vrsta;
      o.textContent = t.label || t.vrsta;
      vrsta.appendChild(o);
    }
    if (zaceto.vrsta && tipovi.some(t => t.vrsta === zaceto.vrsta)) vrsta.value = zaceto.vrsta;
    vrsta.disabled = false;
    dugme.disabled = false;
    pomocVrsta.textContent = `${tipovi.length} vrsta akata.`;
    osveziPomoc();
  })();

  ciklus.slusaj(vrsta, "change", osveziPomoc);

  let radi = false;
  ciklus.slusaj(forma, "submit", async (e) => {
    e.preventDefault();
    if (radi || !vrsta.value) return;
    const o = opis.value.trim();
    if (o.length < NAJMANJE_OPIS) {
      javi(`Opis mora imati najmanje ${NAJMANJE_OPIS} znakova; uneto je ${o.length}.`);
      opis.focus();
      return;
    }

    radi = true;
    dugme.disabled = true;
    dugme.textContent = "Nacrt se izrađuje…";
    poruka.hidden = true;
    sadrzaj.setAttribute("aria-busy", "true");
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
      "Nacrt se izrađuje. Ovo može potrajati nekoliko sekundi."));

    const prekidac = ciklus.prekidac();
    let d;
    try {
      d = await posalji("/api/nacrt", { telo: { vrsta: vrsta.value, opis: o }, signal: prekidac.signal });
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      radi = false;
      dugme.disabled = false;
      dugme.textContent = "Napravi nacrt";
      sadrzaj.setAttribute("aria-busy", "false");
      sadrzaj.replaceChildren();
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      javi("Nacrt nije izrađen. " + porukaZaKorisnika(err));
      return;
    }
    if (ciklus.ugasen) return;

    radi = false;
    dugme.disabled = false;
    dugme.textContent = "Napravi nacrt";
    sadrzaj.setAttribute("aria-busy", "false");

    const tekst = String((d && (d.odgovor || d.nacrt || d.tekst)) || "").trim();
    if (!tekst) {
      sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
        "Server je odgovorio, ali nacrt nije stigao u očekivanom obliku. "
        + "Ovo nije nacrt da akt nije potreban."));
      return;
    }

    const okvir = document.createDocumentFragment();

    // Ograda IZNAD teksta. Nacrt koji izgleda kao gotov podnesak je
    // najskuplja greska koju ovaj ekran moze da napravi.
    const og = el("div", "v2-ograda v2-ograda--nacrt");
    og.setAttribute("role", "alert");
    og.appendChild(el("p", "v2-ograda__naslov", "Ovo je nacrt, ne gotov akt"));
    og.appendChild(el("p", "v2-ograda__telo",
      "Proverite strane, rokove, iznose i pravni osnov pre upotrebe. Nacrt nije "
      + "proveren u odnosu na spise predmeta niti na važeću sudsku praksu."));
    okvir.appendChild(og);

    const sek = el("section", "v2-akt__telo");
    const izabrana = tipovi.find(x => x.vrsta === vrsta.value);
    sek.appendChild(el("h2", "v2-natkapa", (izabrana && izabrana.label) || "Nacrt"));
    sek.appendChild(uPasuse(tekst, "v2-znanje__pasus"));
    okvir.appendChild(sek);

    sadrzaj.replaceChildren(okvir);
    sadrzaj.focus();
  });

  ciklus.kontekst = () => ({ vrsta: vrsta.value, opis: opis.value });

  return ciklus;
}
