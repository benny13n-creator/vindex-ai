/* Vindex V2 — izmena podataka o predmetu.
 *
 * RADNJA nad objektom, u celini „Stanje". Ne otvara novu stranu: advokat
 * ispravlja ime tuzenog gledajuci ostatak predmeta, a ne u praznom obrascu.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * OPTIMISTICKA KONTROLA IZMENE — I ZASTO SE KORISTI
 *
 * `PATCH /api/predmeti/{id}` prima opciono `if_updated_at`. Bez njega je upis
 * slepi „poslednji pobedjuje": ako dva advokata iste kancelarije otvore isti
 * predmet, drugi tiho pregazi prvog i niko to ne sazna. Zato se `updated_at`
 * procitan pri otvaranju Dosijea salje nazad, a 409 se prikazuje kao ono sto
 * jeste — „neko je izmenio predmet u medjuvremenu", ne kao greska servera.
 *
 * BROJ POLJA JE OGRANICEN NA ONO STO SERVER PRIMA. Backend dozvoljava
 * naziv, opis, tip, status, tuzilac, tuzeni, oblast, rizik, vrednost_spora.
 * `broj_predmeta` NIJE u toj listi — polje koje se ne moze sacuvati se ovde
 * NE nudi, jer kontrola koja tiho ne radi je gora od njenog izostanka.
 * ─────────────────────────────────────────────────────────────────────────
 */

import { posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { ostavi } from "../../platform/obavestenje.js";

/** Polja koja server stvarno prihvata, redom prikaza. */
const POLJA = Object.freeze([
  { kljuc: "naziv", naziv: "Naziv predmeta", vrsta: "text" },
  { kljuc: "tuzilac", naziv: "Tužilac", vrsta: "text" },
  { kljuc: "tuzeni", naziv: "Tuženi", vrsta: "text" },
  { kljuc: "vrednost_spora", naziv: "Vrednost spora", vrsta: "text", broj: true },
  { kljuc: "opis", naziv: "Napomena", vrsta: "textarea" },
]);

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

function brojIzTeksta(v) {
  const t = String(v || "").trim();
  if (!t) return null;
  const n = Number(t.replace(/\s/g, "").replace(/\./g, "").replace(",", "."));
  return Number.isFinite(n) && n > 0 ? n : null;
}

/**
 * @param {string} predmetId
 * @param {object} sirovPredmet  neizmenjen `predmet` iz odgovora servera
 * @param {object} ciklus
 * @param {Function} osvezi
 */
export function kontrolaIzmene(predmetId, sirovPredmet, ciklus, osvezi) {
  const p = sirovPredmet || {};
  const omot = el("div", "v2-izmena");

  const otvori = el("button", "v2-dugme", "Izmeni podatke");
  otvori.type = "button";
  omot.appendChild(otvori);

  ciklus.slusaj(otvori, "click", () => {
    if (omot.querySelector(".v2-forma")) return;
    otvori.hidden = true;

    const forma = el("form", "v2-forma v2-izmena__forma");
    forma.noValidate = true;
    const unosi = new Map();

    for (const f of POLJA) {
      const red = el("div", "v2-polje-unos");
      const lab = el("label", "v2-polje-unos__labela", f.naziv);
      lab.htmlFor = "v2-izm-" + f.kljuc;
      const unos = el(f.vrsta === "textarea" ? "textarea" : "input",
                      "v2-polje-unos__kontrola");
      unos.id = "v2-izm-" + f.kljuc;
      if (f.vrsta !== "textarea") unos.type = "text";
      else unos.rows = 3;
      unos.value = p[f.kljuc] == null ? "" : String(p[f.kljuc]);
      unosi.set(f.kljuc, unos);
      red.append(lab, unos);
      forma.appendChild(red);
    }

    const poruka = el("div", "v2-forma__poruka");
    poruka.setAttribute("role", "alert");
    poruka.hidden = true;
    forma.appendChild(poruka);

    const radnje = el("div", "v2-forma__radnje");
    const sacuvaj = el("button", "v2-dugme v2-dugme--glavno", "Sačuvaj");
    sacuvaj.type = "submit";
    const odustani = el("button", "v2-dugme v2-dugme--tiho", "Odustani");
    odustani.type = "button";
    radnje.append(sacuvaj, odustani);
    forma.appendChild(radnje);
    omot.appendChild(forma);
    unosi.get("naziv").focus();

    function javi(t, vrsta) {
      poruka.className = "v2-forma__poruka v2-forma__poruka--" + (vrsta || "greska");
      poruka.textContent = t;
      poruka.hidden = false;
    }

    ciklus.slusaj(odustani, "click", () => {
      forma.remove();
      otvori.hidden = false;
      otvori.focus();
    });

    let salje = false;
    ciklus.slusaj(forma, "submit", async (e) => {
      e.preventDefault();
      if (salje) return;

      // Salju se SAMO polja koja je korisnik stvarno promenio. Slanje svega
      // pretvorilo bi svaku izmenu u prepis celog predmeta i bez potrebe
      // udarilo u tudje izmene drugih polja.
      const izmene = {};
      for (const f of POLJA) {
        const nova = unosi.get(f.kljuc).value.trim();
        const stara = p[f.kljuc] == null ? "" : String(p[f.kljuc]).trim();
        if (nova === stara) continue;
        if (f.broj) {
          const n = brojIzTeksta(nova);
          if (nova && n === null) {
            javi("Vrednost spora mora biti broj veći od nule.");
            unosi.get(f.kljuc).focus();
            return;
          }
          izmene[f.kljuc] = n;
        } else {
          izmene[f.kljuc] = nova;
        }
      }
      if (!Object.keys(izmene).length) {
        javi("Nijedno polje nije promenjeno.", "upozorenje");
        return;
      }
      if (izmene.naziv !== undefined && !izmene.naziv) {
        javi("Naziv predmeta ne može ostati prazan.");
        unosi.get("naziv").focus();
        return;
      }

      salje = true;
      sacuvaj.disabled = true;
      sacuvaj.textContent = "Čuva se…";
      poruka.hidden = true;

      try {
        await posalji(`/api/predmeti/${encodeURIComponent(predmetId)}`, {
          metod: "PATCH",
          // `if_updated_at` sprecava slepi „poslednji pobedjuje".
          telo: Object.assign({}, izmene,
                              p.updated_at ? { if_updated_at: p.updated_at } : {}),
          signal: ciklus.prekidac().signal,
        });
      } catch (err) {
        if (jePrekid(err) || ciklus.ugasen) return;
        salje = false;
        sacuvaj.disabled = false;
        sacuvaj.textContent = "Sačuvaj";
        if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
        if (err && err.status === 409) {
          // 409 NIJE kvar servera: neko je izmenio predmet u medjuvremenu.
          // Recenica mora reci sta se desilo i sta sad, inace advokat samo
          // ponavlja isto i opet dobija istu gresku.
          javi("Neko je izmenio ovaj predmet dok ste ga uređivali. Osvežite Dosije "
             + "da vidite tuđe izmene, pa unesite svoje ponovo — da ih ne biste "
             + "prebrisali.", "upozorenje");
          return;
        }
        if (err && err.vrsta === VRSTA.MREZA) {
          javi("Veza je prekinuta pre nego što je stigao odgovor. Izmena je možda "
             + "sačuvana — osvežite Dosije pre nego što pokušate ponovo.", "upozorenje");
          return;
        }
        javi("Izmena nije sačuvana. " + porukaZaKorisnika(err));
        return;
      }
      if (ciklus.ugasen) return;
      ostavi("Podaci o predmetu su izmenjeni.", "uspeh");
      osvezi();
    });
  });

  return omot;
}
