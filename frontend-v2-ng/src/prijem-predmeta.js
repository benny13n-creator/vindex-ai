/* Vindex V2 NG — PRIJEM DOKUMENATA u predmet: Smart Intake + OCR (NS005, Task 14).
 *
 * Ugovori (routers/smart_intake.py):
 *   POST /api/smart-intake/documents (multipart `files`) → 202 {rezultati[{filename, ok, job_id?, already_submitted?, greska?}],
 *        nastavlja, preostali_fajlovi}. Isti sadržaj istog korisnika = ISTI posao (dedupe na nivou posla).
 *   GET  /api/smart-intake/jobs/{id} → {job{status, attempts, last_error, original_filename, predmet_id},
 *        dokument{tip, tip_pouzdanost, ocr_koriscen}|null, entiteti[{entity_id, entity_type, value, confidence, needs_review, corrected}],
 *        potrebna_provera{razlog, polja}|null}. Tuđ posao → 404.
 *   POST /api/smart-intake/entities/{id}/correct {corrected_value} — original se ne briše
 *   POST /api/smart-intake/jobs/{id}/review/resolve | /review/reject
 *   POST /api/smart-intake/jobs/{id}/finalize {predmet_id} — prikačuje dokument OVOM predmetu; polja predmeta se NE menjaju;
 *        bez imena klijenta ne pravi klijenta. Pre razrešenog pregleda → 409.
 * Stanja posla su STVARNA stanja baze (migracija 073), bez izmišljenih procenata:
 *   received (+attempts>0 = ponovni pokušaj) · preprocessing · classifying · extracting · matching · dedup_check ·
 *   awaiting_review · completed · failed (trajno, posle najvećeg broja pokušaja).
 * Izvučen podatak je PREDLOG: pouzdanost se prikazuje, nesiguran podatak traži pregled, odsutan podatak nije prazan.
 */
