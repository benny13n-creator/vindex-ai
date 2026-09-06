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
import { naPrijavu, odjavi, token } from "../../platform/auth.js";
import { idiNa, putanjaZa } from "../../platform/router.js";
import { ucitajKancelariju } from "./api.js";
import { uNalog, uKlijente, uNaplatu, uTim, uPlan, uMesta, uIstoriju } from "../../domain/kancelarija.js";
import { procitajPlan } from "../../platform/nalog.js";
import { blokoviNaplate } from "./naplata.js";
import { elementPoruke, ostavi } from "../../platform/obavestenje.js";
import { dohvati, posalji } from "../../platform/http.js";
import { blokUvozaKlijenata } from "./uvozKlijenata.js";
import { ucitajPortfolio, sadrzajPortfolia } from "./portfolio.js";

export const CELINE = Object.freeze([
  { kljuc: "nalog", naziv: "Nalog" },
  { kljuc: "klijenti", naziv: "Klijenti" },
  { kljuc: "naplata", naziv: "Naplata" },
  { kljuc: "tim", naziv: "Tim kancelarije" },
  { kljuc: "portfolio", naziv: "Portfolio" },
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

  // H8 (Z017.2 execution queue #9) -- postojeca, kompletna backend
  // sposobnost (GET /api/export/complete, ZIP sa predmeti/klijenti/billing/
  // dokumenti-metadata/beleske/rocista/hronologija) nije imala V2 povrsinu.
  // NE tvrdi se da je izvoz "zakonski obavezan" (§10) -- ovo je jednostavno
  // postojeca korisnicka funkcija koju korisnik legitimno moze da koristi.
  //
  // `dohvati()` parsira odgovor kao JSON i ne odgovara za binarni ZIP, pa
  // ide sirov fetch + Bearer header (isti obrazac kao legacy
  // static/vindex.js:822 exportSviPodaci, dokazano radi u produkciji) --
  // ruta zahteva Authorization header, obican <a href> navigacija ga ne bi
  // ponela.
  const izvoz = el("button", "v2-dugme v2-dugme--tiho", "Preuzmi moje podatke");
  izvoz.type = "button";
  ciklus.slusaj(izvoz, "click", async () => {
    izvoz.disabled = true;
    izvoz.textContent = "Priprema se…";
    try {
      const t = token();
      const odgovor = await fetch("/api/export/complete", {
        headers: t ? { Authorization: "Bearer " + t } : {},
        credentials: "same-origin",
      });
      if (!odgovor.ok) throw new Error("HTTP " + odgovor.status);
      const blob = await odgovor.blob();
      const url = URL.createObjectURL(blob);
      const cd = odgovor.headers.get("Content-Disposition") || "";
      const m = cd.match(/filename="([^"]+)"/);
      const a = el("a");
      a.href = url;
      a.download = m ? m[1] : "vindex-export.zip";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      ostavi("Izvoz je preuzet.", "uspeh");
    } catch (err) {
      ostavi("Izvoz nije uspeo. Pokušajte ponovo.", "greska");
    } finally {
      izvoz.disabled = false;
      izvoz.textContent = "Preuzmi moje podatke";
    }
  });
  radnje.appendChild(izvoz);

  s.appendChild(radnje);
  return s;
}

