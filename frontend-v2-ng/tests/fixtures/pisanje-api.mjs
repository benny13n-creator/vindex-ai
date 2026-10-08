// NS005 — emulacija UGOVORA postojećih ruta za PISANJE (ne implementacije).
// Svaki handler: vlasnik iz `Authorization: Bearer <token>` (inače 401); telo
// `user_id` se IGNORIŠE kao u api.py; tuđ objekat → 404 kao u api.py.
// Kuke: `kuke.pre(putanja, korisnik)` → Promise (kašnjenje) ili {status, telo}
// ili {prekid: true} (veza se prekida posle prijema tela).

import { json } from "./api-fixture.mjs";

export function citajTelo(req) {
  return new Promise((r) => { const d = []; req.on("data", c => d.push(c)); req.on("end", () => r(Buffer.concat(d).toString("utf8"))); });
}

function korisnik(req, korisnici) {
  const a = req.headers.authorization || "";
  if (!a.startsWith("Bearer ")) return null;
  return korisnici[a.slice(7)] || null;
}

async function kuka(kuke, put, k, req, res) {
  if (!kuke.pre) return false;
  const z = await kuke.pre(put, k ? k.id : null);
  if (z && z.prekid) { req.socket.destroy(); return true; }
  if (z && z.status) { json(res, z.status, z.telo ?? { detail: "fixture" }); return true; }
  return res.destroyed;
}

/* POST /api/predmeti (api.py::kreiraj_predmet): naziv obavezan (400), isti naziv
 * istog korisnika u 5 s → 409, status „aktivan", vraća {predmet}. */
export function novPredmetRuta(korisnici, kuke = {}) {
  let brojac = 0;
  return async (req, url, res) => {
    if (url.pathname !== "/api/predmeti" || req.method !== "POST") return false;
    const sirovo = await citajTelo(req);
    const k = korisnik(req, korisnici);
    if (await kuka(kuke, url.pathname, k, req, res)) return true;
    if (!k) { json(res, 401, { detail: "Unauthorized" }); return true; }
    let b; try { b = JSON.parse(sirovo || "{}"); } catch { json(res, 400, { detail: "bad json" }); return true; }
    const naziv = String(b.naziv || "").trim();
    if (!naziv) { json(res, 400, { detail: "naziv je obavezan" }); return true; }
    const sada = Date.now();
    if (k.predmeti.some(p => p.user_id === k.id && p.naziv === naziv && sada - Date.parse(p.created_at) < 5000)) {
      json(res, 409, { detail: "Predmet sa ovim nazivom je upravo kreiran." }); return true;
    }
    const p = { id: `${k.id}-nov${++brojac}`, user_id: k.id, naziv, opis: String(b.opis || ""), tip: b.tip || "opsti", status: "aktivan",
      broj_predmeta: null, tuzilac: null, tuzeni: null, vrednost_spora: null, created_at: new Date(sada).toISOString(),
      updated_at: new Date(sada).toISOString(), brisanje_zapoceto: null };
    k.predmeti.push(p);
    (kuke.upisano || (() => {}))(p, b);
    let telo = { predmet: p };
    if (kuke.izmeniOdgovor) telo = kuke.izmeniOdgovor(telo);
    if (typeof telo === "string") { res.writeHead(200, { "Content-Type": "text/plain" }); res.end(telo); return true; }
    json(res, 200, telo);
    return true;
  };
}
