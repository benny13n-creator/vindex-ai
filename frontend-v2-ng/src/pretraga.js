/* Vindex V2 NG — globalna pretraga (NS005, CAP-160).
 *
 * Ugovor (routers/search.py): GET /api/search?q=&vrste=&limit=
 *   → {q, ukupno, predmeti:[], dokumenti:[], beleske:[], hronologija:[], nepotpuno?: [vrste]}
 *   Server pretražuje SAMO podatke pozivaoca; grana koja padne ide u `nepotpuno`
 *   (to NIJE „nema rezultata"). Upit kraći od 2 znaka → 422 (proverava se i ovde).
 * Traže se samo vrste koje se u V2 mogu OTVORITI (predmet, dokument, beleška,
 * hronologija → odgovarajući odeljak predmeta). Klijenti se ne traže: V2 nema
 * ekran klijenta, a rezultat koji se ne može otvoriti ne prikazuje se kao link.
 */
(function (root) {
  "use strict";

  var VRSTE = ["predmeti", "dokumenti", "beleske", "hronologija"];
  var NASLOV = { predmeti: "Predmeti", dokumenti: "Dokumenti", beleske: "Beleške", hronologija: "Hronologija" };
  var ISPRAVAN_ID = /^[A-Za-z0-9_-]{1,64}$/;

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api, adresa = o.adresaPredmeta;
    var gen = 0, kontroler = null, tajmer = 0;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function stanje(t, oznaka) { var s = $("pr-stanje"); s.hidden = !t; s.textContent = t || ""; if (oznaka) s.dataset.stanje = oznaka; else delete s.dataset.stanje; }
    function ocistiRezultate() { $("pr-rezultati").replaceChildren(); $("pr-nepotpuno").hidden = true; $("pr-nepotpuno").textContent = ""; }
    function ponisti() { gen++; if (kontroler) { kontroler.abort(); kontroler = null; } clearTimeout(tajmer); }

    function link(vrsta, x) {
      var pid = vrsta === "predmeti" ? x.id : (x.meta && x.meta.predmet_id);
      if (pid === undefined || pid === null || !ISPRAVAN_ID.test(String(pid))) return null;
      return adresa(String(pid), vrsta === "dokumenti" ? "dokumenti" : vrsta === "predmeti" ? "pregled" : "rad");
    }

    async function trazi() {
      ponisti();
      var q = $("pr-upit").value.trim().slice(0, 200);
      ocistiRezultate();
      if (q.length < 2) { stanje(q ? "Upišite bar dva znaka." : null); return; }
      var s = sesija.stanje();
      if (s.stanje !== sesija.STANJA.PRIJAVLJEN) { stanje("Niste prijavljeni. Pretraga nije izvršena.", "greska"); return; }
      var moja = gen, korisnik = s.korisnik;
      kontroler = new AbortController();
      stanje("Pretraga…", "ucitavanje");
      var r = await api.get("/api/search", { token: sesija.token(), signal: kontroler.signal, parametri: { q: q, vrste: VRSTE.join(","), limit: 10 },
        oblik: function (x) { return typeof x.ukupno === "number"; } });
      if (moja !== gen || sesija.stanje().korisnik !== korisnik) return;
      kontroler = null;
      if (!r.ok) {
        if (r.greska && r.greska.kod === "ABORTED") return;
        stanje(r.greska && r.greska.kod === "RATE_LIMITED" ? "Previše zahteva. Pretraga nije izvršena; pokušajte malo kasnije."
          : "Pretraga nije uspela. Ovo nije prazan rezultat; pokušajte ponovo.", "greska");
        return;
      }
      var p = r.podaci, ukupno = 0;
      var nepotpuno = Array.isArray(p.nepotpuno) ? p.nepotpuno.filter(function (v) { return NASLOV[v]; }) : [];
      VRSTE.forEach(function (v) {
        var lista = Array.isArray(p[v]) ? p[v] : [];
        var stavke = lista.map(function (x) { return x && typeof x === "object" ? { x: x, href: link(v, x) } : null; }).filter(function (s) { return s && s.href; });
        if (!stavke.length) return;
        ukupno += stavke.length;
        var sek = el("section", "results__group");
        sek.append(el("h2", "results__title", NASLOV[v]));
        var ul = el("ul", "results__list");
        stavke.forEach(function (s) {
          var li = el("li"), a = el("a", "results__item");
          a.href = s.href;
          var naziv = String(s.x.naziv || "").trim() || "Bez naziva";
          a.append(el("span", "results__name", naziv));
          var prev = String(s.x.preview || "").trim();
          if (prev && prev !== naziv) a.append(el("span", "results__preview", prev));
          li.append(a); ul.append(li);
        });
        sek.append(ul);
        $("pr-rezultati").append(sek);
      });
      if (nepotpuno.length) {
        $("pr-nepotpuno").hidden = false;
        $("pr-nepotpuno").textContent = "Pretraga nije potpuna: nije pretraženo — " + nepotpuno.map(function (v) { return NASLOV[v].toLowerCase(); }).join(", ") + ". Odsustvo rezultata u tim grupama ne znači da ih nema.";
      }
      if (!ukupno) stanje(nepotpuno.length ? "U pretraženim grupama nema rezultata za „" + q + "“." : "Nema rezultata za „" + q + "“.", "prazno");
      else stanje(ukupno + (ukupno === 1 ? " rezultat" : " rezultata") + " za „" + q + "“.", "uspeh");
    }

    $("pr-forma").addEventListener("submit", function (e) { e.preventDefault(); trazi(); });
    $("pr-upit").addEventListener("input", function () { clearTimeout(tajmer); tajmer = setTimeout(trazi, 350); });
    var odjavi = sesija.naPromenu(function (novo, staro) {
      if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) { ponisti(); $("pr-upit").value = ""; ocistiRezultate(); stanje(null); }
    });

    return {
      otvori: function () { setTimeout(function () { $("pr-upit").focus(); }, 0); },
      zatvori: function () { ponisti(); },
      zaustavi: function () { odjavi(); ponisti(); },
    };
  }

  root.VxPretraga = Object.freeze({ napravi: napravi });
})(window);
