/* Vindex V2 — finansije kancelarije: stanje naplate, nefakturisan rad,
 * izvestaji (F6/F7).
 *
 * ─────────────────────────────────────────────────────────────────────────
 * TRI IZNOSA KOJA SE NIKAD NE SMEJU SPOJITI
 *
 *   NEFAKTURISANO  — moj rad koji jos nije usao ni u jednu fakturu.
 *                    Klijent ovo NE DUGUJE: nije mu ni ispostavljeno.
 *   NEIZMIRENO     — faktura je izdata i nije placena. Ovo klijent duguje.
 *   NACRT          — faktura postoji kao nacrt i nije izdata. Ovo nije ni
 *                    potrazivanje ni prihod; to je moj nedovrsen posao.
 *
 * Backend ih vraca odvojeno (`neobracunato`, `neizmireno`, `nacrt_iznos`) i
 * ovaj modul ih drzi odvojenima. Sabrati ih u jedan broj „dugovanja" znacilo
 * bi reci advokatu da mu klijenti duguju novac koji nikada nije ni trazen —
 * i obrnuto, prikazati sve kao „nefakturisano" sakrilo bi ono sto stvarno
 * treba naplatiti.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * ODSUTAN IZNOS NIJE NULA. Kad polje ne stigne, `dinar()` kaze da se ne zna.
 * „0 RSD" na mestu nepoznatog je tvrdnja da duga nema.
 *
 * NEPOTPUN IZVOR SE IMENUJE. `/billing/dugovanja` vraca `nepotpuno` kada
 * dopunski izvor (npr. nazivi predmeta) nije procitan. Prikaz to mora reci,
 * jer bi „—" umesto naziva izgledao kao predmet bez naziva.
 */

import { dinar, broj } from "./naplata.js";

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

function ceoBroj(v) {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

/* ── Stanje naplate ─────────────────────────────────────────────────────── */
export function uStanjeNaplate(sirov) {
  const o = sirov || {};
  return {
    // Moj rad koji nije fakturisan — NIJE dug klijenta.
    nefakturisano: dinar(o.neobracunato),
    // Izdata i neplacena faktura — OVO klijent duguje.
    neizmireno: dinar(o.neizmireno),
    // Nacrt nije ispostavljen nikome.
    nacrt: dinar(o.nacrt_iznos),
    naplaceno: dinar(o.naplaceno),
    fakturisano: dinar(o.fakturisano),
    fakturaUkupno: ceoBroj(o.fakture_ukupno),
    fakturaPlacene: ceoBroj(o.fakture_placene),
    fakturaIzdate: ceoBroj(o.fakture_izdate),
  };
}

/* ── Nefakturisan rad po predmetu ───────────────────────────────────────── */
export function uNefakturisano(sirov) {
  const o = sirov || {};
  const grupe = (Array.isArray(o.dugovanja) ? o.dugovanja : [])
    .map(g => {
      const gg = g || {};
      const naziv = tekst(gg.predmet_naziv);
      return {
        predmetId: tekst(gg.predmet_id),
        // „—" je serverova oznaka za naziv koji nije procitan. Ne prikazuje
        // se kao naziv predmeta, nego kao izricito nepoznat.
        naziv: naziv && naziv !== "—" ? naziv : "",
        nazivPoznat: !!naziv && naziv !== "—",
        stavke: (Array.isArray(gg.stavke) ? gg.stavke : []).map(s => ({
          id: tekst(s && s.id),
          opis: tekst(s && s.opis) || "Bez opisa",
          iznos: dinar(s && s.iznos_rsd),
          datum: tekst(s && s.datum),
        })),
        ukupno: dinar(gg.ukupno_rsd),
        ukupnoBroj: broj(gg.ukupno_rsd),
      };
    })
    .filter(g => g.predmetId || g.stavke.length);

  return {
    grupe,
    ukupno: dinar(o.ukupno_rsd),
    predmeta: ceoBroj(o.predmeta),
    stavki: ceoBroj(o.stavki),
    // Izvori koje server nije uspeo da procita — imenuju se, ne precutkuju.
    nepotpuno: (Array.isArray(o.nepotpuno) ? o.nepotpuno : []).map(tekst).filter(Boolean),
  };
}

/* ── Godisnji izvestaj ──────────────────────────────────────────────────── */
export function uGodisnji(sirov) {
  const o = sirov || {};
  const meseci = (Array.isArray(o.po_mesecima) ? o.po_mesecima : []).map(m => ({
    mesec: tekst(m && m.mesec),
    uneseno: dinar(m && m.uneseno),
    unesenoBroj: broj(m && m.uneseno),
    naplaceno: dinar(m && m.naplaceno),
    naplacenoBroj: broj(m && m.naplaceno),
    stavki: ceoBroj(m && m.stavki),
  }));
  const stopa = o.stopa_naplate_pct;
  return {
    godina: ceoBroj(o.godina),
    uneseno: dinar(o.ukupno_uneseno_rsd),
    fakturisano: dinar(o.ukupno_fakturisano),
    naplaceno: dinar(o.ukupno_naplaceno_rsd),
    // Stopa naplate se prikazuje SAMO ako je bilo sta fakturisano: 0% nad
    // nulom nije „lose naplacujem" nego „nema sta da se naplati".
    stopa: broj(stopa),
    stopaZnacajna: broj(o.ukupno_fakturisano) !== null && broj(o.ukupno_fakturisano) > 0,
    meseci,
    // Najveci mesec u godini — merilo za trake, nikad procenat od izmisljenog
    // maksimuma.
    vrh: meseci.reduce((max, m) => Math.max(max, m.unesenoBroj || 0, m.naplacenoBroj || 0), 0),
  };
}

/* ── Rad po tipu predmeta ───────────────────────────────────────────────── */
export function uPoTipu(sirov) {
  const o = sirov || {};
  return {
    od: tekst(o.od),
    do: tekst(o.do),
    ukupno: dinar(o.ukupno_rsd),
    ukupnoBroj: broj(o.ukupno_rsd),
    redovi: (Array.isArray(o.po_tipu) ? o.po_tipu : []).map(r => ({
      tip: tekst(r && (r.tip || r.naziv)),
      iznos: dinar(r && (r.iznos_rsd || r.ukupno_rsd)),
      iznosBroj: broj(r && (r.iznos_rsd || r.ukupno_rsd)),
      stavki: ceoBroj(r && r.stavki),
    })).filter(r => r.tip),
    nepotpuno: (Array.isArray(o.nepotpuno) ? o.nepotpuno : []).map(tekst).filter(Boolean),
  };
}
