/* Vindex V2 — nazivi koje korisnik cita.
 *
 * Ovo je CIST domenski sloj: preslikava sirovi enum iz baze u srpski naziv.
 * Nema DOM-a, nema mreze, nema stanja.
 *
 * Zasto ovde a ne u bazi: display naziv je proizvodna odluka koja se menja
 * cesce od podatka i ne sme traziti migraciju. Baza cuva `aktivan`, korisnik
 * cita „Aktivan". Sirovi enum se korisniku NE prikazuje (Z015 §19).
 */

const STANJE = {
  aktivan:    "Aktivan",
  aktivno:    "Aktivan",
  u_toku:     "U toku",
  zavrsen:    "Završen",
  zavrseno:   "Završen",
  arhiviran:  "Arhiviran",
  na_cekanju: "Na čekanju",
  pauziran:   "Pauziran",
};

/** Kljuc za semanticku boju. Namerno grub: tri klase, ne po jedna za svaki enum. */
const STANJE_KLASA = {
  aktivan: "aktivan", aktivno: "aktivan", u_toku: "aktivan",
  zavrsen: "zavrsen", zavrseno: "zavrsen", arhiviran: "zavrsen",
  na_cekanju: "mirovanje", pauziran: "mirovanje",
};

/* `predmeti.tip` NIJE kontrolisan recnik. Merenje na produkciji (23 predmeta):
 * radni_spor, Parnica, opsti, ugovorni_spor, nasledstvo, naknada_stete,
 * potrosacki_spor, ostalo — samo 1 od 23 pogadja negdasnji uzi recnik.
 * Zato ovde stoje kurirani nazivi ZA POZNATE kljuceve, a nepoznata vrednost
 * se citljivo ispisuje umesto da nestane (vidi `nazivVrste`). */
const VRSTA = {
  parnicni:        "Parnični",
  parnica:         "Parnica",
  parnicni_spor:   "Parnični spor",
  krivicni:        "Krivični",
  upravni:         "Upravni",
  prekrsajni:      "Prekršajni",
  izvrsni:         "Izvršni",
  radni:           "Radni",
  radni_spor:      "Radni spor",
  privredni:       "Privredni",
  privredni_spor:  "Privredni spor",
  porodicni:       "Porodični",
  nasledstvo:      "Nasledstvo",
  naknada_stete:   "Naknada štete",
  ugovorni_spor:   "Ugovorni spor",
  potrosacki_spor: "Potrošački spor",
  opsti:           "Opšti",
  ostalo:          "Ostalo",
};

function normalizuj(v) {
  return String(v || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

/**
 * Nepoznata sirova vrednost se ne brise nego se cita: `radni_spor` -> „Radni
 * spor". To NIJE izmisljanje — to je ista informacija koju je korisnik uneo,
 * samo bez donje crte. Brisanje stvarnog podatka je gore od prikaza sirovog:
 * advokat bi video prazno polje kod predmeta koji vrstu ima.
 */
function citljivo(sirovo) {
  const s = String(sirovo == null ? "" : sirovo).trim().replace(/[_]+/g, " ");
  if (!s) return "";
  const sazeto = s.replace(/\s+/g, " ");
  return sazeto.charAt(0).toLocaleUpperCase("sr-RS") + sazeto.slice(1);
}

/**
 * Prazno stanje je „—". Nepoznato stanje se ISPISUJE citljivo, jer je to
 * podatak koji u bazi postoji; „—" bi tvrdilo da predmet stanje nema.
 * Boju i dalje odredjuje `klasaStanja`, koja za nepoznato ostaje neutralna —
 * rec se prikazuje, semantika se ne pogadja.
 */
export function nazivStanja(sirovo) {
  const k = normalizuj(sirovo);
  if (!k) return "—";
  return STANJE[k] || citljivo(sirovo) || "—";
}

export function klasaStanja(sirovo) {
  const k = normalizuj(sirovo);
  return STANJE_KLASA[k] || "nepoznato";
}

export function nazivVrste(sirovo) {
  const k = normalizuj(sirovo);
  if (!k) return "";
  return VRSTA[k] || citljivo(sirovo);
}

/** Datum u obliku koji advokat prepisuje, ne u ISO obliku iz baze. */
export function datum(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const dan = String(d.getDate()).padStart(2, "0");
  const mesec = String(d.getMonth() + 1).padStart(2, "0");
  return `${dan}.${mesec}.${d.getFullYear()}.`;
}
