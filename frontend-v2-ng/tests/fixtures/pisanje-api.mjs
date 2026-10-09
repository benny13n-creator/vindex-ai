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

/* POST /api/pitanje (api.py::pitanje): {pitanje 3–2000, predmet_id} → 200 + normalizovan odgovor.
 * kontekst_predmeta: true samo ako je predmet pozivaočev, false za tuđ, null bez predmet_id.
 * Scenario po sadržaju pitanja (emulira ishode STVARNOG ask_agent-a, v. test_ns005_t6):
 *   „bez izvora" → LOW, bez `izvori`, tekst odbijanja; „9999" → odbijanje izmišljenog člana;
 *   „pad korpusa" → retrieval_unavailable; „delimično" → izvori_neuspeh; inače HIGH sa izvorima. */
export function pitanjeRuta(korisnici, kuke = {}) {
  return async (req, url, res) => {
    if (url.pathname !== "/api/pitanje" || req.method !== "POST") return false;
    const sirovo = await citajTelo(req);
    const k = korisnik(req, korisnici);
    if (await kuka(kuke, url.pathname, k, req, res)) return true;
    if (!k) { json(res, 401, { detail: "Unauthorized" }); return true; }
    let b; try { b = JSON.parse(sirovo || "{}"); } catch { json(res, 400, {}); return true; }
    const p = String(b.pitanje || "");
    if (p.length < 3 || p.length > 2000) { json(res, 422, { detail: [{ loc: ["body", "pitanje"] }] }); return true; }
    (kuke.upisano || (() => {}))(b);
    const kontekst = b.predmet_id ? k.predmeti.some(x => x.id === b.predmet_id && x.user_id === k.id) : null;
    const osnova = { credits_remaining: 9, kontekst_predmeta: kuke.kontekst !== undefined ? kuke.kontekst : kontekst };
    const NAPOMENA = "\n\n---\n\n⚠️ **Pravna napomena:** Vindex AI pruža informacije zasnovane na zakonskim tekstovima Republike Srbije i ne predstavlja pravni savet.";
    let odg;
    if (/bez izvora/i.test(p)) odg = { odgovor: "Nemam pouzdan odgovor na ovo pitanje u trenutnoj bazi zakona.\n\n---\n📊 Pouzdanost: NISKA | Score: 0.120" + NAPOMENA, confidence: "LOW", top_score: 0.12 };
    else if (/9999/.test(p)) odg = { odgovor: "Član 9999 (Zakon o obligacionim odnosima) nije pronađen u indeksu Vindex baze.", confidence: "LOW", top_score: 0.7 };
    else if (/pad korpusa/i.test(p)) odg = { odgovor: "Došlo je do greške prilikom obrade zahteva. Pokušajte ponovo.", retrieval_unavailable: true };
    else if (/delimi/i.test(p)) odg = { odgovor: "--- PRAVNI ZAKLJUČAK\nDelimičan odgovor." + NAPOMENA, confidence: "MEDIUM", confidence_detail: {}, izvori: [{ zakon: "zakon o radu", clan: "Član 179" }], izvori_neuspeh: ["dokumenti predmeta"] };
    else odg = { odgovor: "--- BRZA PROCENA\nŠteta se dokazuje **računima** i nalazom veštaka. <img src=x onerror=\"window.__xss=7\">\n--- PRAVNI ZAKLJUČAK\nPrimenjuje se ZOO." + NAPOMENA,
                 confidence: "HIGH", confidence_detail: { nivo: "HIGH" }, izvori: [{ zakon: "zakon o obligacionim odnosima", clan: "Član 154" }, { zakon: "zakon o obligacionim odnosima", clan: "200" }, { zakon: "", clan: "Član 1" }],
                 cinjenice_iz_dokumenta: ["Ugovor navodi rok isporuke 30 dana."] };
    json(res, 200, Object.assign({}, osnova, odg));
    return true;
  };
}

