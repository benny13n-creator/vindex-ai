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

/* ── Klijenti (klijenti/router.py) ────────────────────────────────────────
 * k.kartoteka = [{id, user_id, ime, prezime, firma, email, tip, jmbg_encrypted?}]
 * GET  /klijenti?pretraga=  → samo klijenti pozivaoca, BEZ šifrovanih polja; {klijenti, ukupno}
 * POST /klijenti            → ime < 2 znaka → 422; vlasnik iz tokena; {status:"kreiran", klijent} */
const JAVNA_POLJA = ["id", "tip", "ime", "prezime", "firma", "email", "telefon", "status"];
export function klijentiRuta(korisnici, kuke = {}) {
  let n = 0;
  return async (req, url, res) => {
    if (url.pathname !== "/klijenti") return false;
    const sirovo = req.method === "POST" ? await citajTelo(req) : "";
    const k = korisnik(req, korisnici);
    if (await kuka(kuke, url.pathname + ":" + req.method, k, req, res)) return true;
    if (!k) { json(res, 401, { detail: "Prijava je obavezna." }); return true; }
    k.kartoteka = k.kartoteka || [];
    if (req.method === "GET") {
      const q = (url.searchParams.get("pretraga") || "").toLowerCase();
      const svi = Object.values(korisnici).flatMap(x => x.kartoteka || []);
      const moji = svi.filter(x => x.user_id === k.id && (!q || [x.ime, x.prezime, x.firma].some(v => String(v || "").toLowerCase().includes(q))));
      json(res, 200, { klijenti: moji.map(x => Object.fromEntries(JAVNA_POLJA.map(c => [c, x[c] ?? ""]))), ukupno: moji.length });
      return true;
    }
    if (req.method !== "POST") { json(res, 405, { detail: "Method Not Allowed" }); return true; }
    let b; try { b = JSON.parse(sirovo || "{}"); } catch { json(res, 400, { detail: "bad json" }); return true; }
    if (String(b.ime || "").trim().length < 2) { json(res, 422, { detail: [{ loc: ["body", "ime"], msg: "too short" }] }); return true; }
    const red = { id: `kl-${k.id}-n${++n}`, user_id: k.id, tip: b.tip || "fizicko_lice", ime: b.ime, prezime: b.prezime || "", firma: b.firma || "",
      email: b.email || "", telefon: b.telefon || "", status: "aktivan" };
    k.kartoteka.push(red);
    (kuke.upisano || (() => {}))(red, b);
    json(res, 200, { status: "kreiran", klijent: Object.fromEntries(JAVNA_POLJA.map(c => [c, red[c]])) });
    return true;
  };
}

/* POST /api/conflict-check: traži SAMO u predmetima pozivaoca (tužilac/tuženi sadrži termin);
 * aktivan predmet → conflict, ostalo → review, ništa → clear; provera_potpuna=true.
 * kuke.coi(telo, korisnik) može da vrati {status, telo} (npr. pad, nepotpuna provera). */
export function coiRuta(korisnici, kuke = {}) {
  return async (req, url, res) => {
    if (url.pathname !== "/api/conflict-check" || req.method !== "POST") return false;
    const sirovo = await citajTelo(req);
    const k = korisnik(req, korisnici);
    if (!k) { json(res, 401, { detail: "Unauthorized" }); return true; }
    let b; try { b = JSON.parse(sirovo || "{}"); } catch { json(res, 400, { detail: "bad json" }); return true; }
    if (kuke.coi) { const z = await kuke.coi(b, k.id); if (z && z.prekid) { req.socket.destroy(); return true; } if (z && z.status) { json(res, z.status, z.telo ?? {}); return true; } }
    const termini = [b.ime_prezime, b.firma].filter(Boolean).map(x => String(x).toLowerCase());
    const konflikti = [];
    for (const p of k.predmeti.filter(x => x.user_id === k.id)) {
      for (const [polje, v] of [["tuzilac", p.tuzilac], ["tuzeni", p.tuzeni]]) {
        if (termini.some(t => String(v || "").toLowerCase().includes(t))) {
          konflikti.push({ sloj: "predmeti", tip_konflikta: polje, sever: "VISOK", predmet_id: p.id, predmet_naziv: p.naziv, predmet_status: p.status, podudaranje: v });
          break;
        }
      }
    }
    const aktivni = konflikti.filter(x => ["aktivan", "u_toku"].includes(x.predmet_status));
    const status = aktivni.length ? "conflict" : konflikti.length ? "review" : "clear";
    json(res, 200, { status, provera_potpuna: true, slojevi_greska: [], konflikti, poruka: "🚨 serverska poruka sa emodžijem", ukupno: konflikti.length });
    return true;
  };
}

/* POST /api/predmeti/{id}/confirm-links: vlasnik predmeta (inače 500 kao `.single()`),
 * tuđ klijent se tiho izostavlja; vezani klijenti idu u k.klijenti[id] (detalj ih vraća). */
