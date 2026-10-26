/* Vindex V2 NG — Podešavanja › Kancelarija (Settings Master Sprint P1.5).
 *
 * Ugovori (routers/kancelarija.py; kancelarija i uloga se određuju na serveru iz tokena):
 *   GET    /api/kancelarija/moja            → {status: no_firma | pending_invite | aktivan, moja_uloga, firma{id,naziv}, clanovi[]}
 *   PUT    /api/kancelarija/naziv {naziv}   → {ok, naziv}                       (samo administrator)
 *   POST   /api/kancelarija/pozovi {email, uloga} → 201 {ok, action, email, uloga} (samo administrator; ne šalje email)
 *   PUT    /api/kancelarija/uloga/{id} {uloga}     → {ok, uloga}                (samo administrator, član iste kancelarije)
 *   POST   /api/kancelarija/suspenduj/{id}, /reaktiviraj/{id} → {ok}           (samo administrator)
 *   DELETE /api/kancelarija/ukloni/{id}    → {ok}                               (samo administrator, ne sebe)
 * Kontrole se prikazuju samo administratoru, ali to je UX — svaku radnju odobrava ili odbija server.
 * Lokalni V1 podaci o firmi (localStorage `vindex_firma`) se NE čitaju i ne postaju podaci kancelarije.
 */
