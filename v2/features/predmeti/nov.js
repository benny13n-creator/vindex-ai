/* Vindex V2 — Nov predmet.
 *
 * RADNJA unutar prostora PREDMETI (`/app-v2/predmeti/nov`), ne modal.
 * Modal bi ovaj tok ucinio neprenosivim: ne moze se podeliti, `back` ga ne
 * zatvara predvidivo, a na uskom ekranu postaje puna stranica sa lazljivim
 * ramom. Ovako je to obicna scena i ponasa se kao svaka druga.
 *
 * DVA KORAKA, JEDAN ISHOD — i zasto se to KAZE korisniku:
 * Backend prima `naziv`, `opis` i `tip` pri kreiranju; stranke i vrednost
 * spora se postavljaju tek naknadnom izmenom (`PATCH /api/predmeti/{id}`
 * dozvoljava naziv, opis, tip, status, tuzilac, tuzeni, oblast, rizik,
 * vrednost_spora — `broj_predmeta` NE). Zato ovaj ekran radi POST pa, ako
 * su dopunska polja popunjena, PATCH. Ako drugi korak padne, predmet
 * POSTOJI i korisnik se vodi u njegov Dosije sa tacnom porukom sta nije
 * sacuvano. Nikad se ne tvrdi da predmet nije napravljen kad jeste.
 *
 * VRSTA PREDMETA NIJE ZATVOREN SPISAK. Mereno na produkciji: `predmeti.tip`
 * nosi radni_spor, Parnica, opsti, ugovorni_spor, nasledstvo, naknada_stete,
 * potrosacki_spor, ostalo. Zato je ovde `datalist` — predlozi da, prinuda ne.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { idiNa, putanjaZa } from "../../platform/router.js";
import { ostavi } from "../../platform/obavestenje.js";

/** Predlozi vrste — poznate vrednosti iz baze, ne ogranicenje. */
const VRSTE = [
  "Parnica", "Radni spor", "Ugovorni spor", "Naknada štete",
  "Potrošački spor", "Nasledstvo", "Krivični", "Upravni",
  "Prekršajni", "Izvršni", "Privredni", "Porodični", "Opšti", "Ostalo",
];

/** Poslovni naziv -> kljuc koji baza vec koristi. Nepoznato ide kako je uneto. */
const KLJUC = {
  "parnica": "Parnica",
  "radni spor": "radni_spor",
  "ugovorni spor": "ugovorni_spor",
  "naknada štete": "naknada_stete",
  "potrošački spor": "potrosacki_spor",
  "nasledstvo": "nasledstvo",
  "krivični": "krivicni",
  "upravni": "upravni",
  "prekršajni": "prekrsajni",
  "izvršni": "izvrsni",
  "privredni": "privredni",
  "porodični": "porodicni",
  "opšti": "opsti",
  "ostalo": "ostalo",
};

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

/** Polje sa vidljivom labelom. Placeholder NIJE labela. */
function polje(id, naziv, { visered = false, tip = "text", pomoc = "", spisak = "" } = {}) {
  const omot = el("div", "v2-polje-unos");
  const lab = el("label", "v2-polje-unos__labela", naziv);
  lab.htmlFor = id;
  const unos = el(visered ? "textarea" : "input", "v2-polje-unos__kontrola");
  unos.id = id;
  unos.name = id;
  if (!visered) unos.type = tip;
  if (visered) unos.rows = 4;
  if (spisak) unos.setAttribute("list", spisak);
  omot.append(lab, unos);
  if (pomoc) {
    const p = el("p", "v2-polje-unos__pomoc", pomoc);
    p.id = id + "-pomoc";
    unos.setAttribute("aria-describedby", p.id);
    omot.appendChild(p);
  }
  return { omot, unos };
}

function brojIzTeksta(v) {
  // Advokat kuca „850.000,00" ili „850000". Oba znace isti iznos.
  const t = String(v || "").trim();
  if (!t) return null;
  const ocisceno = t.replace(/\s/g, "").replace(/\./g, "").replace(",", ".");
  const n = Number(ocisceno);
  return Number.isFinite(n) && n > 0 ? n : null;
}

