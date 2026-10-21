/* Vindex V2 — prijava problema bez automatskog prilaganja poverljivih podataka. */
(function () {
  "use strict";
  var toggle = document.getElementById("vx-prijava-toggle");
  var panel = document.getElementById("vx-prijava-panel");
  var close = document.getElementById("vx-prijava-zatvori");
  var form = document.getElementById("vx-prijava-forma");
  var result = document.getElementById("vx-prijava-ishod");
  var send = document.getElementById("vx-prijava-salji");
  var mail = document.getElementById("vx-prijava-mejl");
  if (!toggle || !panel || !form || !mail) return;
  function opened(flag) {
    panel.hidden = !flag;
    toggle.setAttribute("aria-expanded", flag ? "true" : "false");
    if (flag) form.elements.kategorija.focus();
    else toggle.focus();
  }
  toggle.addEventListener("click", function () { opened(panel.hidden); });
  close.addEventListener("click", function () { opened(false); });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !panel.hidden) opened(false);
  });
  function show(message, bad) {
    result.hidden = false;
    result.textContent = message;
    result.style.borderLeftColor = bad ? "#e09a8f" : "#8bb9ef";
  }
  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (!form.reportValidity() || send.disabled) return;
    var category = form.elements.kategorija.value;
    var message = form.elements.poruka.value.trim();
    if (message.length < 10 || message.length > 3000) return;
    var title = "Vindex AI - " + (form.elements.kategorija.selectedOptions[0] || {}).textContent;
    mail.href = "mailto:benny13.n@gmail.com?subject=" + encodeURIComponent(title) +
      "&body=" + encodeURIComponent(message);
    var session = window.VxSesija;
    var token = session && session.token && session.token();
    if (!token) {
      show("Za slanje iz aplikacije potrebna je prijava. Možete koristiti direktnu e-poštu ispod.", true);
      return;
    }
    send.disabled = true;
    result.hidden = true;
    try {
      var response = await fetch("/api/support/poruka", {
        method: "POST",
        credentials: "omit",
        headers: { "Content-Type": "application/json", "Accept": "application/json",
                   "Authorization": "Bearer " + token },
        body: JSON.stringify({ kategorija: category, poruka: message, kontekst: location.pathname }),
      });
      var body = await response.json().catch(function () { return null; });
      if (response.ok && body && body.ok === true) {
        if (body.email_poslat === true) {
          show("Prijava je poslata osnivaču. Hvala što pomažete da Vindex bude bolji.", false);
        } else if (body.evidentirano === true) {
          show("Prijava je evidentirana, ali dostava e-pošte nije potvrđena. Za hitne probleme pošaljite poruku direktno na kontakt ispod.", true);
        } else {
          show("Prijem prijave nije potvrđen. Pošaljite je direktno e-poštom.", true);
        }
        form.reset();
      } else {
        show("Prijava nije potvrđena (" + response.status + "). Tekst je sačuvan u polju; možete poslati direktno e-poštom.", true);
      }
    } catch (_) {
      show("Veza je prekinuta; nije poznato da li je prijava primljena. Proverite pre ponovnog slanja ili koristite direktnu e-poštu.", true);
    } finally {
      send.disabled = false;
    }
  });
})();