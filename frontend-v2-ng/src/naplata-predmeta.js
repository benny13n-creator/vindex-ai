/* Vindex V2 NG — naplata predmeta bez spoljnog slanja (NS005, Task 10).
 *
 * Ugovori (routers/billing.py, prefiks /billing):
 *   GET  /billing/entries?predmet_id → {entries[], ukupno_rsd, obracunato_rsd, neobracunato_rsd, ukupno_h}
 *        (samo stavke pozivaoca; pad baze → 5xx, nikad prazna lista)
 *   POST /billing/entries {predmet_id, opis, tip, tarifa_sifra?, iznos_rsd?, sati?, datum?} → {entry}
 *        Predmet mora biti pozivaočev (404). Uz tarifu bez iznosa iznos po AKS tarifi računa SERVER;
 *        uz same sate server primenjuje satnicu predmeta. Nepoznata tarifa → 400; bez osnova za iznos → 422.
 *   GET  /billing/tarifa → {tarifa:[{sifra, naziv, iznos_rsd, is_custom}], bod_rsd}
 *   GET  /billing/timer/aktivan → {aktivan, timer{predmet_id, start_at, opis}|null}
 *   POST /billing/timer/start {predmet_id, opis?} (404 tuđ predmet, 409 već radi)
 *   POST /billing/timer/stop {kreiraj_entry:true} → {trajanje_h, entry} — gasi JEDINI aktivni tajmer korisnika
 *   POST /billing/faktura {predmet_id, entry_ids, klijent_naziv, pdv_stopa, napomena?} → {faktura{broj_fakture, status:"nacrt"}}
 *        (samo sopstvene stavke tog predmeta; stavka već na fakturi → 409)
 *   GET  /billing/faktura?limit → {fakture[]} — sve fakture korisnika; ovde se filtrira po predmetu.
 * NE izlaže se: slanje fakture mejlom, SEF, promena statusa fakture, PDF, brisanje stavke.
 * Upisi se nikad ne ponavljaju automatski; prekid posle slanja = ishod nepoznat (lista se ponovo čita).
 */
