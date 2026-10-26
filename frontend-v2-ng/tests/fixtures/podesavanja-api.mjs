// Mock UGOVORA backend ruta koje koriste V2 Podešavanja (Settings Master Sprint P1).
// Svaki odgovor je napisan ovde; oblik i pravila prate stvarne rute (file:line u komentarima,
// main c4a698ae + ispravke ovog sprinta). Vlasnik se određuje ISKLJUČIVO iz tokena.
//
//   GET  /api/me                          api.py:3481        {user_id, email, ...}
//   GET  /api/plan/status                 routers/plans.py:77
//   GET/POST/DELETE /email-notif/profil, POST /email-notif/test   routers/email_notif.py
//   GET  /api/kancelarija/moja + admin rute (naziv, pozovi, uloga, suspenduj, reaktiviraj, ukloni)  routers/kancelarija.py
//   GET/PUT /api/tarife/moja-satnica      routers/tarife.py:107/127
//   GET/POST /api/sef/podesavanja         routers/sef.py:224/264
//   GET  /api/export/complete             routers/data_export.py:125 (ZIP)
//   DELETE /api/gdpr/account              routers/gdpr.py:202 (anonimizacija; ovde samo brojač, nikad stvarno brisanje)
import { json } from "./api-fixture.mjs";

export const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
export const KORISNICI = {
  A: { token: "PN-token-A", id: "korisnik-A", email: "pn-a@example.test" },      // samostalan advokat
  B: { token: "PN-token-B", id: "korisnik-B", email: "pn-b@example.test" },      // administrator kancelarije
  C: { token: "PN-token-C", id: "korisnik-C", email: "pn-c@example.test" },      // član (saradnik)
};
export const sesija = (k) => JSON.stringify({ access_token: k.token, expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: k.id } });

const ULOGE = ["admin", "partner", "saradnik", "citanje"];
const ULOGA_LABELS = { admin: "Administrator", partner: "Partner", saradnik: "Saradnik", citanje: "Samo čitanje" };

export function podesavanjaMock() {
  return {
    zahtevi: [],
    kasnjenje: 0,                 // ms pre svakog odgovora (spor server)
    pada: {},                     // { "METOD putanja": status } — prinudna greška
    profilEmail: {},              // token → red korisnik_email_notif
    satnica: {},                  // token → broj
    sef: {},                      // token → {seller_pib, seller_naziv, seller_adresa, seller_mesto, api_key}
    plan: {
      [KORISNICI.A.token]: { plan: "solo", plan_display: "Solo", subscription_expires_at: "2027-01-31T00:00:00+00:00", credits_remaining: 87,
        usage_this_month: [{ feature_key: "ai_pitanje", naziv: "AI pravno pitanje", broj_koriscenja: 13, krediti_potroseni: 13, dnevni_limit: 50, mesecni_limit: 300 }] },
      [KORISNICI.B.token]: { plan: "kancelarija", plan_display: "Kancelarija", subscription_expires_at: null, credits_remaining: 400, usage_this_month: [] },
      [KORISNICI.C.token]: { plan: "free", plan_display: "Free", subscription_expires_at: null, credits_remaining: 3, usage_this_month: [] },
    },
    firma: { id: "firma-1", naziv: "Advokatska kancelarija Test", admin_uid: KORISNICI.B.id, created_at: "2026-09-01T10:00:00+00:00" },
    clanovi: [
      { id: "clan-c", email: KORISNICI.C.email, uloga: "saradnik", status: "ACTIVE", user_id: KORISNICI.C.id, joined_at: "2026-09-02T10:00:00+00:00", suspended_at: null },
      { id: "clan-d", email: "pozvan@example.test", uloga: "partner", status: "INVITED", user_id: null, joined_at: null, suspended_at: null },
      { id: "clan-e", email: "suspendovan@example.test", uloga: "citanje", status: "SUSPENDED", user_id: "korisnik-E", joined_at: "2026-09-03T10:00:00+00:00", suspended_at: "2026-10-01T10:00:00+00:00" },
    ],
    poslatiEmailovi: 0,
    anonimizovani: [],            // id-jevi naloga nad kojima je mock izvršio DELETE /api/gdpr/account
  };
}

function korisnik(req) {
  const a = req.headers.authorization || "";
  return Object.values(KORISNICI).find(k => "Bearer " + k.token === a) || null;
}

async function telo(req) {
  const delovi = [];
  for await (const c of req) delovi.push(c);
  const t = Buffer.concat(delovi).toString("utf8");
  if (!t) return { sirovo: "", podaci: null };
  try { return { sirovo: t, podaci: JSON.parse(t) }; } catch { return { sirovo: t, podaci: undefined }; }
}

const ZABRANJENA = ["user_id", "owner_id", "tenant_id", "uid", "vlasnik_id"];

