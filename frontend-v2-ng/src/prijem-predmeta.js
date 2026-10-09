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

  var RAZMAK_MS = 3000, NAJDUZE_MS = 5 * 60 * 1000;
  var ZAVRSNA = { awaiting_review: 1, completed: 1, failed: 1 };
  var STANJA = { received: "U redu za obradu", preprocessing: "Priprema dokumenta", classifying: "Prepoznavanje vrste dokumenta",
    extracting: "Izdvajanje podataka", matching: "Povezivanje podataka", dedup_check: "Provera duplikata",
    awaiting_review: "Čeka vaš pregled", completed: "Obrađeno — spremno za prikačivanje", failed: "Obrada nije uspela" };
  var POLJA = { case_number: "Broj predmeta", court: "Sud", judge: "Sudija", plaintiff: "Tužilac", defendant: "Tuženi",
    deadline: "Rok", amount: "Iznos", date: "Datum", contract_party: "Ugovorna strana", claim_basis: "Osnov zahteva" };
  var VRSTE = { court_decision: "Sudska odluka", judgment: "Presuda", lawsuit: "Tužba", complaint: "Tužba", appeal: "Žalba",
    contract: "Ugovor", power_of_attorney: "Punomoćje", invoice: "Faktura", decision: "Rešenje", summons: "Poziv suda",
    notice: "Obaveštenje", other: "Ostalo", unknown: "Nije prepoznato" };
  var RAZLOZI = { ocr_failed: "Tekst dokumenta nije mogao da se pročita (OCR nije uspeo). Ništa nije izvučeno.",
    classification_uncertain: "Vrsta dokumenta nije pouzdano prepoznata.", low_confidence_extraction: "Neki podaci nisu pouzdano izdvojeni.",
    segmentation_uncertain: "Nije sigurno gde jedan dokument prestaje, a drugi počinje." };
  var DOZVOLJENO = /\.(pdf|docx|txt|jpe?g|png)$/i, MAX_B = 25 * 1024 * 1024;

  function tekst(v) { return String(v == null ? "" : v).trim(); }
  function ispravanId(v) { return /^[A-Za-z0-9_-]{1,64}$/.test(tekst(v)); }
  function procenat(p) { var n = Number(p); return Number.isFinite(n) ? Math.round(n * 100) + "%" : "—"; }
  function nazivPolja(t) { return POLJA[t] || tekst(t).replace(/_/g, " "); }
  function nazivVrste(t) { return VRSTE[tekst(t)] || tekst(t).replace(/_/g, " ") || "Nije prepoznato"; }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api, osvezi = o.osvezi || function () {};
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

    async function prati(p) {
      zaustaviPracenje(p);
      if (!zivi(p)) return;
      p.k = new AbortController();
      var r = await api.get("/api/smart-intake/jobs/" + encodeURIComponent(p.id), { token: sesija.token(), signal: p.k.signal,
        oblik: function (x) { return x.job && typeof x.job.status === "string" && Array.isArray(x.entiteti); } });
      if (!zivi(p)) return;
      p.k = null;
      if (!r.ok) {
        if (r.greska && r.greska.kod === "ABORTED") return;
        prikazi(p, r.greska && r.greska.kod === "NOT_FOUND" ? "Posao nije dostupan." : "Stanje posla nije učitano zbog greške. Ovo ne znači da obrada nije uspela.");
        p.tajmer = setTimeout(function () { prati(p); }, RAZMAK_MS * 2);
        return;
      }
      p.podaci = r.podaci;
      var st = tekst(p.podaci.job.status);
      if (ZAVRSNA[st]) { prikazi(p, null); return; }
      if (Date.now() - p.od > NAJDUZE_MS) { prikazi(p, "Praćenje je zaustavljeno posle 5 minuta. Obrada se nastavlja na serveru — ponovo otpremite isti fajl da biste videli njen ishod."); return; }
      prikazi(p, null);
      p.tajmer = setTimeout(function () { prati(p); }, RAZMAK_MS);
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
      if (provera && RAZLOZI[tekst(provera.razlog)]) { var pr = el("p", "notice", RAZLOZI[tekst(provera.razlog)]); pr.dataset.stanje = "nepoznato"; li.append(pr); }
      if (dok && !(provera && tekst(provera.razlog) === "ocr_failed")) {
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
      if (st === "completed" && !j.predmet_id) akcije.append(dugme("Prikači ovom predmetu", "text-btn text-btn--primary", function (b) { prikaci(p, b); }));
      if (j.predmet_id && j.predmet_id === trenutni.id) li.append(el("p", "intake__done", "Prikačeno ovom predmetu."));
      else if (j.predmet_id) li.append(el("p", "notice", "Ovaj dokument je već prikačen drugom vašem predmetu."));
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
      zakljucaj(p, b, true); javi(p, "ucitavanje", "Prikačivanje dokumenta predmetu…");
      var r = await api.send("/api/smart-intake/jobs/" + encodeURIComponent(p.id) + "/finalize", { telo: { predmet_id: pid }, token: sesija.token(),
        oblik: function (x) { return x.ok === true; } });
      if (moja !== gen || !zivi(p) || trenutni.id !== pid) return;
      zakljucaj(p, b, false);
      if (r.ok && r.podaci) {
        var x = r.podaci, delovi = [];
        if (x.predmet_id && x.predmet_id !== pid) delovi.push("Ovaj dokument je već bio prikačen drugom vašem predmetu; ovde nije ponovo prikačen.");
        else delovi.push("Dokument je prikačen predmetu. Podaci predmeta nisu menjani.");
        if (x.dokumenata_povezano !== undefined && x.dokumenata_ukupno !== undefined && x.dokumenata_povezano < x.dokumenata_ukupno)
          delovi.push("Prikačeno je " + x.dokumenata_povezano + " od " + x.dokumenata_ukupno + " delova dokumenta; ponovite prikačivanje za ostatak.");
        if (x.rok_dodat === true) delovi.push("Rok pronađen u dokumentu upisan je u hronologiju predmeta kao podatak iz dokumenta — proverite ga.");
        else if (x.rok_preskocen_razlog === "niska_pouzdanost") delovi.push("Rok iz dokumenta nije upisan jer njegova pouzdanost nije dovoljna.");
        javi(p, delovi[0].indexOf("Dokument je prikačen") === 0 ? "uspeh" : "nepoznato", delovi.join(" "));
        prati(p);
        osvezi();
        return;
      }
      if (r.ok) { javi(p, "nepoznato", "Prikačivanje je prihvaćeno, ali odgovor nije mogao da se pročita. Proverite dokumente predmeta."); prati(p); osvezi(); return; }
      neuspeh(p, r.greska || {}, "Dokument nije prikačen.");
    }

    function postavi(predmet) {
      if (trenutni && trenutni.id === predmet.id && trenutni.korisnik === sesija.stanje().korisnik) return;
      ocisti();
      trenutni = { id: predmet.id, korisnik: sesija.stanje().korisnik };
    }

    $("pd-forma").addEventListener("submit", function (e) { e.preventDefault(); otpremi(); });
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) ocisti(); });

    return { postavi: postavi, aktiviraj: function () {}, ocisti: ocisti, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxPrijemPredmeta = Object.freeze({ napravi: napravi });
})(window);
