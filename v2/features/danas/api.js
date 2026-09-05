/* Vindex V2 — Danas, pristup podacima.
 *
 * Dva paralelna poziva, jer nijedan sam ne daje istinu:
 *
 *   /api/rokovi/kandidati   obaveze SA stanjem odluke (jedini izvor koji zna
 *                           da li je rok potvrdjen ili je samo predlog)
 *   /api/kalendar/pregled   rocista (druga tabela, drugi objekat) i nazivi
 *                           predmeta, koje kandidati ne vracaju
 *
 * DELIMICAN PAD NIJE PRAZAN EKRAN. Ako jedan izvor padne, drugi se i dalje
 * prikazuje, a ekran to KAZE. Zato se ovde ne koristi `Promise.all` (koji bi
 * jednim padom oborio oba) nego `allSettled`, i pad se pretvara u podatak
 * `__palo`, ne u izuzetak.
 */

import { dohvati } from "../../platform/http.js";
import { jePrekid } from "../../platform/errors.js";
import { sastavi } from "../../domain/danas.js";

/** Koliko unapred Danas gleda. Poklapa se sa poslednjom grupom „Narednih 7 dana". */
export const DANA_UNAPRED = 7;

/**
 * TEHNICKI opseg dohvatanja unazad — NIJE poslovno pravilo.
 *
 * Starost sama po sebi ne znaci nista: nereseni rok star 91 dan moze biti
 * vazniji od onog starog 20 dana. Ovaj broj postoji samo zato sto
 * `/api/rokovi/kandidati` mora dobiti neku donju granicu, i zato sto isti
 * endpoint ogranicava raspon na 365 dana.
 *
 * Pravilo „nereseno ne nestaje zato sto je staro" se ovde NE MOZE sprovesti:
 * `predmet_hronologija` nema nijednu kolonu o resenosti. To je zavisnost
 * kapije Rokovi i zadaci, ne odluka ovog ekrana.
 *
 * Zato UI nikad ne tvrdi da je ovo potpun spisak nerezenih obaveza.
 */
export const DANA_UNAZAD = 90;

function isoPomeraj(dana) {
  const d = new Date();
  d.setDate(d.getDate() + dana);
  return d.toISOString().slice(0, 10);
}

export async function ucitajDanas({ signal } = {}) {
  const od = isoPomeraj(-DANA_UNAZAD);
  const doDatum = isoPomeraj(DANA_UNAPRED);

  const [k, c] = await Promise.allSettled([
    dohvati("/api/rokovi/kandidati", { upit: { od, dana: DANA_UNAPRED }, signal }),
    dohvati("/api/kalendar/pregled", { upit: { od, do: doDatum }, signal }),
  ]);

  // Otkazivanje nije pad izvora — pozivalac ga prepoznaje i cuti.
  for (const r of [k, c]) {
    if (r.status === "rejected" && jePrekid(r.reason)) throw r.reason;
  }

  const kandidati = k.status === "fulfilled" ? k.value : { rokovi: [], __palo: true };
  const kalendar = c.status === "fulfilled" ? c.value : { dogadjaji: [], __palo: true };

  // Oba izvora pala -> to nije „nema obaveza", nego greska. Baca se dalje.
  if (kandidati.__palo && kalendar.__palo) throw k.reason || c.reason;

  // Nazivi predmeta inace dolaze iz kalendara. Kad kalendar padne, rok bi ostao
  // bez predmeta — a rok bez predmeta advokatu skoro nista ne znaci. Tada, i
  // SAMO tada, nazivi se izvlace iz registra. Jedan dodatni poziv na putanji
  // greske je jeftiniji od obaveze koju korisnik ne ume da smesti.
  if (kalendar.__palo && (kandidati.rokovi || []).length) {
    try {
      const reg = await dohvati("/api/predmeti", {
        upit: { view: "summary", limit: 200, offset: 0 }, signal,
      });
      kalendar.dogadjaji = (reg && reg.predmeti ? reg.predmeti : []).map(p => ({
        predmet_id: p.id, predmet_naziv: p.naziv, tip: "__samo_naziv",
      }));
    } catch (e) {
      if (jePrekid(e)) throw e;   // otkazivanje se ne guta
      // Ako i registar padne, obaveza se i dalje prikazuje — bez naziva.
    }
  }

  return sastavi({ kandidati, kalendar });
}

/** Prazan Danas nije prazan ekran: pokazuju se nedavno otvoreni predmeti. */
export async function ucitajNedavnePredmete({ signal } = {}) {
  const o = await dohvati("/api/predmeti", {
    upit: { view: "summary", limit: 5, offset: 0 },
    signal,
  });
  return Array.isArray(o && o.predmeti) ? o.predmeti : [];
}
