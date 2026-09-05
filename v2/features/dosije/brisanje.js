/* Vindex V2 — brisanje predmeta (B12).
 *
 * ─────────────────────────────────────────────────────────────────────────
 * 409 NIJE GRESKA SERVERA — TO JE DELIMICNO BRISANJE
 *
 * `DELETE /api/predmeti/{id}` je fail-closed po specifikaciji P1-5: `200` se
 * vraca ISKLJUCIVO kada je svaki entitet koji politika nalaze dokazano
 * uklonjen. Delimicno brisanje je `409`, bas zato da advokat ne bi dobio
 * umirujucu poruku o predmetu koji i dalje postoji.
 *
 * Zato ovaj ekran 409 prikazuje kao svoju recenicu: „predmet NIJE obrisan u
 * celosti i i dalje postoji". Sve drugo bi ponistilo smisao te odluke na
 * backendu.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * POTVRDA JE IMENOVANA I U DVA KORAKA. Prvi klik ne brise nista — otvara
 * potvrdu koja KAZE naziv predmeta i sta se sve uklanja. Nepovratna radnja
 * iz prvog pokusaja je zamka, narocito na dodirnom ekranu.
 */

import { posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { ostavi } from "../../platform/obavestenje.js";
import { idiNa } from "../../platform/router.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

export function kontrolaBrisanjaPredmeta(predmetId, naziv, ciklus) {
  const omot = el("div", "v2-brisanje");

  const trazi = el("button", "v2-dugme v2-dugme--opasno", "Obriši predmet");
  trazi.type = "button";
  omot.appendChild(trazi);

  ciklus.slusaj(trazi, "click", () => {
    if (omot.querySelector(".v2-potvrda")) return;
    trazi.hidden = true;

    const p = el("div", "v2-potvrda");
    p.setAttribute("role", "alertdialog");
    p.appendChild(el("p", "v2-potvrda__naslov", "Obrisati predmet „" + naziv + "”?"));
    p.appendChild(el("p", "v2-potvrda__telo",
      "Brišu se i spisi, hronologija, rokovi, zadaci i beleške ovog predmeta, "
      + "zajedno sa njihovim vektorima. Ovo se ne može opozvati."));

    const poruka = el("div", "v2-forma__poruka");
    poruka.setAttribute("role", "alert");
    poruka.hidden = true;

    const radnje = el("div", "v2-potvrda__radnje");
    const potvrdi = el("button", "v2-dugme v2-dugme--opasno", "Obriši predmet");
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
      potvrdi.textContent = "Briše se…";
      poruka.hidden = true;
      try {
        await posalji(`/api/predmeti/${encodeURIComponent(predmetId)}`, {
          metod: "DELETE", signal: ciklus.prekidac().signal,
        });
      } catch (err) {
        if (jePrekid(err) || ciklus.ugasen) return;
        potvrdi.disabled = false;
        potvrdi.textContent = "Obriši predmet";
        if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }

        poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
        if (err && err.status === 409) {
          // Backend namerno vraca 409 umesto umirujuceg 200 kada nije sve
          // uklonjeno. Ta odluka bi bila ponistena da je ovde prikazemo kao
          // obicnu gresku.
          poruka.textContent =
            "Predmet NIJE obrisan u celosti i i dalje postoji. Deo podataka nije "
            + "uklonjen, pa je brisanje zaustavljeno. Pokušajte ponovo; ako se "
            + "ponovi, predmet mora biti obrisan uz podršku.";
        } else if (err && err.vrsta === VRSTA.MREZA) {
          poruka.className = "v2-forma__poruka v2-forma__poruka--upozorenje";
          poruka.textContent =
            "Veza je prekinuta pre nego što je stigao odgovor. Predmet je možda "
            + "obrisan — proverite registar pre nego što pokušate ponovo.";
        } else {
          poruka.textContent = "Predmet nije obrisan. " + porukaZaKorisnika(err);
        }
        poruka.hidden = false;
        return;
      }
      if (ciklus.ugasen) return;
      ostavi("Predmet „" + naziv + "” je obrisan.", "uspeh");
      idiNa("predmeti");
    });
  });

  return omot;
}
