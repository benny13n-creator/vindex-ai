# -*- coding: utf-8 -*-
"""Merenje efektivne veličine VIDLJIVOG teksta u legacy interfejsu (Chromium, Playwright).

Pokreće ga tests/test_faza1_izvor_pod.py kao zaseban proces (interpreter sa Playwright-om) i
čita JSON sa stdout-a. Izlaz 3 = Playwright/Chromium nije dostupan, 2 = scenario se nije učitao.

  font_pod_merenje.py scenariji <tema> <ekran>   -> {"scenariji": [[kontekst, {izmereno, ispod}], ...]}
  font_pod_merenje.py kontrola-10px              -> {"pre": ..., "posle": ...}
  font_pod_merenje.py kontrola-pregazeno         -> {"rez": ..., "efektivno": "13px"}

Mreža je zatvorena: API odgovori su fiksture ispod (oblik kao api.py), sve spoljno (CDN, fontovi,
Supabase) se prekida. Nema produkcionih naloga ni podataka.
"""
import http.server
import io
import json
import os
import socket
import socketserver
import sys
import threading

_KOREN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MOTOR = os.path.join(_KOREN, "tests", "assets", "font_motor.js")
POD_FONTA = 11.0
MIN_IZMERENO = 10   # scenario sa manje vidljivih tekstualnih čvorova nije stvarno iscrtan
TABOVI = ["h", "p", "k", "kal", "aiws", "s", "dok", "zadaci-g", "fin", "kanc", "settings"]
EKRANI = {"desktop": {"width": 1440, "height": 900}, "mobilni": {"width": 390, "height": 844}}

PREDMETI = [
    {"id": "pred-1", "naziv": "Tužba — poništaj rešenja o otkazu", "tip": "radni", "status": "aktivan",
     "broj_predmeta": "P1 412/2026", "sud": "Osnovni sud u Beogradu", "klijent_naziv": "Marko Marković",
     "created_at": "2026-09-01T10:00:00Z", "updated_at": "2026-10-10T10:00:00Z",
     "urgentni_rokovi_count": 1, "rizik_nivo": "srednji", "action_priority_key": 1,
     "sledeci_rok": {"datum_iso": "2026-11-02", "dogadjaj": "Rok za tužbu"}},
    {"id": "pred-2", "naziv": "Naknada štete — saobraćajna nezgoda", "tip": "parnicni", "status": "aktivan",
     "broj_predmeta": "P 88/2026", "sud": "Viši sud u Novom Sadu", "klijent_naziv": "Jelena Jovanović",
     "created_at": "2026-08-12T10:00:00Z", "updated_at": "2026-10-01T10:00:00Z",
     "urgentni_rokovi_count": 0, "rizik_nivo": "visok", "action_priority_key": 2, "sledeci_rok": None},
    {"id": "pred-3", "naziv": "Ugovor o zakupu poslovnog prostora", "tip": "privredni", "status": "zavrsen",
     "broj_predmeta": "", "created_at": "2026-05-12T10:00:00Z", "updated_at": "2026-07-01T10:00:00Z",
     "urgentni_rokovi_count": 0, "rizik_nivo": "", "action_priority_key": 9, "sledeci_rok": None},
]
FIKSTURE = {
    "/api/predmeti": {"predmeti": PREDMETI},
    "/api/predmeti/dashboard": {
        "predmeti": PREDMETI, "po_prioritetu": PREDMETI, "po_riziku": PREDMETI[:2], "po_rokovima": PREDMETI[:1],
        "statistike": {"ukupno": 3, "visok_rizik": 1, "hitni_rokovi": 1, "odluke_o_rokovima_dostupne": True,
                       "bez_rizik_procene": 1}},
    "/api/predmeti/pred-1/workspace": {
        "predmet": {"id": "pred-1", "naziv": "Tužba — poništaj rešenja o otkazu", "tip": "radni", "status": "aktivan",
                    "tuzilac": "Marko Marković", "tuzeni": "Alfa d.o.o.", "vrednost_spora": 450000,
                    "rizik": "srednji", "updated_at": "2026-10-10T10:00:00Z"},
        "stranke": [{"uloga": "tuzilac", "naziv": "Marko Marković"}, {"uloga": "tuzeni", "naziv": "Alfa d.o.o."}],
        "protivna_strana": "Alfa d.o.o.",
        "dokumenti": [{"id": "d1", "naziv": "Rešenje o otkazu.pdf", "tip": "resenje",
                       "created_at": "2026-09-02T10:00:00Z", "status": "indeksiran"},
                      {"id": "d2", "naziv": "Ugovor o radu.pdf", "tip": "ugovor", "created_at": "2026-09-03T10:00:00Z"}],
        "rokovi": {"urgentni": [{"id": "r1", "naziv": "Rok za tužbu", "datum": "2026-11-02", "dana": 13}]},
        "beleske": [{"id": "b1", "sadrzaj": "Klijent dostavio rešenje 2. septembra.",
                     "created_at": "2026-09-02T12:00:00Z"}],
        "istorija": [{"pitanje": "Koji je rok za tužbu?", "odgovor": "60 dana od dostavljanja rešenja.",
                      "created_at": "2026-09-05T10:00:00Z"}],
        "statistike": {"dokumenti_count": 2},
        "cockpit": {"ai_sazetak": "Tužba radi poništaja rešenja o otkazu.",
                    "procena_rizika": {"nivo": "srednji", "faktori_plus": ["Pisani dokazi"],
                                       "faktori_minus": ["Kasno dostavljanje"]},
                    "otkriveni_problemi": [{"problem": "Nedostaje dokaz o uručenju", "ozbiljnost": "visoka"}]},
        "case_ready_score": 62,
        "checklist": [{"stavka": "Rešenje o otkazu", "ok": True}, {"stavka": "Dokaz o uručenju", "ok": False}],
        "copilot_preporuka": "Pribaviti dokaz o datumu uručenja."},
    "/klijenti": {"klijenti": [
        {"id": "k1", "ime": "Marko", "prezime": "Marković", "firma": "", "email": "marko@primer.rs",
         "telefon": "060111222", "status": "aktivan"},
        {"id": "k2", "ime": "Jelena", "prezime": "Jovanović", "firma": "Jova d.o.o.", "email": "", "telefon": "",
         "status": "neaktivan"}]},
}
# Scenario se meri tek kada je stvarno učitan.
SIDRA = {
    "LANDING": ("()=>{var l=document.getElementById('vx-landing');return !!l&&getComputedStyle(l).display!=='none'}",
                "početni ekran"),
    "tab-p": ("()=>document.querySelectorAll('#pred-list tr.vx-grid-row').length===3", "3 reda u listi predmeta"),
    "predmet-detalj": ("()=>{var d=document.getElementById('pred-detail'),s=document.getElementById('pred-status-panel');"
                       "return !!d&&d.classList.contains('show')&&!!s&&window.__vxFont.vidljiv(s)"
                       "&&(document.getElementById('pred-detail-naziv')||{}).textContent==='" + PREDMETI[0]["naziv"] + "'}",
                       "otvoren detalj predmeta pred-1"),
    "tab-k": ("()=>document.querySelectorAll('#crm-lista tr.vx-grid-row').length===2", "2 reda u listi klijenata"),
}


