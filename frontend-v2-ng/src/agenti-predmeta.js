/* Vindex V2 NG — savetnik (agent) na zahtev u predmetu, kroz čuvar citata (VCR001 T06, VCR002 T07).
 *
 * Ugovori (routers/multi_agent.py):
 *   GET  /api/agents/lista → {agenti:[{id, naziv, opis}]}   (zatvoren spisak; nudi se SAMO on)
 *   POST /api/agents/run {agent, task, predmet_id} → {odgovor, naziv, provera_citata, kontekst_predmeta}
 *        provera_citata.status: PROVERENI | NEPROVERENI | BEZ_CITATA | NEPOZNATO (pad provere — nikad „provereno“)
 *        Svaki citiran član je proveren protiv izvora iz pravne baze koje je savetnik dobio (kanonski čuvar,
 *        isti kao pravno pitanje); dokumenti predmeta nisu izvor za proveru zakona.
 *   VCR002 T05: POST /api/agents/run-parallel {task, predmet_id, agenti} → {rezultati:[{agent_id, stanje USPEH|NEUSPEH,
 *        odgovor, provera_citata}], kontekst_predmeta, uspesnih, neuspesnih}  — naplata po isporučenom odgovoru.
 *   VCR002 T06: POST /api/agents/pipeline {opis, pipeline, predmet_id} → {rezultati:[{korak, agent, stanje, output,
 *        provera_citata, naplacen}], kompletan, prekid, provera_citata_zavrsnog, kontekst_predmeta,
 *        potreban_pregled_advokata}  — izlaz koraka je nepoverljiv podatak za sledeći; završni nikad ne nasleđuje proveru.
 *   Nude se SAMO dve proverene kombinacije (ne proizvoljne). `Idempotency-Key` šalje api.send (mrežno ponavljanje = 1 izvršenje).
 *   `multi_agent` je profesionalna funkcija: 403 se saopštava, ne skriva; 402 = nema kredita, ništa nije pokrenuto.
 * Odgovor se prikazuje kao tekst (bez HTML-a). Generisanje se nikad ne ponavlja automatski (trošak).
 */
