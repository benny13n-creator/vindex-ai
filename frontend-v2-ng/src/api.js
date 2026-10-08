/* Vindex V2 NG — jedina HTTP granica.
 *
 * Sve mrežne operacije V2 ekrana prolaze ovde: `get` (čitanje) i `send`
 * (pisanje, vidi dole). Svaki ishod je strukturisan objekat:
 *
 *   { ok: true,  status, podaci }
 *   { ok: false, status, greska: { kod, poruka, retryAfter? } }
 *
 * Kodovi: AUTH_REQUIRED 401 · FORBIDDEN 403 · NOT_FOUND 404 · RATE_LIMITED 429
 *         SERVER_ERROR 5xx · HTTP_ERROR ostali · NETWORK_ERROR · INVALID_RESPONSE
 *         ABORTED · CONFIG_ERROR (zahtev nije ni poslat)
 *
 * PRAVILA (fail-closed):
 *  • greška se NIKAD ne pretvara u prazan rezultat — 401/500/mreža nisu „0 predmeta“;
 *  • nema ponavljanja zahteva;
 *  • putanja mora biti `/api/...` na ISTOM izvoru — token nikad ne ide drugom hostu;
 *  • `user_id` se nikad ne šalje: o pripadnosti podataka odlučuje SERVER iz tokena;
 *  • kolačići se ne šalju (`credentials: "omit"`); jedini kredencijal je token
 *    koji je izdao postojeći Supabase login;
 *  • ovaj modul ništa ne ispisuje u konzolu (token ne sme u log).
 */
