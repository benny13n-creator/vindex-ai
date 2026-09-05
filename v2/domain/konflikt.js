/* Vindex V2 — provera sukoba interesa.
 *
 * OWNER-LOCKED PRODUCT INVARIANT (Z017.1 §4):
 * Kada se pri otvaranju predmeta unese ili poveze stranka/klijent, kanonska
 * provera konflikta MORA biti izvrsena, a blokirajuci nalaz MORA zaustaviti
 * tok. Ovaj modul je jedino mesto koje odlucuje sta koji ishod ZNACI.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * CETIRI ISHODA, NE TRI
 *
 * Backend vraca `status` (clear|conflict|review) I ODVOJENO `provera_potpuna`.
 * Ta dva se NE SMEJU spojiti:
 *
 *   status=clear, provera_potpuna=true   -> PROVERENO, nema konflikta
 *   status=clear, provera_potpuna=false  -> NIJE PROVERENO  <-- ne sme „clear"
 *   status=review                        -> ljudska provera pre odluke
 *   status=conflict                      -> BLOKIRA
 *
 * Druga kombinacija je cela poenta. `conflict_check` je vec jednom u istoriji
 * ovog proizvoda „uspesno pretrazivao prazno" i zato javljao „Mozete
 * prihvatiti klijenta" (BETA blocker, `657818a5`). Zato se ovde nepotpuna
 * provera NIKAD ne prikazuje kao cista — fail-closed.
 *
 * SISTEM PODUDARANJA SE NE DIRA. Ovaj modul ne racuna slicnost, ne radi
 * substring poredjenje i ne spusta prag. Kanonski matching zivi u backendu
 * (`routers/conflict_check.py`); ovde se samo cita njegov ishod.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * Cist modul: bez DOM-a, bez mreze, bez stanja.
 */

import { ocistiNaslov } from "./danas.js";

/** Ishodi kojima ekran barata. `nepotpuna` je izveden, ne serverski. */
export const ISHOD = Object.freeze({
  CISTO: "cisto",
  PREGLED: "pregled",
  KONFLIKT: "konflikt",
  NEPOTPUNA: "nepotpuna",
});

/** Sme li se tok nastaviti bez izricite ljudske potvrde. */
export const NASTAVAK = Object.freeze({
  SLOBODNO: "slobodno",     // cisto i provereno
  UZ_POTVRDU: "uz_potvrdu",  // covek mora svesno da nastavi
  BLOKIRANO: "blokirano",    // tok se zaustavlja
});

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

/**
 * Ima li sta da se proverava.
 *
 * Backend na prazan zahtev vraca `status:"clear"` — sto je tacno, ali bi na
 * ekranu znacilo „provereno, cisto" za proveru koja se nikad nije desila.
 * Zato se odluka o tome DA LI zvati donosi ovde, pre poziva.
 */
export function imaStaDaSeProveri({ ime_prezime, firma } = {}) {
  return Boolean(tekst(ime_prezime) || tekst(firma));
}

/** Termini za proveru iz polja obrasca „Nov predmet". */
export function upitIzStranaka({ tuzilac, tuzeni, klijent } = {}) {
  const upiti = [];
  for (const [uloga, vrednost] of [["tužilac", tuzilac], ["tuženi", tuzeni], ["klijent", klijent]]) {
    const v = tekst(vrednost);
    if (v) upiti.push({ uloga, ime_prezime: v });
  }
  return upiti;
}

/** Jedan nadjen konflikt, bez internih identifikatora i bez emodzija. */
export function uKonflikt(sirov) {
  const k = sirov || {};
  return {
    naziv: ocistiNaslov(tekst(k.naziv || k.klijent || k.predmet_naziv)) || "Bez naziva",
    sloj: tekst(k.sloj),
    predmet: ocistiNaslov(tekst(k.predmet_naziv || k.predmet)) || "",
    predmetId: tekst(k.predmet_id),
    uloga: tekst(k.uloga),
    aktivan: Boolean(k.aktivan ?? (tekst(k.status).toLowerCase() === "aktivan")),
    // `severitet`/`score` se NE prikazuju kao broj: ocena slicnosti bez
    // objasnjenja je tacno ono sto kanon zabranjuje, a advokatu ne kazuje
    // nista sto mu naziv predmeta vec ne kaze.
    visok: tekst(k.severitet).toLowerCase() === "visok",
  };
}

