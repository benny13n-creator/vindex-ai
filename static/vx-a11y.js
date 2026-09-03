/* ══════════════════════════════════════════════════════════════════════════
   vx-a11y.js — FAZA 1.4 / 1.5: DOHVATLJIVOST TASTATUROM I NAJAVA PROMENA

   ZASTO ZASEBAN FAJL, A NE 167 IZMENA U IZVORU
   ────────────────────────────────────────────
   Merenje pre izmene: 187 `onclick` rukovalaca na `div`/`span`/`li`/`td`, od
   kojih 167 bez `role` i `tabindex`. Takva kontrola je za tastaturu i citac
   ekrana NEVIDLJIVA — ne moze se dohvatiti, ne najavljuje se kao kontrola.

   Tri razmatrana resenja:
     1. pretvoriti ih u <button>  — odbaceno: `.t-tab` i srodni nose CSS pisan
        za `div` (6 pravila sa `!important`); promena oznake je veci zahvat od
        same pristupacnosti i nosi rizik regresije rasporeda;
     2. dodati atribute u izvor na 167 mesta — odbaceno: 61 od njih nastaje u
        `vindex.js` kao string, pa bi regex nad generisanim HTML-om bio krt, a
        svaki NOV render u buducnosti bi opet bio nedohvatljiv;
     3. OVO — promocija u vreme izvrsavanja, plus MutationObserver.
        Pokriva i staticki markup i sve sto se tek iscrta.

   AKTIVACIJA TASTATUROM SE OVDE NE DODAJE.
   `vindex.js:483` vec ima delegirani aktivator za `[role="button"][tabindex]`,
   a `vindex.js:24209` za `[role="tab"]`. Dodavanje jos jednog napravilo bi
   DUPLU aktivaciju — greska koja je vec jednom napravljena i uhvacena testom
   koji broji koliko se puta radnja izvrsila. Ovde se dodaju samo ATRIBUTI.

   ZAKLJUCANI EKRAN
   ────────────────
   `#tab-h` (Pregled dana / `.kc-sphere`) je LEGACY LOCKED. Svaka petlja ovde
   ga preskace eksplicitno, po imenu, a ne slucajno.
   ══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var LOCKED = '#tab-h';

  /* Elementi koji su vec fokusabilni po prirodi — njih ne diramo. */
  var NATIVNO = { A: 1, BUTTON: 1, INPUT: 1, SELECT: 1, TEXTAREA: 1, SUMMARY: 1 };

  function uZakljucanom(el) {
    return !!(el.closest && el.closest(LOCKED));
  }

  /* ── 1. Promocija kontrola ─────────────────────────────────────────────
     Element sa `onclick` koji nije nativno fokusabilan dobija `role="button"`
     i `tabindex="0"`. Nista drugo se ne menja — ni oznaka, ni klase, ni stil. */
  function promoviši(koren) {
    var n = 0;
    var kandidati = (koren || document).querySelectorAll('[onclick]');
    for (var i = 0; i < kandidati.length; i++) {
      var el = kandidati[i];
      if (NATIVNO[el.tagName]) continue;
      if (uZakljucanom(el)) continue;
      if (el.hasAttribute('role') && el.hasAttribute('tabindex')) continue;
      /* Ugnjezdena kontrola: ako je predak vec dugme, nova tab-meta bi bila
         duplikat i korisnik bi dva puta stao na istu stvar. */
      if (el.parentElement && el.parentElement.closest('[role="button"],button,a')) continue;
      /* Skriven element ne treba da bude tab-meta. */
      if (el.getAttribute('aria-hidden') === 'true') continue;

      if (!el.hasAttribute('role')) el.setAttribute('role', 'button');
      /* FAZA 1: ova linija je bila `void 0;` -- prazna. Element je dobijao
         `role="button"` ali NE i `tabindex`, pa je citacu ekrana bio
         objavljen kao dugme koje tastatura ne moze da dohvati. Mereno:
         82 od 559 kontrola sa `onclick`. Aktivacija se i dalje NE dodaje
         ovde -- delegirani rukovaoci u vindex.js vec pokrivaju
         `[role="button"][tabindex]`. */
      if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '0');
      /* Citac ekrana mora imati sta da procita. Ako element nema sopstveni
         tekst, `title` je jedini preostali izvor imena. */
      if (!el.textContent.trim() && !el.getAttribute('aria-label')) {
        var t = el.getAttribute('title');
        if (t) el.setAttribute('aria-label', t);
      }
      n++;
    }
    return n;
  }

  /* ── 2. Zive oblasti ───────────────────────────────────────────────────
     NE pretvaramo ceo interfejs u `aria-live`. Najavljuje se samo ono sto
     korisnik MORA da zna, a sto se desilo bez njegove radnje ili posle nje:

       oblast                     nivo       zasto
       ─────────────────────────  ─────────  ─────────────────────────────────
       toast-container            assertive  ishod radnje (uspeh/greska)
       rezultat pitanja / analize polite     dug posao se zavrsio
       status otpremanja          polite     dokument je obradjen
       broj rezultata pretrage    polite     "nema pogodaka" je informacija
       stanje snimanja glasa      assertive  korisnik ne vidi da mikrofon radi

     `polite` ceka pauzu u citanju; `assertive` prekida. Greska prekida,
     rezultat ne. */
  /* Imena ispod su PROVERENA u `index.html` — prva verzija ove liste sadrzala
     je cetiri ID-a koja NE POSTOJE (`odgovor`, `praksa-results`,
     `pred-upload-status`, `mic-status`). Bili su pogodjeni, ne izmereni; test
     bi prosao (postoje 3 oblasti) a cetiri najave nikad ne bi radile. */
  var ZIVE = [
    ['toast-container',   'assertive', 'Obavestenja'],
    ['resp',              'polite',    'Odgovor'],
    ['agent-result-wrap', 'polite',    'Rezultat analize'],
    ['doc-upload-loading','polite',    'Obrada dokumenta'],
    ['doc-upload-error',  'assertive', 'Greska pri otpremanju'],
    ['si-upload-err',     'assertive', 'Greska pri otpremanju'],
    ['voice-status',      'assertive', 'Stanje mikrofona'],
    ['cmdk-results',      'polite',    'Rezultati pretrage']
  ];

  function zivo() {
    var n = 0;
    for (var i = 0; i < ZIVE.length; i++) {
      var el = document.getElementById(ZIVE[i][0]);
      if (!el || uZakljucanom(el)) continue;
      if (!el.hasAttribute('aria-live')) {
        el.setAttribute('aria-live', ZIVE[i][1]);
        el.setAttribute('aria-atomic', 'false');
        if (!el.hasAttribute('aria-label')) el.setAttribute('aria-label', ZIVE[i][2]);
        n++;
      }
    }
    /* Zajednicki najavljivac za poruke koje nemaju svoj kontejner. */
    if (!document.getElementById('vx-a11y-najava')) {
      var d = document.createElement('div');
      d.id = 'vx-a11y-najava';
      d.setAttribute('aria-live', 'polite');
      d.setAttribute('aria-atomic', 'true');
      d.style.cssText = 'position:absolute;width:1px;height:1px;overflow:hidden;' +
                        'clip:rect(0 0 0 0);white-space:nowrap;border:0;';
      document.body.appendChild(d);
      n++;
    }
    return n;
  }

  /* Javni API — koristi se u Fazi 3 za najavu ishoda odluke. */
  window.vxNajavi = function (tekst) {
    var d = document.getElementById('vx-a11y-najava');
    if (!d) return;
    d.textContent = '';
    setTimeout(function () { d.textContent = String(tekst || ''); }, 40);
  };

  /* ── 3. Preskoci na sadrzaj ────────────────────────────────────────────
     Prva tab-meta na stranici. Bez nje korisnik tastature mora da prodje kroz
     celu bocnu traku pre nego sto stigne do rada. */
  function preskok() {
    if (document.querySelector('.vx-skip-link')) return 0;
    var cilj = document.getElementById('t-body') ||
               document.querySelector('.vx-main') ||
               document.getElementById('vx-shell');
    if (!cilj) return 0;
    if (!cilj.id) cilj.id = 'vx-glavni-sadrzaj';
    if (!cilj.hasAttribute('tabindex')) cilj.setAttribute('tabindex', '-1');
    var a = document.createElement('a');
    a.className = 'vx-skip-link';
    a.href = '#' + cilj.id;
    a.textContent = 'Preskoči na sadržaj';
    document.body.insertBefore(a, document.body.firstChild);
    return 1;
  }

  /* ── 4. Pokretanje i posmatranje ───────────────────────────────────────
     Interfejs se iscrtava iz JS-a posle svakog ucitavanja podataka, pa
     jednokratni prolaz nije dovoljan. Posmatrac je prigusen (debounce) da ne
     bi radio na svaku pojedinacnu izmenu cvora. */
  var cekanje = null;
  function prolaz() {
    try { promoviši(document); zivo(); } catch (e) { /* nikad ne rusi UI */ }
  }
  function zakaži() {
    if (cekanje) return;
    cekanje = setTimeout(function () { cekanje = null; prolaz(); }, 250);
  }

  function start() {
    preskok();
    prolaz();
    if (window.MutationObserver) {
      new MutationObserver(zakaži).observe(document.body, { childList: true, subtree: true });
    }
    /* Dijagnostika za merni harness — ne utice na ponasanje. */
    window.__vxA11y = { promoviši: promoviši, zivo: zivo, prolaz: prolaz };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
