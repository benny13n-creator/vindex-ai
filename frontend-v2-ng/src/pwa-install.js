/* Instalacija Vindex web-aplikacije iz primarnog V2 prikaza. */
(function () {
  "use strict";

  var dugme = document.getElementById("install-app-btn");
  var dijalog = document.getElementById("install-app-dialog");
  var zatvori = document.getElementById("install-app-close");
  var potvrdi = document.getElementById("install-app-confirm");
  var ponuda = document.getElementById("install-app-native");
  var uputstvo = document.getElementById("install-app-instructions");
  if (!dugme || !dijalog || !zatvori || !potvrdi || !ponuda || !uputstvo) return;

  var odlozeniDogadjaj = null;
  var samostalnaAplikacija = window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone === true;
  if (samostalnaAplikacija) dugme.hidden = true;

  function tekstUputstva() {
    var ua = navigator.userAgent || "";
    var platforma = navigator.platform || "";
    var ios = /iPad|iPhone|iPod/i.test(ua) || (platforma === "MacIntel" && navigator.maxTouchPoints > 1);
    if (ios) return "Na iPhone-u ili iPad-u otvorite stranicu u Safari-ju, dodirnite Podeli (Share), pa „Add to Home Screen“ („Dodaj na početni ekran“).";
    if (/Android/i.test(ua)) return "Na Android uređaju u Chrome-u otvorite meni ⋮ i izaberite „Install app“ ili „Add to Home screen“.";
    if (/Macintosh|Mac OS X/i.test(ua) && /Safari/i.test(ua) && !/Chrome|Chromium|Edg/i.test(ua)) {
      return "Na Mac računaru u Safari-ju otvorite meni Podeli (Share) i izaberite „Add to Dock“, ako je ta opcija dostupna.";
    }
    if (/Chrome|Chromium|Edg\//i.test(ua)) return "Na računaru u Chrome-u ili Edge-u izaberite ikonu instalacije u adresnoj traci ili opciju „Install Vindex“ u meniju pregledača.";
    return "U meniju pregledača potražite „Install app“ ili „Add to Home screen“. Ako opcija nije dostupna, otvorite Vindex u Chrome-u ili Edge-u na računaru, odnosno Safari-ju na iPhone-u ili iPad-u.";
  }

  function otvori() {
    if (samostalnaAplikacija) return;
    uputstvo.textContent = tekstUputstva();
    if (typeof dijalog.showModal === "function") {
      if (!dijalog.open) dijalog.showModal();
    } else {
      dijalog.setAttribute("open", "");
    }
  }

  function zatvoriDijalog() {
    if (typeof dijalog.close === "function" && dijalog.open) dijalog.close();
    else dijalog.removeAttribute("open");
  }

  dugme.addEventListener("click", otvori);
  zatvori.addEventListener("click", zatvoriDijalog);
  dijalog.addEventListener("click", function (dogadjaj) {
    if (dogadjaj.target === dijalog) zatvoriDijalog();
  });

  window.addEventListener("beforeinstallprompt", function (dogadjaj) {
    dogadjaj.preventDefault();
    odlozeniDogadjaj = dogadjaj;
    ponuda.hidden = false;
  });

  potvrdi.addEventListener("click", async function () {
    if (!odlozeniDogadjaj) return;
    var instalacija = odlozeniDogadjaj;
    odlozeniDogadjaj = null;
    ponuda.hidden = true;
    try {
      await instalacija.prompt();
      var izbor = await instalacija.userChoice;
      if (izbor && izbor.outcome === "accepted") zatvoriDijalog();
      else uputstvo.textContent = "Instalacija nije završena. Možete je ponovo pokrenuti iz menija pregledača.";
    } catch (greska) {
      uputstvo.textContent = "Pregledač nije pokrenuo instalaciju. Pokušajte preko opcije za instalaciju u njegovom meniju.";
    }
  });

  window.addEventListener("appinstalled", function () {
    odlozeniDogadjaj = null;
    dugme.hidden = true;
    zatvoriDijalog();
  });

  try {
    var parametri = new URLSearchParams(window.location.search);
    if (parametri.get("instaliraj") === "1") otvori();
  } catch (greska) {}
})();
