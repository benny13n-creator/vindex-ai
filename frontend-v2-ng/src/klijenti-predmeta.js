/* Vindex V2 NG — klijenti predmeta i provera sukoba interesa (NS005, CAP-030/031/032/188).
 *
 * Ugovori:
 *   GET  /klijenti?pretraga=&limit=        → {klijenti, ukupno}   (samo klijenti pozivaoca)
 *   POST /klijenti {tip, ime, prezime, firma, email, telefon} → {klijent}
 *   POST /api/conflict-check {ime_prezime, firma, email}     → {status, provera_potpuna, konflikti}
 *   POST /api/predmeti/{id}/confirm-links {klijent_ids, uloga} → {linked_klijenti}
 *        (server proverava vlasnika predmeta I svakog klijenta; tuđ klijent se tiho
 *         izostavlja iz `linked_klijenti` — zato se uspeh čita iz te liste, ne iz 200)
 * Osetljiva polja (JMBG, PIB, pasoš) se ovde ne unose i ne prikazuju.
 *
 * SUKOB INTERESA — samo se ČITA ishod backenda (domain/konflikt.js, Z017.1 §4):
 *   sukob → povezivanje BLOKIRANO (bez zaobilaženja u V2);
 *   pregled / nepotpuna provera / provera nije izvršena → samo uz izričitu potvrdu;
 *   čisto i potpuno → slobodno.
 * Jedina izmena u odnosu na serverski status: nalazi O ISTOM PREDMETU se izostavljaju
 * (predmet ne može biti u sukobu sam sa sobom — ime klijenta je često već upisano kao
 * tužilac tog predmeta), pa se status ponovo izvodi ISTIM pravilom kao u
 * routers/conflict_check.py (aktivan predmet → sukob; ostalo → pregled). Podudaranje
 * imena se ne dira.
 */