export function podesavanjaRuta(s) {
  return async (req, url, res) => {
    const p = url.pathname, m = req.method;
    const nase = p === "/api/me" || p === "/api/plan/status" || p.startsWith("/email-notif/") || p.startsWith("/api/kancelarija/")
      || p === "/api/tarife/moja-satnica" || p === "/api/sef/podesavanja" || p === "/api/export/complete" || p === "/api/gdpr/account";
    if (!nase) return false;
    const k = korisnik(req);
    const b = await telo(req);
    s.zahtevi.push({ metod: m, putanja: p, token: k ? k.token : null, telo: b.sirovo, idem: req.headers["idempotency-key"] || null });
    if (s.kasnjenje) await new Promise(r => setTimeout(r, s.kasnjenje));
    if (res.destroyed) return true;
    const prinudno = s.pada[m + " " + p];
    if (prinudno) { json(res, prinudno, { detail: "fixture greška" }); return true; }
    if (!k) { json(res, 401, { detail: "Unauthorized" }); return true; }
    if (b.podaci && typeof b.podaci === "object" && ZABRANJENA.some(z => z in b.podaci)) { json(res, 422, { detail: [{ loc: ["body", "user_id"] }] }); return true; }
    const t = k.token;

    if (p === "/api/me" && m === "GET") { json(res, 200, { user_id: k.id, email: k.email, credits_remaining: 0, is_pro: false, is_founder: false }); return true; }
    if (p === "/api/plan/status" && m === "GET") {
      const x = s.plan[t];
      json(res, 200, { addons: [], v2_pristup: true, subscription_seats_extra: 0, year_month: "2026-10", ...x });
      return true;
    }

    // ── B10 email ──
    if (p === "/email-notif/profil" && m === "GET") {
      const r = s.profilEmail[t];
      json(res, 200, r ? { ...r, email: k.email, smtp_ok: true } : { aktivan: false, dan_7: true, dan_3: true, dan_1: true, email: k.email, smtp_ok: true });
      return true;
    }
    if (p === "/email-notif/profil" && m === "POST") { s.profilEmail[t] = { user_id: k.id, ...b.podaci }; json(res, 200, { ok: true, aktivan: b.podaci.aktivan }); return true; }
    if (p === "/email-notif/profil" && m === "DELETE") { delete s.profilEmail[t]; json(res, 200, { ok: true }); return true; }
    if (p === "/email-notif/test" && m === "POST") {
      const n = b.podaci && b.podaci.interval !== undefined ? b.podaci.interval : null;
      if (n !== null && ![1, 3, 7].includes(n)) { json(res, 422, { detail: "interval" }); return true; }
      const r = s.profilEmail[t];
      if (n !== null && !(r && r.aktivan && r["dan_" + n])) { json(res, 409, { detail: "nije uključen" }); return true; }
      s.poslatiEmailovi++;
      json(res, 200, { ok: true, poslato_na: k.email, interval: n });
      return true;
    }

    // ── Kancelarija ──
    const jeAdmin = s.firma && s.firma.admin_uid === k.id;
    const clanReda = s.clanovi.find(c => c.user_id === k.id && c.status === "ACTIVE");
    const vidljivi = () => s.clanovi.filter(c => c.status !== "REMOVED").map(c => ({ id: c.id, email: c.email, uloga: c.uloga,
      uloga_label: ULOGA_LABELS[c.uloga] || c.uloga, status: c.status, joined_at: c.joined_at, suspended_at: c.suspended_at }));
    if (p === "/api/kancelarija/moja" && m === "GET") {
      if (!jeAdmin && !clanReda) { json(res, 200, { status: "no_firma" }); return true; }
      json(res, 200, { status: "aktivan", moja_uloga: jeAdmin ? "admin" : clanReda.uloga, firma: { ...s.firma }, clanovi: vidljivi() });
      return true;
    }
    if (p.startsWith("/api/kancelarija/")) {
      if (!jeAdmin) { json(res, 403, { detail: "Niste administrator nijedne firme." }); return true; }
      const mm = /^\/api\/kancelarija\/(naziv|pozovi|uloga|suspenduj|reaktiviraj|ukloni)(?:\/([^/]+))?$/.exec(p);
      if (!mm) { json(res, 404, { detail: "Not Found" }); return true; }
      const [, radnja, id] = mm;
      const c = id ? s.clanovi.find(x => x.id === id) : null;
      if (radnja === "naziv" && m === "PUT") {
        const n = String((b.podaci || {}).naziv || "").trim();
        if (n.length < 2 || n.length > 120) { json(res, 422, { detail: [{ loc: ["body", "naziv"] }] }); return true; }
        s.firma.naziv = n; json(res, 200, { ok: true, naziv: n }); return true;
      }
      if (radnja === "pozovi" && m === "POST") {
        const e = String((b.podaci || {}).email || "").trim().toLowerCase(), u = (b.podaci || {}).uloga || "saradnik";
        if (!e || e.length > 255 || !ULOGE.includes(u) || u === "admin") { json(res, 422, { detail: [{ loc: ["body", "uloga"] }] }); return true; }
        if (s.clanovi.some(x => x.email === e && x.status !== "REMOVED")) { json(res, 409, { detail: "već član" }); return true; }
        s.clanovi.push({ id: "clan-" + (s.clanovi.length + 1) + "-n", email: e, uloga: u, status: "INVITED", user_id: null, joined_at: null, suspended_at: null });
        json(res, 201, { ok: true, action: "invited", email: e, uloga: u }); return true;
      }
      if (!c || c.status === "REMOVED" && radnja !== "ukloni") { json(res, 404, { detail: "Član nije pronađen u vašoj firmi." }); return true; }
      if (radnja === "uloga" && m === "PUT") {
        const u = (b.podaci || {}).uloga;
        if (!ULOGE.includes(u) || u === "admin") { json(res, 422, { detail: [{ loc: ["body", "uloga"] }] }); return true; }
        c.uloga = u; json(res, 200, { ok: true, uloga: u }); return true;
      }
      if (radnja === "suspenduj" && m === "POST") {
        if (c.status !== "ACTIVE") { json(res, 400, { detail: "Član nije aktivan" }); return true; }
        c.status = "SUSPENDED"; c.suspended_at = "2026-10-26T10:00:00+00:00"; json(res, 200, { ok: true }); return true;
      }
      if (radnja === "reaktiviraj" && m === "POST") {
        if (c.status !== "SUSPENDED") { json(res, 400, { detail: "Član nije suspendovan" }); return true; }
        c.status = "ACTIVE"; c.suspended_at = null; json(res, 200, { ok: true }); return true;
      }
      if (radnja === "ukloni" && m === "DELETE") {
        if (c.user_id === k.id) { json(res, 400, { detail: "Ne možete ukloniti sebe." }); return true; }
        if (c.status === "REMOVED") { json(res, 400, { detail: "Član je već uklonjen." }); return true; }
        c.status = "REMOVED"; json(res, 200, { ok: true }); return true;
      }
      json(res, 405, { detail: "Method Not Allowed" }); return true;
    }

    // ── Satnica ──
    if (p === "/api/tarife/moja-satnica" && m === "GET") {
      json(res, 200, t in s.satnica ? { tarifa_po_satu: s.satnica[t], source: "custom", updated_at: "2026-10-26T10:00:00+00:00" } : { tarifa_po_satu: 7500.0, source: "default" });
      return true;
    }
    if (p === "/api/tarife/moja-satnica" && m === "PUT") {
      const v = (b.podaci || {}).tarifa_po_satu;
      if (typeof v !== "number" || !(v > 0) || v > 1000000) { json(res, 422, { detail: [{ loc: ["body", "tarifa_po_satu"] }] }); return true; }
      s.satnica[t] = v; json(res, 200, { ok: true, tarifa_po_satu: v }); return true;
    }

    // ── SEF ──
    if (p === "/api/sef/podesavanja" && m === "GET") {
      const r = s.sef[t];
      json(res, 200, r ? { konfigurisano: true, podaci: { seller_pib: r.seller_pib, seller_naziv: r.seller_naziv, seller_adresa: r.seller_adresa,
        seller_mesto: r.seller_mesto, api_key_preview: "***" + r.api_key.slice(-4), updated_at: "2026-10-26T10:00:00+00:00" } } : { konfigurisano: false, podaci: null });
      return true;
    }
    if (p === "/api/sef/podesavanja" && m === "POST") {
      const x = b.podaci || {};
      if (!/^\d{9}$/.test(String(x.seller_pib || "")) || !String(x.seller_naziv || "").trim()) { json(res, 422, { detail: [{ loc: ["body", "seller_pib"] }] }); return true; }
      const stari = s.sef[t];
      if (!x.api_key && !stari) { json(res, 422, { detail: "SEF API ključ je obavezan pri prvom čuvanju podešavanja." }); return true; }
      s.sef[t] = { seller_pib: x.seller_pib, seller_naziv: x.seller_naziv, seller_adresa: x.seller_adresa || "", seller_mesto: x.seller_mesto || "", api_key: x.api_key || stari.api_key };
      json(res, 200, { ok: true }); return true;
    }

    // ── Izvoz ──
    if (p === "/api/export/complete" && m === "GET") {
      res.writeHead(200, { "Content-Type": "application/zip", "Content-Disposition": 'attachment; filename="vindex-export-2026-10-26T10-00-00.zip"', "Cache-Control": "no-store" });
      res.end(Buffer.from("PK\u0003\u0004fixture-" + k.id));
      return true;
    }
    // ── Brisanje (anonimizacija) naloga — routers/gdpr.py:202 ──
    if (p === "/api/gdpr/account" && m === "DELETE") {
      s.anonimizovani.push(k.id);
      json(res, 200, { ok: true, poruka: "Vaš korisnički nalog je anonimizovan — email i ime uklonjeni su iz profila.",
        napomena: "Predmeti, klijenti i dokumenti nisu anonimizovani ovim postupkom i zadržavaju se u skladu sa zakonskom obavezom advokata da čuva spise predmeta (Zakon o advokaturi)." });
      return true;
    }
    json(res, 405, { detail: "Method Not Allowed" });
    return true;
  };
}