export function vezaRuta(korisnici, kuke = {}) {
  return async (req, url, res) => {
    const m = /^\/api\/predmeti\/([^/]+)\/confirm-links$/.exec(url.pathname);
    if (!m || req.method !== "POST") return false;
    const sirovo = await citajTelo(req);
    const k = korisnik(req, korisnici);
    if (await kuka(kuke, url.pathname, k, req, res)) return true;
    if (!k) { json(res, 401, { detail: "Unauthorized" }); return true; }
    const id = decodeURIComponent(m[1]);
    if (!k.predmeti.some(x => x.id === id && x.user_id === k.id)) { json(res, 500, { detail: "single: 0 rows" }); return true; }
    let b; try { b = JSON.parse(sirovo || "{}"); } catch { json(res, 400, { detail: "bad json" }); return true; }
    const linked = [];
    for (const kid of (b.klijent_ids || []).slice(0, 5)) {
      const kl = (k.kartoteka || []).find(x => x.id === kid && x.user_id === k.id);
      if (!kl || kuke.odbijKlijenta) continue;
      k.klijenti = k.klijenti || {};
      const lista = (k.klijenti[id] = k.klijenti[id] || []);
      if (!lista.some(x => x.id === kid)) lista.push({ id: kl.id, ime: kl.ime, prezime: kl.prezime, firma: kl.firma, uloga: b.uloga || "stranka" });
      linked.push(kid);
    }
    (kuke.upisano || (() => {}))(linked, b);
    json(res, 200, { success: true, linked_klijenti: linked, rok_dodat: false });
    return true;
  };
}

/* ── Ročišta (routers/rocista.py) ── k.rocista = [{id, predmet_id, user_id, sud, datum, vreme, status, ...}]
 * GET  /api/rocista?predmet_id=  → samo pozivaočeva (po user_id), po datumu; {rocista, ukupno}
 * POST /api/rocista              → predmet mora biti pozivaočev (404); datum YYYY-MM-DD (422); {rociste} */
export function rocistaRuta(korisnici, kuke = {}) {
  let n = 0;
  return async (req, url, res) => {
    if (url.pathname !== "/api/rocista") return false;
    const sirovo = req.method === "POST" ? await citajTelo(req) : "";
    const k = korisnik(req, korisnici);
    if (await kuka(kuke, url.pathname + ":" + req.method, k, req, res)) return true;
    if (!k) { json(res, 401, { detail: "Unauthorized" }); return true; }
    const svi = Object.values(korisnici).flatMap(x => x.rocista || []);
    if (req.method === "GET") {
      const pid = url.searchParams.get("predmet_id");
      let r = svi.filter(x => x.user_id === k.id && (!pid || x.predmet_id === pid)).sort((a, b) => (a.datum < b.datum ? -1 : 1));
      if (kuke.izmeniListu) r = kuke.izmeniListu(r);
      json(res, 200, { rocista: r, ukupno: r.length });
      return true;
    }
    if (req.method !== "POST") { json(res, 405, {}); return true; }
    let b; try { b = JSON.parse(sirovo || "{}"); } catch { json(res, 400, {}); return true; }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(b.datum || "") || !String(b.sud || "").trim()) { json(res, 422, { detail: [{ loc: ["body", "datum"] }] }); return true; }
    if (!k.predmeti.some(p => p.id === b.predmet_id && p.user_id === k.id)) { json(res, 404, { detail: "Predmet nije pronađen" }); return true; }
    const red = { id: `roc-${k.id}-${++n}`, predmet_id: b.predmet_id, user_id: k.id, sud: b.sud, datum: b.datum, vreme: b.vreme || null,
      sudnica: b.sudnica || null, broj_predmeta_suda: b.broj_predmeta_suda || null, napomena: b.napomena || null, status: "zakazano" };
    (k.rocista = k.rocista || []).push(red);
    (kuke.upisano || (() => {}))(red, b);
    json(res, 200, { rociste: red, ok: true });
    return true;
  };
}

/* GET /api/search: samo podaci pozivaoca; kuke.nepotpuno = ["dokumenti"] simulira pad grane. */
export function pretragaRuta(korisnici, kuke = {}) {
  return async (req, url, res) => {
    if (url.pathname !== "/api/search" || req.method !== "GET") return false;
    const k = korisnik(req, korisnici);
    if (await kuka(kuke, url.pathname, k, req, res)) return true;
    if (!k) { json(res, 401, { detail: "Unauthorized" }); return true; }
    const q = (url.searchParams.get("q") || "").trim().toLowerCase();
    if (q.length < 2) { json(res, 422, { detail: "Upit mora imati barem 2 karaktera." }); return true; }
    const nep = kuke.nepotpuno || [];
    const sadrzi = (v) => String(v || "").toLowerCase().includes(q);
    const moji = k.predmeti.filter(p => p.user_id === k.id);
    const out = { q, predmeti: [], dokumenti: [], beleske: [], hronologija: [] };
    if (!nep.includes("predmeti")) out.predmeti = moji.filter(p => sadrzi(p.naziv)).map(p => ({ tip: "predmet", id: p.id, naziv: p.naziv, preview: "", meta: { status: p.status } }));
    if (!nep.includes("dokumenti")) out.dokumenti = (k.dokumentiPretraga || []).filter(d => sadrzi(d.naziv_fajla)).map(d => ({ tip: "dokument", id: d.id, naziv: d.naziv_fajla, preview: "", meta: { predmet_id: d.predmet_id } }));
    if (!nep.includes("beleske")) out.beleske = Object.entries(k.beleske || {}).flatMap(([pid, l]) => l.filter(b => sadrzi(b.sadrzaj)).map(b => ({ tip: "beleska", id: b.id, naziv: b.sadrzaj.slice(0, 60), preview: b.sadrzaj, meta: { predmet_id: pid } })));
    out.ukupno = out.predmeti.length + out.dokumenti.length + out.beleske.length;
    if (nep.length) out.nepotpuno = nep;
    json(res, 200, out);
    return true;
  };
}
