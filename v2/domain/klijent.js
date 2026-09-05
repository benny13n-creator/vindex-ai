/* Vindex V2 — domen KLIJENTA.
 *
 * Klijent je OBJEKAT, ne prostor. Zivi na `/app-v2/klijent/<id>`, dohvata se
 * iz Kancelarije i iz pretrage, i nema svoju stavku u globalnoj navigaciji —
 * vlasnicki kanon ima cetiri prostora, a legacy sidebar nije dokaz da treba
 * peti (Z017.1 §10).
 *
 * ─────────────────────────────────────────────────────────────────────────
 * POVERLJIVA POLJA SE NE PRIKAZUJU
 *
 * `jmbg`, `broj_pasosa` i `pib` su u bazi SIFROVANI, a `filter_klijent` ih
 * po ulozi uklanja iz odgovora. Prikazati prazno polje „JMBG" znacilo bi
 * tvrditi da klijent nema JMBG — a istina je da ga ovaj ekran ne sme videti.
 * Zato se ta polja ne pojavljuju u spisku polja, ni prazna ni popunjena.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * Cist modul: bez DOM-a, bez mreze, bez stanja.
 */

import { citljivo, datum } from "./labels.js";

/** Polja koja ovaj ekran NIKAD ne prikazuje, ma sta backend poslao. */
export const POVERLJIVA = Object.freeze(["jmbg", "broj_pasosa", "pib", "maticni_broj"]);

/**
 * Sme li polje na ekran.
 *
 * Izvezeno NAMERNO, iako se danas zove sa samo jednog mesta. Mutaciono
 * merenje je pokazalo da je zastita bila NEDOHVATLJIVA: spisak polja je
 * fiksan i nijedan poverljiv kljuc u njega ne dolazi, pa je uklanjanje
 * filtera prolazilo neprimeceno. Zastita koju test ne moze da dosegne nije
 * zastita nego komentar. Sada se proverava direktno.
 *
 * Poredi se i po tacnom kljucu i po nazivu polja, jer se poverljiv podatak
 * u buducnosti moze pojaviti pod drugim kljucem a istim imenom.
 */
export function smePrikazati(kljuc, naziv = "") {
  const k = String(kljuc || "").trim().toLowerCase();
  const n = String(naziv || "").trim().toLowerCase();
  if (POVERLJIVA.includes(k)) return false;
  return !["jmbg", "pib", "pasoš", "pasos", "matični broj", "maticni broj"]
    .some(z => n.includes(z));
}

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

/** Ime kojim se klijent zove na ekranu. Firma pretice licno ime. */
export function naziv(sirov) {
  const k = sirov || {};
  const firma = tekst(k.firma);
  const ime = [tekst(k.ime), tekst(k.prezime)].filter(Boolean).join(" ");
  return firma || ime || "Klijent bez naziva";
}

/** Zaglavlje klijenta. Prazno polje ispada — vidi `poljaKlijenta`. */
export function uZaglavlje(sirov) {
  const k = sirov || {};
  return {
    id: k.id || "",
    naziv: naziv(k),
    vrsta: citljivo(tekst(k.tip)),
    stanje: citljivo(tekst(k.status)),
    email: tekst(k.email),
    telefon: tekst(k.telefon),
    adresa: tekst(k.adresa),
    napomena: tekst(k.napomena),
    upisan: datum(k.kreirano || k.created_at),
    poslednjaAktivnost: datum(k.datum_poslednje_aktivnosti),
  };
}

/**
 * Polja u redosledu prikaza; prazna ispadaju, poverljiva se ne pojavljuju.
 * Provera protiv `POVERLJIVA` je pojas i tregeri: cak i da neko doda polje
 * sa tim imenom, ono ne moze proci.
 */
