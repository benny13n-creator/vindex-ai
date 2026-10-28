/* Vindex V2 NG — ročišta predmeta (NS005, CAP-074; N3 stanja i predlozi iz dokumenata).
 *
 * Ugovori (routers/rocista.py):
 *   GET  /api/rocista?predmet_id=  → {rocista, ukupno}  (samo pozivaočeva; po datumu)
 *   POST /api/rocista {predmet_id, sud, datum YYYY-MM-DD, vreme HH:MM?, sudnica?,
 *                      broj_predmeta_suda?, napomena?} → {rociste}
 *        server proverava da je predmet pozivaočev (inače 404); isto ročište u 30 s
 *        se ne duplira. Status novog ročišta je uvek „zakazano".
 *   PATCH /api/rocista/{id} {status, if_updated_at?} → {rociste}; 409 = izmenjeno u međuvremenu
 *   GET  /api/rocista/predlozi?predmet_id= → {predlozi[{kljuc, datum, vreme, sud, sudnica, broj_predmeta_suda,
 *        izvori[{dokument_id, naziv, citat}]}], dokumenata_bez_teksta, proslih}  (ništa ne upisuje)
 *   POST /api/rocista/predlozi/odbaci {predmet_id, kljuc} → {ok}
 * N3: „Odloženo" ne briše ni ne pomera staro ročište — ono ostaje kao istorija, a novo se zakazuje (forma sa
 * istim sudom i brojem). Predlog iz dokumenta NIJE ročište: forma se popunjava, advokat proverava i zakazuje.
 * Brisanje ročišta nije deo V2. Podsetnici se ne šalju odavde. Neuspelo čitanje liste NIJE „nema ročišta".
 */
