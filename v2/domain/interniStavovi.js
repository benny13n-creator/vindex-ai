/* Vindex V2 — Interni pravni stavovi firme (D9), domenski sloj.
 *
 * `pretragaNeuspesna` (Z017.2 backend popravka, interni_stavovi.py) NIKAD
 * ne sme da se pomesa sa "izvrsena pretraga, 0 pogodaka" -- isti invarijant
 * kao B-U-003 za /api/pitanje.
 */

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

function uRezultat(sirov) {
  const r = sirov || {};
  return {
    naslov: tekst(r.naslov) || "Bez naslova",
    tekst: tekst(r.tekst),
    score: Number.isFinite(r.score) ? r.score : null,
  };
}

export function uPretragu(sirov) {
  const o = sirov || {};
  return {
    rezultati: Array.isArray(o.rezultati) ? o.rezultati.map(uRezultat) : [],
    ukupno: Number.isFinite(o.ukupno) ? o.ukupno : 0,
    pretragaNeuspesna: o.pretraga_neuspesna === true,
  };
}

export function nedostaciStava(naslov, tekstStava) {
  const g = [];
  if (tekst(naslov).length < 3) g.push("Naslov mora imati najmanje 3 znaka.");
  if (tekst(tekstStava).length < 30) g.push("Tekst stava mora imati najmanje 30 znakova.");
  return g;
}
