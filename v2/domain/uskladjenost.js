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
    oblik: "tekst",
  },
  {
    kljuc: "pretraga",
    naziv: "Pretraga propisa o digitalnoj imovini",
    pitanje: "Šta ZDI i MiCA kažu o ovome?",
    putanja: "/web3/pretraga",
    najmanje: 10,
    labela: "Pitanje",
    pomoc: "Konkretno pitanje o Zakonu o digitalnoj imovini ili MiCA uredbi.",
    oblik: "tekst",
  },
  {
    kljuc: "whitepaper",
    naziv: "Analiza whitepaper-a",
    pitanje: "Ispunjava li whitepaper zahteve ZDI i MiCA?",
    putanja: "/web3/whitepaper",
    najmanje: 100,
    labela: "Tekst whitepaper-a",
    pomoc: "Nalepite tekst. Najmanje 100 znakova.",
    oblik: "tekst",
  },
  {
    kljuc: "aml",
    naziv: "AML/KYC revizija",
    pitanje: "Gde su rupe u AML/KYC postupku?",
    putanja: "/web3/aml-audit",
    najmanje: 30,
    labela: "Opis postupka",
    pomoc: "Kako klijent identifikuje korisnike i prati transakcije.",
    // OTKRIVENI KVAR (Z017.2): backend vraca {audit_data, objasnjenje}, NIKAD
    // {rezultat} -- generican "tekst" oblik je prikazivao "odgovor nije
    // stigao u ocekivanom obliku" za SVAKI poziv. Popravljeno na "skor".
    oblik: "skor",
    ukupniKljuc: "ukupna_uskladenost",
    nivoKljuc: "uskladenost_nivo",
    kljucPodataka: "audit_data",
  },
  {
    kljuc: "ugovor",
    naziv: "Pravna analiza pametnog ugovora",
    pitanje: "Šta ovaj ugovor pravno znači?",
    putanja: "/web3/analiziraj-ugovor",
    najmanje: 50,
    labela: "Kod ili opis ugovora",
    pomoc: "Izvorni kod ugovora ili opis njegove logike.",
    // OTKRIVENI KVAR (Z017.2): backend (SmartContractReq) ocekuje
    // {solidity_source}, ne {tekst} -- SVAKI pokusaj ove analize je vracao
    // 422 pre nego sto bi handler bio pozvan. Popravljeno.
    poljeTela: "solidity_source",
    oblik: "ugovor",
  },
  {
    kljuc: "due-diligence",
    naziv: "Spremnost za Due Diligence",
    pitanje: "Koliko je moja dokumentacija spremna za regulatorni/bankarski upit?",
    putanja: "/web3/health-score",
    najmanje: 30,
    labela: "Opis posedovane dokumentacije",
    pomoc: "Koju dokumentaciju posedujete o kripto imovini i transakcijama.",
    oblik: "skor",
    ukupniKljuc: "ukupni_skor",
    nivoKljuc: "skor_nivo",
    kljucPodataka: "health_data",
  },
  {
    kljuc: "reporting-simulator",
    naziv: "Simulator izveštavanja (CARF/DAC8)",
    pitanje: "Kako se ovaj scenario tipično kategoriše za izveštavanje?",
    putanja: "/web3/reporting-simulator",
    najmanje: 20,
    labela: "Opis scenarija transakcija",
    pomoc: "Opšta edukacija o CARF/DAC8-tipa kategorijama — ne pravni/poreski savet.",
    oblik: "tekst",
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

/**
 * Z017.2 §7 -- provenance semantika, SAMO za analize čiji backend stvarno
 * prati retrieval ("regulativa"=/web3/compliance, "pretraga"=/web3/pretraga
 * -- obe nose `izvori`/`retrieval_unavailable` posle Pattern A popravke).
 * "whitepaper"/"aml"/"ugovor" NEMAJU RAG uopšte (potvrđeno čitanjem
 * web3_compliance.py -- nijedna ne poziva _get_index/_ugradi_query), pa se
 * za njih NE pogađa stanje koje backend nikad nije saopštio -- ostaju na
 * STALNOJ `OGRADA` iznad, nepromenjeno.
 *
 * Tri stanja se NIKAD ne mešaju (§6): SOURCE_UNAVAILABLE (pretraga NIJE
 * izvršena) != INSUFFICIENT_SOURCE (izvršena, ništa iznad praga) !=
 * SUPPORTED (izvršena, nešto pronađeno -- i dalje samo polazna tačka).
 */
const OGRADA_IZVOR_NEDOSTUPAN = Object.freeze({
  naslov: "Izvor nije mogao biti proveren",
  telo: "Pretraga baze propisa trenutno nije bila dostupna, pa se poreklo ovog nalaza ne može "
      + "potvrditi. Ovo NE znači da propis ne postoji ili da je nalaz netačan — znači da nije "
      + "proveren u ovom pokušaju. Pokušajte ponovo pre nego što se oslonite na njega.",
});

const OGRADA_NEDOVOLJAN_IZVOR = Object.freeze({
  naslov: "Nije pronađena odgovarajuća odredba",
  telo: "Pretraga je izvršena, ali nije pronašla dovoljno relevantnu odredbu za ovo pitanje. "
      + "Odsustvo pogotka ne znači da propis ne postoji — znači da nije pronađen i proveren u "
      + "ovoj bazi. Koristite ovo kao polaznu tačku istraživanja, nikada kao regulatorno mišljenje.",
});

function ogradaPotkrepljena(izvori) {
  return {
    naslov: "Nalaz je potkrepljen pronađenim odredbama",
    telo: "Ispod stoje stvarno preuzeti odlomci na kojima se ovaj nalaz delimično zasniva. "
        + "I dalje proverite izvor pre oslanjanja na njega u konkretnom slučaju — pronalaženje "
        + "odlomka ne znači da je model ispravno protumačio njegov sadržaj.",
    izvori,
  };
}

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

  let ograda = OGRADA;
  const pratiIzvore = o
    && (Object.prototype.hasOwnProperty.call(o, "izvori")
        || Object.prototype.hasOwnProperty.call(o, "retrieval_unavailable"));
  if (pratiIzvore) {
    if (o.retrieval_unavailable === true) {
      ograda = OGRADA_IZVOR_NEDOSTUPAN;
    } else if (Array.isArray(o.izvori) && o.izvori.length > 0) {
      ograda = ogradaPotkrepljena(o.izvori);
    } else {
      ograda = OGRADA_NEDOVOLJAN_IZVOR;
    }
  }

  return {
    telo,
    prazan: telo === "",
    modul: tekst(o.modul),
    ograda,
  };
}
