/* Vindex V2 — finansije kancelarije (`/app-v2/kancelarija/finansije`), F6+F7.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * „KOLIKO MI DUGUJU" I „KOLIKO NISAM FAKTURISAO" NISU ISTO PITANJE
 *
 * Ovaj ekran ih drzi razdvojena i imenuje ih tako da se ne mogu pobrkati:
 *
 *   Nije fakturisano — moj rad koji nije usao ni u jednu fakturu. Klijent
 *                      ovo NE duguje; nije mu ni ispostavljeno.
 *   Nije naplaceno   — izdata faktura koja nije placena. OVO duguju.
 *   Nacrti faktura   — moj nedovrsen posao, ni potrazivanje ni prihod.
 *
 * Jedan zbirni broj „dugovanja" bio bi tvrdnja da klijenti duguju novac koji
 * nikada nije ni trazen.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * TRI IZVORA, `allSettled`. Stanje naplate, nefakturisan rad po predmetu i
 * godisnji izvestaj padaju odvojeno; pad jednog ne sme da isprazni ekran ni
 * da prikaze nulu tamo gde podatak nije stigao.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { dohvati } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { idiNa, putanjaZa, idiNaPutanju } from "../../platform/router.js";
import { uStanjeNaplate, uNefakturisano, uGodisnji } from "../../domain/finansije.js";

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

function nijeUcitano(sta, err) {
  const p = el("div", "v2-poruka v2-poruka--greska");
  p.appendChild(el("p", "v2-poruka__naslov", sta + " nije učitano"));
  p.appendChild(el("p", "v2-poruka__telo",
    porukaZaKorisnika(err) + " Prazan iznos bi ovde bio netačan — "
    + "ne zaključujte da novca nema."));
  return p;
}

async function ucitaj({ signal } = {}) {
  const [s, d, g] = await Promise.allSettled([
    dohvati("/billing/naplata-status", { signal }),
    dohvati("/billing/dugovanja", { signal }),
    dohvati("/billing/report/godisnji", { signal }),
  ]);
  for (const x of [s, d, g]) {
    if (x.status === "rejected" && jePrekid(x.reason)) throw x.reason;
  }
  return {
    stanje: s.status === "fulfilled" ? uStanjeNaplate(s.value) : null,
    stanjeGreska: s.status === "rejected" ? s.reason : null,
    nefakturisano: d.status === "fulfilled" ? uNefakturisano(d.value) : null,
    nefakturisanoGreska: d.status === "rejected" ? d.reason : null,
    godisnji: g.status === "fulfilled" ? uGodisnji(g.value) : null,
    godisnjiGreska: g.status === "rejected" ? g.reason : null,
  };
}

/* ── Stanje naplate ─────────────────────────────────────────────────────── */
function poljeIznosa(oznaka, iznos, objasnjenje, kljuc) {
  const d = el("div", "v2-fin__polje");
  d.dataset.polje = kljuc;
  d.appendChild(el("span", "v2-fin__oznaka", oznaka));
  d.appendChild(el("span", "v2-fin__iznos v2-mono", iznos));
  // Objasnjenje NIJE ukras: bez njega se „nije fakturisano" cita kao dug.
  d.appendChild(el("span", "v2-fin__opis", objasnjenje));
  return d;
}

