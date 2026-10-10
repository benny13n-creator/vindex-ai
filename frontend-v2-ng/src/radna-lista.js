/* Vindex V2 NG — DANAS: radna lista iz kanonske table (NS006, Task 12).
 *
 * Ugovor (routers/workspace.py, nepromenjen):
 *   GET /api/workspace → {danas[], kriticno[], predstojece[], za_pregled[], na_cekanju[], zavrseno_nedavno[],
 *        ukupno_aktivnih, degradirani_izvori[], provera_potpuna}
 *   stavka: {vrsta: case_action | zadatak | review, id, predmet_id, predmet_naziv, naslov, tip, prioritet, rok,
 *            izvor{...}, created_at}
 * Tabla je JEDINI vlasnik pitanja „šta me sada traži": sistemske akcije (deterministički Case Actions), zadaci koje je
 * čovek zadao i dokumenti koji čekaju pregled ostaju RAZLIČITE vrste i tako se i prikazuju. Bez modela pri otvaranju.
 * Nepročitan izvor table se prijavljuje — prazna tabla iz pada NIJE „sve je pod kontrolom".
 */
(function (root) {
  "use strict";

  var KORPE = [["danas", "Danas"], ["kriticno", "Kritično"], ["predstojece", "Predstojeće"], ["za_pregled", "Za pregled"],
               ["na_cekanju", "Na čekanju"], ["zavrseno_nedavno", "Završeno nedavno"]];
  var VRSTA = { case_action: "Radnja sistema", zadatak: "Zadatak", review: "Dokument za pregled" };
  var TIP = { PRIPREMITI_PODNESAK: "Pripremiti podnesak", PRIBAVITI_DOKAZ: "Pribaviti dokaz", RAZRESITI_KONTRADIKCIJU: "Razrešiti protivrečnost",
    OJACATI_DOKAZE: "Ojačati dokaze", PLANIRATI_ROKOVE: "Planirati rokove" };
  var PRIORITET = { critical: "kritično", high: "visoko", medium: "srednje", low: "nisko", informational: "informativno" };

  function tekst(v) { return String(v == null ? "" : v).trim(); }
  function datum(iso) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(tekst(iso)); return m ? m[3] + "." + m[2] + "." + m[1] + "." : ""; }
  function ispravanId(v) { return /^[A-Za-z0-9_-]{1,64}$/.test(tekst(v)); }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api, adresaPredmeta = o.adresaPredmeta;
    var gen = 0, k = null, otvoren = false;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function stanje(st, t) { var n = $("rl-stanje"); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function ocisti() { gen++; if (k) { k.abort(); k = null; } $("rl-korpe").replaceChildren(); stanje(null); }

    function zasto(x) {
      if (x.vrsta === "case_action") {
        var dz = (x.izvor && x.izvor.dokaz) || {};
        var izvor = dz.rociste_id ? "ročište " + (dz.datum ? datum(dz.datum) : "") : dz.source_type === "v2_contradiction" ? "protivrečnost u spisima"
          : dz.izvor === "identify_case_problems" ? "pravilo nad dokazima predmeta" : "";
        return "Zašto: " + tekst(x.naslov) + (izvor ? " (izvor: " + izvor + ")" : "");   // naslov radnje = razlog iz backend-a
      }
      if (x.vrsta === "review") return "Zašto: obrada dokumenta čeka vašu potvrdu pre nego što postane podatak predmeta.";
      return "Zadatak u kancelariji" + (x.izvor && x.izvor.zadatak_status ? " · stanje: " + tekst(x.izvor.zadatak_status) : "");
    }

    function stavka(x) {
      var li = el("li", "today__item today__item--rad");
      li.dataset.vrsta = tekst(x.vrsta); li.dataset.prioritet = tekst(x.prioritet);
      li.append(el("span", "today__when", x.rok ? "rok " + datum(x.rok) : "bez roka"));
      li.append(el("span", "today__kind", (VRSTA[x.vrsta] || tekst(x.vrsta)) + (x.prioritet ? " · " + (PRIORITET[x.prioritet] || x.prioritet) : "")));
      var sta = el("span", "today__what");
      /* radnja sistema: naslov je VRSTA radnje, razlog ide u „Zašto" (bez ponavljanja); zadatak i pregled nose svoj naslov */
      sta.append(el("span", null, x.vrsta === "case_action" ? (TIP[x.tip] || tekst(x.tip).replace(/_/g, " ").toLowerCase()) : tekst(x.naslov)));
      sta.append(el("span", "an-item__meta", zasto(x)));
      li.append(sta);
      if (ispravanId(x.predmet_id)) {
        var a = el("a", "today__case", tekst(x.predmet_naziv) || "Predmet");
        a.href = adresaPredmeta(x.predmet_id, x.vrsta === "case_action" ? "analiza" : "pregled");
        li.append(a);
      } else li.append(el("span", "today__case", tekst(x.predmet_naziv)));
      return li;
    }

    async function ucitaj() {
      var s = sesija.stanje();
      ocisti();
      var moja = gen, korisnik = s.korisnik;
      if (s.stanje !== sesija.STANJA.PRIJAVLJEN) return;
      k = new AbortController();
      stanje("ucitavanje", "Učitavanje radne liste…");
      var r = await api.get("/api/workspace", { token: sesija.token(), signal: k.signal,
        oblik: function (x) { return x && KORPE.every(function (kp) { return Array.isArray(x[kp[0]]); }) && Array.isArray(x.degradirani_izvori); } });
      if (moja !== gen || sesija.stanje().korisnik !== korisnik) return;
      k = null;
      if (!r.ok) {
        if (r.greska && r.greska.kod === "ABORTED") return;
        stanje("greska", "Radna lista nije učitana zbog greške. Ovo ne znači da nema obaveza.");
        return;
      }
      var x = r.podaci;
      var ukupno = KORPE.reduce(function (n, kp) { return n + (kp[0] === "zavrseno_nedavno" ? 0 : x[kp[0]].length); }, 0);
      if (x.degradirani_izvori.length) stanje("nepotpuno", "Radna lista NIJE potpuna — nije pročitano: " + x.degradirani_izvori.map(tekst).join(", ") + ".");
      else if (!ukupno) stanje("prazno", "Nema otvorenih radnji, zadataka ni dokumenata za pregled.");
      else stanje(null);
      KORPE.forEach(function (kp) {
        var lista = x[kp[0]];
        if (!lista.length) return;
        var sek = el("section", "today__group");
        sek.dataset.korpa = kp[0];
        sek.append(el("h3", "answer__h", kp[1] + " (" + lista.length + ")"));
        var ul = el("ul", "today__list");
        lista.slice(0, 50).forEach(function (s2) { ul.append(stavka(s2)); });
        sek.append(ul);
        $("rl-korpe").append(sek);
      });
    }

    var odjavi = sesija.naPromenu(function (novo, staro) {
      if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) { ocisti(); if (otvoren && novo.stanje === sesija.STANJA.PRIJAVLJEN) ucitaj(); }
    });
    return {
      otvori: function () { otvoren = true; ucitaj(); },
      zatvori: function () { otvoren = false; ocisti(); },
      zaustavi: function () { odjavi(); ocisti(); },
    };
  }

  root.VxRadnaLista = Object.freeze({ napravi: napravi });
})(window);
