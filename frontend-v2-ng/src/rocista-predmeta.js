/* Vindex V2 NG — ročišta predmeta (NS005, CAP-074).
 *
 * Ugovori (routers/rocista.py):
 *   GET  /api/rocista?predmet_id=  → {rocista, ukupno}  (samo pozivaočeva; po datumu)
 *   POST /api/rocista {predmet_id, sud, datum YYYY-MM-DD, vreme HH:MM?, sudnica?,
 *                      broj_predmeta_suda?, napomena?} → {rociste}
 *        server proverava da je predmet pozivaočev (inače 404); isto ročište u 30 s
 *        se ne duplira. Status novog ročišta je uvek „zakazano".
 * Izmena statusa i brisanje ročišta NISU deo ovog zadatka. Podsetnici se ne šalju.
 * Neuspelo čitanje liste NIJE „nema ročišta".
 */
(function (root) {
  "use strict";

  var STATUS = { zakazano: "zakazano", odrzano: "održano", odlozeno: "odloženo", otkazano: "otkazano" };
  function datum(iso) { var p = String(iso || "").slice(0, 10).split("-"); return p.length === 3 ? p[2] + "." + p[1] + "." + p[0] + "." : String(iso || ""); }
  function tekst(v) { return typeof v === "string" ? v.trim() : ""; }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api;
    var trenutni = null, genListe = 0, genUpisa = 0, kListe = null, kUpisa = null, salje = false, ucitano = false;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function poruka(stanje, t) { var n = $("roc-poruka"); if (!stanje) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = stanje; n.textContent = t; }
    function stanjeListe(t, oznaka) { var s = $("roc-stanje"); s.hidden = !t; s.textContent = t || ""; if (oznaka) s.dataset.stanje = oznaka; else delete s.dataset.stanje; }
    function zakljucaj(da) { salje = da; $("roc-sacuvaj").disabled = da; $("roc-sacuvaj").textContent = da ? "Zakazivanje…" : "Zakaži ročište"; }

    function ocisti() {
      genListe++; genUpisa++;
      if (kListe) { kListe.abort(); kListe = null; }
      if (kUpisa) { kUpisa.abort(); kUpisa = null; }
      trenutni = null; ucitano = false;
      zakljucaj(false);
      $("roc-lista").replaceChildren(); stanjeListe(null); poruka(null);
      $("roc-forma").reset(); $("roc-forma").hidden = true; $("roc-otvori").hidden = true;
    }

    async function ucitaj(porukaPosle) {
      if (!trenutni) return;
      genListe++;
      if (kListe) kListe.abort();
      var moja = genListe, id = trenutni.id, korisnik = trenutni.korisnik;
      kListe = new AbortController();
      $("roc-lista").replaceChildren();
      stanjeListe("Učitavanje ročišta…", "ucitavanje");
      var r = await api.get("/api/rocista", { token: sesija.token(), signal: kListe.signal, parametri: { predmet_id: id, limit: 100 },
        oblik: function (x) { return Array.isArray(x.rocista); } });
      if (moja !== genListe || !trenutni || trenutni.id !== id || trenutni.korisnik !== korisnik) return;
      kListe = null;
      if (!r.ok) {
        if (r.greska && r.greska.kod === "ABORTED") return;
        stanjeListe("Ročišta nisu učitana zbog greške. Ovo nije prazna lista.", "greska");
        return;
      }
      /* Server filtrira po vlasniku i predmetu; red drugog predmeta je neispravan odgovor. */
      var lista = r.podaci.rocista.filter(function (x) { return x && typeof x === "object"; });
      if (lista.some(function (x) { return x.predmet_id !== undefined && String(x.predmet_id) !== id; })) {
        stanjeListe("Odgovor servera nije ispravan. Ročišta se ne prikazuju.", "greska");
        return;
      }
      if (!lista.length) stanjeListe("Za predmet nije zakazano nijedno ročište.", "prazno");
      else stanjeListe(null);
      lista.forEach(function (x) {
        var li = el("li", "hearing");
        var kad = el("time", "hearing__when", datum(x.datum) + (tekst(x.vreme) ? " u " + tekst(x.vreme).slice(0, 5) : ""));
        if (/^\d{4}-\d{2}-\d{2}/.test(tekst(x.datum))) kad.dateTime = tekst(x.datum).slice(0, 10);
        li.append(kad);
        li.append(el("span", "hearing__court", tekst(x.sud) || "Sud nije naveden"));
        var meta = [tekst(x.sudnica) ? "sudnica " + tekst(x.sudnica) : "", tekst(x.broj_predmeta_suda), STATUS[tekst(x.status)] || tekst(x.status)].filter(Boolean).join(" · ");
        if (meta) li.append(el("span", "hearing__meta", meta));
        if (tekst(x.napomena)) li.append(el("span", "hearing__note", tekst(x.napomena)));
        $("roc-lista").append(li);
      });
      if (porukaPosle) poruka("uspeh", porukaPosle);
    }

    /* Lista se čita tek kada je odeljak „Rad na predmetu" otvoren (aktiviraj):
     * pregled i dokumenti ne izazivaju dodatni zahtev. */
    function postavi(predmet, aktivan) {
      ocisti();
      trenutni = { id: predmet.id, korisnik: sesija.stanje().korisnik };
      $("roc-otvori").hidden = false;
      if (aktivan) aktiviraj();
    }
    function aktiviraj() {
      if (!trenutni || ucitano) return;
      ucitano = true;
      ucitaj();
    }

    async function zakazi() {
      if (salje || !trenutni) return;
      var s = sesija.stanje();
      if (s.stanje !== sesija.STANJA.PRIJAVLJEN || s.korisnik !== trenutni.korisnik) { poruka("greska", "Niste prijavljeni. Ročište nije zakazano."); return; }
      ["roc-sud", "roc-datum", "roc-vreme"].forEach(function (x) { $(x).removeAttribute("aria-invalid"); });
      var sud = $("roc-sud").value.trim(), dat = $("roc-datum").value.trim(), vreme = $("roc-vreme").value.trim();
      if (!sud) { $("roc-sud").setAttribute("aria-invalid", "true"); poruka("greska", "Unesite sud."); $("roc-sud").focus(); return; }
      if (!/^\d{4}-\d{2}-\d{2}$/.test(dat)) { $("roc-datum").setAttribute("aria-invalid", "true"); poruka("greska", "Unesite datum ročišta."); $("roc-datum").focus(); return; }
      if (vreme && !/^\d{2}:\d{2}$/.test(vreme)) { $("roc-vreme").setAttribute("aria-invalid", "true"); poruka("greska", "Vreme mora biti u obliku ČČ:MM."); $("roc-vreme").focus(); return; }
      var telo = { predmet_id: trenutni.id, sud: sud.slice(0, 300), datum: dat };
      if (vreme) telo.vreme = vreme;
      [["sudnica", "roc-sudnica", 100], ["broj_predmeta_suda", "roc-broj", 100], ["napomena", "roc-napomena", 2000]].forEach(function (f) {
        var v = $(f[1]).value.trim(); if (v) telo[f[0]] = v.slice(0, f[2]);
      });
      var moja = ++genUpisa, id = trenutni.id, korisnik = trenutni.korisnik;
      kUpisa = new AbortController();
      zakljucaj(true);
      poruka("ucitavanje", "Ročište se zakazuje…");
      var r = await api.send("/api/rocista", { telo: telo, token: sesija.token(), signal: kUpisa.signal,
        oblik: function (x) { return x.rociste && typeof x.rociste === "object"; } });
      if (moja !== genUpisa || !trenutni || trenutni.id !== id || trenutni.korisnik !== korisnik) return;
      kUpisa = null;
      zakljucaj(false);
      if (r.ok) {
        $("roc-forma").reset(); $("roc-forma").hidden = true; $("roc-otvori").hidden = false;
        poruka(null);
        ucitaj(r.podaci ? "Ročište je zakazano." : "Ročište je verovatno zakazano, ali odgovor nije mogao da se pročita. Proverite listu.");
        return;
      }
      var g = r.greska || {};
      if (g.ishodNepoznat) { poruka("nepoznato", "Ishod nije poznat: ročište je možda zakazano. Osvežite predmet i proverite listu pre ponovnog pokušaja."); return; }
      poruka("greska", { NOT_FOUND: "Predmet nije dostupan. Ročište nije zakazano.", VALIDATION_ERROR: "Server nije prihvatio podatke (proverite datum i vreme). Ročište nije zakazano.",
        AUTH_REQUIRED: "Prijava više nije važeća. Ročište nije zakazano.", RATE_LIMITED: "Previše zahteva. Ročište nije zakazano." }[g.kod] || "Server je odbio zahtev. Ročište nije zakazano.");
    }

    $("roc-otvori").addEventListener("click", function () { if (!trenutni) return; poruka(null); $("roc-forma").hidden = false; $("roc-otvori").hidden = true; $("roc-sud").focus(); });
    $("roc-odustani").addEventListener("click", function () { if (salje) return; $("roc-forma").reset(); $("roc-forma").hidden = true; $("roc-otvori").hidden = !trenutni; poruka(null); });
    $("roc-forma").addEventListener("submit", function (e) { e.preventDefault(); zakazi(); });
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) ocisti(); });

    return { postavi: postavi, aktiviraj: aktiviraj, ocisti: ocisti, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxRocistaPredmeta = Object.freeze({ napravi: napravi });
})(window);