function sekcijaStanja(d) {
  const s = celina("stanje", "Stanje naplate");
  if (!d.stanje) {
    s.appendChild(nijeUcitano("Stanje naplate", d.stanjeGreska));
    return s;
  }
  const n = d.stanje;
  const g = el("div", "v2-fin__mreza");
  g.appendChild(poljeIznosa("Nije naplaćeno", n.neizmireno,
    "Izdate fakture koje nisu plaćene. Ovo klijenti duguju.", "neizmireno"));
  g.appendChild(poljeIznosa("Nije fakturisano", n.nefakturisano,
    "Evidentiran rad koji još nije ušao ni u jednu fakturu. "
    + "Klijent ovo ne duguje — nije mu ispostavljeno.", "nefakturisano"));
  g.appendChild(poljeIznosa("Nacrti faktura", n.nacrt,
    "Fakture koje još nisu izdate. Ni potraživanje ni prihod.", "nacrt"));
  g.appendChild(poljeIznosa("Naplaćeno", n.naplaceno,
    "Plaćene fakture.", "naplaceno"));
  s.appendChild(g);

  if (n.fakturaUkupno !== null) {
    const delovi = [`${n.fakturaUkupno} faktura ukupno`];
    if (n.fakturaIzdate !== null) delovi.push(`${n.fakturaIzdate} izdato`);
    if (n.fakturaPlacene !== null) delovi.push(`${n.fakturaPlacene} plaćeno`);
    s.appendChild(el("p", "v2-celina__prazno", delovi.join(" · ")));
  }
  return s;
}

/* ── Nefakturisan rad po predmetu ───────────────────────────────────────── */
function sekcijaNefakturisanog(d, ciklus) {
  const s = celina("nefakturisano", "Rad koji čeka fakturu");
  if (!d.nefakturisano) {
    s.appendChild(nijeUcitano("Nefakturisan rad", d.nefakturisanoGreska));
    return s;
  }
  const n = d.nefakturisano;

  if (n.nepotpuno.length) {
    // Server je imenovao izvor koji nije procitan — precutati to znacilo bi
    // pustiti da „—" izgleda kao predmet bez naziva.
    s.appendChild(el("p", "v2-poruka v2-poruka--upozorenje",
      "Nije učitano: " + n.nepotpuno.join(", ")
      + ". Iznosi su tačni, ali neki predmeti nisu imenovani."));
  }

  if (!n.grupe.length) {
    s.appendChild(el("p", "v2-celina__prazno",
      "Sav evidentiran rad je fakturisan."));
    return s;
  }

  s.appendChild(el("p", "v2-fin__zbir",
    `${n.ukupno} na ${n.predmeta} ${n.predmeta === 1 ? "predmetu" : "predmeta"}`));

  const ul = el("ul", "v2-fin__lista");
  for (const g of n.grupe) {
    const li = el("li", "v2-fin__grupa");
    const glava = el("div", "v2-fin__glava");
    if (g.predmetId) {
      const a = el("a", "v2-fin__predmet",
        g.nazivPoznat ? g.naziv : "Predmet bez učitanog naziva");
      a.href = putanjaZa("predmet", g.predmetId) + "#celina-naplata";
      ciklus.slusaj(a, "click", (e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        e.preventDefault();
        idiNaPutanju(putanjaZa("predmet", g.predmetId) + "#celina-naplata");
      });
      glava.appendChild(a);
    } else {
      glava.appendChild(el("span", "v2-fin__predmet", "Rad bez predmeta"));
    }
    glava.appendChild(el("span", "v2-fin__iznos v2-mono", " " + g.ukupno));
    li.appendChild(glava);

    const stavke = el("ul", "v2-lista-tanka");
    for (const x of g.stavke) {
      const s2 = el("li", "v2-fin__stavka");
      s2.appendChild(document.createTextNode(x.opis));
      const meta = el("span", "v2-fin__meta");
      if (x.datum) meta.appendChild(el("span", "", " " + x.datum));
      meta.appendChild(el("span", "v2-mono", " " + x.iznos));
      s2.appendChild(meta);
      stavke.appendChild(s2);
    }
    li.appendChild(stavke);
    ul.appendChild(li);
  }
  s.appendChild(ul);
  return s;
}