class ScenarioNijeUcitan(Exception):
    pass


def _server():
    class Tih(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=_KOREN, **kw)

        def log_message(self, *a):
            pass

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", port), Tih)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d" % port


def _mreza(baza):
    def obradi(route):
        u = route.request.url
        if not u.startswith(baza + "/"):
            return route.abort()                       # spoljna mreža je zatvorena
        put = "/" + u[len(baza) + 1:].split("?", 1)[0].split("#", 1)[0]
        if put.startswith("/rest/v1/"):
            return route.fulfill(status=200, content_type="application/json", body="[]")
        if put.startswith("/api/") or put.startswith("/klijenti") or put.startswith("/auth/"):
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(FIKSTURE.get(put, {})))
        return route.continue_()                       # statički fajlovi legacy interfejsa
    return obradi


def _otvori(pw, baza, tema, ekran):
    b = pw.chromium.launch()
    ctx = b.new_context(viewport=EKRANI[ekran])
    ctx.add_init_script("try{localStorage.setItem('vx_theme','%s')}catch(e){}" % tema)
    pg = ctx.new_page()
    pg.route("**/*", _mreza(baza))
    pg.goto(baza + "/index.html", wait_until="domcontentloaded")
    pg.wait_for_timeout(1200)
    pg.add_script_tag(content=io.open(_MOTOR, encoding="utf-8").read())
    stanje = pg.evaluate("document.body.className")
    if ("light-theme" in stanje) != (tema == "light"):
        raise ScenarioNijeUcitan("tema %s nije primenjena kroz produkcioni put: body=%r" % (tema, stanje))
    return b, pg


def _prijava(pg):
    """Ulazak kroz stvarni `updateAuthUI` (isti put kao posle prave prijave)."""
    pg.evaluate("""()=>{ window.currentUser={email:'advokat@kancelarija.rs',id:'u-faza1'};
        window.currentSession={access_token:'test',user:window.currentUser};
        var nu=document.getElementById('nav-user'); if(nu) nu.style.display='flex';
        if(typeof updateAuthUI==='function') updateAuthUI(); }""")
    pg.wait_for_timeout(500)


def _tab(pg, k):
    pg.evaluate("(k)=>{var b=document.getElementById('tab-btn-'+k);"
                "if(typeof setTab==='function'){try{setTab(b,k)}catch(e){}}"
                "var p=document.getElementById('tab-'+k); if(p)p.style.display='block';}", k)


