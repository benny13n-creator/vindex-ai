/* Vindex V2 NG — režim izvora podataka (DEMO | LIVE).
 *
 * Jedino mesto koje odlučuje odakle ekran čita podatke. Učitava se PRE
 * `demo-data.js`, jer demo podaci postoje samo u DEMO režimu.
 *
 *   bez parametra / ?rezim=demo   → DEMO (izmišljeni primeri, kao do sada)
 *   ?rezim=live                   → LIVE (samo stvarni API; nikad demo)
 *   bilo šta drugo                → NEISPRAVNA konfiguracija: glasna greška
 *
 * PRAVILO: LIVE nikada ne prelazi u DEMO. Mrežna greška, greška prijave,
 * neispravan odgovor i neispravna konfiguracija se PRIKAZUJU kao greška.
 * „Živi izvor nije uspeo pa prikazujemo primere“ bio bi lažan uspeh: advokat
 * bi gledao izmišljene predmete misleći da su njegovi.
 */
(function (root) {
  "use strict";

  var DEMO = "demo", LIVE = "live", NEISPRAVAN = "neispravan";

  function razresi(search) {
    var vrednost;
    try { vrednost = new URLSearchParams(search || "").get("rezim"); }
    catch (e) { return { rezim: NEISPRAVAN, greska: "Adresa stranice nije mogla da se pročita." }; }
    if (vrednost === null || vrednost === DEMO) return { rezim: DEMO, greska: null };
    if (vrednost === LIVE) return { rezim: LIVE, greska: null };
    return {
      rezim: NEISPRAVAN,
      greska: "Nepoznat režim podataka „" + String(vrednost).slice(0, 40) + "“. Dozvoljeno je samo „demo“ ili „live“.",
    };
  }

  /* NS004 — PRIMARNI prikaz: V2 servira sam /app (VINDEX_V2_NG_PRIMARY_ENABLED).
   * Putanja je jedini izvor odluke, pa /app NE MOŽE da padne u DEMO: `rezim`
   * se tamo ne čita, uvek je LIVE. Preview (/v2/preview/) i lokalni prototip
   * zadržavaju postojeće pravilo iznad. */
  var PRIMARNI = "primarni", PREGLED = "pregled";
  function prikazZa(putanja) { return /^\/app\/?$/.test(String(putanja || "")) ? PRIMARNI : PREGLED; }
  var prikaz = prikazZa(root.location ? root.location.pathname : "");

  /* Linkovi postojeće prijave (reset lozinke, potvrda naloga, #login/#register)
   * nose token ili nameru u hash-u i očekuju legacy /app. U primarnom prikazu se
   * ODMAH prosleđuju klasičnoj prijavi sa istim hash-om; V2 ih ne čita. */
  var preusmeren = false;
  if (prikaz === PRIMARNI && root.location) {
    var h = String(root.location.hash || "");
    if (/(^|[#&])(access_token|refresh_token|type|error|error_description|error_code)=/.test(h) || h === "#login" || h === "#register") {
      preusmeren = true;
      root.location.replace("/app-legacy" + h);
    }
  }

  var trenutni = prikaz === PRIMARNI ? { rezim: preusmeren ? NEISPRAVAN : LIVE, greska: preusmeren ? "Preusmeravanje na prijavu…" : null }
    : razresi(root.location ? root.location.search : "");

  root.VxRuntime = Object.freeze({
    DEMO: DEMO, LIVE: LIVE, NEISPRAVAN: NEISPRAVAN, PRIMARNI: PRIMARNI, PREGLED: PREGLED,
    razresi: razresi,
    prikazZa: prikazZa,
    prikaz: prikaz,
    rezim: trenutni.rezim,
    greska: trenutni.greska,
    /* Gde se postojeća prijava/odjava nalazi u ovom prikazu. */
    prijava: prikaz === PRIMARNI ? "/app-legacy?posle=app" : "/app",
    odjava: prikaz === PRIMARNI ? "/app-legacy?odjava=1" : null,
  });
})(window);
