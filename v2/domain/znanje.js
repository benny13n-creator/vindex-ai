/* Vindex V2 — domen prostora ZNANJE (pravno istrazivanje).
 *
 * Ovo je ekran sa najvecim pravnim rizikom u celom proizvodu: jedino mesto
 * gde tekst koji je proizveo model moze biti procitan kao tvrdnja o zakonu.
 * Zato ovaj modul postoji odvojeno od prikaza — pravila o tome STA SE SME
 * TVRDITI ne smeju ziveti u funkciji koja crta HTML.
 *
 * TRI STANJA KOJA SE NIKAD NE SMEJU SPOJITI (B-U-003):
 *
 *   1. `retrieval_unavailable` — UPIT NAD KORPUSOM JE PAO.
 *      Odgovor NE pociva na zakonskom korpusu. Ovo NIJE „nema propisa";
 *      to je „nismo proverili". Prikazati ga kao odsustvo propisa je tacno
 *      onaj kvar zbog kojeg je pad Pinecone upita nekad izgledao kao tvrdnja
 *      o zakonu.
 *
 *   2. `izvori_neuspeh` NEPRAZAN — DEO IZVORA NIJE PROVEREN.
 *      Imenuje se TACNO koji („zakonski korpus", „dokumenti predmeta"), jer
 *      „delimicno" advokatu ne kaze sme li da se osloni na odgovor.
 *
 *   3. `izvori` PRAZAN, a nista nije palo — PROVERENO, NEMA POGOTKA.
 *      Ovo je jedina od tri situacije u kojoj se sme reci da izvor nije
 *      pronadjen.
 *
 * PRAZNA LISTA NIJE ISTO STO I ODSUTNO POLJE. Zato se svuda gleda
 * `!== undefined`, a ne istinitost: `[]` znaci „provereno, nema nicega",
 * a odsutno polje znaci „backend o tome nista nije rekao".
 *
 * SIGURNOST SE NE PRIKAZUJE KAO PROCENAT. Backend racuna HIGH/MEDIUM/LOW iz
 * kosinusnog skora; broj bez objasnjenja je kanonom zabranjen KPI, a
 * „87% sigurno" pred sudom ne znaci nista.
 *
 * Cist modul: bez DOM-a, bez mreze, bez stanja.
 */

/** Nivo poklapanja sa korpusom — rec, ne broj. */
const SIGURNOST = {
  HIGH:   { naziv: "Jako poklapanje sa propisom", klasa: "visoka" },
  MEDIUM: { naziv: "Delimično poklapanje sa propisom", klasa: "srednja" },
  LOW:    { naziv: "Slabo poklapanje sa propisom", klasa: "niska" },
};

export function sigurnost(sirovo) {
  const k = String(sirovo || "").trim().toUpperCase();
  return SIGURNOST[k] || null;
}

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

/** Jedan izvor: zakon i clan. Skor se NE prikazuje kao broj korisniku. */
export function uIzvor(sirov) {
  const i = sirov || {};
  const zakon = tekst(i.zakon || i.law);
  const clan = tekst(i.clan || i.article);
  if (!zakon) return null;
  return { zakon, clan, oznaka: clan ? `${zakon}, član ${clan}` : zakon };
}

/**
 * Upozorenja koja se MORAJU prikazati uz odgovor, redom po tezini.
 * Vraca niz `{kljuc, naslov, telo}`. Prazan niz znaci da nema sta da se
 * ogradi — a ne da je odgovor tacan.
 */
export function upozorenja(odg) {
  const o = odg || {};
  const lista = [];

  if (o.retrieval_unavailable) {
    lista.push({
      kljuc: "korpus-pao",
      naslov: "Pretraga zakonskog korpusa nije uspela",
      telo: "Ovaj odgovor NE počiva na pretrazi propisa. To ne znači da propis ne "
          + "postoji — znači da nije proveren. Ponovite pitanje pre nego što se "
          + "oslonite na odgovor.",
    });
  }

  const neuspeh = Array.isArray(o.izvori_neuspeh) ? o.izvori_neuspeh.map(tekst).filter(Boolean) : [];
  if (neuspeh.length) {
    lista.push({
      kljuc: "izvor-nije-proveren",
      naslov: neuspeh.length === 1 ? "Jedan izvor nije proveren" : "Deo izvora nije proveren",
      telo: "Nije provereno: " + neuspeh.join(", ") + ". Odsustvo nalaza iz tog izvora "
          + "nije dokaz da nalaza nema.",
    });
  }

  const izvori = izvoriIz(o);
  if (!izvori.length && !o.retrieval_unavailable && !neuspeh.length) {
    lista.push({
      kljuc: "bez-pogotka",
      naslov: "Nijedan propis nije pronađen za ovo pitanje",
      telo: "Pretraga je izvršena i nije vratila odredbu. Odgovor se oslanja samo na "
          + "opšte znanje modela i ne sme se citirati kao izvor prava.",
    });
  }

  return lista;
}

/** Izvori u obliku za prikaz. Neispravni redovi ispadaju, ne rusi se ekran. */
export function izvoriIz(odg) {
  const sirovi = (odg && odg.izvori) || [];
  if (!Array.isArray(sirovi)) return [];
  return sirovi.map(uIzvor).filter(Boolean);
}

/**
 * Cinjenice koje DOKUMENT NAVODI (B4-M2). To nisu utvrdjene cinjenice i ne
 * smeju se prikazati kao nalaz sistema — dokument ih tvrdi, sistem ih prenosi.
 */
export function cinjeniceIzDokumenta(odg) {
  const c = odg && odg.cinjenice_iz_dokumenta;
  if (!Array.isArray(c)) return [];
  return c.map((x) => {
    if (typeof x === "string") return { tekst: tekst(x), izvor: "" };
    return { tekst: tekst(x && (x.tekst || x.cinjenica || x.text)), izvor: tekst(x && (x.dokument || x.izvor)) };
  }).filter(x => x.tekst);
}

/** Sastavlja sve sto ekran sme da prikaze iz jednog odgovora. */
export function sastaviOdgovor(sirov) {
  const o = sirov || {};
  return {
    tekst: tekst(o.odgovor),
    sigurnost: sigurnost(o.confidence),
    izvori: izvoriIz(o),
    upozorenja: upozorenja(o),
    cinjenice: cinjeniceIzDokumenta(o),
    // `credits_remaining` je stanje NALOGA, ne svojstvo odgovora. Prikazuje se
    // u Kancelariji, ne uz pravni tekst.
    preostaloKredita: Number.isFinite(o.credits_remaining) ? o.credits_remaining : null,
  };
}
