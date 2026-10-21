/* Vindex V2 — autentifikovana prijava nepravilnosti. Bez eksternih skripti. */
(function (root) {
  "use strict";
  function start() {
    var panel = document.getElementById("vx-feedback-panel");
    var toggle = document.getElementById("vx-feedback-toggle");
    var form = document.getElementById("vx-feedback-form");
    var close = document.getElementById("vx-feedback-close");
    var outcome = document.getElementById("vx-feedback-outcome");
    if (!panel || !toggle || !form || !close || !outcome) return;
    var poruka = form.elements.poruka;
    var category = form.elements.kategorija;
    var submit = form.querySelector('[type="submit"]');
    function open() {
      panel.hidden = false;
      toggle.setAttribute("aria-expanded", "true");
      category.focus();
    }
    function hide() {
      panel.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
      toggle.focus();
    }
    toggle.addEventListener("click", function () { panel.hidden ? open() : hide(); });
    close.addEventListener("click", hide);
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !panel.hidden) hide();
    });
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      var opis = poruka.value.trim();
      outcome.hidden = false;
      if (opis.length < 10 || opis.length > 3000) {
        outcome.textContent = "Unesite opis između 10 i 3000 znakova.";
        poruka.focus();
        return;
      }
      var sesija = root.VxSesija;
      var api = root.VxApi;
      var token = sesija && sesija.token();
      if (!token || !api || typeof api.send !== "function") {
        outcome.textContent = "Za slanje prijave potrebno je da budete prijavljeni.";
        return;
      }
      submit.disabled = true;
      outcome.textContent = "Slanje prijave…";
      try {
        var result = await api.send("/api/support/poruka", {
          token: token,
          telo: { kategorija: category.value, poruka: opis, kontekst: "V2: " + root.location.pathname.slice(0, 70) },
          oblik: function (o) { return o && o.ok === true; }
        });
        if (result && result.ok && result.podaci && result.podaci.ok === true) {
          outcome.textContent = "Prijava je predata sistemu za e-poštu. Hvala na povratnoj informaciji.";
          form.reset();
        } else {
          outcome.textContent = (result && result.ishodNepoznat)
            ? "Nije moguće potvrditi prijem. Nemojte slati više puta bez provere; možete pisati na benny13.n@gmail.com."
            : "Prijava nije potvrđena. Pokušajte ponovo ili pišite na benny13.n@gmail.com.";
        }
      } catch (error) {
        outcome.textContent = "Ishod prijave nije poznat. Kontakt: benny13.n@gmail.com.";
      } finally {
        submit.disabled = false;
      }
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})(window);
