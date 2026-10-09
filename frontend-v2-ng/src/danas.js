/* Vindex V2 NG — DANAS: obaveze, odluka o predloženom roku, kalendar (NS005, CAP-070/075/081).
 *
 * Ugovori:
 *   GET  /api/rokovi/kandidati?od&dana → {rokovi[{id, predmet_id, dogadjaj, datum_iso, izvor, vrsta?, stanje?,
 *                                         stanje_odluke: UNCONFIRMED|CONFIRMED|REJECTED}], odseceno}; pad → 503
 *   GET  /api/kalendar/pregled?od&do   → {dogadjaji[{tip, datum, vreme, predmet_id, predmet_naziv, detalji}],
 *                                         degraded_sources[], truncated}
 *   POST /api/rokovi/{id}/potvrdi|odbij → {stanje_odluke}; tuđ rok 404; neuspeo upis 503 (rok ostaje nepotvrđen)
 * Pravila (preneta iz v2/domain/danas.js, FAZA 6.5 / migracija 129):
 *   • rok je SAMO red koji je izjavio `vrsta: "rok"` — po tekstu se ne pogađa; neizjavljen red nije ni obaveza ni predlog;
 *   • obaveza = potvrđen rok ili ročište; predlog (nepotvrđen) se nikad ne prikazuje kao obaveza ni u kalendaru;
 *   • odbijen / izvršen / otkazan rok ne traži pažnju; odbijanje NE briše (ostaje u hronologiji);
 *   • potvrda znači da je advokat rok video i prihvatio za upotrebu — NE da je sistem proverio tačnost;
 *   • nema „potvrdi sve"; odluka se nikad ne ponavlja automatski; prekid posle slanja = ishod nepoznat → ponovno čitanje.
 * Ekran NE tvrdi ništa o podsetnicima mejlom, SMS-u ni Viberu.
 */
