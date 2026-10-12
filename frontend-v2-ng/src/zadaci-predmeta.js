/* Vindex V2 NG — zadaci predmeta (VCR001 T07).
 *
 * Ugovor (routers/zadaci.py):
 *   GET   /api/zadaci/predmet/{id} → {zadaci:[{id, naziv, rok_datum, prioritet, status, updated_at}]}; tuđ predmet → 404
 *   POST  /api/zadaci/kreiraj {naziv 2–200, rok_datum?, prioritet, predmet_id, dodeljen_uid} → {ok, zadatak}
 *         `dodeljen_uid` = prijavljeni korisnik (server dozvoljava samo sebe ili člana kancelarije): bez dodele
 *         zadatak ne bi bio vidljiv na Radnoj listi (`routers/workspace.py` čita po `dodeljen_uid`).
 *   PATCH /api/zadaci/{id}/status {status:"zavrseno", if_updated_at} → 409 ako je izmenjen u međuvremenu.
 */
(function (root) {
  "use strict";

  var PRIORITET = { hitno: "hitno", visoko: "visok prioritet", normalan: "normalan", nisko: "nizak prioritet" };
  var STATUS = { otvoreno: "otvoren", u_toku: "u toku", ceka: "čeka", zavrseno: "završen", otkazano: "otkazan" };
  function tekst(v) { return String(v == null ? "" : v).trim(); }
  function datum(iso) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(tekst(iso)); return m ? m[3] + "." + m[2] + "." + m[1] + "." : ""; }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api;
    var trenutni = null, gen = 0, salje = false;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function poruka(id, st, t) { var n = $(id); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function zakljucaj(da) { salje = da; $("zd-dodaj").disabled = da || !trenutni; }

    async function ucitaj() {
      if (!trenutni) return;
      var moja = ++gen, id = trenutni.id;
      poruka("zd-stanje", "ucitavanje", "Učitavanje zadataka…");
      var r = await api.get("/api/zadaci/predmet/" + encodeURIComponent(id), { token: sesija.token(), oblik: function (x) { return Array.isArray(x.zadaci); } });
      if (moja !== gen || !trenutni || trenutni.id !== id) return;
      $("zd-lista").replaceChildren();
      if (!r.ok) { poruka("zd-stanje", "greska", "Zadaci nisu učitani. Ovo ne znači da ih nema."); return; }
      var lista = r.podaci.zadaci.filter(function (z) { return z && z.id !== undefined && z.id !== null; });
      if (!lista.length) { poruka("zd-stanje", "prazno", "Za ovaj predmet nema zadataka."); return; }
      poruka("zd-stanje", null);
      lista.sort(function (a, b) { var za = a.status === "zavrseno" || a.status === "otkazano", zb = b.status === "zavrseno" || b.status === "otkazano";
        if (za !== zb) return za ? 1 : -1; return (tekst(a.rok_datum) || "9999") < (tekst(b.rok_datum) || "9999") ? -1 : 1; });
      lista.forEach(function (z) {
        var li = el("li", "review"); li.dataset.zadatak = String(z.id);
        li.append(el("span", "review__name", tekst(z.naziv) || "Zadatak"));
        li.append(el("span", "review__meta", [z.rok_datum ? "rok " + datum(z.rok_datum) : "bez roka", PRIORITET[z.prioritet] || tekst(z.prioritet), STATUS[z.status] || tekst(z.status)].filter(Boolean).join(" · ")));
        if (z.status !== "zavrseno" && z.status !== "otkazano") {
          var a = el("span", "review__actions"), b = el("button", "text-btn text-btn--line", "Završeno"); b.type = "button";
          b.setAttribute("aria-label", "Označi kao završen: " + (tekst(z.naziv) || "zadatak"));
          b.addEventListener("click", function () { zavrsi(z, li); });
          a.append(b); li.append(a);
        }
        $("zd-lista").append(li);
      });
    }

    async function zavrsi(z, li) {
      if (!trenutni) return;
      var id = trenutni.id;
      li.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
      var telo = { status: "zavrseno" };
      if (z.updated_at) telo.if_updated_at = z.updated_at;
      var r = await api.send("/api/zadaci/" + encodeURIComponent(String(z.id)) + "/status", { metod: "PATCH", telo: telo, token: sesija.token(),
        oblik: function (x) { return x.ok === true; } });
      if (!trenutni || trenutni.id !== id) return;
      if (r.ok) { poruka("zd-poruka", "uspeh", "Zadatak je označen kao završen."); ucitaj(); return; }
      li.querySelectorAll("button").forEach(function (b) { b.disabled = false; });
      var g = r.greska || {};
      poruka("zd-poruka", g.ishodNepoznat ? "nepoznato" : "greska", g.kod === "CONFLICT" ? "Zadatak je izmenjen u međuvremenu. Lista je osvežena — pokušajte ponovo."
        : g.ishodNepoznat ? "Ishod nije poznat. Osvežite listu pre ponovnog pokušaja." : g.kod === "NOT_FOUND" ? "Zadatak nije dostupan." : "Server je odbio izmenu. Ništa nije promenjeno.");
      if (g.kod === "CONFLICT") ucitaj();
    }

    async function dodaj() {
      if (salje || !trenutni) return;
      var naziv = $("zd-naziv").value.trim(), rok = $("zd-rok").value, prioritet = $("zd-prioritet").value;
      if (naziv.length < 2) { poruka("zd-poruka", "greska", "Naziv zadatka mora imati bar 2 znaka."); $("zd-naziv").focus(); return; }
      if (!PRIORITET.hasOwnProperty(prioritet)) prioritet = "normalan";
      var telo = { naziv: naziv.slice(0, 200), prioritet: prioritet, predmet_id: trenutni.id, dodeljen_uid: sesija.stanje().korisnik };
      if (/^\d{4}-\d{2}-\d{2}$/.test(rok)) telo.rok_datum = rok;
      var id = trenutni.id;
      zakljucaj(true); poruka("zd-poruka", "ucitavanje", "Dodavanje zadatka…");
      var r = await api.send("/api/zadaci/kreiraj", { telo: telo, token: sesija.token(), oblik: function (x) { return x.ok === true; } });
      if (!trenutni || trenutni.id !== id) return;
      zakljucaj(false);
      if (r.ok) { $("zd-forma").reset(); poruka("zd-poruka", "uspeh", "Zadatak je dodat; vidi se i na Radnoj listi (ekran Danas)."); ucitaj(); return; }
      var g = r.greska || {};
      poruka("zd-poruka", g.ishodNepoznat ? "nepoznato" : "greska", g.ishodNepoznat ? "Ishod nije poznat. Osvežite listu pre ponovnog dodavanja."
        : g.kod === "NOT_FOUND" ? "Predmet nije dostupan. Zadatak nije dodat." : "Server je odbio zadatak. Ništa nije dodato.");
    }

    function postavi(predmet, aktivan) {
      if (trenutni && trenutni.id === predmet.id && trenutni.korisnik === sesija.stanje().korisnik) { if (aktivan) aktiviraj(); return; }
      ocisti();
      trenutni = { id: predmet.id, korisnik: sesija.stanje().korisnik, ucitano: false };
      zakljucaj(false);
      if (aktivan) aktiviraj();
    }
    function aktiviraj() { if (!trenutni || trenutni.ucitano) return; trenutni.ucitano = true; ucitaj(); }
    function ocisti() { gen++; trenutni = null; $("zd-forma").reset(); $("zd-lista").replaceChildren(); poruka("zd-stanje", null); poruka("zd-poruka", null); zakljucaj(false); }

    $("zd-forma").addEventListener("submit", function (e) { e.preventDefault(); dodaj(); });
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) ocisti(); });
    return { postavi: postavi, aktiviraj: aktiviraj, ocisti: ocisti, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxZadaciPredmeta = Object.freeze({ napravi: napravi });
})(window);