/* POST /api/praksa/search — javni korpus, ali samo uz prijavu; nevažeća oblast → 400.
 * kuke.odluke = niz odluka koje korpus vraća (filtrira se po query u izreci/broju). */
const OBLASTI_PRAKSE = ["Građanska", "Zaštita prava", "Upravna", "Krivična"];
export function praksaRuta(korisnici, kuke = {}) {
  return async (req, url, res) => {
    if (url.pathname !== "/api/praksa/search" || req.method !== "POST") return false;
    const sirovo = await citajTelo(req);
    const k = korisnik(req, korisnici);
    if (await kuka(kuke, url.pathname, k, req, res)) return true;
    if (!k) { json(res, 401, { detail: "Unauthorized" }); return true; }
    let b; try { b = JSON.parse(sirovo || "{}"); } catch { json(res, 400, {}); return true; }
    (kuke.upisano || (() => {}))(b);
    if (b.matter && !OBLASTI_PRAKSE.includes(b.matter)) { json(res, 400, { error: "Nevalidan matter filter" }); return true; }
    const q = String(b.query || "").toLowerCase();
    const sve = (kuke.odluke || []).filter(o => (!q || (o.izreka_preview + " " + o.decision_number).toLowerCase().includes(q)) && (!b.matter || o.matter === b.matter));
    json(res, 200, { decisions: sve.slice(b.offset || 0, (b.offset || 0) + (b.limit || 10)), total: sve.length, page: 1, limit: b.limit || 10 });
    return true;
  };
}

/* /interni-stavovi/dodaj|pretraga — namespace po korisniku iz tokena (kao interni_stavovi.py). */
export function stavoviRuta(korisnici, kuke = {}) {
  const ns = {};
  return async (req, url, res) => {
    if (!url.pathname.startsWith("/interni-stavovi/") || req.method !== "POST") return false;
    const sirovo = await citajTelo(req);
    const k = korisnik(req, korisnici);
    if (await kuka(kuke, url.pathname, k, req, res)) return true;
    if (!k) { json(res, 401, { detail: "Unauthorized" }); return true; }
    let b; try { b = JSON.parse(sirovo || "{}"); } catch { json(res, 400, {}); return true; }
    (kuke.upisano || (() => {}))(url.pathname, b);
    const prostor = (ns["interni_stavovi_" + k.id] = ns["interni_stavovi_" + k.id] || []);
    if (url.pathname === "/interni-stavovi/dodaj") {
      if (String(b.naslov || "").length < 3 || String(b.tekst || "").length < 30) { json(res, 422, { detail: [{ loc: ["body", "tekst"] }] }); return true; }
      prostor.push({ naslov: b.naslov, tekst: b.tekst });
      json(res, 200, { vektori: 1, naslov: b.naslov });
      return true;
    }
    if (url.pathname === "/interni-stavovi/pretraga") {
      if (kuke.stavoviPad) { json(res, 200, { rezultati: [], ukupno: 0, pretraga_neuspesna: true }); return true; }
      const q = String(b.upit || "").toLowerCase();
      const r = prostor.filter(s => (s.naslov + " " + s.tekst).toLowerCase().includes(q)).map(s => ({ naslov: s.naslov, tekst: s.tekst, score: 0.9 }));
      json(res, 200, { rezultati: r, ukupno: r.length, pretraga_neuspesna: false });
      return true;
    }
    json(res, 404, {});
    return true;
  };
}

/* ── Nacrti (routers/drafting.py) ─────────────────────────────────────────
 * GET /api/podnesak/types, GET /api/courts (javni katalozi);
 * POST /api/podnesak: tip van spiska → 422; tuđ predmet → 404; opis „kritika pala" →
 *   critique_applied:false; „keš" → null; „izmišljen" → placeholder u tekstu.
 * POST /api/nacrti/export/docx → .docx; staging lista/odobri/odbij po korisniku. */
