/* Vindex V2 NG — pravno pitanje u kontekstu predmeta (NS005, CAP-040).
 *
 * Ugovor: POST /api/pitanje {pitanje (3–2000), predmet_id} → 200
 *   {odgovor, confidence?, confidence_detail?, izvori?, izvori_neuspeh?,
 *    retrieval_unavailable?, cinjenice_iz_dokumenta?, kontekst_predmeta, credits_remaining}
 * Backend: pretraga propisa, citation/halucination guard (izmišljen član → odbijanje
 * bez poziva modela), „nema pouzdanog izvora → model se ne poziva", kontekst predmeta
 * fail-closed (tuđ/obrisan predmet se tiho preskače → `kontekst_predmeta:false`),
 * kredit i refund. Ovde se ništa od toga ne ponavlja i ne zaobilazi.
 *
 * Tumačenje odgovora preuzeto iz v2/domain/znanje.js (B-U-003), bez izmene pravila:
 *   1. `retrieval_unavailable` — pretraga korpusa je PALA (nije „nema propisa");
 *   2. `izvori_neuspeh` neprazan — tačno imenovan izvor NIJE proveren;
 *   3. bez izvora, a ništa nije palo — „nijedan propis nije pronađen"; tekst nije izvor prava.
 * Izvori se prikazuju SAMO iz odgovora servera; ništa se ne izmišlja na klijentu.
 * Sigurnost je reč, ne procenat. Pravnu napomenu backend već dodaje u tekst — ne ponavlja se.
 * Pitanje se nikad ne ponavlja automatski (trošak, istorija); kasni odgovor se baca.
 */
