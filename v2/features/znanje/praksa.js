/* Vindex V2 — SUDSKA PRAKSA (`/app-v2/znanje/praksa`).
 *
 * Druga stvar koju advokat pita u prostoru ZNANJE. Nije poseban prostor:
 * „sta kaze propis" i „sta je sud vec presudio" su dva pitanja o istoj temi.
 *
 * ODLUKA NIJE ODGOVOR MODELA. Ovde se prikazuju stvarne presude iz korpusa,
 * pa nema ograde o pouzdanosti — ogradjivati doslovan citat presude znacilo
 * bi tvrditi da je i on generisan. Ono sto se istice je CITAT, jer je to
 * jedini oblik u kome se odluka moze upotrebiti u podnesku.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { idiNa, putanjaZa } from "../../platform/router.js";
import { OBLASTI, uRezultat, uUpit, nedostaciUpita } from "../../domain/praksa.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

export function montirajPraksu(kontejner, kontekst) {
  const ciklus = napraviCiklus();
  const zaceto = kontekst || {};

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--predmet");

  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Sudska praksa");
  h1.id = "v2-naslov-praksa";
  zaglavlje.appendChild(h1);
  zaglavlje.appendChild(el("p", "v2-podnaslov",
    "Odluke iz korpusa sudske prakse. Prikazuje se tekst izreke i citat u obliku "
    + "u kome se može upotrebiti u podnesku."));
  unutra.appendChild(zaglavlje);

  // ── Prebacivanje izmedju propisa i prakse ──
  const izbor = el("nav", "v2-prekidac");
  izbor.setAttribute("aria-label", "Šta pitate");
  const kaPropisima = el("a", "v2-prekidac__stavka", "Propisi");
  kaPropisima.href = putanjaZa("znanje");
  ciklus.slusaj(kaPropisima, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("znanje");
  });
  const ovde = el("span", "v2-prekidac__stavka v2-prekidac__stavka--aktivna", "Sudska praksa");
  ovde.setAttribute("aria-current", "page");
  izbor.append(kaPropisima, ovde);
  unutra.appendChild(izbor);

  // ── Obrazac ──
  const forma = el("form", "v2-forma v2-znanje__forma");
  forma.noValidate = true;

  const omotUpit = el("div", "v2-polje-unos");
  const labU = el("label", "v2-polje-unos__labela", "Pojam");
  labU.htmlFor = "v2-praksa-upit";
  const upit = el("input", "v2-polje-unos__kontrola");
  upit.id = "v2-praksa-upit";
  upit.type = "search";
  upit.placeholder = "Npr. naknada nematerijalne štete";
  upit.value = zaceto.upit || "";
  omotUpit.append(labU, upit);

  const omotObl = el("div", "v2-polje-unos");
  const labO = el("label", "v2-polje-unos__labela", "Oblast");
  labO.htmlFor = "v2-praksa-oblast";
  const oblast = el("select", "v2-polje-unos__kontrola");
  oblast.id = "v2-praksa-oblast";
  const prazna = document.createElement("option");
  prazna.value = ""; prazna.textContent = "Sve oblasti";
  oblast.appendChild(prazna);
  for (const o of OBLASTI) {
    const x = document.createElement("option");
    x.value = o; x.textContent = o;
    oblast.appendChild(x);
  }
  oblast.value = zaceto.oblast || "";
  omotObl.append(labO, oblast);

  const par = el("div", "v2-forma__par");
  par.append(omotUpit, omotObl);

  const radnje = el("div", "v2-forma__radnje");
  const trazi = el("button", "v2-dugme v2-dugme--glavno", "Pretraži praksu");
  trazi.type = "submit";
  radnje.appendChild(trazi);

  forma.append(par, radnje);
  unutra.appendChild(forma);

  const sadrzaj = el("div", "v2-praksa");
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  sadrzaj.setAttribute("aria-labelledby", "v2-naslov-praksa");
  unutra.appendChild(sadrzaj);
  kontejner.appendChild(unutra);
  document.title = "Sudska praksa · Vindex";
  upit.focus();

  function prazno() {
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
      "Unesite pojam ili izaberite oblast. Pretražuje se korpus sudske prakse — "
      + "ne opšte znanje modela."));
  }

  function iscrtaj(r) {
    if (!r.odluke.length) {
      // Prazan rezultat NIJE greska i ne sme izgledati kao pad.
      sadrzaj.replaceChildren(el("p", "v2-celina__prazno",
        "Pretraga je izvršena i nije vratila nijednu odluku. Pokušajte sa širim "
        + "pojmom ili bez filtera oblasti."));
      return;
    }
    const okvir = document.createDocumentFragment();
    okvir.appendChild(el("p", "v2-reg__broj",
      r.ukupno === 1 ? "1 odluka" : `${r.odluke.length} od ${r.ukupno} odluka`));

    const ul = el("ul", "v2-praksa__lista");
    for (const o of r.odluke) {
      const li = el("li", "v2-praksa__red");

      // Citat je prvo sto se vidi: to je jedini oblik u kome se odluka
      // moze upotrebiti u podnesku.
      const citat = el("p", "v2-praksa__citat", o.citat);
      li.appendChild(citat);

      const meta = el("p", "v2-praksa__meta");
      if (o.oblast) meta.appendChild(el("span", "v2-praksa__oblast", o.oblast));
      if (o.datum) meta.appendChild(el("span", "v2-mono", o.datum));
      if (!o.citljiva) {
        meta.appendChild(el("span", "v2-praksa__upozorenje",
          "bez broja odluke — ne može se citirati"));
      }
      if (meta.childNodes.length) li.appendChild(meta);

      if (o.izreka) li.appendChild(el("p", "v2-praksa__izreka", o.izreka));
      ul.appendChild(li);
    }
    okvir.appendChild(ul);
    sadrzaj.replaceChildren(okvir);
  }

  let radi = false;
  async function pretrazi() {
    if (radi) return;
    const unos = { upit: upit.value, oblast: oblast.value };
    const greske = nedostaciUpita(unos);
    if (greske.length) {
      sadrzaj.replaceChildren(el("p", "v2-celina__prazno", greske[0]));
      upit.focus();
      return;
    }

    radi = true;
    trazi.disabled = true;
    trazi.textContent = "Pretražuje se…";
    sadrzaj.setAttribute("aria-busy", "true");
    sadrzaj.replaceChildren(el("p", "v2-celina__prazno", "Pretraga korpusa sudske prakse…"));

    let d;
    try {
      d = await posalji("/api/praksa/search", {
        telo: uUpit(unos), signal: ciklus.prekidac().signal,
      });
    } catch (e) {
      if (jePrekid(e) || ciklus.ugasen) return;
      radi = false;
      trazi.disabled = false;
      trazi.textContent = "Pretraži praksu";
      sadrzaj.setAttribute("aria-busy", "false");
      if (e && e.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      const p = el("div", "v2-poruka v2-poruka--greska");
      p.appendChild(el("p", "v2-poruka__naslov", "Pretraga prakse nije izvršena"));
      p.appendChild(el("p", "v2-poruka__telo",
        porukaZaKorisnika(e) + " Izostanak rezultata NIJE dokaz da odluke nema."));
      sadrzaj.replaceChildren(p);
      return;
    }
    if (ciklus.ugasen) return;

    radi = false;
    trazi.disabled = false;
    trazi.textContent = "Pretraži praksu";
    sadrzaj.setAttribute("aria-busy", "false");
    zaceto.upit = upit.value;
    zaceto.oblast = oblast.value;
    iscrtaj(uRezultat(d));
  }

  ciklus.slusaj(forma, "submit", (e) => { e.preventDefault(); pretrazi(); });

  ciklus.kontekst = () => ({ upit: upit.value, oblast: oblast.value });

  if ((zaceto.upit || "").trim() || zaceto.oblast) pretrazi();
  else prazno();

  return ciklus;
}
