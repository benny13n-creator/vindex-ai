/* Vindex V2 NG — most ka POSTOJEĆOJ prijavi (samo čitanje).
 *
 * V2 nema svoj login, svoje skladište tokena niti osvežavanje tokena. Čita
 * ISKLJUČIVO kanonski zapis koji upisuje postojeći Supabase klijent na istom
 * izvoru (`sb-<ref>-auth-token` u localStorage) — isti mehanizam koji već
 * koristi produkcioni `/app-v2` (v2/platform/auth.js na main-u). Ko je
 * prijavljen na /app, prijavljen je i ovde.
 *
 * Ovaj modul NIKAD:
 *  • ne piše, ne kopira i ne briše zapis sesije (odjava i osvežavanje su posao
 *    postojeće prijave — ovde se samo PRIMEĆUJU);
 *  • ne šalje mrežne zahteve (nema POST na Supabase refresh);
 *  • ne stavlja token u URL, DOM ili konzolu.
 *
 * Istekao token = stanje „istekla“, ne tihi pokušaj. Frontend nije bezbednosna
 * granica: token samo dokazuje identitet serveru, koji odlučuje o pristupu.
 */
(function (root) {
  "use strict";

  var SUPABASE_URL = "https://czsxymueizfqrbbgqqob.supabase.co";
  var KLJUC = "sb-" + new URL(SUPABASE_URL).hostname.split(".")[0] + "-auth-token";
  /* Token koji ističe tokom leta zahteva je isto što i istekao. */
  var REZERVA_MS = 30000;

  var STANJA = { UCITAVANJE: "ucitavanje", PRIJAVLJEN: "prijavljen", NEPRIJAVLJEN: "neprijavljen", ISTEKLA: "istekla", GRESKA: "greska" };

  function procitaj() {
    var sirovo;
    try { sirovo = root.localStorage.getItem(KLJUC); }
    catch (e) { return { stanje: STANJA.GRESKA }; }
    if (!sirovo) return { stanje: STANJA.NEPRIJAVLJEN };
    var o;
    try {
      var tekst = sirovo.indexOf("base64-") === 0
        ? decodeURIComponent(escape(root.atob(sirovo.slice(7))))
        : sirovo;
      o = JSON.parse(tekst);
    } catch (e) { return { stanje: STANJA.GRESKA }; }
    if (!o || typeof o.access_token !== "string" || !o.access_token) return { stanje: STANJA.GRESKA };
    var korisnik = o.user && typeof o.user.id === "string" ? o.user.id : null;
    if (!korisnik) return { stanje: STANJA.GRESKA };
    if (typeof o.expires_at === "number" && o.expires_at * 1000 - Date.now() < REZERVA_MS) {
      return { stanje: STANJA.ISTEKLA, korisnik: korisnik };
    }
    return { stanje: STANJA.PRIJAVLJEN, korisnik: korisnik, token: o.access_token,
             istice: typeof o.expires_at === "number" ? o.expires_at * 1000 : null };
  }

  var trenutno = { stanje: STANJA.UCITAVANJE };
  var slusaoci = [];
  var tajmerIsteka = 0;

  function isto(a, b) {
    return a.stanje === b.stanje && a.korisnik === b.korisnik && a.token === b.token;
  }

  function zakaziIstek() {
    clearTimeout(tajmerIsteka);
    if (trenutno.stanje === STANJA.PRIJAVLJEN && trenutno.istice) {
      var za = Math.max(0, trenutno.istice - REZERVA_MS - Date.now()) + 50;
      tajmerIsteka = setTimeout(proveri, Math.min(za, 2147483000));
    }
  }

  /** Ponovo čita kanonski zapis i obaveštava slušaoce ako se nešto promenilo. */
  function proveri() {
    var novo = procitaj();
    if (isto(novo, trenutno)) return trenutno.stanje;
    var staro = trenutno;
    trenutno = novo;
    zakaziIstek();
    slusaoci.slice().forEach(function (fn) { fn(javno(novo), javno(staro)); });
    return novo.stanje;
  }

  /* Javni opis stanja NE sadrži token. */
  function javno(s) { return { stanje: s.stanje, korisnik: s.korisnik || null }; }

  function token() { return trenutno.stanje === STANJA.PRIJAVLJEN ? trenutno.token : null; }

  /* Prijava/odjava u drugom tabu (V1) stiže kao `storage` događaj. Fokus i
   * povratak na tab hvataju sve ostalo (npr. ručno brisanje, istek u snu).
   * Slušaoci se kače tek kad se neko pretplati (LIVE) — DEMO ekran nema
   * nijedan slušalac ovog modula. */
  var zakaceno = false;
  function naStorage(e) { if (e.key === KLJUC || e.key === null) proveri(); }
  function naVidljivost() { if (!root.document.hidden) proveri(); }
  function zakaci() {
    if (zakaceno) return;
    zakaceno = true;
    root.addEventListener("storage", naStorage);
    root.addEventListener("focus", proveri);
    root.document.addEventListener("visibilitychange", naVidljivost);
  }

  function naPromenu(fn) {
    zakaci();
    slusaoci.push(fn);
    return function () { slusaoci = slusaoci.filter(function (x) { return x !== fn; }); };
  }

  root.VxSesija = Object.freeze({
    STANJA: STANJA,
    KLJUC: KLJUC,
    proveri: proveri,
    stanje: function () { return javno(trenutno); },
    token: token,
    naPromenu: naPromenu,
  });
})(window);