export function montirajNovPredmet(kontejner, kontekst) {
  const ciklus = napraviCiklus();
  const zaceto = kontekst || {};

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--predmet");

  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Nov predmet");
  h1.id = "v2-naslov-nov";
  zaglavlje.appendChild(h1);
  zaglavlje.appendChild(el("p", "v2-podnaslov",
    "Predmet se otvara nazivom. Stranke, broj i vrednost spora mogu se dopuniti kasnije u Dosijeu."));
  unutra.appendChild(zaglavlje);

  const forma = el("form", "v2-forma");
  forma.noValidate = true;

  const p1 = polje("np-naziv", "Naziv predmeta", {
    pomoc: "Po čemu ćete ovaj predmet prepoznati u registru.",
  });
  p1.unos.required = true;
  p1.unos.autocomplete = "off";
  p1.unos.value = zaceto.naziv || "";

  const p2 = polje("np-vrsta", "Vrsta predmeta", {
    spisak: "np-vrste",
    pomoc: "Možete izabrati ponuđenu ili upisati svoju.",
  });
  p2.unos.value = zaceto.vrsta || "";
  const spisak = el("datalist");
  spisak.id = "np-vrste";
  for (const v of VRSTE) {
    const o = document.createElement("option");
    o.value = v;
    spisak.appendChild(o);
  }

  const p3 = polje("np-tuzilac", "Tužilac");
  p3.unos.value = zaceto.tuzilac || "";
  const p4 = polje("np-tuzeni", "Tuženi");
  p4.unos.value = zaceto.tuzeni || "";
  const p5 = polje("np-vrednost", "Vrednost spora", {
    pomoc: "U dinarima. Ostavite prazno ako nije poznata.",
  });
  p5.unos.inputMode = "decimal";
  p5.unos.value = zaceto.vrednost || "";
  const p6 = polje("np-opis", "Napomena", { visered: true });
  p6.unos.value = zaceto.opis || "";

  const par = el("div", "v2-forma__par");
  par.append(p3.omot, p4.omot);

  forma.append(p1.omot, p2.omot, spisak, par, p5.omot, p6.omot);

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;
  forma.appendChild(poruka);

  const radnje = el("div", "v2-forma__radnje");
  const potvrdi = el("button", "v2-dugme v2-dugme--glavno", "Otvori predmet");
  potvrdi.type = "submit";
  const odustani = el("a", "v2-dugme v2-dugme--tiho", "Odustani");
  odustani.href = putanjaZa("predmeti");
  radnje.append(potvrdi, odustani);
  forma.appendChild(radnje);

  unutra.appendChild(forma);
  kontejner.appendChild(unutra);
  p1.unos.focus();
  document.title = "Nov predmet · Vindex";

  function javi(tekst, vrsta) {
    poruka.className = "v2-forma__poruka v2-forma__poruka--" + (vrsta || "greska");
    poruka.textContent = tekst;
    poruka.hidden = false;
    poruka.scrollIntoView({ block: "nearest" });
  }

  function tipZaBazu(uneto) {
    const t = String(uneto || "").trim();
    if (!t) return "opsti";
    return KLJUC[t.toLowerCase()] || t;
  }

  let salje = false;

  ciklus.slusaj(odustani, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("predmeti");
  });

  ciklus.slusaj(forma, "submit", async (e) => {
    e.preventDefault();
    if (salje) return;

    const naziv = p1.unos.value.trim();
    if (!naziv) {
      javi("Naziv predmeta je obavezan.");
      p1.unos.focus();
      return;
    }

    // Dvostruko slanje je duplirani predmet. Dugme se gasi PRE poziva.
    salje = true;
    potvrdi.disabled = true;
    potvrdi.textContent = "Otvara se…";
    poruka.hidden = true;

    const prekidac = ciklus.prekidac();
    let napravljen;
    try {
      napravljen = await posalji("/api/predmeti", {
        telo: { naziv, opis: p6.unos.value.trim(), tip: tipZaBazu(p2.unos.value) },
        signal: prekidac.signal,
      });
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      salje = false;
      potvrdi.disabled = false;
      potvrdi.textContent = "Otvori predmet";
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      if (err && err.vrsta === VRSTA.MREZA) {
        javi("Veza je prekinuta pre nego što je stigao odgovor. Predmet je možda otvoren — "
           + "proverite registar pre nego što pokušate ponovo.", "upozorenje");
        return;
      }
      javi("Predmet nije otvoren. " + porukaZaKorisnika(err));
      return;
    }
    if (ciklus.ugasen) return;

    const id = napravljen && napravljen.predmet && napravljen.predmet.id;
    if (!id) {
      javi("Server je prihvatio zahtev, ali nije vratio predmet. Proverite registar pre ponovnog pokušaja.",
           "upozorenje");
      salje = false;
      potvrdi.disabled = false;
      potvrdi.textContent = "Otvori predmet";
      return;
    }

    // Drugi korak: polja koja kreiranje ne prima. Predmet vec postoji, pa
    // neuspeh ovde NE sme da izgleda kao neuspeh otvaranja predmeta.
    const dopuna = {};
    const tuzilac = p3.unos.value.trim();
    const tuzeni = p4.unos.value.trim();
    const vrednost = brojIzTeksta(p5.unos.value);
    if (tuzilac) dopuna.tuzilac = tuzilac;
    if (tuzeni) dopuna.tuzeni = tuzeni;
    if (vrednost !== null) dopuna.vrednost_spora = vrednost;

    if (Object.keys(dopuna).length) {
      try {
        await posalji(`/api/predmeti/${encodeURIComponent(id)}`, {
          metod: "PATCH", telo: dopuna, signal: prekidac.signal,
        });
      } catch (err) {
        if (!jePrekid(err) && !ciklus.ugasen) {
          // Predmet je otvoren; nedostaju samo dopunska polja. Vodimo
          // korisnika u Dosije i tamo mu to kazemo, umesto da ga drzimo na
          // formi pred kojom bi pomislio da mora ponovo da salje.
          ostavi("Predmet je otvoren, ali stranke i vrednost spora nisu sačuvane. "
               + "Dopunite ih u ovom Dosijeu.", "upozorenje");
        }
      }
    }
    if (ciklus.ugasen) return;
    idiNa("predmet", id);
  });

  // Kontekst se cuva da odlazak i povratak ne obrisu ono sto je vec otkucano.
  ciklus.kontekst = () => ({
    naziv: p1.unos.value, vrsta: p2.unos.value, tuzilac: p3.unos.value,
    tuzeni: p4.unos.value, vrednost: p5.unos.value, opis: p6.unos.value,
  });

  return ciklus;
}
