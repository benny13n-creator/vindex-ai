/* Vindex V2 NG — Nov predmet: tri ulaza u ISTI tok predmeta (VCR001 T02).
 *
 *   Ručno            → postojeći src/nov-predmet.js (POST /api/predmeti), nepromenjen.
 *   Iz opisa problema → POST /api/intake/ekstrakcija {opis_problema} → PREDLOG (ništa se ne upisuje)
 *                       → advokat proverava i ispravlja → klijent (postojeći ili nov: POST /klijenti)
 *                       → provera sukoba interesa (POST /api/conflict-check, isto pravilo kao kartica Klijenti)
 *                       → POST /api/intake/kreiraj {klijent_id, naziv, …} → otvara se predmet.
 *   Iz dokumenta      → src/prijem-predmeta.js sa prefiksom „nd“: finalize BEZ predmet_id otvara predmet.
 *
 * Pravila:
 *  • Predlog modela je predlog: rok iz opisa se upisuje SAMO ako advokat izričito označi da je proverio datum.
 *  • Provera sukoba: „sukob“ zaustavlja otvaranje (kao povezivanje u kartici Klijenti); pregled / nepotpuna /
 *    neizvršena provera traže izričitu potvrdu. Podudaranje imena nije utvrđen sukob — tekst to kaže.
 *  • Ishodi se ne ulepšavaju: 5xx/mreža = ishod nepoznat (prvo proveriti listu predmeta); dok zahtev traje,
 *    slanje je zaključano. Vlasnika određuje server iz tokena.
 */
