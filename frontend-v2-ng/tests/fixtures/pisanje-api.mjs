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

/* PATCH /api/predmeti/{id} (api.py::update_predmet): samo dozvoljena polja (inače 400);
 * vlasnik iz tokena; `if_updated_at` ≠ trenutni → 409; tuđ/nepostojeći → 404;
 * svaki upis pomera updated_at (trigger); vraća {ok, updated_at}. */
const DOZVOLJENO = ["naziv", "opis", "tip", "status", "tuzilac", "tuzeni", "oblast", "rizik", "vrednost_spora"];
export function izmenaPredmetaRuta(korisnici, kuke = {}) {
  let takt = 0;
  return async (req, url, res) => {
    const m = /^\/api\/predmeti\/([^/]+)$/.exec(url.pathname);
    if (!m || req.method !== "PATCH") return false;
    const sirovo = await citajTelo(req);
    const k = korisnik(req, korisnici);
    if (await kuka(kuke, url.pathname, k, req, res)) return true;
    if (!k) { json(res, 401, { detail: "Unauthorized" }); return true; }
    let b; try { b = JSON.parse(sirovo || "{}"); } catch { json(res, 400, { detail: "bad json" }); return true; }
    const polja = Object.fromEntries(Object.entries(b).filter(([x]) => DOZVOLJENO.includes(x)));
    if (!Object.keys(polja).length) { json(res, 400, { detail: "Nema validnih polja za update" }); return true; }
    const p = k.predmeti.find(x => x.id === decodeURIComponent(m[1]) && x.user_id === k.id);
    if (!p) { json(res, 404, { detail: "Predmet nije pronađen" }); return true; }
    if (b.if_updated_at && b.if_updated_at !== p.updated_at) { json(res, 409, { detail: "Predmet je izmenjen u međuvremenu." }); return true; }
    Object.assign(p, polja);
    p.updated_at = new Date(Date.now() + (++takt)).toISOString();
    (kuke.upisano || (() => {}))(p, b);
    json(res, 200, { ok: true, updated_at: p.updated_at });
    return true;
  };
}

/* POST /api/predmeti/{id}/beleske (api.py::dodaj_belesku): vlasnik predmeta pre upisa;
 * prazan sadrzaj → 400; vraća {beleska}. Tuđ predmet: stvarna ruta puca na `.single()`
 * (500, ništa upisano) — emulira se isto. Beleške se čuvaju u k.beleske[id] (najnovija prva). */
export function beleskaRuta(korisnici, kuke = {}) {
  let n = 0;
  return async (req, url, res) => {
    const m = /^\/api\/predmeti\/([^/]+)\/beleske$/.exec(url.pathname);
    if (!m || req.method !== "POST") return false;
    const sirovo = await citajTelo(req);
    const k = korisnik(req, korisnici);
    if (await kuka(kuke, url.pathname, k, req, res)) return true;
    if (!k) { json(res, 401, { detail: "Unauthorized" }); return true; }
    const id = decodeURIComponent(m[1]);
    if (!k.predmeti.some(x => x.id === id && x.user_id === k.id)) { json(res, 500, { detail: "postgrest single: 0 rows" }); return true; }
    let b; try { b = JSON.parse(sirovo || "{}"); } catch { json(res, 400, { detail: "bad json" }); return true; }
    const sadrzaj = String(b.sadrzaj || "").trim();
    if (!sadrzaj) { json(res, 400, { detail: "sadrzaj je obavezan" }); return true; }
    const red = { id: `bel-${k.id}-${++n}`, predmet_id: id, user_id: k.id, sadrzaj, created_at: new Date().toISOString() };
    k.beleske = k.beleske || {};
    (k.beleske[id] = k.beleske[id] || []).unshift(red);
    (kuke.upisano || (() => {}))(red, b);
    json(res, 200, { beleska: red });
    return true;
  };
}
