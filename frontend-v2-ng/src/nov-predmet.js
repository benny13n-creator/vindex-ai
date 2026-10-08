/* Vindex V2 NG — Nov predmet (NS005, CAP-004).
 *
 * Ugovor: POST /api/predmeti  {naziv (obavezan), tip, opis} → {predmet: {id, …}}.
 * Backend NE prima stranke, broj ni vrednost pri otvaranju; one se dopunjuju
 * izmenom predmeta. Vlasnika određuje server iz tokena — telo ga ne nosi.
 * Isti naziv u 5 s backend odbija sa 409 (zaštita od duplog slanja).
 *
 * Ishodi se NE ulepšavaju:
 *  • 2xx sa id-em      → otvara se taj predmet;
 *  • 2xx bez id-a      → predmet JE otvoren, ali ga ne možemo otvoriti: uputi na listu;
 *  • 4xx               → nije otvoren (server je odbio), polja ostaju;
 *  • 5xx/mreža/prekid  → ISHOD NEPOZNAT: predmet je možda otvoren; prvo proveriti listu.
 * Dok zahtev traje, slanje je zaključano (nema duplog slanja). Promena sesije
 * briše formu i odbacuje kasni odgovor.
 */
(function (root) {
  "use strict";

  var VRSTE = ["Parnica", "Radni spor", "Ugovorni spor", "Naknada štete", "Potrošački spor", "Nasledstvo",
               "Krivični", "Upravni", "Prekršajni", "Izvršni", "Privredni", "Porodični", "Opšti", "Ostalo"];
  /* Isti ključevi koje baza već nosi (v2/features/predmeti/nov.js); nepoznato ide kako je uneto. */
  var KLJUC = { "parnica": "Parnica", "radni spor": "radni_spor", "ugovorni spor": "ugovorni_spor", "naknada štete": "naknada_stete",
                "potrošački spor": "potrosacki_spor", "nasledstvo": "nasledstvo", "krivični": "krivicni", "upravni": "upravni",
                "prekršajni": "prekrsajni", "izvršni": "izvrsni", "privredni": "privredni", "porodični": "porodicni",
                "opšti": "opsti", "ostalo": "ostalo" };
  var NAJVISE = { naziv: 300, tip: 60, opis: 4000 };
  var ISPRAVAN_ID = /^[A-Za-z0-9_-]{1,64}$/;

  function tipZaSlanje(v) {
    var t = String(v || "").trim();
    if (!t) return null;
    var k = KLJUC[t.toLowerCase()];
    return k || t;
  }

  function napravi(o) {
    var $ = function (id) { return root.document.getElementById(id); };
    var sesija = o.sesija, api = o.api, naUspeh = o.naUspeh;
    var forma = $("nov-forma"), poruka = $("nov-poruka"), dugme = $("nov-posalji");
    var generacija = 0, kontroler = null, salje = false;

    var lista = $("nov-vrste");
    if (lista && !lista.children.length) VRSTE.forEach(function (v) { var op = root.document.createElement("option"); op.value = v; lista.append(op); });

    function postaviPoruku(stanje, tekst) {
      if (!stanje) { poruka.hidden = true; poruka.textContent = ""; delete poruka.dataset.stanje; return; }
      poruka.hidden = false; poruka.dataset.stanje = stanje; poruka.textContent = tekst;
    }
    function zakljucaj(da) {
      salje = da;
      dugme.disabled = da;
      dugme.textContent = da ? "Otvaranje…" : "Otvori predmet";
      forma.setAttribute("aria-busy", da ? "true" : "false");
    }
    function ocisti() {
      generacija++;
      if (kontroler) { kontroler.abort(); kontroler = null; }
      forma.reset();
      zakljucaj(false);
      postaviPoruku(null);
      $("nov-naziv").removeAttribute("aria-invalid");
    }

    async function posalji() {
      if (salje) return;
      var naziv = $("nov-naziv").value.trim();
      if (!naziv) {
        $("nov-naziv").setAttribute("aria-invalid", "true");
        postaviPoruku("greska", "Naziv predmeta je obavezan.");
        $("nov-naziv").focus();
        return;
      }
      $("nov-naziv").removeAttribute("aria-invalid");
      var telo = { naziv: naziv.slice(0, NAJVISE.naziv) };
      var tip = tipZaSlanje($("nov-tip").value);
      if (tip) telo.tip = tip.slice(0, NAJVISE.tip);
      var opis = $("nov-opis").value.trim();
      if (opis) telo.opis = opis.slice(0, NAJVISE.opis);

      var s = sesija.stanje();
      if (s.stanje !== sesija.STANJA.PRIJAVLJEN) { postaviPoruku("greska", "Niste prijavljeni. Predmet nije otvoren."); return; }
      var moja = ++generacija, korisnik = s.korisnik;
      kontroler = new AbortController();
      zakljucaj(true);
      postaviPoruku("ucitavanje", "Predmet se otvara…");
      var r = await api.send("/api/predmeti", { telo: telo, token: sesija.token(), signal: kontroler.signal,
        oblik: function (d) { return d.predmet && typeof d.predmet === "object" && ISPRAVAN_ID.test(String(d.predmet.id || "")); } });
      if (moja !== generacija) return;                    // sesija/forma se promenila: odgovor se baca
      sesija.proveri();
      if (moja !== generacija || sesija.stanje().korisnik !== korisnik) return;
      kontroler = null;
      if (r.ok && r.podaci) { zakljucaj(false); forma.reset(); postaviPoruku(null); naUspeh(String(r.podaci.predmet.id)); return; }
      zakljucaj(false);
      if (r.ok) { postaviPoruku("nepoznato", "Predmet je otvoren, ali odgovor servera nije mogao da se pročita. Pronađite ga u listi predmeta; ne šaljite ponovo."); return; }
      var g = r.greska || {};
      if (g.ishodNepoznat) {
        postaviPoruku("nepoznato", "Ishod nije poznat: veza je prekinuta ili server nije odgovorio ispravno, pa je predmet možda otvoren. Proverite listu predmeta pre nego što pokušate ponovo.");
        return;
      }
      var t = {
        AUTH_REQUIRED: "Prijava više nije važeća. Predmet nije otvoren; prijavite se ponovo.",
        FORBIDDEN: "Server nije dozvolio otvaranje predmeta za ovaj nalog.",
        CONFLICT: "Predmet sa ovim nazivom je upravo otvoren. Proverite listu predmeta; ako ovo nije duplikat, sačekajte nekoliko sekundi.",
        BAD_REQUEST: "Server nije prihvatio podatke. Predmet nije otvoren; proverite naziv.",
        VALIDATION_ERROR: "Server nije prihvatio podatke. Predmet nije otvoren; proverite unos.",
        RATE_LIMITED: "Previše zahteva. Predmet nije otvoren; pokušajte ponovo malo kasnije.",
        CONFIG_ERROR: "Zahtev nije poslat. Predmet nije otvoren.",
      }[g.kod] || "Server je odbio zahtev. Predmet nije otvoren.";
      postaviPoruku("greska", t);
    }

    forma.addEventListener("submit", function (e) { e.preventDefault(); posalji(); });
    var odjavi = sesija.naPromenu(function (novo, staro) {
      if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) ocisti();
    });

    return {
      otvori: function () { ocisti(); setTimeout(function () { $("nov-naziv").focus(); }, 0); },
      zatvori: ocisti,
      zaustavi: function () { odjavi(); ocisti(); },
    };
  }

  root.VxNovPredmet = Object.freeze({ napravi: napravi, tipZaSlanje: tipZaSlanje });
})(window);