const TIPOVI_PODNESAKA = [{ tip: "tuzba_naknada_stete", naziv: "Tužba za naknadu štete" }, { tip: "zalba_parnicna", naziv: "Žalba (parnični postupak)" }];
export function nacrtRuta(korisnici, kuke = {}) {
  let n = 0;
  return async (req, url, res) => {
    const p = url.pathname;
    if (p === "/api/podnesak/types" && req.method === "GET") {
      if (await kuka(kuke, p, null, req, res)) return true;
      json(res, 200, { tipovi: TIPOVI_PODNESAKA }); return true;
    }
    if (p === "/api/courts" && req.method === "GET") {
      if (await kuka(kuke, p, null, req, res)) return true;
      json(res, 200, { sudovi: { "Osnovni sudovi": [{ naziv: "Osnovni sud u Beogradu", adresa: "Ustanička 29, 11000 Beograd", grad: "Beograd" }], "Viši sudovi": [{ naziv: "Viši sud u Beogradu", adresa: "Savska 17a", grad: "Beograd" }] } });
      return true;
    }
    const jeNacrt = p === "/api/podnesak" || p === "/api/nacrti/export/docx" || p.startsWith("/api/staging/");
    if (!jeNacrt) return false;
    const sirovo = req.method === "POST" ? await citajTelo(req) : "";
    const k = korisnik(req, korisnici);
    if (await kuka(kuke, p, k, req, res)) return true;
    if (!k) { json(res, 401, { detail: "Unauthorized" }); return true; }
    let b = {}; try { b = JSON.parse(sirovo || "{}"); } catch { json(res, 400, {}); return true; }
    k.staging = k.staging || [];
    if (p === "/api/podnesak" && req.method === "POST") {
      (kuke.upisano || (() => {}))(p, b);
      if (!TIPOVI_PODNESAKA.some(t => t.tip === b.tip) || String(b.opis || "").length < 20) { json(res, 422, { detail: [{ loc: ["body", "tip"] }] }); return true; }
      if (b.predmet_id && !k.predmeti.some(x => x.id === b.predmet_id && x.user_id === k.id)) { json(res, 404, { detail: "Predmet nije pronađen." }); return true; }
      const naziv = TIPOVI_PODNESAKA.find(t => t.tip === b.tip).naziv;
      let tekst = `${(b.sud_naziv || "OSNOVNI SUD").toUpperCase()}\n${b.sud_adresa || ""}\n\n${naziv.toUpperCase()}\n\nTužilac traži naknadu štete prema čl. 154 ZOO.\n<script>window.__xss=11</script>\n\nNAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan od strane ovlašćenog advokata pre podnošenja sudu.`;
      if (/izmišljen/.test(b.opis)) tekst = tekst.replace("čl. 154 ZOO", "[proveriti relevantan član] i [proveriti relevantan član]");
      const critique = /kritika pala/.test(b.opis) ? false : /keš/.test(b.opis) ? null : true;
      if (b.predmet_id) k.staging.unshift({ id: `st-${k.id}-${++n}`, predmet_id: b.predmet_id, naziv, tip: b.tip, status: "pending", created_at: new Date().toISOString() });
      json(res, 200, { status: "success", odgovor: tekst, tip: b.tip, naziv, critique_applied: critique, ai_generated: true });
      return true;
    }
    if (p === "/api/nacrti/export/docx" && req.method === "POST") {
      (kuke.upisano || (() => {}))(p, b);
      res.writeHead(200, { "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Content-Disposition": 'attachment; filename="Tuzba_za_naknadu_stete.docx"' });
      res.end(Buffer.from("PK fake docx " + String(b.tekst || "").slice(0, 50)));
      return true;
    }
    const ms = /^\/api\/staging\/predmet\/([^/]+)$/.exec(p);
    if (ms && req.method === "GET") { json(res, 200, { stavke: k.staging.filter(s => s.predmet_id === decodeURIComponent(ms[1])) }); return true; }
    const ma = /^\/api\/staging\/([^/]+)\/(approve|reject)$/.exec(p);
    if (ma && req.method === "POST") {
      const s = k.staging.find(x => x.id === decodeURIComponent(ma[1]));
      if (!s) { json(res, 404, { detail: "Nacrt na čekanju nije pronađen." }); return true; }
      s.status = ma[2] === "approve" ? "approved" : "rejected";
      json(res, 200, { status: s.status, indexed: false, poruka: "confidence_score (0.4) je ispod praga 0.85" });
      return true;
    }
    json(res, 404, {}); return true;
  };
}