(function (root) {
  "use strict";

  function tekst(v) { return String(v == null ? "" : v).trim(); }
  function ispravanId(v) { return /^[A-Za-z0-9_-]{1,64}$/.test(tekst(v)); }
  function ispravanDatum(v) { return /^\d{4}-\d{2}-\d{2}$/.test(tekst(v)); }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api, naUspeh = o.naUspeh || function () {}, ishodCoi = o.ishodCoi;
    var gen = 0, radi = false, predlog = null, klijent = null, coi = null, kPretraga = null, tajmerPretrage = null;

    var prijem = root.VxPrijemPredmeta.napravi({ sesija: sesija, api: api, prefiks: "nd",
      naOtvoren: function (id) { var a = $("nd-otvori-predmet"); a.href = o.adresaPredmeta(id, "pregled"); $("nd-otvoren").hidden = false;
        if (o.osveziListu) o.osveziListu(); } });

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function poruka(st, t) { var n = $("npo-poruka"); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function prijavljen() { return sesija.stanje().stanje === sesija.STANJA.PRIJAVLJEN; }

    /* ── režimi ── */
    var REZIMI = { rucno: ["nov-rezim-rucno", "nov-forma"], opis: ["nov-rezim-opis", "npo-panel"], dokument: ["nov-rezim-dokument", "npd-panel"] };
    function rezim(r) {
      Object.keys(REZIMI).forEach(function (k) {
        var b = $(REZIMI[k][0]), panel = $(REZIMI[k][1]);
        if (k === r) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
        panel.hidden = k !== r;
      });
      if (r === "dokument") prijem.pocniNov();
    }
    Object.keys(REZIMI).forEach(function (k) { $(REZIMI[k][0]).addEventListener("click", function () { rezim(k); }); });

    /* ── A: problem prvo ── */
    async function predlozi() {
      if (radi) return;
      var opis = tekst($("npo-opis").value);
      if (opis.length < 20) { poruka("greska", "Opis treba da ima najmanje 20 znakova."); $("npo-opis").focus(); return; }
      if (!prijavljen()) { poruka("greska", "Niste prijavljeni. Ništa nije poslato."); return; }
      var moja = ++gen;
      radi = true; $("npo-predlozi").disabled = true; poruka("ucitavanje", "Pripremam predlog iz opisa…");
      var r = await api.send("/api/intake/ekstrakcija", { telo: { opis_problema: opis.slice(0, 4000) }, token: sesija.token(),
        oblik: function (x) { return typeof x.predlog_naziva_predmeta === "string"; } });
      if (moja !== gen) return;
      radi = false; $("npo-predlozi").disabled = false;
      if (!r.ok) {
        var g = r.greska || {};
        poruka("greska", g.kod === "FORBIDDEN" ? "Predlog iz opisa nije dostupan u vašem paketu. Predmet možete otvoriti ručno."
          : g.kod === "RATE_LIMITED" ? "Previše zahteva u kratkom roku. Pokušajte malo kasnije."
          : g.kod === "AUTH_REQUIRED" ? "Prijava više nije važeća." : r.status === 402 ? "Nemate dovoljno kredita za predlog. Predmet možete otvoriti ručno."
          : "Predlog nije pripremljen (" + (r.status || "mreža") + "). Ništa nije upisano.");
        return;
      }
      prikaziPredlog(r.podaci);
    }

    function prikaziPredlog(x) {
      predlog = x; coi = null; prikaziCoi(null);
      $("npo-naziv").value = tekst(x.predlog_naziva_predmeta).slice(0, 200);
      $("npo-vrsta").value = tekst(x.vrsta_spora).slice(0, 100);
      $("npo-protivna").value = tekst(x.protivna_strana).slice(0, 200);
      $("npo-vrednost").value = tekst(x.vrednost_spora).slice(0, 100);
      var imaRok = ispravanDatum(x.prvi_rok);
      $("npo-rok-okvir").hidden = !imaRok;
      $("npo-rok-upisi").checked = false;
      $("npo-rok-tekst").textContent = imaRok ? (x.prvi_rok + (tekst(x.rok_opis) ? " — " + tekst(x.rok_opis) : "") + ". Datum je predlog iz opisa; ne upisuje se dok ne potvrdite.") : "";
      var docs = Array.isArray(x.potrebni_dokumenti) ? x.potrebni_dokumenti.map(tekst).filter(Boolean) : [];
      $("npo-dokumenti").replaceChildren.apply($("npo-dokumenti"), docs.map(function (t) { return el("li", "an-item", t); }));
      $("npo-dokumenti-okvir").hidden = !docs.length;
      $("npo-predlog").hidden = false;
      poruka("uspeh", "Predlog je spreman. Proverite podatke, izaberite klijenta i pokrenite proveru sukoba interesa.");
      uskladi();
    }

    function imeKlijenta() {
      if (klijent) return klijent.ime;
      return [tekst($("npo-ime").value), tekst($("npo-prezime").value)].filter(Boolean).join(" ");
    }
    function uskladi() {
      var ime = imeKlijenta();
      $("npo-klijent-izbor").textContent = klijent ? "Izabran klijent iz kartoteke: " + klijent.ime : (ime ? "Nov klijent: " + ime : "Klijent nije izabran.");
      var coiOk = !!coi && coi.ime === ime && (coi.i.nastavak === "slobodno" || (coi.i.nastavak === "potvrda" && $("npo-coi-potvrda").checked));
      $("npo-otvori").disabled = radi || !predlog || tekst($("npo-naziv").value).length < 2 || !ime || !coiOk;
    }

    async function pretrazi() {
      var q = tekst($("npo-klijent-pretraga").value);
      if (kPretraga) { kPretraga.abort(); kPretraga = null; }
      if (q.length < 2) { $("npo-klijenti").replaceChildren(); return; }
      kPretraga = new AbortController();
      var r = await api.get("/klijenti", { token: sesija.token(), signal: kPretraga.signal, parametri: { pretraga: q, limit: 20 },
        oblik: function (x) { return Array.isArray(x.klijenti); } });
      if (!r.ok) { if (r.greska && r.greska.kod === "ABORTED") return; $("npo-klijenti").replaceChildren(el("li", "field__help", "Kartoteka nije učitana.")); return; }
      $("npo-klijenti").replaceChildren.apply($("npo-klijenti"), r.podaci.klijenti.filter(function (k) { return k && ispravanId(k.id); }).map(function (k) {
        var ime = [tekst(k.ime), tekst(k.prezime)].filter(Boolean).join(" ") || tekst(k.firma) || "Klijent bez imena";
        var li = el("li"), b = el("button", "pick__item", ime); b.type = "button";
        b.addEventListener("click", function () { klijent = { id: tekst(k.id), ime: ime }; $("npo-ime").value = ""; $("npo-prezime").value = ""; uskladi(); });
        li.append(b); return li;
      }));
    }

    function prikaziCoi(i) {
      var b = $("npo-coi");
      if (!i) { b.hidden = true; return; }
      b.hidden = false; b.dataset.stanje = i.vrsta;
      var naslov = i.vrsta === "sukob" ? "Mogući sukob interesa u aktivnom predmetu — potrebna provera" : i.naslov;
      var telo = i.vrsta === "sukob" ? "Podudaranje imena nije utvrđen sukob, ali otvaranje je zaustavljeno dok ne proverite navedene predmete (isto pravilo kao pri povezivanju klijenta)." : i.telo;
      $("npo-coi-naslov").textContent = naslov; $("npo-coi-telo").textContent = telo;
      $("npo-coi-lista").replaceChildren.apply($("npo-coi-lista"), i.konflikti.map(function (k) {
        return el("li", "an-item", k.predmet + (k.aktivan ? " (aktivan)" : " (zatvoren)") + (k.opis ? " · " + k.opis : "") + (k.podudaranje ? " · podudaranje: " + k.podudaranje : ""));
      }));
      $("npo-coi-potvrda-red").hidden = i.nastavak !== "potvrda";
      $("npo-coi-potvrda").checked = false;
    }

    async function proveriCoi() {
      var ime = imeKlijenta();
      if (!ime) { poruka("greska", "Prvo izaberite ili upišite klijenta."); return; }
      var moja = gen;
      $("npo-proveri").disabled = true; poruka("ucitavanje", "Provera sukoba interesa…");
      var r = await api.send("/api/conflict-check", { telo: { ime_prezime: ime.slice(0, 200) }, token: sesija.token(),
        oblik: function (x) { return typeof x.status === "string"; } });
      if (moja !== gen) return;
      $("npo-proveri").disabled = false;
      coi = { ime: ime, i: ishodCoi(r.ok ? r.podaci : null, null) };
      prikaziCoi(coi.i);
      poruka(null);
      uskladi();
    }

    async function otvori() {
      if (radi || $("npo-otvori").disabled) return;
      if (!prijavljen()) { poruka("greska", "Niste prijavljeni. Ništa nije poslato."); return; }
      var moja = gen;
      radi = true; uskladi(); poruka("ucitavanje", "Otvaranje predmeta…");
      var kid = klijent && klijent.id;
      if (!kid) {
        var rk = await api.send("/klijenti", { telo: { tip: "fizicko_lice", ime: tekst($("npo-ime").value).slice(0, 100), prezime: tekst($("npo-prezime").value).slice(0, 100) },
          token: sesija.token(), oblik: function (x) { return x.klijent && ispravanId(x.klijent.id); } });
        if (moja !== gen) return;
        if (!rk.ok) {
          radi = false; uskladi();
          poruka((rk.greska || {}).ishodNepoznat ? "nepoznato" : "greska", (rk.greska || {}).ishodNepoznat
            ? "Ishod upisa klijenta nije poznat. Pretražite kartoteku pre ponovnog pokušaja. Predmet nije otvoren."
            : "Klijent nije upisan. Predmet nije otvoren.");
          return;
        }
        klijent = { id: tekst(rk.podaci.klijent.id), ime: imeKlijenta() };      // ponovni pokušaj ne pravi drugog klijenta
        $("npo-ime").value = ""; $("npo-prezime").value = "";
        kid = klijent.id;
      }
      var telo = { klijent_id: kid, naziv: tekst($("npo-naziv").value).slice(0, 200), opis: tekst($("npo-opis").value).slice(0, 4000),
        tip: tekst($("npo-vrsta").value).slice(0, 50) || "opsti", vrsta_spora: tekst($("npo-vrsta").value).slice(0, 100),
        vrednost_spora: tekst($("npo-vrednost").value).slice(0, 100), protivna_strana: tekst($("npo-protivna").value).slice(0, 200) };
      if (predlog && ispravanDatum(predlog.prvi_rok) && $("npo-rok-upisi").checked) {
        telo.prvi_rok = predlog.prvi_rok; telo.rok_opis = tekst(predlog.rok_opis).slice(0, 300) || "Rok iz opisa problema";
      }
      var r = await api.send("/api/intake/kreiraj", { telo: telo, token: sesija.token(), oblik: function (x) { return x.ok === true || !!x.predmet_id; } });
      if (moja !== gen) return;
      radi = false; uskladi();
      if (r.ok && r.podaci && ispravanId(r.podaci.predmet_id)) { poruka("uspeh", "Predmet je otvoren."); naUspeh(tekst(r.podaci.predmet_id)); return; }
      if (r.ok) { poruka("nepoznato", "Predmet je verovatno otvoren, ali odgovor nije mogao da se pročita. Proverite listu predmeta."); return; }
      var g = r.greska || {};
      poruka(g.ishodNepoznat ? "nepoznato" : "greska", g.ishodNepoznat ? "Ishod nije poznat — predmet je možda otvoren. Proverite listu predmeta pre ponovnog pokušaja."
        : r.status === 409 ? "Predmet sa ovim nazivom je upravo otvoren. Proverite listu predmeta."
        : r.status === 404 ? "Klijent nije pronađen u vašoj kartoteci. Predmet nije otvoren." : "Server je odbio otvaranje. Predmet nije otvoren.");
    }

    $("npo-opis-forma").addEventListener("submit", function (e) { e.preventDefault(); predlozi(); });
    $("npo-predlog").addEventListener("submit", function (e) { e.preventDefault(); otvori(); });
    $("npo-proveri").addEventListener("click", proveriCoi);
    $("npo-coi-potvrda").addEventListener("change", uskladi);
    $("npo-naziv").addEventListener("input", uskladi);
    ["npo-ime", "npo-prezime"].forEach(function (id) { $(id).addEventListener("input", function () { klijent = null; uskladi(); }); });
    $("npo-klijent-pretraga").addEventListener("input", function () { clearTimeout(tajmerPretrage); tajmerPretrage = setTimeout(pretrazi, 250); });

    function ocisti() {
      gen++; radi = false; predlog = null; klijent = null; coi = null;
      if (kPretraga) { kPretraga.abort(); kPretraga = null; }
      $("npo-opis-forma").reset(); $("npo-predlog").reset(); $("npo-predlog").hidden = true; $("npo-klijenti").replaceChildren();
      prikaziCoi(null); poruka(null); $("nd-otvoren").hidden = true;
      prijem.ocisti();
      rezim("rucno");
    }
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) ocisti(); });
    rezim("rucno");
    return { ocisti: ocisti, rezim: rezim, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxNovPredmetPrijem = Object.freeze({ napravi: napravi });
})(window);