(function (root) {
  "use strict";

  var LIMIT_FAKTURA = 200;
  var STATUS_FAKTURE = { nacrt: "nacrt", izdata: "izdata", placena: "plaćena", stornirana: "stornirana" };
  var novac = new Intl.NumberFormat("sr-Latn-RS", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  var satiF = new Intl.NumberFormat("sr-Latn-RS", { maximumFractionDigits: 2 });
  function tekst(v) { return String(v == null ? "" : v).trim(); }
  function datum(iso) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(tekst(iso)); return m ? m[3] + "." + m[2] + "." + m[1] + "." : ""; }
  function vreme(iso) { var t = Date.parse(tekst(iso)); if (!Number.isFinite(t)) return ""; var x = new Date(t); return String(x.getHours()).padStart(2, "0") + ":" + String(x.getMinutes()).padStart(2, "0"); }
  function broj(v) { var n = typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : NaN; return Number.isFinite(n) ? n : null; }
  function rsd(v) { var n = broj(v); return n === null ? "—" : novac.format(n) + " RSD"; }
  function ispravanId(v) { return /^[A-Za-z0-9_-]{1,64}$/.test(tekst(v)); }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api, adresaPredmeta = o.adresaPredmeta;
    var trenutni = null, tarife = null, stavke = null;
    var genS = 0, genTf = 0, genTm = 0, genF = 0, kS = null, kTf = null, kTm = null, kF = null;
    var saljeS = false, saljeT = false, saljeF = false, tajmer = null;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function poruka(id, st, t) { var n = $(id); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function prekini(x) { if (x) x.abort(); return null; }
    function istiPredmet(id, korisnik) { return !!trenutni && trenutni.id === id && sesija.stanje().korisnik === korisnik; }
    function prijavljen() { var s = sesija.stanje(); return s.stanje === sesija.STANJA.PRIJAVLJEN && !!trenutni && s.korisnik === trenutni.korisnik; }
    function greskaUpisa(g, nista) {
      return {
        BAD_REQUEST: "Server nije prihvatio zahtev. " + nista,
        VALIDATION_ERROR: "Server nije prihvatio unete podatke. " + nista,
        NOT_FOUND: "Predmet nije dostupan. " + nista,
        FORBIDDEN: "Naplata nije dostupna za vaš nalog. " + nista,
        RATE_LIMITED: "Previše zahteva u kratkom roku. Pokušajte ponovo malo kasnije. " + nista,
        AUTH_REQUIRED: "Prijava više nije važeća. " + nista,
      }[g.kod] || "Server je odbio zahtev. " + nista;
    }

    function zakljucajStavku(da) { saljeS = da; $("np-dodaj").disabled = da; $("np-dodaj").textContent = da ? "Upisivanje…" : "Upiši stavku"; }
    function zakljucajFakturu(da) { saljeF = da; azurirajFakturu(); $("np-faktura-dugme").textContent = da ? "Pravljenje nacrta…" : "Napravi nacrt fakture"; }
    function izabrane() { return Array.prototype.map.call(d.querySelectorAll("#np-stavke input[data-stavka]:checked"), function (c) { return c.dataset.stavka; }); }
    function azurirajFakturu() {
      var n = stavke ? izabrane().length : 0;
      $("np-faktura-dugme").disabled = saljeF || !stavke || n === 0;
      $("np-izabrano").textContent = !stavke ? "" : n === 0 ? "Nijedna stavka nije označena." : "Označeno stavki: " + n + ".";
    }

    function ocisti() {
      genS++; genTf++; genTm++; genF++; kS = prekini(kS); kTf = prekini(kTf); kTm = prekini(kTm); kF = prekini(kF);
      trenutni = null; stavke = null; tajmer = null;
      zakljucajStavku(false); saljeT = false; saljeF = false;
      $("np-forma").reset(); $("np-faktura-forma").reset(); $("np-tajmer-opis").value = "";
      $("np-zbir").replaceChildren(); $("np-zbir").hidden = true;
      $("np-stavke").replaceChildren(); $("np-tabela").hidden = true;
      $("np-fakture").replaceChildren();
      ["np-stavke-stanje", "np-poruka", "np-tajmer-stanje", "np-tajmer-poruka", "np-faktura-poruka", "np-fakture-stanje"].forEach(function (id) { poruka(id, null); });
      $("np-tajmer-drugi").hidden = true; $("np-tajmer-drugi").removeAttribute("href");
      $("np-tajmer-start").hidden = false; $("np-tajmer-start").disabled = true; $("np-tajmer-stop").hidden = true;
      zakljucajFakturu(false);
    }

    /* ── Stavke ── */
    async function ucitajStavke() {
      if (!trenutni) return;
      var moja = ++genS, id = trenutni.id, korisnik = trenutni.korisnik; kS = prekini(kS); kS = new AbortController();
      stavke = null; azurirajFakturu();
      poruka("np-stavke-stanje", "ucitavanje", "Učitavanje stavki naplate…");
      var r = await api.get("/billing/entries", { token: sesija.token(), signal: kS.signal, parametri: { predmet_id: id },
        oblik: function (x) { return Array.isArray(x.entries) && typeof x.ukupno_rsd === "number"; } });
      if (moja !== genS || !istiPredmet(id, korisnik)) return;
      kS = null;
      $("np-stavke").replaceChildren(); $("np-zbir").replaceChildren(); $("np-tabela").hidden = true; $("np-zbir").hidden = true;
      if (!r.ok) { if (r.greska && r.greska.kod === "ABORTED") return; poruka("np-stavke-stanje", "greska", "Stavke naplate nisu učitane zbog greške. Ovo nije prazna lista; faktura se ne može napraviti dok se ne učitaju."); return; }
      var x = r.podaci;
      stavke = x.entries.filter(function (e) { return e && ispravanId(e.id); });
      var zbir = $("np-zbir");
      [["Ukupno", rsd(x.ukupno_rsd)], ["Nije fakturisano", rsd(x.neobracunato_rsd)], ["Na fakturama", rsd(x.obracunato_rsd)],
       ["Evidentirano sati", broj(x.ukupno_h) === null ? "—" : satiF.format(broj(x.ukupno_h))]].forEach(function (p) { zbir.append(el("dt", null, p[0]), el("dd", null, p[1])); });
      zbir.hidden = false;
      if (!stavke.length) { poruka("np-stavke-stanje", "prazno", "Za ovaj predmet još nema stavki naplate."); azurirajFakturu(); return; }
      poruka("np-stavke-stanje", null);
      stavke.forEach(function (e) {
        var tr = el("tr"), naFakturi = e.obracunato === true;
        var c0 = el("td", "ledger__pick");
        if (!naFakturi) {
          var cb = el("input"); cb.type = "checkbox"; cb.dataset.stavka = String(e.id);
          cb.setAttribute("aria-label", "Na fakturu: " + (tekst(e.opis) || "stavka"));
          cb.addEventListener("change", azurirajFakturu);
          c0.append(cb);
        }
        tr.append(c0, el("td", "ledger__date", datum(e.datum) || "—"), el("td", "ledger__desc", tekst(e.opis) || "—"),
          el("td", null, tekst(e.tarifa_sifra) || "—"), el("td", "ledger__num", broj(e.sati) === null ? "—" : satiF.format(broj(e.sati))),
          el("td", "ledger__num", rsd(e.iznos_rsd)), el("td", "ledger__state", naFakturi ? "na fakturi" : "nije fakturisano"));
        $("np-stavke").append(tr);
      });
      $("np-tabela").hidden = false;
      azurirajFakturu();
    }

    async function ucitajTarife() {
      if (tarife) return;
      var moja = ++genTf; kTf = prekini(kTf); kTf = new AbortController();
      var sel = $("np-tarifa"); sel.disabled = true;
      var r = await api.get("/billing/tarifa", { token: sesija.token(), signal: kTf.signal, oblik: function (x) { return Array.isArray(x.tarifa); } });
      if (moja !== genTf) return;
      kTf = null;
      sel.replaceChildren(el("option", null, "Bez tarife (unosite iznos ili sate)")); sel.firstChild.value = "";
      if (!r.ok) { if (r.greska && r.greska.kod === "ABORTED") return; poruka("np-poruka", "greska", "Tarifa nije učitana. Stavku možete upisati sa iznosom ili satima."); return; }
      tarife = r.podaci.tarifa.filter(function (t) { return t && /^[A-Za-z0-9_-]{1,16}$/.test(tekst(t.sifra)) && tekst(t.naziv); });
      tarife.forEach(function (t) {
        var op = el("option", null, tekst(t.sifra) + " — " + tekst(t.naziv) + (broj(t.iznos_rsd) !== null ? " (" + rsd(t.iznos_rsd) + ")" : ""));
        op.value = tekst(t.sifra); sel.append(op);
      });
      sel.disabled = false;
    }

    async function dodajStavku() {
      if (saljeS || !trenutni) return;
      var opis = $("np-opis").value.trim(), sifra = $("np-tarifa").value, iznosT = $("np-iznos").value.trim(), satiT = $("np-sati").value.trim(), dat = $("np-datum").value;
      if (!opis) { poruka("np-poruka", "greska", "Unesite opis radnje."); $("np-opis").focus(); return; }
      var iznos = iznosT === "" ? null : broj(iznosT.replace(",", ".")), sati = satiT === "" ? null : broj(satiT.replace(",", "."));
      if (iznosT !== "" && (iznos === null || iznos < 0)) { poruka("np-poruka", "greska", "Iznos mora biti broj veći ili jednak nuli."); $("np-iznos").focus(); return; }
      if (satiT !== "" && (sati === null || sati <= 0 || sati > 24)) { poruka("np-poruka", "greska", "Sati moraju biti broj veći od nule (najviše 24)."); $("np-sati").focus(); return; }
      if (sifra && !(tarife || []).some(function (t) { return t.sifra === sifra; })) { poruka("np-poruka", "greska", "Izaberite tarifu sa spiska."); return; }
      if (!sifra && iznos === null && sati === null) { poruka("np-poruka", "greska", "Izaberite tarifu, unesite iznos ili unesite sate."); $("np-tarifa").focus(); return; }
      if (dat && !/^\d{4}-\d{2}-\d{2}$/.test(dat)) { poruka("np-poruka", "greska", "Datum nije ispravan."); return; }
      if (!prijavljen()) { poruka("np-poruka", "greska", "Niste prijavljeni. Stavka nije upisana."); return; }
      var telo = { predmet_id: trenutni.id, opis: opis.slice(0, 400), tip: sifra ? "tarifa" : iznos === null ? "satnica" : "ostalo" };
      if (sifra) telo.tarifa_sifra = sifra;
      if (iznos !== null) telo.iznos_rsd = iznos;
      if (sati !== null) telo.sati = sati;
      if (dat) telo.datum = dat;
      var id = trenutni.id, korisnik = trenutni.korisnik, serverRacuna = iznos === null;
      zakljucajStavku(true); poruka("np-poruka", "ucitavanje", "Upisivanje stavke…");
      var r = await api.send("/billing/entries", { telo: telo, token: sesija.token(), oblik: function (x) { return !!x.entry && typeof x.entry === "object"; } });
      if (!istiPredmet(id, korisnik)) return;
      zakljucajStavku(false);
      if (r.ok) {
        $("np-forma").reset();
        poruka("np-poruka", "uspeh", r.podaci ? "Stavka je upisana: " + rsd(r.podaci.entry.iznos_rsd) + (serverRacuna ? " (iznos je izračunao server)." : ".") : "Stavka je upisana, ali odgovor nije mogao da se pročita. Proverite listu.");
        ucitajStavke();
        return;
      }
      var g = r.greska || {};
      if (g.ishodNepoznat) { poruka("np-poruka", "nepoznato", "Ishod nije poznat: veza je prekinuta ili server nije odgovorio ispravno. Lista se ponovo učitava — proverite da li je stavka upisana pre ponovnog pokušaja."); ucitajStavke(); return; }
      poruka("np-poruka", "greska", greskaUpisa(g, "Stavka nije upisana."));
    }

    /* ── Tajmer ── */
    function prikaziTajmer() {
      var t = tajmer, start = $("np-tajmer-start"), stop = $("np-tajmer-stop"), drugi = $("np-tajmer-drugi");
      drugi.hidden = true; drugi.removeAttribute("href");
      if (!t) { start.hidden = false; start.disabled = true; stop.hidden = true; return; }
      if (!t.aktivan) { poruka("np-tajmer-stanje", "prazno", "Tajmer nije pokrenut."); start.hidden = false; start.disabled = saljeT; stop.hidden = true; return; }
      var kada = vreme(t.start_at), dan = datum(t.start_at);
      if (t.predmet_id === trenutni.id) {
        poruka("np-tajmer-stanje", "aktivan", "Tajmer radi za ovaj predmet" + (kada ? " od " + kada + (dan ? " (" + dan + ")" : "") : "") + (t.opis ? " — " + t.opis : "") + ".");
        start.hidden = true; stop.hidden = false; stop.disabled = saljeT; return;
      }
      poruka("np-tajmer-stanje", "aktivan", "Tajmer već radi na drugom vašem predmetu" + (kada ? " od " + kada : "") + ". Zaustavite ga tamo pre pokretanja novog.");
      if (ispravanId(t.predmet_id)) { drugi.href = adresaPredmeta(t.predmet_id, "naplata"); drugi.hidden = false; }
      start.hidden = false; start.disabled = true; stop.hidden = true;
    }
    async function ucitajTajmer() {
      if (!trenutni) return;
      var moja = ++genTm, id = trenutni.id, korisnik = trenutni.korisnik; kTm = prekini(kTm); kTm = new AbortController();
      tajmer = null; prikaziTajmer();
      poruka("np-tajmer-stanje", "ucitavanje", "Učitavanje stanja tajmera…");
      var r = await api.get("/billing/timer/aktivan", { token: sesija.token(), signal: kTm.signal,
        oblik: function (x) { return typeof x.aktivan === "boolean" && (!x.aktivan || (!!x.timer && typeof x.timer === "object")); } });
      if (moja !== genTm || !istiPredmet(id, korisnik)) return;
      kTm = null;
      if (!r.ok) { if (r.greska && r.greska.kod === "ABORTED") return; poruka("np-tajmer-stanje", "greska", "Stanje tajmera nije učitano. Tajmer se ne može pokrenuti ni zaustaviti dok se ne učita."); return; }
      tajmer = r.podaci.aktivan ? { aktivan: true, predmet_id: tekst(r.podaci.timer.predmet_id), start_at: r.podaci.timer.start_at, opis: tekst(r.podaci.timer.opis) } : { aktivan: false };
      prikaziTajmer();
    }
    async function tajmerRadnja(vrsta) {
      if (saljeT || !trenutni || !tajmer) return;
      if (!prijavljen()) { poruka("np-tajmer-poruka", "greska", "Niste prijavljeni. Ništa nije promenjeno."); return; }
      var id = trenutni.id, korisnik = trenutni.korisnik, telo;
      if (vrsta === "start") { telo = { predmet_id: id }; var op = $("np-tajmer-opis").value.trim(); if (op) telo.opis = op.slice(0, 200); }
      else { if (!tajmer.aktivan || tajmer.predmet_id !== id) return; telo = { kreiraj_entry: true }; }
      saljeT = true; $("np-tajmer-start").disabled = true; $("np-tajmer-stop").disabled = true;
      poruka("np-tajmer-poruka", "ucitavanje", vrsta === "start" ? "Pokretanje tajmera…" : "Zaustavljanje tajmera…");
      var r = await api.send("/billing/timer/" + vrsta, { telo: telo, token: sesija.token(),
        oblik: function (x) { return x.success === true; } });
      if (!istiPredmet(id, korisnik)) return;
      saljeT = false;
      if (r.ok) {
        if (vrsta === "start") { $("np-tajmer-opis").value = ""; poruka("np-tajmer-poruka", "uspeh", "Tajmer je pokrenut."); }
        else {
          var e = r.podaci && r.podaci.entry;
          poruka("np-tajmer-poruka", "uspeh", e ? "Tajmer je zaustavljen i upisana je stavka: " + satiF.format(broj(e.sati) || 0) + " h, " + rsd(e.iznos_rsd) + "." : "Tajmer je zaustavljen. Proverite listu stavki.");
          ucitajStavke();
        }
        ucitajTajmer();
        return;
      }
      var g = r.greska || {};
      if (g.ishodNepoznat) { poruka("np-tajmer-poruka", "nepoznato", "Ishod nije poznat. Stanje tajmera i lista stavki se ponovo učitavaju — proverite ih pre ponovnog pokušaja."); ucitajTajmer(); ucitajStavke(); return; }
      if (g.kod === "CONFLICT") { poruka("np-tajmer-poruka", "greska", "Tajmer već radi. Ništa nije promenjeno."); ucitajTajmer(); return; }
      if (g.kod === "NOT_FOUND" && vrsta === "stop") { poruka("np-tajmer-poruka", "greska", "Nema aktivnog tajmera. Ništa nije upisano."); ucitajTajmer(); return; }
      poruka("np-tajmer-poruka", "greska", greskaUpisa(g, "Ništa nije promenjeno."));
      prikaziTajmer();
    }

    /* ── Fakture ── */
    async function ucitajFakture() {
      if (!trenutni) return;
      var moja = ++genF, id = trenutni.id, korisnik = trenutni.korisnik; kF = prekini(kF); kF = new AbortController();
      $("np-fakture").replaceChildren();
      poruka("np-fakture-stanje", "ucitavanje", "Učitavanje faktura…");
      var r = await api.get("/billing/faktura", { token: sesija.token(), signal: kF.signal, parametri: { limit: LIMIT_FAKTURA }, oblik: function (x) { return Array.isArray(x.fakture); } });
      if (moja !== genF || !istiPredmet(id, korisnik)) return;
      kF = null;
      if (!r.ok) { if (r.greska && r.greska.kod === "ABORTED") return; poruka("np-fakture-stanje", "greska", "Fakture nisu učitane zbog greške. Ovo nije prazna lista."); return; }
      var sve = r.podaci.fakture, ove = sve.filter(function (f) { return f && tekst(f.predmet_id) === id; });
      var dopuna = sve.length >= LIMIT_FAKTURA ? " Prikazano je poslednjih " + LIMIT_FAKTURA + " faktura vašeg naloga; starije fakture ovog predmeta možda nisu na spisku." : "";
      if (!ove.length) { poruka("np-fakture-stanje", "prazno", "Za ovaj predmet nema faktura." + dopuna); return; }
      poruka("np-fakture-stanje", dopuna ? "nepotpuno" : null, dopuna.trim());
      ove.forEach(function (f) {
        var li = el("li", "review");
        li.append(el("span", "review__name", (f.is_proforma ? "Predračun " : "Faktura ") + (tekst(f.broj_fakture) || "bez broja") + (tekst(f.klijent_naziv) ? " — " + tekst(f.klijent_naziv) : "")));
        li.append(el("span", "review__meta", [rsd(f.iznos_sa_pdv), STATUS_FAKTURE[tekst(f.status)] || tekst(f.status), datum(f.datum_dospeca) ? "dospeva " + datum(f.datum_dospeca) : ""].filter(Boolean).join(" · ")));
        $("np-fakture").append(li);
      });
    }

    async function napraviFakturu() {
      if (saljeF || !trenutni || !stavke) return;
      var ids = izabrane(), klijent = $("np-klijent").value.trim(), pdv = Number($("np-pdv").value), nap = $("np-napomena").value.trim();
      if (!ids.length) { poruka("np-faktura-poruka", "greska", "Označite bar jednu nefakturisanu stavku."); return; }
      if (!klijent) { poruka("np-faktura-poruka", "greska", "Unesite naziv klijenta kome se faktura izdaje."); $("np-klijent").focus(); return; }
      if (pdv !== 0 && pdv !== 20) { poruka("np-faktura-poruka", "greska", "Izaberite stopu PDV-a sa spiska."); return; }
      if (!prijavljen()) { poruka("np-faktura-poruka", "greska", "Niste prijavljeni. Faktura nije napravljena."); return; }
      var telo = { predmet_id: trenutni.id, entry_ids: ids, klijent_naziv: klijent.slice(0, 300), pdv_stopa: pdv };
      if (nap) telo.napomena = nap.slice(0, 1000);
      var id = trenutni.id, korisnik = trenutni.korisnik;
      zakljucajFakturu(true); poruka("np-faktura-poruka", "ucitavanje", "Pravljenje nacrta fakture…");
      var r = await api.send("/billing/faktura", { telo: telo, token: sesija.token(), oblik: function (x) { return !!x.faktura && typeof x.faktura === "object"; } });
      if (!istiPredmet(id, korisnik)) return;
      zakljucajFakturu(false);
      if (r.ok) {
        var f = r.podaci && r.podaci.faktura;
        $("np-faktura-forma").reset();
        poruka("np-faktura-poruka", "uspeh", (f ? "Napravljen je nacrt fakture br. " + (tekst(f.broj_fakture) || "—") + " na " + rsd(f.iznos_sa_pdv) + "." : "Nacrt fakture je napravljen, ali odgovor nije mogao da se pročita.")
          + " Faktura nije izdata, nije poslata klijentu i nije prijavljena u SEF.");
        ucitajStavke(); ucitajFakture();
        return;
      }
      var g = r.greska || {};
      if (g.ishodNepoznat) { poruka("np-faktura-poruka", "nepoznato", "Ishod nije poznat. Stavke i fakture se ponovo učitavaju — proverite da li je nacrt napravljen pre ponovnog pokušaja."); ucitajStavke(); ucitajFakture(); return; }
      if (g.kod === "CONFLICT") { poruka("np-faktura-poruka", "greska", "Neke stavke su u međuvremenu već na fakturi. Faktura nije napravljena; lista se ponovo učitava."); ucitajStavke(); return; }
      poruka("np-faktura-poruka", "greska", g.kod === "BAD_REQUEST" ? "Neke stavke ne pripadaju ovom predmetu. Faktura nije napravljena." : greskaUpisa(g, "Faktura nije napravljena."));
    }

    function postavi(predmet, aktivan) {
      if (trenutni && trenutni.id === predmet.id && trenutni.korisnik === sesija.stanje().korisnik) { if (aktivan) aktiviraj(); return; }
      ocisti();
      trenutni = { id: predmet.id, korisnik: sesija.stanje().korisnik, ucitano: false };
      if (aktivan) aktiviraj();
    }
    function aktiviraj() {
      if (!trenutni || trenutni.ucitano) return;
      trenutni.ucitano = true;
      ucitajTarife(); ucitajStavke(); ucitajTajmer(); ucitajFakture();
    }

    $("np-forma").addEventListener("submit", function (e) { e.preventDefault(); dodajStavku(); });
    $("np-faktura-forma").addEventListener("submit", function (e) { e.preventDefault(); napraviFakturu(); });
    $("np-tajmer-forma").addEventListener("submit", function (e) { e.preventDefault(); });
    $("np-tajmer-start").addEventListener("click", function () { tajmerRadnja("start"); });
    $("np-tajmer-stop").addEventListener("click", function () { tajmerRadnja("stop"); });
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) { tarife = null; $("np-tarifa").replaceChildren(); ocisti(); } });

    return { postavi: postavi, aktiviraj: aktiviraj, ocisti: ocisti, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxNaplataPredmeta = Object.freeze({ napravi: napravi });
})(window);
