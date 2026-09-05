/* Vindex V2 — sesija.
 *
 * NAMERNO BEZ SDK-a. Legacy `/static/supabase.min.js` je UMD paket koji piše
 * `window.supabase` — globalna promenljiva je tacno ono sto V2 ne sme da nasledi
 * (Z015 §2). Ovde se koristi ISTI mehanizam skladistenja koji taj SDK vec pise,
 * pa je sesija zajednicka: ko je prijavljen na /app, prijavljen je i na /app-v2.
 *
 * Kljuc skladista je konvencija supabase-js v2: `sb-<ref>-auth-token`, gde je
 * <ref> prvi segment hosta projekta. Ako se konvencija ikad promeni, sesija se
 * ovde nece naci i korisnik ce biti poslat na kanonsku prijavu — fail-closed,
 * nikad tihi prolaz.
 *
 * Frontend NIJE bezbednosna granica. Ovaj modul samo pribavlja token; svaku
 * odluku o pristupu donosi backend.
 */

import { upozori } from "./log.js";

const SUPABASE_URL = "https://czsxymueizfqrbbgqqob.supabase.co";
const SUPABASE_ANON = "sb_publishable_fvC51B_GKz_Uf8t3wZ3JDg_TIp3-zBp";
const REF = new URL(SUPABASE_URL).hostname.split(".")[0];
const KLJUC = `sb-${REF}-auth-token`;

/** Kanonsko odrediste prijave. V2 nema svoj ekran za prijavu i nece ga imati
 *  u Wave 1 — prijava ostaje jedan tok za ceo proizvod. */
export const PRIJAVA = "/app";

let _sesija = null;

function procitajSkladiste() {
  let sirovo;
  try {
    sirovo = window.localStorage.getItem(KLJUC);
  } catch (e) {
    upozori("localStorage nije dostupan");
    return null;
  }
  if (!sirovo) return null;
  try {
    // supabase-js v2 ume da upise i `base64-` prefiksiran zapis.
    const tekst = sirovo.startsWith("base64-")
      ? decodeURIComponent(escape(window.atob(sirovo.slice(7))))
      : sirovo;
    const o = JSON.parse(tekst);
    if (!o || !o.access_token) return null;
    return o;
  } catch (e) {
    return null;
  }
}

function upisiSkladiste(o) {
  try { window.localStorage.setItem(KLJUC, JSON.stringify(o)); } catch (e) { /* bez sesije radimo dalje */ }
}

function istekao(o) {
  if (!o || !o.expires_at) return false;
  // 60 s rezerve: token koji istice tokom leta zahteva je isto sto i istekao.
  return (o.expires_at * 1000) - Date.now() < 60_000;
}

async function osvezi(o) {
  if (!o || !o.refresh_token) return null;
  let r;
  try {
    r = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=refresh_token`, {
      method: "POST",
      headers: { "Content-Type": "application/json", apikey: SUPABASE_ANON },
      body: JSON.stringify({ refresh_token: o.refresh_token }),
    });
  } catch (e) {
    return null; // mreza — pozivalac odlucuje
  }
  if (!r.ok) return null;
  const nov = await r.json();
  if (!nov || !nov.access_token) return null;
  const spojeno = Object.assign({}, o, nov);
  upisiSkladiste(spojeno);
  return spojeno;
}

/** Razresava sesiju. Vraca `null` kada korisnik nije prijavljen. */
export async function razresiSesiju() {
  let o = procitajSkladiste();
  if (!o) return null;
  if (istekao(o)) {
    o = await osvezi(o);
    if (!o) return null;
  }
  _sesija = o;
  return o;
}

export function token() {
  return _sesija ? _sesija.access_token : null;
}

export function korisnik() {
  const u = _sesija && _sesija.user;
  return u ? { id: u.id, email: u.email || "" } : null;
}

export function naPrijavu() {
  window.location.replace(PRIJAVA);
}