(function (root) {
  "use strict";

  /* Praćenje stanja posla (OCR001-STATUS-RECOVERY). Ruta stanja ima „60/minute“ po IP adresi i putanji posla; jedan
   * posao na 10 s je 6 zahteva u minutu, a svaki posao ima svoj brojač. Rok praćenja važi i kad zahtevi stalno padaju, a zahtev koji
   * „visi“ prekida se posle ZAHTEV_MS. Posle 429 čeka se `Retry-After` ako ga server pošalje, inače ceo prozor limita. */
  var RAZMAK_MS = 10000, NAJDUZE_MS = 5 * 60 * 1000, ZAHTEV_MS = 20000, POSLE_429_MS = 60000, NAJDUZE_CEKANJE_MS = 60000;
  var KONACNE_GRESKE = { NOT_FOUND: "Posao nije dostupan.", AUTH_REQUIRED: "Prijava više nije važeća. Stanje posla se ne prati.",
    FORBIDDEN: "Nemate pristup ovom poslu." };
  function cekanjePosleGreske(g, uzastopno) {
    if (g && g.kod === "RATE_LIMITED") {
      var ra = Number(g.retryAfter);
      return Number.isFinite(ra) && ra > 0 ? Math.min(Math.max(ra * 1000, RAZMAK_MS), NAJDUZE_MS) : POSLE_429_MS;
    }
    return Math.min(RAZMAK_MS * Math.pow(2, Math.max(0, uzastopno - 1)), NAJDUZE_CEKANJE_MS);   // 10 · 20 · 40 · 60 · 60 s
  }
  var ZAVRSNA = { awaiting_review: 1, completed: 1, failed: 1 };
  var STANJA = { received: "U redu za obradu", preprocessing: "Priprema dokumenta", classifying: "Prepoznavanje vrste dokumenta",
    extracting: "Izdvajanje podataka", matching: "Povezivanje podataka", dedup_check: "Provera duplikata",
    awaiting_review: "Čeka vaš pregled", completed: "Obrađeno — spremno za prikačivanje", failed: "Obrada nije uspela" };
  /* QA-03: nazivi vrsta dokumenata i izdvojenih polja su u src/nazivi.js (isti rečnik kao dosije i analiza). */
  var NAZIVI = root.VxNazivi;
  var RAZLOZI = { ocr_failed: "Tekst dokumenta nije mogao da se pročita (OCR nije uspeo). Ništa nije izvučeno.",
    classification_uncertain: "Vrsta dokumenta nije pouzdano prepoznata.", low_confidence_extraction: "Neki podaci nisu pouzdano izdvojeni.",
    segmentation_uncertain: "Nije sigurno gde jedan dokument prestaje, a drugi počinje." };
  var DOZVOLJENO = /\.(pdf|docx|txt|jpe?g|png)$/i, MAX_B = 25 * 1024 * 1024;

  function tekst(v) { return String(v == null ? "" : v).trim(); }
  /* OCR001: PRIKACENO · U_TOKU · NEPOTPUNO · NIJE_PRIKACENO (routers/smart_intake.py::_stanje_prikacivanja). Server bez
   * tog polja (pre OCR001): `predmet_id` je tada bio jedini znak. */
  var PRIKACIVANJA = { PRIKACENO: 1, U_TOKU: 1, NEPOTPUNO: 1, NIJE_PRIKACENO: 1 };
  function prikacivanje(j) { var s = tekst(j && j.prikacivanje); return PRIKACIVANJA[s] ? s : (j && j.predmet_id ? "PRIKACENO" : "NIJE_PRIKACENO"); }
  function ispravanId(v) { return /^[A-Za-z0-9_-]{1,64}$/.test(tekst(v)); }
  function procenat(p) { var n = Number(p); return Number.isFinite(n) ? Math.round(n * 100) + "%" : "—"; }
  function nazivPolja(t) { return NAZIVI.poljePodatka(t); }
  function nazivVrste(t) { return NAZIVI.vrstaDokumenta(t) || "Nije prepoznato"; }

  function napravi(o) {
    /* VCR001 T02: isti modul služi i strani „Nov predmet → Iz dokumenta“ (prefiks „nd“, ID-jevi nd-*). U tom režimu
     * finalize NE nosi predmet_id (backend otvara predmet iz dokumenta, uz `klijent_strana` po izboru advokata);
     * kad predmet nastane, ostali dokumenti iste sesije se prikače njemu. */
    var P = o.prefiks || "pd";
    var d = root.document, $ = function (id) { return d.getElementById(P === "pd" ? id : P + id.slice(2)); };
    var sesija = o.sesija, api = o.api, osvezi = o.osvezi || function () {}, naOtvoren = o.naOtvoren || function () {};
    var trenutni = null, gen = 0, poslovi = [], saljem = false;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function poruka(id, st, t) { var n = $(id); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function zivi(p) { return !!trenutni && p.gen === gen && sesija.stanje().korisnik === trenutni.korisnik; }
    function zaustaviPracenje(p) { if (p.tajmer) { clearTimeout(p.tajmer); p.tajmer = null; } if (p.k) { p.k.abort(); p.k = null; } }

    function ocisti() {
      gen++;
      poslovi.forEach(zaustaviPracenje);
      poslovi = []; trenutni = null; saljem = false;
      $("pd-forma").reset(); $("pd-poslovi").replaceChildren();
      poruka("pd-poruka", null); poruka("pd-stanje", null);
      $("pd-otpremi").disabled = false; $("pd-otpremi").textContent = "Otpremi";
    }

    /* ── Otpremanje ── */
    async function otpremi() {
      if (saljem || !trenutni) return;
      var fajlovi = Array.prototype.slice.call($("pd-fajlovi").files || []);
      if (!fajlovi.length) { poruka("pd-poruka", "greska", "Izaberite bar jedan fajl."); return; }
      var losi = fajlovi.filter(function (f) { return !DOZVOLJENO.test(f.name) || f.size > MAX_B || f.size < 1; });
      if (losi.length) { poruka("pd-poruka", "greska", "Nije poslato: " + losi.map(function (f) { return f.name; }).join(", ") + " — podržano je PDF, DOCX, TXT, JPG i PNG, do 25 MB po fajlu."); return; }
      var s = sesija.stanje();
      if (s.stanje !== sesija.STANJA.PRIJAVLJEN || s.korisnik !== trenutni.korisnik) { poruka("pd-poruka", "greska", "Niste prijavljeni. Ništa nije poslato."); return; }
      var fd = new FormData();
      fajlovi.forEach(function (f) { fd.append("files", f, f.name); });
      var moja = gen;
      saljem = true; $("pd-otpremi").disabled = true; $("pd-otpremi").textContent = "Otpremanje…";
      poruka("pd-poruka", "ucitavanje", "Otpremanje " + fajlovi.length + (fajlovi.length === 1 ? " fajla…" : " fajlova…"));
      var r = await api.send("/api/smart-intake/documents", { telo: fd, token: sesija.token(), oblik: function (x) { return Array.isArray(x.rezultati); } });
      if (moja !== gen) return;
      saljem = false; $("pd-otpremi").disabled = false; $("pd-otpremi").textContent = "Otpremi";
      if (!r.ok) {
        var g = r.greska || {};
        poruka("pd-poruka", g.ishodNepoznat ? "nepoznato" : "greska", g.ishodNepoznat
          ? "Ishod otpremanja nije poznat. Ponovo otpremite iste fajlove — sistem prepoznaje već poslat dokument i ne pravi duplikat."
          : g.kod === "RATE_LIMITED" ? "Previše otpremanja u kratkom roku. Pokušajte malo kasnije. Ništa nije poslato."
          : g.kod === "AUTH_REQUIRED" ? "Prijava više nije važeća. Ništa nije poslato." : "Server je odbio otpremanje. Ništa nije poslato.");
        return;
      }
      if (!r.podaci) { poruka("pd-poruka", "nepoznato", "Fajlovi su primljeni, ali odgovor nije mogao da se pročita. Ponovo otpremite iste fajlove da biste videli njihove poslove."); return; }
      $("pd-forma").reset();
      var neuspeli = [];
      r.podaci.rezultati.forEach(function (x) {
        if (x && x.ok && ispravanId(x.job_id)) dodajPosao(tekst(x.job_id), tekst(x.filename), !!x.already_submitted);
        else neuspeli.push(tekst(x && x.filename) + ": " + (tekst(x && x.greska) || "nije primljen"));
      });
      var delovi = [];
      if (neuspeli.length) delovi.push("Nije primljeno — " + neuspeli.join("; ") + ".");
      if (r.podaci.nastavlja && Array.isArray(r.podaci.preostali_fajlovi) && r.podaci.preostali_fajlovi.length)
        delovi.push("Server je obradio deo fajlova; ponovo otpremite preostale: " + r.podaci.preostali_fajlovi.map(tekst).join(", ") + ".");
      poruka("pd-poruka", delovi.length ? "greska" : "uspeh", delovi.length ? delovi.join(" ") : "Dokumenti su primljeni i obrađuju se. Obrada se nastavlja na serveru i ako napustite ovu stranicu.");
    }

    /* ── Posao ── */
    function dodajPosao(id, ime, vecPoslat) {
      if (poslovi.some(function (p) { return p.id === id; })) return;
      var p = { id: id, ime: ime, vecPoslat: vecPoslat, gen: gen, od: Date.now(), podaci: null, tajmer: null, k: null, radi: false, li: el("li", "intake") };
      p.li.dataset.posao = id;
      poslovi.push(p);
      $("pd-poslovi").append(p.li);
      prikazi(p, null);
      prati(p);
    }

    /* Sledeće čitanje se zakazuje samo ako staje u rok praćenja — i posle greške i posle 429. Ručna radnja (ispravka,
     * pregled, prikačivanje) i dalje pokreće jedno sveže čitanje i kad je rok prošao. */
    function zakazi(p, ms, napomena) {
      if (Date.now() + ms - p.od > NAJDUZE_MS) {
        prikazi(p, (napomena ? napomena + " " : "") + "Praćenje je zaustavljeno posle 5 minuta. Obrada se nastavlja na serveru — ponovo otpremite isti fajl da biste videli njen ishod.");
        return;
      }
      if (napomena) prikazi(p, napomena);
      p.tajmer = setTimeout(function () { prati(p); }, ms);
    }

    async function prati(p) {
      zaustaviPracenje(p);
      if (!zivi(p)) return;
      var k = p.k = new AbortController(), istekao = false;
      var rok = setTimeout(function () { istekao = true; k.abort(); }, ZAHTEV_MS);
      var r = await api.get("/api/smart-intake/jobs/" + encodeURIComponent(p.id), { token: sesija.token(), signal: k.signal,
        oblik: function (x) { return x.job && typeof x.job.status === "string" && Array.isArray(x.entiteti); } });
      clearTimeout(rok);
      if (!zivi(p) || p.k !== k) return;                       // novo čitanje ili gašenje praćenja je preuzelo posao
      p.k = null;
      if (!r.ok) {
        var g = r.greska || {};
        if (g.kod === "ABORTED" && !istekao) return;
        if (KONACNE_GRESKE[g.kod]) { p.greske = 0; prikazi(p, KONACNE_GRESKE[g.kod]); return; }
        p.greske = (p.greske || 0) + 1;
        zakazi(p, cekanjePosleGreske(g, p.greske), g.kod === "RATE_LIMITED"
          ? "Server je privremeno ograničio broj zahteva; stanje posla se ponovo proverava malo kasnije. Ovo ne znači da obrada nije uspela."
          : "Stanje posla nije učitano zbog greške. Ovo ne znači da obrada nije uspela.");
        return;
      }
      p.greske = 0;
      p.podaci = r.podaci;
      var st = tekst(p.podaci.job.status);
      if (ZAVRSNA[st] && prikacivanje(p.podaci.job) !== "U_TOKU") { prikazi(p, null); return; }
      prikazi(p, null);
      zakazi(p, RAZMAK_MS, null);
    }

    function prikazi(p, napomena) {
      var li = p.li, x = p.podaci;
      li.replaceChildren();
      var glava = el("div", "intake__head");
      glava.append(el("span", "intake__name", p.ime || "Dokument"));
      var st = x ? tekst(x.job.status) : "";
      var oznaka = !x ? "Učitavanje stanja…" : (st === "received" && Number(x.job.attempts) > 0 ? "Ponovni pokušaj zakazan" : (STANJA[st] || st || "Nepoznato stanje"));
      var stanje = el("span", "intake__state", oznaka);
      stanje.dataset.stanje = st || "ucitavanje";
      glava.append(stanje);
      li.append(glava);
      if (p.vecPoslat) li.append(el("p", "field__help", "Ovaj sadržaj je već bio poslat — prikazuje se postojeći posao, bez duplikata."));
      if (napomena) { var n = el("p", "notice", napomena); n.dataset.stanje = "nepoznato"; li.append(n); }
      if (!x) return;
      var j = x.job;
      if (st === "failed") { var f = el("p", "notice", "Obrada nije uspela posle više pokušaja. Dokument nije prikačen; otpremite ga ponovo ili ga dodajte drugim putem."); f.dataset.stanje = "greska"; li.append(f); }
      var dok = x.dokument, provera = x.potrebna_provera;
      /* OCR001: svi razlozi pregleda; `ocr_failed` SA opisom znači da deo dokumenta nije pročitan (ostatak jeste),
       * bez opisa — da tekst uopšte nije pročitan. */
      var provere = Array.isArray(x.potrebne_provere) && x.potrebne_provere.length ? x.potrebne_provere : (provera ? [provera] : []);
      var nistaProcitano = false;
      provere.forEach(function (q) {
        var raz = tekst(q && q.razlog), polja = Array.isArray(q && q.polja) ? q.polja.map(tekst).filter(Boolean) : [];
        var t = raz === "ocr_failed" && polja.length ? "Deo dokumenta nije pouzdano pročitan — " + polja.join("; ") + ". Proverite original pre oslanjanja na izvučene podatke." : RAZLOZI[raz];
        if (raz === "ocr_failed" && !polja.length) nistaProcitano = true;
        if (t) { var pr = el("p", "notice", t); pr.dataset.stanje = "nepoznato"; li.append(pr); }
      });
      if (dok && !nistaProcitano) {
        var meta = [nazivVrste(dok.tip) + " (pouzdanost " + procenat(dok.tip_pouzdanost) + ")"];
        if (dok.ocr_koriscen === true) meta.push("tekst pročitan OCR-om");
        li.append(el("p", "intake__meta", meta.join(" · ")));
      }
      var ents = (x.entiteti || []).filter(function (e) { return e && ispravanId(e.entity_id); });
      if (ents.length) {
        var dl = el("dl", "facts facts--doc");
        ents.forEach(function (e) {
          var v = e.value === null || e.value === undefined ? "" : tekst(e.value);
          var treba = e.needs_review === true || !v;
          var dt = el("dt", null, nazivPolja(e.entity_type));
          var dd = el("dd", "intake__value");
          dd.dataset.polje = tekst(e.entity_type);
          dd.append(el("span", null, v || "nije pronađeno"));
          dd.append(el("span", "intake__conf", v ? " · pouzdanost " + procenat(e.confidence) : ""));
          if (e.corrected) dd.append(el("span", "intake__flag", " · ispravljeno"));
          else if (treba) dd.append(el("span", "intake__flag", " · proverite"));
          if (treba && !e.corrected && !j.predmet_id && st === "awaiting_review") {
            var u = el("input", "field__input intake__input"); u.type = "text"; u.maxLength = 300; u.value = v;
            u.setAttribute("aria-label", "Ispravka: " + nazivPolja(e.entity_type));
            var b = el("button", "text-btn text-btn--line", "Ispravi"); b.type = "button";
            b.addEventListener("click", function () { ispravi(p, e, u, b); });
            var red = el("span", "intake__fix"); red.append(u, b); dd.append(red);
          }
          dl.append(dt, dd);
        });
        li.append(dl);
      }
      var akcije = el("div", "form__actions");
      if (st === "awaiting_review" && !j.predmet_id) {
        akcije.append(dugme("Potvrđujem pregled", "text-btn text-btn--primary", function (b) { odluci(p, "resolve", b); }));
        akcije.append(dugme("Odbij dokument", "text-btn", function (b) { odluci(p, "reject", b); }));
        li.append(el("p", "field__help", "Potvrdom kažete da ste pregledali označene podatke. Tek posle toga dokument može da se prikači predmetu."));
      }
      /* OCR001: „prikačeno“ se čita iz izvedenog stanja servera (`job.prikacivanje`), ne iz `predmet_id`: predmet se
       * beleži pre dokumenata i ostaje posle neuspelog ili prekinutog prikačivanja. */
      var pr = prikacivanje(j);
      if (st === "completed" && pr === "NIJE_PRIKACENO") akcije.append(dugme(trenutni.id ? "Prikači ovom predmetu" : "Otvori predmet iz ovog dokumenta",
        "text-btn text-btn--primary", function (b) { prikaci(p, b); }));
      if (pr === "U_TOKU") { var ut = el("p", "notice", "Prikačivanje je u toku ili je upravo prekinuto. Dokument još nije potvrđen u predmetu; stanje se ponovo proverava."); ut.dataset.stanje = "nepoznato"; li.append(ut); }
      else if (pr === "NEPOTPUNO" && (!trenutni.id || j.predmet_id === trenutni.id)) {
        var np = el("p", "notice", "Prikačivanje nije završeno: dokument nije potvrđen u predmetu. Ponovite prikačivanje — deo koji je već sačuvan neće biti dupliran.");
        np.dataset.stanje = "greska"; li.append(np);
        if (st === "completed") akcije.append(dugme("Ponovi prikačivanje", "text-btn text-btn--primary", function (b) { prikaci(p, b); }));
      } else if (pr === "NEPOTPUNO") { var nd = el("p", "notice", "Prikačivanje ovog dokumenta drugom vašem predmetu nije završeno. Nastavite ga iz tog predmeta."); nd.dataset.stanje = "greska"; li.append(nd); }
      else if (pr === "PRIKACENO" && j.predmet_id === trenutni.id) li.append(el("p", "intake__done", "Prikačeno ovom predmetu."));
      else if (pr === "PRIKACENO") li.append(el("p", "notice", "Ovaj dokument je već prikačen drugom vašem predmetu."));
      if (akcije.childNodes.length) li.append(akcije);
      var por = el("p", "notice intake__msg"); por.hidden = true; por.setAttribute("role", "status"); li.append(por);
      p.poruka = por;
      if (p.zadnja) { por.hidden = false; por.dataset.stanje = p.zadnja[0]; por.textContent = p.zadnja[1]; }   // preživljava ponovno čitanje
    }
    function dugme(t, cls, fn) { var b = el("button", cls, t); b.type = "button"; b.addEventListener("click", function () { fn(b); }); return b; }
    function javi(p, st, t) { p.zadnja = st === "ucitavanje" ? null : [st, t]; if (!p.poruka) return; p.poruka.hidden = false; p.poruka.dataset.stanje = st; p.poruka.textContent = t; }
    function zakljucaj(p, b, da) { p.radi = da; p.li.querySelectorAll("button").forEach(function (x) { x.disabled = da; }); }

    function neuspeh(p, g, nista) {
      if (g.ishodNepoznat) { javi(p, "nepoznato", "Ishod nije poznat. Stanje posla se ponovo učitava — proverite ga pre ponovnog pokušaja."); prati(p); return; }
      javi(p, "greska", ({ NOT_FOUND: "Posao nije dostupan. ", CONFLICT: "Posao trenutno nije u stanju za ovu radnju. ", RATE_LIMITED: "Previše zahteva. ",
        AUTH_REQUIRED: "Prijava više nije važeća. ", PROTECTION_UNAVAILABLE: "Zaštita od dvostrukog upisa nije dostupna. " }[g.kod] || "Server je odbio zahtev. ") + nista);
    }

    async function ispravi(p, e, ulaz, b) {
      if (p.radi || !zivi(p)) return;
      var v = ulaz.value.trim();
      if (!v) { javi(p, "greska", "Unesite ispravnu vrednost."); ulaz.focus(); return; }
      var moja = gen;
      zakljucaj(p, b, true); javi(p, "ucitavanje", "Čuvanje ispravke…");
      var r = await api.send("/api/smart-intake/entities/" + encodeURIComponent(e.entity_id) + "/correct", { telo: { corrected_value: v.slice(0, 300) }, token: sesija.token(),
        oblik: function (x) { return typeof x.corrected_value === "string"; } });
      if (moja !== gen || !zivi(p)) return;
      zakljucaj(p, b, false);
      if (r.ok) { javi(p, "uspeh", "Ispravka je sačuvana: " + nazivPolja(e.entity_type) + "."); prati(p); return; }
      neuspeh(p, r.greska || {}, "Ispravka nije sačuvana.");
    }

    async function odluci(p, radnja, b) {
      if (p.radi || !zivi(p)) return;
      var moja = gen;
      zakljucaj(p, b, true); javi(p, "ucitavanje", radnja === "resolve" ? "Beleženje pregleda…" : "Odbijanje…");
      var r = await api.send("/api/smart-intake/jobs/" + encodeURIComponent(p.id) + "/review/" + radnja, { telo: {}, token: sesija.token(),
        oblik: function (x) { return x.ok === true; } });
      if (moja !== gen || !zivi(p)) return;
      zakljucaj(p, b, false);
      if (r.ok) { javi(p, "uspeh", radnja === "resolve" ? "Pregled je zabeležen." : "Dokument je odbijen i neće biti prikačen."); prati(p); return; }
      neuspeh(p, r.greska || {}, "Ništa nije promenjeno.");
    }

    async function prikaci(p, b) {
      if (p.radi || !zivi(p)) return;
      var moja = gen, pid = trenutni.id;
      if (!pid && trenutni.otvara) return;                      // drugi dokument čeka da prvi otvori predmet
      var telo = { predmet_id: pid };
      if (!pid) {
        var strana = $("pd-klijent-strana") ? tekst($("pd-klijent-strana").value) : "";
        telo = strana === "plaintiff" || strana === "defendant" ? { klijent_strana: strana } : {};
        trenutni.otvara = true;
      }
      zakljucaj(p, b, true); javi(p, "ucitavanje", pid ? "Prikačivanje dokumenta predmetu…" : "Otvaranje predmeta iz dokumenta…");
      p.od = Date.now();                                        // praćenje stanja posle prikačivanja ima svoj rok
      /* OCR001: `ok` je true SAMO za potvrđeno potpuno prikačivanje; false nosi `prikacivanje` (DELIMICNO/NIJE_PRIKACENO). */
      var r = await api.send("/api/smart-intake/jobs/" + encodeURIComponent(p.id) + "/finalize", { telo: telo, token: sesija.token(),
        oblik: function (x) { return typeof x.ok === "boolean"; } });
      if (!pid && moja === gen && trenutni) trenutni.otvara = false;
      if (moja !== gen || !zivi(p) || trenutni.id !== pid) return;
      zakljucaj(p, b, false);
      if (!pid && r.ok && r.podaci && ispravanId(r.podaci.predmet_id)) { otvoren(p, r.podaci); return; }
      if (r.ok && r.podaci && r.podaci.ok !== true) {
        var n = r.podaci, dup = Array.isArray(n.dokumenti) && n.dokumenti.some(function (q) { return q && q.razlog === "duplikat_u_drugom_predmetu"; });
        javi(p, "greska", n.predmet_id && n.predmet_id !== pid ? "Ovaj dokument se prikačuje drugom vašem predmetu i to prikačivanje nije završeno; ovde nije prikačen."
          : n.prikacivanje === "DELIMICNO" ? "Prikačivanje nije završeno: prikačeno je " + n.dokumenata_povezano + " od " + n.dokumenata_ukupno
            + " delova dokumenta. Ponovite prikačivanje za ostatak — već prikačeni delovi neće biti duplirani."
          : dup ? "Dokument NIJE prikačen: isti sadržaj već postoji u drugom vašem predmetu."
          : "Dokument NIJE prikačen. Ponovite prikačivanje — ništa neće biti duplirano.");
        prati(p);
        osvezi();
        return;
      }
      if (r.ok && r.podaci) {
        var x = r.podaci, delovi = [];
        if (x.predmet_id && x.predmet_id !== pid) delovi.push("Ovaj dokument je već bio prikačen drugom vašem predmetu; ovde nije ponovo prikačen.");
        else delovi.push("Dokument je prikačen predmetu. Podaci predmeta nisu menjani.");
        if (x.rok_dodat === true) delovi.push("Rok pronađen u dokumentu upisan je u hronologiju predmeta kao podatak iz dokumenta — proverite ga.");
        dodajPorukeRoka(x, delovi);
        javi(p, delovi[0].indexOf("Dokument je prikačen") === 0 ? "uspeh" : "nepoznato", delovi.join(" "));
        prati(p);
        osvezi();
        return;
      }
      if (r.ok) { javi(p, "nepoznato", "Prikačivanje je prihvaćeno, ali odgovor nije mogao da se pročita. Proverite dokumente predmeta."); prati(p); osvezi(); return; }
      /* OCR001: 409 = drugi pokušaj je u toku, prethodni je upravo prekinut, ili posao traži ručnu proveru. Ništa se ne
       * šalje ponovo samo od sebe; stanje se čita sa servera. */
      if (r.greska && r.greska.kod === "CONFLICT") { javi(p, "nepoznato", "Server sada ne prihvata prikačivanje (drugi pokušaj je u toku, prethodni je upravo prekinut ili dokument traži ručnu proveru). Dokument nije potvrđen u predmetu; stanje se ponovo proverava."); prati(p); return; }
      neuspeh(p, r.greska || {}, "Dokument nije prikačen.");
    }

    /* VCR001 T02: predmet je OTVOREN iz dokumenta — od sada se ostali dokumenti prikače njemu. Ishod se čita iz
     * odgovora servera; ništa se ne pretpostavlja (klijent, provera sukoba, rok). */
    /* N03: zašto rok iz dokumenta NIJE upisan — svaki razlog servera je posebna poruka; nepoznat razlog se prikazuje
     * doslovno, nikad se ne prećutkuje (izgledao bi kao dokument bez roka). */
    var RAZLOZI_ROKA = {
      niska_pouzdanost: "Rok iz dokumenta nije upisan jer njegova pouzdanost nije dovoljna.",
      bez_konkretnog_datuma: "Dokument pominje rok, ali bez konkretnog datuma — rok nije izračunat ni upisan. Utvrdite ga i unesite ručno.",
      upis_nije_uspeo: "Rok iz dokumenta NIJE upisan: upis nije uspeo. Unesite ga ručno u hronologiju predmeta.",
      vec_postoji: "Rok iz dokumenta već postoji u hronologiji predmeta; nije upisan ponovo."
    };
    function porukaPreskocenogRoka(razlog) {
      return Object.prototype.hasOwnProperty.call(RAZLOZI_ROKA, razlog) ? RAZLOZI_ROKA[razlog]
        : "Rok iz dokumenta nije upisan (razlog: " + tekst(razlog) + ").";
    }
    /* N03-FD1: razlog neupisa se kaže i kad je rok iz DRUGOG dela otpremanja upisan; različiti datumi u dokumentima
     * se ne razrešavaju — svaki je zaseban predlog, a advokat to mora da zna. Nema tvrdnje da je reč o istoj obavezi. */
    function dodajPorukeRoka(x, delovi) {
      if (x.rok_preskocen_razlog) delovi.push(porukaPreskocenogRoka(x.rok_preskocen_razlog));
      if (x.rokovi_razliciti_datumi === true) delovi.push("Delovi dokumenta navode različite datume roka. Nijedan nije izabran umesto drugog: svaki upisan datum je zaseban predlog koji čeka vašu potvrdu ili odbijanje. Sistem ne zna da li je reč o istoj obavezi — proverite ih u dokumentu.");
    }

    function otvoren(p, x) {
      trenutni.id = tekst(x.predmet_id);
      var delovi = ["Predmet „" + (tekst(x.naziv) || "bez naziva") + "“ je otvoren iz dokumenta."];
      if (x.klijent_dodat === true) delovi.push("Klijent iz dokumenta je povezan sa predmetom.");
      else if (x.klijent_nesiguran === true) delovi.push("Klijent NIJE povezan: u kartoteci postoji više klijenata sličnog imena. Povežite pravog u kartici Klijenti.");
      else delovi.push("Klijent nije povezan automatski. Povežite ga u kartici Klijenti.");
      if (x.coi_status === "COI_PENDING") delovi.push("Provera sukoba interesa iz dokumenta je zakazana u pozadini — to nije rezultat; pre prihvatanja zastupanja pokrenite proveru u kartici Klijenti.");
      else if (x.coi_status === "COI_FAILED") delovi.push("Provera sukoba interesa iz dokumenta NIJE zakazana. Pokrenite je ručno u kartici Klijenti.");
      if (x.rok_dodat === true) delovi.push("Rok pronađen u dokumentu upisan je u hronologiju kao podatak iz dokumenta — proverite ga.");
      dodajPorukeRoka(x, delovi);
      if (x.ok !== true) delovi.unshift("Dokument NIJE prikačen u novi predmet. Ponovite prikačivanje — predmet i deo koji je već sačuvan neće biti duplirani.");
      javi(p, x.ok === true ? "uspeh" : "greska", delovi.join(" "));
      naOtvoren(trenutni.id, tekst(x.naziv));
      poslovi.forEach(function (q) { if (q !== p && q.podaci) prikazi(q, null); });
      prati(p);
    }

    function postavi(predmet) {
      if (trenutni && trenutni.id === predmet.id && trenutni.korisnik === sesija.stanje().korisnik) return;
      ocisti();
      trenutni = { id: predmet.id, korisnik: sesija.stanje().korisnik };
    }
    /** „Nov predmet → Iz dokumenta“: prijem bez predmeta (prvi finalize ga otvara). */
    function pocniNov() {
      if (trenutni && trenutni.nov && trenutni.korisnik === sesija.stanje().korisnik) return;
      ocisti();
      trenutni = { id: null, nov: true, otvara: false, korisnik: sesija.stanje().korisnik };
    }

    $("pd-forma").addEventListener("submit", function (e) { e.preventDefault(); otpremi(); });
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) ocisti(); });

    return { postavi: postavi, pocniNov: pocniNov, aktiviraj: function () {}, ocisti: ocisti, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxPrijemPredmeta = Object.freeze({ napravi: napravi });
})(window);