/* ── Kancelarija: /api/kancelarija/moja, /portfolio/dashboard, /api/firm/health-index ──
 * k.kancelarija = odgovor za /moja tog korisnika (ili {status:"no_firma"}); portfolio i
 * indeks se računaju nad k.predmeti (samo vlasnik). kuke.pre(put) za greške. */
export function kancelarijaRuta(korisnici, kuke = {}) {
  return async (req, url, res) => {
    const p = url.pathname;
    if (!["/api/kancelarija/moja", "/portfolio/dashboard", "/api/firm/health-index"].includes(p) || req.method !== "GET") return false;
    const k = korisnik(req, korisnici);
    if (await kuka(kuke, p, k, req, res)) return true;
    if (!k) { json(res, 401, { detail: "Unauthorized" }); return true; }
    (kuke.upisano || (() => {}))(p);
    if (p === "/api/kancelarija/moja") { json(res, 200, k.kancelarija || { status: "no_firma" }); return true; }
    const moji = k.predmeti.filter(x => x.user_id === k.id);
    if (p === "/portfolio/dashboard") {
      json(res, 200, { ukupno_predmeta: moji.length, ukupno_aktivnih: moji.filter(x => x.status === "aktivan").length, po_statusu: {}, po_tipu: {},
        rokovi_7_dana: k.rokovi || [], rokovi_14_dana: k.rokovi || [], hitni_rokovi: (k.rokovi || []).filter(r => r.vaznost === "kritičan"),
        neaktivni_30_dana: moji.slice(0, 1).map(x => ({ predmet_id: x.id, naziv: x.naziv, poslednja_izmena: "2026-08-01" })),
        summary: "⚠ 1 HITNIH rokova odmah!" });
      return true;
    }
    json(res, 200, { score: 72, grade: "B+", color: "#fbbf24", components: [{ label: "Rokovi i ročišta", score: 15, max: 20 }, { label: "Naplata", score: 12, max: 20 }],
      n_aktivni: moji.length, n_zatvoreni: 0, chief_partner: "AI DIREKTIVA PARTNERA", weak_signals: ["SLAB SIGNAL"], inst_risks: [], iz_kesa: false });
    return true;
  };
}

/* ── Naplata: /billing/* (routers/billing.py) ──
 * k.stavke / k.fakture / k.tajmer po korisniku. Predmet mora biti pozivaočev (404);
 * uz tarifu bez iznosa iznos računa „server" (bodovi × 50); uz same sate satnica 6000;
 * bez osnova 422; nepoznata tarifa 400; stavka na fakturi → 409; stavke drugog predmeta → 400.
 * kuke.pre(putanja + ":" + metod) za greške/prekid; kuke.upisano(putanja, telo). */
