// Emulacija postojećeg `GET /api/predmeti` (api.py `lista_predmeta`, main 5fd4db65)
// za LIVE testove. Ponavlja UGOVOR, ne implementaciju:
//
//   • korisnik iz `Authorization: Bearer <token>` (inače 401), filtriranje po
//     vlasniku radi SERVER — parametar `user_id` se ignoriše kao i u api.py;
//   • limit = min(max(limit, 1), 500), podrazumevano 200; offset = max(offset, 0);
//   • `status` = jednakost; `q` = ilike nad SAMO `naziv` (bez % i _);
//   • redosled `created_at desc, id desc`;
//   • `ukupno` = count="exact" SVIH redova koji odgovaraju filteru, UKLJUČUJUĆI
//     predmete u brisanju; oni se izbacuju iz strane POSLE brojanja (_bez_tombstone);
//   • offset iza kraja → prazna strana sa tačnim `ukupno`;
//   • `view=summary` → uža projekcija; inače sve kolone ("*"), uključujući `case_dna`.
//
// Kolone su one koje produkciona tabela stvarno ima (migracije 015/094/114 +
// sonda iz test_bu001): NEMA `sud`, NEMA `klijent`.

import { json } from "./api-fixture.mjs";

const SUMMARY = ["id", "naziv", "tip", "status", "broj_predmeta", "created_at", "updated_at", "brisanje_zapoceto"];

/* Realističan `case_dna` (~3,9 KB po predmetu; mereno u api.py komentaru:
 * 92 090 B / 20 predmeta, 85% odgovora). */
function caseDna(i) {
  const cinjenice = Array.from({ length: 18 }, (_, k) => ({ id: `c${i}-${k}`, tekst: `Činjenica ${k} predmeta ${i}: opis događaja i dokaza koji ga potkrepljuju u spisima.`, izvor: "dokument", pouzdanost: 0.8 }));
  return { verzija: 3, cinjenice, rizici: [{ nivo: "srednji", opis: "Rok za žalbu" }], sazetak: "Sažetak predmeta ".repeat(20) };
}

/** n predmeta korisnika; `opcije.status(i)`, `opcije.u_brisanju(i)`, `opcije.naziv(i)` itd. */
export function napraviPredmete(korisnik, n, opcije = {}) {
  const osnova = Date.UTC(2026, 9, 6, 12, 0, 0);
  return Array.from({ length: n }, (_, i) => ({
    id: `${korisnik}-${String(i).padStart(5, "0")}`,
    user_id: korisnik,
    naziv: opcije.naziv ? opcije.naziv(i) : `Predmet ${korisnik} broj ${i}`,
    tip: "parnicni",
    status: opcije.status ? opcije.status(i) : "aktivan",
    broj_predmeta: opcije.broj ? opcije.broj(i) : `P ${1000 + i}/2026`,
    tuzilac: opcije.tuzilac ? opcije.tuzilac(i) : `Tužilac ${i}`,
    tuzeni: opcije.tuzeni ? opcije.tuzeni(i) : `Tuženi ${i}`,
    opis: `TAJNI-OPIS-${korisnik}-${i}`,
    rizik: null,
    vrednost_spora: 100000 + i,
    // Namerno se ponavljaju vremena, da redosled zavisi i od `id` (drugi ključ).
    created_at: new Date(osnova - Math.floor(i / 3) * 3600000).toISOString(),
    updated_at: new Date(osnova - Math.floor(i / 2) * 1800000).toISOString(),
    brisanje_zapoceto: opcije.u_brisanju && opcije.u_brisanju(i) ? new Date(osnova).toISOString() : null,
    assimilation_status: null,
    case_dna: caseDna(i),
  }));
}

function ceoBroj(v, pod) { if (v === null || v === undefined || v === "") return pod; const n = Number(v); return Number.isInteger(n) ? n : NaN; }

/**
 * Handler za pokreniFixture. `korisnici`: { [token]: { id, predmeti } }.
 * `kuke.preStrane(offset, korisnik)` → može da vrati Promise (kašnjenje) ili
 * objekat `{ status, telo }` koji zamenjuje odgovor (greška usred stranica).
 * `kuke.izmeniOdgovor(telo, offset)` → menja telo pre slanja.
 */
export function predmetiRuta(korisnici, kuke = {}) {
  return async (req, url, res) => {
    if (url.pathname !== "/api/predmeti") return false;
    if (req.method !== "GET") { json(res, 405, { detail: "Method Not Allowed" }); return true; }
    const a = req.headers.authorization || "";
    if (!a.startsWith("Bearer ")) { json(res, 401, { detail: "Unauthorized" }); return true; }
    const k = korisnici[a.slice(7)];
    if (!k) { json(res, 401, { detail: "Invalid token" }); return true; }

    let limit = ceoBroj(url.searchParams.get("limit"), 200);
    let offset = ceoBroj(url.searchParams.get("offset"), 0);
    if (Number.isNaN(limit) || Number.isNaN(offset)) { json(res, 422, { detail: "validation" }); return true; }
    limit = Math.min(Math.max(limit, 1), 500);
    offset = Math.max(offset, 0);
    const status = (url.searchParams.get("status") || "").trim().slice(0, 40);
    const q = (url.searchParams.get("q") || "").trim().replace(/[%_]/g, "").slice(0, 120).toLowerCase();
    const summary = (url.searchParams.get("view") || "").trim().toLowerCase() === "summary";

    if (kuke.preStrane) {
      const z = await kuke.preStrane(offset, k.id);
      if (z && z.status) { json(res, z.status, z.telo ?? { detail: "fixture" }); return true; }
    }
    if (res.destroyed) return true;

    let redovi = k.predmeti.filter(p => p.user_id === k.id);
    if (status) redovi = redovi.filter(p => p.status === status);
    if (q) redovi = redovi.filter(p => p.naziv.toLowerCase().includes(q));
    redovi = redovi.slice().sort((x, y) => (x.created_at < y.created_at ? 1 : x.created_at > y.created_at ? -1 : x.id < y.id ? 1 : x.id > y.id ? -1 : 0));
    const ukupno = redovi.length;
    let strana = redovi.slice(offset, offset + limit).filter(p => !p.brisanje_zapoceto);
    if (summary) strana = strana.map(p => Object.fromEntries(SUMMARY.map(c => [c, p[c]])));
    let telo = { predmeti: strana, ukupno, limit, offset };
    if (kuke.izmeniOdgovor) telo = kuke.izmeniOdgovor(telo, offset);
    json(res, 200, telo);
    return true;
  };
}
