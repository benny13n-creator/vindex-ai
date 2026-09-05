/* Vindex V2 — izmena i arhiviranje klijenta (E4/E11).
 *
 * ─────────────────────────────────────────────────────────────────────────
 * „OBRISI" BI OVDE BILA NEISTINA
 *
 * `DELETE /klijenti/{id}` ne brise red — postavlja `status="soft_deleted"`,
 * `aktivan=false` i `deleted_at`. Klijent ostaje u bazi, sa svim vezama ka
 * predmetima, jer se podaci o klijentu cuvaju zbog roka retencije i zbog
 * predmeta koji ga i dalje pominju.
 *
 * Zato ovaj ekran radnju zove ARHIVIRANJE i tako je i opisuje. Dugme
 * „Obriši" iznad poziva koji arhivira bilo bi tvrdnja da su podaci nestali —
 * a advokat koji to poveruje pogresno bi odgovorio klijentu koji trazi
 * brisanje svojih podataka.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * POVERLJIVA POLJA SE NE NUDE NI ZA IZMENU. JMBG, PIB i broj pasosa su
 * sifrovani i ovaj ekran ih ne vidi; polje u koje bi se upisali „na slepo"
 * moglo bi da prepise postojecu vrednost praznim.
 */

import { posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { ostavi } from "../../platform/obavestenje.js";
import { idiNa } from "../../platform/router.js";

/** Polja koja server prihvata i koja ovaj ekran sme da vidi. */
const POLJA = Object.freeze([
  { kljuc: "ime", naziv: "Ime" },
  { kljuc: "prezime", naziv: "Prezime" },
  { kljuc: "firma", naziv: "Naziv firme" },
  { kljuc: "email", naziv: "Email" },
  { kljuc: "telefon", naziv: "Telefon" },
  { kljuc: "adresa", naziv: "Adresa" },
]);

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

/* ── Izmena (E4) ────────────────────────────────────────────────────────── */
export function kontrolaIzmeneKlijenta(klijentId, sirov, ciklus, osvezi) {
  const k = sirov || {};
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
      lab.htmlFor = "v2-kizm-" + f.kljuc;
      const unos = el("input", "v2-polje-unos__kontrola");
      unos.id = "v2-kizm-" + f.kljuc;
      unos.type = "text";
      unos.value = k[f.kljuc] == null ? "" : String(k[f.kljuc]);
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
    unosi.get("ime").focus();

    ciklus.slusaj(odustani, "click", () => {
      forma.remove(); otvori.hidden = false; otvori.focus();
    });

    let salje = false;
    ciklus.slusaj(forma, "submit", async (e) => {
      e.preventDefault();
      if (salje) return;

      // Salju se SAMO promenjena polja. Server `if req.ime:` ignorise prazna,
      // pa slanje svega ne bi obrisalo podatke — ali bi svaku izmenu
      // pretvorilo u prepis celog klijenta.
      const izmene = {};
      for (const f of POLJA) {
        const nova = unosi.get(f.kljuc).value.trim();
        const stara = k[f.kljuc] == null ? "" : String(k[f.kljuc]).trim();
        if (nova !== stara) izmene[f.kljuc] = nova;
      }
      if (!Object.keys(izmene).length) {
        poruka.className = "v2-forma__poruka v2-forma__poruka--upozorenje";
        poruka.textContent = "Nijedno polje nije promenjeno.";
        poruka.hidden = false;
        return;
      }

      salje = true;
      sacuvaj.disabled = true;
      sacuvaj.textContent = "Čuva se…";
      poruka.hidden = true;
      try {
        await posalji(`/klijenti/${encodeURIComponent(klijentId)}`, {
          metod: "PUT",
          // Server ocekuje ceo objekat; nepromenjena polja se salju zatecena,
          // da prazan string ne bi presao kao „obrisi ovo".
          telo: Object.assign({ tip: k.tip || "fizicko_lice" },
                              Object.fromEntries(POLJA.map(f =>
                                [f.kljuc, unosi.get(f.kljuc).value.trim()]))),
          signal: ciklus.prekidac().signal,
        });
      } catch (err) {
        if (jePrekid(err) || ciklus.ugasen) return;
        salje = false;
        sacuvaj.disabled = false;
        sacuvaj.textContent = "Sačuvaj";
        if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
        poruka.className = "v2-forma__poruka v2-forma__poruka--"
          + (err && err.vrsta === VRSTA.MREZA ? "upozorenje" : "greska");
        poruka.textContent = (err && err.vrsta === VRSTA.MREZA)
          ? "Veza je prekinuta pre nego što je stigao odgovor. Izmena je možda "
            + "sačuvana — osvežite stranicu pre nego što pokušate ponovo."
          : "Izmena nije sačuvana. " + porukaZaKorisnika(err);
        poruka.hidden = false;
        return;
      }
      if (ciklus.ugasen) return;
      ostavi("Podaci o klijentu su izmenjeni.", "uspeh");
      osvezi();
    });
  });

  return omot;
}