(function (root) {
  "use strict";

  var DANA_UNAZAD = 90, DANA_UNAPRED = 30, DANA_OBAVEZE = 7;
  var IZ_ODLUKE = { CONFIRMED: "potvrdjen", REJECTED: "odbijen", UNCONFIRMED: "kandidat" };
  var STANJA = { kandidat: 1, potvrdjen: 1, odbijen: 1, izvrsen: 1, otkazan: 1 };
  var MESECI = ["januar", "februar", "mart", "april", "maj", "jun", "jul", "avgust", "septembar", "oktobar", "novembar", "decembar"];
  var DANI = ["nedelja", "ponedeljak", "utorak", "sreda", "četvrtak", "petak", "subota"];
  var GRUPE = [["propusteno", "Propušteno"], ["danas", "Danas"], ["sutra", "Sutra"], ["nedelja", "Narednih 7 dana"]];

  function tekst(v) { return String(v == null ? "" : v).trim(); }
  function bezUkrasa(t) { return tekst(t).replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{2B00}-\u{2BFF}]/gu, "").replace(/\s{2,}/g, " ").trim(); }
  function iso(d) { return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
  function pomeraj(n) { var d = new Date(); d.setDate(d.getDate() + n); return iso(d); }
  function uDan(s) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(tekst(s)); return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null; }
  function razlika(s) { var d = uDan(s); if (!d) return null; var n = new Date(); return Math.round((d - new Date(n.getFullYear(), n.getMonth(), n.getDate())) / 86400000); }
  function datumTekst(s) { var d = uDan(s); return d ? String(d.getDate()).padStart(2, "0") + "." + String(d.getMonth() + 1).padStart(2, "0") + "." + d.getFullYear() + "." : "—"; }
  function danTekst(s) { var d = uDan(s); return d ? DANI[d.getDay()] + ", " + datumTekst(s) : tekst(s); }
  function mesecTekst(s) { var d = uDan(s); return d ? MESECI[d.getMonth()] + " " + d.getFullYear() : ""; }
  function kadaTekst(r) { if (r === null) return ""; if (r === 0) return "danas"; if (r === 1) return "sutra"; if (r === -1) return "juče"; return r < 0 ? "pre " + (-r) + " dana" : "za " + r + " dana"; }
  function grupa(r) { if (r === null) return null; if (r < 0) return "propusteno"; if (r === 0) return "danas"; if (r === 1) return "sutra"; return r <= DANA_OBAVEZE ? "nedelja" : null; }
  function jeRok(red) { return tekst(red && red.vrsta).toLowerCase() === "rok"; }
  /* `izvrsen`/`otkazan` samo iz kolone; potvrda/odbijanje iz audit lanca; kolona za ostalo tek ako odluke nema. */
  function stanjeZapisa(red) {
    var s = tekst(red && red.stanje).toLowerCase();
    if (s === "izvrsen" || s === "otkazan") return s;
    var o = IZ_ODLUKE[tekst(red && red.stanje_odluke).toUpperCase()];
    if (o && o !== "kandidat") return o;
    if (STANJA[s]) return s;
    return o || null;
  }
  function ispravanId(v) { return /^[A-Za-z0-9_-]{1,64}$/.test(tekst(v)); }

  /* Čist sastav (bez DOM-a): ista pravila kao v2/domain/danas.js::sastavi + sastaviKalendar. */
  function sastavi(kand, kal, nazivIzRegistra) {
    var dog = kal && Array.isArray(kal.dogadjaji) ? kal.dogadjaji : [];
    var imena = {};
    dog.forEach(function (e) { if (e && e.predmet_id && e.predmet_naziv) imena[e.predmet_id] = tekst(e.predmet_naziv); });
    var redovi = kand && Array.isArray(kand.rokovi) ? kand.rokovi : [];
    var rokovi = redovi.filter(jeRok);
    /* Obaveza i predlog se biraju POZITIVNO (samo `potvrdjen`, samo `kandidat`), pa odbijen / izvršen /
     * otkazan rok ne može ući ni u jednu listu — poseban filter „razrešenih“ bi bio mrtav kod. */
    var aktivni = rokovi;
    function stavka(r, vrsta) {
      var dat = tekst(r.datum_iso || r.datum);
      return { vrsta: vrsta, id: tekst(r.id), opis: bezUkrasa(r.dogadjaj) || (vrsta === "predlog" ? "Predlog bez opisa" : "Rok bez opisa"),
        predmetId: tekst(r.predmet_id), predmet: imena[r.predmet_id] || (nazivIzRegistra ? tekst(nazivIzRegistra(tekst(r.predmet_id))) : ""), vreme: "", datumIso: dat, razlika: razlika(dat), izvor: tekst(r.izvor) };
    }
    var potvrdjeni = aktivni.filter(function (r) { return stanjeZapisa(r) === "potvrdjen"; }).map(function (r) { return stavka(r, "rok"); });
    var rocista = dog.filter(function (e) { return e && e.tip === "rociste"; }).map(function (e) {
      var d = e.detalji || {}, dat = tekst(e.datum);
      return { vrsta: "rociste", id: tekst(d.id), opis: [tekst(d.sud), tekst(d.sudnica)].filter(Boolean).join(", ") || "Ročište",
        predmetId: tekst(e.predmet_id), predmet: tekst(e.predmet_naziv), vreme: tekst(e.vreme), datumIso: dat, razlika: razlika(dat) };
    });
    var poDatumu = function (a, b) { return a.datumIso === b.datumIso ? (a.vreme || "").localeCompare(b.vreme || "") : (a.datumIso < b.datumIso ? -1 : 1); };
    var sve = potvrdjeni.concat(rocista).filter(function (x) { return x.razlika !== null; }).sort(poDatumu);
    var predlozi = aktivni.filter(function (r) { return stanjeZapisa(r) === "kandidat"; }).map(function (r) { return stavka(r, "predlog"); })
      .filter(function (x) { return x.razlika !== null; }).sort(poDatumu);
    return {
      grupe: GRUPE.map(function (g) { return { kljuc: g[0], naziv: g[1], stavke: sve.filter(function (x) { return grupa(x.razlika) === g[0]; }) }; })
        .filter(function (g) { return g.stavke.length; }),
      kalendar: sve.filter(function (x) { return x.razlika >= 0; }),
      predlozi: predlozi,
      neizjavljeno: redovi.length - rokovi.length,
    };
  }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api, adresaPredmeta = o.adresaPredmeta, nazivPredmeta = o.nazivPredmeta || null;
    var gen = 0, k1 = null, k2 = null, otvoren = false, korisnik = null;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function stanje(id, st, t) { var n = $(id); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function prekini(x) { if (x) x.abort(); return null; }
    function ocisti() {
      gen++; k1 = prekini(k1); k2 = prekini(k2); korisnik = null;
      ["da-obaveze", "da-predlozi", "da-kalendar"].forEach(function (id) { $(id).replaceChildren(); });
      ["da-stanje", "da-obaveze-stanje", "da-predlozi-stanje", "da-kalendar-stanje", "da-napomena", "da-poruka"].forEach(function (id) { stanje(id, null); });
    }

    function vezaPredmeta(x, odeljak) {
      var naziv = x.predmet || "Predmet";
      if (!ispravanId(x.predmetId)) return el("span", "today__case", naziv);
      var a = el("a", "today__case", naziv); a.href = adresaPredmeta(x.predmetId, odeljak); return a;
    }
    function redObaveze(x) {
      var li = el("li", "today__item");
      li.dataset.vrsta = x.vrsta;
      li.append(el("span", "today__when", datumTekst(x.datumIso) + (x.vreme ? " u " + x.vreme : "") + " · " + kadaTekst(x.razlika)));
      li.append(el("span", "today__kind", x.vrsta === "rociste" ? "Ročište" : "Rok"));
      li.append(el("span", "today__what", x.opis));
      li.append(vezaPredmeta(x, "rad"));
      return li;
    }

    function redPredloga(x, moja) {
      var li = el("li", "review");
      li.dataset.rok = x.id;
      var naziv = el("span", "review__name", x.opis);
      li.append(naziv);
      li.append(el("span", "review__meta", [datumTekst(x.datumIso) + " · " + kadaTekst(x.razlika), x.predmet || "", x.izvor === "ai" ? "predložio sistem" : ""].filter(Boolean).join(" · ")));
      var akcije = el("span", "review__actions");
      var da = el("button", "text-btn text-btn--line", "Potvrdi"); da.type = "button"; da.setAttribute("aria-label", "Potvrdi rok: " + x.opis);
      var ne = el("button", "text-btn", "Odbij"); ne.type = "button"; ne.setAttribute("aria-label", "Odbij rok: " + x.opis);
      var st = el("span", "review__meta"); st.setAttribute("role", "status"); st.hidden = true;
      akcije.append(da, ne, st); li.append(akcije);
      if (ispravanId(x.predmetId)) { var a = el("a", "review__meta", "Otvori predmet"); a.href = adresaPredmeta(x.predmetId, "rad"); li.append(a); }
      var radi = false;
      async function odluci(radnja) {
        if (radi || moja !== gen || !ispravanId(x.id)) return;
        var s = sesija.stanje();
        if (s.stanje !== sesija.STANJA.PRIJAVLJEN || s.korisnik !== korisnik) { st.hidden = false; st.textContent = "Niste prijavljeni. Ništa nije zabeleženo."; return; }
        radi = true; da.disabled = true; ne.disabled = true; st.hidden = false; st.textContent = "Beleži se…";
        var r = await api.send("/api/rokovi/" + encodeURIComponent(x.id) + "/" + radnja, { telo: {}, token: sesija.token(),
          oblik: function (y) { return typeof y.stanje_odluke === "string"; } });
        if (moja !== gen) return;
        radi = false;
        if (r.ok) {
          var potvrdjeno = radnja === "potvrdi";
          stanje("da-poruka", "uspeh", potvrdjeno ? "Rok „" + x.opis + "“ je potvrđen: preuzeli ste ga za upotrebu. Potvrda ne znači da je sistem proverio njegovu tačnost."
            : "Rok „" + x.opis + "“ je odbijen. Ne briše se — ostaje u hronologiji predmeta.");
          ucitaj();
          return;
        }
        var g = r.greska || {};
        if (g.ishodNepoznat) { stanje("da-poruka", "nepoznato", "Ishod odluke za rok „" + x.opis + "“ nije poznat: veza je prekinuta ili server nije odgovorio ispravno. Spisak se ponovo učitava — proverite stanje pre ponovnog pokušaja."); ucitaj(); return; }
        da.disabled = false; ne.disabled = false;
        st.textContent = g.kod === "NOT_FOUND" ? "Rok nije dostupan. Ništa nije zabeleženo."
          : g.kod === "AUTH_REQUIRED" ? "Prijava više nije važeća. Ništa nije zabeleženo."
          : g.kod === "RATE_LIMITED" ? "Previše zahteva. Pokušajte malo kasnije. Ništa nije zabeleženo."
          : "Server je odbio zahtev. Ništa nije zabeleženo; rok ostaje nepotvrđen.";
      }
      da.addEventListener("click", function () { odluci("potvrdi"); });
      ne.addEventListener("click", function () { odluci("odbij"); });
      return li;
    }

    async function ucitaj() {
      var s = sesija.stanje();
      var moja = ++gen; k1 = prekini(k1); k2 = prekini(k2);
      korisnik = s.korisnik;
      if (s.stanje !== sesija.STANJA.PRIJAVLJEN) { stanje("da-stanje", "greska", "Niste prijavljeni."); return; }
      k1 = new AbortController(); k2 = new AbortController();
      stanje("da-stanje", "ucitavanje", "Učitavanje obaveza i rokova…");
      var od = pomeraj(-DANA_UNAZAD), t = sesija.token();
      var rez = await Promise.all([
        api.get("/api/rokovi/kandidati", { token: t, signal: k1.signal, parametri: { od: od, dana: DANA_UNAPRED }, oblik: function (x) { return Array.isArray(x.rokovi); } }),
        api.get("/api/kalendar/pregled", { token: t, signal: k2.signal, parametri: { od: od, "do": pomeraj(DANA_UNAPRED) }, oblik: function (x) { return Array.isArray(x.dogadjaji); } }),
      ]);
      if (moja !== gen || sesija.stanje().korisnik !== korisnik) return;
      k1 = null; k2 = null;
      var rk = rez[0], rc = rez[1];
      if ((!rk.ok && rk.greska && rk.greska.kod === "ABORTED") || (!rc.ok && rc.greska && rc.greska.kod === "ABORTED")) return;
      ["da-obaveze", "da-predlozi", "da-kalendar"].forEach(function (id) { $(id).replaceChildren(); });
      if (!rk.ok && !rc.ok) {
        stanje("da-stanje", "greska", rk.greska && rk.greska.kod === "AUTH_REQUIRED" ? "Prijava više nije važeća. Obaveze se ne prikazuju." : "Obaveze i rokovi nisu učitani zbog greške. Ovo nije prazan dan.");
        ["da-obaveze-stanje", "da-predlozi-stanje", "da-kalendar-stanje"].forEach(function (id) { stanje(id, null); });
        return;
      }
      var kal = rc.ok ? rc.podaci : null, kand = rk.ok ? rk.podaci : null;
      var x = sastavi(kand, kal, nazivPredmeta);
      var nepotpuno = [];
      if (!rk.ok) nepotpuno.push("rokovi nisu učitani");
      if (!rc.ok) nepotpuno.push("ročišta nisu učitana");
      if (kal && Array.isArray(kal.degraded_sources) && kal.degraded_sources.indexOf("rocista") !== -1) nepotpuno.push("ročišta nisu učitana");
      if (kal && Array.isArray(kal.degraded_sources) && kal.degraded_sources.indexOf("predmeti") !== -1) nepotpuno.push("nazivi predmeta nisu učitani");
      if (kand && kand.odseceno) nepotpuno.push("rokova ima više nego što je prikazano");
      if (kal && kal.truncated) nepotpuno.push("ročišta ima više nego što je prikazano");
      nepotpuno = nepotpuno.filter(function (v, i, a) { return a.indexOf(v) === i; });
      stanje("da-stanje", nepotpuno.length ? "nepotpuno" : null, nepotpuno.length ? "Pregled NIJE potpun: " + nepotpuno.join("; ") + "." : "");

      // Obaveze (7 dana i propušteno)
      if (!rk.ok && !x.grupe.length) stanje("da-obaveze-stanje", "greska", "Rokovi nisu učitani; ovde mogu nedostajati obaveze.");
      else if (!x.grupe.length) stanje("da-obaveze-stanje", "prazno", nepotpuno.length ? "U učitanim podacima nema obaveza za narednih 7 dana." : "Nema potvrđenih rokova ni ročišta za narednih 7 dana, niti propuštenih u poslednjih 90 dana.");
      else stanje("da-obaveze-stanje", null);
      x.grupe.forEach(function (g) {
        var sek = el("section", "today__group");
        sek.append(el("h3", "answer__h", g.naziv + " (" + g.stavke.length + ")"));
        var ul = el("ul", "today__list");
        g.stavke.forEach(function (s2) { ul.append(redObaveze(s2)); });
        sek.append(ul); $("da-obaveze").append(sek);
      });

      // Predlozi za odluku
      if (!rk.ok) stanje("da-predlozi-stanje", "greska", "Predloženi rokovi nisu učitani zbog greške. Ovo nije prazan spisak.");
      else if (!x.predlozi.length) stanje("da-predlozi-stanje", "prazno", "Nema predloženih rokova koji čekaju vašu odluku.");
      else stanje("da-predlozi-stanje", null);
      x.predlozi.forEach(function (p) { $("da-predlozi").append(redPredloga(p, moja)); });
      if (x.neizjavljeno > 0) stanje("da-napomena", "prazno", x.neizjavljeno + (x.neizjavljeno === 1 ? " zapis hronologije nema" : " zapisa hronologije nema") + " oznaku da je rok, pa se ovde ne prikazuje ni kao obaveza ni kao predlog. Vidite ih u hronologiji predmeta.");

      // Kalendar 30 dana: samo potvrđeni rokovi i ročišta, grupisano po mesecu i danu
      if (!x.kalendar.length) stanje("da-kalendar-stanje", nepotpuno.length ? "nepotpuno" : "prazno", nepotpuno.length ? "U učitanim podacima nema termina u narednih 30 dana." : "Nema potvrđenih rokova ni ročišta u narednih 30 dana.");
      else stanje("da-kalendar-stanje", null);
      var mesec = "", dan = "", ul2 = null;
      x.kalendar.forEach(function (s3) {
        var m = mesecTekst(s3.datumIso);
        if (m !== mesec) { mesec = m; $("da-kalendar").append(el("h3", "answer__h", m)); }
        if (s3.datumIso !== dan) { dan = s3.datumIso; $("da-kalendar").append(el("p", "today__day", danTekst(s3.datumIso))); ul2 = el("ul", "today__list"); $("da-kalendar").append(ul2); }
        ul2.append(redObaveze(s3));
      });
      if (x.predlozi.length) $("da-kalendar").append(el("p", "field__help", "Predloženi rokovi koji čekaju odluku (" + x.predlozi.length + ") nisu u kalendaru dok ih ne potvrdite."));
    }

    var odjavi = sesija.naPromenu(function (novo, staro) {
      if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) { ocisti(); if (otvoren && novo.stanje === sesija.STANJA.PRIJAVLJEN) ucitaj(); }
    });

    return {
      otvori: function () { otvoren = true; ocisti(); ucitaj(); },
      zatvori: function () { otvoren = false; gen++; k1 = prekini(k1); k2 = prekini(k2); },
      zaustavi: function () { odjavi(); ocisti(); },
    };
  }

  root.VxDanas = Object.freeze({ napravi: napravi, _sastavi: sastavi });
})(window);
