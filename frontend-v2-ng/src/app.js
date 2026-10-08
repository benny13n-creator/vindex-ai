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
    /* LIVE: stvaran link na detalj predmeta (radi i „otvori u novom tabu“).
     * DEMO nema detalj: ostaje poštena poruka da to nije deo prikaza. */
    if (demo) { a.href = "#"; a.dataset.akcija = "predmet"; }
    else a.href = adresaPredmeta(p.id, "pregled");
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
    if ($("empty-prijava")) $("empty-prijava").hidden = true;
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

  /* Stanja u kojima je jedini ispravan sledeći korak postojeća prijava. */
  var STANJA_PRIJAVE = { "bez-prijave": 1, "istekla": 1, "greska-sesije": 1, "greska-prijava": 1,
                         "greska-auth_required": 1 };
  function linkPrijave(id, stanjeOznaka) {
    var a = $(id);
    if (!a) {
      /* Registar: link se pravi tek kad zatreba (samo LIVE), da DEMO DOM ostane
       * identičan foundation-u (verify:demo-otisak). */
      if (!STANJA_PRIJAVE[stanjeOznaka]) return;
      a = el("a", "text-btn text-btn--line", "Prijavite se");
      a.id = id;
      $("empty").append(a);
    }
    a.href = (rt && rt.prijava) || "/app";
    a.hidden = !STANJA_PRIJAVE[stanjeOznaka];
  }

  function prikaziStanje() {
    linkPrijave("empty-prijava", izvor.stanje);
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

  /* ── Detalj predmeta (LIVE, samo čitanje) ──────────────────────────────
   * Ruta je u hash-u: #/predmeti/<id> i #/predmeti/<id>/dokumenti. Radi isto
   * pod /v2/preview/ i pod /app; Back, osvežavanje i direktan link rade bez
   * serverske rute. Token nikad nije u adresi. Svaki drugi hash (npr. #glavni)
   * je registar. Sav sadržaj se upisuje kao tekst. */
  function adresaPredmeta(id, odeljak) {
    return "#/predmeti/" + encodeURIComponent(id) + (odeljak === "dokumenti" ? "/dokumenti" : odeljak === "rad" ? "/rad" : odeljak === "pitanje" ? "/pitanje" : "");
  }
  function rutaIzAdrese() {
    /* NS005: radni pogledi bez id-a predmeta imaju prednost nad #/predmeti/<id>. */
    if (/^#\/predmeti\/nov\/?$/.test(location.hash)) return { pogled: "nov" };
    if (/^#\/pretraga\/?$/.test(location.hash)) return { pogled: "pretraga" };
    var m = /^#\/predmeti\/([^\/?#]*)(\/dokumenti|\/rad|\/pitanje)?\/?$/.exec(location.hash);
    if (!m) return null;
    var id;
    try { id = decodeURIComponent(m[1]); } catch (e) { id = ""; }
    return { id: id, odeljak: m[2] === "/dokumenti" ? "dokumenti" : m[2] === "/rad" ? "rad" : m[2] === "/pitanje" ? "pitanje" : "pregled" };
  }

  var NAZIV_STATUSA = { aktivan: "Aktivan", cekanje: "Na čekanju", zatvoren: "Zatvoren", arhiviran: "Arhiviran" };
  /* Isti rečnik vrsta koji koristi postojeći /app (static/vindex.js, izbor vrste
   * predmeta); nepoznata vrednost se prikazuje doslovno. */
  var NAZIV_VRSTE = { parnicno: "Parnični", krivicno: "Krivični", upravno: "Upravni", radno: "Radno", porodicno: "Porodičnopravni",
                      nasledjivanje: "Ostavinski", privredno: "Privredno", nepokretnosti: "Nepokretnosti", ostalo: "Ostalo" };
  var brojFormat = new Intl.NumberFormat("sr-Latn-RS", { maximumFractionDigits: 2 });
  var STANJE_PREDMETA = {
    "ucitavanje": ["Učitavanje predmeta…", "Podaci predmeta se učitavaju sa servera."],
    "bez-prijave": TEKST_STANJA["bez-prijave"],
    "istekla": TEKST_STANJA["istekla"],
    "greska-sesije": TEKST_STANJA["greska-sesije"],
  };
  /* 403 i 404 daju ISTU poruku: spolja se ne razlikuje tuđ od nepostojećeg predmeta. */
  var GRESKA_PREDMETA = {
    NOT_FOUND: ["Predmet nije dostupan", "Predmet ne postoji ili nemate pristup. Podaci se ne prikazuju."],
    FORBIDDEN: ["Predmet nije dostupan", "Predmet ne postoji ili nemate pristup. Podaci se ne prikazuju."],
    AUTH_REQUIRED: ["Prijava više nije važeća", "Server nije prihvatio sesiju. Prijavite se ponovo u Vindex."],
    RATE_LIMITED: ["Previše zahteva", "Server je privremeno ograničio zahteve. Pokušajte ponovo malo kasnije."],
    SERVER_ERROR: ["Predmet nije učitan", "Greška na serveru. Podaci predmeta se ne prikazuju."],
    HTTP_ERROR: ["Predmet nije učitan", "Server je vratio neočekivan odgovor. Podaci se ne prikazuju."],
    NETWORK_ERROR: ["Server nije dostupan", "Veza sa serverom nije uspostavljena. Predmet nije učitan."],
    INVALID_RESPONSE: ["Odgovor servera nije ispravan", "Podaci nisu prikazani jer odgovor nije mogao pouzdano da se pročita."],
  };
  var GRESKA_DOKUMENTA = {
    NOT_FOUND: "Dokument nije dostupan za pregled.",
    FORBIDDEN: "Dokument nije dostupan za pregled.",
    AUTH_REQUIRED: "Server nije prihvatio sesiju. Tekst dokumenta se ne prikazuje.",
    RATE_LIMITED: "Server je privremeno ograničio zahteve. Pokušajte ponovo malo kasnije.",
    NETWORK_ERROR: "Server nije dostupan. Tekst dokumenta nije učitan.",
    INVALID_RESPONSE: "Odgovor servera nije ispravan. Tekst se ne prikazuje.",
  };

  var detalj = null, ruta = null, detaljPodaci = null, izabraniDok = null, radPredmeta = null, klijentiPredmeta = null, rocistaPredmeta = null, pitanjePredmeta = null;
  /* Samo za proveru: šta ekran detalja drži u memoriji. */
  window.__vxDetaljUMemoriji = function () {
    return { predmet: detaljPodaci ? detaljPodaci.predmet.id : null, dokumenata: detaljPodaci ? detaljPodaci.dokumenti.length : 0,
             tekst: $("dok-tekst").textContent.length };
  };

  function cinjenica(dl, naziv, vrednost) {
    if (vrednost === null || vrednost === undefined || vrednost === "") return;
    dl.append(el("dt", null, naziv), el("dd", null, String(vrednost)));
  }
  function nazivStatusa(s) { return Object.prototype.hasOwnProperty.call(NAZIV_STATUSA, s) ? NAZIV_STATUSA[s] : s; }

  function ocistiDokument() {
    izabraniDok = null;
    $("dok-sadrzaj").hidden = true;
    $("dok-uputstvo").hidden = false;
    $("dok-naslov").textContent = "";
    $("dok-cinjenice").replaceChildren();
    $("dok-stanje").hidden = true; $("dok-stanje").textContent = ""; delete $("dok-stanje").dataset.stanje;
    $("dok-tekst").hidden = true; $("dok-tekst").textContent = "";
    $("odeljak-dokumenti").classList.remove("is-doc-open");
    $("dok-nazad").hidden = true;
    document.querySelectorAll("#dok-lista .docs__item").forEach(function (b) { b.removeAttribute("aria-current"); });
  }

  function ocistiPredmet() {
    detaljPodaci = null;
    $("predmet-naslov").textContent = "";
    $("predmet-ref").replaceChildren();
    $("predmet-cinjenice").replaceChildren();
    $("predmet-klijenti").replaceChildren();
    $("predmet-klijenti-blok").hidden = true;
    $("predmet-klijenti-prazno").hidden = true;
    if (klijentiPredmeta) klijentiPredmeta.ocisti();
    $("dok-lista").replaceChildren();
    $("dok-prazno").hidden = true;
    $("dok-broj").textContent = "";
    $("predmet-odeljci").hidden = true;
    $("odeljak-pregled").hidden = true;
    $("odeljak-rad").hidden = true;
    $("odeljak-pitanje").hidden = true;
    $("odeljak-dokumenti").hidden = true;
    $("predmet-stanje").hidden = true;
    if (radPredmeta) radPredmeta.ocisti();
    if (rocistaPredmeta) rocistaPredmeta.ocisti();
    $("predmet-prijava").hidden = true;
    ocistiDokument();
  }

  function prikaziStanjePredmeta(naslov, tekst, oznaka) {
    ocistiPredmet();
    $("predmet-stanje").hidden = false;
    $("predmet-stanje").dataset.stanje = oznaka;
    $("predmet-stanje-naslov").textContent = naslov;
    $("predmet-stanje-tekst").textContent = tekst;
    linkPrijave("predmet-prijava", oznaka);
  }

  function prikaziOdeljak() {
    if (!ruta || !detaljPodaci) return;
    var o = ruta.odeljak;
    if (o === "rad" && rocistaPredmeta) rocistaPredmeta.aktiviraj();
    $("odeljak-pregled").hidden = o !== "pregled";
    $("odeljak-rad").hidden = o !== "rad";
    $("odeljak-pitanje").hidden = o !== "pitanje";
    $("odeljak-dokumenti").hidden = o !== "dokumenti";
    ["pregled", "rad", "pitanje", "dokumenti"].forEach(function (x) {
      var tab = $("tab-" + x);
      tab.href = adresaPredmeta(ruta.id, x);
      if (x === o) tab.setAttribute("aria-current", "page"); else tab.removeAttribute("aria-current");
    });
  }

  function prikaziPredmetPodatke(v) {
    ocistiPredmet();
    detaljPodaci = { predmet: v.predmet, dokumenti: v.dokumenti };
    var p = v.predmet;
    $("predmet-naslov").textContent = p.naziv || "Predmet bez naziva";
    var ref = $("predmet-ref");
    if (p.broj) ref.append(el("span", "ref__no", p.broj));
    if (p.status) {
      var poznat = Object.prototype.hasOwnProperty.call(NAZIV_STATUSA, p.status);
      ref.append(el("span", poznat ? "state state--" + p.status : "state", nazivStatusa(p.status)));
    }
    var dl = $("predmet-cinjenice");
    cinjenica(dl, "Broj predmeta", p.broj);
    cinjenica(dl, "Vrsta", Object.prototype.hasOwnProperty.call(NAZIV_VRSTE, p.tip) ? NAZIV_VRSTE[p.tip] : p.tip);
    cinjenica(dl, "Tužilac", p.tuzilac);
    cinjenica(dl, "Tuženi", p.tuzeni);
    cinjenica(dl, "Vrednost spora", p.vrednost !== null ? brojFormat.format(p.vrednost) + " RSD" : "");
    cinjenica(dl, "Otvoren", p.otvoren ? datum(p.otvoren) : "");
    cinjenica(dl, "Poslednja izmena", p.izmenjeno ? datum(p.izmenjeno) : "");
    v.klijenti.forEach(function (k) {
      var li = el("li", "people__item");
      li.append(el("span", "people__name", k.naziv));
      var meta = [k.firma, k.uloga].filter(Boolean).join(" · ");
      if (meta) li.append(el("span", "people__meta", meta));
      $("predmet-klijenti").append(li);
    });
    /* NS005: blok je uvek vidljiv (vezivanje); `klijenti_linked` je obavezan niz,
     * pa je prazan niz istinito „nijedan klijent". */
    $("predmet-klijenti-prazno").hidden = v.klijenti.length !== 0;
    $("predmet-klijenti-blok").hidden = false;
    if (klijentiPredmeta) klijentiPredmeta.postavi(v.predmet);
    $("dok-broj").textContent = String(v.dokumenti.length);
    var lista = $("dok-lista");
    v.dokumenti.forEach(function (d) {
      var li = el("li");
      var b = el("button", "docs__item");
      b.type = "button"; b.dataset.dok = d.id;
      b.append(el("span", "docs__name", d.naziv || "Dokument bez naziva"));
      var meta = [d.tip ? d.tip.replace(/_/g, " ") : "", d.datum ? datum(d.datum) : ""].filter(Boolean).join(" · ");
      if (meta) b.append(el("span", "docs__meta", meta));
      li.append(b); lista.append(li);
    });
    $("dok-prazno").hidden = v.dokumenti.length !== 0;
    $("predmet-odeljci").hidden = false;
    if (radPredmeta) radPredmeta.postavi(v);
    if (rocistaPredmeta) rocistaPredmeta.postavi(v.predmet, !!ruta && ruta.odeljak === "rad");
    if (pitanjePredmeta) pitanjePredmeta.postavi(v.predmet);
    prikaziOdeljak();
  }

  function prikaziDokumentStanje(v) {
    if (!detaljPodaci || v.dokId !== izabraniDok) return;
    var st = $("dok-stanje");
    $("dok-tekst").hidden = true; $("dok-tekst").textContent = "";
    st.hidden = false; st.dataset.stanje = v.stanje === "greska" ? "greska" : v.stanje;
    st.textContent = v.stanje === "ucitavanje" ? "Učitavanje teksta dokumenta…"
      : (GRESKA_DOKUMENTA[v.greska && v.greska.kod] || "Tekst dokumenta nije učitan zbog greške na serveru.");
  }

  function prikaziDokumentTekst(v) {
    if (!detaljPodaci || v.dokId !== izabraniDok) return;
    var st = $("dok-stanje");
    if (!v.dostupan) {
      st.hidden = false; st.dataset.stanje = "bez-teksta";
      st.textContent = "Tekst ovog dokumenta nije izdvojen, pa ne može da se prikaže u ovom pregledu.";
      $("dok-tekst").hidden = true; $("dok-tekst").textContent = "";
      return;
    }
    st.hidden = true; st.textContent = ""; delete st.dataset.stanje;
    $("dok-tekst").textContent = v.tekst;
    $("dok-tekst").hidden = false;
  }

  function izaberiDokument(id) {
    if (!detaljPodaci) return;
    var d = detaljPodaci.dokumenti.find(function (x) { return x.id === id; });
    if (!d) return;
    ocistiDokument();
    izabraniDok = id;
    document.querySelectorAll("#dok-lista .docs__item").forEach(function (b) {
      if (b.dataset.dok === id) b.setAttribute("aria-current", "true"); else b.removeAttribute("aria-current");
    });
    $("dok-uputstvo").hidden = true;
    $("dok-sadrzaj").hidden = false;
    $("dok-naslov").textContent = d.naziv || "Dokument bez naziva";
    var dl = $("dok-cinjenice");
    cinjenica(dl, "Vrsta dokumenta", d.tip ? d.tip.replace(/_/g, " ") : "");
    cinjenica(dl, "Dodat", d.datum ? datum(d.datum) : "");
    cinjenica(dl, "Veličina", d.velicinaKb !== null ? brojFormat.format(d.velicinaKb) + " KB" : "");
    cinjenica(dl, "Redni broj", d.redniBroj);
    $("odeljak-dokumenti").classList.add("is-doc-open");
    $("dok-nazad").hidden = false;
    $("dok-naslov").focus();
    detalj.otvoriDokument(id);
  }

  function prikaziDetalj(v) {
    if (v.vrsta === "predmet-ocisti") { ocistiPredmet(); if (pitanjePredmeta) pitanjePredmeta.ocisti(); return; }
    if (v.vrsta === "dokument-ocisti") { ocistiDokument(); return; }
    if (v.vrsta === "predmet") { prikaziPredmetPodatke(v); return; }
    if (v.vrsta === "dokument-stanje") { prikaziDokumentStanje(v); return; }
    if (v.vrsta === "dokument") { prikaziDokumentTekst(v); return; }
    if (v.stanje === "greska") {
      var g = GRESKA_PREDMETA[v.greska && v.greska.kod] || GRESKA_PREDMETA.SERVER_ERROR;
      prikaziStanjePredmeta(g[0], g[1], "greska-" + String((v.greska && v.greska.kod) || "nepoznato").toLowerCase());
    } else {
      var t = STANJE_PREDMETA[v.stanje] || GRESKA_PREDMETA.SERVER_ERROR;
      prikaziStanjePredmeta(t[0], t[1], v.stanje);
    }
  }

  var novPredmet = null, pretraga = null, pogledRada = null;
  /* Radni pogledi bez predmeta: id sekcije + kontroler (otvori/zatvori). */
  function pogledi() { return { nov: ["nov-predmet", novPredmet], pretraga: ["pretraga-pogled", pretraga] }; }
  function zatvoriPogledRada() {
    var p = pogledRada && pogledi()[pogledRada];
    if (p) { p[1].zatvori(); $(p[0]).hidden = true; }
    pogledRada = null;
  }

  function primeniRutu() {
    var r = rutaIzAdrese();
    if (r && r.pogled) {
      if (ruta) { ruta = null; detalj.zatvori(); $("predmet").hidden = true; }
      if (pogledRada === r.pogled) return;
      zatvoriPogledRada();
      pogledRada = r.pogled;
      zatvoriFioku(false);
      koren.dataset.pogled = r.pogled;
      var pg = pogledi()[r.pogled];
      $(pg[0]).hidden = false;
      pg[1].otvori();
      return;
    }
    if (pogledRada) {
      zatvoriPogledRada();
      if (!r) { delete koren.dataset.pogled; $("glavni").focus(); return; }
    }
    if (!r) {
      if (ruta) {
        ruta = null;
        detalj.zatvori();
        delete koren.dataset.pogled;
        $("predmet").hidden = true;
        $("glavni").focus();
      }
      return;
    }
    var noviPredmet = !ruta || ruta.id !== r.id;
    ruta = r;
    zatvoriFioku(false);
    koren.dataset.pogled = "predmet";
    $("predmet").hidden = false;
    if (noviPredmet) { detalj.otvori(r.id); $("predmet-naslov").focus(); }
    prikaziOdeljak();
  }

  /* Razdelnik liste dokumenata: miš i strelice, 240–480 px; pamti se lokalno. */
  function postaviSirinuListe(px, pamti) {
    var w = Math.max(240, Math.min(480, Math.round(px)));
    $("odeljak-dokumenti").style.setProperty("--docs-list-w", w + "px");
    $("dok-razdelnik").setAttribute("aria-valuenow", String(w));
    if (pamti) { try { localStorage.setItem("vx-ng-dok-sirina", String(w)); } catch (e) {} }
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
    /* PRIMARNI prikaz (/app): samo stvarne funkcije. Moduli koji još ne
     * postoje se uklanjaju (ne glume rad), panel „Zahteva pažnju“ nije povezan
     * sa stvarnim obavezama pa se ne prikazuje; odjava ide postojećim tokom. */
    var primarni = rt.prikaz === rt.PRIMARNI;
    if (primarni) {
      koren.dataset.prikaz = "primarni";
      document.querySelectorAll(".sidenav__item[data-modul]").forEach(function (a) { a.closest("li").remove(); });
      $("odjava").href = rt.odjava;
      var uskladiOdjavu = function () { $("odjava").hidden = window.VxSesija.stanje().stanje !== window.VxSesija.STANJA.PRIJAVLJEN; };
      window.VxSesija.naPromenu(uskladiOdjavu);
      window.__vxUskladiOdjavu = uskladiOdjavu;
    }
    /* Pretraga u LIVE režimu radi samo nad učitanim poljima; sud i klijent
     * nisu deo odgovora, pa se ne obećavaju. */
    $("pretraga").placeholder = "Naziv, broj predmeta ili stranka";
    /* Sud nema kanonski izvor u podacima predmeta, pa ga LIVE ne obećava:
     * ista kolona, samo poštena oznaka (DEMO zadržava „Broj i sud“). */
    document.querySelector('.cases th[data-kljuc="broj"] .sort').firstChild.nodeValue = "Broj predmeta";
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

    /* Detalj predmeta: isti izvor sesije, sopstveni životni ciklus. */
    detalj = window.VxDetalj.napravi({ sesija: window.VxSesija, izvor: window.VxPredmetIzvor, prikazi: prikaziDetalj });
    /* NS005 — izmena, beleške, hronologija; posle upisa predmet se ponovo čita. */
    radPredmeta = window.VxRadPredmeta.napravi({ sesija: window.VxSesija, api: window.VxApi, osvezi: function () { detalj.osvezi(); } });
    klijentiPredmeta = window.VxKlijentiPredmeta.napravi({ sesija: window.VxSesija, api: window.VxApi, osvezi: function () { detalj.osvezi(); } });
    rocistaPredmeta = window.VxRocistaPredmeta.napravi({ sesija: window.VxSesija, api: window.VxApi });
    pitanjePredmeta = window.VxPitanjePredmeta.napravi({ sesija: window.VxSesija, api: window.VxApi });
    $("dok-lista").addEventListener("click", function (e) {
      var b = e.target.closest("button[data-dok]");
      if (b) izaberiDokument(b.dataset.dok);
    });
    $("dok-nazad").addEventListener("click", function () {
      var id = izabraniDok;
      detalj.zatvoriDokument();
      var b = id && document.querySelector('#dok-lista .docs__item[data-dok="' + CSS.escape(id) + '"]');
      if (b) b.focus();
    });
    var razdelnik = $("dok-razdelnik");
    try { var sacuvana = Number(localStorage.getItem("vx-ng-dok-sirina")); if (sacuvana) postaviSirinuListe(sacuvana); else postaviSirinuListe(320); }
    catch (e) { postaviSirinuListe(320); }
    razdelnik.addEventListener("keydown", function (e) {
      var w = Number(razdelnik.getAttribute("aria-valuenow")) || 320;
      if (e.key === "ArrowLeft") { e.preventDefault(); postaviSirinuListe(w - 16, true); }
      else if (e.key === "ArrowRight") { e.preventDefault(); postaviSirinuListe(w + 16, true); }
    });
    razdelnik.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      var levo = $("dok-lista-okvir").getBoundingClientRect().left;
      razdelnik.setPointerCapture(e.pointerId);
      function pomeri(ev) { postaviSirinuListe(ev.clientX - levo, true); }
      function pusti() { razdelnik.removeEventListener("pointermove", pomeri); razdelnik.removeEventListener("pointerup", pusti); }
      razdelnik.addEventListener("pointermove", pomeri);
      razdelnik.addEventListener("pointerup", pusti);
    });
    /* NS005 — Nov predmet: samo u LIVE, samo prijavljenom korisniku. */
    novPredmet = window.VxNovPredmet.napravi({ sesija: window.VxSesija, api: window.VxApi, naUspeh: function (id) {
      kontrolerLive.osvezi();
      location.hash = adresaPredmeta(id, "pregled");
    } });
    pretraga = window.VxPretraga.napravi({ sesija: window.VxSesija, api: window.VxApi, adresaPredmeta: adresaPredmeta });
    var uskladiNovLink = function () {
      var prijavljen = window.VxSesija.stanje().stanje === window.VxSesija.STANJA.PRIJAVLJEN;
      $("nov-predmet-link").hidden = !prijavljen;
      $("pretraga-link").hidden = !prijavljen;
    };
    window.VxSesija.naPromenu(uskladiNovLink);
    window.addEventListener("hashchange", primeniRutu);

    kontrolerLive.pokreni();
    if (window.__vxUskladiOdjavu) window.__vxUskladiOdjavu();
    uskladiNovLink();
    primeniRutu();
  } else {
    izvor = { stanje: "neispravna-konfiguracija", naslov: "Neispravna konfiguracija",
              tekst: (rt && rt.greska) || "Režim podataka nije učitan. Podaci se ne prikazuju." };
    osvezi();
    prikaziPanelNepovezan();
  }
})();
