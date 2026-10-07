/* Vindex V2 NG — ponašanje početnog radnog prostora (prototip 001).
 *
 * Bez mreže i bez backend-a: čita samo window.VX_DEMO.
 * Stanje ekrana (pretraga, sortiranje, navigacija) živi u `stanje` i NE
 * zavisi od teme — promena teme menja samo atribut na <html>.
 */
(function () {
  "use strict";

  /* Režim odlučuje src/runtime.js. Demo podaci se čitaju ISKLJUČIVO u DEMO
   * režimu; LIVE i neispravna konfiguracija nikad ne dodiruju `VX_DEMO`. */
  var rt = window.VxRuntime;
  var rezim = rt ? rt.rezim : "neispravan";
  var demo = rt && rezim === rt.DEMO ? window.VX_DEMO : null;
  var $ = function (id) { return document.getElementById(id); };
  var koren = document.documentElement;

  var stanje = { upit: "", kljuc: "izmenjeno", smer: "desc" };
  window.__vxStanje = stanje;

  /* ── Pomoćne ───────────────────────────────────────────────────────── */
  var kolator = new Intl.Collator("sr-Latn", { sensitivity: "base", numeric: true });
  var MESECI = ["jan.", "feb.", "mar.", "apr.", "maj", "jun", "jul", "avg.", "sep.", "okt.", "nov.", "dec."];

  /* Pretraga ne sme zavisiti od toga da li je korisnik kucao dijakritike. */
  function normalizuj(s) {
    return String(s || "").toLowerCase()
      .replace(/đ/g, "dj").replace(/[čć]/g, "c").replace(/š/g, "s").replace(/ž/g, "z")
      .normalize("NFD").replace(/[̀-ͯ]/g, "");
  }

  function oblik(n, jedan, dva, pet) {
    var d = n % 10, s = n % 100;
    if (d === 1 && s !== 11) return jedan;
    if (d >= 2 && d <= 4 && (s < 12 || s > 14)) return dva;
    return pet;
  }

  function datum(iso) { var p = iso.split("-"); return p[2] + "." + p[1] + "." + p[0] + "."; }
  function kratak(iso) { var p = iso.split("-"); return Number(p[2]) + ". " + MESECI[Number(p[1]) - 1]; }
  function razlikaDana(iso) { return Math.round((Date.parse(iso) - Date.parse(demo.danas)) / 86400000); }

  function el(tag, cls, tekst) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (tekst != null) e.textContent = tekst;
    return e;
  }

  var tajmer = 0;
  function poruka(t) {
    var s = $("status");
    s.textContent = t; s.classList.add("is-on");
    clearTimeout(tajmer);
    tajmer = setTimeout(function () { s.classList.remove("is-on"); }, 2600);
  }

  /* ── Registar predmeta ─────────────────────────────────────────────── */
  var NAZIV_STANJA = { aktivan: "Aktivan", cekanje: "Na čekanju" };
  var RED_STANJA = { aktivan: 0, cekanje: 1 };
  var POCETNI_SMER = { naziv: "asc", broj: "asc", stanje: "asc", izmenjeno: "desc" };

  var indeks = [];
  /* Samo za proveru (kao __vxStanje): koliko predmeta ekran drži u memoriji. */
  window.__vxPredmetaUMemoriji = function () { return indeks.length; };
  function postaviPredmete(lista) {
    indeks = lista.map(function (p) {
      return { p: p, tekst: normalizuj([p.naziv, p.klijent, p.broj, p.sud, p.vrsta].concat(p.stranke || []).join(" ")) };
    });
  }

  function uporedi(a, b) {
    var r;
    switch (stanje.kljuc) {
      case "naziv": r = kolator.compare(a.naziv, b.naziv); break;
      case "broj": r = kolator.compare(a.broj, b.broj); break;
      case "stanje": r = RED_STANJA[a.stanje] - RED_STANJA[b.stanje]; break;
      default: r = a.izmenjeno < b.izmenjeno ? -1 : a.izmenjeno > b.izmenjeno ? 1 : 0;
    }
    if (stanje.smer === "desc") r = -r;
    /* Determinističan ishod i za jednake vrednosti: konačna veza je broj, pa id. */
    return r || kolator.compare(a.broj, b.broj) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  }

  function vidljivi() {
    var reci = normalizuj(stanje.upit).split(/\s+/).filter(Boolean);
    return indeks
      .filter(function (x) { return reci.every(function (r) { return x.tekst.indexOf(r) !== -1; }); })
      .map(function (x) { return x.p; })
      .sort(uporedi);
  }

  function red(p) {
    var tr = el("tr");
    tr.dataset.id = p.id;

    var c1 = el("td", "cell-name");
    var a = el("a", "case__name", p.naziv);
    a.href = "#"; a.dataset.akcija = "predmet";
    /* Prikaz je ograničen na dva reda (CSS). Podatak se ne skraćuje: ceo naziv
     * je u DOM-u (čitač ekrana, pretraga), u `title` za miš, a fokus tastature
     * otkriva ceo naziv na mestu. */
    a.title = p.naziv;
    /* DEMO: „klijent · vrsta“. LIVE: stranke iz odgovora (tužilac · tuženi);
     * prazni delovi se ne prikazuju, ništa se ne izmišlja. */
    var delovi = p.stranke ? p.stranke : [p.klijent, p.vrsta];
    delovi = delovi.filter(function (x) { return x; });
    var meta = el("span", "case__meta");
    delovi.forEach(function (d, i) { if (i) meta.append(el("span", "sep", "·")); meta.append(d); });
    c1.append(a, meta);

    var c2 = el("td", "cell-ref");
    c2.append(el("span", "ref__no", p.broj || "—"));
    if (p.sud) c2.append(el("span", "ref__court", p.sud));

    /* Klasa stanja samo iz poznatog skupa; nepoznato stanje se prikazuje
     * doslovno, nikad kao „undefined“. */
    var c3 = el("td", "cell-state");
    var poznato = Object.prototype.hasOwnProperty.call(NAZIV_STANJA, p.stanje);
    c3.append(el("span", poznato ? "state state--" + p.stanje : "state", poznato ? NAZIV_STANJA[p.stanje] : p.stanje));

    var c4 = el("td", "cell-date num");
    var vreme = el("time", "date", p.izmenjeno ? datum(p.izmenjeno) : "");
    vreme.dateTime = p.izmenjeno;
    c4.append(vreme);

    tr.append(c1, c2, c3, c4);
    return tr;
  }

  function prikaziRegistar() {
    var lista = vidljivi();
    /* LIVE: broj je `ukupno` iz API-ja (ne broj u memoriji, ne demo broj). */
    var ukupno = izvor.stanje === "podaci" && typeof izvor.ukupno === "number" ? izvor.ukupno : indeks.length;
    var telo = $("rows");
    var frag = document.createDocumentFragment();
    lista.forEach(function (p) { frag.append(red(p)); });
    telo.replaceChildren(frag);

    document.querySelectorAll(".cases th[data-kljuc]").forEach(function (th) {
      if (th.dataset.kljuc === stanje.kljuc) th.setAttribute("aria-sort", stanje.smer === "asc" ? "ascending" : "descending");
      else th.removeAttribute("aria-sort");
    });

    var pretraga = stanje.upit.trim() !== "";
    $("count").textContent = pretraga
      ? lista.length + " od " + ukupno + " " + oblik(ukupno, "predmeta", "predmeta", "predmeta")
      : ukupno + " " + oblik(ukupno, "predmet", "predmeta", "predmeta");

    var prazno = lista.length === 0;
    $("registry").hidden = prazno;
    $("empty").hidden = !prazno;
    /* Oznaka stanja mora pratiti ono što piše na ekranu (ne sme ostati
     * „ucitavanje“ iz prethodnog stanja). DEMO je nema, kao i ranije. */
    if (izvor.stanje === "podaci") $("empty").dataset.stanje = ukupno === 0 ? "prazno" : "bez-rezultata";
    else delete $("empty").dataset.stanje;
    if (prazno) {
      if (ukupno === 0) {
        $("empty-title").textContent = "Nema aktivnih predmeta";
        $("empty-text").textContent = "Kada predmet bude otvoren, pojaviće se ovde.";
        $("empty-clear").hidden = true;
      } else {
        $("empty-title").textContent = "Nijedan predmet ne odgovara pretrazi";
        $("empty-text").textContent = (izvor.stanje === "podaci"
          ? "Pretraženo po nazivu, broju predmeta i strankama za „"
          : "Pretraženo po nazivu, klijentu, vrsti, broju predmeta i sudu za „") + stanje.upit.trim() + "“.";
        $("empty-clear").hidden = false;
      }
    }
    $("pretraga").disabled = ukupno === 0;
  }

  /* ── Stanje bez podataka (LIVE / neispravna konfiguracija) ─────────────
   * Koristi postojeći blok „empty“ (struktura ekrana se ne menja), ali NIKAD
   * ne kaže „nema predmeta“: ovo je greška ili nepovezan izvor, ne prazna
   * kancelarija. Pretraga je isključena, broj se ne prikazuje. */
  var izvor = { stanje: "demo", naslov: "", tekst: "" };

  function prikaziStanje() {
    $("rows").replaceChildren();
    $("registry").hidden = true;
    $("empty").hidden = false;
    $("empty").dataset.stanje = izvor.stanje;
    $("empty-title").textContent = izvor.naslov;
    $("empty-text").textContent = izvor.tekst;
    $("empty-clear").hidden = true;
    $("count").textContent = "";
    $("pretraga").disabled = true;
  }

  function osvezi() {
    if (izvor.stanje === "demo" || izvor.stanje === "podaci") prikaziRegistar();
    else prikaziStanje();
  }

  /* ── LIVE: prikaz stanja koja javlja kontroler (src/live.js) ───────────
   * Svako stanje osim „podaci“ ODMAH briše predmete iz memorije ekrana i
   * pretragu: ništa od prethodne sesije ne sme ostati kao trenutno. */
  var TEKST_STANJA = {
    "ucitavanje": ["Učitavanje predmeta…", "Predmeti se učitavaju sa servera."],
    "bez-prijave": ["Niste prijavljeni", "Prijavite se u Vindex da biste videli svoje predmete."],
    "istekla": ["Sesija je istekla", "Prijavite se ponovo u Vindex. Predmeti se ne prikazuju dok sesija ne bude obnovljena."],
    "greska-sesije": ["Sesija nije mogla da se pročita", "Prijavite se ponovo u Vindex. Predmeti se ne prikazuju."],
    "nepovezano": ["Živi izvor podataka nije povezan", "Predmeti se ne prikazuju dok se ne učitaju sa servera. Primeri se u ovom režimu ne prikazuju."],
    "greska": ["Predmeti nisu učitani", "Došlo je do greške pri učitavanju. Ovo nije prazna lista."],
  };

  /* Svaka klasa greške ima SVOJE stanje. Nijedna ne kaže „nema predmeta“:
   * neuspelo čitanje nije prazna kancelarija. */
  var STANJE_GRESKE = {
    AUTH_REQUIRED: ["greska-prijava", "Prijava više nije važeća", "Server nije prihvatio sesiju. Prijavite se ponovo u Vindex; predmeti se do tada ne prikazuju."],
    FORBIDDEN: ["greska-pristup", "Nemate pristup predmetima", "Server je odbio pristup za ovaj nalog. Predmeti se ne prikazuju."],
    NOT_FOUND: ["greska-servis", "Servis za predmete nije pronađen", "Server nije pronašao listu predmeta. Predmeti nisu učitani."],
    RATE_LIMITED: ["greska-ogranicenje", "Previše zahteva", "Server je privremeno ograničio zahteve. Predmeti nisu učitani; pokušajte ponovo malo kasnije."],
    SERVER_ERROR: ["greska-server", "Server trenutno ne odgovara ispravno", "Predmeti nisu učitani zbog greške na serveru. Ovo nije prazna lista."],
    HTTP_ERROR: ["greska-server", "Predmeti nisu učitani", "Server je vratio neočekivan odgovor. Ovo nije prazna lista."],
    NETWORK_ERROR: ["greska-mreza", "Server nije dostupan", "Veza sa serverom nije uspostavljena. Predmeti nisu učitani; ovo nije prazna lista."],
    INVALID_RESPONSE: ["greska-odgovor", "Odgovor servera nije ispravan", "Podaci nisu prikazani jer odgovor nije mogao pouzdano da se pročita."],
    INCONSISTENT: ["greska-nedosledno", "Lista se promenila tokom učitavanja", "Predmeti nisu prikazani da ne bi bili prikazani nepotpuno. Osvežite stranicu."],
    CONFIG_ERROR: ["greska-konfiguracija", "Greška u podešavanju zahteva", "Zahtev nije poslat. Predmeti se ne prikazuju."],
  };

  function sekundi(ra) { var n = Number(ra); return Number.isFinite(n) && n > 0 && n < 86400 ? Math.ceil(n) : 0; }

  function prikaziLive(v) {
    if (v.vrsta === "podaci") {
      postaviPredmete(v.predmeti || []);
      izvor = { stanje: "podaci", naslov: "", tekst: "", ukupno: v.ukupno };
    } else {
      postaviPredmete([]);
      stanje.upit = "";
      $("pretraga").value = "";
      if (v.vrsta === "greska") {
        var g = (v.greska && STANJE_GRESKE[v.greska.kod]) || ["greska", TEKST_STANJA["greska"][0], TEKST_STANJA["greska"][1]];
        var tekstG = g[2];
        var za = v.greska && v.greska.kod === "RATE_LIMITED" ? sekundi(v.greska.retryAfter) : 0;
        if (za) tekstG = "Server je privremeno ograničio zahteve. Predmeti nisu učitani; pokušajte ponovo za " + za + " s.";
        izvor = { stanje: g[0], naslov: g[1], tekst: tekstG };
      } else {
        var t = TEKST_STANJA[v.vrsta] || TEKST_STANJA["greska"];
        izvor = { stanje: v.vrsta, naslov: t[0], tekst: t[1] };
      }
    }
    osvezi();
  }

  /* ── Panel: zahteva pažnju ─────────────────────────────────────────── */
  function kadaTekst(s) {
    var d = razlikaDana(s.kada);
    if (s.primljen) return { t: "Primljeno " + kratak(s.kada), blizu: false };
    var t = d === 0 ? "Danas" : d === 1 ? "Sutra" : "Za " + d + " " + oblik(d, "dan", "dana", "dana");
    t += " · " + kratak(s.kada) + (s.vreme ? " " + s.vreme : "");
    return { t: t, blizu: d <= 2 };
  }

  var NAJVISE_STAVKI = 5;

  function prikaziPanel() {
    var sve = demo.paznja.slice().sort(function (a, b) {
      return a.kada < b.kada ? -1 : a.kada > b.kada ? 1 : kolator.compare(a.broj, b.broj);
    });
    var stavke = sve.slice(0, NAJVISE_STAVKI);
    var ol = $("attention");
    ol.replaceChildren();
    stavke.forEach(function (s) {
      var li = el("li", "att");
      var top = el("div", "att__top");
      var k = kadaTekst(s);
      var when = el("time", "att__when" + (k.blizu ? " att__when--soon" : ""), k.t);
      when.dateTime = s.kada;
      top.append(el("span", "att__kind", s.vrsta), when);
      var a = el("a", "att__title", s.naslov);
      a.href = "#"; a.dataset.akcija = "stavka";
      var c = el("span", "att__case");
      c.append(el("span", "no", s.broj), " · " + s.predmet);
      li.append(top, a, c);
      ol.append(li);
    });
    ol.hidden = stavke.length === 0;
    $("attention-empty").hidden = stavke.length !== 0;
    /* Bez odredišta „Prikaži sve“ u prototipu: samo pošteno kažemo da ih ima više. */
    var vise = sve.length - stavke.length;
    $("attention-more").hidden = vise <= 0;
    $("attention-more").textContent = vise > 0 ? "Prikazano " + stavke.length + " od " + sve.length + ", po datumu." : "";
    $("panel-toggle-count").textContent = sve.length ? String(sve.length) : "";
    $("demo-date").textContent = "Referentni demo datum: " + datum(demo.danas);
  }

  /* Van DEMO režima panel ne prikazuje nijednu stavku: demo obaveze uz stvarne
   * predmete bile bi izmišljene pravne obaveze. Ne tvrdi ni „nema obaveza“. */
  function prikaziPanelNepovezan() {
    $("attention").replaceChildren();
    $("attention").hidden = true;
    $("attention-empty").hidden = false;
    $("attention-empty").dataset.stanje = "nepovezano";
    document.querySelector("#attention-empty .panel__empty-title").textContent = "Ovaj deo još nije povezan u ovom pregledu.";
    document.querySelector("#attention-empty .panel__empty-text").textContent = "Rokove i obaveze proverite u spisima predmeta.";
    $("attention-more").hidden = true;
    $("attention-more").textContent = "";
    $("panel-toggle-count").textContent = "";
    $("demo-date").textContent = "";
  }

  /* ── Tema ──────────────────────────────────────────────────────────── */
  function postaviTemu(t) {
    koren.dataset.theme = t;
    $("theme-toggle-label").textContent = t === "dark" ? "Svetla tema" : "Tamna tema";
    $("theme-toggle").setAttribute("aria-label", t === "dark" ? "Uključi svetlu temu" : "Uključi tamnu temu");
    try { localStorage.setItem("vx-ng-tema", t); } catch (e) {}
  }

  /* ── Navigacija i fioke ────────────────────────────────────────────── */
  var uski = window.matchMedia("(max-width: 859px)");
  var srednji = window.matchMedia("(max-width: 1279px)");
  var otvorenaFioka = null, okidac = null;

  function postaviSkupljanje(skupljena) {
    if (skupljena) koren.dataset.nav = "skupljena"; else delete koren.dataset.nav;
    var b = $("nav-collapse");
    b.setAttribute("aria-expanded", String(!skupljena));
    b.querySelector(".sidenav__label").textContent = skupljena ? "Proširi navigaciju" : "Skupi navigaciju";
    b.title = skupljena ? "Proširi navigaciju" : "";
    try { localStorage.setItem("vx-ng-nav", skupljena ? "skupljena" : "puna"); } catch (e) {}
  }

  function otvoriFioku(fioka, dugme) {
    zatvoriFioku(false);
    otvorenaFioka = fioka; okidac = dugme;
    fioka.classList.add("is-open");
    dugme.setAttribute("aria-expanded", "true");
    $("scrim").hidden = false;
    ["glavni", "nav", "panel"].forEach(function (id) { var e = $(id); if (e !== fioka) e.inert = true; });
    document.querySelector(".topbar").inert = true;
    var prvi = fioka.querySelector("a[href], button:not([hidden])");
    if (prvi) setTimeout(function () { prvi.focus(); }, 0);
  }

  function zatvoriFioku(vratiFokus) {
    if (!otvorenaFioka) return;
    otvorenaFioka.classList.remove("is-open");
    okidac.setAttribute("aria-expanded", "false");
    $("scrim").hidden = true;
    ["glavni", "nav", "panel"].forEach(function (id) { $(id).inert = false; });
    document.querySelector(".topbar").inert = false;
    if (vratiFokus !== false) okidac.focus();
    otvorenaFioka = null;
  }

  function uskladiRaspored() {
    zatvoriFioku(false);
    /* Na srednjoj širini panel je fioka; na uskoj i navigacija. */
    $("nav-toggle").setAttribute("aria-expanded", "false");
    $("panel-toggle").setAttribute("aria-expanded", "false");
  }

  /* ── Događaji ──────────────────────────────────────────────────────── */
  $("pretraga").addEventListener("input", function (e) { stanje.upit = e.target.value; osvezi(); });
  $("pretraga").addEventListener("keydown", function (e) {
    if (e.key === "Escape" && e.target.value) { e.target.value = ""; stanje.upit = ""; osvezi(); }
  });
  $("empty-clear").addEventListener("click", function () {
    $("pretraga").value = ""; stanje.upit = ""; osvezi(); $("pretraga").focus();
  });

  document.querySelectorAll(".cases th[data-kljuc] .sort").forEach(function (b) {
    b.addEventListener("click", function () {
      var k = b.closest("th").dataset.kljuc;
      if (stanje.kljuc === k) stanje.smer = stanje.smer === "asc" ? "desc" : "asc";
      else { stanje.kljuc = k; stanje.smer = POCETNI_SMER[k]; }
      osvezi();
    });
  });

  $("theme-toggle").addEventListener("click", function () {
    postaviTemu(koren.dataset.theme === "light" ? "dark" : "light");
  });

  $("nav-collapse").addEventListener("click", function () { postaviSkupljanje(koren.dataset.nav !== "skupljena"); });
  $("nav-toggle").addEventListener("click", function () { otvoriFioku($("nav"), $("nav-toggle")); });
  $("panel-toggle").addEventListener("click", function () { otvoriFioku($("panel"), $("panel-toggle")); });
  $("panel-close").addEventListener("click", function () { zatvoriFioku(); });
  $("scrim").addEventListener("click", function () { zatvoriFioku(); });

  document.addEventListener("click", function (e) {
    var a = e.target.closest("a");
    if (!a) return;
    if (a.dataset.modul) {
      e.preventDefault();
      poruka("Modul „" + a.dataset.modul + "“ nije deo ovog prototipa.");
    } else if (a.dataset.akcija) {
      e.preventDefault();
      poruka(a.dataset.akcija === "predmet"
        ? "Detalj predmeta nije deo ovog prototipa."
        : "Otvaranje stavke nije deo ovog prototipa.");
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && otvorenaFioka) { zatvoriFioku(); return; }
    var t = e.target;
    var kuca = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
    if (e.key === "/" && !kuca && !e.ctrlKey && !e.metaKey && !e.altKey && !$("pretraga").disabled) {
      e.preventDefault(); $("pretraga").focus();
    }
  });

  if (uski.addEventListener) { uski.addEventListener("change", uskladiRaspored); srednji.addEventListener("change", uskladiRaspored); }

  /* ── Start ─────────────────────────────────────────────────────────── */
  postaviTemu(koren.dataset.theme === "light" ? "light" : "dark");
  postaviSkupljanje(koren.dataset.nav === "skupljena");
  if (demo) {
    postaviPredmete(demo.predmeti);
    osvezi();
    prikaziPanel();
  } else if (rt && rezim === rt.LIVE && window.VxLive && window.VxSesija) {
    /* Pretraga u LIVE režimu radi samo nad učitanim poljima; sud i klijent
     * nisu deo odgovora, pa se ne obećavaju. */
    $("pretraga").placeholder = "Naziv, broj predmeta ili stranka";
    /* LIVE ne sme nositi oznake demo podataka: ni značku, ni „Demo nalog“,
     * ni napomenu panela, ni natpis tabele. Ne dodaje se nova značka. */
    document.querySelector(".demo-badge").hidden = true;
    document.querySelector(".account").hidden = true;
    document.querySelector(".panel__note").hidden = true;
    document.querySelector(".cases caption").textContent = "Aktivni predmeti";
    prikaziPanelNepovezan();
    prikaziLive({ vrsta: "ucitavanje" });
    var kontrolerLive = window.VxLive.napravi({ sesija: window.VxSesija, izvor: window.VxLiveIzvor || null, prikazi: prikaziLive });
    /* Samo za proveru (kao __vxStanje): ponovno učitavanje bez UI elementa. */
    window.__vxLiveOsvezi = function () { kontrolerLive.osvezi(); };
    kontrolerLive.pokreni();
  } else {
    izvor = { stanje: "neispravna-konfiguracija", naslov: "Neispravna konfiguracija",
              tekst: (rt && rt.greska) || "Režim podataka nije učitan. Podaci se ne prikazuju." };
    osvezi();
    prikaziPanelNepovezan();
  }
})();
