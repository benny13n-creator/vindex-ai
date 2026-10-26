/* Vindex V2 NG — Podešavanja › Moj nalog (Settings Master Sprint P1.2).
 *
 * Ugovori (samo čitanje; vlasnik iz tokena):
 *   GET /api/me           → {user_id, email, ...}            (api.py, `me`)
 *   GET /api/plan/status  → {plan, plan_display, subscription_expires_at, ...}  (routers/plans.py)
 * NE prikazuje se: ime za prikaz (V1 ga čuva samo u localStorage; nema serverske rute za izmenu),
 * promena lozinke u V2 (postojeći postupak je Supabase link iz klasičnog prikaza), founder podaci.
 * Odjava ide postojećim tokom (VxRuntime.odjava); bez njega se dugme ne prikazuje.
 */
(function (root) {
  "use strict";

  function datum(iso) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || "")); return m ? m[3] + "." + m[2] + "." + m[1] + "." : ""; }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api, gen = 0, kontrola = null, otvoren = false;

    function stanje(st, t) { var n = $("pn-nalog-stanje"); n.hidden = !st; n.textContent = t || ""; if (st) n.dataset.stanje = st; else delete n.dataset.stanje; }
    function ocisti() {
      gen++; if (kontrola) kontrola.abort(); kontrola = null;
      $("pn-nalog-podaci").hidden = true; $("pn-nalog-email").textContent = ""; $("pn-nalog-plan").textContent = "";
      stanje(null);
    }
    function uskladiOdjavu() {
      var rt = root.VxRuntime, a = $("pn-nalog-odjava");
      a.hidden = !(rt && rt.odjava) || sesija.stanje().stanje !== sesija.STANJA.PRIJAVLJEN;
      if (rt && rt.odjava) a.href = rt.odjava;
    }
    function greska(g) {
      if (g && g.kod === "AUTH_REQUIRED") return "Prijava je istekla. Prijavite se ponovo.";
      if (g && g.kod === "RATE_LIMITED") return "Previše zahteva. Pokušajte ponovo malo kasnije.";
      return "Podaci naloga nisu učitani. Ovo nije prazan nalog.";
    }
    async function ucitaj() {
      var moj = ++gen; if (kontrola) kontrola.abort(); kontrola = new AbortController();
      stanje("ucitavanje", "Učitavanje naloga…");
      var t = sesija.token(), sig = kontrola.signal;
      var r = await Promise.all([
        api.get("/api/me", { token: t, signal: sig, oblik: function (x) { return typeof x.email === "string"; } }),
        api.get("/api/plan/status", { token: t, signal: sig, oblik: function (x) { return typeof x.plan === "string"; } }),
      ]);
      if (moj !== gen) return;
      kontrola = null;
      if (!r[0].ok) { if (r[0].greska.kod !== "ABORTED") stanje("greska", greska(r[0].greska)); return; }
      stanje(null);
      $("pn-nalog-email").textContent = r[0].podaci.email || "Email adresa nije dostupna";
      if (r[1].ok) {
        var p = r[1].podaci, istek = datum(p.subscription_expires_at);
        $("pn-nalog-plan").textContent = String(p.plan_display || p.plan) + (istek ? " — važi do " + istek : "");
      } else {
        $("pn-nalog-plan").textContent = "Plan trenutno nije učitan.";
      }
      $("pn-nalog-podaci").hidden = false;
    }
    function pokreni() {
      uskladiOdjavu();
      if (sesija.stanje().stanje !== sesija.STANJA.PRIJAVLJEN) { stanje("greska", "Prijavite se da biste videli svoj nalog."); return; }
      ucitaj();
    }
    var odjavi = sesija.naPromenu(function (novo, staro) {
      if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) { ocisti(); if (otvoren) pokreni(); else uskladiOdjavu(); }
    });
    ocisti();
    return {
      otvori: function () { otvoren = true; ocisti(); pokreni(); },
      zatvori: function () { otvoren = false; ocisti(); },
      zaustavi: function () { otvoren = false; odjavi(); ocisti(); },
    };
  }

  root.VxPodesavanjaSekcije = root.VxPodesavanjaSekcije || {};
  root.VxPodesavanjaSekcije.nalog = napravi;
})(window);