/* ── Godina ─────────────────────────────────────────────────────────────── */
function sekcijaGodine(d) {
  const s = celina("godina", "Godina");
  if (!d.godisnji) {
    s.appendChild(nijeUcitano("Godišnji pregled", d.godisnjiGreska));
    return s;
  }
  const g = d.godisnji;
  s.appendChild(el("p", "v2-fin__zbir",
    `${g.godina} — uneseno ${g.uneseno}, fakturisano ${g.fakturisano}, `
    + `naplaćeno ${g.naplaceno}`));

  // Stopa naplate se prikazuje SAMO ako je bilo sta fakturisano: „0%" nad
  // nulom nije lose poslovanje nego odsustvo posla.
  if (g.stopaZnacajna && g.stopa !== null) {
    s.appendChild(el("p", "v2-celina__prazno",
      `Naplaćeno je ${g.stopa}% fakturisanog.`));
  } else {
    s.appendChild(el("p", "v2-celina__prazno",
      "Stopa naplate se ne prikazuje jer u ovoj godini nema fakturisanog iznosa."));
  }

  const sMesecom = g.meseci.filter(m => (m.unesenoBroj || 0) > 0 || (m.naplacenoBroj || 0) > 0);
  if (!sMesecom.length) {
    s.appendChild(el("p", "v2-celina__prazno",
      "U ovoj godini još nema evidentiranog rada ni naplate."));
    return s;
  }

  // Prikazuju se SAMO meseci sa prometom. Dvanaest praznih traka nije
  // pregled nego ukras.
  const tabela = el("div", "v2-fin__meseci");
  for (const m of sMesecom) {
    const r = el("div", "v2-fin__mesec");
    r.appendChild(el("span", "v2-fin__mesec-ime v2-mono", m.mesec));
    const traka = el("span", "v2-fin__traka");
    const ud = el("span", "v2-fin__traka-deo v2-fin__traka-deo--uneseno");
    // Trake se mere prema NAJVECEM stvarnom mesecu, ne prema izmisljenom
    // maksimumu — inace bi mesec od 1.000 RSD izgledao kao pun mesec.
    ud.style.width = g.vrh > 0 ? ((m.unesenoBroj || 0) / g.vrh * 100).toFixed(1) + "%" : "0%";
    traka.appendChild(ud);
    r.appendChild(traka);
    r.appendChild(el("span", "v2-fin__mesec-iznos v2-mono", " " + m.uneseno));
    tabela.appendChild(r);
  }
  s.appendChild(tabela);
  return s;
}

export function montirajFinansije(kontejner) {
  const ciklus = napraviCiklus();

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--predmet");
  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Finansije");
  h1.id = "v2-naslov-finansije";
  zaglavlje.appendChild(h1);
  zaglavlje.appendChild(el("p", "v2-podnaslov",
    "Šta je naplaćeno, šta klijenti duguju i šta još niste fakturisali — "
    + "tri različita iznosa, odvojeno."));
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
  const ovde = el("span", "v2-prekidac__stavka v2-prekidac__stavka--aktivna", "Finansije");
  ovde.setAttribute("aria-current", "page");
  const kaTarifama = el("a", "v2-prekidac__stavka", "Tarife");
  kaTarifama.href = putanjaZa("kancelarija", "tarife");
  ciklus.slusaj(kaTarifama, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("kancelarija", "tarife");
  });
  prekidac.append(kaKanc, ovde, kaTarifama);
  unutra.appendChild(prekidac);

  const sadrzaj = el("div", "v2-kancelarija");
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  sadrzaj.setAttribute("aria-labelledby", "v2-naslov-finansije");
  unutra.appendChild(sadrzaj);
  kontejner.appendChild(unutra);
  document.title = "Finansije · Vindex";

  (async () => {
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno", "Učitava se…"));
    let d;
    try {
      d = await ucitaj({ signal: ciklus.prekidac().signal });
    } catch (e) {
      if (jePrekid(e) || ciklus.ugasen) return;
      if (e && e.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      sadrzaj.replaceChildren(nijeUcitano("Finansije", e));
      return;
    }
    if (ciklus.ugasen) return;
    const okvir = document.createDocumentFragment();
    okvir.appendChild(sekcijaStanja(d));
    okvir.appendChild(sekcijaNefakturisanog(d, ciklus));
    okvir.appendChild(sekcijaGodine(d));
    sadrzaj.replaceChildren(okvir);
  })();

  return ciklus;
}
