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

const VRSTA = {
  parnicni:      "Parnični",
  krivicni:      "Krivični",
  upravni:       "Upravni",
  prekrsajni:    "Prekršajni",
  izvrsni:       "Izvršni",
  radni:         "Radni",
  privredni:     "Privredni",
  porodicni:     "Porodični",
  ostalo:        "Ostalo",
};

function normalizuj(v) {
  return String(v || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

/** Nepoznat enum NE postaje sirovi kljuc na ekranu. Vraca se neutralan naziv. */
export function nazivStanja(sirovo) {
  const k = normalizuj(sirovo);
  if (!k) return "—";
  return STANJE[k] || "—";
}

export function klasaStanja(sirovo) {
  const k = normalizuj(sirovo);
  return STANJE_KLASA[k] || "nepoznato";
}

export function nazivVrste(sirovo) {
  const k = normalizuj(sirovo);
  if (!k) return "";
  return VRSTA[k] || "";
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
