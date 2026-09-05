/* Vindex V2 — racunanje rokova (`/app-v2/znanje/rokovi`), B26.
 *
 * Trece pitanje u Znanju, uz „sta kaze propis" i „sta je sud presudio":
 * „do kada". Zastarelost potrazivanja i procesni rok su isto pitanje sa dve
 * osnove, pa stoje na jednom ekranu sa prekidacem, a ne na dva.
 *
 * Racun je DETERMINISTICAN i dolazi sa zakonskim osnovom (ZOO/ZR za
 * zastarelost, ZPP/ZKP/ZR/ZIO/ZUP za procesne rokove, uz srpske praznike).
 * Zato se zakljucak sme prikazati — ali osnov se prikazuje UZ njega, nikad
 * ispod preloma, jer je clan ono na sta se advokat poziva.
 *
 * „ISTEKLO" DOBIJA SOPSTVENO STANJE. Zastarelo potrazivanje i propusten
 * procesni rok se ne smeju prikazati istim tonom kao „ostalo je jos 40 dana".
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { dohvati, posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { idiNa, putanjaZa } from "../../platform/router.js";
import { ISHOD, uZastarelost, uProcesniRok, nedostaciRacuna,
         uTipoveZastarelosti, uTipoveProcesnih } from "../../domain/rokovi_racun.js";

const OSNOVE = [
  { kljuc: "zastarelost", naziv: "Zastarelost potraživanja" },
  { kljuc: "procesni", naziv: "Procesni rok" },
];

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

function danasIso() {
  const n = new Date();
  const p = (x) => String(x).padStart(2, "0");
  return `${n.getFullYear()}-${p(n.getMonth() + 1)}-${p(n.getDate())}`;
}

export function montirajRokove(kontejner, kontekst) {
  const ciklus = napraviCiklus();
  const z = kontekst || {};
  let osnova = OSNOVE.some(o => o.kljuc === z.osnova) ? z.osnova : "zastarelost";
  let tipovi = { zastarelost: null, procesni: null };

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--tekst");

  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Rokovi");
  h1.id = "v2-naslov-rokovi";
  zaglavlje.appendChild(h1);
  zaglavlje.appendChild(el("p", "v2-podnaslov",
    "Računanje po zakonu — zastarelost potraživanja i procesni rokovi, "
    + "sa srpskim praznicima i radnim danima. Svaki rezultat nosi zakonski osnov."));
  unutra.appendChild(zaglavlje);

  // ── Prekidac: koje pitanje u Znanju ──
  const izbor = el("nav", "v2-prekidac");
  izbor.setAttribute("aria-label", "Šta pitate");
  const kaPropisima = el("a", "v2-prekidac__stavka", "Propisi");
  kaPropisima.href = putanjaZa("znanje");
  ciklus.slusaj(kaPropisima, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("znanje");
  });
  const kaPraksi = el("a", "v2-prekidac__stavka", "Sudska praksa");
  kaPraksi.href = putanjaZa("znanje", "praksa");
  ciklus.slusaj(kaPraksi, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("znanje", "praksa");
  });
  const ovde = el("span", "v2-prekidac__stavka v2-prekidac__stavka--aktivna", "Rokovi");
  ovde.setAttribute("aria-current", "page");
  izbor.append(kaPropisima, kaPraksi, ovde);
  unutra.appendChild(izbor);

  // ── Izbor osnove ──
  const osnovaRed = el("div", "v2-radnja__red");
  osnovaRed.setAttribute("role", "group");
  osnovaRed.setAttribute("aria-label", "Vrsta računa");
  const dugmadOsnove = new Map();
  for (const o of OSNOVE) {
    const d = el("button", "v2-dugme", o.naziv);
    d.type = "button";
    ciklus.slusaj(d, "click", () => {
      if (osnova === o.kljuc) return;
      osnova = o.kljuc;
      ishodOkvir.replaceChildren();
      poruka.hidden = true;
      osveziOsnovu();
    });
    dugmadOsnove.set(o.kljuc, d);
    osnovaRed.appendChild(d);
  }
  unutra.appendChild(osnovaRed);

  // ── Obrazac ──
  const forma = el("form", "v2-forma v2-znanje__forma");
  forma.noValidate = true;

  const omotTip = el("div", "v2-polje-unos");
  const labTip = el("label", "v2-polje-unos__labela", "Vrsta");
  labTip.htmlFor = "v2-rok-tip";
  const tip = el("select", "v2-polje-unos__kontrola");
  tip.id = "v2-rok-tip";
  omotTip.append(labTip, tip);
  const opisTipa = el("p", "v2-polje-unos__pomoc");
  omotTip.appendChild(opisTipa);

  const omotDatum = el("div", "v2-polje-unos");
  const labDatum = el("label", "v2-polje-unos__labela", "Datum od koga rok teče");
  labDatum.htmlFor = "v2-rok-datum";
  const datum = el("input", "v2-polje-unos__kontrola");
  datum.id = "v2-rok-datum";
  datum.type = "date";
  datum.max = "2999-12-31";
  omotDatum.append(labDatum, datum);

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;

  const radnje = el("div", "v2-forma__radnje");
  const racunaj = el("button", "v2-dugme v2-dugme--glavno", "Izračunaj");
  racunaj.type = "submit";
  radnje.appendChild(racunaj);

  forma.append(omotTip, omotDatum, poruka, radnje);
  unutra.appendChild(forma);

  const ishodOkvir = el("div", "v2-rok-ishod");
  ishodOkvir.setAttribute("aria-live", "polite");
  unutra.appendChild(ishodOkvir);

  kontejner.appendChild(unutra);
  document.title = "Rokovi · Vindex";

  function javi(t, vrsta) {
    poruka.className = "v2-forma__poruka v2-forma__poruka--" + (vrsta || "greska");
    poruka.textContent = t;
    poruka.hidden = false;
  }

  function osveziDugmad() {
    for (const [k, d] of dugmadOsnove) {
      const akt = k === osnova;
      d.classList.toggle("v2-dugme--glavno", akt);
      d.setAttribute("aria-pressed", akt ? "true" : "false");
    }
  }

  function opisIzabranog() {
    const lista = tipovi[osnova] || [];
    const t = lista.find(x => x.kljuc === tip.value);
    if (!t) { opisTipa.textContent = ""; return; }
    // Zakonski osnov stoji UZ izbor, pre racuna: advokat bira clan, ne naziv.
    const delovi = [];
    if (t.osnov) delovi.push(t.osnov);
    // Broj dana se dopisuje samo ako ga napomena vec ne izgovara.
    if (t.dana !== undefined && t.dana !== null && !t.ponavlja) {
      delovi.push(`${t.dana} ${t.racunanje}`);
    }
    if (t.opis) delovi.push(t.opis);
    opisTipa.textContent = delovi.join(" · ");
  }

  async function osveziOsnovu() {
    osveziDugmad();
    labDatum.textContent = osnova === "zastarelost"
      ? "Datum od koga zastarelost teče"
      : "Datum od koga rok teče (dostavljanje, objava)";

    if (!tipovi[osnova]) {
      tip.replaceChildren(el("option", "", "Učitava se…"));
      tip.disabled = true;
      try {
        const put = osnova === "zastarelost"
          ? "/zastarelost/tipovi" : "/api/rokovi/procesni/tipovi";
        const r = await dohvati(put, { signal: ciklus.prekidac().signal });
        if (ciklus.ugasen) return;
        tipovi[osnova] = osnova === "zastarelost"
          ? uTipoveZastarelosti(r) : uTipoveProcesnih(r);
      } catch (err) {
        if (jePrekid(err) || ciklus.ugasen) return;
        if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
        tip.replaceChildren(el("option", "", "Vrste nisu učitane"));
        // Prazan spisak vrsta NIJE „nema takvih rokova".
        javi("Spisak vrsta nije učitan. " + porukaZaKorisnika(err)
             + " Ne zaključujte da ova vrsta roka ne postoji.");
        return;
      }
    }
    const lista = tipovi[osnova] || [];
    tip.disabled = false;
    tip.replaceChildren(...lista.map(t => {
      const o = el("option", "", t.naziv);
      o.value = t.kljuc;
      return o;
    }));
    opisIzabranog();
  }

  ciklus.slusaj(tip, "change", opisIzabranog);

  function redPodatka(oznaka, vrednost) {
    const r = el("div", "v2-rok-ishod__red");
    r.appendChild(el("span", "v2-rok-ishod__oznaka", oznaka));
    r.appendChild(el("span", "v2-rok-ishod__vrednost", vrednost));
    return r;
  }

  function iscrtajIshod(r, jeZastarelost) {
    if (!r.upotrebljiv) {
      // Racun bez zakonskog osnova se NE prikazuje kao rezultat.
      const p = el("div", "v2-poruka v2-poruka--greska");
      p.appendChild(el("p", "v2-poruka__naslov", "Rezultat nije prikazan"));
      p.appendChild(el("p", "v2-poruka__telo",
        "Odgovor nije stigao sa zakonskim osnovom, pa se rok ne prikazuje. "
        + "Rok bez člana na koji se možete pozvati nije upotrebljiv pred sudom."));
      ishodOkvir.replaceChildren(p);
      return;
    }

    const k = el("div", "v2-rok-ishod__kartica");
    k.dataset.ishod = r.ishod;

    const naslov = el("p", "v2-rok-ishod__naslov",
      jeZastarelost ? r.vrsta : r.naziv);
    k.appendChild(naslov);

    // Zakonski osnov stoji ODMAH ispod naziva, ne na dnu.
    const osnov = jeZastarelost ? r.osnov : r.naziv;
    if (jeZastarelost && r.osnov) {
      k.appendChild(el("p", "v2-rok-ishod__osnov v2-mono", r.osnov));
    }

    const kljucna = el("p", "v2-rok-ishod__datum");
    kljucna.appendChild(el("span", "v2-mono", r.doDatuma));
    kljucna.appendChild(document.createTextNode(
      jeZastarelost ? " — potraživanje zastareva" : " — rok ističe"));
    k.appendChild(kljucna);

    const stanje = el("p", "v2-rok-ishod__stanje");
    if (r.ishod === ISHOD.ISTEKLO) {
      stanje.textContent = jeZastarelost
        ? "Rok je istekao — potraživanje je zastarelo."
        : "Rok je istekao.";
    } else if (r.ishod === ISHOD.NEPOZNATO) {
      // Odsutan broj dana nije nula i ne sme se prikazati kao „ističe danas".
      stanje.textContent = "Broj preostalih dana nije stigao — datum iznad je "
        + "jedini podatak na koji se oslonite.";
    } else if (r.danaPoznato) {
      stanje.textContent = r.dana === 1
        ? "Preostao je 1 dan."
        : `Preostalo je ${r.dana} dana.`;
    }
    if (stanje.textContent) k.appendChild(stanje);

    const detalji = el("div", "v2-rok-ishod__detalji");
    if (r.odDatuma) detalji.appendChild(redPodatka("Teče od", r.odDatuma));
    if (jeZastarelost && r.rokOpis) detalji.appendChild(redPodatka("Rok", r.rokOpis));
    if (detalji.children.length) k.appendChild(detalji);

    if (r.napomena) k.appendChild(el("p", "v2-rok-ishod__napomena", r.napomena));

    // Racun je pomoc, ne odluka: prekid zastarelosti (priznanje duga, tuzba)
    // ovaj ekran NE zna, pa to mora reci sam.
    k.appendChild(el("p", "v2-rok-ishod__ograda",
      jeZastarelost
        ? "Račun ne uzima u obzir prekid ni zastoj zastarelosti (priznanje "
          + "duga, podnošenje tužbe, viša sila). Proverite ih u spisima predmeta."
        : "Račun polazi od unetog datuma. Proverite dan dostavljanja u spisima "
          + "— od njega zavisi ceo rok."));

    ishodOkvir.replaceChildren(k);
  }

  ciklus.slusaj(forma, "submit", async (e) => {
    e.preventDefault();
    const jeZastarelost = osnova === "zastarelost";
    const ulaz = { tip: tip.value, datum: datum.value };
    const g = nedostaciRacuna(ulaz);
    if (g.length) { javi(g.join(" ")); return; }

    racunaj.disabled = true;
    racunaj.textContent = "Računa se…";
    poruka.hidden = true;
    try {
      const r = await posalji(
        jeZastarelost ? "/zastarelost/kalkulisi" : "/api/rokovi/procesni",
        {
          telo: jeZastarelost
            ? { tip: ulaz.tip, datum_pocetka: ulaz.datum }
            : { tip_roka: ulaz.tip, datum_pocetka: ulaz.datum },
          signal: ciklus.prekidac().signal,
        });
      if (ciklus.ugasen) return;
      iscrtajIshod(jeZastarelost ? uZastarelost(r) : uProcesniRok(r), jeZastarelost);
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      // Prazan ekran posle neuspelog racuna bi se procitao kao „nema roka".
      ishodOkvir.replaceChildren();
      javi(err && err.status === 422
        ? "Rok nije izračunat — proverite datum i vrstu. " + porukaZaKorisnika(err)
        : "Rok nije izračunat. " + porukaZaKorisnika(err)
          + " Ne zaključujte ništa o roku iz izostanka odgovora.");
    } finally {
      if (!ciklus.ugasen) {
        racunaj.disabled = false;
        racunaj.textContent = "Izračunaj";
      }
    }
  });

  ciklus.kontekst = () => ({ osnova });

  datum.value = z.datum || danasIso();
  osveziOsnovu();
  return ciklus;
}
