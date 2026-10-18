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
 *   VCR001 T05: GET /api/staging/{id} → ceo nacrt (tekst); PATCH /api/staging/{id}/tekst {tekst} → čuva izmenu
 *        SAMO dok je nacrt na čekanju (409 posle odluke). Odobrava se tek OTVOREN nacrt, i to sačuvan tekst:
 *        nesačuvana izmena se prvo čuva, pa se odobrava — u bazu znanja ulazi ono što je advokat video.
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
    var genOt = 0, radiOvera = false;
    var trenutni = null, katalog = null, gen = 0, genO = 0, genK = 0, k = null, kO = null, kK = null, salje = false, nacrt = null;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function poruka(id, st, t) { var n = $(id); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function prekini(x) { if (x) x.abort(); return null; }
    function zakljucaj(da) { salje = da; $("nc-generisi").disabled = da || !katalog; $("nc-generisi").textContent = da ? "Izrada nacrta…" : "Izradi nacrt"; }

    var ZA_GENERISAN = "Tekst nacrta (izmene ovde ulaze samo u .docx koji preuzmete; ne čuvaju se na serveru)";
    function ocistiNacrt() {
      nacrt = null; genOt++;
      $("nc-rezultat").hidden = true; $("nc-tekst").value = ""; $("nc-naslov-nacrta").textContent = "";
      $("nc-tekst").readOnly = false; $("nc-tekst-oznaka").textContent = ZA_GENERISAN;
      $("nc-sacuvaj").hidden = true; $("nc-odobri").hidden = true;
      poruka("nc-provera", null); poruka("nc-docx-poruka", null); poruka("nc-otvoren-stanje", null);
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
        var akcije = el("span", "review__actions");
        var ot = el("button", "text-btn text-btn--line", tekst(x.status) === "pending" ? "Otvori i pregledaj" : "Otvori"); ot.type = "button";
        ot.setAttribute("aria-label", "Otvori nacrt: " + (tekst(x.naziv) || tekst(x.tip) || "Nacrt"));
        ot.addEventListener("click", function () { otvori(String(x.id)); });
        akcije.append(ot);
        if (tekst(x.status) === "pending") {
          // Odobrenje je u otvorenom nacrtu (VCR001 T05): ne odobrava se tekst koji advokat nije video.
          var ne = el("button", "text-btn", "Odbij"); ne.type = "button";
          ne.addEventListener("click", function () { odluci(String(x.id), "reject", li); });
          akcije.append(ne);
        }
        li.append(akcije);
        $("nc-overa-lista").append(li);
      });
    }
    async function odluci(sid, radnja, li) {
      if (!trenutni) return false;
      var id = trenutni.id, moja = genO;
      if (li) li.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
      var r = await api.send("/api/staging/" + encodeURIComponent(sid) + "/" + radnja, { token: sesija.token(), oblik: function (x) { return typeof x.status === "string"; } });
      if (moja !== genO || !trenutni || trenutni.id !== id) return false;
      if (r.ok && r.podaci) {
        poruka("nc-overa-poruka", "uspeh", radnja === "reject" ? "Nacrt je odbijen." : (r.podaci.indexed ? "Nacrt je odobren i dodat u bazu znanja kancelarije."
          : r.podaci.razlog === "INDEKSIRANJE_NIJE_USPELO" ? "Nacrt je odobren, ali upis u bazu znanja kancelarije nije uspeo — nacrt nije pretraživ u znanju kancelarije."
          : "Nacrt je odobren. Nije dodat u bazu znanja kancelarije jer ocena kvaliteta nije dovoljna."));
        if (nacrt && nacrt.sid === sid) prikaziOtvoren({ status: radnja === "reject" ? "rejected" : "approved" });
        ucitajOveru();
        return true;
      }
      if (li) li.querySelectorAll("button").forEach(function (b) { b.disabled = false; });
      var g = r.greska || {};
      poruka("nc-overa-poruka", g.ishodNepoznat ? "nepoznato" : "greska", g.ishodNepoznat ? "Ishod nije poznat. Osvežite listu pre ponovnog pokušaja."
        : g.kod === "NOT_FOUND" ? "Nacrt nije dostupan. Ništa nije promenjeno." : "Server je odbio zahtev. Ništa nije promenjeno.");
      return false;
    }

    /* ── Otvoren nacrt sa overe (VCR001 T05) ── */
    function prikaziOtvoren(promena) {
      if (!nacrt || !nacrt.sid) return;
      if (promena) Object.assign(nacrt, promena);
      var naCekanju = nacrt.status === "pending";
      $("nc-tekst").readOnly = !naCekanju;
      $("nc-sacuvaj").hidden = !naCekanju; $("nc-odobri").hidden = !naCekanju;
      $("nc-tekst-oznaka").textContent = naCekanju
        ? "Tekst nacrta na overi (izmene sačuvajte; odobrava se sačuvan tekst)"
        : "Tekst nacrta (" + (STATUS_OVERE[nacrt.status] || nacrt.status) + " — više se ne menja; izmene ulaze samo u .docx)";
      poruka("nc-otvoren-stanje", naCekanju ? "nepoznato" : "uspeh",
        (naCekanju ? "Čeka vašu overu." : "Nacrt je " + (STATUS_OVERE[nacrt.status] || nacrt.status) + ".")
        + (nacrt.izmenjeno ? " Tekst je izmenio advokat" + (nacrt.izmenjenoAt ? " (" + datum(nacrt.izmenjenoAt) + ")" : "") + "." : " Tekst je onakav kakav je Vindex izradio."));
    }
    async function otvori(sid) {
      if (!trenutni) return;
      var moja = ++genOt, id = trenutni.id;
      poruka("nc-overa-poruka", "ucitavanje", "Otvaranje nacrta…");
      var r = await api.get("/api/staging/" + encodeURIComponent(sid), { token: sesija.token(), oblik: function (x) { return typeof x.tekst === "string" && typeof x.status === "string"; } });
      if (moja !== genOt || !trenutni || trenutni.id !== id) return;
      if (!r.ok) {
        var g = r.greska || {};
        poruka("nc-overa-poruka", "greska", g.kod === "NOT_FOUND" ? "Nacrt nije dostupan." : "Nacrt nije otvoren. Ništa nije promenjeno.");
        return;
      }
      poruka("nc-overa-poruka", null); ocistiNacrt(); genOt = moja;
      var x = r.podaci;
      nacrt = { sid: sid, tekst: x.tekst, sacuvan: x.tekst, naziv: tekst(x.naziv) || "Nacrt", tip: tekst(x.tip), status: tekst(x.status),
                izmenjeno: !!x.izmenio_advokat, izmenjenoAt: x.izmenjeno_at };
      $("nc-naslov-nacrta").textContent = "Nacrt: " + nacrt.naziv;
      $("nc-tekst").value = nacrt.tekst;
      $("nc-rezultat").hidden = false;
      prikaziOtvoren();
      $("nc-naslov-nacrta").setAttribute("tabindex", "-1"); $("nc-naslov-nacrta").focus();
    }
    async function sacuvaj() {
      if (!nacrt || !nacrt.sid || nacrt.status !== "pending" || radiOvera) return false;
      var t = $("nc-tekst").value;
      if (!t.trim()) { poruka("nc-otvoren-stanje", "greska", "Nacrt ne može biti prazan. Ništa nije sačuvano."); return false; }
      if (t === nacrt.sacuvan) return true;
      var sid = nacrt.sid, moja = genOt;
      radiOvera = true; $("nc-sacuvaj").disabled = true; $("nc-odobri").disabled = true;
      poruka("nc-otvoren-stanje", "ucitavanje", "Čuvanje izmena…");
      var r = await api.send("/api/staging/" + encodeURIComponent(sid) + "/tekst", { metod: "PATCH", telo: { tekst: t.slice(0, 100000) }, token: sesija.token(),
        oblik: function (x) { return x.sacuvano === true; } });
      radiOvera = false; $("nc-sacuvaj").disabled = false; $("nc-odobri").disabled = false;
      if (moja !== genOt || !nacrt || nacrt.sid !== sid) return false;
      if (r.ok && r.podaci) {
        nacrt.sacuvan = t; nacrt.izmenjeno = true; nacrt.izmenjenoAt = r.podaci.izmenjeno_at;
        prikaziOtvoren();
        poruka("nc-otvoren-stanje", "uspeh", "Izmene su sačuvane. Čeka vašu overu.");
        return true;
      }
      var g = r.greska || {};
      if (g.kod === "CONFLICT") { poruka("nc-otvoren-stanje", "greska", "Nacrt je u međuvremenu odobren ili odbijen — izmena nije sačuvana."); ucitajOveru(); return false; }
      poruka("nc-otvoren-stanje", g.ishodNepoznat ? "nepoznato" : "greska", g.ishodNepoznat
        ? "Ishod čuvanja nije poznat. Otvorite nacrt ponovo pre odobrenja." : "Izmene nisu sačuvane. Tekst je i dalje na ekranu.");
      return false;
    }
    async function odobri() {
      if (!nacrt || !nacrt.sid || nacrt.status !== "pending" || radiOvera) return;
      var sid = nacrt.sid;
      if (!(await sacuvaj())) return;                         // odobrava se SAČUVAN tekst — nikad onaj sa ekrana bez čuvanja
      if (!nacrt || nacrt.sid !== sid) return;
      radiOvera = true; $("nc-odobri").disabled = true; $("nc-sacuvaj").disabled = true;
      await odluci(sid, "approve", null);
      radiOvera = false; $("nc-odobri").disabled = false; $("nc-sacuvaj").disabled = false;
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
    $("nc-sacuvaj").addEventListener("click", sacuvaj);
    $("nc-odobri").addEventListener("click", odobri);
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) { katalog = null; ocisti(); } });

    return { postavi: postavi, aktiviraj: aktiviraj, ocisti: ocisti, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxNacrtPredmeta = Object.freeze({ napravi: napravi });
})(window);