export const TARIFA = [
  { sifra: "T01", naziv: "Tužba za novčano potraživanje (prostija)", bodovi: 12, iznos_rsd: 600, is_custom: false },
  { sifra: "T02", naziv: "Odgovor na tužbu <b>složeniji</b>", bodovi: 20, iznos_rsd: 1000, is_custom: false },
];
export function naplataRuta(korisnici, kuke = {}) {
  let n = 0;
  return async (req, url, res) => {
    const p = url.pathname;
    if (!p.startsWith("/billing/")) return false;
    const sirovo = req.method === "POST" ? await citajTelo(req) : "";
    const k = korisnik(req, korisnici);
    if (await kuka(kuke, p + ":" + req.method, k, req, res)) return true;
    if (!k) { json(res, 401, { detail: "Unauthorized" }); return true; }
    let b = {}; try { b = JSON.parse(sirovo || "{}"); } catch { json(res, 400, {}); return true; }
    k.stavke = k.stavke || []; k.fakture = k.fakture || [];
    const moj = (id) => k.predmeti.some(x => x.id === id && x.user_id === k.id);
    if (req.method === "POST") (kuke.upisano || (() => {}))(p, b);
    if (p === "/billing/tarifa" && req.method === "GET") { json(res, 200, { tarifa: TARIFA, bod_rsd: 50 }); return true; }
    if (p === "/billing/entries" && req.method === "GET") {
      const pid = url.searchParams.get("predmet_id");
      const e = k.stavke.filter(x => x.predmet_id === pid && x.user_id === k.id);
      const uk = e.reduce((s, x) => s + x.iznos_rsd, 0), ob = e.filter(x => x.obracunato).reduce((s, x) => s + x.iznos_rsd, 0);
      json(res, 200, { entries: e, ukupno_rsd: uk, obracunato_rsd: ob, neobracunato_rsd: uk - ob, ukupno_h: e.reduce((s, x) => s + (x.sati || 0), 0) });
      return true;
    }
    if (p === "/billing/entries" && req.method === "POST") {
      if (!moj(b.predmet_id)) { json(res, 404, { detail: "Predmet nije pronađen." }); return true; }
      let iznos = b.iznos_rsd ?? null, t = null;
      if (b.tarifa_sifra) { t = TARIFA.find(x => x.sifra === String(b.tarifa_sifra).toUpperCase()); if (!t) { json(res, 400, { detail: "Nepoznata tarifa sifra." }); return true; } if (iznos === null) iznos = t.bodovi * 50; }
      if (iznos === null && b.sati) iznos = Math.ceil(b.sati * 6000);
      if (iznos === null) { json(res, 422, { detail: "iznos_rsd je obavezan kad tarifa_sifra nije navedena." }); return true; }
      const e = { id: `e-${k.id}-${++n}`, user_id: k.id, predmet_id: b.predmet_id, opis: b.opis, tip: b.tip, tarifa_sifra: t ? t.sifra : null, sati: b.sati ?? null, iznos_rsd: iznos, datum: b.datum || "2026-10-09", obracunato: false };
      k.stavke.unshift(e);
      json(res, 200, { success: true, entry: e }); return true;
    }
    if (p === "/billing/timer/aktivan" && req.method === "GET") { json(res, 200, k.tajmer ? { aktivan: true, timer: k.tajmer } : { aktivan: false, timer: null }); return true; }
    if (p === "/billing/timer/start" && req.method === "POST") {
      if (!moj(b.predmet_id)) { json(res, 404, { detail: "Predmet nije pronađen." }); return true; }
      if (k.tajmer) { json(res, 409, { detail: "Tajmer je već aktivan." }); return true; }
      k.tajmer = { id: `tm-${++n}`, user_id: k.id, predmet_id: b.predmet_id, opis: b.opis || null, start_at: "2026-10-09T08:30:00+00:00", aktivan: true };
      json(res, 200, { success: true, timer: k.tajmer }); return true;
    }
    if (p === "/billing/timer/stop" && req.method === "POST") {
      if (!k.tajmer) { json(res, 404, { detail: "Nema aktivnog tajmera." }); return true; }
      const t = k.tajmer; k.tajmer = null;
      const e = b.kreiraj_entry ? { id: `e-${k.id}-${++n}`, user_id: k.id, predmet_id: t.predmet_id, opis: t.opis || "Rad po predmetu (tajmer)", tip: "satnica", sati: 1.5, iznos_rsd: 9000, datum: "2026-10-09", obracunato: false } : null;
      if (e) k.stavke.unshift(e);
      json(res, 200, { success: true, trajanje_s: 5400, trajanje_h: 1.5, entry: e }); return true;
    }
    if (p === "/billing/faktura" && req.method === "GET") { json(res, 200, { fakture: k.fakture.filter(f => f.user_id === k.id).concat(kuke.dodatneFakture || []), ukupno: k.fakture.length }); return true; }
    if (p === "/billing/faktura" && req.method === "POST") {
      const e = k.stavke.filter(x => x.user_id === k.id && (b.entry_ids || []).includes(x.id));
      if (!e.length) { json(res, 404, { detail: "Radnje nisu pronađene." }); return true; }
      if (e.some(x => x.predmet_id !== b.predmet_id)) { json(res, 400, { detail: "Neke od odabranih radnji ne pripadaju navedenom predmetu." }); return true; }
      if (e.some(x => x.obracunato)) { json(res, 409, { detail: "radnje su već na drugoj fakturi." }); return true; }
      const osn = e.reduce((s, x) => s + x.iznos_rsd, 0), pdv = Math.round(osn * (b.pdv_stopa || 0)) / 100;
      const f = { id: `f-${++n}`, user_id: k.id, predmet_id: b.predmet_id, broj_fakture: `2026/${String(k.fakture.length + 1).padStart(4, "0")}`, klijent_naziv: b.klijent_naziv, iznos_bez_pdv: osn, pdv_iznos: pdv, iznos_sa_pdv: osn + pdv, status: "nacrt", is_proforma: false, datum_dospeca: "2026-11-08" };
      k.fakture.unshift(f); e.forEach(x => { x.obracunato = true; x.faktura_id = f.id; });
      json(res, 200, { success: true, faktura: f, stavke: e.length }); return true;
    }
    json(res, 404, {}); return true;
  };
}