export function poljaKlijenta(z) {
  return [
    { kljuc: "vrsta", naziv: "Vrsta", vrednost: z.vrsta },
    { kljuc: "email", naziv: "Email", vrednost: z.email },
    { kljuc: "telefon", naziv: "Telefon", vrednost: z.telefon },
    { kljuc: "adresa", naziv: "Adresa", vrednost: z.adresa },
    { kljuc: "upisan", naziv: "Upisan", vrednost: z.upisan, mono: true },
  ].filter(x => x.vrednost && smePrikazati(x.kljuc, x.naziv));
}

/**
 * Predmet u spisku klijentovih predmeta.
 *
 * OBLIK JE UGNEZDJEN, NE RAVAN. `/klijenti/{id}` vraca red veze
 * `predmet_klijenti` sa ugnezdjenim predmetom:
 *
 *     { predmet_id, uloga_klijenta, predmeti: { id, naziv, status, tip } }
 *
 * Mereno uzivo: citanje `p.naziv` sa gornjeg nivoa daje `undefined`, pa je
 * svaki predmet klijenta bio „Predmet bez naziva", a veza je vodila nikuda
 * jer je i `p.id` bio prazan. Prihvata se i ravan oblik, da drugi pozivalac
 * (npr. pretraga) ne mora da se prilagodjava ovom.
 */
export function uPredmet(sirov) {
  const red = sirov || {};
  const p = (red.predmeti && typeof red.predmeti === "object") ? red.predmeti : red;
  return {
    id: p.id || red.predmet_id || "",
    naziv: tekst(p.naziv) || "Predmet bez naziva",
    broj: tekst(p.broj_predmeta),
    vrsta: citljivo(tekst(p.tip)),
    uloga: tekst(red.uloga_klijenta),
    izmenjen: datum(p.updated_at || p.created_at),
  };
}

/**
 * Sastavlja dosije klijenta.
 *
 * AKTIVNI I ZAVRSENI PREDMETI SE NE SABIRAJU U JEDAN SPISAK. To su dve
 * razlicite cinjenice o odnosu sa klijentom, i advokat ih cita drugacije:
 * aktivan predmet je obaveza, zavrsen je istorija.
 */
export function sastaviKlijenta(odgovor) {
  const o = odgovor || {};
  const z = uZaglavlje(o.klijent);
  const aktivni = Array.isArray(o.aktivni_predmeti) ? o.aktivni_predmeti.map(uPredmet) : [];
  const zavrseni = Array.isArray(o.zavrseni_predmeti) ? o.zavrseni_predmeti.map(uPredmet) : [];
  return {
    zaglavlje: z,
    polja: poljaKlijenta(z),
    aktivni,
    zavrseni,
    imaPredmete: aktivni.length + zavrseni.length > 0,
  };
}

/**
 * Telo za otvaranje novog klijenta.
 *
 * `tip` odlucuje koje je polje obavezno: pravno lice ima firmu, fizicko ima
 * ime. Backend trazi `ime` (min 2) u oba slucaja, pa se za pravno lice tamo
 * salje naziv firme — to je ugovor servera, ne izbor ovog ekrana.
 */
export function uTeloNovog({ tip, ime, prezime, firma, email, telefon, adresa, napomena } = {}) {
  const jePravno = tekst(tip) === "pravno_lice";
  const nazivFirme = tekst(firma);
  return {
    tip: jePravno ? "pravno_lice" : "fizicko_lice",
    ime: jePravno ? nazivFirme : tekst(ime),
    prezime: jePravno ? "" : tekst(prezime),
    firma: jePravno ? nazivFirme : "",
    email: tekst(email),
    telefon: tekst(telefon),
    adresa: tekst(adresa),
    napomena: tekst(napomena),
  };
}

/** Sta nedostaje da bi se klijent mogao otvoriti. Prazan niz = moze. */
export function nedostaci({ tip, ime, firma } = {}) {
  const jePravno = tekst(tip) === "pravno_lice";
  const greske = [];
  if (jePravno) {
    if (tekst(firma).length < 2) greske.push("Naziv firme mora imati najmanje 2 znaka.");
  } else if (tekst(ime).length < 2) {
    greske.push("Ime mora imati najmanje 2 znaka.");
  }
  return greske;
}