def _sacekaj(pg, kontekst):
    uslov, opis = SIDRA.get(kontekst) or (
        "()=>{var p=document.getElementById('%s');return !!p&&window.__vxFont.vidljiv(p)}" % kontekst,
        "panel %s vidljiv" % kontekst)
    try:
        pg.wait_for_function(uslov, timeout=8000)
    except Exception:
        raise ScenarioNijeUcitan("scenario %s se nije učitao (%s)" % (kontekst, opis))
    # Panel taba ulazi animacijom providnosti (0 -> 1): merenje na početku animacije bi
    # sav tekst panela video kao nevidljiv i izostavilo ga. Čeka se kraj konačnih animacija.
    try:
        pg.wait_for_function("()=>document.getAnimations().every(a=>a.playState!=='running'"
                             "||a.effect.getComputedTiming().iterations===Infinity)", timeout=8000)
    except Exception:
        raise ScenarioNijeUcitan("scenario %s: animacija prikaza se nije završila" % kontekst)


def _skeniraj(pg, kontekst):
    return pg.evaluate("(k)=>window.__vxFont.skeniraj(k, %s)" % POD_FONTA, kontekst)


def scenariji(pw, baza, tema, ekran):
    b, pg = _otvori(pw, baza, tema, ekran)
    try:
        rez = []

        def meri(kontekst):
            _sacekaj(pg, kontekst)
            r = _skeniraj(pg, kontekst)
            if r["izmereno"] < MIN_IZMERENO and kontekst != "tab-h":     # #tab-h je zaključan, meri se ostatak
                raise ScenarioNijeUcitan("%s: izmereno samo %d vidljivih tekstualnih čvorova" % (kontekst, r["izmereno"]))
            rez.append([kontekst, r])

        meri("LANDING")
        _prijava(pg)
        for k in TABOVI:
            _tab(pg, k)
            meri("tab-" + k)
            if k == "p":
                pg.evaluate("()=>pred_select('pred-1')")
                meri("predmet-detalj")
        return {"scenariji": rez}
    finally:
        b.close()


def _lista_predmeta(pw, baza):
    b, pg = _otvori(pw, baza, "dark", "desktop")
    _prijava(pg)
    _tab(pg, "p")
    _sacekaj(pg, "tab-p")
    return b, pg


def kontrola_10px(pw, baza):
    """Vidljiv element sveden na efektivnih 10px mora biti prijavljen."""
    b, pg = _lista_predmeta(pw, baza)
    try:
        pre = _skeniraj(pg, "kontrola")
        pg.evaluate("()=>document.querySelector('#pred-list tr.vx-grid-row td:nth-child(2)')"
                    ".style.setProperty('font-size','10px','important')")
        return {"pre": pre, "posle": _skeniraj(pg, "kontrola")}
    finally:
        b.close()


def kontrola_pregazeno(pw, baza):
    """Deklaracija ispod praga koju pregazi jače pravilo, koja ne pogađa ništa ili pogađa samo
    skriven element nije efektivni sitan tekst i ne sme biti prijavljena."""
    b, pg = _lista_predmeta(pw, baza)
    try:
        pg.evaluate("""()=>{
            var st=document.createElement('style');
            st.textContent='#pred-list td{font-size:9px}'                  /* pregaženo sledećim pravilom */
              +'#pred-list tr.vx-grid-row td{font-size:13px}'
              +'.vxf-ne-postoji{font-size:6px}'                             /* ne pogađa nijedan element */
              +'#vxf-skriven{font-size:8px;display:none}';                  /* pogađa samo skriven element */
            document.head.appendChild(st);
            var s=document.createElement('div'); s.id='vxf-skriven'; s.textContent='Skriven sitan tekst';
            document.getElementById('tab-p').appendChild(s);
        }""")
        efektivno = pg.evaluate("()=>getComputedStyle(document.querySelector("
                                "'#pred-list tr.vx-grid-row td:nth-child(2)')).fontSize")
        return {"rez": _skeniraj(pg, "kontrola"), "efektivno": efektivno}
    finally:
        b.close()


def main(argv):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        print(json.dumps({"greska": "playwright nije instaliran u %s: %s" % (sys.executable, e)}))
        return 3
    srv, baza = _server()
    try:
        with sync_playwright() as pw:
            if argv[0] == "scenariji":
                izlaz = scenariji(pw, baza, argv[1], argv[2])
            elif argv[0] == "kontrola-10px":
                izlaz = kontrola_10px(pw, baza)
            elif argv[0] == "kontrola-pregazeno":
                izlaz = kontrola_pregazeno(pw, baza)
            else:
                raise SystemExit("nepoznat režim %r" % argv[0])
    except ScenarioNijeUcitan as e:
        print(json.dumps({"greska": str(e)}))
        return 2
    except Exception as e:   # npr. Chromium nije instaliran (`playwright install chromium`)
        print(json.dumps({"greska": "pregledač nije pokrenut: %s" % str(e)[:600]}))
        return 3
    finally:
        srv.shutdown()
        srv.server_close()
    print(json.dumps(izlaz))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
