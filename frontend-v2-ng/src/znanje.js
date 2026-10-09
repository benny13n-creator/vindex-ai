/* Vindex V2 NG — ZNANJE: sudska praksa i interni stavovi kancelarije (NS005, CAP-042/045).
 *
 * Ugovori:
 *   POST /api/praksa/search {query?, matter?, year_from?, year_to?, limit, offset}
 *        → {decisions:[{decision_number, decision_date, court, matter, izreka_preview,
 *            izreka_full, citat_format}], total, page, limit}; 400 = nevažeći filter; 500 = pad.
 *   POST /interni-stavovi/pretraga {upit 3–500} → {rezultati:[{naslov, tekst, score}], ukupno,
 *        pretraga_neuspesna}  — namespace stavova = korisnik iz tokena (dokazano testom).
 *   POST /interni-stavovi/dodaj {naslov 3–200, tekst 30–20000} → {vektori, naslov}
 * Pravila preuzeta iz v2/domain/praksa.js: odluka je dokument, ne tvrdnja modela (bez ograda
 * o pouzdanosti); citat se nikad ne dopunjuje izmišljenim delovima (rep „od ." se odseca);
 * odluka bez broja se prikazuje, ali se označava kao necitljiva; skor se ne prikazuje.
 * „Nema rezultata" samo posle USPEŠNOG praznog odgovora. Pretrage se šalju samo na zahtev
 * (pretraga stavova troši kredit). Brisanje stavova nije izloženo.
 */
