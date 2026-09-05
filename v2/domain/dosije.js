/* Vindex V2 — domen Dosijea.
 *
 * Predmet se ne otvara u tablu nego u DOSIJE: jedan predmet, jedna radna
 * povrsina, pet imenovanih celina — Stanje, Hronologija, Analiza predmeta,
 * Spisi, Rokovi i zadaci. To nisu tabovi i ne skrivaju jedna drugu.
 *
 * Ceo Dosije dolazi iz JEDNOG poziva `/api/predmeti/{id}`, koji vraca
 * `{predmet, dokumenti, hronologija, beleske, istorija, komentari,
 *   klijenti_linked}`. Zato ekran nema sedam mreznih poziva ni sedam stanja
 * ucitavanja — ima jedno.
 *
 * Sto ovaj modul NIKAD ne radi:
 *   - ne izmislja pravnu sigurnost; polje kojeg nema ne prikazuje se
 *   - ne pogadja vrstu zapisa hronologije (vidi domain/danas.js)
 *   - ne prikazuje interne identifikatore korisniku
 *
 * Cist modul: bez DOM-a, bez mreze, bez stanja.
 */

import { nazivStanja, klasaStanja, nazivVrste, datum, citljivo } from "./labels.js";
import { ocistiNaslov, datumTekst, razlikaDana, kadaTekst } from "./danas.js";
import { jeRok, stanjeZapisa, STANJE } from "./danas.js";

/** Celine Dosijea, redom. Imena su ono sto korisnik vidi. */
export const CELINE = Object.freeze([
  { kljuc: "stanje", naziv: "Stanje" },
  { kljuc: "hronologija", naziv: "Hronologija" },
  { kljuc: "analiza", naziv: "Analiza predmeta" },
  { kljuc: "spisi", naziv: "Spisi" },
  { kljuc: "rokovi", naziv: "Rokovi i zadaci" },
]);

/** Kratka imena za sidrenu traku — puna imena ostaju na naslovima celina. */
export const SIDRA = Object.freeze([
  { kljuc: "stanje", naziv: "Stanje" },
  { kljuc: "hronologija", naziv: "Hronologija" },
  { kljuc: "analiza", naziv: "Analiza" },
  { kljuc: "spisi", naziv: "Spisi" },
  { kljuc: "rokovi", naziv: "Rokovi" },
  // Naplata je POSLEDNJA: predmet se prvo razume, pa tek onda naplacuje.
  { kljuc: "naplata", naziv: "Naplata" },
]);

function tekst(v) {
  const s = String(v == null ? "" : v).trim();
  return s;
}

/** Iznos u dinarima onako kako ga advokat cita, ne kao sirov broj. */
export function iznos(v) {
  const n = Number(v);
  if (!Number.isFinite(n) || n <= 0) return "";
  return n.toLocaleString("sr-RS", { maximumFractionDigits: 2 }) + " RSD";
}

/**
 * Zaglavlje predmeta — samo ono sto ima poslovnu vrednost i sto podaci
 * stvarno nose. Prazno polje se NE prikazuje: prazan red je tvrdnja da
 * podatak postoji a nije popunjen, a to nije uvek istina.
 */
export function uZaglavlje(sirov) {
  const p = sirov || {};
  const stranke = [tekst(p.tuzilac), tekst(p.tuzeni)].filter(Boolean);
  return {
    id: p.id || "",
    naziv: tekst(p.naziv) || "Predmet bez naziva",
    broj: tekst(p.broj_predmeta),
    vrsta: nazivVrste(p.tip),
    stanje: nazivStanja(p.status),
    stanjeKlasa: klasaStanja(p.status),
    tuzilac: tekst(p.tuzilac),
    tuzeni: tekst(p.tuzeni),
    stranke,
    vrednost: iznos(p.vrednost_spora),
    opis: tekst(p.opis),
    otvoren: datum(p.created_at),
    izmenjen: datum(p.updated_at),
  };
}

/** Polja zaglavlja u redosledu prikaza; prazna ispadaju. */
export function poljaZaglavlja(z) {
  return [
    { naziv: "Broj predmeta", vrednost: z.broj, mono: true },
    { naziv: "Vrsta", vrednost: z.vrsta },
    { naziv: "Tužilac", vrednost: z.tuzilac },
    { naziv: "Tuženi", vrednost: z.tuzeni },
    { naziv: "Vrednost spora", vrednost: z.vrednost, mono: true },
    { naziv: "Otvoren", vrednost: z.otvoren, mono: true },
  ].filter(x => x.vrednost);
}

