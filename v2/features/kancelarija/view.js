/* Vindex V2 — prostor KANCELARIJA.
 *
 * Sve sto nije pravni rad: nalog, klijenti, naplata, tim. Cetiri imenovane
 * celine na jednoj povrsini, isto kao Dosije — bez tabova i bez table sa
 * brojevima.
 *
 * BROJ SME DA STOJI SAMO UZ PITANJE NA KOJE ODGOVARA. „Fakturisano 120.000"
 * nista ne znaci dok se ne kaze da je to odgovor na „koliko sam ispostavio
 * racuna ovog meseca". Zato svaki iznos ovde nosi svoju recenicu, a nijedan
 * nema traku, procenat ni trend.
 *
 * DEO KOJI NIJE UCITAN TO I KAZE. Cetiri izvora padaju odvojeno; pao deo
 * prikazuje poruku, a ne prazan spisak. Prazan spisak je tvrdnja da nema
 * podataka, a to je posle pada upita neistina.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu, odjavi } from "../../platform/auth.js";
import { idiNa, putanjaZa } from "../../platform/router.js";
import { ucitajKancelariju } from "./api.js";
import { uNalog, uKlijente, uNaplatu, uTim, uPlan } from "../../domain/kancelarija.js";
import { procitajPlan } from "../../platform/nalog.js";
import { blokoviNaplate } from "./naplata.js";
import { elementPoruke } from "../../platform/obavestenje.js";

export const CELINE = Object.freeze([
  { kljuc: "nalog", naziv: "Nalog" },
  { kljuc: "klijenti", naziv: "Klijenti" },
  { kljuc: "naplata", naziv: "Naplata" },
  { kljuc: "tim", naziv: "Tim kancelarije" },
]);

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}
function nevidljivo(t) { return el("span", "v2-nevidljivo", t); }

function celina(kljuc, naziv) {
  const s = el("section", "v2-celina");
  s.dataset.celina = kljuc;
  const h = el("h2", "v2-celina__naslov", naziv);
  h.id = "celina-" + kljuc;
  s.appendChild(h);
  s.setAttribute("aria-labelledby", h.id);
  return s;
}

function prazno(t) { return el("p", "v2-celina__prazno", t); }

/** Deo koji nije stigao — razlikuje se od dela koji je stigao prazan. */
function nijeUcitano(sta, e) {
  const d = el("div", "v2-poruka");
  d.appendChild(el("p", "v2-poruka__naslov", sta + " nije učitano"));
  d.appendChild(el("p", "v2-poruka__telo",
    porukaZaKorisnika(e) + " Ovo ne znači da podataka nema."));
  return d;
}

/**
 * Naziv i vrednost su JEDAN par u jednoj celiji mreze. Kao dve odvojene
 * celije, `auto-fit` ih razbacuje u razlicite kolone, pa labela stoji levo a
 * vrednost dve kolone dalje.
 */
function poljeVrednost(naziv, vrednost, mono) {
  const par = el("div", "v2-polja__par");
  par.appendChild(el("dt", "v2-polje", naziv));
  par.appendChild(el("dd", "v2-polja__v" + (mono ? " v2-mono" : ""), vrednost));
  return [par];
}

