/* Vindex V2 — radnje unutar Dosijea: zadaci, rocista, beleske, brisanje spisa.
 *
 * ZASTO SU OVDE, A NE KAO NOVE CELINE
 * Kanon zakljucava PET celina Dosijea. Zadatak i rociste pripadaju celini
 * „Rokovi i zadaci" — ona se tako i zove; beleska pripada „Stanju", jer je
 * radna napomena o predmetu. Nijedno ne dobija sestu celinu, i nijedno se ne
 * pojavljuje kao ROK: zadatak je posao koji je advokat sam sebi zadao,
 * rociste je zakazan termin, a rok je pravna posledica. Ta tri se ne mesaju.
 *
 * SVAKA RADNJA KOJA MENJA PODATKE MORA:
 *   - da se zakljuca pre poziva (dvostruko slanje je duplirani zapis)
 *   - da razlikuje mreznu gresku od odbijanja (kod pisanja mrezni kvar NIJE
 *     dokaz da se nista nije upisalo)
 *   - da posle uspeha osvezi Dosije sa servera, a ne da doslika lokalno
 *     stanje: prikazati zapis iz memorije znaci tvrditi nesto o bazi bez
 *     dokaza da je tamo stigao.
 */

import { posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { ostavi } from "../../platform/obavestenje.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

/**
 * Zajednicki omotac za radnju koja pise.
 *
 * @param {object} o  { dugme, ciklus, poruka, posle, radi }
 */
async function izvrsi({ dugme, tekstUToku, tekstNormalan, poruka, ciklus, poziv, naUspeh, naGresku, imeRadnje, neuspeh }) {
  dugme.disabled = true;
  const staro = dugme.textContent;
  dugme.textContent = tekstUToku;
  poruka.hidden = true;
  try {
    const r = await poziv(ciklus.prekidac().signal);
    if (ciklus.ugasen) return;
    naUspeh(r);
  } catch (err) {
    if (jePrekid(err) || ciklus.ugasen) return;
    dugme.disabled = false;
    dugme.textContent = tekstNormalan || staro;
    if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
    // Radnja koja zna da neki status NIJE kvar (npr. 404 pri brisanju: stavka
    // vise ne postoji) sama ga obradi i vrati `true`.
    if (typeof naGresku === "function" && naGresku(err) === true) return;
    poruka.className = "v2-forma__poruka v2-forma__poruka--"
      + (err && err.vrsta === VRSTA.MREZA ? "upozorenje" : "greska");
    // `neuspeh` postoji zato sto se radnje razlicito slazu u recenici:
    // „Beleska nije sacuvano" nije srpski. Podrazumevani tekst vazi za upis.
    poruka.textContent = neuspeh
      ? neuspeh(err)
      : (err && err.vrsta === VRSTA.MREZA)
        // Kod pisanja mrezni kvar NIJE dokaz da se nista nije upisalo.
        ? "Veza je prekinuta pre nego što je stigao odgovor. " + imeRadnje
          + " je možda sačuvano — osvežite Dosije pre nego što pokušate ponovo."
        : imeRadnje + " nije sačuvano. " + porukaZaKorisnika(err);
    poruka.hidden = false;
  }
}

/* ── Nov zadatak ────────────────────────────────────────────────────────── */
export function obrazacZadatka(predmetId, ciklus, osvezi) {
  const okvir = el("div", "v2-radnja");
  const lab = el("label", "v2-polje-unos__labela", "Nov zadatak");
  lab.htmlFor = "v2-zadatak-naziv";

  const red = el("div", "v2-radnja__red");
  const naziv = el("input", "v2-polje-unos__kontrola");
  naziv.id = "v2-zadatak-naziv";
  naziv.type = "text";
  naziv.placeholder = "Šta treba uraditi";
  naziv.maxLength = 200;

  const rok = el("input", "v2-polje-unos__kontrola v2-radnja__datum");
  rok.type = "date";
  rok.id = "v2-zadatak-rok";
  rok.setAttribute("aria-label", "Rok zadatka (opciono)");

  const dugme = el("button", "v2-dugme", "Dodaj");
  dugme.type = "button";
  red.append(naziv, rok, dugme);

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;
  okvir.append(lab, red, poruka);

  ciklus.slusaj(dugme, "click", () => {
    const t = naziv.value.trim();
    if (t.length < 2) {
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = "Naziv zadatka mora imati najmanje 2 znaka.";
      poruka.hidden = false;
      naziv.focus();
      return;
    }
    izvrsi({
      dugme, tekstUToku: "Dodaje se…", tekstNormalan: "Dodaj", poruka, ciklus,
      imeRadnje: "Zadatak",
      poziv: (signal) => posalji("/api/zadaci/kreiraj", {
        telo: {
          naziv: t,
          predmet_id: predmetId,
          rok_datum: rok.value || null,
        }, signal,
      }),
      naUspeh: () => { ostavi("Zadatak je dodat.", "uspeh"); osvezi(); },
    });
  });

  return okvir;
}

/* ── Novo rociste ───────────────────────────────────────────────────────── */
export function obrazacRocista(predmetId, ciklus, osvezi) {
  const okvir = el("div", "v2-radnja");
  const lab = el("label", "v2-polje-unos__labela", "Novo ročište");
  lab.htmlFor = "v2-rociste-sud";

  const red = el("div", "v2-radnja__red");
  const sud = el("input", "v2-polje-unos__kontrola");
  sud.id = "v2-rociste-sud";
  sud.type = "text";
  sud.placeholder = "Sud";
  sud.maxLength = 300;

  const datum = el("input", "v2-polje-unos__kontrola v2-radnja__datum");
  datum.type = "date";
  datum.id = "v2-rociste-datum";
  datum.setAttribute("aria-label", "Datum ročišta");

  const vreme = el("input", "v2-polje-unos__kontrola v2-radnja__vreme");
  vreme.type = "time";
  vreme.id = "v2-rociste-vreme";
  vreme.setAttribute("aria-label", "Vreme ročišta (opciono)");

  const dugme = el("button", "v2-dugme", "Zakaži");
  dugme.type = "button";
  red.append(sud, datum, vreme, dugme);

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;
  okvir.append(lab, red, poruka);

  ciklus.slusaj(dugme, "click", () => {
    // Sud i datum su OBAVEZNI po serverskom ugovoru — postuju se ovde da
    // korisnik ne dobije 422 koji je mogao da izbegne.
    const nedostaje = [];
    if (!sud.value.trim()) nedostaje.push("sud");
    if (!datum.value) nedostaje.push("datum");
    if (nedostaje.length) {
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = "Ročište traži " + nedostaje.join(" i ") + ".";
      poruka.hidden = false;
      (nedostaje[0] === "sud" ? sud : datum).focus();
      return;
    }
    izvrsi({
      dugme, tekstUToku: "Zakazuje se…", tekstNormalan: "Zakaži", poruka, ciklus,
      imeRadnje: "Ročište",
      poziv: (signal) => posalji("/api/rocista", {
        telo: {
          predmet_id: predmetId,
          sud: sud.value.trim(),
          datum: datum.value,
          vreme: vreme.value || null,
        }, signal,
      }),
      naUspeh: () => { ostavi("Ročište je zakazano.", "uspeh"); osvezi(); },
    });
  });

  return okvir;
}

/* ── Brisanje napomene ────────────────────────────────────── */
/**
 * Napomene stizu iz dve tabele (v. `uNapomene`), pa se i brisu na dve
 * putanje. Advokat tu razliku NE VIDI: za njega je to jedna napomena i jedno
 * dugme. `izvor` bira rutu i nista vise.
 *
 * Potvrda je u dva koraka jer brisanje nije opozivo. 404 znaci da napomena
 * vise ne postoji — to nije greska koju treba prijaviti kao kvar, nego stanje
 * koje ekran treba da uskladi, pa se u tom slucaju samo osvezava.
 */
export function kontrolaBrisanjaNapomene(predmetId, napomena, ciklus, osvezi) {
  const omot = el("span", "v2-beleska__brisi");
  const trazi = el("button", "v2-tekst-akcija v2-tekst-akcija--opasno", "Obriši");
  trazi.type = "button";
  trazi.setAttribute("aria-label", "Obriši napomenu");
  omot.appendChild(trazi);

  const putanja = napomena.izvor === "komentar"
    ? `/komentari/${encodeURIComponent(napomena.id)}`
    : `/api/predmeti/${encodeURIComponent(predmetId)}/beleske/${encodeURIComponent(napomena.id)}`;

  ciklus.slusaj(trazi, "click", () => {
    if (omot.querySelector(".v2-potvrda")) return;
    trazi.hidden = true;

    const p = el("div", "v2-potvrda v2-potvrda--usko");
    p.setAttribute("role", "alertdialog");
    p.appendChild(el("p", "v2-potvrda__naslov", "Obrisati ovu napomenu?"));

    const poruka = el("div", "v2-forma__poruka");
    poruka.setAttribute("role", "alert");
    poruka.hidden = true;

    const radnje = el("div", "v2-potvrda__radnje");
    const potvrdi = el("button", "v2-dugme v2-dugme--opasno", "Obriši");
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

    ciklus.slusaj(potvrdi, "click", () => {
      izvrsi({
        dugme: potvrdi, tekstUToku: "Briše se…", tekstNormalan: "Obriši",
        poruka, ciklus, imeRadnje: "Napomena",
        poziv: (signal) => posalji(putanja, { metod: "DELETE", signal }),
        naUspeh: () => { ostavi("Napomena je obrisana.", "uspeh"); osvezi(); },
        neuspeh: (err) => (err && err.vrsta === VRSTA.MREZA)
          // Mrezni kvar pri brisanju NIJE dokaz da napomena stoji.
          ? "Veza je prekinuta pre nego što je stigao odgovor. Napomena je "
            + "možda obrisana — osvežite Dosije pre nego što pokušate ponovo."
          : "Napomena nije obrisana. " + porukaZaKorisnika(err),
        naGresku: (err) => {
          // 404: napomena vise ne postoji (obrisana drugde ili dvoklik).
          // Ekran se usklađuje sa bazom umesto da prijavi kvar koji nije kvar.
          if (err && err.status === 404) { osvezi(); return true; }
          return false;
        },
      });
    });
  });

  return omot;
}

/* ── Nova beleska ───────────────────────────────────────────────────────── */
export function obrazacBeleske(predmetId, ciklus, osvezi) {
  const okvir = el("div", "v2-radnja");
  const lab = el("label", "v2-polje-unos__labela", "Nova beleška");
  lab.htmlFor = "v2-beleska";

  const polje = el("textarea", "v2-polje-unos__kontrola");
  polje.id = "v2-beleska";
  polje.rows = 3;
  polje.maxLength = 5000;
  polje.placeholder = "Šta je zabeleženo";

  const dugme = el("button", "v2-dugme", "Sačuvaj belešku");
  dugme.type = "button";

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;
  okvir.append(lab, polje, poruka, dugme);

  ciklus.slusaj(dugme, "click", () => {
    const t = polje.value.trim();
    if (!t) {
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = "Prazna beleška se ne čuva.";
      poruka.hidden = false;
      polje.focus();
      return;
    }
    izvrsi({
      dugme, tekstUToku: "Čuva se…", tekstNormalan: "Sačuvaj belešku", poruka, ciklus,
      imeRadnje: "Beleška",
      poziv: (signal) => posalji(
        `/api/predmeti/${encodeURIComponent(predmetId)}/beleske`,
        { telo: { sadrzaj: t }, signal }),
      naUspeh: () => { ostavi("Beleška je sačuvana.", "uspeh"); osvezi(); },
    });
  });

  return okvir;
}

/* ── Brisanje spisa ─────────────────────────────────────────────────────── */
/**
 * Brisanje spisa trazi POTVRDU U DVA KORAKA, i to imenovanu.
 *
 * Prvi klik ne brise nista — otvara potvrdu koja KAZE naziv spisa. Brisanje
 * dokumenta je nepovratno i uklanja i njegove vektore; dugme koje to radi iz
 * prvog pokusaja je zamka, narocito na dodirnom ekranu.
 */
export function kontrolaBrisanjaSpisa(predmetId, spis, ciklus, osvezi) {
  const omot = el("span", "v2-spisi__brisi");
  const trazi = el("button", "v2-tekst-akcija v2-tekst-akcija--opasno", "Obriši");
  trazi.type = "button";
  trazi.setAttribute("aria-label", "Obriši spis " + spis.naziv);
  omot.appendChild(trazi);

  ciklus.slusaj(trazi, "click", () => {
    if (omot.querySelector(".v2-potvrda")) return;
    trazi.hidden = true;

    const p = el("div", "v2-potvrda");
    p.setAttribute("role", "alertdialog");
    p.appendChild(el("p", "v2-potvrda__naslov", "Obrisati „" + spis.naziv + "”?"));
    p.appendChild(el("p", "v2-potvrda__telo",
      "Spis se briše zajedno sa izdvojenim tekstom i njegovim vektorima. "
      + "Ovo se ne može opozvati."));

    const poruka = el("div", "v2-forma__poruka");
    poruka.setAttribute("role", "alert");
    poruka.hidden = true;

    const radnje = el("div", "v2-potvrda__radnje");
    const potvrdi = el("button", "v2-dugme v2-dugme--opasno", "Obriši spis");
    potvrdi.type = "button";
    const odustani = el("button", "v2-dugme v2-dugme--tiho", "Odustani");
    odustani.type = "button";
    radnje.append(potvrdi, odustani);
    p.append(poruka, radnje);
    omot.appendChild(p);
    potvrdi.focus();

    ciklus.slusaj(odustani, "click", () => { p.remove(); trazi.hidden = false; trazi.focus(); });
    ciklus.slusaj(potvrdi, "click", () => {
      izvrsi({
        dugme: potvrdi, tekstUToku: "Briše se…", tekstNormalan: "Obriši spis",
        poruka, ciklus, imeRadnje: "Brisanje spisa",
        poziv: (signal) => posalji(
          `/api/predmeti/${encodeURIComponent(predmetId)}/dokumenti/${encodeURIComponent(spis.id)}`,
          { metod: "DELETE", signal }),
        naUspeh: () => { ostavi("Spis je obrisan.", "uspeh"); osvezi(); },
      });
    });
  });

  return omot;
}