/** Klijenti povezani sa predmetom. `klijent` NIJE `stranka` — ne spajati. */
export function uKlijente(niz) {
  return (niz || []).map(k => ({
    id: (k && (k.id || k.klijent_id)) || "",
    naziv: tekst(k && (k.firma || k.naziv || k.ime)) || "Klijent bez naziva",
    uloga: tekst(k && k.uloga),
  })).filter(x => x.naziv);
}

/** Spis. Naziv se ne sece; interni identifikatori se ne prikazuju. */
export function uSpis(sirov) {
  const d = sirov || {};
  return {
    id: d.id || "",
    naziv: tekst(d.naziv_fajla) || "Spis bez naziva",
    dodat: datum(d.created_at),
    analiziran: Boolean(d.klasifikovan_at),
    status: tekst(d.status),
    imaOriginal: Boolean(tekst(d.storage_path)),
    redniBroj: Number.isFinite(d.redni_broj) ? d.redni_broj : null,
  };
}

/**
 * Zapis hronologije. Vrsta se NE pogadja — prikazuje se samo ono sto je
 * izjavljeno (migracija 129). Neizjavljen red je i dalje dogadjaj u
 * hronologiji; on samo NIJE rok.
 */
export function uZapisHronologije(sirov) {
  const h = sirov || {};
  const iso = h.datum_iso || h.datum || "";
  return {
    id: h.id || "",
    datum: datumTekst(iso),
    datumIso: iso,
    dogadjaj: ocistiNaslov(h.dogadjaj) || "Događaj bez opisa",
    akter: tekst(h.akter),
    dokument: tekst(h.dokument_naziv),
    vaznost: tekst(h.vaznost),
    kritican: tekst(h.vaznost).toLowerCase().startsWith("krit"),
    jeRok: jeRok(h),
  };
}

/** Hronologija, najnovije prvo. */
export function uHronologiju(niz) {
  return (niz || [])
    .map(uZapisHronologije)
    .sort((a, b) => (a.datumIso < b.datumIso ? 1 : a.datumIso > b.datumIso ? -1 : 0));
}

/**
 * Rokovi predmeta iz hronologije. Ista pravila kao Danas: samo izjavljen rok,
 * razresen ne ulazi u aktivne, kandidat je odvojen od potvrdjene obaveze.
 */
export function uRokove(niz, sada) {
  const rokovi = (niz || []).filter(jeRok);
  const aktivni = rokovi.filter(r => {
    const s = stanjeZapisa(r);
    return s !== STANJE.ODBIJEN && s !== STANJE.IZVRSEN && s !== STANJE.OTKAZAN;
  });
  const mapiraj = (r) => {
    const iso = r.datum_iso || r.datum || "";
    const razlika = razlikaDana(iso, sada);
    return {
      id: r.id || "",
      opis: ocistiNaslov(r.dogadjaj) || "Rok bez opisa",
      datum: datumTekst(iso),
      datumIso: iso,
      razlika,
      kada: kadaTekst(razlika),
      proslo: razlika !== null && razlika < 0,
    };
  };
  const sort = (a, b) => (a.datumIso < b.datumIso ? -1 : 1);
  return {
    obaveze: aktivni.filter(r => stanjeZapisa(r) === STANJE.POTVRDJEN).map(mapiraj).sort(sort),
    zaProveru: aktivni.filter(r => stanjeZapisa(r) === STANJE.KANDIDAT).map(mapiraj).sort(sort),
    razreseni: rokovi.length - aktivni.length,
    nedokazivo: (niz || []).length - rokovi.length,
  };
}

/**
 * Spremnost predmeta iz `/api/predmeti/{id}/health`.
 * Prikazuje se SAMO ako backend vrati status — nikad izmisljen procenat.
 */