/* ── Nalog ──────────────────────────────────────────────────────────────── */
function sekcijaNalog(deo, ciklus) {
  const s = celina("nalog", "Nalog");
  if (deo.pao) { s.appendChild(nijeUcitano("Podatak o nalogu", deo.greska)); return s; }
  const n = uNalog(deo.podaci);

  const dl = el("dl", "v2-polja");
  const redovi = [["Email", n.email, false], ["Plan", n.plan, false]];
  if (n.krediti !== null) {
    // Osnivacki nalog ima 9999 kredita — broj bez znacenja, pa se „od koliko"
    // ne prikazuje. Za ostale se prikazuje, jer je granica stvarna.
    redovi.push(["Preostalo AI upita",
      n.kreditiUkupno !== null ? `${n.krediti} od ${n.kreditiUkupno}` : String(n.krediti), true]);
  }
  for (const [naziv, v, mono] of redovi) {
    if (!v) continue;
    for (const x of poljeVrednost(naziv, v, mono)) dl.appendChild(x);
  }
  s.appendChild(dl);

  // ── Plan i potrosnja (H9) ──
  // Podatak dolazi iz onoga sto je boot vec procitao: `/api/plan/status` ima
  // granicu od 60 na sat i ne sme se zvati ponovo zbog prikaza.
  const sirovPlan = procitajPlan();
  const bPlan = el("div", "v2-podblok");
  bPlan.appendChild(el("h3", "v2-natkapa", "Plan i potrošnja"));
  if (!sirovPlan) {
    // Bez podatka se plan NE pogadja iz `/api/me`: tamo stoji drugi pojam.
    bPlan.appendChild(prazno("Podaci o planu nisu učitani pri pokretanju. "
      + "Osvežite stranicu da biste ih videli."));
  } else {
    const pl = uPlan(sirovPlan);
    const dl2 = el("dl", "v2-polja");
    const redovi2 = [["Plan", pl.naziv, false]];
    if (pl.dodaci.length) redovi2.push(["Dodaci", pl.dodaci.join(", "), false]);
    // Istekao datum se IMENUJE kao istek, ne kao rok koji još teče.
    if (pl.istice) {
      redovi2.push([pl.isteklo === true ? "Pretplata istekla" : "Pretplata važi do",
                    pl.istice, true]);
    }
    if (pl.dodatnihMesta !== null && pl.dodatnihMesta > 0) {
      redovi2.push(["Dodatnih mesta", String(pl.dodatnihMesta), true]);
    }
    for (const [naziv, v, mono] of redovi2) {
      if (!v) continue;
      for (const x of poljeVrednost(naziv, v, mono)) dl2.appendChild(x);
    }
    bPlan.appendChild(dl2);

    if (!pl.potrosnja.length) {
      bPlan.appendChild(prazno(pl.mesec
        ? `U mesecu ${pl.mesec} još nema zabeležene potrošnje.`
        : "Nema zabeležene potrošnje."));
    } else {
      if (pl.mesec) bPlan.appendChild(prazno("Potrošnja u mesecu " + pl.mesec + "."));
      const ul2 = el("ul", "v2-lista-tanka");
      for (const u of pl.potrosnja) {
        const li = el("li", "v2-plan__stavka");
        li.appendChild(document.createTextNode(u.naziv));
        const meta = el("span", "v2-plan__meta");
        if (u.koriscenja !== null) {
          meta.appendChild(el("span", "v2-mono",
            " " + u.koriscenja + (u.mesecniLimit !== null ? " / " + u.mesecniLimit : "")));
        }
        // `null` granica znaci „nije objavljena", NE „neograniceno" — pa se
        // nista i ne pise umesto nje.
        li.appendChild(meta);
        ul2.appendChild(li);
      }
      bPlan.appendChild(ul2);
    }
  }
  s.appendChild(bPlan);

  const radnje = el("div", "v2-forma__radnje");
  const izadji = el("button", "v2-dugme", "Odjavi se");
  izadji.type = "button";
  ciklus.slusaj(izadji, "click", () => odjavi());
  radnje.appendChild(izadji);
  s.appendChild(radnje);
  return s;
}