/* ── Rokovi i kalendar: /api/rokovi/kandidati, /api/rokovi/{id}/potvrdi|odbij, /api/kalendar/pregled ──
 * k.rokovi = redovi hronologije {id, predmet_id, dogadjaj, datum_iso, vrsta?, izvor, odluka?};
 * k.dogadjaji = odgovor kalendara (ročišta). Tuđ rok → 404 bez promene. Odluka menja samo `odluka`
 * (red se NE briše). kuke.pre(putanja + ":" + metod); kuke.kalendar(telo) menja odgovor kalendara. */
export function rokoviRuta(korisnici, kuke = {}) {
  return async (req, url, res) => {
    const p = url.pathname;
    const jeOdluka = /^\/api\/rokovi\/[^/]+\/(potvrdi|odbij)$/.test(p);
    if (!(p === "/api/rokovi/kandidati" || p === "/api/kalendar/pregled" || jeOdluka)) return false;
    const sirovo = req.method === "POST" ? await citajTelo(req) : "";
    const k = korisnik(req, korisnici);
    if (await kuka(kuke, (jeOdluka ? "/api/rokovi/odluka" : p) + ":" + req.method, k, req, res)) return true;
    if (!k) { json(res, 401, { detail: "Unauthorized" }); return true; }
    k.rokovi = k.rokovi || [];
    if (p === "/api/rokovi/kandidati" && req.method === "GET") {
      const od = url.searchParams.get("od") || "";
      const r = k.rokovi.filter(x => x.datum_iso >= od).map(x => ({ id: x.id, predmet_id: x.predmet_id, dogadjaj: x.dogadjaj, datum_iso: x.datum_iso, izvor: x.izvor || "ai",
        ...(x.vrsta ? { vrsta: x.vrsta } : {}), ...(x.stanje ? { stanje: x.stanje } : {}), stanje_odluke: x.odluka || "UNCONFIRMED" }));
      json(res, 200, { rokovi: r, ukupno: r.length, odseceno: !!kuke.odseceno }); return true;
    }
    if (p === "/api/kalendar/pregled" && req.method === "GET") {
      let t = { dogadjaji: k.dogadjaji || [], degraded_sources: [], truncated: false };
      if (kuke.kalendar) t = kuke.kalendar(t);
      json(res, 200, t); return true;
    }
    (kuke.upisano || (() => {}))(p, JSON.parse(sirovo || "{}"));
    const m = /^\/api\/rokovi\/([^/]+)\/(potvrdi|odbij)$/.exec(p);
    const r = k.rokovi.find(x => x.id === decodeURIComponent(m[1]));
    if (!r) { json(res, 404, { detail: "Rok nije pronađen." }); return true; }
    r.odluka = m[2] === "potvrdi" ? "CONFIRMED" : "REJECTED";
    json(res, 200, { ok: true, rok_id: r.id, stanje_odluke: r.odluka, dogadjaj: r.dogadjaj, datum_iso: r.datum_iso }); return true;
  };
}

