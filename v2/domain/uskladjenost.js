/* Vindex V2 — domen prostora USKLAĐENOST (digitalna imovina).
 *
 * PETI PROSTOR, USLOVAN. Postoji samo za nalog koji na to ima pravo. Nalog
 * bez prava ga NE VIDI — ne kao onemogucen, ne kao „uskoro". Onemogucena
 * stavka je obecanje koje proizvod ne moze da odrzi.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * ZASTO SVAKA ANALIZA OVDE NOSI OGRADU KOJU DRUGI PROSTORI NEMAJU
 *
 * Mereno na samim rutama: `POST /web3/*` vraca `{rezultat, modul,
 * credits_remaining}`. NEMA polja `izvori`, nema `confidence`, nema
 * `izvori_neuspeh` — ni na jednoj od ovih ruta. To je merljiva razlika u
 * odnosu na `/api/pitanje`, koje izvore vraca i cija se ograda racuna iz
 * njih.
 *
 * Posledica: ovde se NE MOZE prikazati odakle zakljucak dolazi, jer backend
 * to ne saopstava. Regulatorni zakljucak bez izvora, prikazan istim
 * povrsinom kao odgovor sa pet clanova zakona, citao bi se kao jednako
 * potkrepljen. Zato ograda ovde nije opcija koja se pali kad nesto padne —
 * ona je STALNA i izvedena iz oblika odgovora, ne iz njegovog sadrzaja.
 *
 * To NIJE oduzimanje sposobnosti: analiza se izvrsava, rezultat se prikazuje
 * u celosti. Menja se samo tvrdnja koju ekran o njemu iznosi.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * Cist modul: bez DOM-a, bez mreze, bez stanja.
 */

/**
 * Analize koje ovaj prostor nudi.
 *
 * Sve dele isti ugovor (`POST <putanja>` sa `{tekst}` -> `{rezultat}`), pa
 * jedan ekran opsluzuje sve umesto osam skoro istih ekrana. `najmanje` je
 * serverska granica, prepisana doslovno — klijent koji je ne postuje samo
 * proizvodi 422 koji je korisnik mogao da izbegne.
 */
export const ANALIZE = Object.freeze([
  {
    kljuc: "regulativa",
    naziv: "Regulatorna provera",
    pitanje: "Da li je ova aktivnost usklađena sa ZDI i MiCA?",
    putanja: "/web3/compliance",
    najmanje: 30,
    labela: "Opis aktivnosti",
    pomoc: "Opišite čime se klijent bavi: usluga, tokeni, korisnici, jurisdikcije.",
  },
  {
    kljuc: "pretraga",
    naziv: "Pretraga propisa o digitalnoj imovini",
    pitanje: "Šta ZDI i MiCA kažu o ovome?",
    putanja: "/web3/pretraga",
    najmanje: 10,
    labela: "Pitanje",
    pomoc: "Konkretno pitanje o Zakonu o digitalnoj imovini ili MiCA uredbi.",
  },
  {
    kljuc: "whitepaper",
    naziv: "Analiza whitepaper-a",
    pitanje: "Ispunjava li whitepaper zahteve ZDI i MiCA?",
    putanja: "/web3/whitepaper",
    najmanje: 100,
    labela: "Tekst whitepaper-a",
    pomoc: "Nalepite tekst. Najmanje 100 znakova.",
  },
  {
    kljuc: "aml",
    naziv: "AML/KYC revizija",
    pitanje: "Gde su rupe u AML/KYC postupku?",
    putanja: "/web3/aml-audit",
    najmanje: 30,
    labela: "Opis postupka",
    pomoc: "Kako klijent identifikuje korisnike i prati transakcije.",
  },
  {
    kljuc: "ugovor",
    naziv: "Pravna analiza pametnog ugovora",
    pitanje: "Šta ovaj ugovor pravno znači?",
    putanja: "/web3/analiziraj-ugovor",
    najmanje: 50,
    labela: "Kod ili opis ugovora",
    pomoc: "Izvorni kod ugovora ili opis njegove logike.",
  },
]);

export function analizaPoKljucu(kljuc) {
  return ANALIZE.find(a => a.kljuc === String(kljuc || "")) || null;
}

/**
 * Ograda koja stoji uz SVAKI rezultat u ovom prostoru.
 *
 * Nije uslovna i ne zavisi od sadrzaja odgovora — izvedena je iz oblika
 * odgovora: ove rute ne vracaju izvore, pa se poreklo zakljucka ne moze
 * prikazati ni kada je zakljucak tacan.
 */
export const OGRADA = Object.freeze({
  naslov: "Ovaj nalaz nije potkrepljen izvorima",
  telo: "Za razliku od prostora Znanje, ova analiza ne vraća odredbe na koje se "
      + "oslanja, pa se njeno poreklo ne može prikazati. Koristite je kao polaznu "
      + "tačku istraživanja, nikada kao regulatorno mišljenje i nikada kao osnov "
      + "za izjavu prema nadzornom organu.",
});

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

/**
 * Sastavlja rezultat jedne analize.
 *
 * `rezultat` moze doci kao tekst ili kao objekat — uzima se prvo polje koje
 * stvarno nosi tekst, a ako nijedno ne nosi, to se KAZE umesto da se prikaze
 * prazna povrsina koja izgleda kao „nema nalaza".
 */
export function uNalaz(sirov) {
  const o = sirov || {};
  const r = o.rezultat;
  let telo = "";
  if (typeof r === "string") telo = tekst(r);
  else if (r && typeof r === "object") {
    telo = tekst(r.tekst || r.analiza || r.odgovor || r.rezultat || "");
  }
  return {
    telo,
    prazan: telo === "",
    modul: tekst(o.modul),
    ograda: OGRADA,
  };
}
