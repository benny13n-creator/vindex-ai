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

  var trenutni = razresi(root.location ? root.location.search : "");

  root.VxRuntime = Object.freeze({
    DEMO: DEMO, LIVE: LIVE, NEISPRAVAN: NEISPRAVAN,
    razresi: razresi,
    rezim: trenutni.rezim,
    greska: trenutni.greska,
  });
})(window);
