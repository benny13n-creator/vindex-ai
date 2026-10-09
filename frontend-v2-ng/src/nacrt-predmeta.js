/* Vindex V2 NG — nacrt podneska u predmetu + advokatska overa (NS005, CAP-060/061/063).
 *
 * Ugovori (routers/drafting.py):
 *   GET  /api/podnesak/types → {tipovi:[{tip, naziv}]}   (zatvoren spisak; nudi se SAMO on)
 *   GET  /api/courts         → {sudovi: {grupa: [{naziv, adresa, grad}]}}
 *   POST /api/podnesak {tip, opis 20–5000, sud_naziv?, sud_adresa?, predmet_id}
 *        → {status, odgovor, tip, naziv, critique_applied: true|false|null, ai_generated}
 *        Backend: predmet mora biti pozivaočev (404 pre modela), tip van spiska → 422 pre modela,
 *        šablon sam nosi „NAPOMENA SISTEMA … mora biti pregledan od strane ovlašćenog advokata",
 *        provera navoda menja izmišljen član sa „[proveriti relevantan član]",
 *        `critique_applied:false` = ta provera NIJE potvrđena; nacrt odlazi na overu (staging).
 *   POST /api/nacrti/export/docx {tekst, naslov, tip} → .docx
 *   GET  /api/staging/predmet/{id} → {stavke}; POST /api/staging/{id}/approve|reject
 *        Odobrenje može uneti nacrt u bazu znanja kancelarije (samo iznad praga kvaliteta).
 * Ništa od suda, roka, nadležnosti ni takse ovde NIJE provereno i ne tvrdi se.
 * Generisanje se nikad ne ponavlja automatski (trošak); dupli klik je zaključan.
 */
