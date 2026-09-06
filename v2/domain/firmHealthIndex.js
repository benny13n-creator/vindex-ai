/* Vindex V2 — Firm Health Index (F10), domenski sloj.
 *
 * `izKesa` (staleness) MORA da se prikaze -- backend-ov sopstveni komentar
 * (routers/health_index.py) dokumentuje Red Team nalaz da se bez ovog
 * signala stara "88/A/Sve je u redu" ocena moze prikazati preko svežeg
 * "34/C/HITNO" preracunavanja, bez ijednog traga da je stara. Ovaj sloj tu
 * disciplinu prenosi, ne uklanja je.
 *
 * Alarm/insight recenice iz backend-a nose emoji PREFIKS kao deo teksta
 * (ne UI dekoracija koju ovaj sloj bira) -- skida se vodeci emoji+razmak
 * pre prikaza radi doslednosti sa vlasnickim kanonom (bez generickih
 * ikona), sam TEKST poruke se ne menja.
 */

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

// Skida vodeci emoji + razmak (npr. "⚠️ 5 predmeta..." -> "5 predmeta...").
// Samo VODECI simbol -- tekst posle njega je nepromenjen, ne parafraziran.
function bezVodecegEmoji(s) {
  return tekst(s).replace(/^[^\p{L}\p{N}]+\s*/u, "");
}

export function uHealthIndex(sirov) {
  const o = sirov || {};
  return {
    skor: Number.isFinite(o.score) ? o.score : null,
    ocena: tekst(o.grade),
    aktivnihPredmeta: Number.isFinite(o.n_aktivni) ? o.n_aktivni : null,
    zatvorenihPredmeta: Number.isFinite(o.n_zatvoreni) ? o.n_zatvoreni : null,
    komponente: Array.isArray(o.components) ? o.components.map(c => ({
      naziv: tekst(c && c.label),
      skor: Number.isFinite(c && c.score) ? c.score : null,
      max: Number.isFinite(c && c.max) ? c.max : null,
    })) : [],
    upozorenja: Array.isArray(o.alerts) ? o.alerts.map(bezVodecegEmoji).filter(Boolean) : [],
    uvidi: Array.isArray(o.insights) ? o.insights.map(bezVodecegEmoji).filter(Boolean) : [],
    chiefPartner: tekst(o.chief_partner),
    institucionalniRizici: Array.isArray(o.inst_risks) ? o.inst_risks.map(r => ({
      naslov: tekst(r && r.naslov),
      opis: tekst(r && r.opis),
    })).filter(r => r.naslov) : [],
    izKesa: o.iz_kesa === true,
    generisanoU: tekst(o.generated_at),
  };
}