/* ── Arhiviranje (E11) ──────────────────────────────────────────────────── */
export function kontrolaArhiviranja(klijentId, naziv, ciklus) {
  const omot = el("div", "v2-brisanje");

  const trazi = el("button", "v2-dugme v2-dugme--opasno", "Arhiviraj klijenta");
  trazi.type = "button";
  omot.appendChild(trazi);

  ciklus.slusaj(trazi, "click", () => {
    if (omot.querySelector(".v2-potvrda")) return;
    trazi.hidden = true;

    const p = el("div", "v2-potvrda");
    p.setAttribute("role", "alertdialog");
    p.appendChild(el("p", "v2-potvrda__naslov", "Arhivirati klijenta „" + naziv + "”?"));
    // Recenica govori TACNO sta se desava: podaci ostaju.
    p.appendChild(el("p", "v2-potvrda__telo",
      "Klijent se sklanja sa spiska, ali se NE briše: podaci i veze sa predmetima "
      + "ostaju u bazi zbog roka čuvanja i zbog predmeta koji ga pominju. "
      + "Ovo nije brisanje podataka klijenta."));

    const poruka = el("div", "v2-forma__poruka");
    poruka.setAttribute("role", "alert");
    poruka.hidden = true;

    const radnje = el("div", "v2-potvrda__radnje");
    const potvrdi = el("button", "v2-dugme v2-dugme--opasno", "Arhiviraj");
    potvrdi.type = "button";
    const odustani = el("button", "v2-dugme v2-dugme--tiho", "Odustani");
    odustani.type = "button";
    radnje.append(potvrdi, odustani);
    p.append(poruka, radnje);
    omot.appendChild(p);
    potvrdi.focus();

    ciklus.slusaj(odustani, "click", () => {
      p.remove(); trazi.hidden = false; trazi.focus();
    });

    ciklus.slusaj(potvrdi, "click", async () => {
      potvrdi.disabled = true;
      potvrdi.textContent = "Arhivira se…";
      poruka.hidden = true;
      try {
        await posalji(`/klijenti/${encodeURIComponent(klijentId)}`, {
          metod: "DELETE", signal: ciklus.prekidac().signal,
        });
      } catch (err) {
        if (jePrekid(err) || ciklus.ugasen) return;
        potvrdi.disabled = false;
        potvrdi.textContent = "Arhiviraj";
        if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
        poruka.className = "v2-forma__poruka v2-forma__poruka--"
          + (err && err.vrsta === VRSTA.ZABRANJENO ? "upozorenje" : "greska");
        poruka.textContent = (err && err.vrsta === VRSTA.ZABRANJENO)
          ? "Vaša uloga u kancelariji ne dozvoljava arhiviranje klijenata."
          : "Klijent nije arhiviran. " + porukaZaKorisnika(err);
        poruka.hidden = false;
        return;
      }
      if (ciklus.ugasen) return;
      ostavi("Klijent „" + naziv + "” je arhiviran. Podaci su sačuvani.", "uspeh");
      idiNa("kancelarija");
    });
  });

  return omot;
}
