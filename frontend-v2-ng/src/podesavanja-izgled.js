/* Vindex V2 NG — Podešavanja › Izgled i rad (Settings Master Sprint P2.1).
 * Tema: ISTA postavka kao prekidač u gornjoj traci (window.VxTema iz app.js, ključ `vx-ng-tema` na uređaju).
 * Izbor ovde i prekidač gore uvek prikazuju isto stanje (oba slušaju događaj „vx-tema“). Paleta se ne menja.
 * Druge radne preferencije se NE nude: V2 ih nema kao potvrđen ugovor (vidi SETTINGS_MASTER_SPRINT_STATE.md, P2.4).
 */
(function (root) {
  "use strict";

  function napravi() {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    function uskladi() {
      var t = root.VxTema ? root.VxTema.trenutna() : (d.documentElement.dataset.theme === "light" ? "light" : "dark");
      $("pn-tema-dark").checked = t === "dark";
      $("pn-tema-light").checked = t === "light";
    }
    ["pn-tema-dark", "pn-tema-light"].forEach(function (id) {
      $(id).addEventListener("change", function () { if ($(id).checked && root.VxTema) root.VxTema.postavi($(id).value); });
    });
    d.addEventListener("vx-tema", uskladi);
    uskladi();
    return { otvori: uskladi, zatvori: function () {}, zaustavi: function () { d.removeEventListener("vx-tema", uskladi); } };
  }

  root.VxPodesavanjaSekcije = root.VxPodesavanjaSekcije || {};
  root.VxPodesavanjaSekcije.izgled = napravi;
})(window);
