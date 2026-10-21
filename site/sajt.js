/* Vindex — javni sajt: filter kataloga i prijava za beta testiranje.
 * Bez spoljnih biblioteka i bez praćenja. Sajt radi i bez ovog skripta; skript
 * samo dodaje filter i šalje formu. */
(function () {
  "use strict";

  /* ── Katalog: filter po statusu i tekstu ─────────────────────────── */
  var katalog = document.getElementById("katalog-stavke");
  if (katalog) {
    var upit = document.getElementById("filter-tekst");
    var status = document.getElementById("filter-status");
    var rezultat = document.getElementById("filter-rezultat");
    var stavke = Array.prototype.slice.call(katalog.querySelectorAll(".stavka"));
    var oblasti = Array.prototype.slice.call(katalog.querySelectorAll(".oblast"));
    var normalizuj = function (s) {
      return String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "dj");
    };
    var primeni = function () {
      var q = normalizuj(upit.value.trim());
      var st = status.value;
      var vidljivih = 0;
      stavke.forEach(function (s) {
        var ok = (!st || s.getAttribute("data-status") === st) && (!q || normalizuj(s.textContent).indexOf(q) !== -1);
        s.hidden = !ok;
        if (ok) vidljivih++;
      });
      oblasti.forEach(function (o) { o.hidden = !o.querySelector(".stavka:not([hidden])"); });
      rezultat.textContent = vidljivih === stavke.length
        ? "Prikazane su sve stavke (" + stavke.length + ")."
        : "Prikazano " + vidljivih + " od " + stavke.length + " stavki.";
    };
    document.getElementById("filter").hidden = false;
    upit.addEventListener("input", primeni);
    status.addEventListener("change", primeni);
  }

  /* ── Prijava za beta testiranje ──────────────────────────────────── */
  var forma = document.getElementById("beta-forma");
  if (!forma) return;
  var ishod = document.getElementById("beta-ishod");
  var dugme = document.getElementById("beta-posalji");
  var polja = { ime: forma.elements.ime, email: forma.elements.email };

  function greskaPolja(ime, tekst) {
    var el = polja[ime], p = document.getElementById("greska-" + ime);
    el.setAttribute("aria-invalid", tekst ? "true" : "false");
    p.textContent = tekst || "";
    p.hidden = !tekst;
  }
  function prikaziIshod(vrsta, tekst) {
    ishod.className = "ishod ishod--" + vrsta;
    ishod.setAttribute("role", vrsta === "greska" ? "alert" : "status");
    ishod.innerHTML = "";
    tekst.forEach(function (t) { var p = document.createElement("p"); p.textContent = t; ishod.appendChild(p); });
    ishod.hidden = false;
    ishod.focus();
  }

  forma.addEventListener("submit", function (e) {
    e.preventDefault();
    var ime = polja.ime.value.trim(), email = polja.email.value.trim();
    greskaPolja("ime", ime ? "" : "Unesite ime i prezime.");
    greskaPolja("email", /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ? "" : "Unesite ispravnu adresu e-pošte.");
    var prva = !ime ? polja.ime : (polja.email.getAttribute("aria-invalid") === "true" ? polja.email : null);
    if (prva) { prva.focus(); return; }

    dugme.disabled = true;
    dugme.textContent = "Slanje…";
    ishod.hidden = true;
    fetch("/waitlist/prijava", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ime: ime, email: email,
        firma: forma.elements.firma.value.trim(),
        telefon: forma.elements.telefon.value.trim(),
        poruka: forma.elements.poruka.value.trim()
      })
    }).then(function (r) {
      return r.json().then(function (telo) { return { status: r.status, telo: telo }; }, function () { return { status: r.status, telo: null }; });
    }).then(function (o) {
      if (o.status === 200 && o.telo && o.telo.ok === true) {
        forma.querySelectorAll("input, textarea").forEach(function (el) { el.disabled = true; });
        dugme.hidden = true;
        prikaziIshod("uspeh", [
          "Prijava je evidentirana za adresu " + email + ".",
          "Prijave pojedinačno pregleda tim Vindexa. Ova prijava ne otvara nalog, a potvrda se ne šalje e-poštom."
        ]);
        return;
      }
      if (o.status === 422) {
        var detalj = (o.telo && o.telo.detail) || [];
        var poEmailu = Array.isArray(detalj) && detalj.some(function (d) { return (d.loc || []).indexOf("email") !== -1; });
        if (poEmailu) greskaPolja("email", "Server nije prihvatio ovu adresu e-pošte.");
        prikaziIshod("greska", ["Prijava nije sačuvana: proverite unete podatke i pošaljite ponovo."]);
      } else {
        prikaziIshod("greska", [
          "Server nije potvrdio prijavu (" + o.status + "). Pokušajte ponovo kasnije.",
          "Ista adresa se ne upisuje dva puta, pa je ponovno slanje bezbedno."
        ]);
      }
      dugme.disabled = false;
      dugme.textContent = "Pošaljite prijavu";
    }, function () {
      prikaziIshod("greska", [
        "Veza sa serverom je prekinuta, pa nije poznato da li je prijava sačuvana.",
        "Možete je bezbedno poslati ponovo: ista adresa se ne upisuje dva puta."
      ]);
      dugme.disabled = false;
      dugme.textContent = "Pošaljite prijavu";
    });
  });
})();