/* ── Klijenti ───────────────────────────────────────────────────────────── */
function sekcijaKlijenti(deo, ciklus, osvezi) {
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
    s.appendChild(blokUvozaKlijenata(ciklus, osvezi));
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
  s.appendChild(blokUvozaKlijenata(ciklus, osvezi));
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

/* ── Tim ────────────────────────────────────────────────────────────────── *
 * F3 (Z017.2 SS9) -- prikaz je oduvek bio potpun; upravljanje (pozovi/
 * suspenduj/reaktiviraj/ukloni/prihvati/odbij) NIJE postojalo u V2 uopste,
 * bez obzira na `no_firma`. Ovde se dodaju stvarne radnje, svaka pozivom
 * postojece backend rute (`routers/kancelarija.py`) koja vec sprovodi
 * ovlascenje -- dugmad se ovde SAMO uslovljavaju istim pravilom (jeAdmin,
 * status clana) da nikad ne ponude radnju koju server nece izvrsiti.
 */

function dugme(tekst, klasa) {
  const b = el("button", klasa || "v2-dugme v2-dugme--tiho", tekst);
  b.type = "button";
  return b;
}

function redAkcija(c, ciklus, osvezi) {
  const akcije = el("span", "v2-klijenti__akcije");
  if (c.stanje === "ACTIVE") {
    const b = dugme("Suspenduj", "v2-dugme v2-dugme--opasno");
    ciklus.slusaj(b, "click", async () => {
      b.disabled = true;
      try {
        await posalji(`/api/kancelarija/suspenduj/${encodeURIComponent(c.id)}`, {
          signal: ciklus.prekidac().signal,
        });
        if (ciklus.ugasen) return;
        ostavi(`${c.email} suspendovan(a).`, "uspeh");
        osvezi();
      } catch (err) {
        if (jePrekid(err) || ciklus.ugasen) return;
        b.disabled = false;
        if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
        ostavi("Suspenzija nije uspela. " + porukaZaKorisnika(err), "greska");
      }
    });
    akcije.appendChild(b);
  } else if (c.stanje === "SUSPENDED") {
    const b = dugme("Reaktiviraj");
    ciklus.slusaj(b, "click", async () => {
      b.disabled = true;
      try {
        await posalji(`/api/kancelarija/reaktiviraj/${encodeURIComponent(c.id)}`, {
          signal: ciklus.prekidac().signal,
        });
        if (ciklus.ugasen) return;
        ostavi(`${c.email} reaktiviran(a).`, "uspeh");
        osvezi();
      } catch (err) {
        if (jePrekid(err) || ciklus.ugasen) return;
        b.disabled = false;
        if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
        ostavi("Reaktivacija nije uspela. " + porukaZaKorisnika(err), "greska");
      }
    });
    akcije.appendChild(b);
  }
  if (c.stanje === "ACTIVE" || c.stanje === "SUSPENDED" || c.stanje === "INVITED") {
    const u = dugme("Ukloni", "v2-dugme v2-dugme--opasno");
    ciklus.slusaj(u, "click", async () => {
      if (!window.confirm(`Ukloniti ${c.email} iz kancelarije?`)) return;
      u.disabled = true;
      try {
        await posalji(`/api/kancelarija/ukloni/${encodeURIComponent(c.id)}`, {
          metod: "DELETE", signal: ciklus.prekidac().signal,
        });
        if (ciklus.ugasen) return;
        ostavi(`${c.email} uklonjen(a).`, "uspeh");
        osvezi();
      } catch (err) {
        if (jePrekid(err) || ciklus.ugasen) return;
        u.disabled = false;
        if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
        ostavi("Uklanjanje nije uspelo. " + porukaZaKorisnika(err), "greska");
      }
    });
    akcije.appendChild(u);
  }
  return akcije;
}

function blokPozivanja(ciklus, osvezi) {
  const b = el("div", "v2-forma v2-forma--redovi");
  const red = el("div", "v2-forma__red");
  const email = el("input");
  email.type = "email";
  email.placeholder = "kolega@primer.rs";
  email.setAttribute("aria-label", "Email kolege");
  const uloga = el("select");
  for (const [k, naziv] of [["saradnik", "Saradnik"], ["partner", "Partner"], ["citanje", "Čitanje"]]) {
    const opt = el("option", "", naziv);
    opt.value = k;
    uloga.appendChild(opt);
  }
  const posalji_ = dugme("Pozovi", "v2-dugme");
  red.append(email, uloga, posalji_);
  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;
  b.append(red, poruka);

  ciklus.slusaj(posalji_, "click", async () => {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim())) {
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = "Unesite ispravnu email adresu.";
      poruka.hidden = false;
      return;
    }
    posalji_.disabled = true;
    posalji_.textContent = "Poziva se…";
    poruka.hidden = true;
    try {
      await posalji("/api/kancelarija/pozovi", {
        telo: { email: email.value.trim(), uloga: uloga.value },
        signal: ciklus.prekidac().signal,
      });
      if (ciklus.ugasen) return;
      email.value = "";
      ostavi("Poziv je poslat.", "uspeh");
      osvezi();
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      posalji_.disabled = false;
      posalji_.textContent = "Pozovi";
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = "Poziv nije poslat. " + porukaZaKorisnika(err);
      poruka.hidden = false;
    }
  });
  return b;
}

/** Naziv firme + mesta + istorija -- ucitava se ODVOJENO od jezgra tima, isti
 * razlog kao Naplata u Dosijeu: admin ne sme da ceka na audit log da bi
 * upravljao clanovima, a pad ovog dela ne sme da obori invite/suspenduj. */