/* ── Smart Intake: /api/smart-intake/* (routers/smart_intake.py) ──
 * Multipart `files`; isti sadržaj istog korisnika = isti posao (`already_submitted`); tuđ posao → 404.
 * k.poslovi[id] = {id, ime, status, attempts, predmet_id, dokument, entiteti, provera}. Test pomera stanje
 * preko kuke.napreduj(posao, brojCitanja) koja se poziva pri svakom GET-u. kuke.pre(put + ":" + metod).
 * Finalize: samo sopstven predmet; pre razrešenog pregleda 409; NE menja polja predmeta. */
import { createHash } from "node:crypto";
function delovi(sirovo, tip) {
  const m = /boundary=(?:"([^"]+)"|([^;]+))/i.exec(tip || "");
  if (!m) return [];
  const granica = "--" + (m[1] || m[2]);
  return sirovo.split(granica).slice(1, -1).map(d => {
    const kraj = d.indexOf("\r\n\r\n");
    const zaglavlje = d.slice(0, kraj), sadrzaj = d.slice(kraj + 4, d.length - 2);
    const f = /filename="([^"]*)"/.exec(zaglavlje), n = /name="([^"]*)"/.exec(zaglavlje);
    // Telo je pročitano kao latin1 (bajt = znak, za heš sadržaja); ime fajla je UTF-8 kao kod pravog servera.
    return { polje: n ? n[1] : "", ime: f ? Buffer.from(f[1], "latin1").toString("utf8") : null, sadrzaj };
  }).filter(x => x.polje === "files" && x.ime !== null);
}
export function prijemRuta(korisnici, kuke = {}) {
  return async (req, url, res) => {
    const p = url.pathname;
    if (!p.startsWith("/api/smart-intake/")) return false;
    const sirovo = req.method === "POST" ? await new Promise(r => { const d = []; req.on("data", c => d.push(c)); req.on("end", () => r(Buffer.concat(d).toString("latin1"))); }) : "";
    const k = korisnik(req, korisnici);
    const kljucKuke = p.replace(/[0-9a-f-]{36}|ent-[\w-]+/g, "{id}") + ":" + req.method;
    if (await kuka(kuke, kljucKuke, k, req, res)) return true;
    if (!k) { json(res, 401, { detail: "Unauthorized" }); return true; }
    k.poslovi = k.poslovi || {};
    if (p === "/api/smart-intake/documents" && req.method === "POST") {
      const fajlovi = delovi(sirovo, req.headers["content-type"]);
      (kuke.upisano || (() => {}))(p, { fajlova: fajlovi.length, imena: fajlovi.map(f => f.ime), kljuc: req.headers["idempotency-key"] || null });
      const rezultati = fajlovi.map(f => {
        if (!/\.(pdf|docx|txt|jpe?g|png)$/i.test(f.ime)) return { filename: f.ime, ok: false, greska: "Nepodržan format fajla. Podržano: PDF, DOCX, TXT, JPG, PNG." };
        const h = k.id + ":" + createHash("sha256").update(f.sadrzaj, "latin1").digest("hex");
        const postojeci = Object.values(k.poslovi).find(x => x.kljuc === h);
        if (postojeci) return { filename: f.ime, ok: true, job_id: postojeci.id, already_submitted: true };
        const id = (kuke.idPosla || (() => crypto.randomUUID()))();
        k.poslovi[id] = { id, ime: f.ime, kljuc: h, status: "received", attempts: 0, predmet_id: null, citanja: 0, dokument: null, entiteti: [], provera: null };
        return { filename: f.ime, ok: true, job_id: id };
      });
      json(res, 202, { rezultati, ukupno: fajlovi.length, nastavlja: false, preostali_fajlovi: [] }); return true;
    }
    const mj = /^\/api\/smart-intake\/jobs\/([^/]+)(\/finalize|\/review\/resolve|\/review\/reject)?$/.exec(p);
    if (mj) {
      const posao = k.poslovi[decodeURIComponent(mj[1])];
      if (!posao) { json(res, 404, { detail: "Posao nije pronađen." }); return true; }
      const radnja = mj[2] || "";
      if (!radnja && req.method === "GET") {
        posao.citanja++;
        if (kuke.napreduj) kuke.napreduj(posao, posao.citanja);
        json(res, 200, { job: { id: posao.id, status: posao.status, attempts: posao.attempts, last_error: null, original_filename: posao.ime, predmet_id: posao.predmet_id },
          dokument: posao.dokument, entiteti: posao.entiteti, potrebna_provera: posao.provera, dokumenti: [] });
        return true;
      }
      const telo = JSON.parse(Buffer.from(sirovo || "{}", "latin1").toString("utf8"));
      (kuke.upisano || (() => {}))(p, telo);
      if (radnja === "/review/resolve") { if (posao.status === "awaiting_review") posao.status = "completed"; posao.provera = null; json(res, 200, { ok: true, already_finalized: false, review_resolved_now: true, job_status_advanced: true }); return true; }
      if (radnja === "/review/reject") { posao.status = "failed"; posao.provera = null; json(res, 200, { ok: true, review_resolved_now: true, job_status_rejected: true }); return true; }
      if (radnja === "/finalize") {
        if (posao.predmet_id) { json(res, 200, { ok: true, predmet_id: posao.predmet_id, already_finalized: true, dokumenata_povezano: 1 }); return true; }
        if (posao.status === "awaiting_review") { json(res, 409, { detail: "Posao čeka proveru." }); return true; }
        if (!k.predmeti.some(x => x.id === telo.predmet_id && x.user_id === k.id)) { json(res, 404, { detail: "Predmet za prikačivanje nije pronađen." }); return true; }
        posao.predmet_id = telo.predmet_id;
        k.prikaceno = (k.prikaceno || []).concat([{ predmet_id: telo.predmet_id, ime: posao.ime }]);
        json(res, 200, Object.assign({ ok: true, predmet_id: telo.predmet_id, coi_status: "COI_NOT_APPLICABLE", klijent_dodat: false, rok_dodat: false,
          rok_preskocen_razlog: null, dokumenata_ukupno: 1, dokumenata_povezano: 1 }, kuke.finalize || {}));
        return true;
      }
    }
    const me = /^\/api\/smart-intake\/entities\/([^/]+)\/correct$/.exec(p);
    if (me && req.method === "POST") {
      const telo = JSON.parse(Buffer.from(sirovo || "{}", "latin1").toString("utf8"));
      (kuke.upisano || (() => {}))(p, telo);
      const e = Object.values(k.poslovi).flatMap(x => x.entiteti).find(x => x.entity_id === decodeURIComponent(me[1]));
      if (!e) { json(res, 404, { detail: "Stavka nije pronađena." }); return true; }
      e.value = telo.corrected_value; e.corrected = true; e.needs_review = false;
      json(res, 200, { entity_id: e.entity_id, entity_type: e.entity_type, corrected_value: telo.corrected_value }); return true;
    }
    json(res, 404, {}); return true;
  };
}
