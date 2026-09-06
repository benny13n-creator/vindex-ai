/* Vindex V2 — saradnja (B18), domenski sloj.
 *
 * Deljenje predmeta izmedju advokata. Uloga NIJE binarna: citanje/saradnja/
 * vodenje nose razlicita prava i UI ih imenuje razlicito, ne kao generican
 * "clan". Backend (`routers/saradnja.py`) je jedini izvor istine o pravima --
 * ovaj sloj samo prevodi njegov odgovor u citljiv oblik, ne odlucuje sam.
 */

const ULOGA_LABELS = {
  citanje: "Čitanje",
  saradnja: "Saradnja",
  vodenje: "Vođenje",
};

export const ULOGE = Object.freeze([
  { kljuc: "citanje", naziv: "Čitanje" },
  { kljuc: "saradnja", naziv: "Saradnja" },
  { kljuc: "vodenje", naziv: "Vođenje" },
]);

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

/** Nepoznata/prazna uloga NIKAD ne postaje jedna od tri stvarne -- ostaje
 * vidljivo drugacija, isti zakon kao `nazivStanja`/`nazivVrste` (Z015 §19). */
export function nazivUloge(sirovo) {
  const k = tekst(sirovo).toLowerCase();
  return ULOGA_LABELS[k] || "—";
}

export function uSaradnika(sirov) {
  const p = sirov || {};
  return {
    id: tekst(p.saradnik_user_id || p.id),
    email: tekst(p.email) || "—",
    uloga: tekst(p.uloga),
    ulogaNaziv: nazivUloge(p.uloga),
    dodat: tekst(p.dodat || p.created_at),
  };
}

export function uSaradnike(sirov) {
  const lista = Array.isArray(sirov) ? sirov : (sirov && sirov.saradnici) || [];
  return lista.map(uSaradnika);
}

/** Moja uloga na predmetu -- backend vraca {uloga: 'vlasnik'|'citanje'|
 * 'saradnja'|'vodenje'|null}. `null` znaci "nemam nikakvu vezu", ne "nepoznato". */
export function mojaUloga(sirov) {
  const u = tekst((sirov && sirov.uloga) || "");
  return u || null;
}

export function jeVlasnik(sirov) {
  return mojaUloga(sirov) === "vlasnik";
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validanEmail(v) {
  return EMAIL_RE.test(tekst(v));
}
