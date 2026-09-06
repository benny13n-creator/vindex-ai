/* Vindex V2 — uvoz klijenata iz CSV (E10), unutar Kancelarija/Klijenti.
 *
 * POZNAT, NEPOPRAVLJEN JAZ backend-a (`klijenti/router.py::
 * import_klijenti_csv`): NE proverava duplikate pre upisa -- ponovljen
 * uvoz istog fajla pravi duplirane klijente. Ovo se ovde iskreno kaze
 * korisniku pre uvoza, ne prikriva.
 */

import { posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { ostavi } from "../../platform/obavestenje.js";
import { uRezultatUvoza, jeCsvFajl } from "../../domain/uvozKlijenata.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

export function blokUvozaKlijenata(ciklus, osvezi) {
  const b = el("div", "v2-podblok");
  b.appendChild(el("h3", "v2-natkapa", "Uvoz klijenata iz CSV"));
  b.appendChild(el("p", "v2-meta",
    "Kolone: ime, prezime, firma, email, telefon, adresa, tip. Najviše 500 redova. "
    + "Ponovljen uvoz istog fajla pravi duplirane klijente — proverite pre ponovnog uvoza."));

  const unos = el("input");
  unos.type = "file";
  unos.accept = ".csv";
  b.appendChild(unos);

  const dugme = el("button", "v2-dugme", "Uvezi");
  dugme.type = "button";
  b.appendChild(dugme);

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;
  b.appendChild(poruka);

  const rezultatMesto = el("div");
  b.appendChild(rezultatMesto);

  ciklus.slusaj(dugme, "click", async () => {
    const fajl = unos.files && unos.files[0];
    if (!jeCsvFajl(fajl)) {
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = "Izaberite .csv fajl.";
      poruka.hidden = false;
      return;
    }
    dugme.disabled = true;
    dugme.textContent = "Uvozi se…";
    poruka.hidden = true;
    rezultatMesto.replaceChildren();

    const podaci = new FormData();
    podaci.append("fajl", fajl, fajl.name);

    try {
      const r = await posalji("/klijenti/import-csv", { telo: podaci, signal: ciklus.prekidac().signal });
      if (ciklus.ugasen) return;
      const rez = uRezultatUvoza(r);
      const p = el("p", rez.kreiran > 0 ? "v2-forma__poruka v2-forma__poruka--uspeh" : "v2-forma__poruka v2-forma__poruka--upozorenje");
      p.textContent = `Uvezeno ${rez.kreiran} od ${rez.ukupnoPokusano} redova.`;
      rezultatMesto.appendChild(p);
      if (rez.greske.length) {
        const ul = el("ul", "v2-lista-tanka");
        for (const g of rez.greske) ul.appendChild(el("li", "v2-meta", g));
        rezultatMesto.appendChild(ul);
      }
      if (rez.kreiran > 0) {
        ostavi(`${rez.kreiran} klijent(a) uvezeno.`, "uspeh");
        if (osvezi) osvezi();
      }
      unos.value = "";
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = "Uvoz nije uspeo. " + porukaZaKorisnika(err);
      poruka.hidden = false;
    } finally {
      dugme.disabled = false;
      dugme.textContent = "Uvezi";
    }
  });

  return b;
}