(function (root) {
  "use strict";

  var ULOGE = [["partner", "Partner"], ["saradnik", "Saradnik"], ["citanje", "Samo čitanje"]];
  var STATUS = { ACTIVE: "aktivan", INVITED: "pozvan", SUSPENDED: "suspendovan", PENDING: "na čekanju" };
  var ID = /^[A-Za-z0-9-]{1,64}$/;
  function tekst(v) { return String(v == null ? "" : v).trim(); }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api, gen = 0, era = 0, kontrola = null, otvoren = false, podaci = null, zauzeto = false, potvrda = null;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function poruka(id, st, t) { var n = $(id); n.hidden = !st; n.textContent = t || ""; if (st) n.dataset.stanje = st; else delete n.dataset.stanje; }
    function jeAdmin() { return !!podaci && podaci.moja_uloga === "admin"; }

    /* `gen` redosled čitanja (svako `ucitaj` ga povećava); `era` se menja SAMO pri čišćenju (promena naloga,
       zatvaranje) — radnja proverava eru, inače bi njeno sopstveno osvežavanje progutalo poruku o ishodu. */
    function ocisti() {
      era++; gen++; if (kontrola) kontrola.abort(); kontrola = null;
      podaci = null; zauzeto = false; potvrda = null;
      $("pn-kanc-podaci").hidden = true;
      $("pn-kanc-naziv").textContent = ""; $("pn-kanc-uloga").textContent = "";
      $("pn-kanc-naziv-unos").value = ""; $("pn-kanc-poziv-email").value = "";
      $("pn-kanc-clanovi").replaceChildren();
      poruka("pn-kanc-stanje", null); poruka("pn-kanc-poruka", null);
    }

    function validno(x) {
      if (!x || typeof x.status !== "string") return false;
      if (x.status !== "aktivan") return true;
      return !!x.firma && typeof x.firma.naziv === "string" && Array.isArray(x.clanovi) && typeof x.moja_uloga === "string";
    }

    function zakljucaj(z) {
      zauzeto = z;
      $("pn-kanc-podaci").querySelectorAll("button, input, select").forEach(function (n) {
        n.disabled = z || (n.dataset.ulogaZa !== undefined && n.previousSibling.value === n.dataset.ulogaZa);
      });
    }

    function nacrtajClanove() {
      var lista = $("pn-kanc-clanovi");
      lista.replaceChildren();
      var clanovi = podaci.clanovi.filter(function (c) { return c && ID.test(tekst(c.id)); });
      if (!clanovi.length) { lista.append(el("li", "people__item", "U kancelariji još nema drugih članova.")); return; }
      clanovi.forEach(function (c) {
        var li = el("li", "people__item");
        li.dataset.clan = c.id;
        li.append(el("span", "people__name", tekst(c.email)));
        li.append(el("span", "people__meta", [tekst(c.uloga_label) || tekst(c.uloga), STATUS[tekst(c.status)] || tekst(c.status).toLowerCase()].filter(Boolean).join(" · ")));
        if (jeAdmin()) {
          var red = el("div", "form__actions pn-clan-radnje");
          var izbor = el("select", "field__input");
          izbor.setAttribute("aria-label", "Uloga za " + tekst(c.email));
          ULOGE.forEach(function (u) { var op = el("option", null, u[1]); op.value = u[0]; izbor.append(op); });
          izbor.value = ULOGE.some(function (u) { return u[0] === c.uloga; }) ? c.uloga : "";
          var promeni = el("button", "text-btn text-btn--line", "Promeni ulogu");
          promeni.type = "button"; promeni.disabled = true; promeni.dataset.ulogaZa = tekst(c.uloga);
          izbor.addEventListener("change", function () { promeni.disabled = zauzeto || izbor.value === c.uloga; });
          promeni.addEventListener("click", function () {
            if (izbor.value === c.uloga) return;
            radnja("/api/kancelarija/uloga/" + c.id, "PUT", { uloga: izbor.value }, "Uloga za " + tekst(c.email) + " je promenjena.");
          });
          red.append(izbor, promeni);
          if (c.status === "ACTIVE") red.append(dugme("Suspenduj", function () { radnja("/api/kancelarija/suspenduj/" + c.id, "POST", null, tekst(c.email) + " je suspendovan."); }));
          if (c.status === "SUSPENDED") red.append(dugme("Reaktiviraj", function () { radnja("/api/kancelarija/reaktiviraj/" + c.id, "POST", null, tekst(c.email) + " je ponovo aktivan."); }));
          var ukloni = dugme(potvrda === c.id ? "Potvrdi uklanjanje" : (c.status === "INVITED" ? "Povuci poziv" : "Ukloni iz kancelarije"), function () {
            if (potvrda !== c.id) { potvrda = c.id; nacrtajClanove(); return; }
            potvrda = null;
            radnja("/api/kancelarija/ukloni/" + c.id, "DELETE", null, tekst(c.email) + " više nije član kancelarije.");
          });
          ukloni.dataset.radnja = "ukloni";
          red.append(ukloni);
          li.append(red);
        }
        lista.append(li);
      });
    }
    function dugme(t, fn) { var b = el("button", "text-btn", t); b.type = "button"; b.addEventListener("click", fn); return b; }

    function prikazi() {
      var x = podaci;
      poruka("pn-kanc-stanje", null);
      if (x.status === "no_firma") { poruka("pn-kanc-stanje", "prazno", "Niste član nijedne kancelarije u Vindexu. Lična podešavanja su u ostalim odeljcima."); return; }
      if (x.status === "pending_invite") { poruka("pn-kanc-stanje", "prazno", "Imate poziv u kancelariju „" + tekst(x.firma_naziv) + "“. Poziv prihvatate u klasičnom prikazu."); return; }
      if (x.status !== "aktivan") { poruka("pn-kanc-stanje", "greska", "Odgovor servera nije ispravan. Kancelarija se ne prikazuje."); return; }
      $("pn-kanc-naziv").textContent = tekst(x.firma.naziv) || "Kancelarija bez naziva";
      $("pn-kanc-uloga").textContent = x.moja_uloga === "admin" ? "Administrator" : (ULOGE.filter(function (u) { return u[0] === x.moja_uloga; })[0] || [0, tekst(x.moja_uloga)])[1];
      $("pn-kanc-samo-citanje").hidden = jeAdmin();
      $("pn-kanc-naziv-forma").hidden = !jeAdmin();
      $("pn-kanc-poziv-forma").hidden = !jeAdmin();
      if (jeAdmin() && !$("pn-kanc-naziv-unos").value) $("pn-kanc-naziv-unos").value = tekst(x.firma.naziv);
      nacrtajClanove();
      $("pn-kanc-podaci").hidden = false;
      zakljucaj(false);
    }

    async function ucitaj(porukaPosle) {
      var moj = ++gen; if (kontrola) kontrola.abort(); kontrola = new AbortController();
      if (!podaci) poruka("pn-kanc-stanje", "ucitavanje", "Učitavanje kancelarije…");
      var r = await api.get("/api/kancelarija/moja", { token: sesija.token(), signal: kontrola.signal, oblik: validno });
      if (moj !== gen) return;
      kontrola = null;
      if (!r.ok) {
        if (r.greska.kod === "ABORTED") return;
        podaci = null; $("pn-kanc-podaci").hidden = true;
        poruka("pn-kanc-stanje", "greska", r.greska.kod === "AUTH_REQUIRED" ? "Prijava je istekla. Prijavite se ponovo."
          : "Podaci kancelarije nisu učitani. Ovo nije prazna kancelarija.");
        return;
      }
      podaci = r.podaci;
      prikazi();
      if (porukaPosle) poruka("pn-kanc-poruka", "uspeh", porukaPosle);
    }

    function greska(r) {
      var g = r.greska || {};
      if (g.ishodNepoznat) return "Ishod nije poznat. Lista je osvežena — proverite stanje pre ponavljanja.";
      if (g.kod === "FORBIDDEN") return "Server je odbio radnju: samo administrator kancelarije, i samo kada ima slobodnih mesta za poziv/reaktivaciju.";
      if (g.kod === "NOT_FOUND") return "Član nije pronađen u vašoj kancelariji. Lista je osvežena.";
      if (g.kod === "CONFLICT") return "Ta adresa je već član ili ima poziv u ovoj kancelariji.";
      if (g.kod === "BAD_REQUEST") return "Radnja nije moguća u trenutnom stanju člana. Lista je osvežena.";
      if (g.kod === "VALIDATION_ERROR") return "Unos nije prihvaćen. Proverite podatke.";
      if (g.kod === "RATE_LIMITED") return "Previše zahteva. Pokušajte ponovo za minut.";
      if (g.kod === "AUTH_REQUIRED") return "Prijava je istekla. Ništa nije promenjeno.";
      return "Radnja nije potvrđena (" + (g.kod || "greška") + ").";
    }

    async function radnja(putanja, metod, telo, uspeh) {
      if (zauzeto || !jeAdmin()) return false;
      /* Pripremljeno uklanjanje važi samo do sledeće radnje — ne preživljava preimenovanje, promenu uloge i sl. */
      potvrda = null;
      var moj = era;
      zakljucaj(true);
      poruka("pn-kanc-poruka", "ucitavanje", "Zahtev je u toku…");
      var r = await api.send(putanja, { metod: metod, telo: telo, token: sesija.token() });
      if (moj !== era) return false;
      if (r.ok && !(r.podaci && r.podaci.ok === true)) {
        await ucitaj();
        if (moj === era) poruka("pn-kanc-poruka", "nepoznato", "Server je prihvatio zahtev, ali potvrda nije čitljiva. Lista je osvežena.");
        return false;
      }
      if (!r.ok) {
        var t = greska(r);
        await ucitaj();
        if (moj === era) poruka("pn-kanc-poruka", r.greska.ishodNepoznat ? "nepoznato" : "greska", t);
        return false;
      }
      await ucitaj(uspeh);
      return true;
    }

    $("pn-kanc-naziv-forma").addEventListener("submit", function (e) {
      e.preventDefault();
      var n = $("pn-kanc-naziv-unos").value.trim();
      if (n.length < 2 || n.length > 120) { poruka("pn-kanc-poruka", "greska", "Naziv mora imati od 2 do 120 znakova."); return; }
      if (podaci && n === tekst(podaci.firma.naziv)) { poruka("pn-kanc-poruka", "greska", "Naziv je isti kao trenutni."); return; }
      radnja("/api/kancelarija/naziv", "PUT", { naziv: n }, "Naziv kancelarije je sačuvan.");
    });
    $("pn-kanc-poziv-forma").addEventListener("submit", function (e) {
      e.preventDefault();
      var em = $("pn-kanc-poziv-email").value.trim().toLowerCase(), u = $("pn-kanc-poziv-uloga").value;
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em) || em.length > 255) { poruka("pn-kanc-poruka", "greska", "Unesite ispravnu email adresu."); return; }
      var moj = era;
      /* Unos se briše tek kada server potvrdi poziv — pri 409/422 adresa ostaje za ispravku. */
      radnja("/api/kancelarija/pozovi", "POST", { email: em, uloga: u }, "Poziv za " + em + " je dodat. Email se ne šalje.")
        .then(function (ok) { if (ok && moj === era) $("pn-kanc-poziv-email").value = ""; });
    });

    function pokreni() {
      if (sesija.stanje().stanje !== sesija.STANJA.PRIJAVLJEN) { poruka("pn-kanc-stanje", "greska", "Prijavite se da biste videli kancelariju."); return; }
      ucitaj();
    }
    var odjavi = sesija.naPromenu(function (novo, staro) {
      if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) { ocisti(); if (otvoren) pokreni(); }
    });
    ocisti();
    return {
      otvori: function () { otvoren = true; ocisti(); pokreni(); },
      zatvori: function () { otvoren = false; ocisti(); },
      zaustavi: function () { otvoren = false; odjavi(); ocisti(); },
    };
  }

  root.VxPodesavanjaSekcije = root.VxPodesavanjaSekcije || {};
  root.VxPodesavanjaSekcije.kancelarija = napravi;
})(window);
