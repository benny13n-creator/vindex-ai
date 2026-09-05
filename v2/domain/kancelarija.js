/* Vindex V2 — domen prostora KANCELARIJA.
 *
 * Kancelarija je sve sto nije pravni rad: nalog, klijenti, naplata, tim.
 * To NISU cetiri table sa brojevima — svaki broj ovde mora da odgovori na
 * pitanje koje advokat stvarno postavlja, inace ne stoji na ekranu.
 *
 * DVA IZNOSA KOJA SE NIKAD NE SMEJU SPOJITI (B2, mereno uzivo):
 *   `uneseno`     — evidentiran rad, jos NIJE fakturisan
 *   `fakturisano` — izdato u fakturama
 * Ranije je mesecni izvestaj sabirao neobracunat rad kao `fakturisano_rsd`,
 * pa je kancelarija verovala da je izdala racune koje nije. Zato ovde ta dva
 * iznosa imaju razlicita imena, razlicite labele i nikad se ne sabiraju.
 *
 * KREDITI SU STANJE NALOGA, NE UCINAK. Prikazuju se kao broj koji je ostao,
 * bez procenta iskoriscenosti i bez trake koja se puni — to bi bio KPI bez
 * odluke koju pokrece.
 *
 * Cist modul: bez DOM-a, bez mreze, bez stanja.
 */

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

/**
 * Broj ili `null`. ODSUTNA VREDNOST NIJE NULA.
 *
 * `Number(null)` je 0 i `Number("")` je 0 — pa bi naivna konverzija iznos koji
 * backend NIJE poslao prikazala kao „0 RSD", tj. kao tvrdnju „ovog meseca
 * niste ispostavili nijedan racun". To je ista klasa greske koju je B2 vec
 * platio na drugom mestu: nepoznato prikazano kao izmereno.
 */
function broj(v) {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Iznos u dinarima, onako kako se cita. `null` kad iznosa nema. */
export function dinar(v) {
  const n = broj(v);
  if (n === null) return null;
  return n.toLocaleString("sr-RS", { maximumFractionDigits: 0 }) + " RSD";
}

/** Nalog: ko sam, sta imam, koliko mi je ostalo. */
export function uNalog(sirov) {
  const m = sirov || {};
  const preostalo = broj(m.credits_remaining);
  return {
    email: tekst(m.email),
    plan: m.is_pro ? "PRO" : "Besplatan",
    osnivac: Boolean(m.is_founder),
    krediti: preostalo,
    // `credits_total` je 9999 za osnivaca — broj bez znacenja za korisnika,
    // pa se ne prikazuje kao „od koliko".
    kreditiUkupno: m.is_founder ? null : broj(m.credits_total),
  };
}

/** Klijent u obliku za registar. Ime se sastavlja, nikad ne ostaje prazno. */
export function uKlijenta(sirov) {
  const k = sirov || {};
  const firma = tekst(k.firma);
  const ime = [tekst(k.ime), tekst(k.prezime)].filter(Boolean).join(" ");
  return {
    id: k.id || "",
    naziv: firma || ime || "Klijent bez naziva",
    // Fizicko lice i pravno lice se razlikuju; `tip` je u bazi slobodan tekst.
    vrsta: tekst(k.tip),
    email: tekst(k.email),
    telefon: tekst(k.telefon),
    stanje: tekst(k.status),
    // PIB se NE prikazuje u spisku: sifrovan je u bazi i nije pretraziv, pa
    // bi kolona bila prazna na svakom redu i lagala da podatak ne postoji.
  };
}

export function uKlijente(sirov) {
  const niz = (sirov && sirov.klijenti) || [];
  return {
    redovi: Array.isArray(niz) ? niz.map(uKlijenta) : [],
    ukupno: broj(sirov && sirov.ukupno),
  };
}

/**
 * Naplata za tekuci mesec. Svaki iznos nosi pitanje na koje odgovara —
 * bez toga je to samo broj na tabli, sto kanon zabranjuje.
 */
export function uNaplatu(sirov) {
  const b = sirov || {};
  const stavke = [
    { kljuc: "uneseno", naziv: "Evidentiran rad",
      pitanje: "Koliko sam ovog meseca odradio.", iznos: dinar(b.ukupno_unoseno) },
    { kljuc: "neobracunato", naziv: "Još nije fakturisano",
      pitanje: "Šta čeka da bude naplaćeno.", iznos: dinar(b.neobracunato) },
    { kljuc: "fakturisano", naziv: "Fakturisano",
      pitanje: "Koliko sam ispostavio računa.", iznos: dinar(b.fakturisano) },
    { kljuc: "naplaceno", naziv: "Naplaćeno",
      pitanje: "Koliko je stvarno leglo.", iznos: dinar(b.naplaceno) },
  ].filter(x => x.iznos !== null);
  return { mesec: tekst(b.mesec), stavke };
}

/** Tim kancelarije. Tri stanja koja se ne mesaju. */
export function uTim(sirov) {
  const t = sirov || {};
  const stanje = tekst(t.status);
  if (stanje === "no_firma") {
    return { stanje: "nema", poruka: "Niste član nijedne kancelarije." };
  }
  if (stanje === "pending_invite") {
    return {
      stanje: "poziv",
      poruka: `Pozvani ste u kancelariju „${tekst(t.firma_naziv)}".`,
      firma: tekst(t.firma_naziv),
    };
  }
  if (stanje !== "aktivan") {
    return { stanje: "nepoznato", poruka: "Podatak o kancelariji nije dostupan." };
  }
  const clanovi = Array.isArray(t.clanovi) ? t.clanovi : [];
  return {
    stanje: "aktivan",
    firma: tekst(t.firma && t.firma.naziv),
    mojaUloga: tekst(t.moja_uloga),
    clanovi: clanovi.map(c => ({
      id: (c && c.id) || "",
      email: tekst(c && c.email),
      uloga: tekst(c && (c.uloga_label || c.uloga)),
      stanje: tekst(c && c.status),
    })).filter(c => c.email),
  };
}