(function (root) {
  "use strict";

  var STATUS = { zakazano: "zakazano", odrzano: "održano", odlozeno: "odloženo", otkazano: "otkazano" };
  var AKCIJE = [["odrzano", "Održano"], ["odlozeno", "Odloženo"], ["otkazano", "Otkazano"]];
  var PORUKA_STATUSA = { odrzano: "Ročište je označeno kao održano.", otkazano: "Ročište je označeno kao otkazano.",
    zakazano: "Ročište je ponovo zakazano.", odlozeno: "Ročište je označeno kao odloženo. Unesite novi datum i zakažite nastavak." };
  function datum(iso) { var p = String(iso || "").slice(0, 10).split("-"); return p.length === 3 ? p[2] + "." + p[1] + "." + p[0] + "." : String(iso || ""); }
  function tekst(v) { return typeof v === "string" ? v.trim() : ""; }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api;
    var trenutni = null, genListe = 0, genUpisa = 0, genPredloga = 0, kListe = null, kUpisa = null, salje = false, ucitano = false, menja = false;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function poruka(stanje, t) { var n = $("roc-poruka"); if (!stanje) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = stanje; n.textContent = t; }
    function stanjeListe(t, oznaka) { var s = $("roc-stanje"); s.hidden = !t; s.textContent = t || ""; if (oznaka) s.dataset.stanje = oznaka; else delete s.dataset.stanje; }
    function stanjePredloga(t, oznaka) { var s = $("roc-predlozi-stanje"); s.hidden = !t; s.textContent = t || ""; if (oznaka) s.dataset.stanje = oznaka; else delete s.dataset.stanje; }
    function zakljucaj(da) { salje = da; $("roc-sacuvaj").disabled = da; $("roc-sacuvaj").textContent = da ? "Zakazivanje…" : "Zakaži ročište"; }
    function aktuelan(id, korisnik) { return !!trenutni && trenutni.id === id && trenutni.korisnik === korisnik; }
    function prijavljenKao(korisnik) { var s = sesija.stanje(); return s.stanje === sesija.STANJA.PRIJAVLJEN && s.korisnik === korisnik; }

    function ocisti() {
      genListe++; genUpisa++; genPredloga++;
      if (kListe) { kListe.abort(); kListe = null; }
      if (kUpisa) { kUpisa.abort(); kUpisa = null; }
      trenutni = null; ucitano = false; menja = false;
      zakljucaj(false);
      $("roc-lista").replaceChildren(); stanjeListe(null); poruka(null);
      $("roc-predlozi").replaceChildren(); stanjePredloga(null); $("roc-predlozi-naslov").hidden = true;
      $("roc-forma").reset(); $("roc-forma").hidden = true; $("roc-otvori").hidden = true;
    }

    function otvoriFormu(polja) {
      $("roc-forma").reset();
      Object.keys(polja || {}).forEach(function (k) { if (polja[k]) $(k).value = polja[k]; });
      $("roc-forma").hidden = false; $("roc-otvori").hidden = true;
      $(polja && polja["roc-datum"] ? "roc-sud" : (polja && polja["roc-sud"] ? "roc-datum" : "roc-sud")).focus();
    }

    async function ucitaj(porukaPosle) {
      if (!trenutni) return;
      genListe++;
      if (kListe) kListe.abort();
      var moja = genListe, id = trenutni.id, korisnik = trenutni.korisnik;
      kListe = new AbortController();
      $("roc-lista").replaceChildren();
      stanjeListe("Učitavanje ročišta…", "ucitavanje");
      var r = await api.get("/api/rocista", { token: sesija.token(), signal: kListe.signal, parametri: { predmet_id: id, limit: 100 },
        oblik: function (x) { return Array.isArray(x.rocista); } });
      if (moja !== genListe || !aktuelan(id, korisnik)) return;
      kListe = null;
      if (!r.ok) {
        if (r.greska && r.greska.kod === "ABORTED") return;
        stanjeListe("Ročišta nisu učitana zbog greške. Ovo nije prazna lista.", "greska");
        return;
      }
      /* Server filtrira po vlasniku i predmetu; red drugog predmeta je neispravan odgovor. */
      var lista = r.podaci.rocista.filter(function (x) { return x && typeof x === "object"; });
      if (lista.some(function (x) { return x.predmet_id !== undefined && String(x.predmet_id) !== id; })) {
        stanjeListe("Odgovor servera nije ispravan. Ročišta se ne prikazuju.", "greska");
        return;
      }
      if (!lista.length) stanjeListe("Za predmet nije zakazano nijedno ročište.", "prazno");
      else stanjeListe(null);
      lista.forEach(function (x) { $("roc-lista").append(redRocista(x)); });
      if (porukaPosle) poruka("uspeh", porukaPosle);
      ucitajPredloge();
    }

    function redRocista(x) {
      var li = el("li", "hearing");
      var kad = el("time", "hearing__when", datum(x.datum) + (tekst(x.vreme) ? " u " + tekst(x.vreme).slice(0, 5) : ""));
      if (/^\d{4}-\d{2}-\d{2}/.test(tekst(x.datum))) kad.dateTime = tekst(x.datum).slice(0, 10);
      li.append(kad);
      li.append(el("span", "hearing__court", tekst(x.sud) || "Sud nije naveden"));
      var st = tekst(x.status) || "zakazano";
      var meta = [tekst(x.sudnica) ? "sudnica " + tekst(x.sudnica) : "", tekst(x.broj_predmeta_suda), STATUS[st] || st].filter(Boolean).join(" · ");
      if (meta) li.append(el("span", "hearing__meta", meta));
      if (tekst(x.napomena)) li.append(el("span", "hearing__note", tekst(x.napomena)));
      if (typeof x.id === "string" || typeof x.id === "number") {
        var akcije = el("span", "hearing__meta review__actions");
        (st === "zakazano" ? AKCIJE : [["zakazano", "Vrati na zakazano"]]).forEach(function (a) {
          var b = el("button", "text-btn", a[1]); b.type = "button";
          b.setAttribute("aria-label", a[1] + ": ročište " + datum(x.datum));
          b.addEventListener("click", function () { promeniStatus(x, a[0]); });
          akcije.append(b);
        });
        li.append(akcije);
      }
      return li;
    }

    /* Stanje ročišta: jedan PATCH, uz `if_updated_at` kad ga server daje — zastareo prikaz ne prepisuje novije stanje. */
    async function promeniStatus(x, novo) {
      if (menja || salje || !trenutni) return;
      var id = trenutni.id, korisnik = trenutni.korisnik;
      if (!prijavljenKao(korisnik)) { poruka("greska", "Niste prijavljeni. Stanje ročišta nije promenjeno."); return; }
      menja = true;
      d.querySelectorAll("#roc-lista button").forEach(function (b) { b.disabled = true; });
      poruka("ucitavanje", "Beleži se…");
      var telo = { status: novo };
      if (tekst(x.updated_at)) telo.if_updated_at = tekst(x.updated_at);
      var r = await api.send("/api/rocista/" + encodeURIComponent(String(x.id)), { metod: "PATCH", telo: telo, token: sesija.token(),
        oblik: function (y) { return y.rociste && typeof y.rociste === "object"; } });
      if (!aktuelan(id, korisnik)) return;
      menja = false;
      if (r.ok && r.podaci && tekst(r.podaci.rociste.status) === novo) {
        await ucitaj(PORUKA_STATUSA[novo]);
        if (novo === "odlozeno" && aktuelan(id, korisnik)) {
          otvoriFormu({ "roc-sud": tekst(x.sud), "roc-sudnica": tekst(x.sudnica), "roc-broj": tekst(x.broj_predmeta_suda),
            "roc-napomena": "Nastavak odloženog ročišta od " + datum(x.datum) });
          poruka("uspeh", PORUKA_STATUSA.odlozeno);
        }
        return;
      }
      var g = r.greska || {};
      await ucitaj();
      if (!aktuelan(id, korisnik)) return;
      poruka(g.ishodNepoznat || r.ok ? "nepoznato" : "greska",
        (r.status === 409 || g.kod === "CONFLICT") && novo === "zakazano"
          ? "Ročište nije vraćeno: predmet već ima zakazano kasnije ročište (verovatno nastavak) ili je ročište izmenjeno u međuvremenu. Lista je osvežena — ako treba, prvo otkažite nastavak."
          : r.status === 409 || g.kod === "CONFLICT" ? "Ročište je izmenjeno u međuvremenu (npr. u drugom prozoru). Ništa nije prepisano — lista je osvežena, proverite stanje."
          : g.ishodNepoznat || r.ok ? "Ishod nije poznat: stanje je možda promenjeno. Lista je osvežena — proverite pre ponovnog pokušaja."
          : g.kod === "NOT_FOUND" ? "Ročište nije pronađeno. Stanje nije promenjeno." : "Server je odbio izmenu. Stanje ročišta nije promenjeno.");
    }

    async function ucitajPredloge() {
      if (!trenutni) return;
      var moja = ++genPredloga, id = trenutni.id, korisnik = trenutni.korisnik;
      var r = await api.get("/api/rocista/predlozi", { token: sesija.token(), parametri: { predmet_id: id },
        oblik: function (x) { return Array.isArray(x.predlozi); } });
      if (moja !== genPredloga || !aktuelan(id, korisnik)) return;
      $("roc-predlozi").replaceChildren();
      if (!r.ok) {
        if (r.greska && r.greska.kod === "ABORTED") return;
        $("roc-predlozi-naslov").hidden = false;
        stanjePredloga("Predlozi ročišta iz dokumenata nisu učitani. Ovo ne znači da ih nema.", "greska");
        return;
      }
      var lista = r.podaci.predlozi.filter(function (p) { return p && /^\d{4}-\d{2}-\d{2}$/.test(tekst(p.datum)) && tekst(p.kljuc); });
      var bez = Number(r.podaci.dokumenata_bez_teksta) || 0;
      $("roc-predlozi-naslov").hidden = !lista.length && !bez;
      stanjePredloga(bez ? (bez === 1 ? "1 dokument predmeta je bez čitljivog teksta" : bez + " dokumenata predmeta je bez čitljivog teksta")
        + " — iz njega se ročište ne može predložiti. Proverite ga sami." : null, bez ? "nepotpuno" : null);
      lista.forEach(function (p) { $("roc-predlozi").append(redPredloga(p)); });
    }

    function redPredloga(p) {
      var li = el("li", "review");
      li.append(el("span", "review__name", datum(p.datum) + (tekst(p.vreme) ? " u " + tekst(p.vreme) : "") + " · " + (tekst(p.sud) || "sud nije pročitan")
        + (tekst(p.sudnica) ? " · sudnica " + tekst(p.sudnica) : "")));
      li.append(el("span", "review__meta", "Predlog iz dokumenta — nije zakazano dok ga ne zakažete. Proverite datum u dokumentu."));
      (Array.isArray(p.izvori) ? p.izvori : []).forEach(function (iz) {
        li.append(el("span", "review__meta", "„" + tekst(iz && iz.naziv) + "“: " + tekst(iz && iz.citat)));
      });
      var akcije = el("span", "review__actions");
      var da = el("button", "text-btn text-btn--line", "Proveri i zakaži"); da.type = "button";
      var ne = el("button", "text-btn", "Odbaci"); ne.type = "button";
      var st = el("span", "review__meta"); st.setAttribute("role", "status"); st.hidden = true;
      da.addEventListener("click", function () {
        var izvor = (p.izvori || [])[0] || {};
        otvoriFormu({ "roc-sud": tekst(p.sud), "roc-datum": tekst(p.datum), "roc-vreme": tekst(p.vreme), "roc-sudnica": tekst(p.sudnica),
          "roc-broj": tekst(p.broj_predmeta_suda), "roc-napomena": ("Iz dokumenta „" + tekst(izvor.naziv) + "“: " + tekst(izvor.citat)).slice(0, 2000) });
        poruka("ucitavanje", "Proverite podatke prema dokumentu pre zakazivanja. Ništa još nije upisano.");
      });
      var radi = false;
      ne.addEventListener("click", async function () {
        if (radi || !trenutni) return;
        var id = trenutni.id, korisnik = trenutni.korisnik;
        if (!prijavljenKao(korisnik)) { st.hidden = false; st.textContent = "Niste prijavljeni. Ništa nije zabeleženo."; return; }
        radi = true; da.disabled = true; ne.disabled = true; st.hidden = false; st.textContent = "Beleži se…";
        var r = await api.send("/api/rocista/predlozi/odbaci", { telo: { predmet_id: id, kljuc: tekst(p.kljuc) }, token: sesija.token(),
          oblik: function (y) { return y.ok === true; } });
        if (!aktuelan(id, korisnik)) return;
        radi = false;
        if (r.ok) { ucitajPredloge(); return; }
        da.disabled = false; ne.disabled = false;
        st.textContent = (r.greska || {}).ishodNepoznat ? "Ishod nije poznat — predlog je možda odbačen. Osvežite predmet." : "Odbacivanje nije zabeleženo. Predlog ostaje.";
      });
      akcije.append(da, ne, st); li.append(akcije);
      return li;
    }

    /* Lista se čita tek kada je odeljak „Rad na predmetu" otvoren (aktiviraj):
     * pregled i dokumenti ne izazivaju dodatni zahtev. */
    function postavi(predmet, aktivan) {
      ocisti();
      trenutni = { id: predmet.id, korisnik: sesija.stanje().korisnik };
      $("roc-otvori").hidden = false;
      if (aktivan) aktiviraj();
    }
    function aktiviraj() {
      if (!trenutni || ucitano) return;
      ucitano = true;
      ucitaj();
    }

    async function zakazi() {
      if (salje || !trenutni) return;
      var s = sesija.stanje();
      if (s.stanje !== sesija.STANJA.PRIJAVLJEN || s.korisnik !== trenutni.korisnik) { poruka("greska", "Niste prijavljeni. Ročište nije zakazano."); return; }
      ["roc-sud", "roc-datum", "roc-vreme"].forEach(function (x) { $(x).removeAttribute("aria-invalid"); });
      var sud = $("roc-sud").value.trim(), dat = $("roc-datum").value.trim(), vreme = $("roc-vreme").value.trim();
      if (!sud) { $("roc-sud").setAttribute("aria-invalid", "true"); poruka("greska", "Unesite sud."); $("roc-sud").focus(); return; }
      if (!/^\d{4}-\d{2}-\d{2}$/.test(dat)) { $("roc-datum").setAttribute("aria-invalid", "true"); poruka("greska", "Unesite datum ročišta."); $("roc-datum").focus(); return; }
      if (vreme && !/^\d{2}:\d{2}$/.test(vreme)) { $("roc-vreme").setAttribute("aria-invalid", "true"); poruka("greska", "Vreme mora biti u obliku ČČ:MM."); $("roc-vreme").focus(); return; }
      var telo = { predmet_id: trenutni.id, sud: sud.slice(0, 300), datum: dat };
      if (vreme) telo.vreme = vreme;
      [["sudnica", "roc-sudnica", 100], ["broj_predmeta_suda", "roc-broj", 100], ["napomena", "roc-napomena", 2000]].forEach(function (f) {
        var v = $(f[1]).value.trim(); if (v) telo[f[0]] = v.slice(0, f[2]);
      });
      var moja = ++genUpisa, id = trenutni.id, korisnik = trenutni.korisnik;
      kUpisa = new AbortController();
      zakljucaj(true);
      poruka("ucitavanje", "Ročište se zakazuje…");
      var r = await api.send("/api/rocista", { telo: telo, token: sesija.token(), signal: kUpisa.signal,
        oblik: function (x) { return x.rociste && typeof x.rociste === "object"; } });
      if (moja !== genUpisa || !trenutni || trenutni.id !== id || trenutni.korisnik !== korisnik) return;
      kUpisa = null;
      zakljucaj(false);
      if (r.ok) {
        $("roc-forma").reset(); $("roc-forma").hidden = true; $("roc-otvori").hidden = false;
        poruka(null);
        ucitaj(r.podaci ? "Ročište je zakazano." : "Ročište je verovatno zakazano, ali odgovor nije mogao da se pročita. Proverite listu.");
        return;
      }
      var g = r.greska || {};
      if (g.ishodNepoznat) { poruka("nepoznato", "Ishod nije poznat: ročište je možda zakazano. Osvežite predmet i proverite listu pre ponovnog pokušaja."); return; }
      poruka("greska", { NOT_FOUND: "Predmet nije dostupan. Ročište nije zakazano.", VALIDATION_ERROR: "Server nije prihvatio podatke (proverite datum i vreme). Ročište nije zakazano.",
        AUTH_REQUIRED: "Prijava više nije važeća. Ročište nije zakazano.", RATE_LIMITED: "Previše zahteva. Ročište nije zakazano." }[g.kod] || "Server je odbio zahtev. Ročište nije zakazano.");
    }

    $("roc-otvori").addEventListener("click", function () { if (!trenutni) return; poruka(null); otvoriFormu(null); });
    $("roc-odustani").addEventListener("click", function () { if (salje) return; $("roc-forma").reset(); $("roc-forma").hidden = true; $("roc-otvori").hidden = !trenutni; poruka(null); });
    $("roc-forma").addEventListener("submit", function (e) { e.preventDefault(); zakazi(); });
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) ocisti(); });

    return { postavi: postavi, aktiviraj: aktiviraj, ocisti: ocisti, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxRocistaPredmeta = Object.freeze({ napravi: napravi });
})(window);
