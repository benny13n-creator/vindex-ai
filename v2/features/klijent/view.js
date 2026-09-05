/* Vindex V2 — DOSIJE KLIJENTA i otvaranje novog klijenta.
 *
 * Klijent je OBJEKAT (`/app-v2/klijent/<id>`), a „nov" je RADNJA nad tim
 * prostorom (`/app-v2/klijent/nov`) — isti obrazac kao predmet. U globalnoj
 * navigaciji nema stavke „Klijenti": do klijenta se stize iz Kancelarije i
 * iz pretrage. Legacy sidebar item nije dokaz da V2 treba peti prostor.
 *
 * Ekran ima tri celine: Podaci, Aktivni predmeti, Završeni predmeti.
 * Aktivni i zavrseni se NE SPAJAJU — aktivan predmet je obaveza, zavrsen je
 * istorija, i advokat ih cita drugacije.
 */

import { napraviCiklus } from "../../platform/lifecycle.js";
import { dohvati, posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";
import { idiNa, putanjaZa } from "../../platform/router.js";
import { ostavi, elementPoruke } from "../../platform/obavestenje.js";
import { sastaviKlijenta, uTeloNovog, nedostaci } from "../../domain/klijent.js";
import { kontrolaIzmeneKlijenta, kontrolaArhiviranja } from "./radnje.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

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

/* ── Spisak predmeta klijenta ───────────────────────────────────────────── */
function spisakPredmeta(lista, ciklus) {
  const ul = el("ul", "v2-reg__lista");
  for (const p of lista) {
    const li = el("li", "v2-reg__red");
    const naziv = el("span", "v2-reg__naziv");
    const veza = el("a", "v2-reg__veza", p.naziv);
    veza.href = putanjaZa("predmet", p.id);
    ciklus.slusaj(veza, "click", (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
      e.preventDefault();
      idiNa("predmet", p.id);
    });
    naziv.appendChild(veza);
    li.appendChild(naziv);

    const meta = el("span", "v2-reg__meta");
    if (p.broj) meta.appendChild(el("span", "v2-reg__broj-predmeta", p.broj));
    if (p.vrsta) meta.appendChild(el("span", "v2-reg__vrsta", p.vrsta));
    if (p.izmenjen) meta.appendChild(el("span", "v2-reg__datum", p.izmenjen));
    li.appendChild(meta);
    ul.appendChild(li);
  }
  return ul;
}

/* ── Dosije klijenta ────────────────────────────────────────────────────── */
export function montirajKlijenta(kontejner, kontekst, klijentId) {
  const ciklus = napraviCiklus();
  // Posle izmene se dosije ponovo cita SA SERVERA — samo ovaj ekran, ne ceo
  // boot (`/api/plan/status` ima granicu od 60 na sat).
  const osvezi = () => { if (!ciklus.ugasen) ucitaj(); };

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--predmet");
  const sadrzaj = el("div", "v2-dosije");
  sadrzaj.tabIndex = -1;
  sadrzaj.setAttribute("aria-live", "polite");
  unutra.appendChild(sadrzaj);
  kontejner.appendChild(unutra);

  if (!klijentId) {
    sadrzaj.appendChild(el("p", "v2-poruka__naslov", "Klijent nije naveden."));
    return ciklus;
  }

  sadrzaj.appendChild(prazno("Učitava se…"));

  async function ucitaj() {
    const prekidac = ciklus.prekidac();
    let d;
    try {
      d = await dohvati(`/klijenti/${encodeURIComponent(klijentId)}`, { signal: prekidac.signal });
    } catch (e) {
      if (jePrekid(e) || ciklus.ugasen) return;
      if (e && e.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      const p = el("div", "v2-poruka v2-poruka--greska");
      p.appendChild(el("p", "v2-poruka__naslov",
        e && e.vrsta === VRSTA.NEMA ? "Klijent nije pronađen" : "Klijent nije učitan"));
      p.appendChild(el("p", "v2-poruka__telo", porukaZaKorisnika(e)));
      sadrzaj.replaceChildren(p);
      return;
    }
    if (ciklus.ugasen) return;

    const k = sastaviKlijenta(d);
    const okvir = document.createDocumentFragment();

    const zaglavlje = el("header", "v2-dosije__zaglavlje");
    const nazad = el("a", "v2-predmet-traka__nazad", "← Kancelarija");
    nazad.href = putanjaZa("kancelarija");
    ciklus.slusaj(nazad, "click", (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
      e.preventDefault();
      idiNa("kancelarija");
    });
    zaglavlje.appendChild(nazad);
    zaglavlje.appendChild(el("h1", "v2-naslov v2-dosije__naziv", k.zaglavlje.naziv));
    if (k.zaglavlje.stanje) {
      const linija = el("p", "v2-dosije__linija");
      linija.appendChild(el("span", "v2-dosije__stanje", k.zaglavlje.stanje));
      zaglavlje.appendChild(linija);
    }
    okvir.appendChild(zaglavlje);

    const izPrethodne = elementPoruke();
    if (izPrethodne) okvir.appendChild(izPrethodne);

    // ── Podaci ──
    const s1 = celina("podaci", "Podaci");
    if (!k.polja.length) {
      s1.appendChild(prazno("Za ovog klijenta nema evidentiranih podataka."));
    } else {
      const dl = el("dl", "v2-polja");
      for (const p of k.polja) {
        const par = el("div", "v2-polja__par");
        par.appendChild(el("dt", "v2-polje", p.naziv));
        par.appendChild(el("dd", p.mono ? "v2-polja__v v2-mono" : "v2-polja__v", p.vrednost));
        dl.appendChild(par);
      }
      s1.appendChild(dl);
    }
    if (k.zaglavlje.napomena) {
      const b = el("div", "v2-podblok");
      b.appendChild(el("h3", "v2-natkapa", "Napomena"));
      b.appendChild(el("p", "v2-proza", k.zaglavlje.napomena));
      s1.appendChild(b);
    }
    // Izmena i arhiviranje. Arhiviranje stoji odvojeno i vizuelno drugacije —
    // i NE zove se „Obriši", jer server radi soft-delete (vidi radnje.js).
    s1.appendChild(kontrolaIzmeneKlijenta(klijentId, d.klijent || {}, ciklus, osvezi));
    s1.appendChild(kontrolaArhiviranja(klijentId, k.zaglavlje.naziv, ciklus));
    okvir.appendChild(s1);

    // ── Aktivni ──
    const s2 = celina("aktivni", "Aktivni predmeti");
    if (!k.aktivni.length) s2.appendChild(prazno("Nema aktivnih predmeta za ovog klijenta."));
    else s2.appendChild(spisakPredmeta(k.aktivni, ciklus));
    okvir.appendChild(s2);

    // ── Zavrseni ──
    const s3 = celina("zavrseni", "Završeni predmeti");
    if (!k.zavrseni.length) s3.appendChild(prazno("Nema završenih predmeta."));
    else s3.appendChild(spisakPredmeta(k.zavrseni, ciklus));
    okvir.appendChild(s3);

    sadrzaj.replaceChildren(okvir);
    document.title = k.zaglavlje.naziv + " · Vindex";
  }

  ucitaj();

  return ciklus;
}

/* ── Nov klijent ────────────────────────────────────────────────────────── */
export function montirajNovogKlijenta(kontejner, kontekst) {
  const ciklus = napraviCiklus();
  const zaceto = kontekst || {};

  const unutra = el("div", "v2-scena__unutra v2-scena__unutra--predmet");
  const zaglavlje = el("header", "v2-zaglavlje");
  const h1 = el("h1", "v2-naslov", "Nov klijent");
  h1.id = "v2-naslov-nov-klijent";
  zaglavlje.appendChild(h1);
  zaglavlje.appendChild(el("p", "v2-podnaslov",
    "Poverljivi podaci (JMBG, PIB, broj pasoša) unose se u legacy Vindexu — "
    + "ovde se ne prikazuju ni ne unose."));
  unutra.appendChild(zaglavlje);

  const forma = el("form", "v2-forma");
  forma.noValidate = true;

  // ── Vrsta ──
  const omotTip = el("div", "v2-polje-unos");
  const labTip = el("label", "v2-polje-unos__labela", "Vrsta klijenta");
  labTip.htmlFor = "nk-tip";
  const tip = el("select", "v2-polje-unos__kontrola");
  tip.id = "nk-tip";
  for (const [v, t] of [["fizicko_lice", "Fizičko lice"], ["pravno_lice", "Pravno lice"]]) {
    const o = document.createElement("option");
    o.value = v; o.textContent = t;
    tip.appendChild(o);
  }
  tip.value = zaceto.tip || "fizicko_lice";
  omotTip.append(labTip, tip);

  function polje(id, naziv, vrednost) {
    const omot = el("div", "v2-polje-unos");
    const lab = el("label", "v2-polje-unos__labela", naziv);
    lab.htmlFor = id;
    const unos = el("input", "v2-polje-unos__kontrola");
    unos.id = id; unos.type = "text"; unos.autocomplete = "off";
    unos.value = vrednost || "";
    omot.append(lab, unos);
    return { omot, unos, lab };
  }

  const pIme = polje("nk-ime", "Ime", zaceto.ime);
  const pPrezime = polje("nk-prezime", "Prezime", zaceto.prezime);
  const pFirma = polje("nk-firma", "Naziv firme", zaceto.firma);
  const pEmail = polje("nk-email", "Email", zaceto.email);
  const pTelefon = polje("nk-telefon", "Telefon", zaceto.telefon);
  const pAdresa = polje("nk-adresa", "Adresa", zaceto.adresa);

  const parLice = el("div", "v2-forma__par");
  parLice.append(pIme.omot, pPrezime.omot);
  const parKontakt = el("div", "v2-forma__par");
  parKontakt.append(pEmail.omot, pTelefon.omot);

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;

  const radnje = el("div", "v2-forma__radnje");
  const dugme = el("button", "v2-dugme v2-dugme--glavno", "Otvori klijenta");
  dugme.type = "submit";
  const odustani = el("a", "v2-dugme v2-dugme--tiho", "Odustani");
  odustani.href = putanjaZa("kancelarija");
  ciklus.slusaj(odustani, "click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    idiNa("kancelarija");
  });
  radnje.append(dugme, odustani);

  forma.append(omotTip, parLice, pFirma.omot, parKontakt, pAdresa.omot, poruka, radnje);
  unutra.appendChild(forma);
  kontejner.appendChild(unutra);
  document.title = "Nov klijent · Vindex";

  // Vrsta klijenta menja KOJA su polja smislena — pravno lice nema prezime.
  function osveziVrstu() {
    const jePravno = tip.value === "pravno_lice";
    parLice.hidden = jePravno;
    pFirma.omot.hidden = !jePravno;
    (jePravno ? pFirma.unos : pIme.unos).focus();
  }
  ciklus.slusaj(tip, "change", osveziVrstu);
  osveziVrstu();

  function javi(t, vrsta) {
    poruka.className = "v2-forma__poruka v2-forma__poruka--" + (vrsta || "greska");
    poruka.textContent = t;
    poruka.hidden = false;
  }

  let salje = false;
  ciklus.slusaj(forma, "submit", async (e) => {
    e.preventDefault();
    if (salje) return;

    const unos = {
      tip: tip.value, ime: pIme.unos.value, prezime: pPrezime.unos.value,
      firma: pFirma.unos.value, email: pEmail.unos.value,
      telefon: pTelefon.unos.value, adresa: pAdresa.unos.value,
    };
    const greske = nedostaci(unos);
    if (greske.length) {
      javi(greske.join(" "));
      (tip.value === "pravno_lice" ? pFirma.unos : pIme.unos).focus();
      return;
    }

    salje = true;
    dugme.disabled = true;
    dugme.textContent = "Otvara se…";
    poruka.hidden = true;

    const prekidac = ciklus.prekidac();
    let odg;
    try {
      odg = await posalji("/klijenti", { telo: uTeloNovog(unos), signal: prekidac.signal });
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      salje = false;
      dugme.disabled = false;
      dugme.textContent = "Otvori klijenta";
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      if (err && err.vrsta === VRSTA.MREZA) {
        javi("Veza je prekinuta pre nego što je stigao odgovor. Klijent je možda otvoren — "
           + "proverite spisak pre nego što pokušate ponovo.", "upozorenje");
        return;
      }
      javi("Klijent nije otvoren. " + porukaZaKorisnika(err));
      return;
    }
    if (ciklus.ugasen) return;

    const id = odg && (odg.id || (odg.klijent && odg.klijent.id));
    if (!id) {
      javi("Server je prihvatio zahtev, ali nije vratio klijenta. Proverite spisak "
         + "pre ponovnog pokušaja.", "upozorenje");
      salje = false;
      dugme.disabled = false;
      dugme.textContent = "Otvori klijenta";
      return;
    }
    ostavi("Klijent je otvoren.", "uspeh");
    idiNa("klijent", id);
  });

  ciklus.kontekst = () => ({
    tip: tip.value, ime: pIme.unos.value, prezime: pPrezime.unos.value,
    firma: pFirma.unos.value, email: pEmail.unos.value,
    telefon: pTelefon.unos.value, adresa: pAdresa.unos.value,
  });

  return ciklus;
}

/* ── Dispecer objekta KLIJENT ───────────────────────────────────────────── */
export function montirajProstorKlijent(kontejner, kontekst, param) {
  const svi = kontekst || {};
  // `nov` je RADNJA, sve ostalo je identitet klijenta. Rezervisana rec se ne
  // moze sudariti sa UUID-em.
  if (param === "nov") {
    const c = montirajNovogKlijenta(kontejner, svi.nov || null);
    const sops = c.kontekst;
    c.kontekst = () => Object.assign({}, svi, { nov: sops ? sops() : null });
    return c;
  }
  return montirajKlijenta(kontejner, null, param);
}