export function uSpremnost(sirov) {
  const h = sirov || {};
  const status = tekst(h.status);
  if (!status) return null;
  return {
    // `/health` vraca sirov enum („kriticno", „delimicno"). Prikazan takav,
    // to je programerski zargon na ekranu advokata — tacno ono sto Z015 §19
    // zabranjuje. Citljiv ispis ne menja vrednost, samo je cini recju.
    status: citljivo(status),
    statusSirovi: status,
    razlozi: (h.razlozi || []).map(tekst).filter(Boolean),
    // `score` se namerno NE prikazuje kao broj: ocena bez objasnjenja je
    // tacno ono sto vlasnicki kanon zabranjuje. Razlozi jesu upotrebljivi.
  };
}

/** Sastavlja ceo Dosije iz jednog odgovora. */
export function sastaviDosije(odgovor, spremnostSirova, sada) {
  const o = odgovor || {};
  const hron = o.hronologija || [];
  return {
    zaglavlje: uZaglavlje(o.predmet),
    polja: poljaZaglavlja(uZaglavlje(o.predmet)),
    klijenti: uKlijente(o.klijenti_linked),
    spisi: (o.dokumenti || []).map(uSpis),
    hronologija: uHronologiju(hron),
    rokovi: uRokove(hron, sada),
    // Beleske se prenose CELE, ne kao broj. Ranije je ovde stajala samo
    // duzina — ekran je time mogao da kaze „ima 3 beleske", ali ne i STA u
    // njima pise, sto je jedino zbog cega beleska postoji.
    // Jedan tok nad dve tabele — v. `uNapomene`. `/api/predmeti/{id}` vec
    // vraca oba niza, pa ovo ne uvodi nijedan dodatni poziv.
    beleske: uNapomene({ beleske: o.beleske, komentari: o.komentari }),
    brojBelezaka: uNapomene({ beleske: o.beleske, komentari: o.komentari }).length,
    spremnost: uSpremnost(spremnostSirova),
    // Sirov zapis predmeta se cuva SAMO za izmenu: obrazac mora da zna
    // zatecene vrednosti i `updated_at` radi optimisticke kontrole. Nista
    // sa ovog objekta se NE iscrtava direktno — prikaz ide kroz `zaglavlje`
    // i `polja`, koji su vec proslos kroz pravila o praznom i nepoznatom.
    sirovi: o.predmet || null,
  };
}


/* ═══════════════════════════════════════════════════════════════════════
 * ZADACI, ROCISTA I BELESKE
 *
 * Sve troje zive u Dosijeu, ali NIJEDNO nije rok. Zadatak je posao koji je
 * advokat sam sebi zadao; rociste je zakazan termin pred sudom; beleska je
 * ono sto je zapisao. Nijedno ne prolazi kroz ugovor o rokovima iz
 * migracije 129 i nijedno ne sme da se pojavi u „Obavezama" kao rok.
 * ═══════════════════════════════════════════════════════════════════════ */

/** Stanja zadatka koja backend koristi; nepoznato se ispisuje citljivo. */
const ZADATAK_ZAVRSEN = ["zavrsen", "završen", "otkazan", "odbijen"];

export function uZadatak(sirov, sada) {
  const z = sirov || {};
  const rok = tekst(z.rok_datum || z.rok || "");
  const razlika = rok ? razlikaDana(rok, sada) : null;
  const stanje = tekst(z.status).toLowerCase();
  return {
    id: z.id || "",
    naziv: ocistiNaslov(tekst(z.naziv)) || "Zadatak bez naziva",
    opis: tekst(z.opis),
    prioritet: citljivo(tekst(z.prioritet)),
    stanje: citljivo(tekst(z.status)),
    zavrsen: ZADATAK_ZAVRSEN.includes(stanje),
    datum: rok ? datumTekst(rok) : "",
    datumIso: rok,
    razlika,
    kada: razlika === null ? "" : kadaTekst(razlika),
    proslo: razlika !== null && razlika < 0,
  };
}

/**
 * Zadaci predmeta, razdvojeni na otvorene i zavrsene.
 * Zavrsen zadatak se NE BRISE sa ekrana — on je dokaz da je posao uradjen.
 */
export function uZadatke(niz, sada) {
  const svi = (niz || []).map(z => uZadatak(z, sada));
  const otvoreni = svi.filter(z => !z.zavrsen)
    .sort((a, b) => {
      if (!a.datumIso && !b.datumIso) return 0;
      if (!a.datumIso) return 1;
      if (!b.datumIso) return -1;
      return a.datumIso < b.datumIso ? -1 : 1;
    });
  return { otvoreni, zavrseni: svi.filter(z => z.zavrsen), ukupno: svi.length };
}