(function (root) {
  "use strict";

  var AKTIVNI = { "aktivan": 1, "u toku": 1, "u_toku": 1, "priprema": 1, "odložen": 1, "žalba": 1 };
  var TIP_SLOJA = { predmeti: "stranka u predmetu", klijenti: "klijent u kartoteci", uloge: "uloga u predmetu", advokat: "advokat suprotne strane" };
  var TIP_NALAZA = { tuzilac: "kao tužilac", tuzeni: "kao tuženi", naziv_predmeta: "u nazivu predmeta", suprotna_strana: "kao suprotna strana",
                     bivsi_klijent: "kao bivši klijent", klijent_u_sistemu: "kao klijent" };

  function tekst(v) { return String(v == null ? "" : v).trim(); }
  function imeKlijenta(k) { var i = [tekst(k.ime), tekst(k.prezime)].filter(Boolean).join(" "); return i || tekst(k.firma) || "Klijent bez imena"; }

  /** Serverski odgovor → ishod; `predmetId` = predmet za koji se klijent vezuje. */
  function ishod(sirov, predmetId) {
    if (!sirov || typeof sirov !== "object" || !tekst(sirov.status)) {
      return { vrsta: "nepotpuna", nastavak: "potvrda", konflikti: [], naslov: "Provera sukoba interesa nije izvršena",
               telo: "Odsustvo rezultata NE znači da sukoba nema. Ponovite proveru pre povezivanja." };
    }
    var svi = Array.isArray(sirov.konflikti) ? sirov.konflikti : [];
    var drugi = svi.filter(function (k) { return k && tekst(k.predmet_id) !== String(predmetId); }).map(function (k) {
      return { predmet: tekst(k.predmet_naziv) || "Predmet bez naziva", aktivan: !!AKTIVNI[tekst(k.predmet_status).toLowerCase()],
               opis: [TIP_SLOJA[tekst(k.sloj)] || tekst(k.sloj), TIP_NALAZA[tekst(k.tip_konflikta)] || ""].filter(Boolean).join(", "),
               podudaranje: tekst(k.podudaranje) };
    });
    var potpuna = sirov.provera_potpuna === true;
    if (drugi.some(function (k) { return k.aktivan; })) {
      return { vrsta: "sukob", nastavak: "blokirano", konflikti: drugi, naslov: "Sukob interesa u aktivnom predmetu",
               telo: "Povezivanje je zaustavljeno. Proverite navedene predmete i Kodeks profesionalne etike." };
    }
    if (!potpuna) {
      var sl = Array.isArray(sirov.slojevi_greska) ? sirov.slojevi_greska.map(tekst).filter(Boolean) : [];
      return { vrsta: "nepotpuna", nastavak: "potvrda", konflikti: drugi, naslov: "Provera sukoba interesa nije potpuna",
               telo: (sl.length ? "Nije pretraženo: " + sl.join(", ") + ". " : "") + "Odsustvo rezultata NE znači da sukoba nema." };
    }
    if (drugi.length) {
      return { vrsta: "pregled", nastavak: "potvrda", konflikti: drugi, naslov: "Pronađeno preklapanje koje traži proveru",
               telo: "Preklapanje je u zatvorenim predmetima. Pregledajte ga pre povezivanja." };
    }
    return { vrsta: "cisto", nastavak: "slobodno", konflikti: [], naslov: "Nije pronađen sukob interesa", telo: "" };
  }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api, osvezi = o.osvezi;
    var trenutni = null, izabran = null, coi = null;
    var genPretrage = 0, genCoi = 0, genUpisa = 0, kPretraga = null, kCoi = null, kUpis = null, tajmer = 0, salje = false;
    var naCekanju = null;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function poruka(stanje, t) { var n = $("kl-poruka"); if (!stanje) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = stanje; n.textContent = t; }
    function stanjePretrage(t, oznaka) { var s = $("kl-stanje"); s.hidden = !t; s.textContent = t || ""; if (oznaka) s.dataset.stanje = oznaka; else delete s.dataset.stanje; }
    function prekini(k) { if (k) k.abort(); return null; }

    function ponistiIzbor() {
      genCoi++; kCoi = prekini(kCoi);
      izabran = null; coi = null;
      $("kl-izabran").hidden = true; $("kl-izabran-ime").textContent = "";
      $("kl-coi").hidden = true; $("kl-coi-naslov").textContent = ""; $("kl-coi-telo").textContent = ""; $("kl-coi-lista").replaceChildren();
      delete $("kl-coi").dataset.stanje;
      $("kl-potvrda-red").hidden = true; $("kl-potvrda").checked = false;
      uskladiDugme();
    }
    function zatvoriPanel() {
      genPretrage++; genUpisa++; kPretraga = prekini(kPretraga); kUpis = prekini(kUpis); clearTimeout(tajmer);
      salje = false;
      ponistiIzbor();
      $("kl-panel").hidden = true; $("kl-otvori").hidden = !trenutni;
      $("kl-pretraga").value = ""; $("kl-rezultati").replaceChildren(); stanjePretrage(null);
      $("kl-nov-forma").reset(); $("kl-nov-forma").hidden = true; $("kl-nov-prekidac").setAttribute("aria-expanded", "false");
      poruka(null);
    }
    function ocisti() {
      zatvoriPanel();
      trenutni = null;
      $("kl-otvori").hidden = true;
      $("kl-uspeh").hidden = true; $("kl-uspeh").textContent = "";
    }
    function uskladiDugme() {
      var b = $("kl-povezi");
      var moze = !!izabran && !!coi && !salje && (coi.nastavak === "slobodno" || (coi.nastavak === "potvrda" && $("kl-potvrda").checked));
      b.disabled = !moze;
      b.textContent = salje ? "Povezivanje…" : "Poveži sa predmetom";
    }

    function postavi(predmet) {
      ocisti();
      trenutni = { id: predmet.id, korisnik: sesija.stanje().korisnik };
      $("kl-otvori").hidden = false;
      if (naCekanju && naCekanju.id === predmet.id && naCekanju.korisnik === trenutni.korisnik) {
        $("kl-uspeh").hidden = false; $("kl-uspeh").dataset.stanje = "uspeh"; $("kl-uspeh").textContent = naCekanju.tekst;
      }
      naCekanju = null;
    }

    function prijavljen() {
      var s = sesija.stanje();
      return trenutni && s.stanje === sesija.STANJA.PRIJAVLJEN && s.korisnik === trenutni.korisnik;
    }

    /* ── Pretraga ── */
    async function pretrazi() {
      var q = $("kl-pretraga").value.replace(/[,()%*\\]/g, " ").trim().slice(0, 80);
      genPretrage++; kPretraga = prekini(kPretraga);
      $("kl-rezultati").replaceChildren();
      if (q.length < 2) { stanjePretrage(q ? "Upišite bar dva slova." : null); return; }
      if (!prijavljen()) { stanjePretrage("Niste prijavljeni. Pretraga nije izvršena.", "greska"); return; }
      var moja = genPretrage, korisnik = trenutni.korisnik;
      kPretraga = new AbortController();
      stanjePretrage("Pretraga…", "ucitavanje");
      var r = await api.get("/klijenti", { token: sesija.token(), signal: kPretraga.signal, parametri: { pretraga: q, limit: 20 },
        oblik: function (x) { return Array.isArray(x.klijenti); } });
      if (moja !== genPretrage || !trenutni || trenutni.korisnik !== korisnik) return;
      kPretraga = null;
      if (!r.ok) {
        if (r.greska && r.greska.kod === "ABORTED") return;
        stanjePretrage("Pretraga nije uspela. Ovo nije prazan rezultat; pokušajte ponovo.", "greska");
        return;
      }
      var lista = r.podaci.klijenti.filter(function (k) { return k && k.id !== undefined && k.id !== null; });
      if (!lista.length) { stanjePretrage("Nijedan klijent ne odgovara pretrazi „" + q + "“.", "prazno"); return; }
      stanjePretrage(null);
      lista.forEach(function (k) {
        var li = el("li"), b = el("button", "pick__item");
        b.type = "button"; b.dataset.klijent = String(k.id);
        b.append(el("span", "pick__name", imeKlijenta(k)));
        var meta = [tekst(k.firma) && imeKlijenta(k) !== tekst(k.firma) ? tekst(k.firma) : "", tekst(k.email)].filter(Boolean).join(" · ");
        if (meta) b.append(el("span", "pick__meta", meta));
        b.addEventListener("click", function () { izaberi({ id: String(k.id), ime: tekst(k.ime), prezime: tekst(k.prezime), firma: tekst(k.firma), email: tekst(k.email), tip: tekst(k.tip) }); });
        li.append(b); $("kl-rezultati").append(li);
      });
    }

    /* ── Izbor + provera sukoba ── */
    async function izaberi(k) {
      ponistiIzbor();
      poruka(null);
      izabran = k;
      d.querySelectorAll("#kl-rezultati .pick__item").forEach(function (x) {
        if (x.dataset.klijent === k.id) x.setAttribute("aria-current", "true"); else x.removeAttribute("aria-current");
      });
      $("kl-izabran").hidden = false;
      $("kl-izabran-ime").textContent = imeKlijenta(k);
      var coiEl = $("kl-coi");
      coiEl.hidden = false; coiEl.dataset.stanje = "ucitavanje";
      $("kl-coi-naslov").textContent = "Provera sukoba interesa…"; $("kl-coi-telo").textContent = "";
      uskladiDugme();
      var telo = {};
      var ime = [k.ime, k.prezime].filter(Boolean).join(" ");
      if (ime) telo.ime_prezime = ime;
      if (k.firma) telo.firma = k.firma;
      if (k.email) telo.email = k.email;
      if (!telo.ime_prezime && !telo.firma) { prikaziCoi(ishod(null, trenutni.id)); return; }
      if (!prijavljen()) { prikaziCoi(ishod(null, trenutni.id)); return; }
      var moja = ++genCoi, korisnik = trenutni.korisnik, pid = trenutni.id;
      kCoi = new AbortController();
      // Provera ne upisuje podatke predmeta; neuspeh nije „čisto" nego „nije izvršena".
      var r = await api.send("/api/conflict-check", { telo: telo, token: sesija.token(), signal: kCoi.signal,
        oblik: function (x) { return typeof x.status === "string"; } });
      if (moja !== genCoi || !trenutni || trenutni.id !== pid || trenutni.korisnik !== korisnik) return;
      kCoi = null;
      prikaziCoi(ishod(r.ok ? r.podaci : null, pid));
    }
    function prikaziCoi(i) {
      coi = i;
      var coiEl = $("kl-coi");
      coiEl.hidden = false; coiEl.dataset.stanje = i.vrsta;
      $("kl-coi-naslov").textContent = i.naslov; $("kl-coi-telo").textContent = i.telo;
      $("kl-coi-lista").replaceChildren();
      i.konflikti.forEach(function (k) {
        var li = el("li", "coi__item");
        li.append(el("span", "coi__case", k.predmet + (k.aktivan ? " (aktivan)" : " (zatvoren)")));
        var m = [k.opis, k.podudaranje ? "podudaranje: " + k.podudaranje : ""].filter(Boolean).join(" · ");
        if (m) li.append(el("span", "coi__meta", m));
        $("kl-coi-lista").append(li);
      });
      $("kl-potvrda-red").hidden = i.nastavak !== "potvrda";
      $("kl-potvrda").checked = false;
      uskladiDugme();
    }

    /* ── Nov klijent ── */
    async function napraviKlijenta() {
      if (salje || !prijavljen()) { if (!prijavljen()) poruka("greska", "Niste prijavljeni. Klijent nije sačuvan."); return; }
      var ime = $("kl-ime").value.trim();
      if (ime.length < 2) { $("kl-ime").setAttribute("aria-invalid", "true"); poruka("greska", "Ime (ili naziv) klijenta mora imati bar dva znaka."); $("kl-ime").focus(); return; }
      $("kl-ime").removeAttribute("aria-invalid");
      var telo = { tip: $("kl-tip").value === "pravno_lice" ? "pravno_lice" : "fizicko_lice", ime: ime.slice(0, 200) };
      [["prezime", "kl-prezime", 200], ["firma", "kl-firma", 300], ["email", "kl-email", 200], ["telefon", "kl-telefon", 50]].forEach(function (x) {
        var v = $(x[1]).value.trim(); if (v) telo[x[0]] = v.slice(0, x[2]);
      });
      var moja = ++genUpisa, korisnik = trenutni.korisnik, pid = trenutni.id;
      salje = true; kUpis = new AbortController();
      $("kl-nov-sacuvaj").disabled = true; uskladiDugme();
      poruka("ucitavanje", "Klijent se čuva…");
      var r = await api.send("/klijenti", { telo: telo, token: sesija.token(), signal: kUpis.signal,
        oblik: function (x) { return x.klijent && x.klijent.id !== undefined && x.klijent.id !== null; } });
      if (moja !== genUpisa || !trenutni || trenutni.id !== pid || trenutni.korisnik !== korisnik) return;
      salje = false; kUpis = null; $("kl-nov-sacuvaj").disabled = false;
      if (r.ok && r.podaci) {
        var k = r.podaci.klijent;
        $("kl-nov-forma").reset(); $("kl-nov-forma").hidden = true; $("kl-nov-prekidac").setAttribute("aria-expanded", "false");
        poruka("uspeh", "Klijent je sačuvan u kartoteci. Sledi provera sukoba interesa.");
        izaberi({ id: String(k.id), ime: tekst(k.ime), prezime: tekst(k.prezime), firma: tekst(k.firma), email: tekst(k.email), tip: tekst(k.tip) });
        return;
      }
      uskladiDugme();
      if (r.ok) { poruka("nepoznato", "Klijent je sačuvan, ali odgovor servera nije mogao da se pročita. Pronađite ga pretragom; ne čuvajte ga ponovo."); return; }
      var g = r.greska || {};
      if (g.ishodNepoznat) { poruka("nepoznato", "Ishod nije poznat: klijent je možda sačuvan. Pronađite ga pretragom pre nego što pokušate ponovo."); return; }
      poruka("greska", { CONFLICT: "Klijent sa ovim imenom je upravo sačuvan. Pronađite ga pretragom.", VALIDATION_ERROR: "Server nije prihvatio podatke klijenta (proverite ime i e-poštu). Klijent nije sačuvan.",
        AUTH_REQUIRED: "Prijava više nije važeća. Klijent nije sačuvan.", RATE_LIMITED: "Previše zahteva. Klijent nije sačuvan." }[g.kod] || "Server je odbio zahtev. Klijent nije sačuvan.");
    }

    /* ── Povezivanje ── */
    async function povezi() {
      if (salje || !izabran || !coi || !prijavljen()) return;
      if (coi.nastavak === "blokirano" || (coi.nastavak === "potvrda" && !$("kl-potvrda").checked)) { uskladiDugme(); return; }
      var moja = ++genUpisa, korisnik = trenutni.korisnik, pid = trenutni.id, kid = izabran.id, ime = imeKlijenta(izabran);
      salje = true; kUpis = new AbortController(); uskladiDugme();
      poruka("ucitavanje", "Klijent se povezuje…");
      var r = await api.send("/api/predmeti/" + encodeURIComponent(pid) + "/confirm-links", { telo: { klijent_ids: [kid], uloga: "stranka" },
        token: sesija.token(), signal: kUpis.signal, oblik: function (x) { return Array.isArray(x.linked_klijenti); } });
      if (moja !== genUpisa || !trenutni || trenutni.id !== pid || trenutni.korisnik !== korisnik) return;
      salje = false; kUpis = null; uskladiDugme();
      if (r.ok && r.podaci && r.podaci.linked_klijenti.map(String).indexOf(kid) !== -1) {
        naCekanju = { id: pid, korisnik: korisnik, tekst: "Klijent " + ime + " je povezan sa predmetom." };
        osvezi();
        return;
      }
      if (r.ok && r.podaci) { poruka("greska", "Server nije povezao ovog klijenta sa predmetom. Ništa nije promenjeno."); return; }
      if (r.ok) { poruka("nepoznato", "Povezivanje je prihvaćeno, ali odgovor nije mogao da se pročita. Osvežite predmet i proverite listu klijenata."); return; }
      var g = r.greska || {};
      if (g.ishodNepoznat) { poruka("nepoznato", "Ishod nije poznat: klijent je možda povezan. Osvežite predmet i proverite listu klijenata pre ponovnog pokušaja."); return; }
      poruka("greska", { NOT_FOUND: "Predmet nije dostupan. Ništa nije promenjeno.", AUTH_REQUIRED: "Prijava više nije važeća. Ništa nije promenjeno.",
        RATE_LIMITED: "Previše zahteva. Ništa nije promenjeno." }[g.kod] || "Server je odbio zahtev. Ništa nije promenjeno.");
    }

    $("kl-otvori").addEventListener("click", function () {
      if (!trenutni) return;
      $("kl-uspeh").hidden = true;
      $("kl-panel").hidden = false; $("kl-otvori").hidden = true; $("kl-pretraga").focus();
    });
    $("kl-odustani").addEventListener("click", function () { zatvoriPanel(); $("kl-otvori").focus(); });
    $("kl-pretraga").addEventListener("input", function () { clearTimeout(tajmer); tajmer = setTimeout(pretrazi, 300); });
    $("kl-pretraga").addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); clearTimeout(tajmer); pretrazi(); } });
    $("kl-nov-prekidac").addEventListener("click", function () {
      var otvoren = $("kl-nov-forma").hidden;
      $("kl-nov-forma").hidden = !otvoren; $("kl-nov-prekidac").setAttribute("aria-expanded", String(otvoren));
      if (otvoren) $("kl-ime").focus();
    });
    $("kl-nov-forma").addEventListener("submit", function (e) { e.preventDefault(); napraviKlijenta(); });
    $("kl-potvrda").addEventListener("change", uskladiDugme);
    $("kl-povezi").addEventListener("click", povezi);
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) { naCekanju = null; ocisti(); } });

    return { postavi: postavi, ocisti: ocisti, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxKlijentiPredmeta = Object.freeze({ napravi: napravi, ishod: ishod });
})(window);