function blokAdministracijeFirme(firma, ciklus, osvezi) {
  const b = el("div", "v2-podblok");
  b.appendChild(el("h3", "v2-natkapa", "Administracija firme"));

  // Naziv
  const redNaziv = el("div", "v2-forma__red");
  const nazivPolje = el("input");
  nazivPolje.type = "text";
  nazivPolje.value = firma || "";
  nazivPolje.setAttribute("aria-label", "Naziv firme");
  const sacuvajNaziv = dugme("Sačuvaj naziv");
  redNaziv.append(nazivPolje, sacuvajNaziv);
  b.appendChild(redNaziv);
  const porukaNaziv = el("div", "v2-forma__poruka");
  porukaNaziv.setAttribute("role", "alert");
  porukaNaziv.hidden = true;
  b.appendChild(porukaNaziv);

  ciklus.slusaj(sacuvajNaziv, "click", async () => {
    const v = nazivPolje.value.trim();
    if (v.length < 2) {
      porukaNaziv.className = "v2-forma__poruka v2-forma__poruka--greska";
      porukaNaziv.textContent = "Naziv mora imati najmanje 2 znaka.";
      porukaNaziv.hidden = false;
      return;
    }
    sacuvajNaziv.disabled = true;
    try {
      await posalji("/api/kancelarija/naziv", { metod: "PUT", telo: { naziv: v }, signal: ciklus.prekidac().signal });
      if (ciklus.ugasen) return;
      ostavi("Naziv firme je sačuvan.", "uspeh");
      osvezi();
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      sacuvajNaziv.disabled = false;
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      porukaNaziv.className = "v2-forma__poruka v2-forma__poruka--greska";
      porukaNaziv.textContent = "Naziv nije sačuvan. " + porukaZaKorisnika(err);
      porukaNaziv.hidden = false;
    }
  });

  // Mesta -- placeholder dok se ne ucita
  const mestaBlok = el("div", "v2-podblok");
  mestaBlok.appendChild(el("h3", "v2-natkapa", "Mesta"));
  mestaBlok.appendChild(prazno("Učitava se…"));
  b.appendChild(mestaBlok);

  // Istorija -- placeholder dok se ne ucita
  const istorijaBlok = el("div", "v2-podblok");
  istorijaBlok.appendChild(el("h3", "v2-natkapa", "Istorija članstva"));
  istorijaBlok.appendChild(prazno("Učitava se…"));
  b.appendChild(istorijaBlok);

  (async () => {
    let mesta;
    try {
      mesta = uMesta(await dohvati("/api/kancelarija/mesta", { signal: ciklus.prekidac().signal }));
    } catch (e) {
      if (jePrekid(e) || ciklus.ugasen) return;
      mestaBlok.replaceChildren(el("h3", "v2-natkapa", "Mesta"), nijeUcitano("Pregled mesta", e));
      return;
    }
    if (ciklus.ugasen) return;
    mestaBlok.replaceChildren(el("h3", "v2-natkapa", "Mesta"));
    if (mesta.ukupno === null) {
      mestaBlok.appendChild(prazno("Podatak o mestima nije dostupan."));
    } else {
      mestaBlok.appendChild(el("p", "v2-reg__broj",
        `${mesta.iskorisceno} od ${mesta.ukupno} mesta iskorišćeno (${mesta.slobodno} slobodno).`));
    }
  })();

  (async () => {
    let dogadjaji;
    try {
      dogadjaji = uIstoriju(await dohvati("/api/kancelarija/istorija", { signal: ciklus.prekidac().signal }));
    } catch (e) {
      if (jePrekid(e) || ciklus.ugasen) return;
      istorijaBlok.replaceChildren(el("h3", "v2-natkapa", "Istorija članstva"), nijeUcitano("Istorija članstva", e));
      return;
    }
    if (ciklus.ugasen) return;
    istorijaBlok.replaceChildren(el("h3", "v2-natkapa", "Istorija članstva"));
    if (!dogadjaji.length) {
      istorijaBlok.appendChild(prazno("Nema zabeleženih promena članstva."));
    } else {
      const ul = el("ul", "v2-lista-tanka");
      for (const d of dogadjaji) {
        const li = el("li");
        li.appendChild(el("span", "", d.email));
        li.appendChild(el("span", "v2-meta", " · " + d.akcija + (d.kada ? " · " + d.kada.slice(0, 10) : "")));
        ul.appendChild(li);
      }
      istorijaBlok.appendChild(ul);
    }
  })();

  return b;
}

