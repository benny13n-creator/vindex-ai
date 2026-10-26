/* Vindex V2 NG — Podešavanja › Finansije i plan (Settings Master Sprint P1.6).
 *
 * Ugovori (vlasnik iz tokena):
 *   GET  /api/plan/status             → {plan, plan_display, subscription_expires_at, credits_remaining, usage_this_month[]}
 *   GET  /api/tarife/moja-satnica     → {tarifa_po_satu, source: custom|default}
 *   PUT  /api/tarife/moja-satnica     {tarifa_po_satu > 0, ≤ 1 000 000} → {ok, tarifa_po_satu}
 *   GET  /api/sef/podesavanja         → {konfigurisano, podaci{seller_pib, seller_naziv, seller_adresa, seller_mesto, api_key_preview}}
 *   POST /api/sef/podesavanja         {seller_pib (9 cifara), seller_naziv, seller_adresa, seller_mesto, api_key?}
 * Plan, cene i AKS tarifa se NE menjaju. API ključ se samo upisuje (password polje, briše se posle slanja) i nikad
 * ne čita nazad — server vraća samo „***“ + poslednja 4 znaka. Nijedna faktura se ne šalje.
 */
(function (root) {
  "use strict";

  function datum(iso) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || "")); return m ? m[3] + "." + m[2] + "." + m[1] + "." : ""; }
  function iznos(v) { return Number(v).toLocaleString("sr-RS", { maximumFractionDigits: 2 }); }
  function tekst(v) { return String(v == null ? "" : v).trim(); }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api, era = 0, kontrola = null, otvoren = false;
    var satnica = null, sef = null, zauzetoSat = false, zauzetoSef = false;
    var SEF_POLJA = ["pn-sef-pib", "pn-sef-naziv", "pn-sef-adresa", "pn-sef-mesto", "pn-sef-kljuc"];

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function poruka(id, st, t) { var n = $(id); n.hidden = !st; n.textContent = t || ""; if (st) n.dataset.stanje = st; else delete n.dataset.stanje; }

    function osvezi() {
      $("pn-satnica").disabled = !satnica || zauzetoSat;
      $("pn-satnica-sacuvaj").disabled = !satnica || zauzetoSat;
      SEF_POLJA.forEach(function (id) { $(id).disabled = !sef || zauzetoSef; });
      $("pn-sef-sacuvaj").disabled = !sef || zauzetoSef;
    }
    function ocisti() {
      era++; if (kontrola) kontrola.abort(); kontrola = null;
      satnica = null; sef = null; zauzetoSat = false; zauzetoSef = false;
      $("pn-plan-podaci").hidden = true; $("pn-plan-potrosnja").replaceChildren();
      ["pn-plan-naziv", "pn-plan-istek", "pn-plan-krediti", "pn-satnica-izvor", "pn-sef-status"].forEach(function (id) { $(id).textContent = ""; });
      $("pn-satnica").value = "";
      SEF_POLJA.forEach(function (id) { $(id).value = ""; });
      ["pn-fin-stanje", "pn-plan-stanje", "pn-satnica-poruka", "pn-sef-poruka"].forEach(function (id) { poruka(id, null); });
      osvezi();
    }
    function nijeUcitano(g, sta) {
      if (g && g.kod === "AUTH_REQUIRED") return "Prijava je istekla. " + sta + " se ne prikazuje.";
      return sta + " nije učitan zbog greške. Ovo nije prazan podatak.";
    }

    function prikaziPlan(r) {
      if (!r.ok) { poruka("pn-plan-stanje", "greska", nijeUcitano(r.greska, "Plan")); return; }
      var p = r.podaci;
      $("pn-plan-naziv").textContent = tekst(p.plan_display) || tekst(p.plan);
      $("pn-plan-istek").textContent = datum(p.subscription_expires_at) || "bez roka isteka";
      $("pn-plan-krediti").textContent = typeof p.credits_remaining === "number" ? iznos(p.credits_remaining) : "nije poznato";
      var lista = $("pn-plan-potrosnja");
      var stavke = Array.isArray(p.usage_this_month) ? p.usage_this_month : [];
      if (!stavke.length) lista.append(el("li", "people__item", "Ovog meseca nema zabeležene potrošnje."));
      stavke.forEach(function (u) {
        if (!u || !tekst(u.naziv || u.feature_key)) return;
        var li = el("li", "people__item");
        li.append(el("span", "people__name", tekst(u.naziv || u.feature_key)));
        var granice = [typeof u.dnevni_limit === "number" ? u.dnevni_limit + " dnevno" : "", typeof u.mesecni_limit === "number" ? u.mesecni_limit + " mesečno" : ""].filter(Boolean).join(", ");
        li.append(el("span", "people__meta", [iznos(u.broj_koriscenja || 0) + " korišćenja", iznos(u.krediti_potroseni || 0) + " kredita",
          granice ? "ograničenje: " + granice : "bez ograničenja"].join(" · ")));
        lista.append(li);
      });
      $("pn-plan-podaci").hidden = false;
    }
    function prikaziSatnicu(r) {
      if (!r.ok) { poruka("pn-satnica-poruka", "greska", nijeUcitano(r.greska, "Satnica")); return; }
      satnica = r.podaci;
      $("pn-satnica").value = satnica.source === "custom" ? String(satnica.tarifa_po_satu) : "";
      $("pn-satnica").placeholder = String(satnica.tarifa_po_satu);
      $("pn-satnica-izvor").textContent = satnica.source === "custom" ? "Vaša satnica: " + iznos(satnica.tarifa_po_satu) + " RSD."
        : "Niste uneli satnicu; koristi se podrazumevanih " + iznos(satnica.tarifa_po_satu) + " RSD.";
    }
    function prikaziSef(r) {
      if (!r.ok) { poruka("pn-sef-poruka", "greska", nijeUcitano(r.greska, "SEF")); return; }
      sef = r.podaci;
      var p = sef.konfigurisano && sef.podaci ? sef.podaci : null;
      $("pn-sef-pib").value = p ? tekst(p.seller_pib) : "";
      $("pn-sef-naziv").value = p ? tekst(p.seller_naziv) : "";
      $("pn-sef-adresa").value = p ? tekst(p.seller_adresa) : "";
      $("pn-sef-mesto").value = p ? tekst(p.seller_mesto) : "";
      $("pn-sef-kljuc").value = "";
      $("pn-sef-status").textContent = p ? "SEF je podešen. Sačuvan ključ: " + tekst(p.api_key_preview) + "." : "SEF nije podešen. Za prvo čuvanje potreban je API ključ.";
    }

    async function ucitaj() {
      var moja = era; if (kontrola) kontrola.abort(); kontrola = new AbortController();
      var t = sesija.token(), sig = kontrola.signal;
      poruka("pn-fin-stanje", "ucitavanje", "Učitavanje…");
      var r = await Promise.all([
        api.get("/api/plan/status", { token: t, signal: sig, oblik: function (x) { return typeof x.plan === "string"; } }),
        api.get("/api/tarife/moja-satnica", { token: t, signal: sig, oblik: function (x) { return typeof x.tarifa_po_satu === "number" && (x.source === "custom" || x.source === "default"); } }),
        api.get("/api/sef/podesavanja", { token: t, signal: sig, oblik: function (x) { return typeof x.konfigurisano === "boolean"; } }),
      ]);
      if (moja !== era) return;
      kontrola = null;
      if (r.some(function (x) { return !x.ok && x.greska.kod === "ABORTED"; })) return;
      poruka("pn-fin-stanje", null);
      prikaziPlan(r[0]); prikaziSatnicu(r[1]); prikaziSef(r[2]);
      osvezi();
    }

    function greskaUpisa(r) {
      var g = r.greska || {};
      if (g.ishodNepoznat) return "Ishod nije poznat. Prikaz je osvežen sa servera — proverite vrednost pre ponavljanja.";
      if (g.kod === "VALIDATION_ERROR") return "Server nije prihvatio unos" + (g.polja && g.polja.length ? " (" + g.polja.join(", ") + ")" : "") + ". Ništa nije sačuvano.";
      if (g.kod === "AUTH_REQUIRED") return "Prijava je istekla. Ništa nije sačuvano.";
      if (g.kod === "RATE_LIMITED") return "Previše zahteva. Ništa nije sačuvano; pokušajte za minut.";
      return "Čuvanje nije potvrđeno (" + (g.kod || "greška") + ").";
    }

    $("pn-satnica-forma").addEventListener("submit", async function (e) {
      e.preventDefault();
      if (!satnica || zauzetoSat) return;
      var v = Number($("pn-satnica").value);
      if (!$("pn-satnica").value || !Number.isFinite(v) || v <= 0 || v > 1000000) { poruka("pn-satnica-poruka", "greska", "Unesite satnicu veću od 0 i najviše 1.000.000 RSD."); return; }
      var moja = era;
      zauzetoSat = true; osvezi();
      poruka("pn-satnica-poruka", "ucitavanje", "Čuvanje…");
      var r = await api.send("/api/tarife/moja-satnica", { metod: "PUT", telo: { tarifa_po_satu: v }, token: sesija.token(),
        oblik: function (x) { return x.ok === true && typeof x.tarifa_po_satu === "number"; } });
      if (moja !== era) return;
      zauzetoSat = false;
      var tekstPoruke = r.ok && r.podaci ? "Satnica je sačuvana: " + iznos(r.podaci.tarifa_po_satu) + " RSD." : r.ok ? "Server je prihvatio zahtev, ali potvrda nije čitljiva." : greskaUpisa(r);
      var st = r.ok && r.podaci ? "uspeh" : (r.ok || r.greska.ishodNepoznat) ? "nepoznato" : "greska";
      /* Odbijen upis (4xx) ne briše unos; posle uspeha ili nepoznatog ishoda prikazuje se stanje sa servera. */
      if (st !== "greska") {
        var s2 = await api.get("/api/tarife/moja-satnica", { token: sesija.token(), oblik: function (x) { return typeof x.tarifa_po_satu === "number"; } });
        if (moja !== era) return;
        if (s2.ok) prikaziSatnicu(s2);
      }
      poruka("pn-satnica-poruka", st, tekstPoruke);
      osvezi();
    });

    $("pn-sef-forma").addEventListener("submit", async function (e) {
      e.preventDefault();
      if (!sef || zauzetoSef) return;
      var telo = { seller_pib: $("pn-sef-pib").value.trim(), seller_naziv: $("pn-sef-naziv").value.trim(),
        seller_adresa: $("pn-sef-adresa").value.trim(), seller_mesto: $("pn-sef-mesto").value.trim() };
      var kljuc = $("pn-sef-kljuc").value.trim();
      if (!/^\d{9}$/.test(telo.seller_pib)) { poruka("pn-sef-poruka", "greska", "PIB mora imati tačno 9 cifara."); return; }
      if (telo.seller_naziv.length < 2) { poruka("pn-sef-poruka", "greska", "Unesite naziv prodavca."); return; }
      if (kljuc) { if (kljuc.length < 10) { poruka("pn-sef-poruka", "greska", "API ključ je prekratak."); return; } telo.api_key = kljuc; }
      else if (!sef.konfigurisano) { poruka("pn-sef-poruka", "greska", "Za prvo čuvanje potreban je SEF API ključ."); return; }
      var moja = era;
      zauzetoSef = true; osvezi();
      $("pn-sef-kljuc").value = "";
      poruka("pn-sef-poruka", "ucitavanje", "Čuvanje…");
      var r = await api.send("/api/sef/podesavanja", { metod: "POST", telo: telo, token: sesija.token(), oblik: function (x) { return x.ok === true; } });
      telo = null; kljuc = "";
      if (moja !== era) return;
      zauzetoSef = false;
      var tekstPoruke = r.ok && r.podaci ? "SEF podaci su sačuvani." : r.ok ? "Server je prihvatio zahtev, ali potvrda nije čitljiva." : greskaUpisa(r);
      var st = r.ok && r.podaci ? "uspeh" : (r.ok || r.greska.ishodNepoznat) ? "nepoznato" : "greska";
      if (st !== "greska") {
        var s2 = await api.get("/api/sef/podesavanja", { token: sesija.token(), oblik: function (x) { return typeof x.konfigurisano === "boolean"; } });
        if (moja !== era) return;
        if (s2.ok) prikaziSef(s2);
      }
      poruka("pn-sef-poruka", st, tekstPoruke);
      osvezi();
    });

    function pokreni() {
      if (sesija.stanje().stanje !== sesija.STANJA.PRIJAVLJEN) { poruka("pn-fin-stanje", "greska", "Prijavite se da biste videli plan i finansijska podešavanja."); return; }
      ucitaj();
    }
    var odjavi = sesija.naPromenu(function (novo, staro) {
      if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) { ocisti(); if (otvoren) pokreni(); }
    });
    ocisti();
    return {
      otvori: function () { otvoren = true; ocisti(); pokreni(); },
      zatvori: function () { otvoren = false; ocisti(); },
      zaustavi: function () { otvoren = false; odjavi(); ocisti(); },
    };
  }

  root.VxPodesavanjaSekcije = root.VxPodesavanjaSekcije || {};
  root.VxPodesavanjaSekcije.finansije = napravi;
})(window);
