/* Vindex V2 NG — KANCELARIJA: tim, portfolio, zdravlje (NS005, CAP-091/090/095).
 *
 * Ugovori:
 *   GET /api/kancelarija/moja  → {status:"aktivan", moja_uloga, firma{id,naziv}, clanovi[{email,uloga_label,status}]}
 *                                | {status:"no_firma"} | {status:"pending_invite", firma_naziv}; pad → 503
 *   GET /portfolio/dashboard   → {ukupno_predmeta, ukupno_aktivnih, po_statusu, po_tipu, rokovi_7_dana[],
 *                                 rokovi_14_dana[], hitni_rokovi[], neaktivni_30_dana[]}; pad → 503
 *   GET /api/firm/health-index → {score 0–100, grade, components[{label, score, max}], n_aktivni, n_zatvoreni}; pad → 503
 * Portfolio i indeks se računaju nad predmetima PRIJAVLJENOG korisnika (tako rade rute).
 * NE prikazuje se: AI „direktiva partnera", slabi signali, institucionalni rizici,
 * boja ocene sa servera, serverski sažetak sa ikonicama. Indeks troši kredit → samo na zahtev.
 * Upravljanje članstvom (poziv, uloge, uklanjanje) nije deo ovog zadatka.
 */
(function (root) {
  "use strict";

  var STATUS_CLANA = { ACTIVE: "aktivan", INVITED: "pozvan", SUSPENDED: "suspendovan" };
  function tekst(v) { return String(v == null ? "" : v).trim(); }
  function datum(iso) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(tekst(iso)); return m ? m[3] + "." + m[2] + "." + m[1] + "." : tekst(iso); }
  function broj(v) { return typeof v === "number" && Number.isFinite(v) ? v : null; }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api, adresaPredmeta = o.adresaPredmeta;
    var genT = 0, genP = 0, genZ = 0, kT = null, kP = null, kZ = null;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function stanje(id, st, t) { var n = $(id); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function prekini(k) { if (k) k.abort(); return null; }
    function greskaTekst(g, sta) {
      if (g && g.kod === "AUTH_REQUIRED") return "Prijava više nije važeća. " + sta + " se ne prikazuje.";
      if (g && g.kod === "RATE_LIMITED") return "Previše zahteva. Pokušajte ponovo malo kasnije.";
      if (g && g.kod === "FORBIDDEN") return sta + " nije dostupan za vaš nalog.";
      return sta + " nije učitan zbog greške. Ovo nije prazan rezultat.";
    }

    function ocisti() {
      genT++; genP++; genZ++; kT = prekini(kT); kP = prekini(kP); kZ = prekini(kZ);
      ["ka-tim-lista", "ka-portfolio", "ka-zdravlje"].forEach(function (id) { $(id).replaceChildren(); });
      $("ka-firma").textContent = ""; $("ka-uloga").textContent = "";
      ["ka-tim-stanje", "ka-portfolio-stanje", "ka-zdravlje-stanje"].forEach(function (id) { stanje(id, null); });
      $("ka-zdravlje-dugme").disabled = false;
    }

    async function ucitajTim() {
      var moja = ++genT; kT = prekini(kT); kT = new AbortController();
      $("ka-tim-lista").replaceChildren(); $("ka-firma").textContent = ""; $("ka-uloga").textContent = "";
      stanje("ka-tim-stanje", "ucitavanje", "Učitavanje tima…");
      var r = await api.get("/api/kancelarija/moja", { token: sesija.token(), signal: kT.signal, oblik: function (x) { return typeof x.status === "string"; } });
      if (moja !== genT) return;
      kT = null;
      if (!r.ok) { if (r.greska && r.greska.kod === "ABORTED") return; stanje("ka-tim-stanje", "greska", greskaTekst(r.greska, "Tim kancelarije")); return; }
      var x = r.podaci;
      if (x.status === "no_firma") { stanje("ka-tim-stanje", "prazno", "Niste član nijedne kancelarije u Vindexu."); return; }
      if (x.status === "pending_invite") { stanje("ka-tim-stanje", "prazno", "Imate poziv u kancelariju „" + tekst(x.firma_naziv) + "“. Poziv prihvatate u klasičnom prikazu."); return; }
      if (x.status !== "aktivan" || !x.firma || !Array.isArray(x.clanovi)) { stanje("ka-tim-stanje", "greska", "Odgovor servera nije ispravan. Tim se ne prikazuje."); return; }
      stanje("ka-tim-stanje", null);
      $("ka-firma").textContent = tekst(x.firma.naziv) || "Kancelarija bez naziva";
      $("ka-uloga").textContent = "Vaša uloga: " + (x.moja_uloga === "admin" ? "administrator" : tekst(x.moja_uloga));
      if (!x.clanovi.length) { stanje("ka-tim-stanje", "prazno", "U kancelariji još nema drugih članova."); return; }
      x.clanovi.forEach(function (c) {
        var li = el("li", "people__item");
        li.append(el("span", "people__name", tekst(c.email)));
        li.append(el("span", "people__meta", [tekst(c.uloga_label) || tekst(c.uloga), STATUS_CLANA[tekst(c.status)] || tekst(c.status).toLowerCase()].filter(Boolean).join(" · ")));
        $("ka-tim-lista").append(li);
      });
    }

    function stavkaRoka(r) {
      var li = el("li", "chrono__item");
      var t = el("time", "chrono__date", datum(r.datum_iso) || "—");
      li.append(t);
      var a = el("a", "chrono__text", tekst(r.predmet_naziv) + (tekst(r.dogadjaj) ? " — " + tekst(r.dogadjaj) : ""));
      if (/^[A-Za-z0-9_-]{1,64}$/.test(tekst(r.predmet_id))) a.href = adresaPredmeta(tekst(r.predmet_id), "rad"); else a = el("span", "chrono__text", a.textContent);
      li.append(a);
      if (tekst(r.vaznost)) li.append(el("span", "chrono__meta", "važnost: " + tekst(r.vaznost)));
      return li;
    }

    async function ucitajPortfolio() {
      var moja = ++genP; kP = prekini(kP); kP = new AbortController();
      $("ka-portfolio").replaceChildren();
      stanje("ka-portfolio-stanje", "ucitavanje", "Učitavanje portfolija…");
      var r = await api.get("/portfolio/dashboard", { token: sesija.token(), signal: kP.signal,
        oblik: function (x) { return typeof x.ukupno_predmeta === "number" && Array.isArray(x.rokovi_14_dana) && Array.isArray(x.neaktivni_30_dana); } });
      if (moja !== genP) return;
      kP = null;
      if (!r.ok) { if (r.greska && r.greska.kod === "ABORTED") return; stanje("ka-portfolio-stanje", "greska", greskaTekst(r.greska, "Portfolio")); return; }
      stanje("ka-portfolio-stanje", null);
      var x = r.podaci, wrap = $("ka-portfolio");
      var dl = el("dl", "facts");
      [["Predmeta ukupno", x.ukupno_predmeta], ["Aktivnih", broj(x.ukupno_aktivnih)], ["Rokova u narednih 7 dana", Array.isArray(x.rokovi_7_dana) ? x.rokovi_7_dana.length : null],
       ["Kritičnih rokova u 7 dana", Array.isArray(x.hitni_rokovi) ? x.hitni_rokovi.length : null], ["Bez aktivnosti 30+ dana", x.neaktivni_30_dana.length]].forEach(function (p) {
        if (p[1] === null || p[1] === undefined) return;
        dl.append(el("dt", null, p[0]), el("dd", null, String(p[1])));
      });
      wrap.append(dl);
      wrap.append(el("h3", "answer__h", "Rokovi u narednih 14 dana"));
      if (!x.rokovi_14_dana.length) wrap.append(el("p", "list-state", "U narednih 14 dana nema upisanih rokova u vašim predmetima."));
      else { var ol = el("ol", "chrono"); x.rokovi_14_dana.forEach(function (r2) { ol.append(stavkaRoka(r2)); }); wrap.append(ol); }
      if (x.neaktivni_30_dana.length) {
        wrap.append(el("h3", "answer__h", "Predmeti bez aktivnosti 30+ dana"));
        var ul = el("ul", "people");
        x.neaktivni_30_dana.forEach(function (p) {
          var li = el("li", "people__item"), a = el("a", "people__name", tekst(p.naziv) || "Predmet bez naziva");
          if (/^[A-Za-z0-9_-]{1,64}$/.test(tekst(p.predmet_id))) a.href = adresaPredmeta(tekst(p.predmet_id), "pregled");
          li.append(a);
          if (tekst(p.poslednja_izmena)) li.append(el("span", "people__meta", "poslednja izmena " + datum(p.poslednja_izmena)));
          ul.append(li);
        });
        wrap.append(ul);
      }
    }

    async function izracunajZdravlje() {
      var moja = ++genZ; kZ = prekini(kZ); kZ = new AbortController();
      $("ka-zdravlje").replaceChildren(); $("ka-zdravlje-dugme").disabled = true;
      stanje("ka-zdravlje-stanje", "ucitavanje", "Izračunavanje indeksa…");
      var r = await api.get("/api/firm/health-index", { token: sesija.token(), signal: kZ.signal,
        oblik: function (x) { return typeof x.score === "number" && Array.isArray(x.components); } });
      if (moja !== genZ) return;
      kZ = null; $("ka-zdravlje-dugme").disabled = false;
      if (!r.ok) { if (r.greska && r.greska.kod === "ABORTED") return; stanje("ka-zdravlje-stanje", "greska", greskaTekst(r.greska, "Indeks zdravlja")); return; }
      stanje("ka-zdravlje-stanje", null);
      var x = r.podaci, wrap = $("ka-zdravlje");
      var vrh = el("p", "health__score");
      vrh.append(el("span", "health__value", String(Math.round(x.score))), el("span", "health__max", " / 100"));
      if (tekst(x.grade)) vrh.append(el("span", "health__grade", "  ocena " + tekst(x.grade)));
      wrap.append(vrh);
      var dl = el("dl", "facts");
      x.components.forEach(function (c) {
        if (!c || !tekst(c.label) || broj(c.score) === null || broj(c.max) === null) return;
        dl.append(el("dt", null, tekst(c.label)), el("dd", null, c.score + " od " + c.max));
      });
      wrap.append(dl);
      var meta = [broj(x.n_aktivni) !== null ? x.n_aktivni + " aktivnih" : "", broj(x.n_zatvoreni) !== null ? x.n_zatvoreni + " zatvorenih predmeta" : ""].filter(Boolean).join(", ");
      wrap.append(el("p", "field__help", "Ocena se računa programom iz podataka vaših predmeta" + (meta ? " (" + meta + ")" : "") + "." + (x.iz_kesa ? " Prikazan je rezultat izračunat u poslednjih sat vremena." : "")));
    }

    $("ka-zdravlje-dugme").addEventListener("click", izracunajZdravlje);
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) ocisti(); });

    return {
      otvori: function () { ocisti(); if (sesija.stanje().stanje !== sesija.STANJA.PRIJAVLJEN) { stanje("ka-tim-stanje", "greska", "Niste prijavljeni."); return; } ucitajTim(); ucitajPortfolio(); },
      zatvori: function () { genT++; genP++; genZ++; kT = prekini(kT); kP = prekini(kP); kZ = prekini(kZ); },
      zaustavi: function () { odjavi(); ocisti(); },
    };
  }

  root.VxKancelarija = Object.freeze({ napravi: napravi });
})(window);