/* ── Klijenti ───────────────────────────────────────────────────────────── */
function sekcijaKlijenti(deo, ciklus) {
  const s = celina("klijenti", "Klijenti");
  if (deo.pao) { s.appendChild(nijeUcitano("Spisak klijenata", deo.greska)); return s; }

  // Otvaranje klijenta je radnja ovog prostora i zato stoji uz spisak, a ne
  // u globalnoj navigaciji: klijenti su socivo Kancelarije, ne peti prostor.
  const noviK = el("a", "v2-dugme", "Nov klijent");
  noviK.href = putanjaZa("klijent", "nov");
  ciklus.slusaj(noviK, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("klijent", "nov");
  });

  const k = uKlijente(deo.podaci);
  if (!k.redovi.length) {
    s.appendChild(prazno("Još nema evidentiranih klijenata."));
    s.appendChild(noviK);
    return s;
  }
  if (k.ukupno !== null) {
    s.appendChild(el("p", "v2-reg__broj",
      k.ukupno === 1 ? "1 klijent" : `${k.ukupno} klijenata`));
  }
  const ul = el("ul", "v2-klijenti");
  for (const x of k.redovi) {
    const li = el("li", "v2-klijenti__red");

    // Red vodi u DOSIJE klijenta. Prava <a href> veza: srednji klik i „otvori
    // u novoj kartici" rade nativno. Klijent bez id-ja NE postaje veza —
    // lazan deep link je gori od izostanka veze.
    const naziv = el("span", "v2-klijenti__naziv");
    if (x.id) {
      const veza = el("a", "v2-reg__veza", x.naziv);
      veza.href = putanjaZa("klijent", x.id);
      ciklus.slusaj(veza, "click", (e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        e.preventDefault();
        idiNa("klijent", x.id);
      });
      naziv.appendChild(veza);
    } else {
      naziv.textContent = x.naziv;
    }
    li.appendChild(naziv);

    const meta = el("span", "v2-klijenti__meta");
    if (x.vrsta) {
      const v = el("span", "v2-klijenti__vrsta");
      v.appendChild(nevidljivo("Vrsta: "));
      v.appendChild(document.createTextNode(x.vrsta));
      meta.appendChild(v);
    }
    // Kontakt se prikazuje samo ako postoji — prazan red bi tvrdio da je polje
    // ostavljeno nepopunjeno, a klijent kontakt mozda i nema.
    if (x.email) {
      const e2 = el("span", "");
      e2.appendChild(nevidljivo("Email: "));
      e2.appendChild(document.createTextNode(x.email));
      meta.appendChild(e2);
    }
    if (x.telefon) {
      const t = el("span", "");
      t.appendChild(nevidljivo("Telefon: "));
      t.appendChild(document.createTextNode(x.telefon));
      meta.appendChild(t);
    }
    li.appendChild(meta);
    ul.appendChild(li);
  }
  s.appendChild(ul);
  if (k.ukupno !== null && k.ukupno > k.redovi.length) {
    s.appendChild(el("p", "v2-celina__prazno",
      `Prikazano ${k.redovi.length} od ${k.ukupno}. Ostale nađite kroz pretragu (Ctrl+K).`));
  }
  s.appendChild(noviK);
  return s;
}

/* ── Naplata ────────────────────────────────────────────────────────────── */
function sekcijaNaplata(deo, rad, ciklus, osvezi) {
  const s = celina("naplata", "Naplata");
  if (deo.pao) { s.appendChild(nijeUcitano("Pregled naplate", deo.greska)); return s; }
  const b = uNaplatu(deo.podaci);
  // Odsustvo mesecnog pregleda se saopstava, ali NE prekida celinu: tajmer i
  // evidentiranje rada moraju biti dostupni i kad mesec jos nema nijedan unos
  // — to je bas trenutak kada advokat prvi put unosi rad. Rani izlaz je istu
  // gresku vec jednom napravio u celini „Rokovi i zadaci".
  if (!b.stavke.length) {
    s.appendChild(prazno("Za tekući mesec nema evidentiranog rada ni faktura."));
  }
  if (b.mesec) s.appendChild(el("p", "v2-reg__broj", "Tekući mesec: " + b.mesec));
  const ul = el("ul", "v2-naplata");
  for (const x of b.stavke) {
    const li = el("li", "v2-naplata__red");
    li.appendChild(el("span", "v2-naplata__naziv", x.naziv));
    li.appendChild(el("span", "v2-naplata__iznos v2-mono", x.iznos));
    // Recenica uz broj postoji da broj ne bi bio KPI bez odluke.
    li.appendChild(el("span", "v2-naplata__pitanje", x.pitanje));
    ul.appendChild(li);
  }
  s.appendChild(ul);

  // Tajmer, evidentiranje rada i fakture (F4/F5). Naplata je posao
  // kancelarije, pa zivi ovde — Dosije zadrzava svojih pet celina.
  if (rad && osvezi) s.appendChild(blokoviNaplate(rad, ciklus, osvezi));

  return s;
}