(function (root) {
  "use strict";

  var NAZIV = { intake: "Prijem i klasifikacija", research: "Pravno istraživanje", drafting: "Pisanje podnesaka",
                litigation: "Parnična strategija", billing: "Troškovi i naplata", deadline: "Rokovi" };
  var NACINI = {
    pojedinacno: { pomoc: "Jedan izabran savetnik. Naplaćuje se kao jedan poziv savetnika." },
    paralelno: { agenti: ["research", "litigation", "intake"], ruta: "/api/agents/run-parallel",
      naslov: "Tri pogleda istovremeno",
      pomoc: "Pravno istraživanje, parnična strategija i prijem rade istovremeno nad istim zadatkom. Naplaćuje se po jedan poziv za svakog savetnika koji odgovori; neuspeli se ne naplaćuju." },
    /* VCR002 RC FIX 2: niz je ISKLJUČEN. Pad radnika posle plaćenog koraka ostavlja plaćen rad nigde zabeležen,
     * a nova radnja ga ponovo naplaćuje (tests/test_vcr002_rc_fix2_niz_oporavak.py). Uključuje se tek kad postoji
     * trajna evidencija koraka i bezbedan oporavak — to traži novu šemu i posebno odobrenje. */
    niz: { iskljucen: true, agenti: ["research", "litigation", "drafting"], ruta: "/api/agents/pipeline",
      naslov: "Od istraživanja do nacrta",
      pomoc: "Istraživanje, zatim parnična strategija, zatim nacrt — svaki korak koristi prethodni kao nepoverljiv radni materijal. Svaki završen korak se naplaćuje kao jedan poziv; ako se niz prekine, završeni koraci ostaju vidljivi." },
  };
  var EMODZI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}]/gu;
  function tekst(v) { return String(v == null ? "" : v).trim(); }
  function cisto(t) { return String(t || "").replace(/\*\*/g, "").replace(EMODZI, "").trim(); }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api;
    var trenutni = null, katalog = null, gen = 0, k = null, kK = null, salje = false;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function poruka(id, st, t) { var n = $(id); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function nacin() { var v = $("ag-nacin").value; return NACINI.hasOwnProperty(v) ? v : "pojedinacno"; }
    function zakljucaj(da) {
      salje = da; $("ag-posalji").disabled = da || !katalog; $("ag-nacin").disabled = da;
      $("ag-posalji").textContent = da ? (nacin() === "pojedinacno" ? "Savetnik radi…" : "Savetnici rade…") : "Pokreni savetnika";
    }
    function ocistiOdgovor() {
      $("ag-odgovor").hidden = true; $("ag-odgovor-naslov").textContent = "";
      $("ag-citati").replaceChildren(); $("ag-tekst").replaceChildren(); poruka("ag-kontekst", null);
    }
    function ocisti() {
      gen++; if (k) k.abort(); if (kK) kK.abort(); k = null; kK = null;
      trenutni = null; zakljucaj(false);
      $("ag-forma").reset(); poruka("ag-stanje", null); ocistiOdgovor(); promeniNacin();
    }

    async function ucitajKatalog() {
      if (katalog) { zakljucaj(salje); return; }
      kK = new AbortController();
      var r = await api.get("/api/agents/lista", { token: sesija.token(), signal: kK.signal, oblik: function (x) { return Array.isArray(x.agenti); } });
      kK = null;
      if (!r.ok) { if (r.greska && r.greska.kod === "ABORTED") return; poruka("ag-stanje", "greska", "Spisak savetnika nije učitan. Savetnik trenutno nije dostupan."); return; }
      var lista = r.podaci.agenti.filter(function (a) { return a && NAZIV.hasOwnProperty(a.id); });
      if (!lista.length) { poruka("ag-stanje", "greska", "Nijedan savetnik nije dostupan."); return; }
      katalog = lista;
      var s = $("ag-agent"); s.replaceChildren();
      lista.forEach(function (a) { var op = el("option", null, NAZIV[a.id]); op.value = a.id; s.append(op); });
      /* Kombinovani načini se nude SAMO ako server nudi sve njihove savetnike. */
      Object.keys(NACINI).forEach(function (n) {
        var ag = NACINI[n].agenti; if (!ag) return;
        var op = $("ag-nacin").querySelector('option[value="' + n + '"]');
        if (op) op.disabled = !!NACINI[n].iskljucen || !ag.every(function (id) { return lista.some(function (a) { return a.id === id; }); });
      });
      opis(); promeniNacin(); zakljucaj(salje);
    }
    function opis() {
      var a = (katalog || []).filter(function (x) { return x.id === $("ag-agent").value; })[0];
      $("ag-agent-pomoc").textContent = a ? cisto(a.opis) : "";
    }
    function promeniNacin() {
      var n = nacin();
      $("ag-agent-polje").hidden = n !== "pojedinacno";
      $("ag-nacin-pomoc").textContent = NACINI[n].pomoc;
    }

    function prikaziCitate(p, ul, uvod) {
      ul = ul || $("ag-citati"); ul.replaceChildren(); uvod = uvod || "";
      function upozorenje(kljuc, naslov, telo, nivo) {
        var li = el("li", nivo === "ok" ? "warn warn--ok" : "warn"); li.dataset.kljuc = kljuc;
        li.append(el("p", "warn__title", uvod + naslov)); if (telo) li.append(telo); ul.append(li);
      }
      var st = p && tekst(p.status);
      if (st === "PROVERENI") { upozorenje("citati-provereni", "Svi citirani članovi (" + p.ukupno + ") potvrđeni su u izvorima iz pravne baze.", null, "ok"); return; }
      if (st === "BEZ_CITATA") { upozorenje("bez-citata", "Odgovor ne citira članove zakona.", null, "ok"); return; }
      if (st === "NEPROVERENI") {
        var n = (p.neprovereni || []).length;
        var lista = el("ul", "warn__list");
        (p.neprovereni || []).forEach(function (c) {
          lista.append(el("li", null, "Član " + tekst(c.clan) + (c.zakon ? " (" + tekst(c.zakon) + ")" : "") + (c.razlog ? " — " + tekst(c.razlog) : "")));
        });
        upozorenje("citati-neprovereni", n + (n === 1 ? " citiran član nije potvrđen" : " citiranih članova nije potvrđeno") + " u pravnoj bazi. Proverite u izvoru pre upotrebe.", lista);
        return;
      }
      upozorenje("citati-nepoznato", "Provera citata nije izvršena. Ne oslanjajte se na navedene članove bez provere u izvoru.", null);
    }
    function prikaziTekst(t, telo, nivo) {
      telo = telo || $("ag-tekst"); if (!nivo) telo.replaceChildren();
      var pasus = [], h = nivo || "h4";
      function zatvori() { var x = cisto(pasus.join("\n")); if (x) telo.append(el("p", "answer__p", x)); pasus = []; }
      String(t || "").replace(/\r\n/g, "\n").split("\n").forEach(function (r) {
        var m = /^\s*#{1,6}\s*(.*)$/.exec(r);
        if (m) { zatvori(); var x = cisto(m[1]); if (x) telo.append(el(h, "answer__h", x)); return; }
        if (!r.trim()) { zatvori(); return; }
        pasus.push(r);
      });
      zatvori();
    }
    /* QA-08: „predmet pročitan“ (kp) NIJE „dokumenti pročitani“. Šta je savetnik stvarno dobio javlja server
     * (`izvori_predmeta`); bez te evidencije se ne tvrdi da je savet zasnovan na dokumentima. */
    function oznake(lista) {
      var a = (Array.isArray(lista) ? lista : []).map(function (x) { return tekst(x && x.oznaka); }).filter(Boolean);
      return a.slice(0, 12).join(", ") + (a.length > 12 ? " i još " + (a.length - 12) : "");
    }
    function prikaziKontekst(kp, iz) {
      if (kp === false) { poruka("ag-kontekst", "nepoznato", "Podaci ovog predmeta NISU pročitani; savet je opšti."); return; }
      if (kp !== true) return;
      if (!iz || typeof iz !== "object") { poruka("ag-kontekst", "nepoznato", "Predmet je pročitan, ali nije utvrđeno koje je dokumente savetnik dobio."); return; }
      var uk = Array.isArray(iz.ukljuceni) ? iz.ukljuceni : [], n = iz.dokumenata_u_predmetu;
      var del = uk.filter(function (u) { return !u.potpun; });
      var t;
      if (iz.greska_citanja) t = "Dokumenti predmeta nisu (potpuno) pročitani zbog greške. Ne oslanjajte se na savet kao na pregled dokumenata.";
      else if (!n) t = "Predmet je pročitan, ali nema dokumenata; savet nije zasnovan na dokumentima.";
      else if (!uk.length) t = "Savetnik nije dobio tekst nijednog od " + n + " dokumenata predmeta.";
      else t = "Savetnik je dobio tekst " + uk.length + " od " + n + " dokumenata: " + oznake(uk) + "."
        + (del.length ? " Delimično (samo početak): " + oznake(del) + "." : "")
        + (iz.izostavljenih_ukupno ? " Ostali (" + iz.izostavljenih_ukupno + ") nisu pročitani u ovom odgovoru — za određeni dokument navedite njegov redni broj, npr. DOK-01." : "");
      var nisu = (Array.isArray(iz.trazeni_nisu_dostavljeni) ? iz.trazeni_nisu_dostavljeni : []).map(function (x) {
        return tekst(x.oznaka) + (x.razlog === "NE_POSTOJI" ? " ne postoji u ovom predmetu" : x.razlog === "BEZ_TEKSTA" ? " nema izdvojen tekst"
          : x.razlog === "OGRANICENJE" ? " nije dostavljen (ograničenje broja dokumenata)" : " nije pročitan (nije utvrđeno zašto)");
      });
      var visak = (Number(iz.trazenih_nedostavljenih_ukupno) || 0) - nisu.length;
      if (nisu.length) t += " Traženo, a NIJE pročitano: " + nisu.join("; ") + (visak > 0 ? " i još " + visak : "") + ".";
      var potpun = !iz.greska_citanja && n > 0 && iz.svi_dokumenti_u_celini === true && !nisu.length;
      poruka("ag-kontekst", potpun ? "uspeh" : "nepoznato", t);
    }
    function upozoriNedostavljene(lista, ime) {
      var oz = (Array.isArray(lista) ? lista : []).map(tekst).filter(Boolean);
      if (oz.length) upozorenjeVrh("nedostavljeni", (ime ? ime + ": " : "") + "odgovor pominje " + oz.join(", ")
        + ", čiji tekst savetnik nije dobio — te tvrdnje nisu proverene u izvoru.");
    }
    /* Jedan rezultat kombinovanog rada: naslov, stanje, SOPSTVENA provera citata, tekst. */
    function blokRezultata(agent, stanje, provera, odgovor, napomena) {
      var s = el("section", "ag-rez"); s.dataset.agent = agent; s.dataset.stanje = stanje;
      s.append(el("h4", "answer__h ag-rez__naslov", (NAZIV[agent] || "Savetnik") + (stanje === "USPEH" ? "" : " — nije uspeo")));
      if (stanje === "USPEH") {
        var ul = el("ul", "warns"); ul.setAttribute("aria-label", "Provera citata: " + (NAZIV[agent] || "savetnik"));
        s.append(ul); prikaziCitate(provera, ul);
        var telo = el("div", "ag-rez__telo"); s.append(telo); prikaziTekst(odgovor, telo, "h5");
      } else {
        s.append(el("p", "notice", napomena || "Ovaj savetnik nije odgovorio i nije naplaćen."));
      }
      $("ag-tekst").append(s);
    }
    function upozorenjeVrh(kljuc, naslov, nivo) {
      var li = el("li", nivo === "ok" ? "warn warn--ok" : "warn"); li.dataset.kljuc = kljuc;
      li.append(el("p", "warn__title", naslov)); $("ag-citati").append(li);
    }

    function prikaziParalelno(p) {
      var rez = Array.isArray(p.rezultati) ? p.rezultati : [];
      $("ag-odgovor-naslov").textContent = NACINI.paralelno.naslov;
      $("ag-citati").replaceChildren();
      var neusp = rez.filter(function (x) { return x.stanje !== "USPEH"; }).length;
      if (neusp) upozorenjeVrh("delimicno", "Odgovorilo je " + (rez.length - neusp) + " od " + rez.length + " savetnika. Savetnici koji nisu odgovorili nisu naplaćeni.");
      upozorenjeVrh("pregled", "Radni materijal: pre upotrebe ga mora pregledati advokat. Citati su provereni za svakog savetnika posebno.", "ok");
      prikaziKontekst(p.kontekst_predmeta, p.izvori_predmeta);
      rez.forEach(function (x) { if (x.stanje === "USPEH") upozoriNedostavljene(x.pominje_nedostavljene, NAZIV[x.agent_id]); });
      $("ag-tekst").replaceChildren();
      rez.forEach(function (x) { blokRezultata(x.agent_id, x.stanje === "USPEH" ? "USPEH" : "NEUSPEH", x.provera_citata, x.odgovor); });
    }
    function prikaziNiz(p) {
      var rez = Array.isArray(p.rezultati) ? p.rezultati : [];
      $("ag-odgovor-naslov").textContent = NACINI.niz.naslov;
      $("ag-citati").replaceChildren();
      if (!p.kompletan) {
        var kor = p.prekid && p.prekid.korak ? p.prekid.korak : rez.length;
        upozorenjeVrh("prekinut", "Niz je prekinut na koraku " + kor + ". Završeni koraci su prikazani i naplaćeni; prekinuti nije naplaćen.");
      }
      var zav = $("ag-citati"), li = el("li", "warn__grupa"); li.dataset.kljuc = "zavrsni";
      var ul = el("ul", "warns"); li.append(ul); zav.append(li);
      prikaziCitate(p.provera_citata_zavrsnog, ul, "Završni odgovor: ");
      upozorenjeVrh("pregled", "Radni materijal, ne pravni zaključak: pre upotrebe ga mora pregledati advokat. Provera citata ranijeg koraka ne važi za završni odgovor.", "ok");
      prikaziKontekst(p.kontekst_predmeta, p.izvori_predmeta);
      $("ag-tekst").replaceChildren();
      rez.forEach(function (x) {
        blokRezultata(x.agent, x.stanje === "USPEH" ? "USPEH" : "NEUSPEH", x.provera_citata, x.output,
          "Ovaj korak nije izvršen i nije naplaćen.");
      });
    }

    async function pokreni() {
      if (salje || !trenutni || !katalog) return;
      var n = nacin(), agent = $("ag-agent").value, zadatak = $("ag-zadatak").value.trim();
      var opcija = $("ag-nacin").querySelector('option[value="' + n + '"]');
      if (opcija && opcija.disabled) { poruka("ag-stanje", "greska", "Ovaj način rada trenutno nije dostupan."); return; }
      if (n === "pojedinacno" && (!NAZIV.hasOwnProperty(agent) || !katalog.some(function (a) { return a.id === agent; }))) { poruka("ag-stanje", "greska", "Izaberite savetnika sa spiska."); return; }
      if (zadatak.length < 10) { poruka("ag-stanje", "greska", "Opišite zadatak (bar 10 znakova)."); $("ag-zadatak").focus(); return; }
      var moja = ++gen, id = trenutni.id, korisnik = sesija.stanje().korisnik;
      k = new AbortController(); zakljucaj(true); ocistiOdgovor();
      var zahtev;
      if (n === "pojedinacno") {
        poruka("ag-stanje", "ucitavanje", "Savetnik radi i proverava citate… (do minut)");
        zahtev = { putanja: "/api/agents/run", telo: { agent: agent, task: zadatak.slice(0, 2000), predmet_id: id },
          oblik: function (x) { return typeof x.odgovor === "string" && x.odgovor.trim() !== ""; } };
      } else if (n === "paralelno") {
        poruka("ag-stanje", "ucitavanje", "Tri savetnika rade istovremeno i proveravaju citate… (do minut)");
        zahtev = { putanja: NACINI.paralelno.ruta, telo: { task: zadatak.slice(0, 2000), predmet_id: id, agenti: NACINI.paralelno.agenti.slice() },
          oblik: function (x) { return Array.isArray(x.rezultati) && x.rezultati.length > 0; } };
      } else {
        poruka("ag-stanje", "ucitavanje", "Savetnici rade jedan za drugim: istraživanje, strategija, nacrt… (do tri minuta)");
        zahtev = { putanja: NACINI.niz.ruta, telo: { opis: zadatak.slice(0, 2000), predmet_id: id, pipeline: NACINI.niz.agenti.slice() },
          oblik: function (x) { return Array.isArray(x.rezultati) && x.rezultati.length > 0; } };
      }
      var r = await api.send(zahtev.putanja, { telo: zahtev.telo, token: sesija.token(), signal: k.signal, oblik: zahtev.oblik });
      if (moja !== gen || !trenutni || trenutni.id !== id || sesija.stanje().korisnik !== korisnik) return;
      k = null; zakljucaj(false);
      if (r.ok && r.podaci) {
        poruka("ag-stanje", null);
        if (n === "pojedinacno") {
          $("ag-odgovor-naslov").textContent = "Savetnik: " + NAZIV[agent];
          prikaziCitate(r.podaci.provera_citata);
          prikaziKontekst(r.podaci.kontekst_predmeta, r.podaci.izvori_predmeta);
          upozoriNedostavljene(r.podaci.izvori_predmeta && r.podaci.izvori_predmeta.odgovor_pominje_nedostavljene);
          prikaziTekst(r.podaci.odgovor);
        } else if (n === "paralelno") {
          var p = r.podaci;
          if (!p.rezultati.some(function (x) { return x.stanje === "USPEH"; })) { poruka("ag-stanje", "greska", "Nijedan savetnik nije odgovorio. Ništa nije naplaćeno; pokušajte kasnije."); return; }
          prikaziParalelno(p);
        } else {
          prikaziNiz(r.podaci);
        }
        $("ag-odgovor").hidden = false;
        return;
      }
      if (r.ok) { poruka("ag-stanje", "nepoznato", "Savetnik je odgovorio, ali odgovor nije mogao da se pročita. Pokušajte ponovo."); return; }
      var g = r.greska || {};
      if (r.status === 402) { poruka("ag-stanje", "greska", "Nemate dovoljno kredita za ovaj način rada. Ništa nije pokrenuto ni naplaćeno."); return; }
      if (r.status === 503) { poruka("ag-stanje", "greska", "AI servis trenutno nije dostupan. Savet nije dobijen; pokušajte kasnije."); return; }
      if (g.ishodNepoznat) { poruka("ag-stanje", "nepoznato", "Odgovor nije dobijen: veza je prekinuta ili server nije odgovorio ispravno. Ne ponavljajte odmah — rad je možda naplaćen."); return; }
      poruka("ag-stanje", "greska", {
        FORBIDDEN: "Savetnik nije dostupan za vaš nalog (profesionalni paket) ili su krediti potrošeni.",
        RATE_LIMITED: "Previše zahteva u kratkom roku. Pokušajte ponovo malo kasnije.",
        AUTH_REQUIRED: "Prijava više nije važeća.",
        VALIDATION_ERROR: "Server nije prihvatio zahtev.",
      }[g.kod] || "Server je odbio zahtev. Savet nije dobijen.");
    }

    /* Spisak se čita tek kad je kartica pitanja otvorena (ugovor „cena“: otvaranje drugih kartica ne zove ništa više). */
    function postavi(predmet, aktivan) {
      if (trenutni && trenutni.id === predmet.id && trenutni.korisnik === sesija.stanje().korisnik) { if (aktivan) aktiviraj(); return; }
      ocisti();
      trenutni = { id: predmet.id, korisnik: sesija.stanje().korisnik, ucitano: false };
      if (aktivan) aktiviraj();
    }
    function aktiviraj() { if (!trenutni || trenutni.ucitano) return; trenutni.ucitano = true; ucitajKatalog(); }

    $("ag-forma").addEventListener("submit", function (e) { e.preventDefault(); pokreni(); });
    $("ag-agent").addEventListener("change", opis);
    $("ag-nacin").addEventListener("change", function () { promeniNacin(); poruka("ag-stanje", null); });
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) { katalog = null; ocisti(); } });

    return { postavi: postavi, aktiviraj: aktiviraj, ocisti: ocisti, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxAgentiPredmeta = Object.freeze({ napravi: napravi });
})(window);
