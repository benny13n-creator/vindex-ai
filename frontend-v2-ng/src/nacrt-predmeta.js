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
 *   NS4 O3: POST /api/staging/{id}/ponovi-upis — samo kad server kaže `ponovni_upis_moguc` (odobren, iznad praga,
 *        upis nije potvrđen kao potpun); konačnu podobnost proverava server (atomsko preuzimanje).
 *   MIR001 C3b: nacrt iz spisa (AI radni predlog) i dokument za sud imaju svoj tok — v. „AI radni predlog → izričito
 *        usvajanje → dokument za sud“ niže; ovde ih lista samo prikazuje i otvara.
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
  var TIP_PREDLOGA = "nacrt_iz_spisa", TIP_ZA_SUD = "dokument_za_sud";
  function statusStavke(x) {
    var st = tekst(x.status);
    if (tekst(x.tip) === TIP_PREDLOGA) return st === "rejected" ? "AI predlog — odbijen" : "AI predlog — za pregled, ne izvozi se";
    if (tekst(x.tip) === TIP_ZA_SUD) return { pending: "dokument za sud — čeka vaše odobrenje", approved: "dokument za sud — odobren", rejected: "dokument za sud — odbijen" }[st] || st;
    return STATUS_OVERE[st] || st;
  }

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
      $("nc-tekst").hidden = false; $("nc-tekst-oznaka").hidden = false; $("nc-akcije").hidden = false;
      $("nc-usvajanje").hidden = true; $("nc-stavke").replaceChildren(); $("nc-tacke").replaceChildren();
      $("nc-razlozi").replaceChildren(); $("nc-sud-tekst").value = ""; $("nc-napomene").textContent = "";
      poruka("nc-sud-poruka", null);
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
        li.append(el("span", "review__meta", [datum(x.created_at), statusStavke(x)].filter(Boolean).join(" · ")));
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
        if (x.ponovni_upis_moguc === true) {
          var pu = el("button", "text-btn", "Ponovi upis u bazu znanja"); pu.type = "button";
          pu.addEventListener("click", function () { odluci(String(x.id), "ponovi-upis", li); });
          akcije.append(pu);
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
        poruka("nc-overa-poruka", "uspeh", radnja === "reject" ? "Nacrt je odbijen." : (r.podaci.indexed ? (radnja === "ponovi-upis" ? "Nacrt je dodat u bazu znanja kancelarije." : "Nacrt je odobren i dodat u bazu znanja kancelarije.")
          : r.podaci.razlog === "INDEKSIRANJE_NIJE_USPELO" ? "Nacrt je odobren, ali upis u bazu znanja kancelarije nije potvrđen kao potpun — sistem ga zato ne koristi kao overen izvor u znanju kancelarije. Upis možete ponoviti iz liste."
          : r.podaci.razlog === "NACRT_IZ_SPISA" ? "Nacrt je odobren kao radni nacrt. Nacrt iz spisa se ne dodaje u bazu znanja kancelarije ni u dokumente predmeta."
          : "Nacrt je odobren. Nije dodat u bazu znanja kancelarije jer ocena kvaliteta nije dovoljna."));
        // C3b (GATE-02 N5): odluka iz liste o otvorenom AI predlogu / dokumentu za sud → ponovo se čita sa servera
        if (nacrt && nacrt.usvajanje && (nacrt.sid === sid || (nacrt.dok && String(nacrt.dok.id) === sid))) otvori(sid);
        else if (nacrt && nacrt.sid === sid) prikaziOtvoren({ status: radnja === "reject" ? "rejected" : "approved" });
        ucitajOveru();
        return true;
      }
      if (li) li.querySelectorAll("button").forEach(function (b) { b.disabled = false; });
      var g = r.greska || {};
      poruka("nc-overa-poruka", g.ishodNepoznat ? "nepoznato" : "greska", g.ishodNepoznat ? "Ishod nije poznat. Osvežite listu pre ponovnog pokušaja."
        : g.kod === "NOT_FOUND" ? "Nacrt nije dostupan. Ništa nije promenjeno."
        : radnja === "ponovi-upis" ? "Ponovni upis sada nije moguć (nacrt nije podoban ili je upis već u toku). Osvežite listu."
        : "Server je odbio zahtev. Ništa nije promenjeno.");
      return false;
    }

    /* ── Otvoren nacrt sa overe (VCR001 T05) ── */
    function prikaziOtvoren(promena) {
      if (!nacrt || !nacrt.sid || nacrt.usvajanje) return;
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
      var x = r.podaci;
      if (x.tip === TIP_PREDLOGA || x.tip === TIP_ZA_SUD) { otvoriUsvajanje(x, moja); return; }
      poruka("nc-overa-poruka", null); ocistiNacrt(); genOt = moja;
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

    /* ── MIR001 C3b: AI radni predlog → izričito usvajanje → dokument za sud ──
     * Ugovori (routers/drafting.py, shared/usvajanje_nacrta.py):
     *   GET  /api/staging/{predlog} → {tip:"nacrt_iz_spisa", status_teksta, predlog:{stavke, procesne_tacke, dokumenti}, dokumenti_za_sud}
     *   POST /api/staging/{predlog}/dokument-za-sud → dokument za sud (prazan; ponovljen zahtev = ista verzija na čekanju)
     *   POST /api/staging/{dok}/stavka {stavka, odluka: USVOJENO|ODBACENO} — tekst stavke dodaje SERVER iz snimka
     *   POST /api/staging/{dok}/procesne-tacke {tacke}; PATCH /api/staging/{dok}/tekst {tekst}
     *   POST /api/staging/{dok}/approve {sha256, rev} — odobrava se tačno prikazan tekst i odluke
     *   POST /api/staging/{dok}/docx → samo odobren tekst, bez naslova i podnožja sistema
     * AI predlog se ne menja, ne odobrava i ne izvozi. Ništa se ne usvaja automatski; „usvoji sve“ ne postoji. */
    var GRANICA_NAPOMENA = "═══ VINDEX — INTERNE NAPOMENE";
    // isto pravilo kao server (shared/usvajanje_nacrta._RE_OZNAKA): velikim slovima uz bilo koji razdvajač, ili uz crticu
    var OZNAKA_SPISA = /(^|[^\wА-Яа-я])(?:(?:DOK|ДОК)[ \t\u00a0.\-\u2010-\u2015\u2212]*|(?:[Dd][Oo][Kk]|[Дд][Оо][Кк])[\-\u2010-\u2015\u2212])\d/;
    var ODLUKE_TACKE = [["", "— izaberite —"], ["POTVRDJENO", "Potvrđujem (upišite stanje)"], ["ISPRAVLJENO", "Ispravljam (upišite tačno stanje)"],
                        ["NEPOZNATO", "Nepoznato — ne mogu pouzdano da utvrdim"], ["NIJE_PRIMENLJIVO", "Nije primenljivo"]];
    var STANJE_DOK = { PROCITAN: "pročitan", DELIMICNO_PROCITAN: "delimično pročitan", BEZ_TEKSTA: "bez teksta", NIJE_PROCITAN: "nije pročitan" };
    function enc(x) { return encodeURIComponent(String(x)); }
    function zaSudPorukaGreske(g, podrazumevano) {
      return g.ishodNepoznat ? "Ishod nije poznat. Osvežite dokument pre sledećeg koraka."
        : g.kod === "CONFLICT" ? "Dokument za sud je u međuvremenu promenjen, odobren ili odbijen. Prikazano je trenutno stanje — proverite ga."
        : g.kod === "NOT_FOUND" ? "Dokument nije dostupan." : podrazumevano;
    }
    async function otvoriUsvajanje(x, moja) {
      var pr = x, dokId = null;
      if (x.tip === TIP_ZA_SUD) {
        dokId = x.id;
        var rp = await api.get("/api/staging/" + enc((x.usvajanje || {}).predlog_id), { token: sesija.token(), oblik: function (y) { return typeof y.tip === "string"; } });
        if (moja !== genOt) return;
        if (!rp.ok || rp.podaci.tip !== TIP_PREDLOGA) { poruka("nc-overa-poruka", "greska", "AI predlog iz kog je dokument nastao nije dostupan. Ništa nije promenjeno."); return; }
        pr = rp.podaci;
      } else {
        var dz = (pr.dokumenti_za_sud || []).slice().sort(function (a, b) { return (b.verzija || 0) - (a.verzija || 0); });
        var cek = dz.filter(function (d) { return d.status === "pending"; })[0] || dz[0];
        dokId = cek ? cek.id : null;
      }
      var dok = null;
      if (dokId) {
        var rd = await api.get("/api/staging/" + enc(dokId), { token: sesija.token(), oblik: function (y) { return !!y.usvajanje; } });
        if (moja !== genOt) return;
        if (!rd.ok) { poruka("nc-overa-poruka", "greska", "Dokument za sud nije otvoren. Ništa nije promenjeno."); return; }
        dok = rd.podaci.usvajanje;
      }
      poruka("nc-overa-poruka", null); ocistiNacrt(); genOt = moja;
      nacrt = { sid: pr.id, usvajanje: true, naziv: "AI radni predlog", tip: TIP_PREDLOGA, status: tekst(pr.status),
                predmetId: pr.predmet_id, predlog: pr.predlog || null, dok: dok, sacuvanSud: dok ? dok.tekst : "", radi: false,
                crtanoZa: dok ? String(dok.id) : null };
      $("nc-naslov-nacrta").textContent = "AI radni predlog i dokument za sud";
      $("nc-tekst").hidden = true; $("nc-tekst-oznaka").hidden = true; $("nc-akcije").hidden = true;
      $("nc-rezultat").hidden = false;
      var deo = String(pr.tekst || "").split(GRANICA_NAPOMENA);
      if (!nacrt.predlog) {
        $("nc-tekst").hidden = false; $("nc-tekst-oznaka").hidden = false; $("nc-tekst").readOnly = true; $("nc-tekst").value = deo[0].trim();
        $("nc-tekst-oznaka").textContent = "AI predlog (samo za čitanje; ne izvozi se)";
        poruka("nc-otvoren-stanje", "nepoznato", "Ovaj nacrt je izrađen pre kontrolisanog usvajanja i nema zapis za usvajanje. Ne izvozi se kao dokument za sud; izradite novi predlog.");
      } else {
        $("nc-napomene").textContent = deo.length > 1 ? (GRANICA_NAPOMENA + deo.slice(1).join(GRANICA_NAPOMENA)).trim() : "(nema)";
        $("nc-usvajanje").hidden = false;
        crtajUsvajanje();
      }
      $("nc-naslov-nacrta").setAttribute("tabindex", "-1"); $("nc-naslov-nacrta").focus();
    }
    function dokumentIzvora(oznaka) {
      return ((nacrt && nacrt.predlog && nacrt.predlog.dokumenti) || []).filter(function (d) { return d.oznaka === oznaka; })[0] || null;
    }
    function prikazIzvora(oznaka) {
      var d = dokumentIzvora(oznaka), det = el("details", "adopt__src");
      det.append(el("summary", null, oznaka + (d && tekst(d.naziv) ? " — " + tekst(d.naziv) : "") + (d && STANJE_DOK[d.stanje] ? " (" + STANJE_DOK[d.stanje] + ")" : "") + " · prikaži dokument"));
      var pre = el("pre", "adopt__pre", d && d.dokument_id ? "Učitavanje…" : "Dokument nije dostupan za prikaz (nije pročitan ili nije u spisu).");
      det.append(pre);
      det.addEventListener("toggle", async function () {
        if (!det.open || !d || !d.dokument_id || det.dataset.ucitan) return;
        det.dataset.ucitan = "1";
        var izv = root.VxPredmetIzvor;
        var r = izv ? await izv.ucitajTekst(nacrt.predmetId, d.dokument_id, sesija.token()) : { ok: false };
        pre.textContent = r.ok ? (r.dostupan ? r.tekst : "Dokument nema pročitan tekst.") : "Tekst dokumenta nije učitan.";
      });
      return det;
    }
    function tackeSaEkrana() {
      var m = {};
      $("nc-tacke").querySelectorAll("li[data-tacka]").forEach(function (li) {
        m[li.dataset.tacka] = { odluka: li.querySelector("[data-polje=odluka]").value, tekst: li.querySelector("[data-polje=tekst]").value };
      });
      return m;
    }
    /* Tačke čiji izbor ili opis na ekranu nije ono što je sačuvano (GATE-02 B1: odobrava se samo sačuvano). */
    function nesacuvaneTacke(ekr) {
      var sac = (nacrt && nacrt.dok && nacrt.dok.procesne_tacke) || {};
      ekr = ekr || tackeSaEkrana();
      return Object.keys(ekr).filter(function (k) {
        var x = sac[k] || {};
        if (!ekr[k].odluka) return false;               // bez odluke nema šta da se sačuva (sačuvana se ne može poništiti)
        return ekr[k].odluka !== (x.odluka || "") || tekst(ekr[k].tekst) !== tekst(x.tekst);
      });
    }
    function crtajUsvajanje() {
      if (!nacrt || !nacrt.usvajanje || !nacrt.predlog) return;
      var ekranTacke = tackeSaEkrana(), zadrzi = {}, dokId = nacrt.dok ? String(nacrt.dok.id) : null;
      if (nacrt.crtanoZa === dokId || nacrt.crtanoZa === null)
        nesacuvaneTacke(ekranTacke).forEach(function (k) { zadrzi[k] = ekranTacke[k]; });
      nacrt.crtanoZa = dokId;
      var dok = nacrt.dok, odluke = {};
      ((dok && dok.stavke) || []).forEach(function (s) { odluke[s.id] = s; });
      var otvoreno = nacrt.status !== "rejected" && (!dok || dok.status === "pending");
      var lista = $("nc-stavke"); lista.replaceChildren();
      nacrt.predlog.stavke.forEach(function (s) {
        var li = el("li", "adopt__item"); li.dataset.stavka = s.id;
        li.append(el("p", "adopt__text", s.tekst));
        // R1: u dokument za sud ulazi `tekst_za_dokument` — izvod naveden bez interne oznake spisa (DOK-nn)
        var zaDok = tekst(s.tekst_za_dokument) ? s.tekst_za_dokument : s.tekst;
        if (zaDok !== s.tekst) {
          li.append(el("p", "adopt__meta", "U dokument za sud ulazi (izvod bez interne oznake spisa):"));
          li.append(el("p", "adopt__text", zaDok));
        }
        if (OZNAKA_SPISA.test(zaDok)) li.append(el("p", "adopt__state", "Sadrži internu oznaku spisa (DOK-nn), koju sud ne poznaje — posle usvajanja je u tekstu zamenite nazivom dokumenta; dok je u tekstu, odobrenje nije moguće."));
        if (s.izvori && s.izvori.length) {
          li.append(el("p", "adopt__meta", "Izvori koje navodi AI (nisu provereni): " + s.izvori.join(", ")));
          s.izvori.forEach(function (oz) { li.append(prikazIzvora(oz)); });
        } else li.append(el("p", "adopt__meta", "AI uz ovu stavku ne navodi dokument spisa."));
        var o = odluke[s.id] || {};
        li.append(el("p", "adopt__state", o.odluka === "USVOJENO" ? "Usvojeno u dokument za sud" + (o.u_tekstu_doslovno ? "" : " — u dokumentu je izmenjeno ili uklonjeno")
          : o.odluka === "ODBACENO" ? "Ne usvajam — ne ulazi u dokument za sud" : "Nije odlučeno — nije u dokumentu za sud"));
        if (otvoreno && o.odluka !== "USVOJENO") {
          var a = el("span", "review__actions");
          var da = el("button", "text-btn text-btn--line", "Proverio sam — usvajam u dokument za sud"); da.type = "button";
          da.addEventListener("click", function () { odluciStavku(s.id, "USVOJENO"); });
          a.append(da);
          if (!o.odluka) {
            var ne = el("button", "text-btn", "Ne usvajam"); ne.type = "button";
            ne.addEventListener("click", function () { odluciStavku(s.id, "ODBACENO"); });
            a.append(ne);
          }
          li.append(a);
        }
        lista.append(li);
      });
      var tl = $("nc-tacke"); tl.replaceChildren();
      var sacuvane = (dok && dok.procesne_tacke) || {};
      nacrt.predlog.procesne_tacke.forEach(function (t) {
        var li = el("li", "adopt__item"); li.dataset.tacka = t.kljuc;
        li.append(el("p", "adopt__state", t.naziv));
        if (tekst(t.pomoc)) li.append(el("p", "adopt__meta", t.pomoc));
        (t.kandidati || []).forEach(function (c) {
          li.append(el("p", "adopt__meta", "Iz spisa (doslovno, značenje nije utvrđeno): " + c.oznaka + " — „" + c.izvod + "“"
            + (c.nije_utvrdjeno && c.nije_utvrdjeno.length ? " · Nije utvrđeno: " + c.nije_utvrdjeno.join("; ") : "")
            + (c.kasnije && c.kasnije.length ? " · Kasnije u spisu: " + c.kasnije.join("; ") : "")));
        });
        var s = sacuvane[t.kljuc] || {}, z = otvoreno ? zadrzi[t.kljuc] : null;
        var sel = el("select", "field__input"); sel.setAttribute("aria-label", "Odluka: " + t.naziv);
        ODLUKE_TACKE.forEach(function (x) { var op = el("option", null, x[1]); op.value = x[0]; op.disabled = !x[0] && !!s.odluka; sel.append(op); });
        sel.value = (z ? z.odluka : s.odluka) || ""; sel.disabled = !otvoreno; sel.dataset.polje = "odluka";
        var ta = el("textarea", "field__input field__input--area"); ta.rows = 2; ta.maxLength = 2000;
        ta.setAttribute("aria-label", "Stanje kako ga vi utvrđujete: " + t.naziv); ta.value = (z ? z.tekst : s.tekst) || ""; ta.readOnly = !otvoreno; ta.dataset.polje = "tekst";
        li.append(sel, ta);
        if (z) li.append(el("p", "adopt__state", "Nesačuvana izmena — sačuvajte odluke pre odobrenja."));
        else if (s.odluka) li.append(el("p", "adopt__meta", "Sačuvano: vaša odluka (" + (datum(s.at) || "") + ")."));
        tl.append(li);
      });
      $("nc-tacke-sacuvaj").hidden = !otvoreno;
      // dokument za sud
      var t2 = $("nc-sud-tekst");
      t2.value = dok ? dok.tekst : ""; nacrt.sacuvanSud = t2.value;
      t2.readOnly = !otvoreno;
      t2.placeholder = dok ? "" : "Prazno: dokument za sud nastaje tek kad usvojite stavku ili sami napišete tekst.";
      var odobren = !!(dok && dok.status === "approved" && dok.odobreno);
      $("nc-sud-sacuvaj").hidden = !otvoreno; $("nc-sud-odobri").hidden = !otvoreno;
      $("nc-sud-docx").hidden = !odobren; $("nc-sud-nova").hidden = !odobren || nacrt.status === "rejected";
      var r = $("nc-razlozi"); r.replaceChildren();
      ((dok && dok.razlozi_protiv_odobrenja) || []).forEach(function (x) { r.append(el("li", null, x)); });
      poruka("nc-sud-stanje", odobren ? "uspeh" : "nepoznato",
        nacrt.status === "rejected" && !odobren ? "AI predlog je odbijen — iz njega se više ništa ne usvaja."
        : !dok ? "Dokument za sud još ne postoji. Ništa iz AI predloga nije u njemu."
        : odobren ? "Odobren dokument za sud (verzija " + dok.verzija + ", " + datum(dok.odobreno.at) + "). .docx sadrži ovaj tekst (osnovno formatiranje: red sa „# “ je naslov, **…** podebljano). Usvajanje je vaša odluka — sistem nije proverio da su tvrdnje tačne."
        : dok.status === "rejected" ? "Ova verzija dokumenta za sud je odbijena."
        : "Dokument za sud, verzija " + dok.verzija + " — čeka vaše odobrenje. Usvojene stavke su ovde; nijedna nije proverena od strane sistema.");
    }
    async function obezbediDokument() {
      if (nacrt.dok) return true;
      var pid = nacrt.sid;
      var r = await api.send("/api/staging/" + enc(nacrt.sid) + "/dokument-za-sud", { token: sesija.token(), oblik: function (x) { return typeof x.id === "string" || typeof x.id === "number"; } });
      if (!isti(pid)) return false;
      if (!r.ok) { poruka("nc-sud-poruka", "greska", zaSudPorukaGreske(r.greska || {}, "Dokument za sud nije napravljen. Ništa nije promenjeno.")); return false; }
      nacrt.dok = r.podaci;
      return true;
    }
    async function osveziDokument() {
      if (!nacrt || !nacrt.dok) return;
      var sid = nacrt.sid;
      var rd = await api.get("/api/staging/" + enc(nacrt.dok.id), { token: sesija.token(), oblik: function (y) { return !!y.usvajanje; } });
      if (rd.ok && nacrt && nacrt.sid === sid) { nacrt.dok = rd.podaci.usvajanje; crtajUsvajanje(); }
    }
    async function zaSud(fn) {                     // jedna radnja odjednom; ishod uvek ponovo nacrta ekran
      if (!nacrt || !nacrt.usvajanje || nacrt.radi) return;
      var sid = nacrt.sid;
      nacrt.radi = true; $("nc-usvajanje").querySelectorAll("button").forEach(function (b) { b.disabled = true; });
      try { await fn(); } finally {
        if (nacrt && nacrt.sid === sid) {
          nacrt.radi = false; $("nc-usvajanje").querySelectorAll("button").forEach(function (b) { b.disabled = false; });
        }
      }
    }
    function nesacuvanTekst() {
      return !!nacrt && (!nacrt.dok || nacrt.dok.status === "pending") && $("nc-sud-tekst").value !== (nacrt.dok ? nacrt.sacuvanSud : "");
    }
    function isti(pid) { return !!nacrt && nacrt.sid === pid; }       // GATE-02 N4: kasan odgovor drugog predloga se odbacuje
    function odluciStavku(sid, odluka) {
      return zaSud(async function () {
        poruka("nc-sud-poruka", null);
        if (nesacuvanTekst()) { poruka("nc-sud-poruka", "greska", "Prvo sačuvajte izmene teksta dokumenta za sud — usvojena stavka se dodaje na kraj sačuvanog teksta."); return; }
        var pid = nacrt.sid;
        if (!(await obezbediDokument())) return;
        var r = await api.send("/api/staging/" + enc(nacrt.dok.id) + "/stavka", { telo: { stavka: sid, odluka: odluka }, token: sesija.token(), oblik: function (x) { return !!x.id; } });
        if (!isti(pid)) return;
        if (r.ok) { nacrt.dok = r.podaci; crtajUsvajanje(); poruka("nc-sud-poruka", "uspeh", odluka === "USVOJENO" ? "Stavka " + sid + " je dodata na kraj dokumenta za sud." : "Stavka " + sid + " ne ulazi u dokument za sud."); return; }
        poruka("nc-sud-poruka", "greska", zaSudPorukaGreske(r.greska || {}, "Odluka nije sačuvana. Ništa nije promenjeno."));
        await osveziDokument();
      });
    }
    function sacuvajTacke() {
      return zaSud(async function () {
        poruka("nc-sud-poruka", null);
        var tacke = {}, n = 0;
        $("nc-tacke").querySelectorAll("li[data-tacka]").forEach(function (li) {
          var o = li.querySelector("[data-polje=odluka]").value;
          if (!o) return;
          tacke[li.dataset.tacka] = { odluka: o, tekst: li.querySelector("[data-polje=tekst]").value.slice(0, 2000) }; n++;
        });
        var bezOdluke = [];
        $("nc-tacke").querySelectorAll("li[data-tacka]").forEach(function (li) {
          if (!li.querySelector("[data-polje=odluka]").value && tekst(li.querySelector("[data-polje=tekst]").value)) bezOdluke.push(li.dataset.tacka);
        });
        if (bezOdluke.length) { poruka("nc-sud-poruka", "greska", "Uz opis izaberite i odluku (" + bezOdluke.length + " tačk" + (bezOdluke.length === 1 ? "a" : "e") + "). Ništa nije sačuvano."); return; }
        if (!n) { poruka("nc-sud-poruka", "greska", "Niste izabrali nijednu odluku. Ništa nije sačuvano."); return; }
        var bez = Object.keys(tacke).filter(function (k) { return (tacke[k].odluka === "POTVRDJENO" || tacke[k].odluka === "ISPRAVLJENO") && !tacke[k].tekst.trim(); });
        if (bez.length) { poruka("nc-sud-poruka", "greska", "Uz „potvrđujem“ ili „ispravljam“ upišite stanje kako ga vi utvrđujete. Ništa nije sačuvano."); return; }
        if (nesacuvanTekst()) { poruka("nc-sud-poruka", "greska", "Prvo sačuvajte izmene teksta dokumenta za sud."); return; }
        var pid = nacrt.sid;
        if (!(await obezbediDokument())) return;
        var r = await api.send("/api/staging/" + enc(nacrt.dok.id) + "/procesne-tacke", { telo: { tacke: tacke }, token: sesija.token(), oblik: function (x) { return !!x.id; } });
        if (!isti(pid)) return;
        if (r.ok) { nacrt.dok = r.podaci; crtajUsvajanje(); poruka("nc-sud-poruka", "uspeh", "Odluke o procesnim informacijama su sačuvane (" + n + ")."); return; }
        poruka("nc-sud-poruka", "greska", zaSudPorukaGreske(r.greska || {}, "Odluke nisu sačuvane (proverite opis i izvore). Ništa nije promenjeno."));
        await osveziDokument();
      });
    }
    async function sacuvajSudTekst() {
      var t = $("nc-sud-tekst").value;
      if (!t.trim()) { poruka("nc-sud-poruka", "greska", "Dokument za sud je prazan. Ništa nije sačuvano."); return false; }
      if (nacrt.dok && t === nacrt.sacuvanSud) return true;
      var pid = nacrt.sid;
      if (!(await obezbediDokument())) return false;
      var r = await api.send("/api/staging/" + enc(nacrt.dok.id) + "/tekst", { metod: "PATCH", telo: { tekst: t.slice(0, 100000) }, token: sesija.token(), oblik: function (x) { return x.sacuvano === true; } });
      if (!isti(pid)) return false;
      if (r.ok) { await osveziDokument(); poruka("nc-sud-poruka", "uspeh", "Tekst dokumenta za sud je sačuvan."); return true; }
      poruka("nc-sud-poruka", "greska", zaSudPorukaGreske(r.greska || {}, "Tekst nije sačuvan. Tekst je i dalje na ekranu."));
      if ((r.greska || {}).kod === "CONFLICT") await osveziDokument();
      return false;
    }
    function odobriZaSud() {
      return zaSud(async function () {
        poruka("nc-sud-poruka", null);
        var nes = nesacuvaneTacke();
        if (nes.length) {
          poruka("nc-sud-poruka", "greska", "Imate nesačuvane odluke o procesnim informacijama (" + nes.length + "). Sačuvajte ih ili ih vratite — odobrava se samo ono što je sačuvano. Ništa nije odobreno.");
          return;
        }
        var pid = nacrt.sid;
        if (!(await sacuvajSudTekst()) || !isti(pid)) return;
        var d0 = nacrt.dok;
        if (d0.razlozi_protiv_odobrenja && d0.razlozi_protiv_odobrenja.length) {
          poruka("nc-sud-poruka", "greska", "Dokument još ne može da se odobri — pogledajte spisak ispod teksta."); return;
        }
        var r = await api.send("/api/staging/" + enc(d0.id) + "/approve", { telo: { sha256: d0.sha256, rev: d0.rev }, token: sesija.token(), oblik: function (x) { return typeof x.status === "string"; } });
        if (!isti(pid)) return;
        await osveziDokument();
        if (r.ok && r.podaci.status === "approved") { poruka("nc-sud-poruka", "uspeh", "Dokument za sud je odobren. Ne dodaje se u bazu znanja kancelarije."); ucitajOveru(); return; }
        poruka("nc-sud-poruka", "greska", zaSudPorukaGreske(r.greska || {}, "Dokument nije odobren. Pogledajte šta još nedostaje."));
      });
    }
    function docxZaSud() {
      return zaSud(async function () {
        if (!nacrt.dok || nacrt.dok.status !== "approved") return;
        poruka("nc-sud-poruka", "ucitavanje", "Priprema .docx fajla…");
        var r = await api.preuzmi("/api/staging/" + enc(nacrt.dok.id) + "/docx", { telo: {}, token: sesija.token(), tip: DOCX });
        if (!r.ok) { poruka("nc-sud-poruka", "greska", r.greska.kod === "CONFLICT" ? "Fajl nije napravljen: izvozi se samo odobren tekst, a sačuvan tekst se razlikuje od odobrenog." : "Fajl nije preuzet. Pokušajte ponovo."); return; }
        var url = URL.createObjectURL(r.blob), a = el("a");
        a.href = url; a.download = r.ime || "Dokument_za_sud.docx"; d.body.append(a); a.click(); a.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
        poruka("nc-sud-poruka", "uspeh", "Fajl „" + (r.ime || "Dokument_za_sud.docx") + "“ je preuzet — sadrži odobren tekst.");
      });
    }
    function novaVerzija() {
      return zaSud(async function () {
        var pid = nacrt.sid;
        var r = await api.send("/api/staging/" + enc(nacrt.sid) + "/dokument-za-sud", { token: sesija.token(), oblik: function (x) { return !!x.id; } });
        if (!isti(pid)) return;
        if (r.ok) { nacrt.dok = r.podaci; crtajUsvajanje(); poruka("nc-sud-poruka", "uspeh", "Nova verzija " + r.podaci.verzija + " — ponovo je odobravate; procesne informacije ponovo odlučujete."); ucitajOveru(); return; }
        poruka("nc-sud-poruka", "greska", zaSudPorukaGreske(r.greska || {}, "Nova verzija nije napravljena."));
      });
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
      var r;
      if (nacrt.sid) {
        /* MIR001 C3b: nacrt sa pregleda izvozi SERVER iz sačuvanog teksta — samo tekst za sud, bez internih napomena.
           Nesačuvana izmena se prvo čuva (kao pre odobrenja), da DOCX bude ono što advokat vidi. */
        if (nacrt.status === "pending" && t !== nacrt.sacuvan && !(await sacuvaj())) return;
        $("nc-docx").disabled = true;
        poruka("nc-docx-poruka", "ucitavanje", "Priprema .docx fajla…");
        r = await api.preuzmi("/api/staging/" + encodeURIComponent(nacrt.sid) + "/docx", { telo: {}, token: sesija.token(), tip: DOCX });
      } else {
        $("nc-docx").disabled = true;
        poruka("nc-docx-poruka", "ucitavanje", "Priprema .docx fajla…");
        r = await api.preuzmi("/api/nacrti/export/docx", { telo: { tekst: t.slice(0, 100000), naslov: nacrt.naziv.slice(0, 200), tip: nacrt.tip }, token: sesija.token(), tip: DOCX });
      }
      $("nc-docx").disabled = false;
      if (!r.ok && r.greska.kod === "CONFLICT") {
        poruka("nc-docx-poruka", "greska", "Fajl nije napravljen: tekst za sud još sadrži izostavljena mesta [IZOSTAVLJENO …] ili [PROVERITI …], " +
          "ili granica internih napomena nije pronađena. Razrešite ih u tekstu, sačuvajte i pokušajte ponovo. Interne napomene se ne izvoze.");
        return;
      }
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
    $("nc-tacke-sacuvaj").addEventListener("click", sacuvajTacke);
    $("nc-sud-sacuvaj").addEventListener("click", function () { zaSud(sacuvajSudTekst); });
    $("nc-sud-odobri").addEventListener("click", odobriZaSud);
    $("nc-sud-docx").addEventListener("click", docxZaSud);
    $("nc-sud-nova").addEventListener("click", novaVerzija);
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) { katalog = null; ocisti(); } });

    return { postavi: postavi, aktiviraj: aktiviraj, ocisti: ocisti, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxNacrtPredmeta = Object.freeze({ napravi: napravi });
})(window);