/* ── Tim ────────────────────────────────────────────────────────────────── */
function sekcijaTim(deo) {
  const s = celina("tim", "Tim kancelarije");
  if (deo.pao) { s.appendChild(nijeUcitano("Podatak o kancelariji", deo.greska)); return s; }
  const t = uTim(deo.podaci);
  if (t.stanje !== "aktivan") {
    s.appendChild(prazno(t.poruka));
    return s;
  }
  if (t.firma) s.appendChild(el("p", "v2-reg__broj", t.firma));
  if (!t.clanovi.length) {
    s.appendChild(prazno("U kancelariji nema drugih članova."));
    return s;
  }
  const ul = el("ul", "v2-klijenti");
  for (const c of t.clanovi) {
    const li = el("li", "v2-klijenti__red");
    li.appendChild(el("span", "v2-klijenti__naziv", c.email));
    const meta = el("span", "v2-klijenti__meta");
    if (c.uloga) meta.appendChild(el("span", "v2-klijenti__vrsta", c.uloga));
    if (c.stanje) meta.appendChild(el("span", "", c.stanje));
    li.appendChild(meta);
    ul.appendChild(li);
  }
  s.appendChild(ul);
  return s;
}

/* ── Montiranje ─────────────────────────────────────────────────────────── */
export function montirajKancelariju(kontejner) {
  const ciklus = napraviCiklus();

  // Posle upisa (tajmer, evidentiran rad, faktura) prostor se ponovo cita SA
  // SERVERA. Doslikati novo stanje iz memorije znacilo bi tvrditi nesto o
  // bazi bez dokaza da je tamo stiglo. Ponovo se cita SAMO ovaj prostor —
  // `location.reload()` bi ponovo pokrenuo ceo boot i potrosio jos jedan
  // poziv `/api/plan/status`, koji ima granicu od 60 na sat.

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--predmet");
  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Kancelarija");
  h1.id = "v2-naslov-kancelarija";
  zaglavlje.appendChild(h1);
  unutra.appendChild(zaglavlje);

  // Finansije i Tarife su POGLEDI ovog prostora, ne nove destinacije u
  // globalnoj navigaciji.
  const prekidac = el("nav", "v2-prekidac");
  prekidac.setAttribute("aria-label", "Kancelarija");
  const ovde = el("span", "v2-prekidac__stavka v2-prekidac__stavka--aktivna", "Kancelarija");
  ovde.setAttribute("aria-current", "page");
  const kaFin = el("a", "v2-prekidac__stavka", "Finansije");
  kaFin.href = putanjaZa("kancelarija", "finansije");
  ciklus.slusaj(kaFin, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("kancelarija", "finansije");
  });
  const kaTar = el("a", "v2-prekidac__stavka", "Tarife");
  kaTar.href = putanjaZa("kancelarija", "tarife");
  ciklus.slusaj(kaTar, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("kancelarija", "tarife");
  });
  prekidac.append(ovde, kaFin, kaTar);
  unutra.appendChild(prekidac);

  const sadrzaj = el("div", "v2-kancelarija");
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  sadrzaj.setAttribute("aria-labelledby", "v2-naslov-kancelarija");
  unutra.appendChild(sadrzaj);
  kontejner.appendChild(unutra);
  document.title = "Kancelarija · Vindex";

  async function ucitajIPrikazi() {
    sadrzaj.replaceChildren(prazno("Učitava se…"));
    const prekidac = ciklus.prekidac();
    let d;
    try {
      d = await ucitajKancelariju({ signal: prekidac.signal });
    } catch (e) {
      if (jePrekid(e) || ciklus.ugasen) return;
      if (e && e.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      sadrzaj.replaceChildren(nijeUcitano("Kancelarija", e));
      return;
    }
    if (ciklus.ugasen) return;

    const okvir = document.createDocumentFragment();
    const izPrethodne = elementPoruke();
    if (izPrethodne) okvir.appendChild(izPrethodne);
    okvir.appendChild(sekcijaNalog(d.nalog, ciklus));
    okvir.appendChild(sekcijaKlijenti(d.klijenti, ciklus));
    okvir.appendChild(sekcijaNaplata(d.naplata, d.rad, ciklus, ucitajIPrikazi));
    okvir.appendChild(sekcijaTim(d.tim));
    sadrzaj.replaceChildren(okvir);
  }

  ucitajIPrikazi();

  return ciklus;
}