function sekcijaTim(deo, ciklus, osvezi) {
  const s = celina("tim", "Tim kancelarije");
  if (deo.pao) { s.appendChild(nijeUcitano("Podatak o kancelariji", deo.greska)); return s; }
  const t = uTim(deo.podaci);

  // Pozvani korisnik dobija PRIHVATI/ODBIJ -- ranije je ovde stajala samo
  // poruka o pozivu, bez ijedne radnje (dead end).
  if (t.stanje === "poziv") {
    s.appendChild(el("p", "", t.poruka));
    const akcije = el("div", "v2-forma__red");
    const prihvati = dugme("Prihvati", "v2-dugme");
    const odbij = dugme("Odbij", "v2-dugme v2-dugme--opasno");
    ciklus.slusaj(prihvati, "click", async () => {
      prihvati.disabled = true; odbij.disabled = true;
      try {
        await posalji("/api/kancelarija/prihvati", { signal: ciklus.prekidac().signal });
        if (ciklus.ugasen) return;
        ostavi("Pridružili ste se kancelariji.", "uspeh");
        osvezi();
      } catch (err) {
        if (jePrekid(err) || ciklus.ugasen) return;
        prihvati.disabled = false; odbij.disabled = false;
        if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
        ostavi("Prihvatanje nije uspelo. " + porukaZaKorisnika(err), "greska");
      }
    });
    ciklus.slusaj(odbij, "click", async () => {
      if (!window.confirm("Odbiti poziv u ovu kancelariju?")) return;
      prihvati.disabled = true; odbij.disabled = true;
      try {
        await posalji("/api/kancelarija/odbij", { signal: ciklus.prekidac().signal });
        if (ciklus.ugasen) return;
        ostavi("Poziv je odbijen.", "uspeh");
        osvezi();
      } catch (err) {
        if (jePrekid(err) || ciklus.ugasen) return;
        prihvati.disabled = false; odbij.disabled = false;
        if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
        ostavi("Odbijanje nije uspelo. " + porukaZaKorisnika(err), "greska");
      }
    });
    akcije.append(prihvati, odbij);
    s.appendChild(akcije);
    return s;
  }

  if (t.stanje !== "aktivan") {
    s.appendChild(prazno(t.poruka));
    return s;
  }
  if (t.firma) s.appendChild(el("p", "v2-reg__broj", t.firma));
  if (!t.clanovi.length) {
    s.appendChild(prazno("U kancelariji nema drugih članova."));
  } else {
    const ul = el("ul", "v2-klijenti");
    for (const c of t.clanovi) {
      const li = el("li", "v2-klijenti__red");
      li.appendChild(el("span", "v2-klijenti__naziv", c.email));
      const meta = el("span", "v2-klijenti__meta");
      if (c.uloga) meta.appendChild(el("span", "v2-klijenti__vrsta", c.uloga));
      if (c.stanje) meta.appendChild(el("span", "", c.stanje));
      li.appendChild(meta);
      // Admin ne moze da suspenduje/ukloni SEBE preko ove liste -- clanovi
      // ovde su uvek TUDji redovi (backend clanovi tabela ne sadrzi admina).
      if (t.jeAdmin) li.appendChild(redAkcija(c, ciklus, osvezi));
      ul.appendChild(li);
    }
    s.appendChild(ul);
  }
  if (t.jeAdmin) {
    s.appendChild(blokPozivanja(ciklus, osvezi));
    s.appendChild(blokAdministracijeFirme(t.firma, ciklus, osvezi));
  }
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
    okvir.appendChild(sekcijaKlijenti(d.klijenti, ciklus, ucitajIPrikazi));
    okvir.appendChild(sekcijaNaplata(d.naplata, d.rad, ciklus, ucitajIPrikazi));
    okvir.appendChild(sekcijaTim(d.tim, ciklus, ucitajIPrikazi));

    // Portfolio (F9) -- ucitava se ODVOJENO i POSLE jezgra, isti obrazac kao
    // Naplata: pad ovog dela ne sme da obori ostatak Kancelarije.
    const cPort = celina("portfolio", "Portfolio");
    cPort.appendChild(prazno("Učitava se…"));
    okvir.appendChild(cPort);
    sadrzaj.replaceChildren(okvir);

    (async () => {
      let p;
      try {
        p = await ucitajPortfolio({ signal: ciklus.prekidac().signal });
      } catch (e) {
        if (jePrekid(e) || ciklus.ugasen) return;
        p = { ucitano: false, greska: e };
      }
      if (ciklus.ugasen) return;
      cPort.replaceChildren();
      const h = el("h2", "v2-celina__naslov", "Portfolio");
      h.id = "celina-portfolio";
      cPort.appendChild(h);
      cPort.appendChild(sadrzajPortfolia(p, ciklus));
    })();
  }

  ucitajIPrikazi();

  return ciklus;
}