(function (root) {
  "use strict";

  var ZABRANJENI_PARAMETRI = { user_id: 1, userid: 1, uid: 1, owner_id: 1 };

  function greska(kod, poruka, status, dodatak) {
    var g = { kod: kod, poruka: poruka };
    if (dodatak) for (var k in dodatak) g[k] = dodatak[k];
    return { ok: false, status: status || 0, greska: g };
  }

  function kodZaStatus(s) {
    if (s === 401) return "AUTH_REQUIRED";
    if (s === 403) return "FORBIDDEN";
    if (s === 404) return "NOT_FOUND";
    if (s === 429) return "RATE_LIMITED";
    if (s >= 500) return "SERVER_ERROR";
    return "HTTP_ERROR";
  }

  function napraviAdresu(putanja, parametri) {
    if (typeof putanja !== "string" || putanja.indexOf("/api/") !== 0 || putanja.indexOf("//") !== -1 || putanja.indexOf("?") !== -1) {
      throw new Error("putanja mora biti /api/... bez upita i bez drugog hosta");
    }
    var q = new URLSearchParams();
    if (parametri) {
      Object.keys(parametri).forEach(function (k) {
        if (ZABRANJENI_PARAMETRI[String(k).toLowerCase()]) {
          throw new Error("parametar „" + k + "“ nije dozvoljen: pripadnost podataka određuje server");
        }
        var v = parametri[k];
        if (v !== undefined && v !== null) q.append(k, String(v));
      });
    }
    var s = q.toString();
    return putanja + (s ? "?" + s : "");
  }

  /**
   * GET /api/... sa opcionim tokenom.
   * @param {string} putanja  npr. "/api/predmeti"
   * @param {{token?: string, signal?: AbortSignal, parametri?: Object, oblik?: function(*):boolean}} opcije
   */
  async function get(putanja, opcije) {
    opcije = opcije || {};
    var adresa;
    try { adresa = napraviAdresu(putanja, opcije.parametri); }
    catch (e) { return greska("CONFIG_ERROR", e.message, 0); }

    if (opcije.signal && opcije.signal.aborted) return greska("ABORTED", "Zahtev je otkazan.", 0);

    var zaglavlja = { Accept: "application/json" };
    if (typeof opcije.token === "string" && opcije.token) zaglavlja.Authorization = "Bearer " + opcije.token;

    var odgovor;
    try {
      odgovor = await root.fetch(adresa, {
        method: "GET", headers: zaglavlja, signal: opcije.signal,
        credentials: "omit", cache: "no-store", redirect: "error",
      });
    } catch (e) {
      if ((opcije.signal && opcije.signal.aborted) || (e && e.name === "AbortError")) {
        return greska("ABORTED", "Zahtev je otkazan.", 0);
      }
      return greska("NETWORK_ERROR", "Server nije dostupan.", 0);
    }

    if (!odgovor.ok) {
      var dodatak = null;
      if (odgovor.status === 429) {
        var ra = odgovor.headers.get("Retry-After");
        if (ra) dodatak = { retryAfter: ra };
      }
      return greska(kodZaStatus(odgovor.status), "Server je odgovorio statusom " + odgovor.status + ".", odgovor.status, dodatak);
    }

    var tekst;
    try { tekst = await odgovor.text(); }
    catch (e) {
      if ((opcije.signal && opcije.signal.aborted) || (e && e.name === "AbortError")) {
        return greska("ABORTED", "Zahtev je otkazan.", odgovor.status);
      }
      return greska("NETWORK_ERROR", "Odgovor nije primljen do kraja.", odgovor.status);
    }

    var podaci;
    try { podaci = JSON.parse(tekst); }
    catch (e) { return greska("INVALID_RESPONSE", "Odgovor nije ispravan JSON.", odgovor.status); }
    if (podaci === null || typeof podaci !== "object" || Array.isArray(podaci)) {
      return greska("INVALID_RESPONSE", "Odgovor nema očekivani oblik.", odgovor.status);
    }
    if (typeof opcije.oblik === "function" && !opcije.oblik(podaci)) {
      return greska("INVALID_RESPONSE", "Odgovor nema očekivani oblik.", odgovor.status);
    }
    return { ok: true, status: odgovor.status, podaci: podaci };
  }

  /* ── Pisanje (NS005) ────────────────────────────────────────────────────
   * Odvojeno od `get` NAMERNO: čitanje bez posledice, pisanje sa posledicom.
   * Iste granice kao `get` (isti izvor, `/api/...`, bez kolačića, bez
   * preusmeravanja, bez ispisa), plus:
   *  • samo metodi koje V2 stvarno koristi; DELETE ne postoji u ovom sloju;
   *  • telo ne sme nositi vlasnika (`user_id`, `owner_id`, `tenant_id`…) —
   *    pripadnost određuje server iz tokena;
   *  • NIKAD se ne ponavlja;
   *  • kada odgovor ne stigne (mreža, prekid, otkazivanje u letu) ili server
   *    padne (5xx), ishod NIJE poznat: zahtev je možda upisan. Takav ishod
   *    nosi `ishodNepoznat: true` i ekran ne sme reći „nije sačuvano“.
   *    Samo odbijanje servera (4xx) znači da upis nije izvršen.
   * Kodovi pored onih iz `get`: BAD_REQUEST 400 · CONFLICT 409 ·
   * TOO_LARGE 413 · UNSUPPORTED_MEDIA 415 · VALIDATION_ERROR 422 ·
   * OUTCOME_UNKNOWN (mreža/prekid posle slanja). */
  var METODI_PISANJA = { POST: 1, PATCH: 1 };
  var ZABRANJENA_POLJA = { user_id: 1, userid: 1, uid: 1, owner_id: 1, tenant_id: 1, vlasnik_id: 1 };

  function kodPisanja(s) {
    if (s === 400) return "BAD_REQUEST";
    if (s === 409) return "CONFLICT";
    if (s === 413) return "TOO_LARGE";
    if (s === 415) return "UNSUPPORTED_MEDIA";
    if (s === 422) return "VALIDATION_ERROR";
    return kodZaStatus(s);
  }

  function zabranjenoPolje(telo) {
    var kljucevi = [];
    if (typeof FormData !== "undefined" && telo instanceof FormData) telo.forEach(function (v, k) { kljucevi.push(k); });
    else if (telo && typeof telo === "object") kljucevi = Object.keys(telo);
    for (var i = 0; i < kljucevi.length; i++) if (ZABRANJENA_POLJA[String(kljucevi[i]).toLowerCase()]) return kljucevi[i];
    return null;
  }

  /* 422 nosi samo IMENA polja koja server nije prihvatio — nikad sirov tekst. */
  function poljaIz422(tekst) {
    try {
      var d = JSON.parse(tekst).detail;
      if (!Array.isArray(d)) return [];
      return d.map(function (x) { return x && Array.isArray(x.loc) ? String(x.loc[x.loc.length - 1]) : ""; })
        .filter(function (x) { return /^[A-Za-z_][A-Za-z0-9_]{0,40}$/.test(x); });
    } catch (e) { return []; }
  }

  /**
   * POST/PATCH /api/... sa tokenom tekuće sesije.
   * @param {string} putanja
   * @param {{metod?: "POST"|"PATCH", telo?: Object|FormData, token?: string, signal?: AbortSignal, oblik?: function(*):boolean}} opcije
   */
  async function send(putanja, opcije) {
    opcije = opcije || {};
    var metod = String(opcije.metod || "POST").toUpperCase();
    if (!METODI_PISANJA[metod]) return greska("CONFIG_ERROR", "Metod nije dozvoljen.", 0);
    var adresa;
    try { adresa = napraviAdresu(putanja, null); }
    catch (e) { return greska("CONFIG_ERROR", e.message, 0); }
    var telo = opcije.telo;
    var zabranjeno = zabranjenoPolje(telo);
    if (zabranjeno) return greska("CONFIG_ERROR", "polje „" + zabranjeno + "“ nije dozvoljeno: pripadnost podataka određuje server", 0);
    if (typeof opcije.token !== "string" || !opcije.token) return greska("AUTH_REQUIRED", "Niste prijavljeni.", 0);
    if (opcije.signal && opcije.signal.aborted) return greska("ABORTED", "Zahtev je otkazan.", 0);

    var zaglavlja = { Accept: "application/json", Authorization: "Bearer " + opcije.token };
    var sadrzaj;
    if (typeof FormData !== "undefined" && telo instanceof FormData) sadrzaj = telo;
    else if (telo !== undefined && telo !== null) { zaglavlja["Content-Type"] = "application/json"; sadrzaj = JSON.stringify(telo); }

    var odgovor;
    try {
      odgovor = await root.fetch(adresa, {
        method: metod, headers: zaglavlja, body: sadrzaj, signal: opcije.signal,
        credentials: "omit", cache: "no-store", redirect: "error",
      });
    } catch (e) {
      /* Zahtev je možda stigao do servera: ishod nije poznat ni kad je otkazan u letu. */
      if ((opcije.signal && opcije.signal.aborted) || (e && e.name === "AbortError")) {
        return greska("ABORTED", "Zahtev je otkazan; ishod upisa nije poznat.", 0, { ishodNepoznat: true });
      }
      return greska("OUTCOME_UNKNOWN", "Veza je prekinuta pre odgovora; ishod upisa nije poznat.", 0, { ishodNepoznat: true });
    }

    var tekst;
    try { tekst = await odgovor.text(); }
    catch (e) {
      if (!odgovor.ok) return greska(kodPisanja(odgovor.status), "Server je odgovorio statusom " + odgovor.status + ".", odgovor.status, { ishodNepoznat: odgovor.status >= 500 });
      return greska("OUTCOME_UNKNOWN", "Odgovor nije primljen do kraja; ishod upisa nije poznat.", odgovor.status, { ishodNepoznat: true });
    }

    if (!odgovor.ok) {
      var dodatak = { ishodNepoznat: odgovor.status >= 500 };
      if (odgovor.status === 429) { var ra = odgovor.headers.get("Retry-After"); if (ra) dodatak.retryAfter = ra; }
      if (odgovor.status === 422) dodatak.polja = poljaIz422(tekst);
      return greska(kodPisanja(odgovor.status), "Server je odgovorio statusom " + odgovor.status + ".", odgovor.status, dodatak);
    }

    /* 2xx: upis JE prihvaćen. Neispravno telo ne pretvara uspeh u grešku,
     * ali pozivalac zna da podatke odgovora ne može da koristi. */
    var podaci = null;
    if (tekst) { try { podaci = JSON.parse(tekst); } catch (e) { podaci = null; } }
    var ispravno = podaci !== null && typeof podaci === "object" && !Array.isArray(podaci)
      && (typeof opcije.oblik !== "function" || opcije.oblik(podaci));
    return ispravno ? { ok: true, status: odgovor.status, podaci: podaci }
      : { ok: true, status: odgovor.status, podaci: null, neispravanOdgovor: true };
  }

  root.VxApi = Object.freeze({ get: get, send: send });
})(window);