(function (root) {
  "use strict";

  var SIGURNOST = { HIGH: "Jako poklapanje sa propisom", MEDIUM: "Delimično poklapanje sa propisom", LOW: "Slabo poklapanje sa propisom" };
  /* Ikonice iz serverskog teksta se ne prikazuju (vizuelni kanon); sadržaj ostaje. */
  var EMODZI = /[⚖⚠⚡⚔️]|\uD83D[\uDCCA\uDEA8\uDCA1]|🧠|🎯/g;

  function tekst(v) { return String(v == null ? "" : v).trim(); }

  function uIzvor(i) {
    i = i || {};
    var z = tekst(i.zakon || i.law), clan = tekst(i.clan || i.article);
    if (!z) return null;
    var zakon = z.charAt(0).toLocaleUpperCase("sr-RS") + z.slice(1);
    var c = /^(član|clan)\b|^(čl|cl)\./i.test(clan) ? clan : (clan ? "član " + clan : "");
    return c ? zakon + ", " + c : zakon;
  }

  function upozorenja(o) {
    var lista = [];
    if (o.retrieval_unavailable) lista.push(["korpus-pao", "Pretraga zakonskog korpusa nije uspela",
      "Ovaj odgovor NE počiva na pretrazi propisa. To ne znači da propis ne postoji — znači da nije proveren. Ponovite pitanje pre nego što se oslonite na odgovor."]);
    var neuspeh = Array.isArray(o.izvori_neuspeh) ? o.izvori_neuspeh.map(tekst).filter(Boolean) : [];
    if (neuspeh.length) lista.push(["izvor-nije-proveren", neuspeh.length === 1 ? "Jedan izvor nije proveren" : "Deo izvora nije proveren",
      "Nije provereno: " + neuspeh.join(", ") + ". Odsustvo nalaza iz tog izvora nije dokaz da nalaza nema."]);
    if (!izvori(o).length && !o.retrieval_unavailable && !neuspeh.length) lista.push(["bez-pogotka", "Nijedan propis nije pronađen za ovo pitanje",
      "Pretraga je izvršena i nije vratila odredbu na koju bi se odgovor oslonio. Tekst ispod nije izvor prava i ne sme se citirati."]);
    return lista;
  }
  function izvori(o) { return Array.isArray(o.izvori) ? o.izvori.map(uIzvor).filter(Boolean) : []; }

  function odeljci(t) {
    var redovi = String(t || "").replace(/\r\n/g, "\n").split("\n"), out = [], cur = { naslov: "", redovi: [] };
    redovi.forEach(function (r) {
      var m = /^\s*-{2,}\s*(.*?)\s*$/.exec(r);
      if (m) { if (cur.redovi.join("").trim() || cur.naslov) out.push(cur); cur = { naslov: m[1], redovi: [] }; return; }
      cur.redovi.push(r);
    });
    if (cur.redovi.join("").trim() || cur.naslov) out.push(cur);
    return out.map(function (x) { return { naslov: x.naslov.replace(/\*\*/g, "").replace(EMODZI, "").trim(), telo: x.redovi.join("\n").replace(/\*\*/g, "").replace(EMODZI, "").trim() }; })
      .filter(function (x) { return x.telo || x.naslov; });
  }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api;
    var trenutni = null, gen = 0, kontroler = null, salje = false, poslednji = null;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function stanje(st, t) { var n = $("pp-stanje"); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function zakljucaj(da) { salje = da; $("pp-posalji").disabled = da; $("pp-posalji").textContent = da ? "Pretraga propisa…" : "Postavi pitanje"; $("pp-forma").setAttribute("aria-busy", da ? "true" : "false"); }
    function ocistiOdgovor() {
      $("pp-odgovor").hidden = true;
      ["pp-upozorenja", "pp-izvori", "pp-tekst", "pp-cinjenice"].forEach(function (id) { $(id).replaceChildren(); });
      $("pp-izvori-blok").hidden = true; $("pp-cinjenice-blok").hidden = true;
      $("pp-sigurnost").hidden = true; $("pp-sigurnost").textContent = "";
      $("pp-kontekst").hidden = true; $("pp-kontekst").textContent = "";
      $("pp-postavljeno").textContent = "";
    }
    function ocisti() {
      gen++;
      if (kontroler) { kontroler.abort(); kontroler = null; }
      trenutni = null; poslednji = null;
      zakljucaj(false); stanje(null); ocistiOdgovor();
      $("pp-forma").reset();
    }

    function prikazi(pitanje, odg) {
      ocistiOdgovor();
      $("pp-postavljeno").textContent = pitanje;
      upozorenja(odg).forEach(function (u) {
        var li = el("li", "warn"); li.dataset.kljuc = u[0];
        li.append(el("p", "warn__title", u[1]), el("p", "warn__text", u[2]));
        $("pp-upozorenja").append(li);
      });
      if (odg.kontekst_predmeta === false) {
        $("pp-kontekst").hidden = false;
        $("pp-kontekst").textContent = "Podaci ovog predmeta NISU uključeni u odgovor (predmet nije mogao da se pročita). Odgovor je opšti.";
      } else if (odg.kontekst_predmeta === true) {
        $("pp-kontekst").hidden = false;
        $("pp-kontekst").textContent = "Odgovor je dat uz beleške i utvrđene činjenice ovog predmeta.";
      }
      var sig = SIGURNOST[tekst(odg.confidence).toUpperCase()];
      if (sig) { $("pp-sigurnost").hidden = false; $("pp-sigurnost").textContent = sig; }
      var iz = izvori(odg);
      if (iz.length) {
        $("pp-izvori-blok").hidden = false;
        iz.forEach(function (x) { $("pp-izvori").append(el("li", "source", x)); });
      }
      odeljci(odg.odgovor).forEach(function (s) {
        var sec = el("section", "answer__part");
        if (s.naslov) sec.append(el("h3", "answer__h", s.naslov));
        if (s.telo) sec.append(el("p", "answer__text", s.telo));
        $("pp-tekst").append(sec);
      });
      var cin = Array.isArray(odg.cinjenice_iz_dokumenta) ? odg.cinjenice_iz_dokumenta : [];
      cin.map(function (x) { return typeof x === "string" ? tekst(x) : tekst(x && (x.tekst || x.cinjenica || x.text)); }).filter(Boolean).forEach(function (c) {
        $("pp-cinjenice").append(el("li", "source", c));
      });
      $("pp-cinjenice-blok").hidden = !$("pp-cinjenice").children.length;
      $("pp-odgovor").hidden = false;
    }

    async function posalji() {
      if (salje || !trenutni) return;
      var p = $("pp-pitanje").value.trim();
      if (p.length < 3) { $("pp-pitanje").setAttribute("aria-invalid", "true"); stanje("greska", "Pitanje mora imati bar tri znaka."); $("pp-pitanje").focus(); return; }
      if (p.length > 2000) { $("pp-pitanje").setAttribute("aria-invalid", "true"); stanje("greska", "Pitanje može imati najviše 2.000 znakova."); return; }
      $("pp-pitanje").removeAttribute("aria-invalid");
      var s = sesija.stanje();
      if (s.stanje !== sesija.STANJA.PRIJAVLJEN || s.korisnik !== trenutni.korisnik) { stanje("greska", "Niste prijavljeni. Pitanje nije postavljeno."); return; }
      var moja = ++gen, id = trenutni.id, korisnik = trenutni.korisnik;
      kontroler = new AbortController();
      zakljucaj(true);
      stanje("ucitavanje", "Vindex pretražuje propise i proverava izvore…");
      var r = await api.send("/api/pitanje", { telo: { pitanje: p, predmet_id: id }, token: sesija.token(), signal: kontroler.signal,
        oblik: function (x) { return typeof x.odgovor === "string"; } });
      if (moja !== gen || !trenutni || trenutni.id !== id || sesija.stanje().korisnik !== korisnik) return;
      kontroler = null;
      zakljucaj(false);
      if (r.ok && r.podaci) { stanje(null); poslednji = { pitanje: p, odg: r.podaci }; prikazi(p, r.podaci); return; }
      if (r.ok) { stanje("nepoznato", "Odgovor je stigao, ali nije mogao pouzdano da se pročita. Ništa se ne prikazuje."); return; }
      var g = r.greska || {};
      if (g.ishodNepoznat) { stanje("nepoznato", "Odgovor nije dobijen: veza je prekinuta ili server nije odgovorio ispravno. Pitanje je možda obrađeno; pokušajte ponovo za trenutak."); return; }
      stanje("greska", {
        BAD_REQUEST: "Pitanje nije obrađeno: sadržaj nije prihvaćen. Preformulišite pitanje.",
        VALIDATION_ERROR: "Pitanje mora imati između 3 i 2.000 znakova.",
        FORBIDDEN: "Ova funkcija nije dostupna za vaš nalog ili su krediti potrošeni.",
        AUTH_REQUIRED: "Prijava više nije važeća. Pitanje nije postavljeno.",
        RATE_LIMITED: "Previše pitanja u kratkom roku. Pokušajte ponovo malo kasnije.",
        NOT_FOUND: "Servis za pravna pitanja nije dostupan.",
      }[g.kod] || (r.status === 402 ? "Krediti su potrošeni. Pitanje nije postavljeno." : "Server je odbio zahtev. Pitanje nije postavljeno."));
    }

    function postavi(predmet) {
      if (trenutni && trenutni.id === predmet.id && trenutni.korisnik === sesija.stanje().korisnik) return;   // isti predmet: odgovor ostaje
      ocisti();
      trenutni = { id: predmet.id, korisnik: sesija.stanje().korisnik };
    }

    $("pp-forma").addEventListener("submit", function (e) { e.preventDefault(); posalji(); });
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) ocisti(); });

    return { postavi: postavi, ocisti: ocisti, zaustavi: function () { odjavi(); ocisti(); },
             _poslednji: function () { return poslednji ? poslednji.pitanje : null; } };
  }

  root.VxPitanjePredmeta = Object.freeze({ napravi: napravi, upozorenja: upozorenja, izvori: izvori, odeljci: odeljci });
})(window);