/**
 * Prevodi serverski odgovor u ishod kojim ekran sme da barata.
 *
 * ODSUTAN ODGOVOR NIJE CIST ODGOVOR. `null` (pad poziva, prekid, nepoznat
 * oblik) daje `NEPOTPUNA`, nikad `CISTO`.
 */
export function uIshod(sirov) {
  const o = sirov || {};
  const status = tekst(o.status).toLowerCase();
  const konflikti = Array.isArray(o.konflikti) ? o.konflikti.map(uKonflikt) : [];
  const slojeviGreska = Array.isArray(o.slojevi_greska)
    ? o.slojevi_greska.map(tekst).filter(Boolean) : [];

  // `provera_potpuna` mora biti IZRICITO `true`. Odsutno polje se tretira kao
  // nepotpuno: stariji ili izmenjen backend ne sme tiho da prodje kao cist.
  const potpuna = o.provera_potpuna === true;

  if (!sirov || (!status && !konflikti.length)) {
    return {
      ishod: ISHOD.NEPOTPUNA,
      nastavak: NASTAVAK.UZ_POTVRDU,
      konflikti: [],
      slojeviGreska,
      naslov: "Provera sukoba interesa nije izvršena",
      telo: "Odsustvo rezultata NE znači da konflikta nema. Ponovite proveru pre "
          + "nego što otvorite predmet.",
    };
  }

  if (status === "conflict") {
    const aktivni = konflikti.filter(k => k.aktivan);
    return {
      ishod: ISHOD.KONFLIKT,
      nastavak: NASTAVAK.BLOKIRANO,
      konflikti,
      slojeviGreska,
      naslov: aktivni.length
        ? "Sukob interesa u aktivnom predmetu"
        : "Sukob interesa",
      telo: "Otvaranje predmeta je zaustavljeno. Proverite navedene predmete i "
          + "Kodeks profesionalne etike pre nego što prihvatite klijenta.",
    };
  }

  if (!potpuna) {
    return {
      ishod: ISHOD.NEPOTPUNA,
      nastavak: NASTAVAK.UZ_POTVRDU,
      konflikti,
      slojeviGreska,
      naslov: "Provera sukoba interesa nije potpuna",
      telo: (slojeviGreska.length
              ? "Nije pretraženo: " + slojeviGreska.join(", ") + ". "
              : "")
          + "Odsustvo rezultata NE znači da konflikta nema.",
    };
  }

  if (status === "review" || konflikti.length) {
    return {
      ishod: ISHOD.PREGLED,
      nastavak: NASTAVAK.UZ_POTVRDU,
      konflikti,
      slojeviGreska,
      naslov: "Pronađeno preklapanje koje traži proveru",
      telo: "Preklapanje je u zatvorenim predmetima ili je slabije. Pregledajte ga "
          + "pre nego što otvorite predmet.",
    };
  }

  return {
    ishod: ISHOD.CISTO,
    nastavak: NASTAVAK.SLOBODNO,
    konflikti: [],
    slojeviGreska,
    naslov: "Nije pronađen sukob interesa",
    telo: "",
  };
}

/**
 * Spaja ishode za vise stranaka u jedan. Najstroziji pobedjuje —
 * blokirajuci nalaz nad jednom strankom blokira ceo tok.
 */
export function spoji(ishodi) {
  const lista = (ishodi || []).filter(Boolean);
  if (!lista.length) return uIshod(null);

  const blok = lista.find(x => x.nastavak === NASTAVAK.BLOKIRANO);
  if (blok) {
    return { ...blok, konflikti: lista.flatMap(x => x.konflikti) };
  }
  const uzPotvrdu = lista.find(x => x.nastavak === NASTAVAK.UZ_POTVRDU);
  if (uzPotvrdu) {
    return {
      ...uzPotvrdu,
      konflikti: lista.flatMap(x => x.konflikti),
      slojeviGreska: [...new Set(lista.flatMap(x => x.slojeviGreska))],
    };
  }
  return lista[0];
}
