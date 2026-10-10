/* Vindex V2 NG — „VINDEX JE PRIPREMIO" (NS007, Task 15–16).
 *
 * Rad koji je Vindex SAM pripremio (autonomy_work_items, READY_FOR_REVIEW) — lista (Danas, Pregled predmeta) i
 * pregled jednog proizvoda (`#/pripremljeno/<id>`) sa odlukom advokata.
 *   lista   ← GET /api/workspace (Danas, isti zahtev kao radna lista) ili GET /api/autonomy/work-items?matter_id=
 *   detalj  ← GET /api/autonomy/work-items/{id}
 *   odluka  ← POST …/{id}/accept | …/{id}/reject  (VxApi.send: Idempotency-Key; „ishod nepoznat" se poštuje)
 * Prihvatanje je SAMO odluka o pregledu: ništa se ne šalje, ne podnosi i ne menja u predmetu — tako i piše na ekranu.
 * Svaka stavka nosi poreklo (iz dokumenta / uneo advokat / analiza AI); AI deo nikad nije „utvrđena činjenica".
 * Nema modela pri otvaranju. Sav tekst ide kao tekst (textContent).
 */
(function (root) {
  "use strict";

  var TIP = { HEARING_PREP: "Priprema za ročište", PRECEDENT_IMPACT: "Nova praksa — analiza uticaja", CASE_CHANGE_BRIEF: "Promena predmeta" };
  var KVALITET = { AI_PREPARED_FOR_REVIEW: "Sadrži analizu (AI) — za vaš pregled", DETERMINISTIC: "Samo iz spisa — bez AI dela" };
  var POREKLO = { SOURCE_FACT: "Iz dokumenta", HUMAN_CONFIRMED: "Uneo advokat", DETERMINISTIC_DERIVATION: "Izračunato",
    AI_ANALYSIS: "Analiza (AI)", UNKNOWN: "Poreklo nepoznato" };
  var STATUS = { READY_FOR_REVIEW: "Čeka vaš pregled", ACCEPTED: "Prihvaćeno", REJECTED: "Odbačeno",
    SUPERSEDED: "Zastarelo — okidač se promenio (npr. ročište ili analiza predmeta)", FAILED: "Nije pripremljeno",
    QUEUED: "U pripremi", RUNNING: "U pripremi", DEAD_LETTER: "Nije pripremljeno" };
  var KLASA = { podupire: "u prilog predmeta", osporava: "protiv pozicije predmeta", neutralno: "neutralno", nije_utvrdjeno: "nije utvrđeno" };
  var AI_RAZLOG = { MODEL_NEDOSTUPAN: "AI deo nije pripremljen: model nije bio dostupan. Deo iz spisa je potpun.",
    NIJEDNA_STAVKA_NIJE_PROSLA_PROVERU: "AI deo nije prikazan: nijedan predlog nije prošao proveru izvora.",
    NEMA_STAVKI_IZ_SPISA: "AI deo nije pripremljen: u spisu nema stavki na koje bi se oslonio." };
  var TEZINA = { kriticna: "kritična", visoka: "visoka", srednja: "srednja", niska: "niska" };
  var UUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

  function tekst(v) { return String(v == null ? "" : v).trim(); }
  function datum(iso) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(tekst(iso)); return m ? m[3] + "." + m[2] + "." + m[1] + "." : ""; }
  function vreme(iso) {
    var d = new Date(tekst(iso));
    if (isNaN(d.getTime())) return "";
    return datum(d.toISOString()) + " u " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  }
  function niz(v) { return Array.isArray(v) ? v : []; }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api, adresaPredmeta = o.adresaPredmeta, adresaRada = o.adresaRada;
    var gen = 0, k = null, otvoren = null, saljem = false;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function stanje(id, st, t) { var n = $(id); if (!n) return; if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function poreklo(p) { var s = el("span", "prov", POREKLO[p] || POREKLO.UNKNOWN); s.dataset.poreklo = POREKLO[p] ? p : "UNKNOWN"; return s; }

    /* ── lista ──────────────────────────────────────────────────────────── */
    function stavkaListe(x) {
      var li = el("li", "an-item vp-item");
      li.dataset.rad = tekst(x.id); li.dataset.tip = tekst(x.tip || x.work_type);
      var red = el("div", "an-item__head");
      var naslov = el("a", "vp-item__title", tekst(x.naslov || x.title) || TIP[x.tip || x.work_type] || "Pripremljen rad");
      naslov.href = UUID.test(tekst(x.id)) ? adresaRada(x.id) : "#/danas";
      red.append(naslov);
      var kv = el("span", "prov", KVALITET[x.kvalitet || x.quality_state] || "Za pregled");
      kv.dataset.poreklo = (x.kvalitet || x.quality_state) === "DETERMINISTIC" ? "SOURCE_FACT" : "AI_ANALYSIS";
      red.append(kv);
      li.append(red);
      var meta = el("p", "an-item__meta");
      meta.append(el("span", null, (TIP[x.tip || x.work_type] || "Pripremljen rad") + " · "));
      var naziv = tekst(x.predmet_naziv) || "predmet";
      if (UUID.test(tekst(x.predmet_id)) && adresaPredmeta) { var a = el("a", "text-btn", naziv); a.href = adresaPredmeta(x.predmet_id); meta.append(a); }
      else meta.append(el("span", null, naziv));
      var kad = vreme(x.pripremljeno || x.ready_at);
      if (kad) meta.append(el("span", null, " · pripremljeno " + kad));
      li.append(meta);
      if (tekst(x.razlog || x.reason)) li.append(el("p", "an-item__meta", "Zašto: " + tekst(x.razlog || x.reason)));
      if (tekst(x.sazetak || x.summary)) li.append(el("p", "vp-item__summary", tekst(x.sazetak || x.summary)));
      return li;
    }

    /** stanjeIzvora: "OK" | "NIJE_UKLJUCENO" | "NIJE_PROCITANO" | null (učitavanje/očišćeno). */
    function prikaziListu(blokId, ulId, stanjeId, stavke, stanjeIzvora, prazno) {
      var blok = $(blokId), ul = $(ulId);
      if (!ul) return;
      ul.replaceChildren();
      stanje(stanjeId, null);
      if (stanjeIzvora === "NIJE_UKLJUCENO") { if (blok) blok.hidden = true; return; }
      if (blok) blok.hidden = false;
      if (stanjeIzvora === null) return;
      if (stanjeIzvora !== "OK") { stanje(stanjeId, "greska", "Pripremljeni rad nije učitan. Ovo ne znači da ga nema."); return; }
      var lista = niz(stavke);
      if (!lista.length) { if (prazno) stanje(stanjeId, "prazno", prazno); else if (blok) blok.hidden = true; return; }
      lista.slice(0, 20).forEach(function (x) { ul.append(stavkaListe(x)); });
    }

    /* ── detalj ─────────────────────────────────────────────────────────── */
    function sekcija(naslov) { var s = el("section", "matter__section vp-sec"); s.append(el("h2", "matter__h2", naslov)); return s; }
    function stavkaPorekla(glavni, porekloKod, dodaci) {
      var li = el("li", "an-item");
      var red = el("div", "an-item__head");
      red.append(el("span", "an-item__text", glavni));
      if (porekloKod) red.append(poreklo(porekloKod));
      li.append(red);
      niz(dodaci).forEach(function (x) { if (x) li.append(x); });
      return li;
    }
    function izvor(naziv, strana) {
      if (!tekst(naziv)) return null;
      return el("p", "an-item__meta", "Izvor: " + tekst(naziv) + (strana ? " · približno str. " + strana : ""));
    }
    function lista(stavke, fn) { var ul = el("ul", "an-list"); niz(stavke).forEach(function (x) { ul.append(fn(x)); }); return ul; }
    function aiDeo(ai, napomenaFallback) {
      var s = sekcija("Predlozi analize (AI)");
      s.append(el("p", "field__help", tekst(ai && ai.napomena) || napomenaFallback));
      if (!ai || ai.stanje !== "PRIPREMLJENO") { s.append(el("p", "list-state", AI_RAZLOG[ai && ai.razlog] || "AI deo nije pripremljen.")); return s; }
      return s;
    }

    function prikaziPripremuRocista(c, koren) {
      var r = c.rociste || {};
      var s1 = sekcija("Ročište");
      s1.append(lista([r], function () {
        return stavkaPorekla([datum(r.datum), r.vreme ? "u " + r.vreme : "", r.sud || "", r.sudnica ? "sudnica " + r.sudnica : ""].filter(Boolean).join(" · "),
          null, [el("p", "an-item__meta", "Iz evidencije ročišta predmeta (ne iz analize)")]);
      }));
      koren.append(s1);
      var s2 = sekcija("Ključne činjenice iz spisa");
      if (!niz(c.kljucne_cinjenice).length) s2.append(el("p", "list-state", "U spisu nema potvrđenih činjenica."));
      else s2.append(lista(c.kljucne_cinjenice, function (x) { return stavkaPorekla(tekst(x.tekst), x.poreklo, [izvor(x.dokument_naziv, x.strana_procena)]); }));
      koren.append(s2);
      if (niz(c.protivrecnosti).length) {
        var s3 = sekcija("Aktivne protivrečnosti");
        s3.append(lista(c.protivrecnosti, function (x) {
          var ul = lista(x.ucesnici, function (u) { return stavkaPorekla(tekst(u.tvrdnja) || "Tvrdnja nije dostupna", null, [izvor(u.dokument_naziv)]); });
          ul.classList.add("an-sub");
          return stavkaPorekla(tekst(x.sporna_tacka), x.poreklo, [el("p", "an-item__meta", "Težina: " + (TEZINA[x.tezina] || tekst(x.tezina) || "nije navedena")), ul]);
        }));
        koren.append(s3);
      }
      if (niz(c.otvorene_radnje).length) {
        var s4 = sekcija("Otvorene radnje");
        s4.append(lista(c.otvorene_radnje, function (x) { return stavkaPorekla(tekst(x.razlog), "DETERMINISTIC_DERIVATION", [el("p", "an-item__meta", (x.rok ? "rok " + datum(x.rok) : "bez roka"))]); }));
        koren.append(s4);
      }
      if (niz(c.nedostaje).length) {
        var s5 = sekcija("Šta nedostaje");
        s5.append(lista(c.nedostaje, function (x) { return stavkaPorekla(tekst(x.tekst), x.poreklo, [x.opis ? el("p", "an-item__meta", tekst(x.opis)) : null]); }));
        koren.append(s5);
      }
      var ai = c.ai || {};
      var s6 = aiDeo(ai, "Predlog analize (AI) — nije utvrđena činjenica.");
      if (ai.stanje === "PRIPREMLJENO") {
        if (niz(ai.pitanja).length) { s6.append(el("h3", "answer__h", "Pitanja za proveru pre ročišta")); s6.append(lista(ai.pitanja, function (x) { return stavkaPorekla(tekst(x.tekst), "AI_ANALYSIS"); })); }
        if (niz(ai.beleske).length) { s6.append(el("h3", "answer__h", "Beleške za pripremu")); s6.append(lista(ai.beleske, function (x) { return stavkaPorekla(tekst(x.tekst), "AI_ANALYSIS"); })); }
      }
      koren.append(s6);
    }

    function prikaziUticajPrakse(c, koren) {
      var z = c.izvor || {};
      var s1 = sekcija("Odluka");
      s1.append(lista([z], function () {
        return stavkaPorekla([tekst(z.broj), tekst(z.sud), datum(z.datum) || tekst(z.datum)].filter(Boolean).join(" · "), "SOURCE_FACT",
          [el("p", "an-item__meta", z.provereno ? "Proverena u bazi sudskih odluka" + (z.oblast ? " · " + tekst(z.oblast) : "") : "Izvor nije proveren")]);
      }));
      if (tekst(z.izvod)) { var q = el("blockquote", "vp-izvod", tekst(z.izvod)); s1.append(q); }
      koren.append(s1);
      var zs = c.zasto || {};
      if (tekst(zs.obrazlozenje_radar)) {
        var s2 = sekcija("Zašto je pronađena");
        s2.append(lista([zs], function () { return stavkaPorekla(tekst(zs.obrazlozenje_radar), "AI_ANALYSIS", [el("p", "an-item__meta", tekst(zs.napomena))]); }));
        koren.append(s2);
      }
      var ai = c.ai || {};
      var s3 = aiDeo(ai, "Analiza uticaja (AI) — nije utvrđena činjenica.");
      if (ai.stanje === "PRIPREMLJENO") {
        s3.append(el("p", "an-item__meta", "Procena odnosa prema predmetu: " + (KLASA[ai.klasifikacija] || "nije utvrđeno")));
        if (niz(ai.uticaj).length) {
          s3.append(el("h3", "answer__h", "Mogući uticaj na predmet"));
          s3.append(lista(ai.uticaj, function (x) { return stavkaPorekla(tekst(x.tekst), "AI_ANALYSIS", [el("p", "an-item__meta", "Izvod iz odluke: „" + tekst(x.izvod_iz_odluke) + "“")]); }));
        }
        if (niz(ai.pitanja).length) { s3.append(el("h3", "answer__h", "Pitanja za pregled")); s3.append(lista(ai.pitanja, function (x) { return stavkaPorekla(tekst(x.tekst), "AI_ANALYSIS"); })); }
        if (ai.razmotriti_argument && ai.razmotriti_argument.da) s3.append(el("p", "notice", "Razmotriti argument: " + tekst(ai.razmotriti_argument.razlog)));
      }
      koren.append(s3);
    }

    function ocistiDetalj() {
      ["vpr-delovi"].forEach(function (id) { var n = $(id); if (n) n.replaceChildren(); });
      ["vpr-meta", "vpr-razlog"].forEach(function (id) { var n = $(id); if (n) n.textContent = ""; });
      stanje("vpr-stanje", null); stanje("vpr-poruka", null);
      if ($("vpr-sadrzaj")) $("vpr-sadrzaj").hidden = true;
      if ($("vpr-odluka-blok")) $("vpr-odluka-blok").hidden = true;
      if ($("vpr-znanje-blok")) { $("vpr-znanje-blok").hidden = true; stanje("vpr-znanje-poruka", null); $("vpr-predlozi-znanje").disabled = false; }
      if ($("vpr-razlog-odbijanja")) $("vpr-razlog-odbijanja").value = "";
      if ($("vpr-naslov")) $("vpr-naslov").textContent = "Pripremljeni rad";
    }

    function prikaziDetalj(w) {
      $("vpr-naslov").textContent = tekst(w.title) || TIP[w.work_type] || "Pripremljeni rad";
      var meta = $("vpr-meta");
      meta.replaceChildren();
      meta.append(el("span", null, (TIP[w.work_type] || "Pripremljen rad") + " · "));
      if (UUID.test(tekst(w.predmet_id))) { var a = el("a", "text-btn", tekst(w.predmet_naziv) || "predmet"); a.href = adresaPredmeta(w.predmet_id); meta.append(a); }
      var kad = vreme(w.ready_at);
      meta.append(el("span", null, (kad ? " · pripremljeno " + kad : "") + " · " + (STATUS[w.status] || tekst(w.status))));
      $("vpr-razlog").textContent = tekst(w.reason) ? "Zašto je pripremljeno: " + tekst(w.reason) : "";
      var koren = $("vpr-delovi");
      var c = w.content_json || {};
      if (w.work_type === "HEARING_PREP" && c.rociste) prikaziPripremuRocista(c, koren);
      else if (w.work_type === "PRECEDENT_IMPACT" && c.izvor) prikaziUticajPrakse(c, koren);
      else koren.append(el("p", "list-state", "Sadržaj nije dostupan za ovaj rad."));
      $("vpr-sadrzaj").hidden = false;
      $("vpr-odluka-blok").hidden = w.status !== "READY_FOR_REVIEW";
      $("vpr-prihvati").disabled = false; $("vpr-odbaci").disabled = false;
      /* NS008 Task 15 — samo prihvaćen rad sme da se PREDLOŽI kao znanje (staging + advokatska overa). */
      if ($("vpr-znanje-blok")) $("vpr-znanje-blok").hidden = w.status !== "ACCEPTED";
    }

    var predlazem = false;
    async function predloziZnanje() {
      if (!otvoren || predlazem) return;
      var moja = gen, id = otvoren.id, korisnik = otvoren.korisnik;
      predlazem = true; $("vpr-predlozi-znanje").disabled = true;
      stanje("vpr-znanje-poruka", "ucitavanje", "Šaljem rad na advokatsku overu…");
      var r = await api.send("/api/law-brain/rad/" + encodeURIComponent(id) + "/predlozi-znanje", { token: sesija.token(),
        oblik: function (x) { return x && typeof x.staging_id === "string"; } });
      predlazem = false;
      if (moja !== gen || !otvoren || otvoren.id !== id || sesija.stanje().korisnik !== korisnik) return;
      if (r.ok) { stanje("vpr-znanje-poruka", "ok", r.podaci.novo ? "Rad čeka advokatsku overu. Znanje kancelarije postaje tek posle odobrenja." : "Ovaj rad je već predložen i čeka overu (ili je obrađen)."); return; }
      $("vpr-predlozi-znanje").disabled = false;
      if (r.greska && r.greska.ishodNepoznat) { stanje("vpr-znanje-poruka", "nepoznato", "Ishod nije poznat — rad je možda već predložen. Ponovni pokušaj neće napraviti duplikat."); return; }
      stanje("vpr-znanje-poruka", "greska", r.status === 409 ? "Kao znanje može se predložiti samo prihvaćen rad sa sadržajem." : "Predlog nije sačuvan zbog greške. Pokušajte ponovo.");
    }

    async function otvori(id) {
      var s = sesija.stanje();
      gen++;
      if (k) { k.abort(); k = null; }
      ocistiDetalj();
      otvoren = { id: tekst(id), korisnik: s.korisnik };
      if (!UUID.test(otvoren.id)) { stanje("vpr-stanje", "greska", "Pripremljeni rad nije pronađen."); return; }
      if (s.stanje !== sesija.STANJA.PRIJAVLJEN) { stanje("vpr-stanje", "greska", "Niste prijavljeni."); return; }
      var moja = gen;
      k = new AbortController();
      stanje("vpr-stanje", "ucitavanje", "Učitavanje pripremljenog rada…");
      var r = await api.get("/api/autonomy/work-items/" + encodeURIComponent(otvoren.id), { token: sesija.token(), signal: k.signal,
        oblik: function (x) { return x && typeof x.id === "string" && typeof x.status === "string"; } });
      if (moja !== gen || !otvoren || sesija.stanje().korisnik !== otvoren.korisnik) return;
      k = null;
      if (!r.ok) {
        if (r.greska && r.greska.kod === "ABORTED") return;
        stanje("vpr-stanje", "greska", r.status === 404 ? "Pripremljeni rad nije pronađen."
          : "Pripremljeni rad nije učitan zbog greške. Ovo ne znači da ga nema.");
        return;
      }
      stanje("vpr-stanje", null);
      prikaziDetalj(r.podaci);
    }

    async function odluci(akcija) {
      if (!otvoren || saljem) return;
      var moja = gen, id = otvoren.id, korisnik = otvoren.korisnik;
      saljem = true;
      $("vpr-prihvati").disabled = true; $("vpr-odbaci").disabled = true;
      stanje("vpr-poruka", "ucitavanje", akcija === "accept" ? "Beležim prihvatanje…" : "Beležim odbijanje…");
      var telo = akcija === "reject" && tekst($("vpr-razlog-odbijanja").value) ? { razlog: tekst($("vpr-razlog-odbijanja").value).slice(0, 1000) } : undefined;
      var r = await api.send("/api/autonomy/work-items/" + encodeURIComponent(id) + "/" + akcija, { token: sesija.token(), telo: telo,
        oblik: function (x) { return x && typeof x.status === "string"; } });
      saljem = false;
      if (moja !== gen || !otvoren || otvoren.id !== id || sesija.stanje().korisnik !== korisnik) return;
      if (r.ok) {
        stanje("vpr-poruka", "ok", (r.podaci.status === "ACCEPTED" ? "Prihvaćeno." : "Odbačeno.") + " Ništa nije poslato niti promenjeno u predmetu.");
        $("vpr-odluka-blok").hidden = true;
        if ($("vpr-znanje-blok")) $("vpr-znanje-blok").hidden = r.podaci.status !== "ACCEPTED";
        return;
      }
      if (r.greska && r.greska.ishodNepoznat) { stanje("vpr-poruka", "nepoznato", "Ishod odluke nije poznat — ponovo učitavam stanje."); await otvori(id); stanje("vpr-poruka", "nepoznato", "Ishod prethodne odluke nije bio poznat; prikazano je trenutno stanje."); return; }
      if (r.status === 409) { stanje("vpr-poruka", "greska", "Ovaj rad više nije na pregledu."); await otvori(id); stanje("vpr-poruka", "greska", "Ovaj rad više nije na pregledu."); return; }
      stanje("vpr-poruka", "greska", "Odluka nije zabeležena zbog greške. Pokušajte ponovo.");
      $("vpr-prihvati").disabled = false; $("vpr-odbaci").disabled = false;
    }

    function zatvori() { gen++; if (k) { k.abort(); k = null; } otvoren = null; ocistiDetalj(); }

    if ($("vpr-prihvati")) $("vpr-prihvati").addEventListener("click", function () { odluci("accept"); });
    if ($("vpr-odbaci")) $("vpr-odbaci").addEventListener("click", function () { odluci("reject"); });
    if ($("vpr-predlozi-znanje")) $("vpr-predlozi-znanje").addEventListener("click", predloziZnanje);
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) zatvori(); });

    return { prikaziListu: prikaziListu, otvori: otvori, zatvori: zatvori, zaustavi: function () { odjavi(); zatvori(); } };
  }

  root.VxPripremljeno = Object.freeze({ napravi: napravi });
})(window);
