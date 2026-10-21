/* Vindex V2 NG — prijava problema ili predloga (Website V3).
 *
 * Stalno dugme u donjem desnom uglu radnog prostora otvara mali dijalog:
 * kategorija + opis → POST /api/support/poruka (postojeća ruta, routers/support.py).
 *
 * PRAVILA
 *  • Prikazuje se samo prijavljenom korisniku (LIVE); o identitetu odlučuje server iz tokena.
 *  • Uz poruku ide SAMO naziv ekrana (npr. „Predmet“), nikad ID predmeta, tekst predmeta,
 *    dokument, AI odgovor ni snimak ekrana. Korisniku piše šta se šalje.
 *  • Uspeh se prikazuje samo kada server potvrdi `ok: true`; tada piše da li je prijava
 *    sačuvana (broj) ili samo prosleđena. Prekinuta veza = ishod nepoznat, tekst ostaje.
 *  • Ponovljen mrežni zahtev istog klika nosi isti `Idempotency-Key` (VxApi.send), a ruta
 *    je u shared/idempotency.py — jedan klik je jedna prijava.
 */
(function (root) {
  "use strict";

  var KATEGORIJE = [
    ["tehnicko", "Tehnički problem"],
    ["ai", "Netačan AI odgovor"],
    ["podatak", "Problem sa podacima ili dokumentom"],
    ["predlog", "Predlog"],
    ["ostalo", "Nešto drugo"],
  ];
  var MIN = 10, MAX = 3000;

  /* Naziv ekrana iz adrese, bez identifikatora (#/predmet/<id>/... → „Predmet“). */
  function nazivEkrana(hash) {
    var deo = String(hash || "").replace(/^#\/?/, "").split(/[/?]/)[0];
    return { danas: "Danas", znanje: "Znanje", kancelarija: "Kancelarija", pretraga: "Pretraga",
             predmet: "Predmet", "nov-predmet": "Nov predmet" }[deo] || "Predmeti";
  }

  function el(oznaka, svojstva, deca) {
    var e = root.document.createElement(oznaka);
    Object.keys(svojstva || {}).forEach(function (k) {
      if (k === "tekst") e.textContent = svojstva[k];
      else e.setAttribute(k, svojstva[k]);
    });
    (deca || []).forEach(function (d) { e.appendChild(d); });
    return e;
  }

  /**
   * @param {{sesija, api, hash?: function():string}} o
   */
  function napravi(o) {
    var doc = root.document;
    var sesija = o.sesija, api = o.api;
    var hash = o.hash || function () { return root.location.hash; };

    var dugme = el("button", { type: "button", class: "prijava-dugme", id: "prijava-dugme",
      "aria-haspopup": "dialog", "aria-controls": "prijava-dijalog",
      "aria-label": "Prijavi problem ili pošalji predlog", title: "Prijavi problem ili pošalji predlog" });
    dugme.innerHTML = '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3.5 4.5h13v8.5h-7l-3.5 3v-3h-2.5z"/><path d="M7 8h6M7 10.5h4"/></svg>';

    var izbor = el("select", { id: "prijava-kategorija", name: "kategorija" },
      KATEGORIJE.map(function (k) { return el("option", { value: k[0], tekst: k[1] }); }));
    var opis = el("textarea", { id: "prijava-opis", name: "poruka", rows: "6", maxlength: String(MAX),
      "aria-describedby": "prijava-opis-pomoc prijava-greska", required: "" });
    var pomoc = el("p", { class: "prijava__pomoc", id: "prijava-opis-pomoc",
      tekst: "Opišite šta ste radili, šta ste očekivali i šta se desilo. Najmanje " + MIN + " znakova." });
    var greska = el("p", { class: "prijava__greska", id: "prijava-greska", hidden: "" });
    var ekran = el("strong", { id: "prijava-ekran" });
    var napomena = el("p", { class: "prijava__napomena" }, [
      doc.createTextNode("Poruka se šalje podršci Vindexa zajedno sa adresom vašeg naloga i nazivom ekrana ("),
      ekran,
      doc.createTextNode("). Sadržaj predmeta, dokumenti, AI odgovori i snimak ekrana se ne prilažu. Ne unosite podatke klijenata osim ako su neophodni za opis problema."),
    ]);
    var ishod = el("div", { class: "prijava__ishod", id: "prijava-ishod", tabindex: "-1", hidden: "" });
    var posalji = el("button", { type: "submit", class: "text-btn text-btn--primary", id: "prijava-posalji", tekst: "Pošalji" });
    var zatvori = el("button", { type: "button", class: "text-btn text-btn--line", id: "prijava-zatvori", tekst: "Zatvori" });

    var forma = el("form", { class: "prijava__forma", novalidate: "" }, [
      el("h2", { id: "prijava-naslov", tekst: "Prijavi problem ili pošalji predlog" }),
      napomena,
      el("div", { class: "prijava__polje" }, [el("label", { for: "prijava-kategorija", tekst: "Vrsta" }), izbor]),
      el("div", { class: "prijava__polje" }, [el("label", { for: "prijava-opis", tekst: "Opis" }), opis, pomoc, greska]),
      ishod,
      el("div", { class: "prijava__dno" }, [posalji, zatvori]),
    ]);
    var dijalog = el("dialog", { class: "prijava", id: "prijava-dijalog", "aria-labelledby": "prijava-naslov" }, [forma]);

    doc.body.appendChild(dugme);
    doc.body.appendChild(dijalog);

    var salje = false;

    function postaviGresku(t) {
      greska.textContent = t || "";
      greska.hidden = !t;
      opis.setAttribute("aria-invalid", t ? "true" : "false");
    }
    function prikaziIshod(vrsta, t) {
      ishod.className = "prijava__ishod prijava__ishod--" + vrsta;
      ishod.setAttribute("role", vrsta === "greska" ? "alert" : "status");
      ishod.textContent = t;
      ishod.hidden = false;
    }

    function otvori() {
      ekran.textContent = nazivEkrana(hash());
      postaviGresku("");
      if (!salje) ishod.hidden = true;
      if (typeof dijalog.showModal === "function") dijalog.showModal(); else dijalog.setAttribute("open", "");
      izbor.focus();
    }
    function zatvoriDijalog() {
      if (typeof dijalog.close === "function" && dijalog.open) dijalog.close(); else dijalog.removeAttribute("open");
    }
    dijalog.addEventListener("close", function () { dugme.focus(); });
    dugme.addEventListener("click", otvori);
    zatvori.addEventListener("click", zatvoriDijalog);
    /* Klik na pozadinu (van forme) zatvara, kao ESC. */
    dijalog.addEventListener("click", function (e) { if (e.target === dijalog) zatvoriDijalog(); });

    forma.addEventListener("submit", async function (e) {
      e.preventDefault();
      if (salje) return;
      var tekst = opis.value.trim();
      if (tekst.length < MIN) { postaviGresku("Opis mora imati najmanje " + MIN + " znakova."); opis.focus(); return; }
      postaviGresku("");
      var token = sesija.token();
      if (!token) { prikaziIshod("greska", "Niste prijavljeni. Prijavite se ponovo, pa pošaljite poruku."); return; }

      salje = true;
      posalji.disabled = true;
      posalji.textContent = "Slanje…";
      ishod.hidden = true;
      var r = await api.send("/api/support/poruka", {
        telo: { kategorija: izbor.value, poruka: tekst, kontekst: nazivEkrana(hash()) },
        token: token,
        oblik: function (x) { return !!x && x.ok === true; },
      });
      salje = false;
      posalji.disabled = false;
      posalji.textContent = "Pošalji";

      if (r.ok && r.podaci) {
        opis.value = "";
        izbor.value = KATEGORIJE[0][0];
        prikaziIshod("uspeh", r.podaci.sacuvano && r.podaci.broj
          ? "Prijava je primljena i sačuvana pod brojem " + String(r.podaci.broj).slice(0, 8) + "."
          : "Prijava je primljena i prosleđena podršci.");
        zatvori.focus();
        return;
      }
      var g = (r.greska || {});
      var poruka;
      if (r.ok) poruka = "Server nije potvrdio prijem prijave. Tekst je ostao u polju; možete pokušati ponovo.";
      else if (g.kod === "AUTH_REQUIRED") poruka = "Sesija je istekla. Prijavite se ponovo, pa pošaljite poruku.";
      else if (g.kod === "RATE_LIMITED") poruka = "Poslali ste više prijava u kratkom roku. Pokušajte ponovo kasnije.";
      else if (r.status === 422) poruka = "Server nije prihvatio opis. Proverite dužinu teksta (" + MIN + " do " + MAX + " znakova).";
      else poruka = "Nije potvrđeno da je prijava primljena. Tekst je ostao u polju. Ako pošaljete ponovo, a prva je ipak stigla, podrška će dobiti dve iste prijave.";
      prikaziIshod("greska", poruka);
      ishod.focus();
    });

    function uskladi() {
      var prijavljen = sesija.stanje().stanje === sesija.STANJA.PRIJAVLJEN;
      dugme.hidden = !prijavljen;
      doc.documentElement.dataset.prijava = prijavljen ? "da" : "";
      if (!prijavljen) zatvoriDijalog();
    }
    sesija.naPromenu(uskladi);
    uskladi();

    return { otvori: otvori, zatvori: zatvoriDijalog, uskladi: uskladi };
  }

  root.VxPrijavaProblema = Object.freeze({ napravi: napravi, nazivEkrana: nazivEkrana, KATEGORIJE: KATEGORIJE });
})(typeof window !== "undefined" ? window : globalThis);
