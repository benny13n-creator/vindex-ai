/* Vindex V2 NG — jedina HTTP granica (samo čitanje).
 *
 * Sve mrežne operacije V2 ekrana prolaze ovde. Namerno postoji SAMO `get`:
 * ovaj sloj ne ume da piše. Svaki ishod je strukturisan objekat:
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

  root.VxApi = Object.freeze({ get: get });
})(window);