(function (root) {
  "use strict";

  var OBLASTI = ["Građanska", "Zaštita prava", "Upravna", "Krivična"];
  function tekst(v) { return String(v == null ? "" : v).trim(); }
  function datumOdluke(iso) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(tekst(iso)); return m ? m[3] + "." + m[2] + "." + m[1] + "." : tekst(iso); }
  function ocistiCitat(s) { return String(s || "").replace(/,?\s*od\s*\.?\s*$/i, "").replace(/[\s,;]+$/, "").trim(); }
  function uOdluku(d) {
    d = d || {};
    var broj = tekst(d.decision_number), sud = tekst(d.court), datum = tekst(d.decision_date);
    var citat = ocistiCitat(tekst(d.citat_format)) || [sud, broj, datum ? "od " + datumOdluke(datum) : ""].filter(Boolean).join(", ");
    return { broj: broj, sud: sud, oblast: tekst(d.matter), datum: datum ? datumOdluke(datum) : "", izreka: tekst(d.izreka_preview) || tekst(d.izreka_full), citat: citat, citljiva: !!broj };
  }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api;
    var genP = 0, genS = 0, genD = 0, kP = null, kS = null, kD = null, saljeStav = false, popunjeno = false;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function poruka(id, st, t) { var n = $(id); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function prekini(k) { if (k) k.abort(); return null; }
    function prijavljen() { return sesija.stanje().stanje === sesija.STANJA.PRIJAVLJEN; }

    function ocisti() {
      genP++; genS++; genD++; kP = prekini(kP); kS = prekini(kS); kD = prekini(kD); saljeStav = false;
      ["zn-praksa-forma", "zn-stav-forma", "zn-dodaj-forma"].forEach(function (id) { $(id).reset(); });
      ["zn-praksa-lista", "zn-stav-lista"].forEach(function (id) { $(id).replaceChildren(); });
      ["zn-praksa-stanje", "zn-stav-stanje", "zn-dodaj-poruka"].forEach(function (id) { poruka(id, null); });
      $("zn-dodaj-forma").hidden = true; $("zn-dodaj-otvori").setAttribute("aria-expanded", "false");
      $("zn-dodaj-sacuvaj").disabled = false; $("zn-dodaj-sacuvaj").textContent = "Sačuvaj stav";
    }

    /* ── Sudska praksa ── */
    async function traziPraksu() {
      genP++; kP = prekini(kP);
      $("zn-praksa-lista").replaceChildren();
      var telo = { limit: 10, offset: 0 };
      var q = $("zn-praksa-upit").value.trim().slice(0, 300);
      if (q) telo.query = q;
      var obl = $("zn-praksa-oblast").value;
      if (OBLASTI.indexOf(obl) !== -1) telo.matter = obl;
      var od = Number($("zn-praksa-od").value), doG = Number($("zn-praksa-do").value);
      if ($("zn-praksa-od").value && (!Number.isInteger(od) || od < 1900 || od > 2100)) { poruka("zn-praksa-stanje", "greska", "Godina „od“ nije ispravna."); return; }
      if ($("zn-praksa-do").value && (!Number.isInteger(doG) || doG < 1900 || doG > 2100)) { poruka("zn-praksa-stanje", "greska", "Godina „do“ nije ispravna."); return; }
      if ($("zn-praksa-od").value) telo.year_from = od;
      if ($("zn-praksa-do").value) telo.year_to = doG;
      if (telo.year_from && telo.year_to && telo.year_from > telo.year_to) { poruka("zn-praksa-stanje", "greska", "Godina „od“ mora biti manja ili jednaka godini „do“."); return; }
      if (!telo.query && !telo.matter && !telo.year_from && !telo.year_to) { poruka("zn-praksa-stanje", "greska", "Unesite pojam ili izaberite bar jedan filter."); return; }
      if (!prijavljen()) { poruka("zn-praksa-stanje", "greska", "Niste prijavljeni. Pretraga nije izvršena."); return; }
      var moja = genP, korisnik = sesija.stanje().korisnik;
      kP = new AbortController();
      poruka("zn-praksa-stanje", "ucitavanje", "Pretraga sudske prakse…");
      /* Pretraga ne upisuje podatke; POST je zato što je tako ugovor rute. */
      var r = await api.send("/api/praksa/search", { telo: telo, token: sesija.token(), signal: kP.signal, oblik: function (x) { return Array.isArray(x.decisions); } });
      if (moja !== genP || sesija.stanje().korisnik !== korisnik) return;
      kP = null;
      if (!r.ok || !r.podaci) {
        var g = (r.greska) || {};
        if (g.kod === "ABORTED") return;
        poruka("zn-praksa-stanje", "greska", g.kod === "BAD_REQUEST" ? "Filter nije prihvaćen. Proverite oblast i godine."
          : g.kod === "RATE_LIMITED" ? "Previše pretraga. Pokušajte ponovo malo kasnije."
          : "Pretraga prakse nije uspela. Ovo nije prazan rezultat; pokušajte ponovo.");
        return;
      }
      var odluke = r.podaci.decisions.map(uOdluku);
      var ukupno = Number.isFinite(r.podaci.total) ? r.podaci.total : odluke.length;
      if (!odluke.length) { poruka("zn-praksa-stanje", "prazno", "Nijedna odluka ne odgovara pretrazi."); return; }
      poruka("zn-praksa-stanje", "uspeh", "Prikazano " + odluke.length + " od " + ukupno + (ukupno === 1 ? " odluke." : " odluka."));
      odluke.forEach(function (x) {
        var li = el("li", "decision");
        li.append(el("p", "decision__cite", x.citat || "Odluka bez oznake"));
        var meta = [x.sud, x.oblast, x.datum].filter(Boolean).join(" · ");
        if (meta) li.append(el("p", "decision__meta", meta));
        if (!x.citljiva) li.append(el("p", "decision__flag", "Odluka nema broj — ne može se citirati u podnesku."));
        if (x.izreka) li.append(el("p", "decision__text", x.izreka));
        $("zn-praksa-lista").append(li);
      });
    }

    /* ── Interni stavovi ── */
    async function traziStavove() {
      genS++; kS = prekini(kS);
      $("zn-stav-lista").replaceChildren();
      var q = $("zn-stav-upit").value.trim();
      if (q.length < 3) { poruka("zn-stav-stanje", "greska", "Upit mora imati bar tri znaka."); return; }
      if (!prijavljen()) { poruka("zn-stav-stanje", "greska", "Niste prijavljeni. Pretraga nije izvršena."); return; }
      var moja = genS, korisnik = sesija.stanje().korisnik;
      kS = new AbortController();
      poruka("zn-stav-stanje", "ucitavanje", "Pretraga internih stavova…");
      var r = await api.send("/interni-stavovi/pretraga", { telo: { upit: q.slice(0, 500) }, token: sesija.token(), signal: kS.signal,
        oblik: function (x) { return Array.isArray(x.rezultati) && typeof x.pretraga_neuspesna === "boolean"; } });
      if (moja !== genS || sesija.stanje().korisnik !== korisnik) return;
      kS = null;
      if (!r.ok || !r.podaci) {
        var g = r.greska || {};
        if (g.kod === "ABORTED") return;
        poruka("zn-stav-stanje", "greska", g.kod === "FORBIDDEN" ? "Interni stavovi nisu dostupni za vaš nalog." : "Pretraga stavova nije uspela. Ovo nije prazan rezultat.");
        return;
      }
      if (r.podaci.pretraga_neuspesna) { poruka("zn-stav-stanje", "greska", "Pretraga stavova nije izvršena (servis nije odgovorio). Ovo nije prazan rezultat."); return; }
      var lista = r.podaci.rezultati.filter(function (x) { return x && tekst(x.tekst); });
      if (!lista.length) { poruka("zn-stav-stanje", "prazno", "Nijedan stav kancelarije ne odgovara upitu."); return; }
      poruka("zn-stav-stanje", null);
      lista.forEach(function (x) {
        var li = el("li", "decision");
        li.append(el("p", "decision__cite", tekst(x.naslov) || "Stav bez naslova"));
        li.append(el("p", "decision__text", tekst(x.tekst)));
        $("zn-stav-lista").append(li);
      });
    }

    async function dodajStav() {
      if (saljeStav) return;
      var naslov = $("zn-dodaj-naslov").value.trim(), t = $("zn-dodaj-tekst").value.trim();
      if (naslov.length < 3) { poruka("zn-dodaj-poruka", "greska", "Naslov mora imati bar tri znaka."); $("zn-dodaj-naslov").focus(); return; }
      if (t.length < 30) { poruka("zn-dodaj-poruka", "greska", "Tekst stava mora imati bar 30 znakova."); $("zn-dodaj-tekst").focus(); return; }
      if (!prijavljen()) { poruka("zn-dodaj-poruka", "greska", "Niste prijavljeni. Stav nije sačuvan."); return; }
      var moja = ++genD, korisnik = sesija.stanje().korisnik;
      kD = new AbortController(); saljeStav = true;
      $("zn-dodaj-sacuvaj").disabled = true; $("zn-dodaj-sacuvaj").textContent = "Čuvanje…";
      poruka("zn-dodaj-poruka", "ucitavanje", "Stav se čuva…");
      var r = await api.send("/interni-stavovi/dodaj", { telo: { naslov: naslov.slice(0, 200), tekst: t.slice(0, 20000) }, token: sesija.token(), signal: kD.signal,
        oblik: function (x) { return typeof x.vektori === "number"; } });
      if (moja !== genD || sesija.stanje().korisnik !== korisnik) return;
      kD = null; saljeStav = false;
      $("zn-dodaj-sacuvaj").disabled = false; $("zn-dodaj-sacuvaj").textContent = "Sačuvaj stav";
      if (r.ok && r.podaci && r.podaci.vektori > 0) { $("zn-dodaj-forma").reset(); poruka("zn-dodaj-poruka", "uspeh", "Stav „" + naslov + "“ je sačuvan i biće pronađen pretragom."); return; }
      if (r.ok && r.podaci) { poruka("zn-dodaj-poruka", "greska", "Server nije indeksirao stav (0 delova). Stav neće biti pronađen pretragom."); return; }
      if (r.ok) { poruka("zn-dodaj-poruka", "nepoznato", "Stav je prihvaćen, ali odgovor nije mogao da se pročita. Proverite ga pretragom; ne čuvajte ga ponovo."); return; }
      var g = r.greska || {};
      if (g.ishodNepoznat) { poruka("zn-dodaj-poruka", "nepoznato", "Ishod nije poznat: stav je možda sačuvan. Proverite ga pretragom pre nego što pokušate ponovo."); return; }
      poruka("zn-dodaj-poruka", "greska", g.kod === "FORBIDDEN" ? "Interni stavovi nisu dostupni za vaš nalog. Stav nije sačuvan." : g.kod === "VALIDATION_ERROR" ? "Server nije prihvatio naslov ili tekst. Stav nije sačuvan." : "Server je odbio zahtev. Stav nije sačuvan.");
    }

    $("zn-praksa-forma").addEventListener("submit", function (e) { e.preventDefault(); traziPraksu(); });
    $("zn-stav-forma").addEventListener("submit", function (e) { e.preventDefault(); traziStavove(); });
    $("zn-dodaj-forma").addEventListener("submit", function (e) { e.preventDefault(); dodajStav(); });
    $("zn-dodaj-otvori").addEventListener("click", function () {
      var o2 = $("zn-dodaj-forma").hidden;
      $("zn-dodaj-forma").hidden = !o2; $("zn-dodaj-otvori").setAttribute("aria-expanded", String(o2));
      if (o2) $("zn-dodaj-naslov").focus();
    });
    if (!popunjeno) {
      popunjeno = true;
      OBLASTI.forEach(function (x) { var op = d.createElement("option"); op.value = x; op.textContent = x; $("zn-praksa-oblast").append(op); });
    }
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) ocisti(); });

    return { otvori: function () { setTimeout(function () { $("zn-praksa-upit").focus(); }, 0); }, zatvori: function () {}, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxZnanje = Object.freeze({ napravi: napravi, uOdluku: uOdluku });
})(window);