(function (root) {
  "use strict";

  var DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  function tekst(v) { return String(v == null ? "" : v).trim(); }
  function datum(iso) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(tekst(iso)); return m ? m[3] + "." + m[2] + "." + m[1] + "." : ""; }
  var STATUS_OVERE = { pending: "čeka overu", approved: "odobren", rejected: "odbijen" };

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api;
    var trenutni = null, katalog = null, gen = 0, genO = 0, genK = 0, k = null, kO = null, kK = null, salje = false, nacrt = null;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function poruka(id, st, t) { var n = $(id); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function prekini(x) { if (x) x.abort(); return null; }
    function zakljucaj(da) { salje = da; $("nc-generisi").disabled = da || !katalog; $("nc-generisi").textContent = da ? "Izrada nacrta…" : "Izradi nacrt"; }

    function ocistiNacrt() {
      nacrt = null;
      $("nc-rezultat").hidden = true; $("nc-tekst").value = ""; $("nc-naslov-nacrta").textContent = "";
      poruka("nc-provera", null); poruka("nc-docx-poruka", null);
    }
    function ocisti() {
      gen++; genO++; genK++; k = prekini(k); kO = prekini(kO); kK = prekini(kK);
      trenutni = null; zakljucaj(false);
      $("nc-forma").reset(); poruka("nc-poruka", null); ocistiNacrt();
      $("nc-overa-lista").replaceChildren(); poruka("nc-overa-stanje", null);
    }

    /* ── Katalog tipova i sudova (jednom po prijavi) ── */
    async function ucitajKatalog() {
      if (katalog) return;
      var moja = ++genK; kK = prekini(kK); kK = new AbortController();
      poruka("nc-poruka", "ucitavanje", "Učitavanje vrsta podnesaka…");
      var t = sesija.token() || undefined;
      var r1 = await api.get("/api/podnesak/types", { token: t, signal: kK.signal, oblik: function (x) { return Array.isArray(x.tipovi); } });
      var r2 = await api.get("/api/courts", { token: t, signal: kK.signal, oblik: function (x) { return x.sudovi && typeof x.sudovi === "object"; } });
      if (moja !== genK) return;
      kK = null;
      if (!r1.ok) { poruka("nc-poruka", "greska", "Spisak vrsta podnesaka nije učitan, pa nacrt ne može da se izradi. Osvežite stranicu."); zakljucaj(false); return; }
      var tipovi = r1.podaci.tipovi.filter(function (x) { return x && tekst(x.tip) && tekst(x.naziv); });
      var sel = $("nc-tip"); sel.replaceChildren(el("option", null, "Izaberite vrstu podneska")); sel.firstChild.value = "";
      tipovi.forEach(function (x) { var op = el("option", null, tekst(x.naziv)); op.value = tekst(x.tip); sel.append(op); });
      var sud = $("nc-sud"); sud.replaceChildren(el("option", null, "Bez unapred izabranog suda")); sud.firstChild.value = "";
      if (r2.ok) {
        Object.keys(r2.podaci.sudovi).forEach(function (grupa) {
          var lista = r2.podaci.sudovi[grupa];
          if (!Array.isArray(lista)) return;
          var og = d.createElement("optgroup"); og.label = grupa;
          lista.forEach(function (s, i) { if (!s || !tekst(s.naziv)) return; var op = el("option", null, tekst(s.naziv)); op.value = grupa + "\u0001" + i; og.append(op); });
          sud.append(og);
        });
      }
      katalog = { tipovi: tipovi, sudovi: r2.ok ? r2.podaci.sudovi : null };
      $("nc-sud-red").hidden = !r2.ok;
      poruka("nc-poruka", r2.ok ? null : "greska", r2.ok ? "" : "Spisak sudova nije učitan; nacrt se može izraditi bez unapred izabranog suda.");
      zakljucaj(false);
    }

    /* ── Nacrti na overi ── */
    async function ucitajOveru() {
      if (!trenutni) return;
      var moja = ++genO, id = trenutni.id; kO = prekini(kO); kO = new AbortController();
      poruka("nc-overa-stanje", "ucitavanje", "Učitavanje nacrta na overi…");
      var r = await api.get("/api/staging/predmet/" + encodeURIComponent(id), { token: sesija.token(), signal: kO.signal, oblik: function (x) { return Array.isArray(x.stavke); } });
      if (moja !== genO || !trenutni || trenutni.id !== id) return;
      kO = null;
      $("nc-overa-lista").replaceChildren();
      if (!r.ok) { if (r.greska && r.greska.kod === "ABORTED") return; poruka("nc-overa-stanje", "greska", "Nacrti na overi nisu učitani. Ovo nije prazna lista."); return; }
      var st = r.podaci.stavke.filter(function (x) { return x && x.id !== undefined && x.id !== null; });
      if (!st.length) { poruka("nc-overa-stanje", "prazno", "Za ovaj predmet nema nacrta na overi."); return; }
      poruka("nc-overa-stanje", null);
      st.forEach(function (x) {
        var li = el("li", "review");
        li.dataset.stavka = String(x.id);
        li.append(el("span", "review__name", tekst(x.naziv) || tekst(x.tip) || "Nacrt"));
        li.append(el("span", "review__meta", [datum(x.created_at), STATUS_OVERE[tekst(x.status)] || tekst(x.status)].filter(Boolean).join(" · ")));
        if (tekst(x.status) === "pending") {
          var akcije = el("span", "review__actions");
          var da = el("button", "text-btn text-btn--line", "Odobri"); da.type = "button";
          var ne = el("button", "text-btn", "Odbij"); ne.type = "button";
          da.addEventListener("click", function () { odluci(String(x.id), "approve", li); });
          ne.addEventListener("click", function () { odluci(String(x.id), "reject", li); });
          akcije.append(da, ne); li.append(akcije);
        }
        $("nc-overa-lista").append(li);
      });
    }
    async function odluci(sid, radnja, li) {
      if (!trenutni) return;
      var id = trenutni.id, moja = genO;
      li.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
      var r = await api.send("/api/staging/" + encodeURIComponent(sid) + "/" + radnja, { token: sesija.token(), oblik: function (x) { return typeof x.status === "string"; } });
      if (moja !== genO || !trenutni || trenutni.id !== id) return;
      if (r.ok && r.podaci) {
        poruka("nc-overa-poruka", "uspeh", radnja === "reject" ? "Nacrt je odbijen." : (r.podaci.indexed ? "Nacrt je odobren i dodat u bazu znanja kancelarije."
          : "Nacrt je odobren. Nije dodat u bazu znanja kancelarije jer ocena kvaliteta nije dovoljna."));
        ucitajOveru();
        return;
      }
      li.querySelectorAll("button").forEach(function (b) { b.disabled = false; });
      var g = r.greska || {};
      poruka("nc-overa-poruka", g.ishodNepoznat ? "nepoznato" : "greska", g.ishodNepoznat ? "Ishod nije poznat. Osvežite listu pre ponovnog pokušaja."
        : g.kod === "NOT_FOUND" ? "Nacrt nije dostupan. Ništa nije promenjeno." : "Server je odbio zahtev. Ništa nije promenjeno.");
    }

    /* ── Izrada nacrta ── */
    async function generisi() {
      if (salje || !trenutni || !katalog) return;
      var tip = $("nc-tip").value, opis = $("nc-opis").value.trim();
      if (!katalog.tipovi.some(function (x) { return x.tip === tip; })) { poruka("nc-poruka", "greska", "Izaberite vrstu podneska sa spiska."); $("nc-tip").focus(); return; }
      if (opis.length < 20) { poruka("nc-poruka", "greska", "Opis činjenica mora imati bar 20 znakova."); $("nc-opis").focus(); return; }
      var telo = { tip: tip, opis: opis.slice(0, 5000), predmet_id: trenutni.id };
      var sv = $("nc-sud").value;
      if (sv && katalog.sudovi) {
        var del = sv.split("\u0001"), s = (katalog.sudovi[del[0]] || [])[Number(del[1])];
        if (s) { telo.sud_naziv = tekst(s.naziv).slice(0, 200); if (tekst(s.adresa)) telo.sud_adresa = tekst(s.adresa).slice(0, 300); }
      }
      var ss = sesija.stanje();
      if (ss.stanje !== sesija.STANJA.PRIJAVLJEN || ss.korisnik !== trenutni.korisnik) { poruka("nc-poruka", "greska", "Niste prijavljeni. Nacrt nije izrađen."); return; }
      var moja = ++gen, id = trenutni.id, korisnik = trenutni.korisnik;
      k = new AbortController();
      zakljucaj(true); ocistiNacrt();
      poruka("nc-poruka", "ucitavanje", "Izrada nacrta i provera navoda… (do minut)");
      var r = await api.send("/api/podnesak", { telo: telo, token: sesija.token(), signal: k.signal, oblik: function (x) { return typeof x.odgovor === "string" && x.odgovor.trim() !== ""; } });
      if (moja !== gen || !trenutni || trenutni.id !== id || sesija.stanje().korisnik !== korisnik) return;
      k = null; zakljucaj(false);
      if (r.ok && r.podaci) {
        poruka("nc-poruka", null);
        nacrt = { tekst: r.podaci.odgovor, naziv: tekst(r.podaci.naziv) || "Nacrt", tip: tip };
        $("nc-naslov-nacrta").textContent = "Nacrt: " + nacrt.naziv;
        $("nc-tekst").value = nacrt.tekst;
        $("nc-rezultat").hidden = false;
        var mesta = (nacrt.tekst.match(/\[proveriti relevantan član\]/g) || []).length;
        if (r.podaci.critique_applied === false) poruka("nc-provera", "nepoznato", "Provera izmišljenih navoda NIJE potvrđena za ovaj nacrt. Svaki naveden član i broj odluke proverite u izvoru.");
        else if (r.podaci.critique_applied === null) poruka("nc-provera", "nepoznato", "Prikazan je nacrt iste vrste za ovaj predmet izrađen pre nekoliko minuta (nije izrađen ponovo).");
        else if (mesta) poruka("nc-provera", "nepoznato", "Nacrt sadrži " + mesta + (mesta === 1 ? " mesto označeno" : " mesta označena") + " „[proveriti relevantan član]“ — tamo član nije potkrepljen izvorom.");
        setTimeout(function () { if (trenutni && trenutni.id === id) ucitajOveru(); }, 1500);
        return;
      }
      if (r.ok) { poruka("nc-poruka", "nepoznato", "Nacrt je izrađen, ali odgovor nije mogao da se pročita. Proverite nacrte na overi."); return; }
      var g = r.greska || {};
      if (g.ishodNepoznat) { poruka("nc-poruka", "nepoznato", "Nacrt nije dobijen: veza je prekinuta ili server nije odgovorio ispravno. Možda je izrađen — proverite nacrte na overi pre ponovnog pokušaja."); setTimeout(ucitajOveru, 1500); return; }
      poruka("nc-poruka", "greska", {
        VALIDATION_ERROR: "Server nije prihvatio vrstu ili opis. Nacrt nije izrađen.",
        NOT_FOUND: "Predmet nije dostupan. Nacrt nije izrađen.",
        FORBIDDEN: "Izrada nacrta nije dostupna za vaš nalog ili su krediti potrošeni.",
        RATE_LIMITED: "Previše nacrta u kratkom roku (najviše 5 u minutu). Pokušajte ponovo malo kasnije.",
        AUTH_REQUIRED: "Prijava više nije važeća. Nacrt nije izrađen.",
      }[g.kod] || "Server je odbio zahtev. Nacrt nije izrađen.");
    }

    async function docx() {
      if (!nacrt || !trenutni) return;
      var t = $("nc-tekst").value;
      if (!t.trim()) { poruka("nc-docx-poruka", "greska", "Nacrt je prazan."); return; }
      $("nc-docx").disabled = true;
      poruka("nc-docx-poruka", "ucitavanje", "Priprema .docx fajla…");
      var r = await api.preuzmi("/api/nacrti/export/docx", { telo: { tekst: t.slice(0, 100000), naslov: nacrt.naziv.slice(0, 200), tip: nacrt.tip }, token: sesija.token(), tip: DOCX });
      $("nc-docx").disabled = false;
      if (!r.ok) { poruka("nc-docx-poruka", "greska", "Fajl nije preuzet (" + (r.greska.kod === "SERVER_ERROR" ? "greška na serveru" : "neispravan odgovor") + "). Nacrt je i dalje na ekranu."); return; }
      var url = URL.createObjectURL(r.blob), a = el("a");
      a.href = url; a.download = r.ime || "Nacrt.docx"; d.body.append(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
      poruka("nc-docx-poruka", "uspeh", "Fajl „" + (r.ime || "Nacrt.docx") + "“ je preuzet.");
    }

    function postavi(predmet, aktivan) {
      if (trenutni && trenutni.id === predmet.id && trenutni.korisnik === sesija.stanje().korisnik) { if (aktivan) aktiviraj(); return; }
      ocisti();
      trenutni = { id: predmet.id, korisnik: sesija.stanje().korisnik, ucitano: false };
      if (aktivan) aktiviraj();
    }
    function aktiviraj() {
      if (!trenutni || trenutni.ucitano) return;
      trenutni.ucitano = true;
      ucitajKatalog();
      ucitajOveru();
    }

    $("nc-forma").addEventListener("submit", function (e) { e.preventDefault(); generisi(); });
    $("nc-docx").addEventListener("click", docx);
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) { katalog = null; ocisti(); } });

    return { postavi: postavi, aktiviraj: aktiviraj, ocisti: ocisti, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxNacrtPredmeta = Object.freeze({ napravi: napravi });
})(window);
