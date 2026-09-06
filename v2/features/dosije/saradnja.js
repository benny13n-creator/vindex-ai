/* Vindex V2 — saradnja na predmetu, unutar Dosijea (B18).
 *
 * ─────────────────────────────────────────────────────────────────────────
 * ZASTO JE OVO U STANJU, A NE NOVA CELINA
 *
 * Saradnja odgovara na "ko sve ima pristup ovom predmetu" -- to je pitanje o
 * IDENTITETU/ADMINISTRACIJI predmeta, isto mesto gde vec zive stranke i
 * broj predmeta. Za razliku od Naplate (koja opravdano ima sopstvenu celinu
 * jer je svakodnevna radnja), deljenje predmeta je RETKA, admin-tipa radnja
 * -- ne zasluzuje sopstveno sidro u navigaciji (mandat §20: pet imenovanih
 * sidara, ne modul-po-capability).
 *
 * ─────────────────────────────────────────────────────────────────────────
 * VLASNIK NIJE JEDINA MOGUCA VEZA, ALI JE JEDINA KOJU OVA VERZIJA PRIKAZUJE
 *
 * Backend (`routers/saradnja.py`) razlikuje "vlasnik" od tri saradnicke
 * uloge (citanje/saradnja/vodenje). Ova prva verzija prikazuje UPRAVLJANJE
 * (dodaj/ukloni) SAMO vlasniku predmeta -- saradnikov pogled na TUDJI
 * deljeni predmet ("moji-predmeti") NIJE ovde pokriven i ostaje sledeci
 * korak, ne skriven propust: `GET /api/saradnja/uloga/{id}` se poziva PRVO
 * i ako uloga nije "vlasnik", ovaj blok se uopste ne prikazuje (nema
 * poluprikazane forme koju saradnik ne sme da koristi).
 */

import { dohvati, posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { ostavi } from "../../platform/obavestenje.js";
import { uSaradnike, jeVlasnik, validanEmail, ULOGE } from "../../domain/saradnja.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

/** Prvo pita ULOGU (jedan jeftin poziv). Samo vlasnik dobija listu -- tudje
 * predmete ne treba ni pokusati ispisati, pa i pri gresci liste ostaje jasno
 * da je posredi VLASNIKOV predmet, ne tudji. */
export async function ucitajSaradnjuPredmeta(predmetId, { signal } = {}) {
  let u;
  try {
    u = await dohvati(`/api/saradnja/uloga/${encodeURIComponent(predmetId)}`, { signal });
  } catch (e) {
    if (jePrekid(e)) throw e;
    return { prikazati: false, ulogaPala: true };
  }
  if (!jeVlasnik(u)) return { prikazati: false };

  try {
    const s = await dohvati(`/api/saradnja/saradnici/${encodeURIComponent(predmetId)}`, { signal });
    return { prikazati: true, saradnici: uSaradnike(s), saradniciPali: false };
  } catch (e) {
    if (jePrekid(e)) throw e;
    return { prikazati: true, saradnici: [], saradniciPali: true, greska: e };
  }
}

function redSaradnika(s, predmetId, ciklus, osvezi) {
  const li = el("li", "v2-lista-tanka__red");
  const glavni = el("span", "", s.email);
  li.appendChild(glavni);
  li.appendChild(el("span", "v2-meta", " · " + s.ulogaNaziv));

  const ukloni = el("button", "v2-dugme-tekst v2-dugme-tekst--opasnost", "Ukloni");
  ukloni.type = "button";
  ciklus.slusaj(ukloni, "click", async () => {
    if (!window.confirm(`Ukloniti ${s.email} sa ovog predmeta?`)) return;
    ukloni.disabled = true;
    try {
      await posalji(
        `/api/saradnja/ukloni/${encodeURIComponent(predmetId)}/${encodeURIComponent(s.id)}`,
        { metod: "DELETE", signal: ciklus.prekidac().signal },
      );
      if (ciklus.ugasen) return;
      ostavi(`${s.email} uklonjen(a) sa predmeta.`, "uspeh");
      osvezi();
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      ukloni.disabled = false;
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      ostavi("Uklanjanje nije uspelo. " + porukaZaKorisnika(err), "greska");
    }
  });
  li.appendChild(ukloni);
  return li;
}

function blokDodavanja(predmetId, ciklus, osvezi) {
  const b = el("div", "v2-forma v2-forma--redovi");
  const red = el("div", "v2-forma__red");

  const email = el("input");
  email.type = "email";
  email.placeholder = "email@primer.rs";
  email.setAttribute("aria-label", "Email kolege");

  const uloga = el("select");
  for (const u of ULOGE) {
    const opt = el("option", "", u.naziv);
    opt.value = u.kljuc;
    uloga.appendChild(opt);
  }

  const dodaj = el("button", "v2-dugme", "Dodaj saradnika");
  dodaj.type = "button";
  red.append(email, uloga, dodaj);

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;
  b.append(red, poruka);

  ciklus.slusaj(dodaj, "click", async () => {
    if (!validanEmail(email.value)) {
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = "Unesite ispravnu email adresu.";
      poruka.hidden = false;
      return;
    }
    dodaj.disabled = true;
    dodaj.textContent = "Dodaje se…";
    poruka.hidden = true;
    try {
      await posalji(`/api/saradnja/dodaj/${encodeURIComponent(predmetId)}`, {
        telo: { saradnik_email: email.value.trim(), uloga: uloga.value },
        signal: ciklus.prekidac().signal,
      });
      if (ciklus.ugasen) return;
      email.value = "";
      ostavi("Saradnik je dodat.", "uspeh");
      osvezi();
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      dodaj.disabled = false;
      dodaj.textContent = "Dodaj saradnika";
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = "Saradnik nije dodat. " + porukaZaKorisnika(err);
      poruka.hidden = false;
    }
  });
  return b;
}

/** Vraca `null` kad saradnja ne treba da se prikaze (nije vlasnik) --
 * pozivalac tada ne dodaje podblok uopste, umesto da prikaze prazan okvir. */
export function sadrzajSaradnje(s, predmetId, ciklus, osvezi) {
  if (!s || !s.prikazati) return null;

  const b = el("div", "v2-podblok");
  b.appendChild(el("h3", "v2-natkapa", "Saradnici"));

  if (s.saradniciPali) {
    const p = el("p", "v2-celina__prazno",
      "Lista saradnika nije učitana. " + porukaZaKorisnika(s.greska));
    b.appendChild(p);
  } else if (!s.saradnici.length) {
    b.appendChild(el("p", "v2-celina__prazno", "Nijedan kolega još nema pristup ovom predmetu."));
  } else {
    const ul = el("ul", "v2-lista-tanka");
    for (const sar of s.saradnici) ul.appendChild(redSaradnika(sar, predmetId, ciklus, osvezi));
    b.appendChild(ul);
  }

  b.appendChild(blokDodavanja(predmetId, ciklus, osvezi));
  return b;
}
