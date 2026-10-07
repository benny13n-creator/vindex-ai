/* Vindex V2 NG — DEMONSTRACIONI podaci.
 *
 * Sve ispod je izmišljeno: nazivi predmeta, klijenti, brojevi predmeta i
 * obaveze. Nazivi sudova su stvarne institucije, ali nijedan zapis nije
 * stvaran predmet. Obaveze u panelu nisu izračunati pravni rokovi niti AI
 * nalazi — to su primeri koji pokazuju raspored.
 *
 * Scenario se bira URL parametrima (vidi README):
 *   ?predmeti=standard|prazno|veliko   ?paznja=standard|prazno
 */
(function () {
  "use strict";

  /* Fiksan referentni datum: snimci i testovi moraju biti ponovljivi. */
  var DEMO_DANAS = "2026-10-05";

  var STANDARD = [
    { naziv: "Naknada štete zbog povrede na radu", klijent: "M. Petrović", vrsta: "Radni spor", broj: "P1 412/2026", sud: "Osnovni sud u Novom Sadu", stanje: "aktivan", izmenjeno: "2026-10-02" },
    { naziv: "Raskid ugovora o zakupu poslovnog prostora", klijent: "Lumen Trade d.o.o.", vrsta: "Privredni spor", broj: "P 512/2026", sud: "Privredni sud u Beogradu", stanje: "aktivan", izmenjeno: "2026-10-01" },
    { naziv: "Poništaj rešenja o utvrđivanju poreza na imovinu", klijent: "D. Jovanović", vrsta: "Upravni spor", broj: "U 8823/2025", sud: "Upravni sud", stanje: "cekanje", izmenjeno: "2026-09-30" },
    { naziv: "Naknada nematerijalne štete zbog povrede prava ličnosti i duševnih bolova usled objavljivanja netačnih informacija u elektronskom mediju i na društvenim mrežama", klijent: "S. Nikolić", vrsta: "Naknada štete", broj: "P 3107/2025", sud: "Viši sud u Beogradu", stanje: "aktivan", izmenjeno: "2026-09-29" },
    { naziv: "Izvršenje na osnovu verodostojne isprave", klijent: "Agro Banat Promet d.o.o.", vrsta: "Izvršni", broj: "Iiv 2210/2026", sud: "Osnovni sud u Zrenjaninu", stanje: "aktivan", izmenjeno: "2026-09-26" },
    { naziv: "Utvrđenje prava svojine na stanu", klijent: "Lj. Đorđević i Č. Đorđević", vrsta: "Parnica", broj: "P 1423/2025", sud: "Osnovni sud u Novom Sadu", stanje: "aktivan", izmenjeno: "2026-09-25" },
    { naziv: "Ostavinski postupak iza pok. R. Stojanovića", klijent: "N. Stojanović", vrsta: "Nasledstvo", broj: "O 977/2026", sud: "Osnovni sud u Nišu", stanje: "cekanje", izmenjeno: "2026-09-22" },
    { naziv: "Odbrana u postupku zbog prekršaja iz oblasti bezbednosti saobraćaja", klijent: "V. Ilić", vrsta: "Prekršajni", broj: "PR 6608/2026", sud: "Prekršajni sud u Kragujevcu", stanje: "aktivan", izmenjeno: "2026-09-19" },
    { naziv: "Naplata potraživanja po osnovu ugovora o isporuci robe", klijent: "Severna Industrija Metalnih Konstrukcija i Opreme a.d. Subotica", vrsta: "Privredni spor", broj: "P 1188/2026", sud: "Privredni sud u Subotici", stanje: "aktivan", izmenjeno: "2026-09-17" },
    { naziv: "Razvod braka i vršenje roditeljskog prava", klijent: "J. Marković", vrsta: "Porodični", broj: "P2 245/2026", sud: "Osnovni sud u Kraljevu", stanje: "aktivan", izmenjeno: "2026-09-15" },
    { naziv: "Zaštita potrošača — reklamacija na neispravan uređaj", klijent: "T. Pavlović", vrsta: "Potrošački spor", broj: "P 4419/2026", sud: "Osnovni sud u Čačku", stanje: "cekanje", izmenjeno: "2026-09-11" },
    { naziv: "Poništaj odluke o otkazu ugovora o radu", klijent: "Ž. Šećerović", vrsta: "Radni spor", broj: "P1 98/2026", sud: "Osnovni sud u Šapcu", stanje: "aktivan", izmenjeno: "2026-09-08" },
  ];

  var PAZNJA = [
    { vrsta: "Ročište", naslov: "Glavna rasprava", broj: "P 1423/2025", predmet: "Utvrđenje prava svojine na stanu", kada: "2026-10-06", vreme: "10:30" },
    { vrsta: "Interni rok", naslov: "Nacrt odgovora na tužbu — pregled pre slanja", broj: "P 512/2026", predmet: "Raskid ugovora o zakupu poslovnog prostora", kada: "2026-10-07" },
    { vrsta: "Novi dokument", naslov: "Dopis suda nije pregledan", broj: "U 8823/2025", predmet: "Poništaj rešenja o utvrđivanju poreza na imovinu", kada: "2026-10-02", primljen: true },
    { vrsta: "Klijent", naslov: "Potvrditi punomoćje sa klijentom", broj: "O 977/2026", predmet: "Ostavinski postupak iza pok. R. Stojanovića", kada: "2026-10-09" },
    { vrsta: "Interni rok", naslov: "Pripremiti spisak dokaza", broj: "P1 412/2026", predmet: "Naknada štete zbog povrede na radu", kada: "2026-10-12" },
  ];

  /* Veliki skup: determinističan generator (isto seme → isti predmeti). */
  function veliki(n) {
    var seme = 20261005;
    function rnd() { seme = (seme * 1103515245 + 12345) % 2147483648; return seme / 2147483648; }
    function izaberi(a) { return a[Math.floor(rnd() * a.length)]; }
    var teme = ["Naknada štete", "Raskid ugovora", "Utvrđenje prava svojine", "Naplata potraživanja", "Poništaj rešenja", "Smetanje državine", "Deoba zajedničke imovine", "Izdržavanje deteta", "Poništaj otkaza", "Zaštita od diskriminacije", "Iseljenje iz stana", "Ništavost ugovora"];
    var osnovi = ["po ugovoru o delu", "iz saobraćajne nezgode", "po osnovu zakupa", "iz radnog odnosa", "na nepokretnosti u katastarskoj parceli", "po osnovu kredita", "zbog neizvršenja obaveze", ""];
    var klijenti = ["M. Petrović", "A. Kovačević", "Lumen Trade d.o.o.", "D. Jovanović", "Z. Popović", "Ćirić Gradnja d.o.o.", "B. Lukić", "S. Nikolić", "Agro Banat Promet d.o.o.", "I. Đurić", "N. Stojanović", "Žitopromet a.d."];
    var vrste = [["Parnica", "P"], ["Radni spor", "P1"], ["Privredni spor", "P"], ["Upravni spor", "U"], ["Izvršni", "Iiv"], ["Porodični", "P2"]];
    var sudovi = ["Osnovni sud u Novom Sadu", "Prvi osnovni sud u Beogradu", "Privredni sud u Beogradu", "Upravni sud", "Osnovni sud u Nišu", "Viši sud u Kragujevcu", "Osnovni sud u Subotici"];
    var out = [];
    for (var i = 0; i < n; i++) {
      var v = izaberi(vrste);
      var osnov = izaberi(osnovi);
      var dan = new Date(Date.UTC(2026, 9, 4) - Math.floor(rnd() * 300) * 86400000);
      out.push({
        naziv: izaberi(teme) + (osnov ? " " + osnov : ""),
        klijent: izaberi(klijenti),
        vrsta: v[0],
        broj: v[1] + " " + (100 + Math.floor(rnd() * 9800)) + "/" + (rnd() < 0.6 ? "2026" : "2025"),
        sud: v[0] === "Upravni spor" ? "Upravni sud" : izaberi(sudovi),
        stanje: rnd() < 0.78 ? "aktivan" : "cekanje",
        izmenjeno: dan.toISOString().slice(0, 10),
      });
    }
    return out;
  }

  /* Demo podaci postoje SAMO u DEMO režimu (src/runtime.js). U LIVE režimu i
   * kod neispravne konfiguracije `VX_DEMO` se ne definiše uopšte, pa ga ništa
   * ne može ni slučajno prikazati. Bez runtime.js režim nije dokazan → ništa. */
  if (!window.VxRuntime || window.VxRuntime.rezim !== window.VxRuntime.DEMO) return;

  var q = new URLSearchParams(window.location.search);
  var scenarioPredmeti = q.get("predmeti") || "standard";
  var scenarioPaznja = q.get("paznja") || "standard";

  var predmeti = scenarioPredmeti === "prazno" ? [] : scenarioPredmeti === "veliko" ? STANDARD.concat(veliki(228)) : STANDARD;
  window.VX_DEMO = {
    danas: DEMO_DANAS,
    predmeti: predmeti.map(function (p, i) { p.id = "demo-" + (i + 1); return p; }),
    paznja: scenarioPaznja === "prazno" ? [] : PAZNJA,
  };
})();
