/* Vindex V2 NG — savetnik (agent) na zahtev u predmetu, kroz čuvar citata (VCR001 T06).
 *
 * Ugovori (routers/multi_agent.py):
 *   GET  /api/agents/lista → {agenti:[{id, naziv, opis}]}   (zatvoren spisak; nudi se SAMO on)
 *   POST /api/agents/run {agent, task, predmet_id} → {odgovor, naziv, provera_citata, kontekst_predmeta}
 *        provera_citata.status: PROVERENI | NEPROVERENI | BEZ_CITATA | NEPOZNATO (pad provere — nikad „provereno“)
 *        Svaki citiran član je proveren protiv izvora iz pravne baze koje je savetnik dobio (kanonski čuvar,
 *        isti kao pravno pitanje); dokumenti predmeta nisu izvor za proveru zakona.
 *   `multi_agent` je profesionalna funkcija: 403 se saopštava, ne skriva.
 * Odgovor se prikazuje kao tekst (bez HTML-a). Generisanje se nikad ne ponavlja automatski (trošak).
 */
(function (root) {
  "use strict";

  var NAZIV = { intake: "Prijem i klasifikacija", research: "Pravno istraživanje", drafting: "Pisanje podnesaka",
                litigation: "Parnična strategija", billing: "Troškovi i naplata", deadline: "Rokovi" };
  var EMODZI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}]/gu;
  function tekst(v) { return String(v == null ? "" : v).trim(); }
  function cisto(t) { return String(t || "").replace(/\*\*/g, "").replace(EMODZI, "").trim(); }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api;
    var trenutni = null, katalog = null, gen = 0, k = null, kK = null, salje = false;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function poruka(id, st, t) { var n = $(id); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function zakljucaj(da) { salje = da; $("ag-posalji").disabled = da || !katalog; $("ag-posalji").textContent = da ? "Savetnik radi…" : "Pokreni savetnika"; }
    function ocistiOdgovor() {
      $("ag-odgovor").hidden = true; $("ag-odgovor-naslov").textContent = "";
      $("ag-citati").replaceChildren(); $("ag-tekst").replaceChildren(); poruka("ag-kontekst", null);
    }
    function ocisti() {
      gen++; if (k) k.abort(); if (kK) kK.abort(); k = null; kK = null;
      trenutni = null; zakljucaj(false);
      $("ag-forma").reset(); poruka("ag-stanje", null); ocistiOdgovor();
    }

    async function ucitajKatalog() {
      if (katalog) { zakljucaj(salje); return; }
      kK = new AbortController();
      var r = await api.get("/api/agents/lista", { token: sesija.token(), signal: kK.signal, oblik: function (x) { return Array.isArray(x.agenti); } });
      kK = null;
      if (!r.ok) { if (r.greska && r.greska.kod === "ABORTED") return; poruka("ag-stanje", "greska", "Spisak savetnika nije učitan. Savetnik trenutno nije dostupan."); return; }
      var lista = r.podaci.agenti.filter(function (a) { return a && NAZIV.hasOwnProperty(a.id); });
      if (!lista.length) { poruka("ag-stanje", "greska", "Nijedan savetnik nije dostupan."); return; }
      katalog = lista;
      var s = $("ag-agent"); s.replaceChildren();
      lista.forEach(function (a) { var op = el("option", null, NAZIV[a.id]); op.value = a.id; s.append(op); });
      opis(); zakljucaj(salje);
    }
    function opis() {
      var a = (katalog || []).filter(function (x) { return x.id === $("ag-agent").value; })[0];
      $("ag-agent-pomoc").textContent = a ? cisto(a.opis) : "";
    }

    function prikaziCitate(p) {
      var ul = $("ag-citati"); ul.replaceChildren();
      function upozorenje(kljuc, naslov, telo, nivo) {
        var li = el("li", nivo === "ok" ? "warn warn--ok" : "warn"); li.dataset.kljuc = kljuc;
        li.append(el("p", "warn__title", naslov)); if (telo) li.append(telo); ul.append(li);
      }
      var st = p && tekst(p.status);
      if (st === "PROVERENI") { upozorenje("citati-provereni", "Svi citirani članovi (" + p.ukupno + ") potvrđeni su u izvorima iz pravne baze.", null, "ok"); return; }
      if (st === "BEZ_CITATA") { upozorenje("bez-citata", "Odgovor ne citira članove zakona.", null, "ok"); return; }
      if (st === "NEPROVERENI") {
        var n = (p.neprovereni || []).length;
        var lista = el("ul", "warn__list");
        (p.neprovereni || []).forEach(function (c) {
          lista.append(el("li", null, "Član " + tekst(c.clan) + (c.zakon ? " (" + tekst(c.zakon) + ")" : "") + (c.razlog ? " — " + tekst(c.razlog) : "")));
        });
        upozorenje("citati-neprovereni", n + (n === 1 ? " citiran član nije potvrđen" : " citiranih članova nije potvrđeno") + " u pravnoj bazi. Proverite u izvoru pre upotrebe.", lista);
        return;
      }
      upozorenje("citati-nepoznato", "Provera citata nije izvršena. Ne oslanjajte se na navedene članove bez provere u izvoru.", null);
    }
    function prikaziTekst(t) {
      var telo = $("ag-tekst"); telo.replaceChildren();
      var pasus = [];
      function zatvori() { var x = cisto(pasus.join("\n")); if (x) telo.append(el("p", "answer__p", x)); pasus = []; }
      String(t || "").replace(/\r\n/g, "\n").split("\n").forEach(function (r) {
        var m = /^\s*#{1,6}\s*(.*)$/.exec(r);
        if (m) { zatvori(); var h = cisto(m[1]); if (h) telo.append(el("h4", "answer__h", h)); return; }
        if (!r.trim()) { zatvori(); return; }
        pasus.push(r);
      });
      zatvori();
    }

    async function pokreni() {
      if (salje || !trenutni || !katalog) return;
      var agent = $("ag-agent").value, zadatak = $("ag-zadatak").value.trim();
      if (!NAZIV.hasOwnProperty(agent) || !katalog.some(function (a) { return a.id === agent; })) { poruka("ag-stanje", "greska", "Izaberite savetnika sa spiska."); return; }
      if (zadatak.length < 10) { poruka("ag-stanje", "greska", "Opišite zadatak (bar 10 znakova)."); $("ag-zadatak").focus(); return; }
      var moja = ++gen, id = trenutni.id, korisnik = sesija.stanje().korisnik;
      k = new AbortController(); zakljucaj(true); ocistiOdgovor();
      poruka("ag-stanje", "ucitavanje", "Savetnik radi i proverava citate… (do minut)");
      var r = await api.send("/api/agents/run", { telo: { agent: agent, task: zadatak.slice(0, 2000), predmet_id: id }, token: sesija.token(), signal: k.signal,
        oblik: function (x) { return typeof x.odgovor === "string" && x.odgovor.trim() !== ""; } });
      if (moja !== gen || !trenutni || trenutni.id !== id || sesija.stanje().korisnik !== korisnik) return;
      k = null; zakljucaj(false);
      if (r.ok && r.podaci) {
        poruka("ag-stanje", null);
        $("ag-odgovor-naslov").textContent = "Savetnik: " + NAZIV[agent];
        prikaziCitate(r.podaci.provera_citata);
        if (r.podaci.kontekst_predmeta === false) poruka("ag-kontekst", "nepoznato", "Podaci ovog predmeta NISU pročitani; savet je opšti.");
        else if (r.podaci.kontekst_predmeta === true) poruka("ag-kontekst", "uspeh", "Savet je dat uz podatke i dokumente ovog predmeta.");
        prikaziTekst(r.podaci.odgovor);
        $("ag-odgovor").hidden = false;
        return;
      }
      if (r.ok) { poruka("ag-stanje", "nepoznato", "Savetnik je odgovorio, ali odgovor nije mogao da se pročita. Pokušajte ponovo."); return; }
      var g = r.greska || {};
      if (r.status === 503) { poruka("ag-stanje", "greska", "AI servis trenutno nije dostupan. Savet nije dobijen; pokušajte kasnije."); return; }
      if (g.ishodNepoznat) { poruka("ag-stanje", "nepoznato", "Odgovor nije dobijen: veza je prekinuta ili server nije odgovorio ispravno. Ne ponavljajte odmah — rad je možda naplaćen."); return; }
      poruka("ag-stanje", "greska", {
        FORBIDDEN: "Savetnik nije dostupan za vaš nalog (profesionalni paket) ili su krediti potrošeni.",
        RATE_LIMITED: "Previše zahteva u kratkom roku. Pokušajte ponovo malo kasnije.",
        AUTH_REQUIRED: "Prijava više nije važeća.",
        VALIDATION_ERROR: "Server nije prihvatio zahtev.",
      }[g.kod] || "Server je odbio zahtev. Savet nije dobijen.");
    }

    /* Spisak se čita tek kad je kartica pitanja otvorena (ugovor „cena“: otvaranje drugih kartica ne zove ništa više). */
    function postavi(predmet, aktivan) {
      if (trenutni && trenutni.id === predmet.id && trenutni.korisnik === sesija.stanje().korisnik) { if (aktivan) aktiviraj(); return; }
      ocisti();
      trenutni = { id: predmet.id, korisnik: sesija.stanje().korisnik, ucitano: false };
      if (aktivan) aktiviraj();
    }
    function aktiviraj() { if (!trenutni || trenutni.ucitano) return; trenutni.ucitano = true; ucitajKatalog(); }

    $("ag-forma").addEventListener("submit", function (e) { e.preventDefault(); pokreni(); });
    $("ag-agent").addEventListener("change", opis);
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) { katalog = null; ocisti(); } });

    return { postavi: postavi, aktiviraj: aktiviraj, ocisti: ocisti, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxAgentiPredmeta = Object.freeze({ napravi: napravi });
})(window);