/**
 * Rociste. Datum i sud su OBAVEZNI po serverskom ugovoru, pa red bez njih
 * nije rociste nego nepotpun zapis — i ne prikazuje se kao termin.
 */
export function uRociste(sirov, sada) {
  const r = sirov || {};
  const d = tekst(r.datum);
  const razlika = d ? razlikaDana(d, sada) : null;
  const mesto = [tekst(r.sud), tekst(r.sudnica)].filter(Boolean).join(", ");
  return {
    id: r.id || "",
    sud: tekst(r.sud),
    mesto,
    datum: d ? datumTekst(d) : "",
    datumIso: d,
    vreme: tekst(r.vreme),
    brojSuda: tekst(r.broj_predmeta_suda),
    napomena: tekst(r.napomena),
    razlika,
    kada: razlika === null ? "" : kadaTekst(razlika),
    proslo: razlika !== null && razlika < 0,
    potpuno: Boolean(d && tekst(r.sud)),
  };
}

export function uRocista(niz, sada) {
  const svi = (niz || []).map(r => uRociste(r, sada));
  const potpuna = svi.filter(r => r.potpuno).sort((a, b) => (a.datumIso < b.datumIso ? -1 : 1));
  return { redovi: potpuna, nepotpuna: svi.length - potpuna.length };
}

/** Beleska. Prazna beleska se ne prikazuje — prazan red nije zapis. */
export function uBelesku(sirov, izvor = "beleska") {
  const b = sirov || {};
  const sadrzaj = tekst(b.sadrzaj || b.tekst || b.beleska);
  const kada = b.created_at || b.kreirano || null;
  return {
    id: b.id || "",
    tekst: sadrzaj,
    datum: datum(kada),
    // Odsutan trenutak se NE popunjava danasnjim datumom. `datum` u tom
    // slucaju nosi kanonsku oznaku nepoznatog („—"), a `datumPoznat` govori
    // ekranu da ne dopisuje datumsku odrednicu uz napomenu — nedostatak
    // vremena upisa je artefakt zapisa, ne tvrdnja o predmetu.
    datumPoznat: !!kada,
    // Sirov trenutak se cuva SAMO za uredjivanje niza. Nikad se ne prikazuje —
    // `datum` je jedini oblik koji advokat vidi.
    kada: kada ? String(kada) : "",
    // `izvor` odredjuje ISKLJUCIVO putanju za brisanje. Ne prikazuje se: dve
    // tabele nisu dva pojma za advokata, nego posledica istorije baze.
    izvor,
  };
}

export function uBeleske(niz, izvor = "beleska") {
  return (niz || []).map(b => uBelesku(b, izvor)).filter(b => b.tekst);
}

/* ═══════════════════════════════════════════════════════════════════════
 * NAPOMENE — JEDAN TOK NAD DVE TABELE
 *
 * Legacy `/app` prikazuje DVA odvojena spiska slobodnog teksta na istom
 * predmetu: „Beleške" (`predmet_beleske`) i „Komentari" (`predmet_komentari`).
 * Oba su vlasnikova, oba su slobodan tekst o predmetu, nijedno nema polje po
 * kome bi se razlikovalo. To su dva imena za istu radnju — a „1 koncept = 1
 * vlasnik = 1 istina" je vlasnikovo pravilo, ne moje.
 *
 * V2 zato ima JEDAN tok: „Beleške". Ni jedan postojeci zapis ne nestaje —
 * citaju se OBE tabele; nove napomene se upisuju u `predmet_beleske`. Poreklo
 * reda se ne prikazuje jer advokatu ne znaci nista; nosi se samo zato sto se
 * brisanje razlikuje po putanji.
 * ═══════════════════════════════════════════════════════════════════════ */
export function uNapomene({ beleske, komentari } = {}) {
  const spojene = uBeleske(beleske, "beleska")
    .concat(uBeleske(komentari, "komentar"));
  // Najnovije prvo: napomena se pise da bi se sutra procitala.
  return spojene.sort((a, b) => {
    if (a.kada === b.kada) return 0;
    if (!a.kada) return 1;
    if (!b.kada) return -1;
    return a.kada < b.kada ? 1 : -1;
  });
}
