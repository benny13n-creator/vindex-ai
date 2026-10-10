/* Vindex V2 NG — PREGLED: živo stanje predmeta (NS006, Task 11).
 *
 * Tri kratka odgovora na vrhu Pregleda, bez zasebne AI sinteze i bez drugog motora preporuka:
 *   A. Šta se promenilo   ← GET /api/predmeti/{id}/genome-v2/promene  (deterministička razlika verzija)
 *   B. Šta traži pažnju   ← GET /api/case-actions/predmeti/{id}       (kanonske akcije, kritične i visoke)
 *   C. Šta je sledeće     ← ista lista akcija, prva po kanonskom redosledu (prioritet, pa rok)
 * Oba poziva su samo čitanje; model se ne poziva. Pad izvora se prikazuje kao nedostupnost, nikad kao „sve je u redu".
 * Ako se ništa nije promenilo — to se i kaže; ništa se ne izmišlja da bi ekran izgledao bogatije.
 */
(function (root) {
  "use strict";

  var RED = { critical: 0, high: 1, medium: 2, low: 3, informational: 4 };
  var PRIORITET = { critical: "kritično", high: "visoko", medium: "srednje", low: "nisko", informational: "informativno" };
  var TIP = { PRIPREMITI_PODNESAK: "Pripremiti podnesak", PRIBAVITI_DOKAZ: "Pribaviti dokaz", RAZRESITI_KONTRADIKCIJU: "Razrešiti protivrečnost",
    OJACATI_DOKAZE: "Ojačati dokaze", PLANIRATI_ROKOVE: "Planirati rokove" };

  function tekst(v) { return String(v == null ? "" : v).trim(); }
  function datum(iso) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(tekst(iso)); return m ? m[3] + "." + m[2] + "." + m[1] + "." : ""; }
  function poredak(a, b) {
    var pa = RED.hasOwnProperty(a.prioritet) ? RED[a.prioritet] : 9, pb = RED.hasOwnProperty(b.prioritet) ? RED[b.prioritet] : 9;
    if (pa !== pb) return pa - pb;
    return (tekst(a.rok) || "9999-12-31") < (tekst(b.rok) || "9999-12-31") ? -1 : (tekst(a.rok) || "9999-12-31") > (tekst(b.rok) || "9999-12-31") ? 1 : 0;
  }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api, adresaAnalize = o.adresaAnalize || function () { return "#/"; };
    var trenutni = null, gen = 0, kontroler = null;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function stanje(id, st, t) { var n = $(id); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function zivi(moja, id) { return moja === gen && !!trenutni && trenutni.id === id && sesija.stanje().korisnik === trenutni.korisnik; }

    function ocisti() {
      gen++;
      if (kontroler) { kontroler.abort(); kontroler = null; }
      trenutni = null;
      ["zp-promene", "zp-paznja", "zp-sledece"].forEach(function (id) { $(id).replaceChildren(); });
      ["zp-promene-stanje", "zp-paznja-stanje", "zp-sledece-stanje"].forEach(function (id) { stanje(id, null); });
      $("zp-blok").hidden = true;
    }

    async function ucitaj() {
      var moja = ++gen, id = trenutni.id;
      if (kontroler) kontroler.abort();
      kontroler = new AbortController();
      if (sesija.stanje().stanje !== sesija.STANJA.PRIJAVLJEN) return;
      $("zp-blok").hidden = false;
      ["zp-promene-stanje", "zp-paznja-stanje", "zp-sledece-stanje"].forEach(function (x) { stanje(x, "ucitavanje", "Učitavanje…"); });
      var r = await Promise.all([
        api.get("/api/predmeti/" + encodeURIComponent(id) + "/genome-v2/promene", { token: sesija.token(), signal: kontroler.signal,
          oblik: function (x) { return x && typeof x.stanje === "string" && Array.isArray(x.promene); } }),
        api.get("/api/case-actions/predmeti/" + encodeURIComponent(id), { token: sesija.token(), signal: kontroler.signal,
          oblik: function (x) { return x && Array.isArray(x.akcije); } }),
      ]);
      if (!zivi(moja, id)) return;
      kontroler = null;
      if ((r[0].greska && r[0].greska.kod === "ABORTED") || (r[1].greska && r[1].greska.kod === "ABORTED")) return;
      prikaziPromene(r[0]);
      prikaziAkcije(r[1]);
    }

    function prikaziPromene(r) {
      var ul = $("zp-promene");
      if (!r.ok) { stanje("zp-promene-stanje", "greska", "Promene nisu učitane. Ovo ne znači da promena nema."); return; }
      var x = r.podaci;
      if (x.stanje === "PRVA_VERZIJA") { stanje("zp-promene-stanje", "prazno", "Analiza predmeta ima samo jednu verziju — još nema sa čim da se uporedi."); return; }
      if (x.stanje === "DEGRADED") { stanje("zp-promene-stanje", "greska", "Istorija verzija trenutno nije dostupna."); return; }
      if (x.stanje === "UNKNOWN") { stanje("zp-promene-stanje", "nepoznato", x.trenutna_verzija ? "Promene od prethodne verzije nisu poznate." : "Analiza predmeta još nije izračunata."); return; }
      if (!x.promene.length) { stanje("zp-promene-stanje", "prazno", "Nema nove materijalne promene od prethodne verzije analize (v" + x.prethodna_verzija + ")."); return; }
      stanje("zp-promene-stanje", null);
      x.promene.slice(0, 4).forEach(function (p) {
        var li = el("li", "an-change"); li.dataset.oznaka = tekst(p.oznaka);
        li.append(el("span", "an-change__mark", tekst(p.oznaka)), el("span", null, tekst(p.opis)));
        ul.append(li);
      });
      var dalje = el("li", "an-item");
      var a = el("a", "text-btn", (x.promene.length > 4 ? "Još " + (x.promene.length - 4) + " i detalji" : "Detalji") + " u Analizi (v" + x.trenutna_verzija + ")");
      a.href = adresaAnalize(trenutni.id);
      dalje.append(a);
      ul.append(dalje);
    }

    function stavkaAkcije(a) {
      var li = el("li", "an-item");
      li.dataset.akcija = tekst(a.id); li.dataset.prioritet = tekst(a.prioritet);
      var red = el("div", "an-item__head");
      red.append(el("span", "an-item__text", TIP[a.tip] || tekst(a.tip).replace(/_/g, " ").toLowerCase()));
      red.append(el("span", "zp-prio", PRIORITET[a.prioritet] || tekst(a.prioritet)));   // prioritet, ne poreklo: zaseban stil
      li.append(red);
      li.append(el("span", "an-item__meta", "Zašto: " + tekst(a.razlog) + (a.rok ? " · rok " + datum(a.rok) : " · bez roka")));
      return li;
    }

    function prikaziAkcije(r) {
      if (!r.ok) {
        stanje("zp-paznja-stanje", "greska", "Radnje predmeta nisu učitane. Ovo ne znači da ih nema.");
        stanje("zp-sledece-stanje", "greska", "Sledeći korak nije poznat jer radnje nisu učitane.");
        return;
      }
      var sve = r.podaci.akcije.filter(function (a) { return a && a.status !== "closed"; }).slice().sort(poredak);
      var paznja = sve.filter(function (a) { return a.prioritet === "critical" || a.prioritet === "high"; });
      if (!paznja.length) stanje("zp-paznja-stanje", "prazno", "Nijedna otvorena radnja nije kritična ni visokog prioriteta.");
      else { stanje("zp-paznja-stanje", null); paznja.slice(0, 3).forEach(function (a) { $("zp-paznja").append(stavkaAkcije(a)); }); }
      if (!sve.length) stanje("zp-sledece-stanje", "prazno", "Nema otvorenih radnji za ovaj predmet.");
      else { stanje("zp-sledece-stanje", null); $("zp-sledece").append(stavkaAkcije(sve[0])); }
    }

    function postavi(predmet, aktivan) {
      if (trenutni && trenutni.id === predmet.id && trenutni.korisnik === sesija.stanje().korisnik) { if (aktivan) aktiviraj(); return; }
      ocisti();
      trenutni = { id: predmet.id, korisnik: sesija.stanje().korisnik, ucitano: false };
      if (aktivan) aktiviraj();
    }
    function aktiviraj() { if (!trenutni || trenutni.ucitano) return; trenutni.ucitano = true; ucitaj(); }

    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) ocisti(); });
    return { postavi: postavi, aktiviraj: aktiviraj, ocisti: ocisti, osvezi: function () { if (trenutni) { trenutni.ucitano = true; ucitaj(); } },
             zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxZiviPregled = Object.freeze({ napravi: napravi });
})(window);
