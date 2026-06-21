
/* ── Srpska ćirilica — Vukova azbuka (inline, bez eksternog fajla) ────────── */
(function(global){
  'use strict';

  // ── Fonetska mapa (za prevod reči) ─────────────────────────────────────────
  var MAP=[
    ['lj','\u0459'],['Lj','\u0409'],['LJ','\u0409'],
    ['nj','\u045a'],['Nj','\u040a'],['NJ','\u040a'],
    ['d\u017e','\u045f'],['D\u017e','\u040f'],['D\u017d','\u040f'],
    ['a','\u0430'],['A','\u0410'],['b','\u0431'],['B','\u0411'],
    ['v','\u0432'],['V','\u0412'],['g','\u0433'],['G','\u0413'],
    ['d','\u0434'],['D','\u0414'],['\u0111','\u0452'],['\u0110','\u0402'],
    ['e','\u0435'],['E','\u0415'],['\u017e','\u0436'],['\u017d','\u0416'],
    ['z','\u0437'],['Z','\u0417'],['i','\u0438'],['I','\u0418'],
    ['j','\u0458'],['J','\u0408'],['k','\u043a'],['K','\u041a'],
    ['l','\u043b'],['L','\u041b'],['m','\u043c'],['M','\u041c'],
    ['n','\u043d'],['N','\u041d'],['o','\u043e'],['O','\u041e'],
    ['p','\u043f'],['P','\u041f'],['r','\u0440'],['R','\u0420'],
    ['s','\u0441'],['S','\u0421'],['t','\u0442'],['T','\u0422'],
    ['\u0107','\u045b'],['\u0106','\u040b'],['\u010d','\u0447'],['\u010c','\u0427'],
    ['\u0161','\u0448'],['\u0160','\u0428'],['u','\u0443'],['U','\u0423'],
    ['f','\u0444'],['F','\u0424'],['h','\u0445'],['H','\u0425'],
    ['c','\u0446'],['C','\u0426']
  ];
  function _seg(t){for(var i=0;i<MAP.length;i++)t=t.split(MAP[i][0]).join(MAP[i][1]);return t;}

  // ── Azbučna mapa za nabrajanje (a=1→а, b=2→б, c=3→в …) ────────────────────
  // 26 latiničnih slova → 26 ćiriličnih po azbučnom redosledu (bez dvoznaka)
  var ENUM_LC=['\u0430','\u0431','\u0432','\u0433','\u0434','\u0435','\u0436',
               '\u0437','\u0438','\u0458','\u043a','\u043b','\u043c','\u043d',
               '\u043e','\u043f','\u0440','\u0441','\u0442','\u045b','\u0443',
               '\u0444','\u0445','\u0446','\u0447','\u0448'];
  var ENUM_UC=['\u0410','\u0411','\u0412','\u0413','\u0414','\u0415','\u0416',
               '\u0417','\u0418','\u0408','\u041a','\u041b','\u041c','\u041d',
               '\u041e','\u041f','\u0420','\u0421','\u0422','\u040b','\u0423',
               '\u0424','\u0425','\u0426','\u0427','\u0428'];

  function _enumCyr(ch){
    var idx=ch.toLowerCase().charCodeAt(0)-97;
    if(idx<0||idx>25) return null;
    return ch===ch.toUpperCase()?ENUM_UC[idx]:ENUM_LC[idx];
  }

  // Zamenjuje oznake nabrajanja PRE fonetske konverzije:
  //   (a) (b) (c)   — slovo u zagradi
  //   a.  b.  c.    — slovo+tačka na početku reda ili posle razmaka
  //   a)  b)  c)    — slovo+zagrada na početku reda ili posle razmaka
  function _applyEnum(text){
    // (x) — uvek, gde god se pojavi kao oznaka nabrajanja
    text=text.replace(/\(([a-zA-Z])\)/g,function(m,ch){
      var r=_enumCyr(ch); return r?'('+r+')':m;
    });
    // x. ili x) na početku teksta ili posle novog reda (sa opcionalnim razmakom)
    text=text.replace(/(^|\n)([ \t]*)([a-zA-Z])([.)]) /g,function(m,nl,sp,ch,punct){
      var r=_enumCyr(ch); return r?nl+sp+r+punct+' ':m;
    });
    return text;
  }

  // Prolazi kroz DOM čvorove i konvertuje samo TEXT_NODE — preskače tagove
  function _walkNode(node){
    if(node.nodeType===3){
      var v=node.nodeValue;
      if(v&&v.trim()) node.nodeValue=_seg(_applyEnum(v));
    } else if(node.nodeType===1){
      var tag=node.nodeName.toUpperCase();
      if(tag==='SCRIPT'||tag==='STYLE'||tag==='CODE'||tag==='PRE') return;
      for(var i=0;i<node.childNodes.length;i++) _walkNode(node.childNodes[i]);
    }
  }

  // Konvertuje ceo element (in-place)
  function cirilicaElement(el){if(el) _walkNode(el);}

  // Konvertuje čisti string (za PDF export i slično)
  function pretvoriUCirilicu(tekst){
    if(!tekst||typeof tekst!=='string') return tekst;
    var d=document.createElement('div');
    d.innerHTML=tekst;
    _walkNode(d);
    return d.innerHTML;
  }

  global.pretvoriUCirilicu=pretvoriUCirilicu;
  global.cirilicaElement=cirilicaElement;
})(window);


/* ═══════════════════════════════ NEXT BLOCK ═══════════════════════════════ */


/* ── Vindex Shell: show app when logged in, landing when not ── */
(function(){
  function vxSync(){
    var nu  = document.getElementById('nav-user');
    var sh  = document.getElementById('vx-shell');
    var ld  = document.getElementById('vx-landing');
    var ts  = document.getElementById('vx-topbar-settings-btn');
    var loggedIn = nu && nu.style.display === 'flex';
    if(sh) sh.style.display = loggedIn ? 'flex' : 'none';
    if(ld) ld.style.display = loggedIn ? 'none' : 'flex';
  }
  function vxInit(){
    var nu = document.getElementById('nav-user');
    if(nu){
      new MutationObserver(vxSync).observe(nu, {attributes:true, attributeFilter:['style']});
    }
    vxSync();
  }
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded', function(){ vxInit(); if(window.lucide)lucide.createIcons(); });
  } else {
    vxInit();
    if(window.lucide) lucide.createIcons();
  }
})();


/* ═══════════════════════════════ NEXT BLOCK ═══════════════════════════════ */


var BASE_URL   = window.location.origin;
var STRIPE_URL = ''; // Set to your Stripe checkout or pricing page URL
var activeTab = 'q';
var _initialNavDone = false;
var _cyrillicOn = false;
var vxNavHistory = [];
var _vxGoingBack = false;
var _vxTabLabels = {h:'Komandni centar',q:'Istraživanje zakona',n:'Nacrti podnesaka',a:'Analiza dokumenta',s:'Sudska praksa',p:'Predmeti',t:'Strategija',k:'Klijenti',w:'Web3 & Compliance',kal:'Rokovi i ročišta',pi:'Product Intelligence',alati:'AI Centar',dok:'Baza znanja',settings:'Podešavanja'};
var currentUserIsPro     = false;
var currentUserIsFounder = false;
var _lastRawText = '';

function toggleCyrillic() {
  _cyrillicOn = document.getElementById('cyr-toggle').checked;
  // Ažuriraj trenutni odgovor
  var rb = document.getElementById('rb');
  if (_lastRawText && rb && document.getElementById('resp').classList.contains('show')) {
    rb.innerHTML = formatResponse(_lastRawText) + _feedbackBar(lastPitanje, _lastRawText);
    if (_cyrillicOn) cirilicaElement(rb);
  }
  // Ažuriraj preview podneska ako je vidljiv
  var previewBody = document.getElementById('podnesak-preview-body');
  var previewEl   = document.getElementById('podnesak-preview');
  if (_lastRawText && previewBody && previewEl && previewEl.style.display !== 'none') {
    var highlighted = escHtml(_lastRawText).replace(/\[([A-ZŠĐČĆŽ\s\-—]+?)\s*—\s*POPUNITI\]/g,
      '<span class="popuniti">[$1 — POPUNITI]</span>');
    previewBody.innerHTML = highlighted;
    if (_cyrillicOn) cirilicaElement(previewBody);
  }
  // Ažuriraj history panel
  if (_chatHistoryRows.length) renderChatHistory(_chatHistoryRows);
}

function _applyPismo(rawText) {
  // Vraća samo HTML string; ćirilica se primenjuje naknadno na DOM čvorove
  return formatResponse(rawText);
}

// ─── Supabase konfiguracija ───────────────────────────────────────────────────
// Popunite sa vrednostima iz Supabase Dashboard → Settings → API
var SUPABASE_URL      = 'https://czsxymueizfqrbbgqqob.supabase.co';
var SUPABASE_ANON_KEY = 'sb_publishable_fvC51B_GKz_Uf8t3wZ3JDg_TIp3-zBp';
// ─────────────────────────────────────────────────────────────────────────────

var _supa = null;
function getSupabase() {
  if (!_supa && SUPABASE_URL !== 'VAŠA_SUPABASE_URL' && window.supabase) {
    _supa = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  }
  return _supa;
}

// ─── Auth stanje ──────────────────────────────────────────────────────────────
var currentUser         = null;
var currentSession      = null;
var userCredits         = 0;
var TOTAL_CREDITS       = 15;
var conversationHistory = [];  // [{q, a}, ...] — max 3 para
var currentChatSessionId = null;
var _chatHistoryRows     = [];

async function initAuth() {
  var sb = getSupabase();
  if (!sb) return;
  var res = await sb.auth.getSession();
  if (res.data && res.data.session) {
    currentSession = res.data.session;
    currentUser    = res.data.session.user;
    await loadCredits();
    updateAuthUI();
    loadChatHistory();
  }
  sb.auth.onAuthStateChange(async function(event, session) {
    currentSession = session;
    currentUser    = session ? session.user : null;
    if (currentUser) {
      await loadCredits();
      loadChatHistory();
      pred_load();
      if ((event === 'SIGNED_IN' || event === 'INITIAL_SESSION') && !_initialNavDone) {
        _initialNavDone = true;
        piTrack('auth', 'login', {event: event});
        var hTab = document.querySelector('[onclick*="\'h\'"]');
        if (hTab) setTab(hTab, 'h');
        // Onboarding — jedini flow je onboardingCheck (stari onboard_show je deaktiviran)
      }
    } else {
      userCredits = 0; _creditsLoaded = false; _creditsLoadedAt = 0; _chatHistoryRows = [];
      var ch=document.getElementById('chat-hist'); if(ch){ch.innerHTML='';ch.style.display='none';}
      var alatiTab = document.getElementById('tab-btn-alati');
      if (alatiTab) setTab(alatiTab, 'alati');
    }
    updateAuthUI();
  });
}

var _creditsLoaded = false;
var _creditsLoadedAt = 0;

async function loadCredits() {
  if (!currentSession) return;
  var now = Date.now();
  if (_creditsLoaded && (now - _creditsLoadedAt) < 5000) { updateCreditDisplay(); return; }
  console.log('[Vindex] loadCredits: dohvatam /api/me...');
  try {
    var r = await fetch(BASE_URL + '/api/me', {
      headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
    });
    console.log('[Vindex] /api/me status:', r.status);
    if (r.ok) {
      var d = await r.json();
      console.log('[Vindex] /api/me odgovor:', d);
      userCredits       = (d.credits_remaining !== undefined && d.credits_remaining !== null) ? d.credits_remaining : 0;
      TOTAL_CREDITS     = d.credits_total || 15;
      currentUserIsPro     = !!d.is_pro;
      currentUserIsFounder = !!d.is_founder;
      _creditsLoaded    = true;
      _creditsLoadedAt  = Date.now();
      _updateProTabUI();
      _updateStratTabUI();
      _updateAdminTabUI();
      updateCreditDisplay();
      if (currentUserIsPro) {
        ucitajApiKljuceve();
        // F7: prikaži PRO panele
        var ip = document.getElementById('interni-stavovi-panel');
        if (ip && activeTab === 'q') ip.style.display = '';
        if (activeTab === 'n') ucitajPlaybookStatus();
      }
    } else {
      console.warn('[Vindex] /api/me greška, status:', r.status);
    }
  } catch(e) { console.warn('[Vindex] loadCredits greška:', e); }
}

function updateCreditDisplay() {
  var navNum  = document.getElementById('nav-credits-num');
  var navPill = document.getElementById('nav-credit-pill');
  var tVal    = document.getElementById('t-credits-val');
  var execBtn = document.getElementById('exec-btn');
  var btnLbl  = document.getElementById('btn-lbl');

  console.log('[Vindex] updateCreditDisplay: userCredits =', userCredits);

  if (navNum)  navNum.textContent = userCredits;
  if (tVal)    tVal.textContent   = userCredits + ' / ' + TOTAL_CREDITS;

  var cls = userCredits > 3 ? '' : userCredits > 0 ? 'warn' : 'empty';
  if (navPill) { navPill.className = 'nav-credit-pill ' + cls; }
  if (tVal)    { tVal.className    = 't-credits-val ' + cls; }

  if (execBtn) {
    if (userCredits <= 0) {
      execBtn.disabled = true;
      if (btnLbl) btnLbl.textContent = 'Nemate dovoljno kredita';
    } else {
      execBtn.disabled = false;
      if (btnLbl && btnLbl.textContent === 'Nemate dovoljno kredita') {
        btnLbl.textContent = 'Pretraži pravnu bazu';
      }
    }
  }
}

function updateAuthUI() {
  var navUser  = document.getElementById('nav-user');
  var navCta   = document.getElementById('nav-cta-btn');
  var navEmail = document.getElementById('nav-user-email');
  var tRow     = document.getElementById('t-credits-row');
  var shell    = document.getElementById('vx-shell');
  var landing  = document.getElementById('vx-landing');

  if (currentUser) {
    if (navUser)  navUser.style.display  = 'flex';
    if (navCta)   navCta.style.display   = 'none';
    if (navEmail) navEmail.textContent   = currentUser.email || '';
    if (tRow)     tRow.style.display     = 'flex';
    if (shell)    shell.style.display    = 'flex';
    if (landing)  landing.style.display  = 'none';
    updateCreditDisplay();
  } else {
    if (navUser)  navUser.style.display  = 'none';
    if (navCta)   navCta.style.display   = '';
    if (tRow)     tRow.style.display     = 'none';
    if (shell)    shell.style.display    = 'none';
    if (landing)  landing.style.display  = 'flex';
  }
}

// ─── Auth modal ───────────────────────────────────────────────────────────────
var authMode = 'login';

function openModal() {
  document.getElementById('auth-modal').classList.add('open');
}
function closeModal() {
  document.getElementById('auth-modal').classList.remove('open');
  document.getElementById('auth-error').textContent = '';
  document.getElementById('auth-error').style.color = '';
}

/* ── Waitlist / Early Access ─────────────────────────────────────── */
function wl_open() {
  document.getElementById('wl-overlay').classList.add('open');
  document.getElementById('wl-form-wrap').style.display = '';
  document.getElementById('wl-success-wrap').style.display = 'none';
  setTimeout(function(){ var el = document.getElementById('wl-ime'); if(el) el.focus(); }, 80);
}
function wl_close() {
  document.getElementById('wl-overlay').classList.remove('open');
}
async function wl_submit() {
  var ime     = (document.getElementById('wl-ime').value     || '').trim();
  var email   = (document.getElementById('wl-email').value   || '').trim();
  var firma   = (document.getElementById('wl-firma').value   || '').trim();
  var telefon = (document.getElementById('wl-telefon').value || '').trim();
  var poruka  = (document.getElementById('wl-poruka').value  || '').trim();

  if (!ime)   { showToast('Unesite ime i prezime.', 'warn'); document.getElementById('wl-ime').focus(); return; }
  if (!email || !email.includes('@')) { showToast('Unesite ispravnu email adresu.', 'warn'); document.getElementById('wl-email').focus(); return; }

  var btn = document.getElementById('wl-submit-btn');
  btn.disabled = true;
  btn.textContent = 'Šaljem...';

  try {
    var resp = await fetch('/waitlist/prijava', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ime: ime, email: email, firma: firma, telefon: telefon, poruka: poruka })
    });
    var data = await resp.json();
    if (data.ok) {
      document.getElementById('wl-confirmed-email').textContent = email;
      document.getElementById('wl-form-wrap').style.display = 'none';
      document.getElementById('wl-success-wrap').style.display = '';
    } else {
      showToast(data.detail || 'Greška pri prijavi. Pokušajte ponovo.', 'err');
      btn.disabled = false;
      btn.textContent = 'Prijavite se za rani pristup';
    }
  } catch(e) {
    showToast('Greška mreže. Proverite konekciju.', 'err');
    btn.disabled = false;
    btn.textContent = 'Prijavite se za rani pristup';
  }
}
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape' && document.getElementById('wl-overlay').classList.contains('open')) wl_close();
});

var _EYE_OPEN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
var _EYE_SHUT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';

function togglePw(inputId, btn) {
  var inp = document.getElementById(inputId);
  var showing = inp.type === 'text';
  inp.type = showing ? 'password' : 'text';
  btn.innerHTML = showing ? _EYE_OPEN : _EYE_SHUT;
  btn.title = showing ? 'Prikaži lozinku' : 'Sakrij lozinku';
}

function showToast(msg, type) {
  var c = document.getElementById('toast-container');
  if (!c) return;
  var t = document.createElement('div');
  t.className = 'toast' + (type ? ' toast-' + type : '');
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(function() {
    t.style.transition = 'opacity 0.35s';
    t.style.opacity = '0';
    setTimeout(function() { t.remove(); }, 380);
  }, 3200);
}

function setAuthMode(mode) {
  authMode = mode;
  var allForms = ['auth-login-form','auth-register-form','auth-forgot-form','auth-reset-form'];
  allForms.forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
  var target = document.getElementById('auth-' + mode + '-form');
  if (target) target.style.display = 'flex';

  var showTabs = (mode === 'login' || mode === 'register');
  var tabsEl = document.getElementById('auth-tabs-row');
  if (tabsEl) tabsEl.style.display = showTabs ? '' : 'none';
  document.getElementById('auth-login-tab').classList.toggle('active', mode === 'login');
  document.getElementById('auth-reg-tab').classList.toggle('active', mode === 'register');

  var titles = {
    login:    ['Dobrodošli.', 'Prijavite se na vaš nalog.'],
    register: ['Dobrodošli.', 'Registracija je potpuno besplatna.'],
    forgot:   ['Reset lozinke.', 'Poslaćemo vam link na email.'],
    reset:    ['Nova lozinka.', 'Izaberite novu lozinku za nalog.'],
  };
  var t = titles[mode] || titles.login;
  var titleEl = document.getElementById('auth-modal-title');
  var subEl   = document.getElementById('auth-modal-sub');
  if (titleEl) titleEl.innerHTML = t[0];
  if (subEl)   subEl.textContent = t[1];

  document.getElementById('auth-error').textContent = '';
}

async function doForgotPassword() {
  var sb = getSupabase();
  if (!sb) { _setAuthError('Autentifikacija nije konfigurisana.'); return; }
  var email = document.getElementById('forgot-email').value.trim();
  if (!email) { _setAuthError('Unesite email adresu.'); return; }
  var btn = document.getElementById('forgot-btn');
  btn.textContent = 'Šalje se...'; btn.disabled = true;
  var redirectTo = window.location.origin + window.location.pathname;
  var res = await sb.auth.resetPasswordForEmail(email, { redirectTo: redirectTo });
  btn.textContent = 'Pošalji reset link'; btn.disabled = false;
  if (res.error) { _setAuthError('Greška: ' + (res.error.message || 'Pokušajte ponovo.')); return; }
  _setAuthError('Link je poslat! Proverite email (i Spam folder).', true);
  showToast('Reset link poslat na ' + email, 'info');
}

async function doResetPassword() {
  var sb = getSupabase();
  if (!sb) { _setAuthError('Autentifikacija nije konfigurisana.'); return; }
  var p1 = document.getElementById('reset-password').value;
  var p2 = document.getElementById('reset-password2').value;
  if (!p1 || p1.length < 8) { _setAuthError('Lozinka mora imati najmanje 8 karaktera.'); return; }
  if (p1 !== p2) {
    _setAuthError('Lozinke se ne poklapaju.');
    showToast('Lozinke se ne poklapaju.', 'err');
    return;
  }
  var btn = document.getElementById('reset-btn');
  btn.textContent = 'Čuvam...'; btn.disabled = true;
  var res = await sb.auth.updateUser({ password: p1 });
  btn.textContent = 'Sačuvaj novu lozinku'; btn.disabled = false;
  if (res.error) { _setAuthError('Greška: ' + (res.error.message || 'Pokušajte ponovo.')); return; }
  showToast('Lozinka uspešno promenjena!', 'ok');
  history.replaceState(null, '', window.location.pathname);
  setAuthMode('login');
  document.getElementById('reset-password').value = '';
  document.getElementById('reset-password2').value = '';
}

function _setAuthError(msg, isOk) {
  var el = document.getElementById('auth-error');
  el.textContent = msg;
  el.style.color = isOk ? '#4ade80' : '#ff6b6b';
}

async function doLogin() {
  var sb = getSupabase();
  if (!sb) { _setAuthError('Autentifikacija nije konfigurisana.'); return; }
  var email = document.getElementById('login-email').value.trim();
  var pass  = document.getElementById('login-password').value;
  if (!email || !pass) { _setAuthError('Unesite email i lozinku.'); return; }
  var btn = document.getElementById('login-btn');
  btn.textContent = 'Prijava...'; btn.disabled = true;
  var res = await sb.auth.signInWithPassword({ email: email, password: pass });
  btn.textContent = 'Prijavite se'; btn.disabled = false;
  if (res.error) { _setAuthError('Pogrešan email ili lozinka. Pokušajte ponovo.'); return; }
  currentSession = res.data.session;
  currentUser    = res.data.user;
  closeModal();
  updateAuthUI();
  loadCredits();
}

async function doRegister() {
  var sb = getSupabase();
  if (!sb) { _setAuthError('Autentifikacija nije konfigurisana.'); return; }
  var email   = document.getElementById('reg-email').value.trim();
  var pass    = document.getElementById('reg-password').value;
  var confirm = document.getElementById('reg-confirm-password').value;
  if (!email || !pass) { _setAuthError('Unesite email i lozinku.'); return; }
  if (pass.length < 8) { _setAuthError('Lozinka mora imati najmanje 8 karaktera.'); return; }
  if (pass !== confirm) { _setAuthError('Lozinke se ne poklapaju.'); return; }
  var btn = document.getElementById('reg-btn');
  btn.textContent = 'Registracija...'; btn.disabled = true;
  try {
    var chk = await fetch(BASE_URL + '/api/check-email', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({email: email})
    });
    var chkData = await chk.json();
    if (!chkData.valid) {
      _setAuthError('Privremene email adrese nisu dozvoljene. Koristite pravu email adresu.');
      btn.textContent = 'Registruj se'; btn.disabled = false;
      return;
    }
  } catch(e) { /* Nastavlja bez provere ako API nije dostupan */ }

  // Poziva backend koji kreira user_credits (15 kredita) i profile — ne zaobilazi setup
  try {
    var regRes = await fetch(BASE_URL + '/api/register', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ email: email, password: pass })
    });
    var regData = await regRes.json();
    if (!regRes.ok) {
      var msg = regData.detail || 'Greška pri registraciji.';
      if (msg.toLowerCase().includes('već registrovana') || msg.toLowerCase().includes('already')) {
        msg = 'Ovaj email je već registrovan. Prijavite se.';
      }
      _setAuthError(msg);
      btn.textContent = 'Registruj se'; btn.disabled = false;
      return;
    }
  } catch(e) {
    _setAuthError('Greška mreže. Pokušajte ponovo.');
    btn.textContent = 'Registruj se'; btn.disabled = false;
    return;
  }

  // Login za Supabase sesiju (backend kreirao korisnika sa email_confirm=true)
  var loginRes = await sb.auth.signInWithPassword({ email: email, password: pass });
  btn.textContent = 'Registruj se'; btn.disabled = false;
  if (loginRes.error) {
    _setAuthError('Registracija uspešna. Prijavite se sa vašim podacima.', true);
    return;
  }
  currentSession = loginRes.data.session;
  currentUser    = loginRes.data.user;
  closeModal();
  updateAuthUI();
  loadCredits();
}

async function doLogout() {
  var sb = getSupabase();
  if (sb) await sb.auth.signOut();
  currentUser = null; currentSession = null; userCredits = 0;
  updateAuthUI();
}

// ─── Chat sesija & memorija ───────────────────────────────────────────────────

function _generateUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    var r = Math.random()*16|0, v = c==='x' ? r : (r&0x3|0x8);
    return v.toString(16);
  });
}

// PII filter — uklanja JMBG, email, telefon, PIB pre slanja u bazu
function _piiFilter(text) {
  return (text || '')
    .replace(/\b\d{13}\b/g, '[JMBG]')
    .replace(/\b[\w.+\-]+@[\w\-]+\.\w+\b/gi, '[email]')
    .replace(/\b0[67]\d[\s\-\/]?\d{3}[\s\-\/]?\d{3,4}\b/g, '[tel]')
    .replace(/\b\+381[\s]?\d{2}[\s]?\d{3}[\s]?\d{3,4}\b/g, '[tel]')
    .replace(/\b\d{9}\b/g, '[PIB]');
}

function initChatSession() {
  currentChatSessionId = localStorage.getItem('vindex_session_id');
  if (!currentChatSessionId) {
    currentChatSessionId = _generateUUID();
    localStorage.setItem('vindex_session_id', currentChatSessionId);
  }
}

function newChat() {
  // Čisti ekran i polja
  document.getElementById('resp').classList.remove('show');
  document.getElementById('rb').innerHTML = '';
  var _cb = document.getElementById('rag-confidence-badge'); if (_cb) _cb.style.display='none';
  var _si = document.getElementById('rag-source-info'); if (_si) _si.style.display='none';
  ['qi','no','aitxt','aq'].forEach(function(id){ var el=document.getElementById(id); if(el) el.value=''; });
  // Resetuje stanje
  conversationHistory = [];
  _lastRawText = '';
  lastPitanje  = '';
  _followUpUsed = false;
  // Nova sesija
  currentChatSessionId = _generateUUID();
  localStorage.setItem('vindex_session_id', currentChatSessionId);
  // Čisti history panel
  _chatHistoryRows = [];
  var hist = document.getElementById('chat-hist');
  if (hist) { hist.innerHTML = ''; hist.style.display = 'none'; }
}

async function saveTurnToSupabase(userMsg, assistantMsg) {
  var sb = getSupabase();
  if (!sb || !currentSession || !currentChatSessionId) return;
  var uid = currentSession.user.id;
  try {
    await sb.from('conversations').insert([
      { user_id:uid, session_id:currentChatSessionId, role:'user',      content:_piiFilter(userMsg).substring(0,2000),      tab:activeTab },
      { user_id:uid, session_id:currentChatSessionId, role:'assistant', content:_piiFilter(assistantMsg).substring(0,3000), tab:activeTab }
    ]);
  } catch(e) { console.warn('[Vindex] saveTurn:', e.message); }
}

async function loadChatHistory() {
  var sb = getSupabase();
  if (!sb || !currentSession || !currentChatSessionId) return;
  try {
    var res = await sb.from('conversations')
      .select('role,content,tab,created_at')
      .eq('session_id', currentChatSessionId)
      .order('created_at', { ascending: true })
      .limit(20);
    if (res.error) throw res.error;
    _chatHistoryRows = res.data || [];
    // Obnovi conversationHistory (max 3 para za AI kontekst)
    conversationHistory = [];
    for (var i = 0; i + 1 < _chatHistoryRows.length; i += 2) {
      if (_chatHistoryRows[i].role === 'user' && _chatHistoryRows[i+1].role === 'assistant') {
        conversationHistory.push({ q: _chatHistoryRows[i].content, a: _chatHistoryRows[i+1].content.substring(0,600) });
      }
    }
    if (conversationHistory.length > 3) conversationHistory = conversationHistory.slice(-3);
    renderChatHistory(_chatHistoryRows);
  } catch(e) { console.warn('[Vindex] loadHistory:', e.message); }
}

function renderChatHistory(rows) {
  var hist = document.getElementById('chat-hist');
  if (!hist) return;
  // Grupiše u parove user/assistant
  var pairs = [];
  for (var i = 0; i + 1 < rows.length; i += 2) {
    if (rows[i].role === 'user' && rows[i+1].role === 'assistant') {
      pairs.push({ q: rows[i].content, a: rows[i+1].content });
    }
  }
  if (pairs.length === 0) { hist.style.display = 'none'; return; }
  hist.innerHTML = pairs.map(function(p) {
    var aShort = p.a.length > 180 ? p.a.substring(0, 180) + '\u2026' : p.a;
    return '<div class="chat-turn">'
      + '<div class="chat-q"><span class="chat-q-icon">\u2696</span>' + escHtml(p.q) + '</div>'
      + '<div class="chat-a">' + escHtml(aShort) + '</div>'
      + '</div>';
  }).join('');
  hist.style.display = 'block';
  hist.scrollTop = hist.scrollHeight;
  if (_cyrillicOn) cirilicaElement(hist);
}

// ─── Paywall ──────────────────────────────────────────────────────────────────
function showPaywall() {
  document.getElementById('paywall-modal').classList.add('open');
}
function closePaywall() {
  document.getElementById('paywall-modal').classList.remove('open');
}
function openSubscription() {
  closePaywall();
  if (STRIPE_URL) {
    window.open(STRIPE_URL, '_blank');
  } else {
    showToast('Za PRO pretplatu kontaktirajte: info@vindex.rs', 'info');
    setTimeout(function() {
      window.location.href = 'mailto:info@vindex.rs?subject=Pretplata%20Vindex%20AI';
    }, 800);
  }
}

// ─── EmailJS (zadržano) ───────────────────────────────────────────────────────
var EMAILJS_PUBLIC_KEY  = 'VAŠ_PUBLIC_KEY';
var EMAILJS_SERVICE_ID  = 'VAŠ_SERVICE_ID';
var EMAILJS_TEMPLATE_ID = 'VAŠ_TEMPLATE_ID';
if (EMAILJS_PUBLIC_KEY !== 'VAŠ_PUBLIC_KEY' && window.emailjs) {
  emailjs.init(EMAILJS_PUBLIC_KEY);
}

/* MOBILE MENU */
function toggleMenu() {
  var menu = document.getElementById('mobile-menu');
  var burger = document.getElementById('hamburger');
  menu.classList.toggle('open');
  burger.classList.toggle('open');
}
function closeMobileMenu() {
  document.getElementById('mobile-menu').classList.remove('open');
  document.getElementById('hamburger').classList.remove('open');
}

/* CURSOR */
var cursor = document.getElementById('cursor');
var ring   = document.getElementById('cursor-ring');
var cx = 0, cy = 0, rx = 0, ry = 0;
if (cursor) {
  document.addEventListener('mousemove', function(e) { cx=e.clientX; cy=e.clientY; cursor.style.left=cx+'px'; cursor.style.top=cy+'px'; });
  function animRing() { rx+=(cx-rx)*0.1; ry+=(cy-ry)*0.1; ring.style.left=rx+'px'; ring.style.top=ry+'px'; requestAnimationFrame(animRing); }
  animRing();
  document.querySelectorAll('a,button,.feat-card,.tc,.plat-card,.val-row').forEach(function(el){el.addEventListener('mouseenter',function(){document.body.classList.add('hovering');});el.addEventListener('mouseleave',function(){document.body.classList.remove('hovering');});});
  document.querySelectorAll('.magnetic').forEach(function(el){el.addEventListener('mousemove',function(e){var r=el.getBoundingClientRect();var x=e.clientX-r.left-r.width/2;var y=e.clientY-r.top-r.height/2;el.style.transform='translate('+(x*0.22)+'px,'+(y*0.22)+'px)';});el.addEventListener('mouseleave',function(){el.style.transform='';});});
}

/* CANVAS */
var cv=document.getElementById('cv'),ctx=cv.getContext('2d');
var W=cv.width=window.innerWidth,H=cv.height=window.innerHeight;
var mx=W/2,my=H/2;
window.addEventListener('resize',function(){W=cv.width=window.innerWidth;H=cv.height=window.innerHeight;});
window.addEventListener('mousemove',function(e){mx=e.clientX;my=e.clientY;});
var pts=[];
for(var i=0;i<60;i++){pts.push({x:Math.random()*W,y:Math.random()*H,vx:(Math.random()-.5)*.18,vy:(Math.random()-.5)*.18,t:Math.random()*Math.PI*2,r:Math.random()*.8+.25});}
function drawBg(){var isL=document.body.classList.contains('light-theme');var rgb=isL?'0,153,187':'0,212,255';ctx.clearRect(0,0,W,H);ctx.strokeStyle='rgba('+rgb+','+(isL?'0.04':'0.048')+')';ctx.lineWidth=1;for(var x=0;x<W;x+=80){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,H);ctx.stroke();}for(var y=0;y<H;y+=80){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke();}var g=ctx.createRadialGradient(mx,my,0,mx,my,420);g.addColorStop(0,'rgba('+rgb+','+(isL?'0.05':'0.07')+')');g.addColorStop(1,'transparent');ctx.fillStyle=g;ctx.fillRect(0,0,W,H);for(var i=0;i<pts.length;i++){var p=pts[i];p.x+=p.vx;p.y+=p.vy;p.t+=.007;if(p.x<0)p.x=W;if(p.x>W)p.x=0;if(p.y<0)p.y=H;if(p.y>H)p.y=0;var rawA=.4+.4*Math.sin(p.t);var a=isL?Math.max(0.12,Math.min(0.22,rawA*.28)):Math.max(0.35,Math.min(0.75,rawA*.75));ctx.beginPath();ctx.arc(p.x,p.y,p.r+.5,0,Math.PI*2);ctx.fillStyle='rgba('+rgb+','+a+')';ctx.fill();for(var j=i+1;j<pts.length;j++){var q=pts[j],d=Math.hypot(p.x-q.x,p.y-q.y);if(d<160){ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);ctx.strokeStyle='rgba('+rgb+','+((isL?0.09:0.18)*(1-d/160))+')';ctx.lineWidth=.7;ctx.stroke();}}}requestAnimationFrame(drawBg);}
drawBg();

/* SPHERE */
(function(){
  var canvas=document.getElementById('sphereCanvas');
  if(!canvas) return;
  var c=canvas.getContext('2d'),wrap=document.getElementById('sphereWrap');
  function resize(){canvas.width=wrap.clientWidth;canvas.height=wrap.clientHeight;}
  resize();window.addEventListener('resize',resize);
  var laws=['ZOO čl.200','Zakon o radu','čl.179','KZ čl.135','ZPP čl.10','ZOO čl.155','čl.53','Nasleđivanje','čl.89','Porodični zakon','čl.72','ZKP čl.220','čl.40','Zakon o svojini','čl.205','ZOO čl.262','čl.147','Zakon o PDV','čl.18','Ustav čl.36','ZOR čl.76','čl.111','Privredna društva','čl.55','čl.182','Porodični zakon','ZOO čl.354'];
  var spts=[];
  for(var i=0;i<laws.length;i++){var phi=Math.acos(1-2*(i+.5)/laws.length),theta=Math.PI*(1+Math.sqrt(5))*i;spts.push({ox:Math.sin(phi)*Math.cos(theta),oy:Math.sin(phi)*Math.sin(theta),oz:Math.cos(phi),label:laws[i],pulse:Math.random()*Math.PI*2});}
  var angle=0,smx=0,smy=0;
  canvas.addEventListener('mousemove',function(e){var r=canvas.getBoundingClientRect();smx=(e.clientX-r.left-canvas.width/2)/canvas.width*0.8;smy=(e.clientY-r.top-canvas.height/2)/canvas.height*0.8;});
  function draw(){c.clearRect(0,0,canvas.width,canvas.height);var cx2=canvas.width/2,cy2=canvas.height/2,R=Math.min(canvas.width,canvas.height)*0.44;angle+=0.004;var cosX=Math.cos(smy*0.5),sinX=Math.sin(smy*0.5),cosY=Math.cos(angle+smx*0.5),sinY=Math.sin(angle+smx*0.5);var proj=spts.map(function(p,idx){var x1=p.ox*cosY+p.oz*sinY,z1=-p.ox*sinY+p.oz*cosY;var y2=p.oy*cosX-z1*sinX,z2=p.oy*sinX+z1*cosX;p.pulse+=0.025;var sc=1/(2-z2);return{sx:cx2+x1*R*sc,sy:cy2+y2*R*sc,z:z2,label:p.label,pulse:p.pulse,idx:idx};}).sort(function(a,b){return a.z-b.z;});proj.forEach(function(a,i){if(a.z<0)return;proj.slice(i+1).forEach(function(b){if(b.z<0)return;var d=Math.hypot(a.sx-b.sx,a.sy-b.sy);if(d<95){var al=(1-d/95)*0.09*((a.z+b.z)/2+0.5);c.beginPath();c.moveTo(a.sx,a.sy);c.lineTo(b.sx,b.sy);c.strokeStyle='rgba(74,168,255,'+al+')';c.lineWidth=0.6;c.stroke();}});});proj.forEach(function(p){var depth=(p.z+1)/2,al=Math.max(0,depth),pulse=0.7+0.3*Math.sin(p.pulse),isGold=p.idx%5===0;c.beginPath();c.arc(p.sx,p.sy,2+depth*2.5,0,Math.PI*2);c.fillStyle=isGold?'rgba(201,168,76,'+(al*pulse*0.9)+')':'rgba(74,168,255,'+(al*pulse*0.88)+')';c.fill();if(depth>0.22){c.font='300 '+(10+depth*5)+'px JetBrains Mono,monospace';c.fillStyle=isGold?'rgba(201,168,76,'+(al*0.88)+')':'rgba(150,210,255,'+(al*0.84)+')';c.fillText(p.label,p.sx+6,p.sy-4);}});requestAnimationFrame(draw);}
  draw();
})();

/* fillQ */
function fillQ(q) {
  document.querySelectorAll('.t-tab').forEach(function(x){x.classList.remove('active');});
  var qtab = document.querySelector('.t-tab[onclick*="\'q\'"]');
  if (qtab) qtab.classList.add('active');
  ['q','n','a','s'].forEach(function(id){document.getElementById('tab-'+id).style.display='none';});
  document.getElementById('tab-q').style.display = 'block';
  activeTab = 'q';
  document.getElementById('btn-lbl').textContent = 'Pretraži pravnu bazu';
  document.getElementById('resp').classList.remove('show');
  document.getElementById('podnesak-preview').style.display='none';
  document.getElementById('qi').value = q;
  document.getElementById('qi').focus();
}

/* MARQUEE */
var mq1=['Zakon o obligacionim odnosima','Zakon o radu','Krivični zakonik','Zakon o parničnom postupku','Porodični zakon','Zakon o nasleđivanju','Zakon o privrednim drustvima','Ustav Republike Srbije'];
var mq2=['Tačnost - Preciznost - Brzina','AI za srpsko pravo','Svi važeći zakoni Republike Srbije','Ocena pouzdanosti','Vindex AI - Beta','Advokat 2.0','Srpski pravni sistem'];
function buildTrack(id,items){var t=document.getElementById(id);if(!t)return;var all=items.concat(items).concat(items).concat(items);t.innerHTML=all.map(function(x){return '<span class="marquee-item">'+x+'<span class="marquee-sep"> &middot; </span></span>';}).join('');}
buildTrack('mq1',mq1);buildTrack('mq2',mq2);

/* COUNTER ANIMATION */
var countersStarted = false;
var cObs = new IntersectionObserver(function(entries){
  if(entries[0].isIntersecting && !countersStarted){
    countersStarted = true;
    document.querySelectorAll('[data-target]').forEach(function(el){
      var target=parseInt(el.dataset.target),suf=el.dataset.suf||'',dur=2000,start=performance.now();
      function upd(now){var t=Math.min((now-start)/dur,1),ease=1-Math.pow(1-t,3);el.innerHTML=Math.floor(ease*target).toLocaleString('sr')+'<span class="acc">'+suf+'</span>';if(t<1)requestAnimationFrame(upd);}
      requestAnimationFrame(upd);
    });
  }
},{threshold:0.5});
var heroSec = document.getElementById('hero');
if(heroSec) cObs.observe(heroSec);

/* ── KONTROLNI CENTAR ────────────────────────────────────────── */
function _dashGreeting(){var h=new Date().getHours();if(h<12)return'Dobro jutro';if(h<18)return'Dobar dan';return'Dobro veče';}
function _dashFormatDate(){var d=new Date();var dn=['nedeljа','ponedeljak','utorak','sreda','četvrtak','petak','subota'];var mn=['januar','februar','mart','april','maj','jun','jul','avgust','septembar','oktobar','novembar','decembar'];return dn[d.getDay()]+', '+d.getDate()+'. '+mn[d.getMonth()]+' '+d.getFullYear()+'.';}

var _kcAnimId = null;
function kcConstellationInit() {
  if (_kcAnimId) { cancelAnimationFrame(_kcAnimId); _kcAnimId = null; }
  var canvas = document.getElementById('kc-inline-canvas');
  if (!canvas) return;
  var ctx = canvas.getContext('2d');
  var S = 390;
  canvas.width  = S;
  canvas.height = S;
  var cx = S / 2, cy = S / 2, R = S * 0.46;
  var t0 = Date.now();

  function p3(lat, lon, angle) {
    var phi = (90 - lat) * Math.PI / 180;
    var th  = lon * Math.PI / 180;
    var x = Math.sin(phi) * Math.cos(th);
    var y = Math.cos(phi);
    var z = Math.sin(phi) * Math.sin(th);
    var rx = x * Math.cos(angle) - z * Math.sin(angle);
    var rz = x * Math.sin(angle) + z * Math.cos(angle);
    return { px: cx + rx * R, py: cy - y * R, vis: rz };
  }

  function drawLine(pts, baseAlpha, width) {
    for (var i = 0; i < pts.length - 1; i++) {
      var a = pts[i], b = pts[i+1];
      var al = Math.max(0, (a.vis + b.vis) / 2);
      if (al < 0) continue;
      ctx.beginPath();
      ctx.moveTo(a.px, a.py);
      ctx.lineTo(b.px, b.py);
      ctx.strokeStyle = 'rgba(0,212,255,' + (baseAlpha * Math.min(1, al + 0.12)) + ')';
      ctx.lineWidth = width;
      ctx.stroke();
    }
  }

  function drawOrbitalRing(angle, tilt, size, alpha, animAngle) {
    var steps = 120;
    ctx.beginPath();
    for (var i = 0; i <= steps; i++) {
      var a = (i / steps) * Math.PI * 2 + animAngle;
      var ex = Math.cos(a) * size;
      var ey = Math.sin(a) * size * Math.sin(tilt);
      var px = cx + ex;
      var py = cy + ey;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.strokeStyle = 'rgba(0,212,255,' + alpha + ')';
    ctx.lineWidth = 1.2;
    ctx.shadowColor = 'rgba(0,212,255,0.4)';
    ctx.shadowBlur = 6;
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  function draw() {
    if (!canvas.isConnected) { _kcAnimId = null; return; }
    ctx.clearRect(0, 0, S, S);
    var e = (Date.now() - t0) / 1000;
    var angle = e * (Math.PI * 2 / 40);

    /* Meridijani */
    for (var lon = 0; lon < 180; lon += 30) {
      var pts = [];
      for (var lat = -90; lat <= 90; lat += 4) pts.push(p3(lat, lon, angle));
      drawLine(pts, 0.3, 0.7);
    }

    /* Paralele */
    var lats = [-60, -30, 0, 30, 60];
    for (var li = 0; li < lats.length; li++) {
      var pts2 = [];
      for (var lo = 0; lo <= 360; lo += 4) pts2.push(p3(lats[li], lo, angle));
      var isEq = lats[li] === 0;
      drawLine(pts2, isEq ? 0.55 : 0.28, isEq ? 1.1 : 0.7);
    }

    /* Tačke na presečištima */
    for (var la = -60; la <= 60; la += 30) {
      for (var lo2 = 0; lo2 < 360; lo2 += 30) {
        var pt = p3(la, lo2, angle);
        if (pt.vis > 0.05) {
          ctx.beginPath();
          ctx.arc(pt.px, pt.py, 1.8, 0, Math.PI * 2);
          ctx.fillStyle = 'rgba(0,212,255,' + Math.min(0.85, pt.vis * 0.7 + 0.2) + ')';
          ctx.fill();
        }
      }
    }

    /* Orbitalni prsten 1 — spolja */
    drawOrbitalRing(angle, Math.PI * 0.22, R * 1.22, 0.5, e * 0.4);
    /* Orbitalni prsten 2 — ugaonut */
    drawOrbitalRing(angle, Math.PI * 0.15, R * 1.13, 0.28, -e * 0.28 + 1.1);

    _kcAnimId = requestAnimationFrame(draw);
  }

  if (window._kcResizeH) window.removeEventListener('resize', window._kcResizeH);
  window._kcResizeH = function() {
    var el = document.getElementById('kc-inline-canvas');
    if (el) { el.width = S; el.height = S; }
  };
  window.addEventListener('resize', window._kcResizeH);
  draw();
}

async function dash_load(){
  if(!currentSession){document.getElementById('kc-body').innerHTML='<div class="kc-empty">Prijavite se da biste videli kontrolni centar.</div>';return;}
  piTrack('dashboard','view');
  var body=document.getElementById('kc-body');
  if(!body)return;
  body.innerHTML='<div class="kc-loading">Učitavam...</div>';
  try{
    var hdr={'Authorization':'Bearer '+currentSession.access_token};
    var [r,br,inR]=await Promise.all([
      fetch(BASE_URL+'/api/dashboard/command-center',{headers:hdr}),
      fetch(BASE_URL+'/billing/pregled',{headers:hdr}).catch(function(){return null;}),
      fetch(BASE_URL+'/api/inbox',{headers:hdr}).catch(function(){return null;})
    ]);
    if(!r.ok)throw new Error('HTTP '+r.status);
    var d=await r.json();
    var bd=br&&br.ok?await br.json():null;
    var inboxData=inR&&inR.ok?await inR.json():null;
    body.innerHTML=_dashRender(d,bd,inboxData);
    if(window.lucide)lucide.createIcons();
    kcConstellationInit();
    _kcStartClock();
    notif_load();
  }catch(e){
    body.innerHTML='<div class="kc-empty">Greška pri učitavanju. <span onclick="dash_load()" style="color:#4aa8ff;cursor:pointer;">Pokušaj ponovo</span></div>';
  }
}

var _kcClockInterval = null;
function _kcStartClock() {
  if (_kcClockInterval) clearInterval(_kcClockInterval);
  function _tick() {
    var el = document.getElementById('kc-live-clock');
    if (!el) { clearInterval(_kcClockInterval); _kcClockInterval = null; return; }
    var d = new Date();
    el.textContent = ('0'+d.getHours()).slice(-2)+':'+('0'+d.getMinutes()).slice(-2)+':'+('0'+d.getSeconds()).slice(-2);
  }
  _tick();
  _kcClockInterval = setInterval(_tick, 1000);
}

function _fmtRSD(v){var n=Math.round(v||0);if(n>=1000000)return(n/1000000).toFixed(1)+'M';if(n>=1000)return(n/1000).toFixed(0)+'k';return String(n);}
function _dashRender(d,bd,inboxData){
  var today=new Date().toISOString().slice(0,10);
  var p2=new Date(Date.now()+2*86400000).toISOString().slice(0,10);
  var html='';
  var uName=currentUser?(currentUser.email||'').split('@')[0]:'';

  var hitniCount=(d.hitni_rokovi||[]).length;
  var rocistaCount=(d.danasnja_rocista||[]).length;
  var visokRizikCount=(d.predmeti_visok_rizik||[]).length;
  var neobracunato=bd?_fmtRSD(bd.neobracunato||0):'—';

  // ── TOP BAR ────────────────────────────────────────────────────
  html+='<div class="kc-topbar">';
  html+='<div class="kc-topbar-left">';
  html+='<div class="kc-greeting">'+_dashGreeting()+(uName?', '+escHtml(uName):'')+'. </div>';
  html+='<div class="kc-date">'+_dashFormatDate()+'</div>';
  html+='</div>';
  html+='<div class="kc-topbar-right">';
  html+='<div class="kc-search" title="Globalna pretraga — dolazi uskoro"><span class="kc-search-icon">⌕</span><span class="kc-search-ph">Pretraži predmete, klijente...</span><span class="kc-search-kbd">⌘K</span></div>';
  html+='<button class="kc-new-btn" onclick="intakeOtvori()">+ Novi predmet</button>';
  html+='</div></div>';

  // ── 4 KPI KARTICE ──────────────────────────────────────────────
  html+='<div class="kc-kpi-row">';
  html+='<div class="kc-kpi"><div class="kc-kpi-n">'+(d.ukupno_aktivnih||0)+'</div><div class="kc-kpi-l">Aktivnih<br>predmeta</div></div>';
  html+='<div class="kc-kpi'+(hitniCount>0?' warn':'')+'"><div class="kc-kpi-n'+(hitniCount>0?' warn':'')+'">'+hitniCount+'</div><div class="kc-kpi-l">Hitnih<br>rokova</div></div>';
  html+='<div class="kc-kpi'+(rocistaCount>0?' warn':'')+'"><div class="kc-kpi-n'+(rocistaCount>0?' warn':'')+'">'+rocistaCount+'</div><div class="kc-kpi-l">Ročišta<br>danas</div></div>';
  html+='<div class="kc-kpi"><div class="kc-kpi-n">'+neobracunato+'</div><div class="kc-kpi-l">Nenaplaćeno<br>RSD</div></div>';
  html+='</div>';

  // ── AI PREPORUKE / SUMMARY ─────────────────────────────────────
  var preporuke=d.ai_preporuke||[];
  if(preporuke.length){
    html+='<div class="kc-preporuke">';
    preporuke.forEach(function(p){html+='<div class="kc-prep-item">'+escHtml(p)+'</div>';});
    html+='</div>';
  }else if(d.summary){
    html+='<div class="kc-summary">'+escHtml(d.summary)+'</div>';
  }

  // ── 2-COLUMN MAIN ──────────────────────────────────────────────
  html+='<div class="kc-two-col">';

  // LEVA KOLONA: prioritetni predmeti + neaktivni + billing
  html+='<div class="kc-col">';

  var prioritetni=[];
  (d.predmeti_visok_rizik||[]).slice(0,4).forEach(function(p){
    prioritetni.push({id:p.predmet_id,naziv:p.predmet_naziv||'Predmet',sub:(p.faktori||[]).slice(0,2).join(' · '),dot:'hitan'});
  });
  (d.pad_procene||[]).slice(0,3).forEach(function(p){
    prioritetni.push({id:p.predmet_id,naziv:p.predmet_naziv||'Predmet',sub:(p.prethodni_rizik||'?')+' → '+(p.trenutni_rizik||'?'),dot:'bitan'});
  });

  html+='<div class="kc-section"><div class="kc-section-hd"><span>Prioritetni predmeti</span><span class="kc-section-hd-count">'+prioritetni.length+'</span></div>';
  if(!prioritetni.length){
    html+='<div class="kc-empty">Nema predmeta koji zahtevaju hitnu pažnju</div>';
  }else{
    prioritetni.forEach(function(p){
      html+='<div class="kc-row" onclick="_dashGoToPredmet(\''+escHtml(p.id)+'\')">';
      html+='<div class="kc-row-dot '+p.dot+'"></div>';
      html+='<div class="kc-row-main"><div class="kc-row-naziv">'+escHtml(p.naziv)+'</div>';
      if(p.sub)html+='<div class="kc-row-sub">'+escHtml(p.sub)+'</div>';
      html+='</div><div class="kc-row-arrow">→</div></div>';
    });
  }
  html+='</div>';

  var neakt=(d.neaktivni_30_dana||[]).slice(0,4);
  if(neakt.length){
    html+='<div class="kc-section"><div class="kc-section-hd"><span>Bez aktivnosti 30+ dana</span><span class="kc-section-hd-count">'+neakt.length+'</span></div>';
    neakt.forEach(function(p){
      html+='<div class="kc-row" onclick="_dashGoToPredmet(\''+escHtml(p.predmet_id)+'\')">';
      html+='<div class="kc-row-dot bitan"></div>';
      html+='<div class="kc-row-main"><div class="kc-row-naziv">'+escHtml(p.naziv||'Predmet')+'</div><div class="kc-row-sub">Bez aktivnosti od '+escHtml(p.poslednja_izmena||'—')+'</div></div>';
      html+='<div class="kc-row-arrow">→</div></div>';
    });
    html+='</div>';
  }

  if(bd){
    html+='<div class="kc-section"><div class="kc-section-hd"><span>Naplata — '+escHtml(bd.mesec||'')+'</span></div>';
    html+='<div class="kc-billing-row">';
    html+='<div class="billing-kc-kpi"><div class="billing-kc-n">'+_fmtRSD(bd.ukupno_unoseno||0)+'</div><div class="billing-kc-l">Uneseno<br>RSD</div></div>';
    html+='<div class="billing-kc-kpi"><div class="billing-kc-n'+(((bd.neobracunato||0)>0)?' warn':'')+'">'+_fmtRSD(bd.neobracunato||0)+'</div><div class="billing-kc-l">Nenaplaćeno<br>RSD</div></div>';
    html+='<div class="billing-kc-kpi"><div class="billing-kc-n">'+_fmtRSD(bd.naplaceno||0)+'</div><div class="billing-kc-l">Naplaćeno<br>RSD</div></div>';
    html+='</div></div>';
  }
  html+='</div>';

  // DESNA KOLONA: rokovi 7 dana + ročišta + novi dokumenti
  html+='<div class="kc-col">';

  var rokovi7=d.rokovi_7_dana||[];
  html+='<div class="kc-section"><div class="kc-section-hd"><span>Rokovi — 7 dana</span><span class="kc-section-hd-count">'+rokovi7.length+'</span></div>';
  if(!rokovi7.length){
    html+='<div class="kc-empty">Nema nadolazećih rokova</div>';
  }else{
    rokovi7.slice(0,8).forEach(function(r){
      var isToday=r.datum_iso===today;
      var isUrgent=r.datum_iso<=p2;
      var dot=(isToday||isUrgent)?'hitan':(r.vaznost==='bitan'?'bitan':'info');
      var datumLbl=isToday?'DANAS':r.datum_iso;
      html+='<div class="kc-row" onclick="_dashGoToPredmet(\''+escHtml(r.predmet_id)+'\')">';
      html+='<div class="kc-row-dot '+dot+'"></div>';
      html+='<div class="kc-row-main"><div class="kc-row-naziv">'+escHtml(r.predmet_naziv||'Predmet')+'</div><div class="kc-row-sub">'+escHtml(r.dogadjaj||'')+'</div></div>';
      html+='<div class="kc-row-datum">'+escHtml(datumLbl)+'</div><div class="kc-row-arrow">→</div></div>';
    });
  }
  html+='</div>';

  var rocista=d.danasnja_rocista||[];
  if(rocista.length){
    html+='<div class="kc-section"><div class="kc-section-hd"><span>Ročišta danas</span><span class="kc-section-hd-count">'+rocista.length+'</span></div>';
    rocista.forEach(function(r){
      html+='<div class="kc-row" onclick="_dashGoToPredmet(\''+escHtml(r.predmet_id)+'\')">';
      html+='<div class="kc-row-dot hitan"></div>';
      html+='<div class="kc-row-main"><div class="kc-row-naziv">'+escHtml(r.predmet_naziv||'Predmet')+'</div><div class="kc-row-sub">'+escHtml(r.sud||'Sud nije navedeno')+(r.vreme?' — '+escHtml(r.vreme):'')+'</div></div>';
      html+='<div class="kc-row-arrow">→</div></div>';
    });
    html+='</div>';
  }

  var noviDok=(d.novi_dokumenti||[]).slice(0,4);
  if(noviDok.length){
    html+='<div class="kc-section"><div class="kc-section-hd"><span>Novi dokumenti (24h)</span><span class="kc-section-hd-count">'+noviDok.length+'</span></div>';
    noviDok.forEach(function(dok){
      html+='<div class="kc-row" onclick="_dashGoToPredmet(\''+escHtml(dok.predmet_id)+'\')">';
      html+='<div class="kc-row-dot info"></div>';
      html+='<div class="kc-row-main"><div class="kc-row-naziv">'+escHtml(dok.naziv_fajla||'Dokument')+'</div><div class="kc-row-sub">'+escHtml(dok.predmet_naziv||'—')+'</div></div>';
      html+='<div class="kc-row-arrow">→</div></div>';
    });
    html+='</div>';
  }

  html+='</div>'; // end desna kolona
  html+='</div>'; // end kc-two-col

  // ── AI ALATI ──────────────────────────────────────────────────
  html+='<div class="kc-ai-section">';
  html+='<div class="kc-ai-section-hd">AI Alati</div>';
  html+='<div class="kc-ai-grid">';
  html+='<div class="kc-ai-card" onclick="openAITool(\'q\')">';
  html+='<div class="kc-ai-card-top"><span class="kc-ai-card-icon">⚖</span><span class="kc-ai-card-title">Istraživanje zakona</span></div>';
  html+='<div class="kc-ai-card-desc">Postavi pravno pitanje. Dobij zakon, član i citat iz srpske pravne baze.</div>';
  html+='<button class="kc-ai-card-cta">Otvori →</button></div>';
  html+='<div class="kc-ai-card" onclick="openAITool(\'a\')">';
  html+='<div class="kc-ai-card-top"><span class="kc-ai-card-icon">📄</span><span class="kc-ai-card-title">Analiza dokumenta</span></div>';
  html+='<div class="kc-ai-card-desc">Učitaj dokument. AI izvlači ključne klauzule, rizike i preporučene korake.</div>';
  html+='<button class="kc-ai-card-cta">Otvori →</button></div>';
  html+='<div class="kc-ai-card" onclick="openAITool(\'s\')">';
  html+='<div class="kc-ai-card-top"><span class="kc-ai-card-icon">🏛</span><span class="kc-ai-card-title">Sudska praksa</span></div>';
  html+='<div class="kc-ai-card-desc">Pretraži relevantne presude srpskih sudova za tvoj predmet.</div>';
  html+='<button class="kc-ai-card-cta">Otvori →</button></div>';
  html+='<div class="kc-ai-card pro" onclick="openAITool(\'n\')">';
  html+='<div class="kc-ai-card-top"><span class="kc-ai-card-icon">✍</span><span class="kc-ai-card-title">Nacrti i podnesci</span></div>';
  html+='<div class="kc-ai-card-desc">AI generiše tužbu, žalbu, ugovor ili drugi pravni dokument za predmet.</div>';
  html+='<button class="kc-ai-card-cta">Otvori →</button></div>';
  html+='</div></div>';

  return html;
}

/* ── FAZA 1 — Komandni centar panel components ─────────────────── */
function _kcIco(name, cls) {
  return '<i data-lucide="'+name+'"'+(cls?' class="'+cls+'"':'')+' style="display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;"></i>';
}

function _kcRelTime(iso) {
  if (!iso) return '';
  var diff = Date.now() - new Date(iso).getTime();
  var h = Math.floor(diff / 3600000);
  if (h < 1) return 'Maloprije';
  if (h < 24) return 'Pre ' + h + 'h';
  var days = Math.floor(h / 24);
  return 'Pre ' + days + (days === 1 ? ' dan' : ' dana');
}

function _kcDaysUntil(iso) {
  if (!iso) return null;
  var diff = new Date(iso).getTime() - Date.now();
  return Math.ceil(diff / 86400000);
}

function _kcPanelAktivni(d) {
  var top = d.top_aktivni_predmeti || [];
  var visokRizikIds = (d.predmeti_visok_rizik||[]).reduce(function(m,r){m[r.predmet_id]=1;return m;},{});
  var hitniIds      = (d.hitni_rokovi||[]).reduce(function(m,r){m[r.predmet_id]=1;return m;},{});
  var rokByPredmet  = (d.rokovi_7_dana||[]).reduce(function(m,r){if(!m[r.predmet_id])m[r.predmet_id]=r.datum_iso;return m;},{});
  var ukupno = d.ukupno_aktivnih || 0;
  var h = '<div class="kc-panel" id="kc-panel-aktivni">';
  h += '<div class="kc-panel-hd"><span class="kc-panel-title">'+_kcIco('briefcase')+'Aktivni predmeti</span>';
  h += '<span class="kc-panel-hd-cta" onclick="setTab(document.getElementById(\'tab-btn-p\'),\'p\')">Vidi sve →</span></div>';
  if (!top.length) {
    h += '<div class="kc-panel-empty">';
    h += '<span class="kc-panel-empty-ico">'+_kcIco('briefcase')+'</span>';
    h += '<span class="kc-panel-empty-title">Nema aktivnih predmeta</span>';
    h += '</div>';
  } else {
    top.forEach(function(p) {
      var isRisk  = visokRizikIds[p.id];
      var isHitni = hitniIds[p.id];
      var icoName = isRisk ? 'alert-triangle' : (isHitni ? 'alert-circle' : 'check-circle');
      var icoCls  = isRisk ? 'kc-ico-danger' : (isHitni ? 'kc-ico-warn' : 'kc-ico-ok');
      var rokIso  = rokByPredmet[p.id];
      var rokDays = rokIso ? _kcDaysUntil(rokIso) : null;
      var rokTxt  = rokDays !== null ? (rokDays <= 0 ? 'Danas' : 'Rok: ' + rokDays + (rokDays === 1 ? ' dan' : ' dana')) : '';
      h += '<div class="kc-panel-row" onclick="_dashGoToPredmet(\''+escHtml(p.id)+'\')">';
      h += '<span class="kc-row-ico '+icoCls+'">'+_kcIco(icoName)+'</span>';
      h += '<div class="kc-panel-row-info">';
      h += '<div class="kc-panel-row-top"><span class="kc-panel-row-naziv">'+escHtml(p.naziv||'—')+'</span>';
      if (rokTxt) h += '<span class="kc-panel-row-ts">'+escHtml(rokTxt)+'</span>';
      h += '</div>';
      h += '<div class="kc-panel-row-meta">'+escHtml(p.status||'aktivan')+(p.tip?' · '+escHtml(p.tip):'')+'</div>';
      h += '</div></div>';
    });
    if (ukupno > top.length) {
      var jos = ukupno - top.length;
      h += '<div class="kc-panel-expand" onclick="setTab(document.getElementById(\'tab-btn-p\'),\'p\')">Još '+jos+' '+(jos===1?'predmet':'predmeta')+' ▾</div>';
    }
  }
  h += '</div>';
  return h;
}

function _kcPanelRokovi(d) {
  var rocista  = (d.danasnja_rocista||[]).slice(0,3);
  var hitniRok = (d.hitni_rokovi||[]).slice(0,3);
  var rokovi7  = (d.rokovi_7_dana||[]).slice(0,3);
  var hasData  = rocista.length || hitniRok.length || rokovi7.length;
  var h = '<div class="kc-panel" id="kc-panel-rokovi">';
  h += '<div class="kc-panel-hd"><span class="kc-panel-title">'+_kcIco('calendar-clock')+'Današnji rokovi</span>';
  h += '<span class="kc-panel-hd-cta" onclick="setTab(document.getElementById(\'tab-btn-kal\'),\'kal\')">Vidi sve →</span></div>';
  if (!hasData) {
    h += '<div class="kc-panel-empty">';
    h += '<span class="kc-panel-empty-ico">'+_kcIco('calendar-x')+'</span>';
    h += '<span class="kc-panel-empty-title">Nema rokova danas.</span>';
    h += '<span class="kc-panel-empty-sub">Odlično, sve je pod kontrolom.</span>';
    h += '</div>';
  } else {
    rocista.forEach(function(r) {
      h += '<div class="kc-panel-row" onclick="_dashGoToPredmet(\''+escHtml(r.predmet_id)+'\')">';
      h += '<span class="kc-row-ico kc-ico-warn">'+_kcIco('gavel')+'</span>';
      h += '<div class="kc-panel-row-info">';
      h += '<div class="kc-panel-row-top"><span class="kc-panel-row-naziv">'+escHtml(r.predmet_naziv||'Predmet')+'</span>';
      if (r.vreme) h += '<span class="kc-panel-row-ts">'+escHtml(r.vreme)+'</span>';
      h += '</div>';
      h += '<div class="kc-panel-row-meta">Ročište'+(r.sud?' · '+escHtml(r.sud):'')+'</div>';
      h += '</div></div>';
    });
    hitniRok.forEach(function(r) {
      h += '<div class="kc-panel-row" onclick="_dashGoToPredmet(\''+escHtml(r.predmet_id)+'\')">';
      h += '<span class="kc-row-ico kc-ico-danger">'+_kcIco('alert-triangle')+'</span>';
      h += '<div class="kc-panel-row-info">';
      h += '<div class="kc-panel-row-top"><span class="kc-panel-row-naziv">'+escHtml(r.dogadjaj||'Rok')+'</span>';
      h += '<span class="kc-panel-row-ts">'+escHtml(r.datum_iso||'—')+'</span></div>';
      h += '<div class="kc-panel-row-meta">'+escHtml(r.predmet_naziv||'—')+'</div>';
      h += '</div></div>';
    });
    if (!rocista.length && !hitniRok.length) {
      rokovi7.forEach(function(r) {
        h += '<div class="kc-panel-row" onclick="_dashGoToPredmet(\''+escHtml(r.predmet_id)+'\')">';
        h += '<span class="kc-row-ico kc-ico-teal">'+_kcIco('calendar-clock')+'</span>';
        h += '<div class="kc-panel-row-info">';
        h += '<div class="kc-panel-row-top"><span class="kc-panel-row-naziv">'+escHtml(r.dogadjaj||'Rok')+'</span>';
        h += '<span class="kc-panel-row-ts">'+escHtml(r.datum_iso||'—')+'</span></div>';
        h += '<div class="kc-panel-row-meta">'+escHtml(r.predmet_naziv||'—')+'</div>';
        h += '</div></div>';
      });
    }
  }
  h += '</div>';
  return h;
}

function _kcPanelPreporuke(d) {
  var preporuke = d.ai_preporuke || [];
  var h = '<div class="kc-panel" id="kc-panel-preporuke">';
  h += '<div class="kc-panel-hd"><span class="kc-panel-title">'+_kcIco('lightbulb')+'AI preporuke</span>';
  h += '<span class="kc-panel-hd-cta" onclick="setTab(document.getElementById(\'tab-btn-alati\'),\'alati\')">Vidi sve →</span></div>';
  if (!preporuke.length) {
    h += '<div class="kc-panel-empty">';
    h += '<span class="kc-panel-empty-ico">'+_kcIco('check-circle')+'</span>';
    h += '<span class="kc-panel-empty-title">Sve je pod kontrolom</span>';
    h += '<span class="kc-panel-empty-sub">Nema hitnih preporuka.</span>';
    h += '</div>';
  } else {
    preporuke.slice(0,3).forEach(function(p) {
      var txt = p.toLowerCase();
      var icoName, icoCls;
      if (txt.indexOf('rizik') >= 0 || txt.indexOf('pogor') >= 0) {
        icoName = 'alert-triangle'; icoCls = 'kc-ico-orange';
      } else if (txt.indexOf('ročiš') >= 0 || txt.indexOf('rok') >= 0) {
        icoName = 'calendar-clock'; icoCls = 'kc-ico-teal';
      } else if (txt.indexOf('dokument') >= 0) {
        icoName = 'file-text'; icoCls = 'kc-ico-teal';
      } else {
        icoName = 'scale'; icoCls = 'kc-ico-teal';
      }
      h += '<div class="kc-panel-row kc-panel-preporuka">';
      h += '<span class="kc-row-ico '+icoCls+'">'+_kcIco(icoName)+'</span>';
      h += '<div class="kc-panel-row-info">';
      h += '<div class="kc-panel-row-top"><span class="kc-panel-row-naziv" style="white-space:normal;line-height:1.35">'+escHtml(p)+'</span></div>';
      h += '</div></div>';
    });
  }
  h += '</div>';
  return h;
}

function _kcPanelAktivnosti(d) {
  var acts = [];
  (d.danasnja_rocista||[]).slice(0,2).forEach(function(r){
    acts.push({ico:'gavel',cls:'kc-ico-warn',txt:'Ročište — '+(r.predmet_naziv||'Predmet'),sub:'Sud'+( r.sud?' · '+r.sud:''),ts:r.vreme||'',id:r.predmet_id});
  });
  (d.novi_dokumenti||[]).slice(0,2).forEach(function(dok){
    if(acts.length<4)acts.push({ico:'file-text',cls:'kc-ico-teal',txt:dok.naziv_fajla||'Dokument',sub:dok.predmet_naziv||'—',ts:_kcRelTime(dok.created_at),id:dok.predmet_id});
  });
  (d.pad_procene||[]).slice(0,1).forEach(function(p){
    if(acts.length<4)acts.push({ico:'alert-triangle',cls:'kc-ico-orange',txt:p.predmet_naziv||'Predmet',sub:'Rizik: '+(p.prethodni_rizik||'?')+' → '+(p.trenutni_rizik||'?'),ts:'',id:p.predmet_id});
  });
  var h = '<div class="kc-panel" id="kc-panel-aktivnosti">';
  h += '<div class="kc-panel-hd"><span class="kc-panel-title">'+_kcIco('activity')+'Poslednje aktivnosti</span>';
  h += '<span class="kc-panel-hd-cta" onclick="setTab(document.getElementById(\'tab-btn-p\'),\'p\')">Vidi sve →</span></div>';
  if (!acts.length) {
    h += '<div class="kc-panel-empty">';
    h += '<span class="kc-panel-empty-ico">'+_kcIco('activity')+'</span>';
    h += '<span class="kc-panel-empty-title">Nema nedavnih aktivnosti</span>';
    h += '</div>';
  } else {
    acts.forEach(function(a){
      var clickAttr = a.id ? ' onclick="_dashGoToPredmet(\''+escHtml(a.id)+'\')"' : '';
      h += '<div class="kc-panel-row"'+clickAttr+'>';
      h += '<span class="kc-row-ico '+a.cls+'">'+_kcIco(a.ico)+'</span>';
      h += '<div class="kc-panel-row-info">';
      h += '<div class="kc-panel-row-top"><span class="kc-panel-row-naziv">'+escHtml(a.txt)+'</span>';
      if (a.ts) h += '<span class="kc-panel-row-ts">'+escHtml(a.ts)+'</span>';
      h += '</div>';
      h += '<div class="kc-panel-row-meta">'+escHtml(a.sub)+'</div>';
      h += '</div></div>';
    });
  }
  h += '</div>';
  return h;
}

/* ── FAZA 1.8 — Komandni centar: Sphere-inside + greeting + 4-col */
_dashRender = function(d, bd, inboxData) {
  var aktivni  = d.ukupno_aktivnih || 0;
  var hitniRok = (d.hitni_rokovi||[]).length;
  var noviDok  = (d.statistike && d.statistike.novi_dokumenti != null)
                   ? d.statistike.novi_dokumenti : (d.novi_dokumenti||[]).length;
  var visokRiz = (d.statistike && d.statistike.predmeti_visok_rizik != null)
                   ? d.statistike.predmeti_visok_rizik : (d.predmeti_visok_rizik||[]).length;

  var html = '';
  var _dn = localStorage.getItem('vindex_display_name') || (currentUser ? (currentUser.email||'').split('@')[0] : '');
  var userName = _dn ? escHtml(_dn) : '';

  /* ── 1. HEADER — greeting ──────────────────────────────────── */
  html += '<div class="kc-hdr">';
  html += '<div class="kc-hdr-inner">';
  html += '<div class="kc-hdr-eyebrow">Komandni centar</div>';
  html += '<div class="kc-hdr-title">Dobrodošli nazad'+(userName ? ', '+userName : '')+'.</div>';
  html += '<div class="kc-hdr-sub">Ovde je pregled stanja vaše kancelarije.</div>';
  html += '</div>';
  html += '<div style="text-align:right;flex-shrink:0;">';
  html += '<div class="kc-hdr-date">'+_dashFormatDate()+'</div>';
  html += '<div class="kc-hdr-clock" id="kc-live-clock"></div>';
  html += '</div>';
  html += '</div>';

  /* ── 2. QUICK ACTIONS — 4 kartice ─────────────────────────── */
  html += '<div class="kc-qa-bar">';
  html += '<button class="kc-qa-btn" onclick="intakeOtvori()">'+_kcIco('briefcase');
  html += '<div class="kc-qa-btn-body"><div class="kc-qa-btn-title">Novi predmet</div><div class="kc-qa-btn-desc">Kreiraj novi predmet</div></div></button>';
  html += '<button class="kc-qa-btn" onclick="setTab(document.getElementById(\'tab-btn-k\'),\'k\');setTimeout(crmOtvoriFormu,250)">'+_kcIco('user-plus');
  html += '<div class="kc-qa-btn-body"><div class="kc-qa-btn-title">Novi klijent</div><div class="kc-qa-btn-desc">Dodaj novog klijenta</div></div></button>';
  html += '<button class="kc-qa-btn" onclick="openAITool(\'a\')">'+_kcIco('file-text');
  html += '<div class="kc-qa-btn-body"><div class="kc-qa-btn-title">Otpremi dokument</div><div class="kc-qa-btn-desc">Dodaj dokument</div></div></button>';
  html += '<button class="kc-qa-btn" onclick="setTab(document.getElementById(\'tab-btn-alati\'),\'alati\')">'+_kcIco('sparkles');
  html += '<div class="kc-qa-btn-body"><div class="kc-qa-btn-title">Pokreni AI analizu</div><div class="kc-qa-btn-desc">Analiziraj sa AI</div></div></button>';
  html += '</div>';

  /* ── 3. SFERA sa statistikama unutra ──────────────────────── */
  html += '<div class="kc-sphere-wrap">';
  html += '<div class="kc-sphere">';
  html += '<canvas id="kc-inline-canvas" style="position:absolute;inset:0;width:100%;height:100%;border-radius:50%;z-index:1;pointer-events:none;"></canvas>';
  html += '<div class="kc-sphere-inner">';
  html += '<div class="kc-sphere-divv"></div>';
  html += '<div class="kc-sphere-divh"></div>';
  /* TL — Aktivnih predmeta */
  html += '<div class="kc-sphere-quad clickable" onclick="setTab(document.getElementById(\'tab-btn-p\'),\'p\')">';
  html += '<div class="kc-sphere-ico">'+_kcIco('briefcase')+'</div>';
  html += '<div class="kc-sphere-num">'+aktivni+'</div>';
  html += '<div class="kc-sphere-lbl">Aktivnih<br>predmeta</div></div>';
  /* TR — Hitnih rokova */
  html += '<div class="kc-sphere-quad clickable" onclick="setTab(document.getElementById(\'tab-btn-kal\'),\'kal\')">';
  html += '<div class="kc-sphere-ico'+(hitniRok>0?' warn':'')+'">'+_kcIco('clock')+'</div>';
  html += '<div class="kc-sphere-num'+(hitniRok>0?' warn':'')+'">'+hitniRok+'</div>';
  html += '<div class="kc-sphere-lbl">Hitnih<br>rokova</div></div>';
  /* BL — Novi dokumenti */
  html += '<div class="kc-sphere-quad">';
  html += '<div class="kc-sphere-ico">'+_kcIco('file-text')+'</div>';
  html += '<div class="kc-sphere-num">'+noviDok+'</div>';
  html += '<div class="kc-sphere-lbl">Novih<br>dok. (24h)</div></div>';
  /* BR — Visok rizik */
  html += '<div class="kc-sphere-quad">';
  html += '<div class="kc-sphere-ico'+(visokRiz>0?' danger':'')+'">'+_kcIco('shield-alert')+'</div>';
  html += '<div class="kc-sphere-num'+(visokRiz>0?' danger':'')+'">'+visokRiz+'</div>';
  html += '<div class="kc-sphere-lbl">Visok<br>rizik</div></div>';
  html += '</div>'; /* kc-sphere-inner */
  html += '</div>'; /* kc-sphere */
  html += '</div>'; /* kc-sphere-wrap */

  /* ── 4. PANELI — 4 kolone ──────────────────────────────────── */
  html += '<div class="kc-panels-grid">';
  html += _kcPanelAktivni(d);
  html += _kcPanelRokovi(d);
  html += _kcPanelPreporuke(d);
  html += _kcPanelAktivnosti(d);
  html += '</div>';

  /* ── 5. INBOX — Prioritetne stavke (kriticno + visok) ─────────── */
  if (inboxData) {
    var _hitne = (inboxData.stavke || []).filter(function(i) {
      return i.prioritet === 'kriticno' || i.prioritet === 'visok';
    }).slice(0, 6);
    if (_hitne.length) {
      var _tipIco = {rociste:'⚖',rok:'⏰',dokument:'📄',naplata:'💰',neaktivan:'💤'};
      var _kriticnoN = inboxData.kriticno || 0;
      var _visokN    = inboxData.visok    || 0;
      html += '<div class="kc-inbox-section">';
      html += '<div class="kc-inbox-hd">';
      html += '<span class="kc-panel-title">'+_kcIco('inbox')+'Inbox — Prioritetne stavke</span>';
      html += '<div style="display:flex;gap:6px;align-items:center;">';
      if (_kriticnoN) html += '<span class="kc-inbox-tag kc-inbox-tag-red">'+_kriticnoN+' kritično</span>';
      if (_visokN)    html += '<span class="kc-inbox-tag kc-inbox-tag-orange">'+_visokN+' visok</span>';
      html += '</div></div>';
      html += '<div class="kc-inbox-rows">';
      _hitne.forEach(function(item) {
        var ico    = _tipIco[item.tip] || '•';
        var dotCls = item.prioritet === 'kriticno' ? 'kc-inbox-dot-red' : 'kc-inbox-dot-orange';
        html += '<div class="kc-inbox-row" onclick="_dashGoToPredmet(\''+escHtml(item.predmet_id)+'\')">';
        html += '<div class="kc-inbox-dot '+dotCls+'"></div>';
        html += '<div class="kc-inbox-ico">'+ico+'</div>';
        html += '<div class="kc-inbox-info">';
        html += '<div class="kc-inbox-naslov">'+escHtml(item.naslov)+'</div>';
        html += '<div class="kc-inbox-sub">'+escHtml(item.predmet_naziv||'—')+'</div>';
        html += '</div>';
        html += '<div class="kc-inbox-datum">'+escHtml((item.datum||'').slice(5))+'</div>';
        html += '</div>';
      });
      html += '</div></div>';
    }
  }

  return html;
};

/* Quick Actions za VINDEX CORE sfera (overlay preserved) */
function _vx2_stub_start() { var html = ''; html += '<div class="vx2-core-wrap">';
  html += '<div class="vx2-core-header">';
  html += '<div class="vx2-greeting">'+_dashGreeting()+(uName?', '+escHtml(uName):'')+'. </div>';
  html += '<div class="vx2-date">'+_dashFormatDate()+'</div>';
  html += '</div>';

  html += '<div class="vx2-orbit-system">';
  html += '<div class="vx2-orbit-ring vx2-orbit-ring-1"></div>';
  html += '<div class="vx2-orbit-ring vx2-orbit-ring-2"></div>';

  var rokDot = hitniRokovi.length > 0 ? 'danger' : (rokovi7.length > 0 ? 'warn' : '');
  html += '<div class="vx2-sat vx2-sat-n" onclick="setTab(document.getElementById(\'tab-btn-kal\'),\'kal\')" title="Rokovi">';
  html += '<div class="vx2-sat-dot '+rokDot+'"></div>';
  html += '<div class="vx2-sat-num">'+rokovi7.length+'</div>';
  html += '<div class="vx2-sat-lbl">rokova</div></div>';

  html += '<div class="vx2-sat vx2-sat-e" onclick="setTab(document.getElementById(\'tab-btn-p\'),\'p\')" title="Predmeti">';
  html += '<div class="vx2-sat-dot"></div>';
  html += '<div class="vx2-sat-num">'+aktivni+'</div>';
  html += '<div class="vx2-sat-lbl">predmeta</div></div>';

  var rsdLbl = neobracunato > 0 ? _fmtRSD(neobracunato) : '0';
  html += '<div class="vx2-sat vx2-sat-s" title="Nenaplaćeno RSD">';
  html += '<div class="vx2-sat-dot'+(neobracunato>0?' warn':'')+'"></div>';
  html += '<div class="vx2-sat-num" style="font-size:0.82rem">'+rsdLbl+'</div>';
  html += '<div class="vx2-sat-lbl">RSD</div></div>';

  html += '<div class="vx2-sat vx2-sat-w" onclick="setTab(document.getElementById(\'tab-btn-k\'),\'k\')" title="Klijenti">';
  html += '<div class="vx2-sat-dot"></div>';
  html += '<div class="vx2-sat-num" style="font-size:1rem;color:rgba(255,255,255,0.35)">—</div>';
  html += '<div class="vx2-sat-lbl">klijenti</div></div>';

  html += '<div class="vx2-sphere" onclick="vxCoreQuickActions()" title="Quick Actions — kliknite">';
  html += '<div class="vx2-sphere-title">VINDEX</div>';
  html += '<div class="vx2-sphere-name">CORE</div>';
  html += '</div>';
  html += '</div>'; /* orbit-system */

  html += '<div class="vx2-core-status'+(statusCls?' '+statusCls:'')+'"><div class="vx2-status-dot"></div>'+escHtml(statusTxt)+'</div>';
  html += '</div>'; /* core-wrap */

  /* ── 4 NAVIGACIONA PANELA ────────────────────────────────────── */
  html += '<div class="vx2-panels">';

  /* Panel: PREDMETI */
  var predWarn = predmHitni.length > 0;
  html += '<div class="vx2-panel'+(predWarn?' has-warn':'')+ '" onclick="setTab(document.getElementById(\'tab-btn-p\'),\'p\')">';
  html += '<div class="vx2-panel-hd"><span class="vx2-panel-name">Predmeti</span>'+(predWarn?'<span class="vx2-panel-warn">⚠</span>':'')+'</div>';
  html += '<div class="vx2-panel-stats"><span class="vx2-panel-stat-n">'+aktivni+'</span><span class="vx2-panel-stat-l">aktivna</span>';
  if (predmHitni.length) html += '<span class="vx2-panel-stat-n warn" style="margin-left:6px">'+predmHitni.length+'</span><span class="vx2-panel-stat-l">hitnih</span>';
  html += '</div>';
  html += '<div class="vx2-panel-preview">';
  var pprev = predmHitni.slice(0,2);
  if (pprev.length) {
    pprev.forEach(function(p){ html += '<div class="vx2-panel-item'+(predWarn?' warn':'')+'">'+escHtml(p.predmet_naziv||'Predmet')+'</div>'; });
  } else {
    html += '<div class="vx2-panel-item">Nema hitnih predmeta</div>';
  }
  html += '</div><div class="vx2-panel-cta">Otvori →</div></div>';

  /* Panel: KLIJENTI */
  html += '<div class="vx2-panel" onclick="setTab(document.getElementById(\'tab-btn-k\'),\'k\')">';
  html += '<div class="vx2-panel-hd"><span class="vx2-panel-name">Klijenti</span></div>';
  html += '<div class="vx2-panel-stats"><span class="vx2-panel-stat-n" style="font-size:1.2rem;color:rgba(255,255,255,0.3)">—</span></div>';
  html += '<div class="vx2-panel-preview"><div class="vx2-panel-item">Baza klijenata kancelarije</div></div>';
  html += '<div class="vx2-panel-cta">Otvori →</div></div>';

  /* Panel: ROKOVI */
  var rokWarn = hitniRokovi.length > 0;
  html += '<div class="vx2-panel'+(rokWarn?' has-warn':'')+ '" onclick="setTab(document.getElementById(\'tab-btn-kal\'),\'kal\')">';
  html += '<div class="vx2-panel-hd"><span class="vx2-panel-name">Rokovi</span>'+(rokWarn?'<span class="vx2-panel-warn">⚠</span>':'')+'</div>';
  html += '<div class="vx2-panel-stats"><span class="vx2-panel-stat-n'+(rokWarn?' warn':'')+'">'+rokovi7.length+'</span><span class="vx2-panel-stat-l">ove ned.</span>';
  if (hitniRokovi.length) html += '<span class="vx2-panel-stat-n danger" style="margin-left:6px">'+hitniRokovi.length+'</span><span class="vx2-panel-stat-l">hitnih</span>';
  html += '</div>';
  html += '<div class="vx2-panel-preview">';
  rokovi7.slice(0,2).forEach(function(r){
    var isToday = r.datum_iso===today;
    html += '<div class="vx2-panel-item'+(isToday?' danger':'')+'">'+
      (isToday?'DANAS — ':'')+escHtml(r.predmet_naziv||'Predmet')+'</div>';
  });
  if (!rokovi7.length) html += '<div class="vx2-panel-item">Nema nadolazećih rokova</div>';
  html += '</div><div class="vx2-panel-cta">Otvori →</div></div>';

  /* Panel: AI HUB */
  html += '<div class="vx2-panel" onclick="setTab(document.getElementById(\'tab-btn-alati\'),\'alati\')">';
  html += '<div class="vx2-panel-hd"><span class="vx2-panel-name">AI Hub</span></div>';
  html += '<div class="vx2-panel-stats"><span class="vx2-panel-stat-n" style="font-size:1.1rem;color:rgba(74,168,255,0.65)">847</span><span class="vx2-panel-stat-l">zakona RS</span></div>';
  html += '<div class="vx2-panel-ai-actions">';
  html += '<button class="vx2-panel-ai-btn" onclick="event.stopPropagation();openAITool(\'q\')">⚖ Istraži zakon</button>';
  html += '<button class="vx2-panel-ai-btn" onclick="event.stopPropagation();openAITool(\'a\')">☐ Analiziraj dokument</button>';
  html += '</div>';
  html += '<div class="vx2-panel-cta">Otvori hub →</div></div>';

  html += '</div>'; /* vx2-panels */

  /* ── RECENT ACTIVITY ─────────────────────────────────────────── */
  var acts = [];
  hitniRokovi.slice(0,1).forEach(function(r){
    acts.push({txt:'Hitni rok — '+(r.predmet_naziv||'Predmet'), tm: r.datum_iso||'hitno'});
  });
  rocistaToday.slice(0,1).forEach(function(r){
    acts.push({txt:'Ročište danas — '+(r.predmet_naziv||'Predmet'), tm: r.vreme||'danas'});
  });
  (d.novi_dokumenti||[]).slice(0,2).forEach(function(dok){
    acts.push({txt:'Dokument — '+(dok.naziv_fajla||'Fajl'), tm:'nedavno'});
  });
  predmHitni.slice(0,1).forEach(function(p){
    if (acts.length < 4) acts.push({txt:'Prioritetni predmet — '+(p.predmet_naziv||'Predmet'), tm:'aktivno'});
  });

  if (acts.length) {
    html += '<div class="vx2-activity">';
    html += '<div class="vx2-activity-hd">Nedavna aktivnost</div>';
    html += '<div class="vx2-activity-rows">';
    acts.slice(0,4).forEach(function(a){
      html += '<div class="vx2-activity-row"><div class="vx2-activity-dot"></div>';
      html += '<div class="vx2-activity-text">'+escHtml(a.txt)+'</div>';
      html += '<div class="vx2-activity-time">'+escHtml(a.tm)+'</div></div>';
    });
    html += '</div></div>';
  }

  return html;
};

/* Quick Actions za VINDEX CORE sfera */
function vxCoreQuickActions() {
  var ov = document.getElementById('vx2-qa-overlay');
  if (ov) { ov.classList.add('open'); document.body.style.overflow='hidden'; }
}
function vxCoreCloseQA() {
  var ov = document.getElementById('vx2-qa-overlay');
  if (ov) { ov.classList.remove('open'); document.body.style.overflow=''; }
}
/* ── kraj VINDEX AI 2.0 Home Screen ────────────────────────────── */

function _dashGoToPredmet(predmetId){
  if(!predmetId)return;
  _dashGoToTab('p');
  setTimeout(function(){pred_select(predmetId);},150);
}

function _dashGoToTab(tabId){
  var el=document.querySelector('[onclick*="\''+tabId+'\'"]');
  if(el)setTab(el,tabId);
}

/* REVEAL */
var revObs=new IntersectionObserver(function(entries){entries.forEach(function(e){if(e.isIntersecting){e.target.classList.add('v');revObs.unobserve(e.target);}});},{threshold:0.1});
document.querySelectorAll('.r').forEach(function(el){revObs.observe(el);});

/* TABS */
function setTab(el,t){
  // PRO gate — tabovi "n" i "t" zahtevaju PRO status
  if ((t === 'n' || t === 't' || t === 'w') && !currentUserIsPro) {
    openProUpgradeModal();
    return;
  }
  // Navigation history — push current tab before switching
  if (!_vxGoingBack && typeof activeTab !== 'undefined' && activeTab && activeTab !== t) {
    vxNavHistory.push(activeTab);
    if (vxNavHistory.length > 20) vxNavHistory.shift();
  }
  document.querySelectorAll('.t-tab').forEach(function(x){x.classList.remove('active');});
  el.classList.add('active');
  // Ako je AI tool tab aktivan — označi i "AI Alati" nav dugme kao aktivno
  var _aiTools = {q:1,a:1,n:1,s:1,t:1,w:1,ob:1};
  if (_aiTools[t]) {
    var _ab = document.getElementById('tab-btn-alati');
    if (_ab) _ab.classList.add('active');
  }
  ['h','q','n','a','s','p','t','k','w','ob','kal','pi','alati','dok','settings'].forEach(function(id){var el2=document.getElementById('tab-'+id);if(el2)el2.style.display='none';});
  document.getElementById('tab-'+t).style.display='block';
  activeTab=t;
  var lbl={h:'Komandni centar',q:'Istraživanje zakona',n:'Nacrti podnesaka',a:'Analiza dokumenta',s:'Sudska praksa',p:'Predmeti',t:'Strategija',k:'Klijenti',w:'Web3 Compliance',ob:'Pravne oblasti',kal:'Rokovi i ročišta',pi:'Product Intelligence',alati:'AI Centar',dok:'Baza znanja',settings:'Podešavanja'};
  var execRow = document.getElementById('t-exec-row');
  var credRow = document.getElementById('t-credits-row');
  var respEl  = document.getElementById('resp');
  var _noExec = {h:1,t:1,k:1,w:1,ob:1,kal:1,pi:1,alati:1,dok:1,settings:1,p:1};
  if (execRow) execRow.style.display = _noExec[t] ? 'none' : '';
  if (credRow) credRow.style.display = _noExec[t] ? 'none' : (credRow.dataset.wasVisible === '1' ? '' : 'none');
  if (t==='h') dash_load();
  if (t==='pi') piLoad();
  // Sakrij FAB kada korisnik napusti predmete
  if (t !== 'p') { if (typeof pred_fab_hide === 'function') pred_fab_hide(); }
  if (t==='n') {
    updatePodnesakHint();
    ucitajPlaybookStatus();
    // Auto-fill podnesak-opis from active predmet workspace snapshot
    var opisPodnesakEl = document.getElementById('podnesak-opis');
    if (opisPodnesakEl && !opisPodnesakEl.value && window._predFull) {
      var pf = window._predFull;
      var parts = [];
      if (pf.stranke && pf.stranke.length > 0) {
        var kl = pf.stranke[0];
        var kName = ((kl.ime||'') + ' ' + (kl.prezime||'')).trim() || kl.firma || '';
        if (kName) parts.push('Tužilac/Stranka: ' + kName);
      }
      if (pf.protivna_strana && pf.protivna_strana.length > 0) {
        var ps = pf.protivna_strana[0];
        var psName = ((ps.ime||'') + ' ' + (ps.prezime||'')).trim() || ps.firma || '';
        if (psName) parts.push('Protivna strana: ' + psName);
      }
      if (pf.predmet && pf.predmet.naziv) parts.push('Predmet: ' + pf.predmet.naziv);
      if (parts.length) opisPodnesakEl.value = parts.join('\n') + '\n';
    }
  }
  if (t==='q' && currentUserIsPro) { var ip = document.getElementById('interni-stavovi-panel'); if (ip) ip.style.display = ''; }
  if (t==='s') praksa_load_initial();
  if (t==='p') { pred_load(); predFirmaInit(); }
  if (t==='k') ucitajKlijente();
  if (t==='w') web3InitTab();
  if (t==='ob') oblastiInit();
  if (t==='kal') kalendarLoad();
  if (t==='settings') settingsLoad();
  if (el && el.scrollIntoView) el.scrollIntoView({ block:'nearest', inline:'nearest', behavior:'smooth' });
  if (window.lucide) lucide.createIcons();
  piTrack('nav', 'tab_switch', {tab: t});
  setTimeout(tabsUpdateArrows, 350);
  document.getElementById('btn-lbl').textContent = lbl[t] || '';
  if (respEl) respEl.classList.remove('show');
  document.getElementById('podnesak-preview').style.display='none';
  if (window.micStopAll) micStopAll();
  vxUpdateBreadcrumb(t);
  if (window.mobileNavUpdateActive) mobileNavUpdateActive(t);
}

// Otvori AI alat iz huba — čuva AI Alati kao aktivan parent
function openAITool(t) {
  var btn = document.getElementById('tab-btn-' + t);
  if (btn) setTab(btn, t);
}

function vxGoBack() {
  if (vxNavHistory.length === 0) return;
  var prev = vxNavHistory.pop();
  var btn = document.getElementById('tab-btn-' + prev);
  if (btn) {
    _vxGoingBack = true;
    setTab(btn, prev);
    _vxGoingBack = false;
  }
}

function vxUpdateBreadcrumb(t) {
  var backBtn = document.getElementById('vx-back-btn');
  var backSep = document.getElementById('vx-back-sep');
  var pathEl  = document.getElementById('vx-breadcrumb-path');
  if (!pathEl) return;
  var _aiSubtabs = {q:1,a:1,n:1,s:1,t:1,w:1};
  var label = _vxTabLabels[t] || t;
  pathEl.textContent = _aiSubtabs[t] ? 'AI Centar / ' + label : label;
  if (vxNavHistory.length > 0) {
    if (backBtn) backBtn.classList.add('visible');
    if (backSep) backSep.classList.add('visible');
  } else {
    if (backBtn) backBtn.classList.remove('visible');
    if (backSep) backSep.classList.remove('visible');
  }
}

function saveDisplayName() {
  var el = document.getElementById('settings-display-name-input');
  if (!el) return;
  var name = el.value.trim();
  if (name) localStorage.setItem('vindex_display_name', name);
  else localStorage.removeItem('vindex_display_name');
  showToast('Prikazno ime sačuvano ✓', 'info');
  if (activeTab === 'h') dash_load();
}

// Popuni Podešavanja panel podacima korisnika
function settingsLoad() {
  var emailEl = document.getElementById('settings-email-val');
  var planEl  = document.getElementById('settings-plan-val');
  var dnEl    = document.getElementById('settings-display-name-input');
  if (dnEl) dnEl.value = localStorage.getItem('vindex_display_name') || '';
  var _email = currentUser ? (currentUser.email || '') : '';
  if (emailEl) emailEl.textContent = _email || '—';
  if (planEl) planEl.textContent = currentUserIsPro ? 'VindexAI PRO' : 'Basic';
  planLoad();
  sef_loadSettings();
  sms_loadProfil();
  emailNotifLoad();
  kancelarijaLoad();
  billingDugovanjaLoad();
}

// ── Moj plan — status i upotreba ─────────────────────────────────────────────

async function planLoad() {
  if (!currentSession) return;
  var badge = document.getElementById('plan-badge');
  var wrap  = document.getElementById('plan-usage-wrap');
  if (!wrap) return;

  var PLAN_LABELS = {free:'Free', advokat:'Advokat', pro:'PRO', firma:'Firma'};
  var PLAN_COLORS = {free:'rgba(255,255,255,.45)', advokat:'#4aa8ff', pro:'#a78bfa', firma:'#c9a84c'};

  try {
    var r = await fetch(BASE_URL + '/api/plan/status', {
      headers: {'Authorization': 'Bearer ' + currentSession.access_token}
    });
    if (!r.ok) { wrap.innerHTML = ''; return; }
    var d = await r.json();

    var planName = d.plan || 'free';
    var label    = PLAN_LABELS[planName] || planName;
    var color    = PLAN_COLORS[planName] || '#fff';

    if (badge) {
      badge.textContent = label;
      badge.style.cssText = 'font-size:.6rem;font-weight:700;letter-spacing:.06em;padding:.1rem .5rem;border-radius:4px;background:rgba(74,168,255,.12);color:'+color+';border:1px solid rgba(74,168,255,.18);';
      badge.style.display = '';
    }
    var planVal = document.getElementById('settings-plan-val');
    if (planVal) planVal.textContent = label;

    var usage  = d.usage  || {};
    var overage = d.overage || {};
    var fields = [
      {key:'ai_queries',   label:'AI upiti'},
      {key:'doc_analyses', label:'Analize dokumenata'},
      {key:'strategies',   label:'Strategije'},
    ];

    var html = '';
    for (var i = 0; i < fields.length; i++) {
      var f    = fields[i];
      var u    = usage[f.key] || {};
      var used  = u.used  || 0;
      var limit = u.limit;

      var barHtml;
      if (limit === null) {
        barHtml = '<div style="font-size:.68rem;color:#4ade80;margin-top:2px;">∞ neograničeno</div>';
      } else if (!limit) {
        barHtml = '<div style="font-size:.68rem;color:rgba(255,255,255,.25);margin-top:2px;">nije u ovom planu</div>';
      } else {
        var pct = Math.min(100, Math.round(used / limit * 100));
        var barColor = pct >= 90 ? '#f87171' : pct >= 70 ? '#fb923c' : '#4aa8ff';
        barHtml = '<div style="background:rgba(255,255,255,.07);border-radius:4px;height:4px;overflow:hidden;margin-top:4px;">'
          + '<div style="height:100%;width:'+pct+'%;background:'+barColor+';border-radius:4px;transition:width .3s;"></div>'
          + '</div>'
          + '<div style="font-size:.63rem;color:rgba(255,255,255,.3);margin-top:2px;">'+used+' / '+limit+'</div>';
      }

      html += '<div style="margin-bottom:.5rem;">'
        + '<div style="font-size:.71rem;color:rgba(255,255,255,.5);">'+f.label+'</div>'
        + barHtml
        + '</div>';
    }

    var totalOverage = (overage.queries||0) + (overage.docs||0) + (overage.strategies||0);
    if (totalOverage > 0) {
      html += '<div style="margin-top:.35rem;padding:.3rem .5rem;background:rgba(251,146,60,.08);border:1px solid rgba(251,146,60,.2);border-radius:6px;font-size:.7rem;color:#fb923c;">⚠ Overage: '+totalOverage+' jedinica iznad plana</div>';
    }

    var ym = d.year_month || '';
    if (ym) html += '<div style="font-size:.6rem;color:rgba(255,255,255,.2);margin-top:.5rem;">Mesec: '+ym+'</div>';

    wrap.innerHTML = html;
  } catch(e) {
    if (wrap) wrap.innerHTML = '<div style="font-size:.75rem;color:rgba(255,255,255,.25);">Nije moguće učitati podatke o planu.</div>';
  }
}

// ── Billing Dugovanja ────────────────────────────────────────────────────────

async function billingDugovanjaLoad() {
  if (!currentSession) return;
  var listEl = document.getElementById('billing-dugovanja-list');
  var kpiEl  = document.getElementById('billing-dugovanja-kpi');
  if (!listEl) return;
  listEl.innerHTML = '<div style="font-size:0.75rem;color:rgba(255,255,255,0.3);padding:0.5rem 0;">Učitavam...</div>';
  try {
    var r = await fetch('/billing/dugovanja', { headers: { 'Authorization': 'Bearer ' + currentSession.access_token } });
    if (!r.ok) { listEl.innerHTML = '<div style="font-size:0.75rem;color:#f87171;">Greška pri učitavanju.</div>'; return; }
    var d = await r.json();
    var dugovanja = d.dugovanja || [];

    if (kpiEl) {
      var fmt = function(n){ return Math.round(n).toLocaleString('sr-RS') + ' RSD'; };
      kpiEl.innerHTML = [
        { label: 'Ukupno duguje', val: fmt(d.ukupno_rsd || 0), color: d.ukupno_rsd > 0 ? '#f87171' : '#4ade80' },
        { label: 'Predmeta', val: d.predmeta || 0, color: '#89c8ff' },
        { label: 'Stavki', val: d.stavki || 0, color: 'rgba(255,255,255,0.5)' },
      ].map(function(k){
        return '<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);border-radius:7px;padding:0.45rem 0.7rem;text-align:center;flex:1;">'
          +'<div style="font-size:0.9rem;font-weight:700;color:'+k.color+';">'+k.val+'</div>'
          +'<div style="font-size:0.57rem;color:rgba(255,255,255,0.35);text-transform:uppercase;letter-spacing:.05em;margin-top:1px;">'+k.label+'</div>'
          +'</div>';
      }).join('');
    }

    if (!dugovanja.length) {
      listEl.innerHTML = '<div style="font-size:0.78rem;color:rgba(255,255,255,0.3);padding:0.5rem 0;text-align:center;">✅ Nema neplaćenih stavki. Sve je naplaćeno!</div>';
      return;
    }

    listEl.innerHTML = dugovanja.map(function(g){
      var iznos = Math.round(g.ukupno_rsd || 0).toLocaleString('sr-RS');
      return '<div onclick="pred_select(\''+g.predmet_id+'\')" style="display:flex;align-items:center;gap:0.6rem;padding:0.5rem 0.65rem;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:7px;cursor:pointer;transition:border-color .15s;" onmouseover="this.style.borderColor=\'rgba(74,168,255,0.2)\'" onmouseout="this.style.borderColor=\'rgba(255,255,255,0.07)\'">'
        +'<div style="flex:1;min-width:0;">'
        +'<div style="font-size:0.78rem;color:#e2e8f0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+_htmlEsc(g.predmet_naziv||'—')+'</div>'
        +'<div style="font-size:0.65rem;color:rgba(255,255,255,0.38);margin-top:1px;">'+(g.stavke||[]).length+' stavk'+(g.stavke&&g.stavke.length===1?'a':'i')+'</div>'
        +'</div>'
        +'<div style="flex-shrink:0;text-align:right;">'
        +'<div style="font-size:0.82rem;font-weight:700;color:#f87171;">'+iznos+'</div>'
        +'<div style="font-size:0.58rem;color:rgba(255,255,255,0.3);">RSD</div>'
        +'</div>'
        +'<span style="font-size:0.65rem;color:#89c8ff;flex-shrink:0;">→</span>'
        +'</div>';
    }).join('');
  } catch(e) {
    if (listEl) listEl.innerHTML = '<div style="font-size:0.75rem;color:#f87171;">Greška: ' + _htmlEsc(e.message) + '</div>';
  }
}

// ── SMS / WhatsApp notifikacije ───────────────────────────────────────────────
function _smsMsg(txt, color) {
  var el = document.getElementById('sms-msg');
  if (!el) return;
  el.textContent = txt;
  el.style.color = color || '#4ade80';
  el.style.display = 'inline';
  setTimeout(function(){ el.style.display='none'; }, 4000);
}

async function sms_loadProfil() {
  if (!currentSession) return;
  try {
    var r = await fetch('/sms/telefon', {headers:{'Authorization':'Bearer '+currentSession.access_token}});
    if (!r.ok) return;
    var d = await r.json();
    var inp = document.getElementById('sms-telefon-input');
    var chk = document.getElementById('sms-whatsapp-chk');
    var badge = document.getElementById('sms-status-badge');
    var testBtn = document.getElementById('sms-test-btn');
    var deakBtn = document.getElementById('sms-deaktivir-btn');
    if (inp && d.telefon) inp.value = d.telefon;
    if (chk) chk.checked = !!d.whatsapp;
    if (badge) {
      if (d.aktivan && d.telefon) {
        badge.textContent = 'AKTIVNO';
        badge.style.background = 'rgba(74,222,128,0.15)';
        badge.style.color = '#4ade80';
        badge.style.display = 'inline';
      } else { badge.style.display = 'none'; }
    }
    if (testBtn) testBtn.style.display = (d.aktivan && d.telefon) ? 'inline-block' : 'none';
    if (deakBtn) deakBtn.style.display = (d.aktivan && d.telefon) ? 'inline-block' : 'none';
  } catch(e) {}
}

async function sms_sacuvaj() {
  var inp = document.getElementById('sms-telefon-input');
  var chk = document.getElementById('sms-whatsapp-chk');
  if (!inp || !inp.value.trim()) { _smsMsg('Unesite broj telefona', '#f87171'); return; }
  if (!currentSession) { _smsMsg('Niste prijavljeni', '#f87171'); return; }
  try {
    var r = await fetch('/sms/telefon', {
      method:'POST', headers:{'Authorization':'Bearer '+currentSession.access_token,'Content-Type':'application/json'},
      body: JSON.stringify({broj: inp.value.trim(), whatsapp: chk ? !!chk.checked : false})
    });
    var d = await r.json();
    if (!r.ok) { _smsMsg(d.detail || 'Greška', '#f87171'); return; }
    _smsMsg('Broj sačuvan ✓');
    sms_loadProfil();
  } catch(e) { _smsMsg('Greška mreže', '#f87171'); }
}

async function sms_testSms() {
  if (!currentSession) return;
  var btn = document.getElementById('sms-test-btn');
  if (btn) btn.disabled = true;
  try {
    var r = await fetch('/sms/test', {method:'POST', headers:{'Authorization':'Bearer '+currentSession.access_token}});
    var d = await r.json();
    if (!r.ok) { _smsMsg(d.detail || 'Greška pri slanju', '#f87171'); }
    else { _smsMsg('Test SMS poslat na ' + (d.poslat_na||'')); }
  } catch(e) { _smsMsg('Greška mreže', '#f87171'); }
  finally { if (btn) btn.disabled = false; }
}

async function sms_deaktiviraj() {
  if (!currentSession) return;
  if (!confirm('Deaktivirati SMS notifikacije?')) return;
  try {
    await fetch('/sms/telefon', {method:'DELETE', headers:{'Authorization':'Bearer '+currentSession.access_token}});
    _smsMsg('SMS notifikacije deaktivirane');
    sms_loadProfil();
  } catch(e) { _smsMsg('Greška mreže', '#f87171'); }
}

// ── Kancelarija (Phase 5.4) ───────────────────────────────────────────────────

var _kancData = null; // cached /api/kancelarija/moja response

function _kancShow(state) {
  ['kancelarija-no-firma','kancelarija-pending','kancelarija-aktivan'].forEach(function(id){
    var el = document.getElementById(id);
    if (el) el.style.display = (id === 'kancelarija-'+state) ? '' : 'none';
  });
  var ldg = document.getElementById('kancelarija-loading');
  if (ldg) ldg.style.display = 'none';
}

async function kancelarijaLoad() {
  if (!currentSession) return;
  var ldg = document.getElementById('kancelarija-loading');
  if (ldg) ldg.style.display = 'inline';
  try {
    var r = await fetch('/api/kancelarija/moja', {headers:{'Authorization':'Bearer '+currentSession.access_token}});
    if (!r.ok) { _kancShow('no-firma'); return; }
    var d = await r.json();
    _kancData = d;
    if (d.status === 'no_firma') {
      _kancShow('no-firma');
    } else if (d.status === 'pending_invite') {
      _kancShow('pending');
      var nnEl = document.getElementById('kancelarija-pending-naziv');
      if (nnEl) nnEl.textContent = d.firma_naziv || '—';
    } else if (d.status === 'aktivan') {
      _kancShow('aktivan');
      var nazEl = document.getElementById('kancelarija-naziv-display');
      var roleEl = document.getElementById('kancelarija-role-display');
      var adminBtns = document.getElementById('kancelarija-admin-btns');
      var invPanel = document.getElementById('kancelarija-invite-panel');
      var leavePanel = document.getElementById('kancelarija-leave-panel');
      if (nazEl) nazEl.textContent = d.firma.naziv;
      var roleLabels = {admin:'Administrator', partner:'Partner', saradnik:'Saradnik', citanje:'Samo čitanje'};
      if (roleEl) roleEl.textContent = 'Vaša uloga: ' + (roleLabels[d.moja_uloga] || d.moja_uloga);
      var isAdmin = d.moja_uloga === 'admin';
      if (adminBtns) adminBtns.style.display = isAdmin ? 'flex' : 'none';
      if (invPanel)  invPanel.style.display  = isAdmin ? '' : 'none';
      if (leavePanel) leavePanel.style.display = isAdmin ? 'none' : '';
      _kancRenderClanovi(d.clanovi || [], isAdmin);
    }
  } catch(e) { _kancShow('no-firma'); }
}

function _kancRenderClanovi(clanovi, isAdmin) {
  var list = document.getElementById('kancelarija-clanovi-list');
  if (!list) return;
  if (!clanovi.length) { list.innerHTML = '<div style="font-size:0.75rem;color:rgba(255,255,255,0.3);">Nema članova.</div>'; return; }
  var statusLabels = {pending:'Čeka', aktivan:'Aktivan', odbijen:'Odbijen'};
  var statusColors = {pending:'#c9a84c', aktivan:'#4ade80', odbijen:'#f87171'};
  list.innerHTML = clanovi.map(function(c){
    var stColor = statusColors[c.status] || '#aaa';
    var stLabel = statusLabels[c.status] || c.status;
    var actions = '';
    if (isAdmin) {
      var roleOpts = ['partner','saradnik','citanje'].map(function(u){
        return '<option value="'+u+'"'+(c.uloga===u?' selected':'')+'>'+({partner:'Partner',saradnik:'Saradnik',citanje:'Čitanje'}[u]||u)+'</option>';
      }).join('');
      actions = '<select onchange="kancPromeniUlogu(\''+c.id+'\',this.value)" style="background:rgba(13,27,42,0.95);border:1px solid rgba(255,255,255,0.15);border-radius:5px;padding:2px 5px;color:rgba(255,255,255,0.8);font-size:0.72rem;outline:none;font-family:inherit;cursor:pointer;">'+roleOpts+'</select>'
        +'<button onclick="kancUkloni(\''+c.id+'\',\''+c.email+'\')" style="background:none;border:1px solid rgba(239,68,68,0.3);border-radius:5px;padding:2px 7px;color:#f87171;font-size:0.72rem;cursor:pointer;font-family:inherit;">×</button>';
    }
    return '<div style="display:flex;align-items:center;gap:0.4rem;padding:0.3rem 0.45rem;background:rgba(255,255,255,0.03);border-radius:6px;">'
      +'<span style="flex:1;font-size:0.78rem;color:rgba(255,255,255,0.8);">'+c.email+'</span>'
      +'<span style="font-size:0.65rem;color:'+stColor+';padding:1px 5px;border-radius:3px;border:1px solid '+stColor+'33;">'+stLabel+'</span>'
      +actions+'</div>';
  }).join('');
}

async function kancelarijaKreiraj() {
  if (!currentSession) return;
  var inp = document.getElementById('kancelarija-new-naziv');
  var errEl = document.getElementById('kancelarija-kreiraj-err');
  if (!inp || !inp.value.trim()) { if(errEl){errEl.textContent='Unesite naziv.';errEl.style.display='';} return; }
  try {
    var r = await fetch('/api/kancelarija/kreiraj', {
      method:'POST', headers:{'Authorization':'Bearer '+currentSession.access_token,'Content-Type':'application/json'},
      body: JSON.stringify({naziv: inp.value.trim()})
    });
    var d = await r.json();
    if (!r.ok) { if(errEl){errEl.textContent=d.detail||'Greška.';errEl.style.display='';} return; }
    if (errEl) errEl.style.display = 'none';
    inp.value = '';
    await kancelarijaLoad();
  } catch(e) { if(errEl){errEl.textContent='Greška mreže.';errEl.style.display='';} }
}

async function kancPrihvati() {
  if (!currentSession) return;
  var errEl = document.getElementById('kancelarija-pending-err');
  try {
    var r = await fetch('/api/kancelarija/prihvati', {method:'POST', headers:{'Authorization':'Bearer '+currentSession.access_token}});
    if (!r.ok) { var d=await r.json(); if(errEl){errEl.textContent=d.detail||'Greška.';errEl.style.display='';} return; }
    await kancelarijaLoad();
  } catch(e) { if(errEl){errEl.textContent='Greška mreže.';errEl.style.display='';} }
}

async function kancOdbij() {
  if (!currentSession) return;
  if (!confirm('Odbiti pozivnicu?')) return;
  try {
    await fetch('/api/kancelarija/odbij', {method:'POST', headers:{'Authorization':'Bearer '+currentSession.access_token}});
    await kancelarijaLoad();
  } catch(e) {}
}

async function kancPozovi() {
  if (!currentSession) return;
  var emailInp = document.getElementById('kancelarija-invite-email');
  var ulogaInp = document.getElementById('kancelarija-invite-uloga');
  var stEl = document.getElementById('kancelarija-invite-status');
  if (!emailInp || !emailInp.value.trim()) return;
  try {
    var r = await fetch('/api/kancelarija/pozovi', {
      method:'POST', headers:{'Authorization':'Bearer '+currentSession.access_token,'Content-Type':'application/json'},
      body: JSON.stringify({email: emailInp.value.trim(), uloga: ulogaInp ? ulogaInp.value : 'saradnik'})
    });
    var d = await r.json();
    if (!r.ok) {
      if(stEl){stEl.textContent=d.detail||'Greška.';stEl.style.color='#f87171';stEl.style.display='';}
    } else {
      if(stEl){stEl.textContent='Poziv poslat na '+emailInp.value.trim();stEl.style.color='#4ade80';stEl.style.display='';}
      emailInp.value = '';
      await kancelarijaLoad();
    }
    setTimeout(function(){ if(stEl) stEl.style.display='none'; }, 4000);
  } catch(e) { if(stEl){stEl.textContent='Greška mreže.';stEl.style.color='#f87171';stEl.style.display='';} }
}

async function kancUkloni(clanId, email) {
  if (!currentSession) return;
  if (!confirm('Ukloniti '+email+' iz firme?')) return;
  try {
    var r = await fetch('/api/kancelarija/ukloni/'+clanId, {method:'DELETE', headers:{'Authorization':'Bearer '+currentSession.access_token}});
    if (!r.ok) { var d=await r.json(); showToast(d.detail||'Greška.', 'err'); return; }
    await kancelarijaLoad();
  } catch(e) { showToast('Greška mreže.', 'err'); }
}

async function kancPromeniUlogu(clanId, uloga) {
  if (!currentSession) return;
  try {
    var r = await fetch('/api/kancelarija/uloga/'+clanId, {
      method:'PUT', headers:{'Authorization':'Bearer '+currentSession.access_token,'Content-Type':'application/json'},
      body: JSON.stringify({uloga: uloga})
    });
    if (!r.ok) { var d=await r.json(); showToast(d.detail||'Greška.', 'err'); await kancelarijaLoad(); }
  } catch(e) { showToast('Greška mreže.', 'err'); }
}

async function kancRename() {
  if (!currentSession || !_kancData || !_kancData.firma) return;
  var novi = prompt('Novi naziv firme:', _kancData.firma.naziv || '');
  if (!novi || !novi.trim()) return;
  try {
    var r = await fetch('/api/kancelarija/naziv', {
      method:'PUT', headers:{'Authorization':'Bearer '+currentSession.access_token,'Content-Type':'application/json'},
      body: JSON.stringify({naziv: novi.trim()})
    });
    if (!r.ok) { var d=await r.json(); showToast(d.detail||'Greška.', 'err'); return; }
    await kancelarijaLoad();
  } catch(e) { showToast('Greška mreže.', 'err'); }
}

async function kancOstavi() {
  if (!currentSession) return;
  if (!confirm('Napustiti firmu? Izgubićete pristup svim deljenim predmetima.')) return;
  try {
    var r = await fetch('/api/kancelarija/napusti', {method:'DELETE', headers:{'Authorization':'Bearer '+currentSession.access_token}});
    if (!r.ok) { var d=await r.json(); showToast(d.detail||'Greška.', 'err'); return; }
    await kancelarijaLoad();
  } catch(e) { showToast('Greška mreže.', 'err'); }
}

// Reset lozinke iz Podešavanja
function doForgotPasswordFromSettings() {
  var email = currentUser ? (currentUser.email || '') : '';
  if (!email) { showToast('Email adresa nije dostupna. Prijavite se ponovo.', 'err'); return; }
  var sb2 = getSupabase ? getSupabase() : sb;
  if (!sb2) { showToast('Greška: Supabase nije dostupan.', 'err'); return; }
  showToast('Šaljemo reset link na ' + email + '...', 'info');
  sb2.auth.resetPasswordForEmail(email, {redirectTo: window.location.origin + window.location.pathname})
    .then(function(r){
      if (!r.error) showToast('Link poslat na ' + email + ' — proverite inbox ✓', 'info');
      else showToast('Greška: ' + (r.error.message || 'Pokušajte ponovo.'), 'err');
    });
}

function _updateProTabUI() {
  var tabBtn = document.getElementById('tab-btn-n');
  var badge  = document.getElementById('pro-badge-n');
  if (!tabBtn) return;
  if (currentUserIsPro) {
    tabBtn.classList.remove('locked');
    if (badge) { badge.textContent = 'PRO'; badge.style.background = ''; }
    tabBtn.title = 'PRO funkcija — pristup omogućen';
  } else {
    tabBtn.classList.add('locked');
    if (badge) badge.textContent = '\uD83D\uDD12 PRO';
    tabBtn.title = 'Ova funkcija je dostupna isključivo PRO korisnicima';
  }
}

function openProUpgradeModal() {
  var m = document.getElementById('pro-upgrade-modal');
  if (m) { m.classList.add('open'); document.body.style.overflow = 'hidden'; }
}

function _updateStratTabUI() {
  var tabBtn = document.getElementById('tab-btn-t');
  var badge  = document.getElementById('pro-badge-t');
  if (!tabBtn) return;
  if (currentUserIsPro) {
    tabBtn.classList.remove('locked');
    if (badge) { badge.textContent = 'PRO'; badge.style.background = ''; }
    tabBtn.title = 'PRO funkcija — pristup omogućen';
  } else {
    tabBtn.classList.add('locked');
    if (badge) badge.textContent = '🔒 PRO';
    tabBtn.title = 'Ova funkcija je dostupna isključivo PRO korisnicima';
  }
}

// ── F5 AI STRATEGIJA ──────────────────────────────────────────────────────────

var STRAT_MODULI = {
  red_team: {
    naziv:    'Red Team analiza',
    endpoint: '/strategija/red-team',
    opis:     'Analizira slabosti tvog predmeta iz perspektive protivne strane. Identifikuje rupe, procesne zamke i argumente koje će protivnik koristiti.',
    label:    'Opis predmeta (tvoja strana, činjenice, dokazi)',
    min:      50
  },
  litigation: {
    naziv:    'Litigation Simulator',
    endpoint: '/strategija/litigation',
    opis:     'Procenjuje verovatnoću uspeha na sudu u % na osnovu srpske sudske prakse. Preporučuje strategiju: tužba / odbrana / nagodba.',
    label:    'Opis predmeta (strane, činjenice, pravni osnov)',
    min:      50
  },
  sudija: {
    naziv:    'Procena ishoda predmeta',
    endpoint: '/strategija/sudija',
    opis:     'Neutralna analiza predmeta iz perspektive iskusnog sudije. Procenjuje osnovanost navoda obe strane bez favorizovanja.',
    label:    'Opis predmeta (navodi obe strane, procesni stadijum)',
    min:      50
  },
  due_diligence: {
    naziv:    'Due Diligence',
    endpoint: '/strategija/due-diligence',
    opis:     'Sistematski pregled ugovora ili dokumenta — kritični rizici, formalni nedostaci, nedostajuće klauzule, preporuka.',
    label:    'Tekst dokumenta / ugovora za analizu',
    min:      100
  },
  revizor: {
    naziv:    'Revizija dokumenta',
    endpoint: '/strategija/revizor',
    opis:     'Pregledava dokument ili nacrt i predlaže konkretne izmene. Identifikuje kritične greške, formalne nedostatke i daje gotove formulacije za ispravke.',
    label:    'Tekst dokumenta ili nacrta za reviziju',
    min:      100
  },
  witness: {
    naziv:    'Analiza iskaza',
    endpoint: '/strategija/witness',
    opis:     'Analizira iskaz ili svedočenje — identifikuje unutrašnje kontradikcije, sumnjive delove i generiše pitanja za unakrsno ispitivanje.',
    label:    'Tekst iskaza, svedočenja ili izjave stranke',
    min:      50,
    tip:      'standard'
  },
  sudija_v2: {
    naziv:    'Simulacija sudskog postupka',
    endpoint: '/strategija/sudija-v2',
    opis:     'Trostepena simulacija: AI tužilac iznosi argumente → AI branilac odgovara → AI sudija donosi odluku. Najrealističniji prikaz sudskog ishoda.',
    label:    'Opis predmeta (strane, činjenice, pravni osnov, stadijum postupka)',
    min:      100,
    tip:      'debate'
  }
};

var _stratAktivniModul = 'red_team';

// Inicijalizacija opisa i labele pri prvom prikazu taba
(function() {
  if (!STRAT_MODULI) return;
  var m = STRAT_MODULI['red_team'];
  document.addEventListener('DOMContentLoaded', function() {
    var opisEl = document.getElementById('strat-opis');
    var labelEl = document.getElementById('strat-input-label');
    if (opisEl && m) opisEl.textContent = m.opis;
    if (labelEl && m) labelEl.textContent = m.label;
    var tekstEl = document.getElementById('strat-tekst');
    if (tekstEl) tekstEl.addEventListener('input', function() {
      var c = document.getElementById('strat-chars');
      if (c) c.textContent = this.value.length;
    });
  });
})();

function stratIzaberiModul(modul, btn) {
  _stratAktivniModul = modul;
  document.querySelectorAll('.strat-btn').forEach(function(b) { b.classList.remove('active'); });
  btn.classList.add('active');
  var m = STRAT_MODULI && STRAT_MODULI[modul];
  if (!m) return;
  var opisEl = document.getElementById('strat-opis');
  var labelEl = document.getElementById('strat-input-label');
  if (opisEl) opisEl.textContent = m.opis;
  if (labelEl) labelEl.textContent = m.label;
  // Sakrij prethodni rezultat i resetuj polje
  var wrapEl = document.getElementById('strat-rezultat-wrap');
  var tekstEl = document.getElementById('strat-tekst');
  var charsEl = document.getElementById('strat-chars');
  if (wrapEl) wrapEl.style.display = 'none';
  if (tekstEl) tekstEl.value = '';
  if (charsEl) charsEl.textContent = '0';
}

async function stratPokreni() {
  var tekstEl   = document.getElementById('strat-tekst');
  var submitBtn = document.getElementById('strat-submit-btn');
  var wrapEl    = document.getElementById('strat-rezultat-wrap');
  var naslovEl  = document.getElementById('strat-rezultat-naslov');
  var bodyEl    = document.getElementById('strat-rezultat-body');

  var tekst = tekstEl ? tekstEl.value.trim() : '';
  var modul = STRAT_MODULI[_stratAktivniModul];

  if (!currentUser) { openModal(); return; }

  if (!currentUserIsPro) {
    if (wrapEl) wrapEl.style.display = 'block';
    if (bodyEl) bodyEl.innerHTML = '<div class="strat-pro-gate">🔒 <strong>' + modul.naziv + '</strong> je dostupna samo PRO korisnicima.<br><small>Upgrade na PRO za pristup svim AI strategijskim alatima.</small></div>';
    if (naslovEl) naslovEl.textContent = modul.naziv;
    return;
  }

  if (tekst.length < modul.min) {
    if (wrapEl) wrapEl.style.display = 'block';
    if (bodyEl) bodyEl.innerHTML = '<div class="strat-error">Unesite najmanje ' + modul.min + ' karaktera.</div>';
    if (naslovEl) naslovEl.textContent = modul.naziv;
    return;
  }

  if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Analiziram...'; }
  if (wrapEl) wrapEl.style.display = 'block';
  if (naslovEl) naslovEl.textContent = modul.naziv;
  if (bodyEl) bodyEl.innerHTML = '<div class="strat-loading">⏳ ' + modul.naziv + ' u toku...</div>';

  piTrack('strategija','query',{modul:_stratAktivniModul});
  try {
    var res = await fetch(BASE_URL + modul.endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + (currentSession ? currentSession.access_token : '')
      },
      body: JSON.stringify({ tekst: tekst })
    });

    if (res.status === 403) {
      if (bodyEl) bodyEl.innerHTML = '<div class="strat-pro-gate">🔒 <strong>' + modul.naziv + '</strong> je dostupna samo PRO korisnicima.<br><small>Upgrade na PRO za pristup svim AI strategijskim alatima.</small></div>';
      return;
    }

    // HTTP 202 = dugotrajni posao → polling
    if (res.status === 202) {
      var jobData = await res.json();
      if (bodyEl) bodyEl.innerHTML = '<div class="strat-loading">⏳ Analiza pokrenuta (posao: '+jobData.job_id.slice(0,8)+'...)<br><small>Ovo može trajati 60-90 sekundi. Pratimo napredak...</small></div>';
      await strat_job_poll(jobData.job_id, bodyEl, submitBtn);
      return;
    }

    if (!res.ok) throw new Error('Server greška: ' + res.status);

    var data = await res.json();
    if (data.modul === 'sudija_v2') {
      if (bodyEl) bodyEl.innerHTML =
        '<div class="debate-sekcija debate-tuzilac">'
        + '<div class="debate-header">⚔️ TUŽILAC — Argumenti</div>'
        + '<div class="debate-sadrzaj">' + stratFormatirajRezultat(data.tuzilac || '') + '</div>'
        + '</div>'
        + '<div class="debate-sekcija debate-branilac">'
        + '<div class="debate-header">🛡️ BRANILAC — Odgovor</div>'
        + '<div class="debate-sadrzaj">' + stratFormatirajRezultat(data.branilac || '') + '</div>'
        + '</div>'
        + '<div class="debate-sekcija debate-presuda">'
        + '<div class="debate-header">👨‍⚖️ SUDIJA — Odluka</div>'
        + '<div class="debate-sadrzaj">' + stratFormatirajRezultat(data.presuda || '') + '</div>'
        + '</div>';
    } else {
      if (bodyEl) bodyEl.innerHTML = stratFormatirajRezultat(data.rezultat || '');
    }

  } catch(e) {
    if (bodyEl) bodyEl.innerHTML = '<div class="strat-error">Greška: ' + _htmlEsc(e.message) + '</div>';
  } finally {
    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Pokreni analizu'; }
  }
}

// Polling za async AI poslove (HTTP 202 pattern)
async function strat_job_poll(jobId, bodyEl, submitBtn) {
  var elapsed = 0;
  var dotStr  = ['⏳', '⌛', '⏳', '⌛'];
  var dotIdx  = 0;
  while (elapsed < 180) { // max 3 minuta
    await new Promise(function(r){ setTimeout(r, 4000); });
    elapsed += 4;
    try {
      var r = await fetch(BASE_URL + '/api/jobs/' + jobId, {
        headers: { 'Authorization': 'Bearer ' + (currentSession ? currentSession.access_token : '') }
      });
      if (!r.ok) { if (bodyEl) bodyEl.innerHTML = '<div class="strat-error">Greška pri proveri statusa.</div>'; break; }
      var j = await r.json();
      if (j.status === 'done') {
        var d = j.result || {};
        if (bodyEl) bodyEl.innerHTML = stratFormatirajRezultat(d.rezultat || JSON.stringify(d, null, 2));
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Pokreni analizu'; }
        return;
      }
      if (j.status === 'error') {
        if (bodyEl) bodyEl.innerHTML = '<div class="strat-error">Greška: ' + _htmlEsc(j.error || 'Nepoznata greška') + '</div>';
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Pokreni analizu'; }
        return;
      }
      // pending/running — ažuriraj prikaz
      if (bodyEl) bodyEl.innerHTML = '<div class="strat-loading">'+dotStr[dotIdx%4]+' Analiza u toku — '+elapsed+'s...<br><small>Kompleksna analiza (6 AI modula) traje 60-90s.</small></div>';
      dotIdx++;
    } catch(e) {
      if (bodyEl) bodyEl.innerHTML = '<div class="strat-error">Greška: ' + _htmlEsc(e.message) + '</div>';
      break;
    }
  }
  if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Pokreni analizu'; }
}

function stratFormatirajRezultat(tekst) {
  if (!tekst) return '';
  var escaped = tekst
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  return escaped
    .replace(/^(\d+\.\s+[A-ZŠĐŽČĆА-Я\s]{3,})$/gm, '<span class="strat-sekcija">$1</span>')
    .replace(/^(🔴[^\n]+)$/gm, '<span class="strat-kritican">$1</span>')
    .replace(/^(🟡[^\n]+)$/gm, '<span class="strat-upozorenje">$1</span>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
}

function stratKopiraj() {
  var bodyEl = document.getElementById('strat-rezultat-body');
  if (!bodyEl) return;
  var tekst = bodyEl.innerText || bodyEl.textContent;
  navigator.clipboard.writeText(tekst).then(function() {
    var btn = document.querySelector('.strat-copy-btn');
    if (btn) {
      btn.textContent = '✓ Kopirano';
      setTimeout(function() { btn.textContent = '📋 Kopiraj'; }, 2000);
    }
  });
}

// ── F6 DOCX EXPORT ────────────────────────────────────────────────────────────

async function exportujKaoWord(naslov, tekst, tip) {
  tip = tip || 'analiza';
  if (!tekst || tekst.trim().length < 20) {
    showToast('Nema sadržaja za export.', 'warn');
    return;
  }
  if (!currentSession) { openModal(); return; }
  try {
    var res = await fetch(BASE_URL + '/export/docx', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + currentSession.access_token
      },
      body: JSON.stringify({ naslov: naslov || 'Vindex analiza', tekst: tekst, tip: tip })
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    var blob = await res.blob();
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'vindex_' + (naslov || 'analiza').replace(/\s+/g, '_').substring(0, 40) + '.docx';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch(e) {
    showToast('Greška pri exportu: ' + e.message, 'err');
  }
}

// ── F6 API KLJUČEVI ───────────────────────────────────────────────────────────

async function ucitajApiKljuceve() {
  var sekcija = document.getElementById('api-kljucevi-sekcija');
  var lista   = document.getElementById('api-kljucevi-lista');
  if (!sekcija || !lista || !currentSession) return;
  try {
    var res = await fetch(BASE_URL + '/api-kljucevi/lista', {
      headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
    });
    if (res.status === 403) { sekcija.style.display = 'none'; return; }
    sekcija.style.display = 'block';
    var data = await res.json();
    if (!data.kljucevi || !data.kljucevi.length) {
      lista.innerHTML = '<div style="font-size:0.8rem;color:rgba(255,255,255,0.28);padding:4px 0;">Nema aktivnih API ključeva.</div>';
      return;
    }
    lista.innerHTML = data.kljucevi.map(function(k) {
      var dat = k.poslednje_koriscenje
        ? new Date(k.poslednje_koriscenje).toLocaleDateString('sr-RS')
        : 'Nije korišćen';
      return '<div class="api-kljuc-red">' +
        '<span class="api-kljuc-naziv">' + _htmlEsc(k.naziv) + '</span>' +
        '<span class="api-kljuc-stat">' + (k.broj_poziva || 0) + ' poziva</span>' +
        '<span class="api-kljuc-datum">' + dat + '</span>' +
        '<button class="btn-danger-small" onclick="opoziviApiKljuc(\'' + k.id + '\')">Opozovi</button>' +
        '</div>';
    }).join('');
  } catch(e) { console.warn('API ključevi greška:', e); }
}

async function kreirajApiKljuc() {
  if (!currentSession) { openModal(); return; }
  var naziv = (document.getElementById('api-kljuc-naziv').value || '').trim() || 'Default';
  try {
    var res = await fetch(BASE_URL + '/api-kljucevi/novi', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + currentSession.access_token
      },
      body: JSON.stringify({ naziv: naziv })
    });
    var data = await res.json();
    if (!res.ok) { showToast(data.detail || 'Greška', 'err'); return; }
    var display = document.getElementById('api-novi-kljuc-display');
    display.innerHTML =
      '<strong>Novi API ključ — sačuvajte, neće biti ponovo prikazan:</strong>' +
      '<span class="api-kljuc-value">' + data.kljuc + '</span>' +
      '<button class="btn-word" onclick="navigator.clipboard.writeText(\'' + data.kljuc + '\');showToast(\'Ključ kopiran\')">📋 Kopiraj</button>';
    display.style.display = 'block';
    document.getElementById('api-kljuc-naziv').value = '';
    await ucitajApiKljuceve();
  } catch(e) { showToast('Greška: ' + e.message, 'err'); }
}

async function opoziviApiKljuc(id) {
  if (!confirm('Opozovite ovaj API ključ? Integracije koje ga koriste prestaće da rade.')) return;
  if (!currentSession) return;
  await fetch(BASE_URL + '/api-kljucevi/' + id, {
    method: 'DELETE',
    headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
  });
  await ucitajApiKljuceve();
}

// ── F6 WEB PUSH ───────────────────────────────────────────────────────────────

// VAPID public key se učitava sa servera
var _vapidPublicKey = null;

async function _getVapidKey() {
  if (_vapidPublicKey) return _vapidPublicKey;
  try {
    var r = await fetch(BASE_URL + '/push/vapid-public');
    if (!r.ok) return null;
    var d = await r.json();
    _vapidPublicKey = d.public_key || null;
    return _vapidPublicKey;
  } catch(e) { return null; }
}

function _urlBase64ToUint8Array(base64String) {
  var padding = '='.repeat((4 - base64String.length % 4) % 4);
  var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  var rawData = window.atob(base64);
  return Uint8Array.from(Array.from(rawData).map(function(c) { return c.charCodeAt(0); }));
}

async function subscribePush() {
  var btn = document.getElementById('push-btn');
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    if (btn) { btn.textContent = '❌ Browser ne podržava push'; btn.disabled = true; }
    return;
  }
  if (!currentSession) { openModal(); return; }
  var vapidKey = await _getVapidKey();
  if (!vapidKey) {
    if (btn) { btn.textContent = '⚠ Push nije konfigurisan'; btn.disabled = true; }
    return;
  }
  try {
    var reg = await navigator.serviceWorker.ready;
    var sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: _urlBase64ToUint8Array(vapidKey)
    });
    var subJson = sub.toJSON();
    var res = await fetch(BASE_URL + '/push/subscribe', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + currentSession.access_token
      },
      body: JSON.stringify({
        endpoint: subJson.endpoint,
        p256dh:   subJson.keys.p256dh,
        auth:     subJson.keys.auth
      })
    });
    if (res.ok) {
      if (btn) { btn.textContent = '✓ Notifikacije uključene'; btn.disabled = true; }
      showToast('Push notifikacije uključene');
    }
  } catch(e) {
    console.error('Push subscribe greška:', e);
    if (btn) btn.textContent = '⚠ Greška — provjerite dozvole';
  }
}
function closeProUpgradeModal() {
  var m = document.getElementById('pro-upgrade-modal');
  if (m) { m.classList.remove('open'); document.body.style.overflow = ''; }
}

// ── F7 PLAYBOOK UI ────────────────────────────────────────────────────────────

async function ucitajPlaybookStatus() {
  var panel = document.getElementById('playbook-detalji');
  if (!panel || !currentSession) return;
  if (!currentUserIsPro) { panel.style.display = 'none'; return; }
  panel.style.display = '';
  try {
    var res = await fetch(BASE_URL + '/api/playbook/status', {
      headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
    });
    if (res.status === 403) { panel.style.display = 'none'; return; }
    var data = await res.json();
    var count = data.chunk_count || 0;
    var badge = document.getElementById('playbook-count-badge');
    if (badge) {
      badge.textContent = count > 0 ? count + ' vektora' : '';
      badge.style.display = count > 0 ? 'inline' : 'none';
    }
    var lista = document.getElementById('playbook-lista');
    if (lista) {
      if (count === 0) {
        lista.innerHTML = '<p class="playbook-prazno">Nema uploadovanih dokumenata.</p>';
      } else {
        lista.innerHTML = '<p class="playbook-prazno">' + count + ' vektora indeksirano i aktivno.</p>';
      }
    }
  } catch(e) { console.warn('Playbook status greška:', e); }
}

async function playbookUploadFajlove(files) {
  if (!currentSession) { openModal(); return; }
  var progress = document.getElementById('playbook-progress');
  if (progress) progress.style.display = 'block';
  var uspešno = 0;
  for (var i = 0; i < files.length; i++) {
    var file = files[i];
    if (progress) progress.textContent = 'Uplodujem: ' + file.name + '...';
    var formData = new FormData();
    formData.append('file', file);
    try {
      var res = await fetch(BASE_URL + '/api/playbook/upload', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + currentSession.access_token },
        body: formData
      });
      if (res.ok) {
        uspešno++;
      } else {
        var err = await res.json().catch(function(){return {};});
        if (progress) { progress.textContent = 'Greška: ' + (err.detail || 'Upload nije uspeo'); }
        await new Promise(function(r){setTimeout(r,2000);});
      }
    } catch(e) {
      if (progress) { progress.textContent = 'Greška: ' + e.message; }
      await new Promise(function(r){setTimeout(r,2000);});
    }
  }
  if (progress) progress.textContent = '✓ ' + uspešno + '/' + files.length + ' fajlova uploadovano';
  await ucitajPlaybookStatus();
  setTimeout(function(){ if(progress) progress.style.display='none'; }, 3000);
  var input = document.getElementById('playbook-file-input');
  if (input) input.value = '';
}

function playbookDrop(event) {
  event.preventDefault();
  var files = event.dataTransfer.files;
  if (files && files.length) playbookUploadFajlove(files);
}

async function obrisiSvPlaybook() {
  if (!confirm('Obrisati sve firminine dokumente iz Playbook-a? Ova akcija je nepovratna.')) return;
  if (!currentSession) return;
  try {
    var res = await fetch(BASE_URL + '/api/playbook', {
      method: 'DELETE',
      headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
    });
    if (res.ok) { await ucitajPlaybookStatus(); showToast('Playbook obrisan'); }
    else showToast('Greška pri brisanju.', 'err');
  } catch(e) { showToast('Greška: ' + e.message, 'err'); }
}

// ── F7 INTERNI STAVOVI ────────────────────────────────────────────────────────

async function dodajInterniStav() {
  var naslov = (document.getElementById('interni-naslov').value || '').trim();
  var tekst  = (document.getElementById('interni-tekst').value  || '').trim();
  if (!naslov || naslov.length < 3) { showToast('Naslov je obavezan (min 3 karaktera).', 'warn'); return; }
  if (!tekst  || tekst.length  < 30) { showToast('Tekst stava mora imati min 30 karaktera.', 'warn'); return; }
  if (!currentSession) { openModal(); return; }
  try {
    var res = await fetch(BASE_URL + '/interni-stavovi/dodaj', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + currentSession.access_token
      },
      body: JSON.stringify({ naslov: naslov, tekst: tekst })
    });
    if (res.status === 403) { showToast('PRO funkcija.', 'warn'); return; }
    var data = await res.json();
    if (res.ok) {
      showToast('✓ Stav dodat (' + data.vektori + ' vektora)');
      document.getElementById('interni-naslov').value = '';
      document.getElementById('interni-tekst').value  = '';
    } else {
      showToast(data.detail || 'Greška.', 'err');
    }
  } catch(e) { showToast('Greška: ' + e.message, 'err'); }
}

async function pretraziInterneStavove() {
  var upit = (document.getElementById('interni-upit').value || '').trim();
  if (!upit) return;
  if (!currentSession) { openModal(); return; }
  var div = document.getElementById('interni-rezultati');
  div.innerHTML = '<div class="strat-loading">Pretražujem...</div>';
  try {
    var res = await fetch(BASE_URL + '/interni-stavovi/pretraga', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + currentSession.access_token
      },
      body: JSON.stringify({ upit: upit })
    });
    var data = await res.json();
    if (!res.ok) { div.innerHTML = '<div class="strat-error">Greška: ' + _htmlEsc(data.detail||'') + '</div>'; return; }
    if (!data.rezultati || !data.rezultati.length) {
      div.innerHTML = '<p class="playbook-prazno">Nema rezultata za ovaj upit.</p>';
      return;
    }
    div.innerHTML = data.rezultati.map(function(r) {
      var tekst = (r.tekst || '').substring(0, 220);
      if ((r.tekst||'').length > 220) tekst += '...';
      return '<div class="interni-rezultat-red">' +
        '<span class="interni-score">' + Math.round(r.score * 100) + '%</span>' +
        '<span class="interni-rezultat-naslov">' + _htmlEsc(r.naslov || '') + '</span>' +
        '<span class="interni-rezultat-tekst">' + _htmlEsc(tekst) + '</span>' +
        '</div>';
    }).join('');
  } catch(e) {
    div.innerHTML = '<div class="strat-error">Greška: ' + _htmlEsc(e.message) + '</div>';
  }
}

async function obrisiSveInterneStavove() {
  if (!confirm('Obrisati sve interne stavove? Ova akcija je nepovratna.')) return;
  if (!currentSession) return;
  try {
    var res = await fetch(BASE_URL + '/interni-stavovi/obrisi-sve', {
      method: 'DELETE',
      headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
    });
    if (res.ok) showToast('✓ Svi interni stavovi obrisani.');
    else showToast('Greška pri brisanju.', 'err');
  } catch(e) { showToast('Greška: ' + e.message, 'err'); }
}

function _htmlEsc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ── F8: KOMENTARI ─────────────────────────────────────────── */
var _aktPredmetId = null;

async function ucitajKomentare(predmetId) {
  _aktPredmetId = predmetId;
  var lista = document.getElementById('pred-kom-lista');
  if (!lista) return;
  lista.innerHTML = '<span style="font-size:0.75rem;color:rgba(255,255,255,0.25);">Učitavam...</span>';
  try {
    var r = await fetch('/predmeti/'+predmetId+'/komentari', {
      headers: {'Authorization':'Bearer '+currentSession.access_token}
    });
    var d = await r.json();
    var koms = d.komentari || [];
    if (!koms.length) { lista.innerHTML = '<div style="font-size:0.76rem;color:rgba(255,255,255,0.25);padding:6px 0;">Nema komentara.</div>'; return; }
    lista.innerHTML = koms.map(function(k){
      var dat = k.kreirano ? new Date(k.kreirano).toLocaleString('sr-RS',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}) : '';
      var izmTag = k.izmenjeno ? ' · izmenjeno' : '';
      return '<div class="kom-red" data-kid="'+_htmlEsc(k.id)+'">'
        +'<div class="kom-meta">'+_htmlEsc(dat)+izmTag+'</div>'
        +'<div class="kom-tekst">'+_htmlEsc(k.tekst)+'</div>'
        +'<div class="kom-akcije"><button class="kom-btn-del" onclick="obrisiKomentar(\''+_htmlEsc(k.id)+'\')">Obriši</button></div>'
        +'</div>';
    }).join('');
  } catch(e) {
    lista.innerHTML = '<div style="font-size:0.76rem;color:rgba(255,80,80,0.5);">Greška pri učitavanju.</div>';
  }
}

async function dodajKomentar() {
  var inp = document.getElementById('pred-kom-input');
  if (!inp || !_aktPredmetId) return;
  var tekst = inp.value.trim();
  if (!tekst) return;
  inp.disabled = true;
  try {
    await fetch('/predmeti/'+_aktPredmetId+'/komentari', {
      method:'POST',
      headers:{'Content-Type':'application/json','Authorization':'Bearer '+currentSession.access_token},
      body: JSON.stringify({tekst: tekst})
    });
    inp.value = '';
    ucitajKomentare(_aktPredmetId);
  } catch(e) {}
  inp.disabled = false;
}

async function obrisiKomentar(komId) {
  if (!confirm('Obrisati komentar?')) return;
  await fetch('/komentari/'+komId, {
    method:'DELETE',
    headers:{'Authorization':'Bearer '+currentSession.access_token}
  });
  if (_aktPredmetId) ucitajKomentare(_aktPredmetId);
}

/* ── F8: CRM KLIJENTI ──────────────────────────────────────── */
var _crmTip = 'fizicko_lice';
var crmAktivniId = null;
var _crmProfilData = null;

async function ucitajKlijente(pretraga) {
  var lista = document.getElementById('crm-lista');
  if (!lista) return;
  lista.innerHTML = '<div class="crm-prazno">Učitavam...</div>';
  var url = '/klijenti' + (pretraga ? '?pretraga='+encodeURIComponent(pretraga) : '');
  try {
    var r = await fetch(url, {headers:{'Authorization':'Bearer '+currentSession.access_token}});
    var d = await r.json();
    var klijenti = d.klijenti || [];
    if (!klijenti.length) {
      lista.innerHTML = '<div class="crm-prazno">Nema klijenata. Dodajte prvog klikom na "+ Novi klijent".</div>';
      return;
    }
    lista.innerHTML = klijenti.map(function(k){
      var sub = [k.firma, k.email, k.telefon].filter(Boolean).join(' · ');
      return '<div class="crm-kartica" onclick="crmOtvoriProfil(\''+_htmlEsc(k.id)+'\')">'
        +'<div class="crm-kartica-ime">'+_htmlEsc((k.ime||'')+' '+(k.prezime||''))+'</div>'
        +(sub ? '<div class="crm-kartica-sub">'+_htmlEsc(sub)+'</div>' : '')
        +'<div class="crm-kartica-sub" style="margin-top:4px;">'+_htmlEsc(k.status||'aktivan')+'</div>'
        +'</div>';
    }).join('');
  } catch(e) {
    lista.innerHTML = '<div class="crm-prazno" style="color:rgba(255,80,80,0.5);">Greška pri učitavanju.</div>';
  }
}

function crm_pretrazi() {
  var v = document.getElementById('crm-search-input');
  ucitajKlijente(v ? v.value.trim() : '');
}

async function crmOtvoriProfil(klijentId) {
  crmAktivniId = klijentId;
  document.getElementById('crm-lista-view').style.display = 'none';
  document.getElementById('crm-profil-view').style.display = 'block';
  document.getElementById('crm-podaci-javni').innerHTML = '<div class="crm-prazno">Učitavam...</div>';
  document.getElementById('crm-podaci-poverljivi').style.display = 'none';
  document.getElementById('crm-reveal-btn').textContent = 'Prikaži poverljive podatke';
  try {
    var r = await fetch('/klijenti/'+klijentId, {headers:{'Authorization':'Bearer '+currentSession.access_token}});
    var d = await r.json();
    _crmProfilData = d;
    var k = d.klijent || {};
    document.getElementById('crm-profil-ime').textContent = (k.ime||'') + ' ' + (k.prezime||'') + (k.firma ? ' · '+k.firma : '');
    crmRenderPodaci(k);
    crmRenderPredmeti(d.aktivni_predmeti || [], d.zavrseni_predmeti || []);
    crmUcitajTarifu(klijentId);
  } catch(e) {
    document.getElementById('crm-podaci-javni').innerHTML = '<div class="crm-prazno" style="color:rgba(255,80,80,0.5);">Greška.</div>';
  }
  crmProfilTab('podaci');
}

function crmZatvoriProfil() {
  crmAktivniId = null;
  document.getElementById('crm-profil-view').style.display = 'none';
  document.getElementById('crm-lista-view').style.display = 'block';
}

function crmProfilTab(tab) {
  ['podaci','aktivni','zavrseni','timeline','dokumenti'].forEach(function(t){
    var btn = document.getElementById('crm-pt-'+t);
    var pane = document.getElementById('crm-pane-'+t);
    if(btn) btn.classList.toggle('active', t===tab);
    if(pane) pane.style.display = t===tab ? 'block' : 'none';
  });
  if (tab === 'timeline' && crmAktivniId) crmUcitajTimeline(crmAktivniId);
  if (tab === 'dokumenti' && crmAktivniId) crmUcitajDokumente(crmAktivniId);
}

function crmRenderPodaci(k) {
  var polja = [
    ['Tip', k.tip], ['Status', k.status], ['Email', k.email],
    ['Telefon', k.telefon], ['Adresa', k.adresa], ['Matični broj', k.maticni_broj],
    ['Napomena', k.napomena], ['Pravni osnov', k.pravni_osnov_obrade],
    ['Datum nastanka', (k.datum_nastanka||'').slice(0,10)],
    ['Posl. aktivnost', (k.datum_poslednje_aktivnosti||'').slice(0,10)],
  ];
  document.getElementById('crm-podaci-javni').innerHTML = polja.filter(function(p){return p[1];}).map(function(p){
    return '<div class="crm-podaci-row"><span class="crm-podaci-lbl">'+_htmlEsc(p[0])+'</span><span class="crm-podaci-val">'+_htmlEsc(p[1])+'</span></div>';
  }).join('');
}

function crmRenderPredmeti(aktivni, zavrseni) {
  var aEl = document.getElementById('crm-aktivni-lista');
  var zEl = document.getElementById('crm-zavrseni-lista');
  function renderPred(arr, el) {
    if (!arr.length) { el.innerHTML='<div class="crm-prazno">Nema predmeta.</div>'; return; }
    el.innerHTML = arr.map(function(p){
      var pr = p.predmeti || {};
      return '<div class="crm-predmet-item"><b>'+_htmlEsc(pr.naziv||'—')+'</b> <span style="color:rgba(255,255,255,0.4);font-size:0.75rem;">'+_htmlEsc(p.uloga_klijenta||'')+'</span></div>';
    }).join('');
  }
  renderPred(aktivni, aEl);
  renderPred(zavrseni, zEl);
}

async function crmOtkrijPoverljivo() {
  if (!crmAktivniId) return;
  var btn = document.getElementById('crm-reveal-btn');
  var pane = document.getElementById('crm-podaci-poverljivi');
  if (pane.style.display === 'block') { pane.style.display='none'; btn.textContent='Prikaži poverljive podatke'; return; }
  btn.textContent = 'Učitavam...'; btn.disabled = true;
  try {
    var r = await fetch('/klijenti/'+crmAktivniId+'?reveal_confidential=true', {headers:{'Authorization':'Bearer '+currentSession.access_token}});
    if (r.status === 403) { alert('Nemate pravo uvida u poverljive podatke.'); btn.textContent='Prikaži poverljive podatke'; btn.disabled=false; return; }
    var d = await r.json();
    var k = d.klijent || {};
    var items = [['JMBG', k.jmbg], ['Broj pasoša', k.broj_pasosa], ['PIB', k.pib]].filter(function(i){return i[1];});
    if (!items.length) { pane.innerHTML='<div style="font-size:0.8rem;color:rgba(255,255,255,0.35);padding:8px 0;">Nema upisanih poverljivih podataka.</div>'; }
    else { pane.innerHTML = items.map(function(i){ return '<div class="crm-podaci-row"><span class="crm-podaci-lbl">'+_htmlEsc(i[0])+'</span><span class="crm-podaci-val" style="font-family:monospace;color:#ffd080;">'+_htmlEsc(i[1])+'</span></div>'; }).join(''); }
    pane.style.display = 'block';
    btn.textContent = 'Sakrij poverljive podatke';
  } catch(e) { alert('Greška.'); btn.textContent='Prikaži poverljive podatke'; }
  btn.disabled = false;
}

async function crmUcitajTimeline(klijentId) {
  var el = document.getElementById('crm-timeline-lista');
  el.innerHTML = '<div class="crm-prazno">Učitavam...</div>';
  try {
    var r = await fetch('/klijenti/'+klijentId+'/timeline', {headers:{'Authorization':'Bearer '+currentSession.access_token}});
    var d = await r.json();
    var events = d.timeline || [];
    if (!events.length) { el.innerHTML='<div class="crm-prazno">Nema aktivnosti.</div>'; return; }
    el.innerHTML = events.map(function(ev){
      return '<div class="crm-timeline-item"><div class="crm-tl-ikona">'+(ev.ikona||'📌')+'</div><div class="crm-tl-body"><div class="crm-tl-datum">'+_htmlEsc((ev.datum||'').slice(0,16).replace('T',' '))+'</div><div class="crm-tl-opis">'+_htmlEsc(ev.opis||ev.tip||'')+'</div></div></div>';
    }).join('');
  } catch(e) { el.innerHTML='<div class="crm-prazno" style="color:rgba(255,80,80,0.5);">Greška.</div>'; }
}

async function crmUcitajDokumente(klijentId) {
  var el = document.getElementById('crm-dokumenti-lista');
  el.innerHTML = '<div class="crm-prazno">Učitavam...</div>';
  try {
    var r = await fetch('/klijenti/'+klijentId+'/dokumenti', {headers:{'Authorization':'Bearer '+currentSession.access_token}});
    var d = await r.json();
    var docs = d.dokumenti || [];
    if (!docs.length) { el.innerHTML='<div class="crm-prazno">Nema dokumenata. <span style="color:rgba(255,255,255,0.3);font-size:0.75rem;">(Upload: advokat+)</span></div>'; return; }
    el.innerHTML = docs.map(function(doc){
      var size = doc.velicina ? (doc.velicina/1024).toFixed(0)+' KB' : '';
      return '<div class="crm-predmet-item" style="display:flex;justify-content:space-between;align-items:center;">'
        +'<span>'+_htmlEsc(doc.tip_dokumenta||'dokument')+' <span style="font-size:0.72rem;color:rgba(255,255,255,0.35);">'+_htmlEsc(size)+'</span></span>'
        +'<a href="/klijenti/'+_htmlEsc(klijentId)+'/dokumenti/'+_htmlEsc(doc.id)+'/download" class="crm-btn-edit" style="text-decoration:none;" target="_blank">⬇ Preuzmi</a>'
        +'</div>';
    }).join('');
  } catch(e) { el.innerHTML='<div class="crm-prazno" style="color:rgba(255,80,80,0.5);">Greška.</div>'; }
}

var _crmDirty = false;
function crmMarkDirty() { _crmDirty = true; }
function crmConfirmClose() {
  if (_crmDirty && !confirm('Imate nesačuvane izmene. Zatvoriti bez čuvanja?')) return;
  crmZatvoriFormu();
}
function crmValidateJmbg(el) {
  var v = el.value.replace(/\D/g,'');
  var w = document.getElementById('crm-jmbg-warn');
  if (w) w.style.display = (v.length > 0 && v.length !== 13) ? 'block' : 'none';
}

function crmOtvoriFormu(editId) {
  document.getElementById('crm-edit-id').value = editId || '';
  document.getElementById('crm-modal-title').textContent = editId ? 'Uredi klijenta' : 'Novi klijent';
  if (!editId) {
    ['crm-f-ime','crm-f-prezime','crm-f-firma','crm-f-email','crm-f-telefon','crm-f-jmbg','crm-f-pasos','crm-f-pib','crm-f-adresa','crm-f-napomena'].forEach(function(id){ var el=document.getElementById(id); if(el) el.value=''; });
    var w = document.getElementById('crm-jmbg-warn'); if (w) w.style.display='none';
    crmSetTip('fizicko_lice');
  }
  _crmDirty = false;
  document.getElementById('crm-overlay').classList.add('open');
}

function crmZatvoriFormu() {
  _crmDirty = false;
  document.getElementById('crm-overlay').classList.remove('open');
}

function crmSetTip(tip) {
  _crmTip = tip;
  document.getElementById('crm-tip-fiz').classList.toggle('active', tip === 'fizicko_lice');
  document.getElementById('crm-tip-prav').classList.toggle('active', tip === 'pravno_lice');
}

async function crmSacuvaj() {
  var editId = document.getElementById('crm-edit-id').value;
  var payload = {
    tip:                  _crmTip,
    ime:                  (document.getElementById('crm-f-ime').value || '').trim(),
    prezime:              (document.getElementById('crm-f-prezime').value || '').trim(),
    firma:                (document.getElementById('crm-f-firma').value || '').trim(),
    email:                (document.getElementById('crm-f-email').value || '').trim(),
    telefon:              (document.getElementById('crm-f-telefon').value || '').trim(),
    jmbg:                 (document.getElementById('crm-f-jmbg').value || '').trim(),
    broj_pasosa:          (document.getElementById('crm-f-pasos').value || '').trim(),
    pib:                  (document.getElementById('crm-f-pib').value || '').trim(),
    adresa:               (document.getElementById('crm-f-adresa').value || '').trim(),
    napomena:             (document.getElementById('crm-f-napomena').value || '').trim(),
    pravni_osnov_obrade:  document.getElementById('crm-f-osnov').value || 'legitimni_interes',
  };
  if (!payload.ime) { alert('Ime je obavezno polje.'); return; }
  var url = editId ? '/klijenti/'+editId : '/klijenti';
  var method = editId ? 'PUT' : 'POST';
  try {
    var r = await fetch(url, {
      method: method,
      headers:{'Content-Type':'application/json','Authorization':'Bearer '+currentSession.access_token},
      body: JSON.stringify(payload)
    });
    if (!r.ok) { var err=await r.json(); alert('Greška: '+(err.detail||r.status)); return; }
    crmZatvoriFormu();
    if (editId && crmAktivniId === editId) crmOtvoriProfil(editId);
    else ucitajKlijente();
  } catch(e) { alert('Greška pri čuvanju.'); }
}

async function crmUredi(klijentId) {
  try {
    var r = await fetch('/klijenti/'+klijentId, {headers:{'Authorization':'Bearer '+currentSession.access_token}});
    var d = await r.json();
    var k = d.klijent;
    document.getElementById('crm-f-ime').value      = k.ime      || '';
    document.getElementById('crm-f-prezime').value  = k.prezime  || '';
    document.getElementById('crm-f-firma').value    = k.firma    || '';
    document.getElementById('crm-f-email').value    = k.email    || '';
    document.getElementById('crm-f-telefon').value  = k.telefon  || '';
    document.getElementById('crm-f-adresa').value   = k.adresa   || '';
    document.getElementById('crm-f-napomena').value = k.napomena || '';
    if (document.getElementById('crm-f-osnov')) document.getElementById('crm-f-osnov').value = k.pravni_osnov_obrade || 'legitimni_interes';
    crmSetTip(k.tip || 'fizicko_lice');
    crmOtvoriFormu(klijentId);
  } catch(e) { alert('Greška pri učitavanju klijenta.'); }
}

async function crmObrisi(klijentId) {
  if (!confirm('Soft-delete klijenta? (Samo partner može. Podaci ostaju u sistemu.)')) return;
  var r = await fetch('/klijenti/'+klijentId, {
    method:'DELETE',
    headers:{'Authorization':'Bearer '+currentSession.access_token}
  });
  if (r.status === 403) { alert('Samo partner može brisati klijente.'); return; }
  crmZatvoriProfil();
  ucitajKlijente();
}

function crmCheckKonfliktOtvori() {
  ['cf-ime','cf-prezime','cf-firma'].forEach(function(id){ var el=document.getElementById(id); if(el) el.value=''; });
  document.getElementById('cf-rezultat').innerHTML = '';
  document.getElementById('crm-conflict-overlay').classList.add('open');
}
function crmZatvoriKonflikt() { document.getElementById('crm-conflict-overlay').classList.remove('open'); }

// ── CSV Import ──────────────────────────────────────────────────────────────
var _csvFajl = null;

function crmCsvImportOtvori() {
  _csvFajl = null;
  var btn  = document.getElementById('crm-csv-btn');
  var res  = document.getElementById('crm-csv-result');
  var nm   = document.getElementById('crm-csv-filename');
  var inp  = document.getElementById('crm-csv-file');
  if (btn) { btn.disabled = true; btn.style.opacity = '0.5'; btn.style.cursor = 'not-allowed'; btn.textContent = 'Uvezi klijente'; }
  if (res) { res.style.display = 'none'; res.innerHTML = ''; }
  if (nm)  { nm.style.display = 'none'; nm.textContent = ''; }
  if (inp) inp.value = '';
  document.getElementById('crm-csv-overlay').classList.add('open');
}

function crmCsvImportZatvori() {
  document.getElementById('crm-csv-overlay').classList.remove('open');
}

function crmCsvFileSelected(input) {
  var f = input.files && input.files[0];
  if (!f) return;
  _csvFajl = f;
  var nm  = document.getElementById('crm-csv-filename');
  var btn = document.getElementById('crm-csv-btn');
  if (nm)  { nm.textContent = f.name + ' (' + (f.size/1024).toFixed(0) + ' KB)'; nm.style.display = ''; }
  if (btn) { btn.disabled = false; btn.style.opacity = '1'; btn.style.cursor = 'pointer'; }
}

async function crmCsvPosalji() {
  if (!_csvFajl || !currentSession) return;
  var btn = document.getElementById('crm-csv-btn');
  var res = document.getElementById('crm-csv-result');
  if (btn) { btn.disabled = true; btn.textContent = 'Uvozim...'; }
  if (res) { res.style.display = 'none'; res.innerHTML = ''; }
  try {
    var fd = new FormData();
    fd.append('fajl', _csvFajl);
    var r = await fetch(BASE_URL + '/klijenti/import-csv', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + currentSession.access_token },
      body: fd,
    });
    var d = await r.json();
    if (!r.ok) {
      res.innerHTML = '<span style="color:#f87171;">⚠ Greška: ' + _htmlEsc(d.detail || 'Nepoznata greška') + '</span>';
    } else {
      var greske = (d.greske || []).length;
      var html = '<span style="color:#4ade80;font-weight:600;">✓ Uvezeno: ' + d.kreiran + ' klijenata</span>';
      if (d.ukupno_pokusano) html += ' <span style="color:rgba(255,255,255,.4);">od ' + d.ukupno_pokusano + '</span>';
      if (greske > 0) {
        html += '<br><span style="color:#fbbf24;">⚠ ' + greske + ' grešaka:</span><ul style="margin:.3rem 0 0;padding-left:1.2rem;color:rgba(255,255,255,.5);font-size:.72rem;">';
        d.greske.forEach(function(g) { html += '<li>' + _htmlEsc(g) + '</li>'; });
        html += '</ul>';
      }
      res.innerHTML = html;
      if (d.kreiran > 0) { crm_load(); showToast('Uvezeno ' + d.kreiran + ' klijenata', 'ok'); }
    }
    if (res) res.style.display = '';
  } catch(e) {
    if (res) { res.style.display = ''; res.innerHTML = '<span style="color:#f87171;">Greška mreže: ' + _htmlEsc(e.message) + '</span>'; }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Uvezi klijente'; }
  }
}

async function crmPokreniKonflikt() {
  var ime = (document.getElementById('cf-ime').value||'').trim();
  if (!ime) { alert('Ime je obavezno.'); return; }
  var rezultat = document.getElementById('cf-rezultat');
  rezultat.innerHTML = 'Provjeram...';
  try {
    var r = await fetch('/klijenti/check-conflict', {
      method:'POST',
      headers:{'Content-Type':'application/json','Authorization':'Bearer '+currentSession.access_token},
      body: JSON.stringify({
        ime: ime,
        prezime: (document.getElementById('cf-prezime').value||'').trim(),
        firma:   (document.getElementById('cf-firma').value||'').trim(),
      })
    });
    var d = await r.json();
    if (!d.conflict_detected) {
      rezultat.innerHTML = '<div class="crm-conflict-ok">✅ Nije pronađen sukob interesa.</div>';
    } else {
      var detalji = (d.details||[]).map(function(c){ return '<div style="margin-top:6px;font-size:0.78rem;">⚠ '+_htmlEsc(c.detalji)+'</div>'; }).join('');
      rezultat.innerHTML = '<div class="crm-conflict-warn"><b>⚠ Pronađen potencijalni sukob!</b>'+detalji+'</div>';
    }
  } catch(e) { rezultat.innerHTML='<span style="color:rgba(255,80,80,0.7);">Greška pri provjeri.</span>'; }
}

/* ── F11: WEB3 / COMPLIANCE ──────────────────────────────── */
var WEB3_MODULI = {
  web3_pretraga: {
    naziv:       'ZDI/MiCA Pretraga',
    endpoint:    '/web3/pretraga',
    opis:        'Pretražuje bazu ZDI (Srbija, 146 članova) i MiCA (EU 2023/1114). Postavite pitanje o kripto-regulativi — npr. "Da li mi treba dozvola NBS za razmenu kriptovaluta?" ili "Šta mora sadržati whitepaper po ZDI?"',
    label:       'Vaše pitanje o ZDI ili MiCA regulativi',
    placeholder: 'Npr: Da li fizičko lice mora da prijavi prihode od prodaje Bitcoina? Koja je poreska stopa?',
    min:         10
  },
  compliance_check: {
    naziv:       'Compliance Check',
    endpoint:    '/web3/compliance',
    opis:        'Proverava da li opisana aktivnost ili poslovni model zahteva dozvolu NBS/KHoV (Srbija) ili CASP autorizaciju (EU MiCA). Dobijate konkretan odgovor: DA/NE/DELIMIČNO za svaki propis.',
    label:       'Opis aktivnosti ili poslovnog modela',
    placeholder: 'Npr: Planiram da pokrenem platformu koja korisnicima omogućava razmenu Bitcoina za evro. Imamo srpsko DOO, ciljamo i EU klijente.',
    min:         30
  },
  whitepaper_check: {
    naziv:       'Whitepaper Analiza',
    endpoint:    '/web3/whitepaper',
    opis:        'Analizira whitepaper ili opis ICO/token projekta — da li ispunjava zahteve ZDI čl. 12-19 (Srbija) i MiCA čl. 6 (EU). Dobijate listu šta postoji, šta nedostaje i konkretne preporuke.',
    label:       'Tekst whitepaper-a ili opis token projekta',
    placeholder: 'Unesite tekst whitepaper-a, opis projekta, ili ključne elemente koje planirate da uključite...',
    min:         100
  },
  mica_score: {
    naziv:       'MiCA Readiness Score',
    endpoint:    '/web3/mica-score',
    opis:        'Izračunava MiCA Readiness Score (0-100) za vaš kripto projekt. Ocenjuje 5 kategorija: whitepaper usklađenost, CASP zahtevi, AML/KYC, rezerve/backing i zabrana zloupotrebe tržišta. Dobijate skor i konkretne preporuke za poboljšanje.',
    label:       'Opis kripto projekta ili token inicijative',
    placeholder: 'Npr: Planiramo pokretanje stablecoin-a vezanog za euro. Imamo EU entitet, whitepaper je u pripremi, nismo još prijavili NBS. Ciljamo na maloprodajne klijente u Srbiji i EU...',
    min:         50
  },
  license_check: {
    naziv:       'ZDI License Check',
    endpoint:    '/web3/license-check',
    opis:        'Proverava da li vaša aktivnost zahteva dozvolu po Zakonu o digitalnoj imovini (ZDI). Klasifikuje imovinu (virtualna valuta/digitalni token), utvrđuje nadležni organ (NBS ili KHoV), procenjuje rizik i navodi potrebne mere.',
    label:       'Opis aktivnosti vezane za digitalnu imovinu',
    placeholder: 'Npr: Pravno lice iz Srbije želi da pruža usluge čuvanja Bitcoin-a za klijente, kao i razmenu kriptovaluta za fiat valute...',
    min:         20
  },
  aml_audit: {
    naziv:       'AML/KYC Auditor',
    endpoint:    '/web3/aml-audit',
    opis:        'Proverava usklađenost AML/KYC politike sa ZDI (čl. 81-97), ZSPNFT i FATF standardima. Ocenjuje 8 kategorija i daje skor usklađenosti (0-100) sa konkretnim preporukama.',
    label:       'Tekst AML/KYC politike ili opis internih procedura',
    placeholder: 'Unesite tekst vaše AML/KYC politike, opis internih procedura za sprečavanje pranja novca, ili ključne elemente koje imate implementirane...',
    min:         50
  },
  smart_contract: {
    naziv:       'Pametni Ugovor — Pravna Analiza',
    endpoint:    '/web3/analiziraj-ugovor',
    opis:        'Pravna analiza Solidity pametnih ugovora — isključivo iz pravne perspektive. Prevodimo mašinsku logiku u pravni jezik: poslovne funkcije, pravne indikatore, regulatornu relevantnost i rizike. Nije bezbednosni audit koda. Košta 5 kredita po analizi.',
    label:       'Solidity izvorni kod ugovora',
    placeholder: 'Nalepite Solidity kod ovde...',
    min:         20,
    maxChars:    50000,
    btnText:     'Analiziraj ugovor'
  }
};
var _web3AktivniModul = 'web3_pretraga';

function web3InitTab() {
  var m = WEB3_MODULI[_web3AktivniModul];
  var opisEl  = document.getElementById('web3-opis');
  var labelEl = document.getElementById('web3-input-label');
  var txtEl   = document.getElementById('web3-tekst');
  if (opisEl)  opisEl.textContent  = m.opis;
  if (labelEl) labelEl.textContent = m.label;
  if (txtEl)   txtEl.placeholder   = m.placeholder;
  document.querySelectorAll('.web3-moduli .strat-btn').forEach(function(b) {
    b.classList.toggle('active', b.dataset.modul === _web3AktivniModul);
  });
}

function web3IzaberiModul(modul, btn) {
  _web3AktivniModul = modul;
  document.querySelectorAll('.web3-moduli .strat-btn').forEach(function(b) { b.classList.remove('active'); });
  if (btn) btn.classList.add('active');
  var m = WEB3_MODULI[modul];
  var opisEl    = document.getElementById('web3-opis');
  var labelEl   = document.getElementById('web3-input-label');
  var txtEl     = document.getElementById('web3-tekst');
  var charsEl   = document.getElementById('web3-chars');
  var wrapEl    = document.getElementById('web3-rezultat-wrap');
  var submitBtn = document.getElementById('web3-submit-btn');
  if (opisEl)    opisEl.textContent    = m.opis;
  if (labelEl)   labelEl.textContent   = m.label;
  if (txtEl)     { txtEl.placeholder   = m.placeholder; txtEl.value = ''; }
  if (charsEl)   charsEl.textContent   = '0';
  if (wrapEl)    wrapEl.style.display  = 'none';
  if (submitBtn) submitBtn.textContent = m.btnText || 'Analiziraj';
}

document.addEventListener('DOMContentLoaded', function() {
  var txtEl = document.getElementById('web3-tekst');
  if (txtEl) txtEl.addEventListener('input', function() {
    var c = document.getElementById('web3-chars');
    if (c) c.textContent = this.value.length;
  });
});

// Portal init — runs early; if ?token= in URL, shows client portal view instead of app
document.addEventListener('DOMContentLoaded', function() {
  if (window.location.search.indexOf('token=') !== -1) {
    portal_init();
  }
});

async function web3Pokreni() {
  var txtEl  = document.getElementById('web3-tekst');
  var btn    = document.getElementById('web3-submit-btn');
  var wrapEl = document.getElementById('web3-rezultat-wrap');
  var naslov = document.getElementById('web3-rezultat-naslov');
  var bodyEl = document.getElementById('web3-rezultat-body');
  var tekst  = txtEl ? txtEl.value.trim() : '';
  var modul  = WEB3_MODULI[_web3AktivniModul];

  if (!currentUser) { openModal(); return; }
  if (!currentUserIsPro) {
    if (bodyEl) bodyEl.innerHTML = '<div class="strat-pro-gate">🔒 Web3 Compliance je dostupan samo PRO korisnicima.</div>';
    if (wrapEl) wrapEl.style.display = 'block';
    return;
  }
  if (tekst.length < modul.min) {
    if (bodyEl) bodyEl.innerHTML = '<div class="strat-error">Unesite najmanje ' + modul.min + ' karaktera.</div>';
    if (wrapEl) wrapEl.style.display = 'block';
    return;
  }

  var isSmartContract = (_web3AktivniModul === 'smart_contract');
  btn.disabled = true;
  btn.textContent = isSmartContract ? 'Vindex analizira ugovor...' : 'Analiziram...';
  if (naslov) naslov.textContent = modul.naziv;
  var loadingMsg = isSmartContract
    ? '⏳ Vindex analizira ugovor...'
    : '⏳ ' + modul.naziv + ' — analiza u toku (ZDI + MiCA)...';
  if (bodyEl) bodyEl.innerHTML = '<div class="strat-loading">' + loadingMsg + '</div>';
  if (wrapEl) wrapEl.style.display = 'block';

  try {
    var reqBody = isSmartContract
      ? JSON.stringify({solidity_source: tekst})
      : JSON.stringify({tekst: tekst});
    var res = await fetch(modul.endpoint, {
      method: 'POST',
      headers: {'Content-Type':'application/json', 'Authorization':'Bearer '+(currentSession ? currentSession.access_token : '')},
      body: reqBody
    });
    if (res.status === 403) {
      if (bodyEl) bodyEl.innerHTML = '<div class="strat-pro-gate">🔒 ' + modul.naziv + ' je dostupna samo PRO korisnicima.</div>';
      return;
    }
    if (res.status === 402) {
      var errData = {}; try { errData = await res.json(); } catch(e2) {}
      var errMsg = (errData.detail && errData.detail.message) ? errData.detail.message : 'Nemate dovoljno kredita za ovu analizu.';
      if (bodyEl) bodyEl.innerHTML = '<div class="strat-error">💳 ' + _htmlEsc(errMsg) + '</div>';
      return;
    }
    if (!res.ok) throw new Error('Server greška: ' + res.status);
    var data = await res.json();
    if (bodyEl) {
      if (data.modul === 'smart_contract') bodyEl.innerHTML = web3RenderSmartContract(data);
      else if (data.modul === 'mica_score') bodyEl.innerHTML = web3RenderScore(data.score_data, data.objasnjenje, 'mica');
      else if (data.modul === 'license_check') bodyEl.innerHTML = web3RenderLicense(data.license_data, data.objasnjenje);
      else if (data.modul === 'aml_audit') bodyEl.innerHTML = web3RenderAudit(data.audit_data, data.objasnjenje);
      else bodyEl.innerHTML = web3FormatirajRezultat(data.rezultat || '');
    }
  } catch(e) {
    if (bodyEl) bodyEl.innerHTML = '<div class="strat-error">Greška: ' + _htmlEsc(e.message) + '</div>';
  } finally {
    btn.disabled = false;
    btn.textContent = (WEB3_MODULI[_web3AktivniModul] && WEB3_MODULI[_web3AktivniModul].btnText) || 'Analiziraj';
  }
}

function web3FormatirajRezultat(tekst) {
  if (!tekst) return '<div class="strat-error">Nema rezultata.</div>';
  var esc = tekst.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  return esc
    .replace(/^(\d+\.\s+[A-ZŠĐČĆŽА-Я][A-ZŠĐČĆŽА-Я\s\/\(\)]{2,})$/gm, '<div class="strat-sekcija">$1</div>')
    .replace(/(✓[^\n]+)/g, '<span class="web3-ok">$1</span>')
    .replace(/(✗[^\n]+)/g, '<span class="web3-error-item">$1</span>')
    .replace(/(⚠️[^\n]+)/g, '<span class="web3-warning-item">$1</span>')
    .replace(/\n/g, '<br>');
}

function web3Kopiraj() {
  var bodyEl = document.getElementById('web3-rezultat-body');
  if (!bodyEl) return;
  navigator.clipboard.writeText(bodyEl.innerText).then(function() {
    var btn = document.querySelector('.web3-copy-btn');
    if (btn) { btn.textContent = '✓ Kopirano'; setTimeout(function() { btn.textContent = '📋 Kopiraj'; }, 2000); }
  });
}

/* ── Phase 5.1: Pravne oblasti ──────────────────────────────────────────── */
var _oblastTrenutna = 'krivicno';

var _OBLASTI_META = {
  krivicno: {
    naziv: 'Krivično pravo',
    opis: 'Specijalizovani asistent za krivično pravo (KZ + ZKP). Pitajte o krivičnim delima, kaznama, pritvoru, krivičnom postupku i pravnim sredstvima.',
    reference: ['KZ čl. 1-368', 'ZKP postupak', 'Zaštitne mere', 'Zastarelost KZ'],
    placeholder: 'npr. Koja je kazna za krađu? Koji su uslovi za uslovnu osudu? Šta je pritvoreničko pravo?'
  },
  privredno: {
    naziv: 'Privredno pravo',
    opis: 'Specijalizovani asistent za privredno pravo (ZPD + ZOO + Zakon o stečaju). Pitajte o osnivanju društava, organima upravljanja, stečaju i privrednim ugovorima.',
    reference: ['ZPD čl. 1-750+', 'ZOO privredni', 'Zakon o stečaju', 'APR registracija'],
    placeholder: 'npr. Kako se osniva DOO? Ko odgovara za dugove DOO? Šta je reorganizacija u stečaju?'
  },
  radno: {
    naziv: 'Radno pravo',
    opis: 'Specijalizovani asistent za radno pravo (ZR + ZBZO). Pitajte o otkazima, pravima zaposlenih, radnim sporovima, otpremnini i rokovima.',
    reference: ['ZR čl. 1-287', 'ZBZO zaštita', 'Rok za tužbu 60d', 'Zastarelost 3g'],
    placeholder: 'npr. Koji je rok za pobijanje otkaza? Šta je obavezna procedura kod otkaza? Kolika je otpremnina?'
  }
};

function oblastiIzaberiOblast(oblast, btn) {
  _oblastTrenutna = oblast;
  document.querySelectorAll('[data-oblast]').forEach(function(b) { b.classList.remove('active'); });
  if (btn) btn.classList.add('active');
  var meta = _OBLASTI_META[oblast];
  var opisEl = document.getElementById('ob-opis');
  if (opisEl) opisEl.innerHTML = '<span style="color:rgba(255,255,255,0.65);">' + _htmlEsc(meta.opis) + '</span>';
  var refEl = document.getElementById('ob-reference');
  if (refEl) refEl.innerHTML = '<span>📚 Baza znanja:</span>' + meta.reference.map(function(r){ return '<span class="web3-ref-badge">' + _htmlEsc(r) + '</span>'; }).join('');
  var tEl = document.getElementById('ob-tekst');
  if (tEl) tEl.placeholder = meta.placeholder;
  var wEl = document.getElementById('ob-rezultat-wrap');
  if (wEl) wEl.style.display = 'none';
}

async function oblastiPokreni() {
  var pitanje = (document.getElementById('ob-tekst').value || '').trim();
  if (!pitanje || pitanje.length < 5) {
    document.getElementById('ob-rezultat-body').innerHTML = '<div class="strat-error">Unesite pitanje (min. 5 karaktera).</div>';
    document.getElementById('ob-rezultat-wrap').style.display = 'block';
    return;
  }
  if (!currentUser) { openModal(); return; }
  var btn    = document.getElementById('ob-submit-btn');
  var wrapEl = document.getElementById('ob-rezultat-wrap');
  var bodyEl = document.getElementById('ob-rezultat-body');
  var naslov = document.getElementById('ob-rezultat-naslov');
  btn.disabled = true; btn.textContent = '⏳ Analiziram...';
  if (naslov) naslov.textContent = _OBLASTI_META[_oblastTrenutna].naziv + ' — AI odgovor';
  if (bodyEl) bodyEl.innerHTML = '<div class="strat-loading">⏳ ' + _OBLASTI_META[_oblastTrenutna].naziv + ' — analiza u toku...</div>';
  if (wrapEl) wrapEl.style.display = 'block';
  try {
    var res = await fetch(BASE_URL + '/api/oblasti/' + _oblastTrenutna, {
      method: 'POST',
      headers: {'Content-Type':'application/json','Authorization':'Bearer '+(currentSession ? currentSession.access_token : '')},
      body: JSON.stringify({pitanje: pitanje})
    });
    if (res.status === 402) {
      var ed = {}; try { ed = await res.json(); } catch(e2) {}
      if (bodyEl) bodyEl.innerHTML = '<div class="strat-error">💳 ' + _htmlEsc((ed.detail && ed.detail.message) || 'Nemate dovoljno kredita.') + '</div>';
      return;
    }
    if (!res.ok) throw new Error('Server greška: ' + res.status);
    var data = await res.json();
    if (bodyEl) bodyEl.innerHTML = web3FormatirajRezultat(data.data || '');
    if (wrapEl) wrapEl.scrollIntoView({behavior:'smooth', block:'start'});
  } catch(e) {
    if (bodyEl) bodyEl.innerHTML = '<div class="strat-error">Greška: ' + _htmlEsc(e.message) + '</div>';
  } finally {
    btn.disabled = false; btn.textContent = 'Pitaj AI';
  }
}

function oblastiKopiraj() {
  var bodyEl = document.getElementById('ob-rezultat-body');
  if (!bodyEl) return;
  navigator.clipboard.writeText(bodyEl.innerText).then(function() {
    var btns = document.querySelectorAll('#ob-rezultat-wrap .web3-copy-btn');
    btns.forEach(function(b) { b.textContent = '✓ Kopirano'; setTimeout(function() { b.textContent = '📋 Kopiraj'; }, 2000); });
  });
}

function oblastiInit() {
  oblastiIzaberiOblast('krivicno', document.querySelector('[data-oblast="krivicno"]'));
}

function web3ScoreBojaKlasa(score, max) {
  var pct = max > 0 ? (score / max) * 100 : score;
  if (pct >= 70) return 'ok';
  if (pct >= 40) return 'warning';
  return 'danger';
}

function web3StatusIkona(status) {
  if (status === 'ok') return '✅';
  if (status === 'warning') return '⚠️';
  return '❌';
}

var _w3KatNazivi = {
  whitepaper_uskladenost: 'Whitepaper usklađenost',
  casp_zahtevi: 'CASP zahtevi',
  aml_kyc: 'AML/KYC',
  rezerve_i_backing: 'Rezerve i backing',
  market_abuse: 'Zabrana zloupotrebe tržišta',
  kyc_procedure: 'KYC procedure',
  pep_screening: 'PEP screening',
  transakcijski_monitoring: 'Transakcijski monitoring',
  travel_rule: 'Travel rule',
  izvestavanje_sumljivih: 'Izveštavanje sumnjivih',
  cuvanje_dokumentacije: 'Čuvanje dokumentacije',
  obuka_zaposlenih: 'Obuka zaposlenih',
  interna_kontrola: 'Interna kontrola'
};

function _web3RenderKategorije(kategorije) {
  var html = '<div class="w3-kat-lista">';
  Object.keys(kategorije || {}).forEach(function(k) {
    var kat = kategorije[k];
    var skor = kat.skor || 0;
    var max = kat.max || 20;
    var status = kat.status || 'ok';
    var klasa = web3ScoreBojaKlasa(skor, max);
    var pct = Math.round((skor / max) * 100);
    html += '<div class="w3-kat-item">';
    html += '<div class="w3-kat-row"><span class="w3-kat-naziv">' + web3StatusIkona(status) + ' ' + (_w3KatNazivi[k] || k) + '</span>';
    html += '<span class="w3-kat-skor ' + klasa + '">' + skor + '/' + max + '</span></div>';
    html += '<div class="w3-progress"><div class="w3-progress-bar ' + klasa + '" style="width:' + pct + '%"></div></div>';
    if (kat.komentar) html += '<div class="w3-kat-komentar">' + _htmlEsc(kat.komentar) + '</div>';
    html += '</div>';
  });
  html += '</div>';
  return html;
}

function _web3RenderListe(data) {
  var html = '';
  var nedostaci = data.kriticni_nedostaci || [];
  if (nedostaci.length) {
    html += '<div class="w3-lista-sekcija"><div class="w3-lista-naslov">Kritični nedostaci</div>';
    nedostaci.forEach(function(n) { html += '<div class="w3-lista-item danger">' + _htmlEsc(n) + '</div>'; });
    html += '</div>';
  }
  var preporuke = data.preporuke || [];
  if (preporuke.length) {
    html += '<div class="w3-lista-sekcija"><div class="w3-lista-naslov">Preporuke</div>';
    preporuke.forEach(function(p) { html += '<div class="w3-lista-item ok">' + _htmlEsc(p) + '</div>'; });
    html += '</div>';
  }
  return html;
}

function web3RenderScore(scoreData, objasnjenje, tip) {
  if (!scoreData || typeof scoreData !== 'object') {
    return '<div class="strat-error">Greška pri parsiranju scoring rezultata.</div>';
  }
  var ukupni = scoreData.ukupni_skor || 0;
  var nivo = scoreData.skor_nivo || '';
  var kruKlasa = web3ScoreBojaKlasa(ukupni, 100);
  var html = '<div class="w3-score-wrap">';
  html += '<div class="w3-score-krug ' + kruKlasa + '"><span class="w3-score-broj">' + ukupni + '</span><span class="w3-score-label">/100</span></div>';
  html += '<div class="w3-score-info"><div class="w3-score-nivo ' + kruKlasa + '">' + _htmlEsc(nivo) + '</div>';
  html += '<div class="w3-score-opis">' + _htmlEsc(objasnjenje || '') + '</div>';
  html += '</div></div>';
  html += _web3RenderKategorije(scoreData.kategorije);
  html += _web3RenderListe(scoreData);
  return html;
}

function web3RenderLicense(licenseData, objasnjenje) {
  if (!licenseData || typeof licenseData !== 'object') {
    return '<div class="strat-error">Greška pri parsiranju license rezultata.</div>';
  }
  var organ = licenseData.nadlezni_organ || '';
  var dozvola = licenseData.dozvola_potrebna;
  var rizik = (licenseData.rizik_nivo || '').toUpperCase();
  var klasifikacija = licenseData.klasifikacija_imovine || '';

  var html = '<div class="w3-license-wrap">';
  if (organ && organ !== 'nije_primenjivo') {
    html += '<span class="w3-license-badge organ">🏛️ ' + _htmlEsc(organ) + '</span>';
  }
  html += '<span class="w3-license-badge ' + (dozvola ? 'dozvola-da' : 'dozvola-ne') + '">';
  html += (dozvola ? '⚠️ Dozvola POTREBNA' : '✅ Dozvola NIJE potrebna') + '</span>';
  if (rizik) {
    var rizikKlasa = rizik === 'VISOK' ? 'rizik-visok' : rizik === 'SREDNJI' ? 'rizik-srednji' : 'rizik-nizak';
    html += '<span class="w3-license-badge ' + rizikKlasa + '">Rizik: ' + _htmlEsc(rizik) + '</span>';
  }
  html += '</div>';
  if (klasifikacija) {
    html += '<div class="w3-license-tip">Klasifikacija imovine: <strong>' + _htmlEsc(klasifikacija) + '</strong></div>';
  }
  if (licenseData.tip_dozvole) {
    html += '<div class="w3-license-tip">Tip dozvole: ' + _htmlEsc(licenseData.tip_dozvole) + '</div>';
  }
  if (objasnjenje) {
    html += '<div class="w3-score-opis" style="margin-bottom:10px">' + _htmlEsc(objasnjenje) + '</div>';
  }
  var pravniOsnov = licenseData.pravni_osnov || [];
  if (pravniOsnov.length) {
    html += '<div class="w3-lista-sekcija"><div class="w3-lista-naslov">Pravni osnov</div>';
    pravniOsnov.forEach(function(p) { html += '<div class="w3-lista-item">' + _htmlEsc(p) + '</div>'; });
    html += '</div>';
  }
  var obaveze = licenseData.obavezne_mere || [];
  if (obaveze.length) {
    html += '<div class="w3-lista-sekcija"><div class="w3-lista-naslov">Obavezne mere</div>';
    obaveze.forEach(function(m) { html += '<div class="w3-lista-item ok">' + _htmlEsc(m) + '</div>'; });
    html += '</div>';
  }
  if (licenseData['kazne_pri_kršenju']) {
    html += '<div class="w3-lista-sekcija"><div class="w3-lista-naslov">Kazne pri kršenju</div>';
    html += '<div class="w3-lista-item danger">' + _htmlEsc(licenseData['kazne_pri_kršenju']) + '</div>';
    html += '</div>';
  }
  return html;
}

function web3RenderAudit(auditData, objasnjenje) {
  if (!auditData || typeof auditData !== 'object') {
    return '<div class="strat-error">Greška pri parsiranju audit rezultata.</div>';
  }
  var ukupno = auditData.ukupna_uskladenost || 0;
  var nivo = auditData.uskladenost_nivo || '';
  var kruKlasa = web3ScoreBojaKlasa(ukupno, 100);
  var html = '<div class="w3-score-wrap">';
  html += '<div class="w3-score-krug ' + kruKlasa + '"><span class="w3-score-broj">' + ukupno + '</span><span class="w3-score-label">/100</span></div>';
  html += '<div class="w3-score-info"><div class="w3-score-nivo ' + kruKlasa + '">AML/KYC: ' + _htmlEsc(nivo) + '</div>';
  html += '<div class="w3-score-opis">' + _htmlEsc(objasnjenje || '') + '</div>';
  html += '</div></div>';
  html += _web3RenderKategorije(auditData.kategorije);
  html += _web3RenderListe(auditData);
  return html;
}

/* ── F12: Smart Contract Legal Analyzer render (v2) ─────────── */
function web3RenderSmartContract(data) {
  var a = data.analysis_result;
  if (!a || typeof a !== 'object') {
    return '<div class="strat-error">Greška pri parsiranju analize ugovora.</div>';
  }
  var html = '';

  // Header: naziv ugovora + confidence badge
  var ct = ((a.confidence_tier || data.confidence_tier || 'LOW') + '').toUpperCase();
  var ctLabel = ct === 'HIGH' ? 'Visoko poverenje' : ct === 'MEDIUM' ? 'Srednje poverenje' : 'Nisko poverenje — rezultati su indikativni';
  var ctClass = ct === 'HIGH' ? 'sc-conf-high' : ct === 'MEDIUM' ? 'sc-conf-medium' : 'sc-conf-low';
  html += '<div class="sc-header-row">';
  html += '<div class="sc-contract-title">📜 ' + _htmlEsc(data.contract_name || 'Pametni ugovor');
  if (data.solidity_version && data.solidity_version !== 'nepoznata') {
    html += '<span class="sc-version">Solidity ' + _htmlEsc(data.solidity_version) + '</span>';
  }
  html += '</div>';
  html += '<span class="sc-confidence-badge ' + ctClass + '">' + ctLabel + '</span>';
  html += '</div>';

  if (a.proxy_upozorenje) {
    html += '<div class="sc-proxy-warning">⚠️ Detektovan proxy pattern — ovaj ugovor može imati skrivenu implementacionu logiku koja nije vidljiva u dostavljenom kodu.</div>';
  }

  // [1] Pravni sažetak (Executive Summary)
  var sazetak = Array.isArray(a.pravni_sazetak) ? a.pravni_sazetak : [];
  if (sazetak.length) {
    html += '<div class="sc-section sc-sazetak-wrap">';
    html += '<div class="sc-section-head">⚡ Pravni sažetak — 30 sekundi</div>';
    html += '<div class="sc-section-body">';
    sazetak.forEach(function(s) { html += '<div class="sc-sazetak-item">• ' + _htmlEsc(s) + '</div>'; });
    html += '</div></div>';
  }

  // [2] Poslovna funkcija
  var pf = a.poslovna_funkcija || {};
  if (pf.opis || pf.tip_ugovora) {
    html += '<div class="sc-poslovna-card">';
    html += '<div class="sc-section-header-static">Poslovna funkcija';
    if (pf.tip_ugovora) html += ' <span class="sc-tip-badge">' + _htmlEsc(pf.tip_ugovora) + '</span>';
    html += '</div>';
    if (pf.opis) html += '<div class="sc-poslovna-body">' + _htmlEsc(pf.opis) + '</div>';
    html += '</div>';
  }

  // [3] Pravni rizici — visoko istaknuti, odmah posle sažetka
  var rizici = Array.isArray(a.pravni_rizici) ? a.pravni_rizici : [];
  if (rizici.length) {
    html += '<div class="sc-section">';
    html += '<div class="sc-section-head">⚠️ Pravni rizici (' + rizici.length + ')</div>';
    html += '<div class="sc-section-body">';
    rizici.forEach(function(r) {
      var oz = ((r.ozbiljnost || '') + '').toUpperCase();
      var cls = (oz === 'KRITIČAN' || oz === 'KRITICAN') ? 'sc-rizik-kritican' : oz === 'VISOK' ? 'sc-rizik-visok' : oz === 'SREDNJI' ? 'sc-rizik-srednji' : 'sc-rizik-nizak';
      var ikona = (oz === 'KRITIČAN' || oz === 'KRITICAN') ? '🚨' : oz === 'VISOK' ? '⚠️' : oz === 'SREDNJI' ? '🔶' : 'ℹ️';
      html += '<div class="sc-rizik-row ' + cls + '">';
      html += '<div class="sc-rizik-head">' + ikona + ' <span class="sc-rizik-oz">' + _htmlEsc(r.ozbiljnost || '') + '</span> — ' + _htmlEsc(r.rizik || '') + '</div>';
      if (r.obrazlozenje) html += '<div class="sc-rizik-obr">' + _htmlEsc(r.obrazlozenje) + '</div>';
      html += '</div>';
    });
    html += '</div></div>';
  }

  // [4] Administrativna ovlašćenja
  var adm = a.administrativna_ovlascenja || {};
  var admFunkcije = Array.isArray(adm.privilegovane_funkcije) ? adm.privilegovane_funkcije : [];
  var admNivo = adm.nivo || '';
  if (admNivo || admFunkcije.length) {
    var admNivoClass = admNivo === 'VISOKA' ? 'sc-centralizacija-visoka' : admNivo === 'SREDNJA' ? 'sc-centralizacija-srednja' : admNivo === 'NEMA' ? 'sc-centralizacija-niska' : 'sc-centralizacija-niska';
    html += '<div class="sc-section">';
    html += '<div class="sc-section-head sc-collapsible" onclick="scToggle(this)">🔑 Administrativna ovlašćenja <span class="sc-rel-badge ' + admNivoClass + '" style="margin-left:8px">' + _htmlEsc(admNivo) + '</span><span class="sc-caret">▾</span></div>';
    html += '<div class="sc-section-body">';
    var admUloge = Array.isArray(adm.privilegovane_uloge) ? adm.privilegovane_uloge : [];
    if (admUloge.length) {
      html += '<div class="sc-reg-clanovi" style="margin-bottom:10px">';
      admUloge.forEach(function(u) { html += '<span class="sc-clan-tag">' + _htmlEsc(u) + '</span>'; });
      html += '</div>';
    }
    if (admFunkcije.length) {
      admFunkcije.forEach(function(f) {
        html += '<div class="sc-adm-funkcija">';
        html += '<div class="sc-adm-naziv"><code>' + _htmlEsc(f.naziv || '') + '</code>';
        if (f.ovlasceni_akter) html += ' <span class="sc-adm-akter">(' + _htmlEsc(f.ovlasceni_akter) + ')</span>';
        html += '</div>';
        if (f.poslovna_posledica) html += '<div class="sc-adm-poslovna"><strong>Poslovna posledica:</strong> ' + _htmlEsc(f.poslovna_posledica) + '</div>';
        if (f.pravna_posledica) html += '<div class="sc-adm-pravna"><strong>Pravna posledica:</strong> ' + _htmlEsc(f.pravna_posledica) + '</div>';
        html += '</div>';
      });
    } else if (admNivo === 'NEMA') {
      html += '<div class="sc-ind-obr">Nisu identifikovana posebna administrativna ovlašćenja.</div>';
    }
    html += '</div></div>';
  }

  // [5] Centralizacija
  var cent = a.centralizacija || {};
  if (cent.nivo) {
    var centClass = cent.nivo === 'VISOKA' ? 'sc-centralizacija-visoka' : cent.nivo === 'SREDNJA' ? 'sc-centralizacija-srednja' : 'sc-centralizacija-niska';
    html += '<div class="sc-section">';
    html += '<div class="sc-section-head sc-collapsible" onclick="scToggle(this)">🏛️ Analiza centralizacije <span class="sc-rel-badge ' + centClass + '" style="margin-left:8px">' + _htmlEsc(cent.nivo) + '</span><span class="sc-caret">▾</span></div>';
    html += '<div class="sc-section-body">';
    if (cent.obrazlozenje) html += '<div class="sc-ind-obr" style="margin-bottom:8px">' + _htmlEsc(cent.obrazlozenje) + '</div>';
    var centFaktori = Array.isArray(cent.faktori) ? cent.faktori : [];
    if (centFaktori.length) {
      centFaktori.forEach(function(f) { html += '<div class="sc-sazetak-item">• ' + _htmlEsc(f) + '</div>'; });
    }
    html += '</div></div>';
  }

  // [6] Ključne radnje
  var radnje = Array.isArray(a.kljucne_radnje) ? a.kljucne_radnje : [];
  if (radnje.length) {
    html += '<div class="sc-section">';
    html += '<div class="sc-section-head sc-collapsible" onclick="scToggle(this)">📋 Ključne radnje <span class="sc-caret">▾</span></div>';
    html += '<div class="sc-section-body">';
    radnje.forEach(function(r) {
      html += '<div class="sc-adm-funkcija">';
      html += '<div class="sc-adm-naziv"><strong>' + _htmlEsc(r.radnja || '') + '</strong>';
      if (r.pravni_karakter) html += ' <span class="sc-adm-akter">— ' + _htmlEsc(r.pravni_karakter) + '</span>';
      html += '</div>';
      var opis = r.poslovna_funkcija || r.opis || '';
      if (opis) html += '<div class="sc-ind-obr">' + _htmlEsc(opis) + '</div>';
      var dogadjaji = Array.isArray(r.moguci_pravni_dogadjaji) ? r.moguci_pravni_dogadjaji : [];
      if (dogadjaji.length) {
        html += '<div class="sc-adm-pravna"><em>Mogući pravni događaji:</em> ' + dogadjaji.map(function(d){ return _htmlEsc(d); }).join(' • ') + '</div>';
      }
      html += '</div>';
    });
    html += '</div></div>';
  }

  // [7] Pravni indikatori (sa faktorima ZA/PROTIV)
  var pi = a.pravni_indikatori || {};
  var indNazivi = {
    pruzanje_finansijske_usluge: 'Pružanje finansijske usluge',
    upravljanje_tudom_imovinom:  'Upravljanje tuđom imovinom',
    investiciona_shema:          'Investiciona shema',
    anonimnost_ucesnika:         'Anonimnost učesnika'
  };
  var indKeys = Object.keys(indNazivi);
  if (indKeys.some(function(k){ return !!(pi && pi[k]); })) {
    html += '<div class="sc-section">';
    html += '<div class="sc-section-head sc-collapsible" onclick="scToggle(this)">⚖️ Pravni indikatori <span class="sc-caret">▾</span></div>';
    html += '<div class="sc-section-body sc-indikatori-grid">';
    indKeys.forEach(function(k) {
      var ind = (pi && pi[k]) || {};
      var val = ((ind.indikator || 'NEDOVOLJNO PODATAKA') + '').toUpperCase();
      var valClass = val === 'DA' ? 'sc-ind-da' : (val === 'MOGUĆE' || val === 'MOGUCE') ? 'sc-ind-moguce' : val === 'NE' ? 'sc-ind-ne' : 'sc-ind-nd';
      var valIkona = val === 'DA' ? '🔴' : (val === 'MOGUĆE' || val === 'MOGUCE') ? '🟡' : val === 'NE' ? '🟢' : '⚪';
      html += '<div class="sc-indikator-card">';
      html += '<div class="sc-ind-naziv">' + _htmlEsc(indNazivi[k]) + '</div>';
      html += '<div class="sc-ind-value ' + valClass + '">' + valIkona + ' ' + _htmlEsc(ind.indikator || 'NEDOVOLJNO PODATAKA') + '</div>';
      if (ind.obrazlozenje) html += '<div class="sc-ind-obr">' + _htmlEsc(ind.obrazlozenje) + '</div>';
      var fZa = Array.isArray(ind.faktori_za) ? ind.faktori_za : [];
      var fPro = Array.isArray(ind.faktori_protiv) ? ind.faktori_protiv : [];
      if (fZa.length) html += '<div class="sc-faktori sc-faktori-za"><strong>Za:</strong> ' + fZa.map(function(f){ return _htmlEsc(f); }).join('; ') + '</div>';
      if (fPro.length) html += '<div class="sc-faktori sc-faktori-protiv"><strong>Protiv:</strong> ' + fPro.map(function(f){ return _htmlEsc(f); }).join('; ') + '</div>';
      html += '</div>';
    });
    html += '</div></div>';
  }

  // [8] AML/KYC blok
  var amlKyc = a.aml_kyc || {};
  if (amlKyc.nivo_rizika || amlKyc.obrazlozenje) {
    var amlClass = amlKyc.nivo_rizika === 'VISOK' ? 'sc-centralizacija-visoka' : amlKyc.nivo_rizika === 'SREDNJI' ? 'sc-centralizacija-srednja' : 'sc-centralizacija-niska';
    html += '<div class="sc-section">';
    html += '<div class="sc-section-head sc-collapsible" onclick="scToggle(this)">🛡️ AML/KYC <span class="sc-rel-badge ' + amlClass + '" style="margin-left:8px">' + _htmlEsc(amlKyc.nivo_rizika || '') + '</span><span class="sc-caret">▾</span></div>';
    html += '<div class="sc-section-body">';
    if (amlKyc.obrazlozenje) html += '<div class="sc-ind-obr" style="margin-bottom:8px">' + _htmlEsc(amlKyc.obrazlozenje) + '</div>';
    var amlKar = Array.isArray(amlKyc.karakteristike) ? amlKyc.karakteristike : [];
    if (amlKar.length) {
      amlKar.forEach(function(k) { html += '<div class="sc-sazetak-item">• ' + _htmlEsc(k) + '</div>'; });
    }
    if (amlKyc.napomena) html += '<div class="sc-disclaimer" style="margin-top:8px;font-size:0.78rem">' + _htmlEsc(amlKyc.napomena) + '</div>';
    html += '</div></div>';
  }

  // [9] Klasifikacija tokena
  var tokeni = Array.isArray(a.klasifikacija_tokena) ? a.klasifikacija_tokena : [];
  if (tokeni.length) {
    html += '<div class="sc-section">';
    html += '<div class="sc-section-head sc-collapsible" onclick="scToggle(this)">🪙 Klasifikacija tokena <span class="sc-caret">▾</span></div>';
    html += '<div class="sc-section-body">';
    tokeni.forEach(function(t) {
      var tVal = ((t.status || 'NEDOVOLJNO PODATAKA') + '').toUpperCase();
      var tClass = tVal === 'DA' ? 'sc-ind-da' : tVal === 'MOGUĆE' ? 'sc-ind-moguce' : tVal === 'NE' ? 'sc-ind-ne' : 'sc-ind-nd';
      html += '<div class="sc-adm-funkcija">';
      html += '<div class="sc-adm-naziv"><strong>' + _htmlEsc(t.kategorija || '') + '</strong> <span class="sc-ind-value ' + tClass + '" style="font-size:0.78rem;padding:1px 6px">' + _htmlEsc(t.status || '') + '</span></div>';
      var tZa = Array.isArray(t.faktori_za) ? t.faktori_za : [];
      var tPro = Array.isArray(t.faktori_protiv) ? t.faktori_protiv : [];
      if (tZa.length) html += '<div class="sc-faktori sc-faktori-za"><strong>Za:</strong> ' + tZa.map(function(f){ return _htmlEsc(f); }).join('; ') + '</div>';
      if (tPro.length) html += '<div class="sc-faktori sc-faktori-protiv"><strong>Protiv:</strong> ' + tPro.map(function(f){ return _htmlEsc(f); }).join('; ') + '</div>';
      html += '</div>';
    });
    html += '</div></div>';
  }

  // [10] Regulatorna relevantnost — objektni clanovi (v2)
  var regs = Array.isArray(a.regulatorna_relevantnost) ? a.regulatorna_relevantnost : [];
  if (regs.length) {
    html += '<div class="sc-section">';
    html += '<div class="sc-section-head sc-collapsible" onclick="scToggle(this)">📚 Regulatorna relevantnost <span class="sc-caret">▾</span></div>';
    html += '<div class="sc-section-body">';
    regs.forEach(function(reg) {
      var nr = ((reg.nivo_relevantnosti || '') + '').toUpperCase();
      var nrClass = nr === 'VISOK' ? 'sc-rel-visok' : nr === 'SREDNJI' ? 'sc-rel-srednji' : 'sc-rel-moguc';
      html += '<div class="sc-regulativa-card">';
      html += '<div class="sc-reg-head"><strong>' + _htmlEsc(reg.propis || '') + '</strong><span class="sc-rel-badge ' + nrClass + '">' + _htmlEsc(reg.nivo_relevantnosti || '') + '</span></div>';
      var cl = Array.isArray(reg.relevantni_clanovi) ? reg.relevantni_clanovi : [];
      if (cl.length) {
        html += '<div class="sc-reg-clanovi">';
        cl.forEach(function(c) {
          if (c && typeof c === 'object') {
            // v2 schema: {clan, razlog_aktivacije, relevantna_funkcija}
            html += '<div class="sc-clan-obj">';
            html += '<span class="sc-clan-tag">' + _htmlEsc(c.clan || '') + '</span>';
            if (c.relevantna_funkcija) html += ' <code class="sc-clan-fn">' + _htmlEsc(c.relevantna_funkcija) + '</code>';
            if (c.razlog_aktivacije) html += '<div class="sc-clan-razlog">' + _htmlEsc(c.razlog_aktivacije) + '</div>';
            html += '</div>';
          } else {
            // v1 fallback: plain string
            html += '<span class="sc-clan-tag">' + _htmlEsc(c || '') + '</span>';
          }
        });
        html += '</div>';
      }
      if (reg.obrazlozenje) html += '<div class="sc-reg-obr">' + _htmlEsc(reg.obrazlozenje) + '</div>';
      html += '</div>';
    });
    html += '</div></div>';
  }

  // [11] Off-chain zavisnosti (default collapsed)
  var offchain = Array.isArray(a.offchain_zavisnosti) ? a.offchain_zavisnosti : [];
  if (offchain.length) {
    html += '<div class="sc-section">';
    html += '<div class="sc-section-head sc-collapsible" onclick="scToggle(this)">🔗 Off-chain zavisnosti (' + offchain.length + ') <span class="sc-caret">▸</span></div>';
    html += '<div class="sc-section-body" style="display:none">';
    offchain.forEach(function(oc) {
      html += '<div class="sc-offchain-item"><span class="sc-offchain-naziv">' + _htmlEsc(oc.zavisnost || '') + '</span>';
      if (oc.napomena) html += '<span class="sc-offchain-napomena"> — ' + _htmlEsc(oc.napomena) + '</span>';
      html += '</div>';
    });
    html += '</div></div>';
  }

  if (Array.isArray(a.limitacije_analize) && a.limitacije_analize.length) {
    html += '<div class="sc-section">';
    html += '<div class="sc-section-head sc-collapsible" onclick="scToggle(this)">ℹ️ Limitacije analize <span class="sc-caret">▸</span></div>';
    html += '<div class="sc-section-body" style="display:none">';
    a.limitacije_analize.forEach(function(l) { html += '<div class="sc-sazetak-item">• ' + _htmlEsc(l) + '</div>'; });
    html += '</div></div>';
  }

  html += '<div class="sc-disclaimer">Ova analiza predstavlja automatski generisane pravne indikatore i ne predstavlja pravno mišljenje niti pravni savet. Rezultati su zasnovani isključivo na dostavljenom izvornom kodu i ne uzimaju u obzir poslovni kontekst, stvarne transakcije, identitet strana, niti sudsku ili regulatornu praksu. Pre donošenja bilo kakve pravne ili poslovne odluke, konsultujte ovlašćenog pravnika.</div>';

  return html;
}

function scToggle(headerEl) {
  var body = headerEl.nextElementSibling;
  var caret = headerEl.querySelector('.sc-caret');
  if (!body) return;
  var isHidden = body.style.display === 'none';
  body.style.display = isHidden ? '' : 'none';
  if (caret) caret.textContent = isHidden ? '▾' : '▸';
}

/* PODNESAK HELPERS */
var _PODNESAK_HINTS = {
  tuzba_naknada_stete:    '⚖ Navedite: tužioca i tuženog (ime, adresa), opis štetnog dogadjaja, datum, vrstu i visinu štete, dostupne dokaze.',
  tuzba_radni_spor:       '💼 Navedite: zaposlenog (ime, adresa), poslodavca (naziv, sedište), razlog spora (nezakonit otkaz / neisplaćena zarada / mobbing), datum i zahtevani iznos.',
  tuzba_razvod:           '👪 Navedite: supružnike (ime, adresa), datum i mesto zaključenja braka, zajedničku decu (ime, godište), razloge za razvod, zahteve u pogledu dece i imovine.',
  zalba_parnicna:         '⚠ Navedite: naziv suda, broj predmeta, datum presude, razloge za žalbu.',
  zalba_na_presudu:       '⚠ Navedite: naziv suda, broj predmeta, datum presude, razloge za žalbu (pogrešna primena prava / pogrešno činjenično stanje / bitna povreda ZPP).',
  zalba_na_resenje:       '📋 Navedite: naziv organa koji je doneo rešenje, broj rešenja, datum dostave, razloge za žalbu, broj drugostepenog organa.',
  prigovor_platni_nalog:  '🔔 Navedite: naziv suda, broj platnog naloga (Pl. br.), datum dostave, dužnika, poverioca, iznos i razloge prigovora.',
  predlog_privremena_mera:'⚡ Navedite: sud, predlagača, protivnika obezbeđenja, potraživanje (iznos/opis), predloženu meru (zabrana otuđenja, zaplena), razloge hitnosti.',
  predlog_izvrsenje:      '⚡ Navedite: vrstu izvršne isprave (presuda/rešenje), broj i datum isprave, izvršenika (ime, adresa), iznos duga i željeno sredstvo izvršenja.',
  krivicna_prijava:       '🚨 Navedite: podnosioca (ime, adresa), okrivljenog (ime, adresa), naziv krivičnog dela (npr. prevara čl. 208 KZ), datum i opis dogadjaja, dostupne dokaze.',
  opomena_duznik:         '📩 Navedite: poverioca (ime/naziv), dužnika (ime/naziv), iznos duga, osnov (faktura, ugovor), rok za plaćanje.',
  zahtev_poslodavcu:      '📝 Navedite: zaposlenog (ime), poslodavca (naziv), sadržaj zahteva (isplata zarade, godišnji odmor...), zakonski osnov, rok za odgovor.',
  obaveštenje_o_otkazu:   '📨 Navedite: stranu koja otkazuje, drugu stranu, datum otkaza, otkazni rok, razlog otkaza.',
  ugovor_kupoprodaja:     '🛒 Navedite: prodavca, kupca (ime, adresa), predmet prodaje (opis, serijski broj), cenu u RSD, način plaćanja, rok isporuke.',
  ugovor_zakup:           '🏠 Navedite: zakupodavca, zakupca (ime, adresa), opis nepokretnosti (adresa, površina), zakupninu (RSD/mesečno), period zakupa, depozit.',
};

/* Tipovi koji idu na /api/nacrt (drafting modul) */
var _NACRT_API_TYPES = new Set();
/* Pre-populate nacrt types — confirmed/extended by /api/nacrt/types fetch */
/* NOTE: 8 tipova → /api/podnesak (structured extraction+RAG+enrichment pipeline):
   tuzba_naknada_stete, zalba_parnicna, predlog_izvrsenje,
   tuzba_radni_spor, tuzba_razvod, prigovor_platni_nalog,
   krivicna_prijava, predlog_privremena_mera */
[
  'ugovor_neodredjeno','ugovor_odredjeno','aneks','sporazumni_raskid','punomocje',
  'zalba_na_presudu','zalba_na_resenje',
  'opomena_duznik','zahtev_poslodavcu','obaveštenje_o_otkazu',
  'ugovor_kupoprodaja','ugovor_zakup'
].forEach(function(v){ _NACRT_API_TYPES.add(v); });

/* Dinamičko učitavanje tipova ugovora iz /api/nacrt/types */
(function() {
  var BASE = (typeof BASE_URL !== 'undefined' ? BASE_URL : '') || '';
  fetch(BASE + '/api/nacrt/types')
    .then(function(r) { return r.ok ? r.json() : null; })
    .then(function(data) {
      if (!data || !Array.isArray(data.tipovi)) return;
      data.tipovi.forEach(function(t) {
        _NACRT_API_TYPES.add(t.vrsta);
        if (t.opis_hint) _PODNESAK_HINTS[t.vrsta] = '📄 ' + t.opis_hint;
      });
    })
    .catch(function() {});
})();
var _PODNESAK_PRIMERI = {
  tuzba: 'Tužilac Petar Petrović, ul. Vojvode Mišića 5, Beograd potražuje naknadu štete od tuženog Jovana Jovanovića, ul. Kneza Miloša 12, Beograd. Dana 15.03.2024. tuženi je vozilom reg. oznake BG 123-AB prouzrokovao saobraćajnu nezgodu na raskrsnici ul. Vojvode Mišića i Makedonske, usled čega je tužilac zadobio telesne povrede i pretrpeo materijalnu štetu (oštećeno vozilo) u ukupnom iznosu od 350.000 RSD. Postoji policijski zapisnik i nalaz lekara.',
  zalba: 'Žalilac Ana Anić, ul. Svetog Save 3, Novi Sad izjavljuje žalbu na presudu Osnovnog suda u Novom Sadu P. 456/2023 od 10.01.2024, kojom je odbijen njen tužbeni zahtev za naknadu štete. Prvostepeni sud je pogrešno utvrdio da nema uzročno-posledične veze, uprkos medicinskom nalazu koji potvrđuje direktnu vezu između povrede i štetnog dogadjaja. Protivnik žalioca je Osiguravajuće društvo "X" d.o.o.',
  izvrsenje: 'Tražilac izvršenja Dragan Dragić, ul. Cara Dušana 7, Kragujevac traži izvršenje na osnovu pravosnažne i izvršne presude Osnovnog suda u Kragujevcu P. 789/2022 od 05.06.2023, kojom je izvršenik Nikola Nikolić, ul. Toplička 2, Kragujevac obavezan da plati iznos od 180.000 RSD sa zakonskom zateznom kamatom od 05.06.2023. Izvršnik nije dobrovoljno izvršio obavezu. Predlažem zaplembu zarade izvršenika.',
};
function updatePodnesakHint() {
  var tip = document.getElementById('podnesak-tip');
  var hint = document.getElementById('podnesak-hint');
  if (tip && hint) hint.textContent = _PODNESAK_HINTS[tip.value] || '';
}

/* ─── SUD SELEKCIJA ─────────────────────────────────────────────────────── */
var _sudoviCache = null;
(function _loadSudovi() {
  fetch(BASE_URL + '/api/courts')
    .then(function(r){ return r.json(); })
    .then(function(d){ _sudoviCache = d.sudovi; })
    .catch(function(){});
})();

function _sud_dropdown_show() {
  if (!_sudoviCache) return;
  _sud_filter(document.getElementById('podnesak-sud-input').value || '');
}
function _sud_dropdown_hide() {
  var dd = document.getElementById('podnesak-sud-dropdown');
  if (dd) dd.style.display = 'none';
}
function _sud_filter(q) {
  var dd = document.getElementById('podnesak-sud-dropdown');
  if (!dd || !_sudoviCache) return;
  var ql = q.toLowerCase().trim();
  var html = '';
  var shown = 0;
  Object.entries(_sudoviCache).forEach(function(entry) {
    var kat = entry[0], lista = entry[1];
    var matches = lista.filter(function(s) {
      return !ql || s.naziv.toLowerCase().includes(ql) || s.grad.toLowerCase().includes(ql);
    });
    if (!matches.length) return;
    html += '<div style="padding:.35rem .75rem;font-size:.65rem;letter-spacing:.1em;text-transform:uppercase;color:#6b7d95;border-top:1px solid rgba(255,255,255,.05);">' + _htmlEsc(kat) + '</div>';
    matches.forEach(function(s) {
      html += '<div onclick="_sud_select(' + JSON.stringify(s.naziv) + ',' + JSON.stringify(s.adresa) + ')"'
        + ' style="padding:.45rem .75rem;font-size:.8rem;color:#cbd5e0;cursor:pointer;" '
        + ' onmouseenter="this.style.background=\'rgba(74,168,255,.1)\'" onmouseleave="this.style.background=\'\'">'
        + '<div style="color:#e2e8f0;font-weight:500;">' + _htmlEsc(s.naziv) + '</div>'
        + '<div style="font-size:.72rem;color:rgba(255,255,255,.35);">' + _htmlEsc(s.adresa) + '</div>'
        + '</div>';
      shown++;
    });
  });
  dd.innerHTML = html || '<div style="padding:.6rem .75rem;font-size:.8rem;color:rgba(255,255,255,.3);">Nije pronađen sud.</div>';
  dd.style.display = shown > 0 || ql ? 'block' : 'none';
}
function _sud_select(naziv, adresa) {
  document.getElementById('podnesak-sud-input').value = naziv;
  document.getElementById('podnesak-sud-naziv').value = naziv;
  document.getElementById('podnesak-sud-adresa').value = adresa;
  document.getElementById('podnesak-sud-dropdown').style.display = 'none';
}
function _sud_clear() {
  document.getElementById('podnesak-sud-input').value = '';
  document.getElementById('podnesak-sud-naziv').value = '';
  document.getElementById('podnesak-sud-adresa').value = '';
}
function _selectPodnesakOption(value) {
  var hidden = document.getElementById('podnesak-tip');
  if (hidden) hidden.value = value;
  document.querySelectorAll('.podnesak-option').forEach(function(btn) {
    btn.classList.toggle('selected', btn.dataset.value === value);
  });
  updatePodnesakHint();
}
function fillPodnesakPrimer(kljuc) {
  var el = document.getElementById('podnesak-opis');
  var mapa = { tuzba:'tuzba_naknada_stete', zalba:'zalba_parnicna', izvrsenje:'predlog_izvrsenje' };
  if (mapa[kljuc]) _selectPodnesakOption(mapa[kljuc]);
  if (el) { el.value = _PODNESAK_PRIMERI[kljuc] || ''; el.focus(); }
}

function copyPodnesak(btn) {
  var text = _lastRawText || '';
  if (!text) return;
  navigator.clipboard.writeText(text).then(function(){
    var orig = btn.textContent;
    btn.textContent = '✓ Kopirano!';
    setTimeout(function(){ btn.textContent = orig; }, 1800);
  }).catch(function(){
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;top:-9999px;left:-9999px;';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    var orig = btn.textContent;
    btn.textContent = '✓ Kopirano!';
    setTimeout(function(){ btn.textContent = orig; }, 1800);
  });
}

function editPodnesak() {
  document.getElementById('podnesak-preview').style.display='none';
  var el = document.getElementById('podnesak-opis');
  if (el) { el.focus(); el.scrollIntoView({behavior:'smooth', block:'center'}); }
}

/* ─── GLASOVNI UNOS (Web Speech API) ─────────────────────────────────────── */
(function(){
  var _rec           = null;   // aktivni SpeechRecognition objekat
  var _activeId      = null;   // ID textarea koji se snima
  var _baseText      = '';     // tekst u textarea pre početka snimanja
  var _useContinuous = true;   // false = fallback mode (za service-not-allowed)
  var _silenceTimer  = null;   // setTimeout handle za auto-submit
  var _SILENCE_MS    = 2500;   // ms tišine pre auto-submita

  function supported() {
    return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  }

  function _setStatus(id, on, msg) {
    var s = document.getElementById('mic-status-' + id);
    var b = document.getElementById('mic-' + id);
    var span = s ? s.querySelector('span:last-child') : null;
    if (s) on ? s.classList.add('show') : s.classList.remove('show');
    if (b) on ? b.classList.add('mic-active') : b.classList.remove('mic-active');
    if (span && msg) span.textContent = msg;
  }

  function _errorMsg(code) {
    var msgs = {
      'not-allowed':        '🔒 Mikrofon blokiran. Kliknite na katanac u URL baru → dozvolite mikrofon → osvežite stranicu.',
      'permission-denied':  '🔒 Mikrofon blokiran. Kliknite na katanac u URL baru → dozvolite mikrofon → osvežite stranicu.',
      'service-not-allowed':'⚙️ Servis blokiran. Probajte: Katanac → Mikrofon → Dozvoli. Ako ne radi, koristite Chrome na desktop-u.',
      'no-speech':          '',  // tiho — normalna situacija
      'aborted':            '',  // tiho — korisnik je sam zaustavio
      'audio-capture':      '🎙️ Mikrofon nije pronađen. Proverite da li je uređaj priključen.',
      'network':            '🌐 Nema internet konekcije. Glasovni unos zahteva online vezu.',
      'language-not-supported': '🌍 Srpski jezik nije podržan na ovom uređaju. Probajte Chrome na Windows/Mac.',
    };
    return msgs[code] || ('Greška glasovnog unosa: ' + code + '. Probajte ponovo ili koristite kucanje.');
  }

  function _cancelSilenceTimer() {
    if (_silenceTimer) { clearTimeout(_silenceTimer); _silenceTimer = null; }
    // Ukloni countdown vizual
    if (_activeId) _setStatus(_activeId, true, 'Snimam... govorite na srpskom (klik = stop)');
  }

  function _autoSubmit(targetId) {
    _silenceTimer = null;
    _stop();
    var ta = document.getElementById(targetId);
    if (!ta || !ta.value.trim()) return;

    // Bez logovanog korisnika auto-submit samo otvara modal, ne šalje
    if (!window.currentUser) {
      showToast('🎙 Prijavite se da biste koristili glasovni unos.', 'err');
      if (typeof openModal === 'function') openModal();
      return;
    }
    var btn = document.getElementById('mic-' + targetId);
    if (btn) btn.classList.remove('mic-active');
    showToast('🎙 Šaljem upit...', 'info');
    window._vxLastInputWasVoice = true;
    setTimeout(function() {
      if (typeof execQuery === 'function') execQuery();
    }, 300);
  }

  function _resetSilenceTimer(targetId) {
    _cancelSilenceTimer();
    // Countdown vizual u status labeli
    var count = Math.round(_SILENCE_MS / 1000);
    _setStatus(targetId, true, 'Snimam... auto-slanje za ' + count + 's (klik = otkaži)');
    var elapsed = 0;
    var tickInterval = setInterval(function() {
      elapsed += 500;
      var remaining = ((_SILENCE_MS - elapsed) / 1000).toFixed(1);
      if (elapsed >= _SILENCE_MS || !_activeId) { clearInterval(tickInterval); return; }
      _setStatus(targetId, true, 'Šaljem za ' + remaining + 's — govorite za nastavak');
    }, 500);
    _silenceTimer = setTimeout(function() {
      clearInterval(tickInterval);
      _autoSubmit(targetId);
    }, _SILENCE_MS);
  }

  function _stop() {
    _cancelSilenceTimer();
    if (_rec) { try { _rec.abort(); } catch(e){} _rec = null; }
    if (_activeId) { _setStatus(_activeId, false); _activeId = null; }
  }

  function _buildRec(useContinuous) {
    var SR  = window.SpeechRecognition || window.webkitSpeechRecognition;
    var rec = new SR();
    rec.lang            = 'sr-RS';
    rec.continuous      = useContinuous;
    rec.interimResults  = true;
    rec.maxAlternatives = 1;
    return rec;
  }

  function _start(targetId) {
    var ta      = document.getElementById(targetId);
    _baseText   = ta ? ta.value.trimEnd() : '';
    var pending = '';

    function tryStart(useCont) {
      var rec = _buildRec(useCont);

      rec.onstart = function() {
        _activeId = targetId;
        var lbl = useCont ? 'Snimam... govorite na srpskom (klik = stop)' : 'Snimam rečenicu... (klik = stop)';
        _setStatus(targetId, true, lbl);
      };

      rec.onresult = function(e) {
        var interim = '';
        for (var i = e.resultIndex; i < e.results.length; i++) {
          var chunk = e.results[i][0].transcript;
          if (e.results[i].isFinal) {
            pending += (_baseText || pending ? ' ' : '') + chunk.trim();
            _baseText = '';
          } else {
            interim = chunk;
          }
        }
        if (ta) {
          ta.value = (pending + (interim ? ' ' + interim : '')).trimStart();
          ta.selectionStart = ta.selectionEnd = ta.value.length;
        }
        // Svaki novi tekst resetuje tajmer za tišinu
        _resetSilenceTimer(targetId);
      };

      rec.onerror = function(ev) {
        var code = ev.error;
        _cancelSilenceTimer();
        _stop();
        // service-not-allowed u continuous modu — retry bez continuous
        if (code === 'service-not-allowed' && useCont) {
          _useContinuous = false;
          showToast('ℹ️ Prebacujem na jednorečenični mod...', 'info');
          setTimeout(function(){ tryStart(false); }, 400);
          return;
        }
        var msg = _errorMsg(code);
        if (msg) showToast(msg, 'err');
      };

      rec.onend = function() {
        if (_activeId === targetId) {
          // U non-continuous modu: automatski restart dok korisnik ne klikne stop
          if (!useCont && _rec === rec) {
            // rec je već završio — pokrenemo novi samo ako je _activeId još aktivan
            var newRec = _buildRec(false);
            _attachHandlers(newRec, targetId, pending);
            _rec = newRec;
            try { newRec.start(); } catch(e) { _stop(); }
            return;
          }
          _setStatus(targetId, false);
          _activeId = null;
          _rec = null;
        }
      };

      _rec = rec;
      try { rec.start(); } catch(e) { _stop(); showToast(_errorMsg('service-not-allowed'), 'err'); }
    }

    // Pomoćna funkcija za reconnect u non-continuous modu
    function _attachHandlers(rec, tid, sharedPending) {
      rec.lang = 'sr-RS'; rec.continuous = false; rec.interimResults = true;
      rec.onstart  = function(){ _setStatus(tid, true, 'Snimam rečenicu... (klik = stop)'); };
      rec.onresult = function(e){
        var interim = '';
        for (var i = e.resultIndex; i < e.results.length; i++) {
          var chunk = e.results[i][0].transcript;
          if (e.results[i].isFinal) { sharedPending += (sharedPending ? ' ':'') + chunk.trim(); }
          else { interim = chunk; }
        }
        var t = document.getElementById(tid);
        if (t) { t.value = (sharedPending + (interim?' '+interim:'')).trimStart(); t.selectionStart = t.selectionEnd = t.value.length; }
        _resetSilenceTimer(tid);
      };
      rec.onerror  = function(ev){ _cancelSilenceTimer(); var m=_errorMsg(ev.error); if(m) showToast(m,'err'); _stop(); };
      rec.onend    = function(){
        if (_activeId === tid && _rec === rec) {
          var nr = _buildRec(false); _attachHandlers(nr, tid, sharedPending); _rec = nr;
          try { nr.start(); } catch(e){ _stop(); }
        }
      };
    }

    tryStart(_useContinuous);
  }

  // ── AudioContext wake-up (iOS zahteva ovo unutar click handlera) ──────────
  var _audioCtx = null;
  function _wakeAudio() {
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      if (!_audioCtx) _audioCtx = new AC();
      if (_audioCtx.state === 'suspended') _audioCtx.resume();
    } catch(e) {}
  }

  // ── Javna API — sve SINHRONO unutar click handler-a ──────────────────────
  window.micToggle = function(targetId) {
    // 1. Provjera podrške
    if (!supported()) {
      showToast('⚠️ Glasovni unos nije podržan. Koristite Chrome ili Safari (iOS 15+).', 'err');
      return;
    }
    // 2. HTTPS provjera
    if (window.location.protocol !== 'https:' && window.location.hostname !== 'localhost') {
      showToast('⚠️ Glasovni unos zahteva HTTPS. Otvorite aplikaciju preko https://', 'err');
      return;
    }
    // 3. Probudi audio context SINHORNO (iOS user gesture rule)
    _wakeAudio();
    // 4. Ubij prethodnu instancu SINHRONO
    if (_rec) { try { _rec.abort(); } catch(e){} _rec = null; }
    // 5. Stop ako je isti target aktivan, inače start
    if (_activeId === targetId) {
      _stop();
    } else {
      if (_activeId) _stop();
      // _start() mora biti pozvan direktno — bez Promise/setTimeout između
      _start(targetId);
    }
  };

  window.micStopAll = function() { _stop(); };

  window._micIsActive = function() { return !!_rec; };
})();

/* ── Phase 2.3: Zakon izmene metadata ──────────────────────────────────────── */
var _ZAKON_IZMENE_DATA = {
  "ZR": {
    naziv:"Zakon o radu", pocetna:"24/2005", poslednja:"109/2025", god:2025,
    triggers:["Zakon o radu","Zakona o radu","Zakonu o radu","Zakonom o radu","zakonu o radu","zakona o radu","zakon o radu","ZR"]
  },
  "ZOO": {
    naziv:"Zakon o obligacionim odnosima", pocetna:"29/1978", poslednja:"44/2018", god:2018,
    triggers:["Zakon o obligacionim","Zakona o obligacionim","Zakonu o obligacionim","Zakonom o obligacionim","obligacionim odnosima","ZOO"]
  },
  "KZ": {
    naziv:"Krivični zakonik", pocetna:"85/2005", poslednja:"9/2023", god:2023,
    triggers:["Krivični zakonik","Krivičnog zakonika","Krivičnom zakoniku","Krivičnim zakonikom","krivični zakonik","krivičnog zakonika","KZ"]
  },
  "ZPP": {
    naziv:"Zakon o parničnom postupku", pocetna:"72/2011", poslednja:"18/2020", god:2020,
    triggers:["Zakon o parničnom","Zakona o parničnom","Zakonu o parničnom","parničnom postupku","ZPP"]
  },
  "ZKP": {
    naziv:"Zakonik o krivičnom postupku", pocetna:"72/2011", poslednja:"35/2019", god:2019,
    triggers:["Zakonik o krivičnom","Zakonika o krivičnom","krivičnom postupku","ZKP"]
  },
  "ZPD": {
    naziv:"Zakon o privrednim društvima", pocetna:"36/2011", poslednja:"109/2021", god:2021,
    triggers:["Zakon o privrednim","Zakona o privrednim","privrednim društvima","ZPD"]
  },
  "ZDI": {
    naziv:"Zakon o digitalnoj imovini", pocetna:"153/2020", poslednja:"153/2020", god:2020,
    triggers:["Zakon o digitalnoj imovini","Zakona o digitalnoj imovini","digitalnoj imovini","ZDI"]
  },
  "ZZPL": {
    naziv:"Zakon o zaštiti podataka o ličnosti", pocetna:"87/2018", poslednja:"87/2018", god:2018,
    triggers:["zaštiti podataka o ličnosti","podataka o ličnosti","ZZPL"]
  },
  "ZN": {
    naziv:"Zakon o nasleđivanju", pocetna:"46/1995", poslednja:"6/2015", god:2015,
    triggers:["Zakon o nasleđivanju","Zakona o nasleđivanju","nasleđivanju","ZN"]
  },
  "PZ": {
    naziv:"Porodični zakon", pocetna:"18/2005", poslednja:"6/2015", god:2015,
    triggers:["Porodični zakon","Porodičnog zakona","Porodičnom zakonu","PZ"]
  },
  "ZIO": {
    naziv:"Zakon o izvršenju i obezbeđenju", pocetna:"106/2015", poslednja:"9/2020", god:2020,
    triggers:["Zakon o izvršenju","Zakona o izvršenju","izvršenju i obezbeđenju","ZIO"]
  },
  "ZOUP": {
    naziv:"Zakon o opštem upravnom postupku", pocetna:"18/2016", poslednja:"95/2018", god:2018,
    triggers:["opštem upravnom postupku","upravnom postupku","ZOUP"]
  },
  "ZSPNFT": {
    naziv:"Zakon o sprečavanju pranja novca i finansiranja terorizma", pocetna:"113/2017", poslednja:"35/2023", god:2023,
    triggers:["pranja novca i finansiranja","sprečavanju pranja","pranja novca","ZSPNFT"]
  },
  "ZPDG": {
    naziv:"Zakon o porezu na dohodak građana", pocetna:"24/2001", poslednja:"118/2021", god:2021,
    triggers:["porezu na dohodak","dohodak građana","ZPDG"]
  }
};

function _izmenaTag(code) {
  var info = _ZAKON_IZMENE_DATA[code];
  if (!info) return '';
  var isRecent = (new Date().getFullYear() - info.god) <= 1;
  var cls = 'izmena-tag' + (isRecent ? ' izmena-recent' : '');
  var title = info.naziv + ' | Poslednja izmena Sl.gl. RS ' + info.poslednja;
  var lbl = (isRecent ? '⚠️ ' : '') + 'Sl.gl. ' + info.poslednja;
  return '<span class="' + cls + '" title="' + title + '">' + lbl + '</span>';
}

function _injectIzmeneBadges(html) {
  // For each law, iterate its triggers list (covers nominative + genitive + dative
  // + instrumental case forms + abbreviation — Serbian is highly inflected).
  // Uses indexOf (no regex) — safe for Serbian diacritics, no \b escaping issues.
  var tagged = {};

  // Flatten all triggers with their code, sort longest-needle-first
  var all = [];
  Object.keys(_ZAKON_IZMENE_DATA).forEach(function(code) {
    var info = _ZAKON_IZMENE_DATA[code];
    var trigs = info.triggers || [info.naziv, code];
    trigs.forEach(function(needle) { all.push({ needle: needle, code: code }); });
  });
  all.sort(function(a, b) { return b.needle.length - a.needle.length; });

  all.forEach(function(t) {
    if (tagged[t.code]) return;
    var idx = html.indexOf(t.needle);
    if (idx === -1) return;
    var tag = _izmenaTag(t.code);
    html = html.slice(0, idx + t.needle.length) + tag + html.slice(idx + t.needle.length);
    tagged[t.code] = true;
  });
  return html;
}

/* RESPONSE FORMATTER */
function escHtml(s){ if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

var lastPitanje = '';

function _linkGlasnik(val) {
  // Pretvara "Sl. glasnik RS, br. X/YYYY" u klikabilni link ka PIS portalu
  return escHtml(val).replace(
    /(Sl\.\s*(?:glasnik|list)\s*(?:RS|SRS|SFRJ|SRJ|SCG)[^<\n]{0,120})/g,
    '<a class="glasnik-link" href="https://www.pravno-informacioni-sistem.rs/" target="_blank" rel="noopener" title="Pravno-informacioni sistem RS">$1</a>'
  );
}

function formatResponse(rawText) {
  var defs = [
    // ── "--- CAPS" format — svi tipovi (PARNICA, COMPLIANCE, PORESKI, DEFINICIJA) ──
    { key:'[✓] STATUSNA POTVRDA:',              cls:'resp-status-ok',   lbl:'✓ Potvrda citiranja',             icon:'' },
    { key:'[v] STATUSNA POTVRDA:',              cls:'resp-status-ok',   lbl:'✓ Potvrda citiranja',             icon:'' },
    { key:'[~] STATUSNA POTVRDA:',              cls:'resp-status-warn', lbl:'~ Potvrda citiranja',             icon:'' },
    { key:'[!] STATUSNA POTVRDA:',              cls:'resp-status-err',  lbl:'! Potvrda citiranja',             icon:'' },
    { key:'--- HIJERARHIJA IZVORA',             cls:'resp-hijerarhija', lbl:'⚖ Hijerarhija izvora',            icon:'hijerarhija' },
    { key:'--- PRAVNI ZAKLJUČAK',               cls:'resp-zakljucak',   lbl:'⚖️ Pravni zaključak',             icon:'zakljucak' },
    // Specifičnije ANALIZA sekcije moraju biti pre generičke --- ANALIZA
    { key:'--- ANALIZA USKLAĐENOSTI',           cls:'resp-steta',       lbl:'⚖ Analiza usklađenosti',          icon:'steta' },
    { key:'--- ANALIZA PORESKE OBAVEZE',        cls:'resp-steta',       lbl:'⚖ Analiza poreske obaveze',       icon:'steta' },
    { key:'--- ANALIZA ŠTETE',                  cls:'resp-steta',       lbl:'⚖ Analiza štete',                 icon:'steta' },
    { key:'--- ANALIZA',                        cls:'resp-steta',       lbl:'⚖ Analiza',                       icon:'steta' },
    { key:'--- PROCENA VREDNOSTI ZAHTEVA',      cls:'resp-procena',     lbl:'💰 Procena vrednosti zahteva',     icon:'' },
    { key:'--- CITAT ZAKONA',                   cls:'resp-citat',       lbl:'📖 Citat zakona [RAG]',            icon:'citat' },
    { key:'--- PRAVNI OSNOV',                   cls:'resp-pravni-osnov',lbl:'⚖ Pravni osnov',                  icon:'osnov' },
    // Specifičnije RIZICI sekcije pre generičke
    { key:'--- RIZICI I ROKOVI',                cls:'resp-rizici',      lbl:'⚠️ Rizici i rokovi',              icon:'rizici' },
    { key:'--- PORESKI RIZICI',                 cls:'resp-rizici',      lbl:'⚠️ Poreski rizici',               icon:'rizici' },
    { key:'--- RIZICI I IZUZECI',               cls:'resp-rizici',      lbl:'⚠️ Rizici i izuzeci',             icon:'rizici' },
    { key:'--- KADA OVO NE VAŽI',               cls:'resp-kad-ne-vazi', lbl:'⛔ Kada ovo ne važi',              icon:'' },
    // Procesni koraci — specifičnije pre generičkog
    { key:'--- COMPLIANCE KORACI',              cls:'resp-procesni',    lbl:'✅ Compliance koraci',             icon:'procesni' },
    { key:'--- PORESKE OBAVEZE — KORACI', cls:'resp-procesni',    lbl:'📋 Poreske obaveze — koraci',      icon:'procesni' },
    { key:'--- PROCESNI KORACI',                cls:'resp-procesni',    lbl:'📋 Procesni koraci',               icon:'procesni' },
    // DEFINICIJA specifične sekcije
    { key:'--- PRAVNA DEFINICIJA',              cls:'resp-pravna-def',  lbl:'📖 Pravna definicija',             icon:'citat' },
    { key:'--- PRAKTIČAN PRIMER',               cls:'resp-edgecase',    lbl:'💡 Praktičan primer',              icon:'' },
    { key:'--- KLJUČNO PITANJE',                cls:'resp-kljucno-parnica', lbl:'🎯 Ključno pitanje',          icon:'' },
    { key:'--- POTREBNE INFORMACIJE',           cls:'resp-potrebne',    lbl:'📌 Potrebne informacije',          icon:'' },
    { key:'--- MIŠLJENJA MINISTARSTAVA',          cls:'resp-misljenje',   lbl:'📋 Mišljenja ministarstava',       icon:'' },
    { key:'--- IZVOR',                          cls:'resp-izvor',       lbl:'Izvor',                           icon:'' },
    // ── v2.0 sekcije (emoji + mixed case) ──────────────────────────────────
    { key:'⚡ TL;DR',                      cls:'resp-tldr',        lbl:'⚡ TL;DR — Kratak zaključak', icon:'tldr' },
    { key:'⚖️ Pravni zaključak',           cls:'resp-zakljucak',   lbl:'⚖️ Pravni zaključak',        icon:'zakljucak' },
    { key:'📖 Citat zakona',               cls:'resp-citat',       lbl:'📖 Citat zakona',             icon:'citat' },
    { key:'📖 Pravna definicija',          cls:'resp-zakljucak',   lbl:'📖 Pravna definicija',        icon:'zakljucak' },
    { key:'🔗 Lanac rezonovanja',          cls:'resp-lanac',       lbl:'🔗 Lanac rezonovanja',        icon:'lanac' },
    { key:'⚖ Pravni osnov',               cls:'resp-pravni-osnov',lbl:'⚖ Pravni osnov',             icon:'osnov' },
    { key:'⚠️ Rizici i rokovi zastarelosti', cls:'resp-rizici',   lbl:'⚠️ Rizici i rokovi',         icon:'rizici' },
    { key:'⚠️ Rizici i rokovi',            cls:'resp-rizici',      lbl:'⚠️ Rizici i rokovi',         icon:'rizici' },
    { key:'⚠️ Poreski rizici',             cls:'resp-rizici',      lbl:'⚠️ Poreski rizici',          icon:'rizici' },
    { key:'✅ Compliance koraci',          cls:'resp-procesni',    lbl:'✅ Compliance koraci',        icon:'procesni' },
    { key:'📋 Poreske obaveze — koraci',   cls:'resp-procesni',    lbl:'📋 Poreske obaveze',         icon:'procesni' },
    { key:'📋 Procesni koraci',            cls:'resp-procesni',    lbl:'📋 Procesni koraci',          icon:'procesni' },
    { key:'🎯 Pouzdanost',                 cls:'resp-pouzdanost',  lbl:'🎯 Pouzdanost',               icon:'pouzdanost' },
    { key:'🎯 Ključno pitanje',            cls:'resp-kljucno',     lbl:'🎯 Ključno pitanje',          icon:'kljucno' },
    { key:'💡 Praktičan primer',           cls:'resp-edgecase',    lbl:'💡 Praktičan primer',         icon:'' },
    { key:'ℹ️ Napomena',                   cls:'resp-disclaimer',  lbl:'Napomena',                   icon:'' },
    // ── v1 sekcije (CAPS + colon) — zadržane za kompatibilnost ─────────────
    { key:'KRATAK ZAKLJUČAK (TL;DR):', cls:'resp-tldr',       lbl:'⚡ TL;DR — Kratak zaključak', icon:'tldr' },
    { key:'HIJERARHIJA IZVORA:', cls:'resp-hijerarhija', lbl:'⚖ Hijerarhija izvora',   icon:'hijerarhija' },
    { key:'PRAVNI ZAKLJUČAK:',  cls:'resp-zakljucak',  lbl:'⚖️ Pravni zaključak',    icon:'zakljucak' },
    { key:'ANALIZA ŠTETE:',     cls:'resp-steta',      lbl:'⚖ Analiza štete',         icon:'steta' },
    { key:'CITAT ZAKONA:',      cls:'resp-citat',      lbl:'📖 Citat zakona',          icon:'citat' },
    { key:'CITAT IZ ZAKONA:',   cls:'resp-citat',      lbl:'📖 Citat zakona',          icon:'citat' },
    { key:'PRAVNI OSNOV:',      cls:'resp-pravni-osnov',lbl:'Pravni osnov',            icon:'osnov' },
    { key:'POUZDANOST:',        cls:'resp-pouzdanost', lbl:'Pouzdanost',               icon:'pouzdanost' },
    { key:'RIZICI I IZUZECI:',  cls:'resp-rizici',     lbl:'⚠️ Rizici i izuzeci',     icon:'rizici' },
    { key:'KADA OVO NE VAŽI:',  cls:'resp-edgecase',   lbl:'📍 Kada ovo ne važi',     icon:'edgecase' },
    { key:'PROCESNI KORACI:',   cls:'resp-procesni',   lbl:'⚡ Procesni koraci',       icon:'procesni' },
    { key:'KLJUČNO PITANJE:',   cls:'resp-kljucno',    lbl:'🎯 Ključno pitanje',       icon:'kljucno' },
    { key:'DODATNA PITANJA:',   cls:'resp-pitanja',    lbl:'🔍 Potrebne informacije',  icon:'pitanja' },
    { key:'NACRT:',             cls:'resp-nacrt',      lbl:'Nacrt dokumenta',       icon:'' },
    { key:'ANALIZA:',           cls:'resp-analiza',    lbl:'Analiza',               icon:'' },
    { key:'IDENTIFIKOVANI RIZICI:', cls:'resp-rizici', lbl:'⚠️ Identifikovani rizici', icon:'' },
    { key:'PREPORUKE:',         cls:'resp-preporuke',  lbl:'Preporuke',             icon:'' },
    { key:'ODGOVOR:',           cls:'resp-odgovor',    lbl:'Odgovor',               icon:'' },
    { key:'PRAVNA POSLEDICA:',  cls:'resp-posledica',  lbl:'Pravna posledica',      icon:'' },
    { key:'SLUŽBENI IZVOR:',    cls:'resp-izvor',      lbl:'Izvor',                 icon:'' },
    { key:'VAŽNA NAPOMENA:',    cls:'resp-disclaimer', lbl:'Pravna napomena',       icon:'' },
    { key:'NAPOMENA SISTEMA:',  cls:'resp-disclaimer', lbl:'Napomena sistema',      icon:'' },
  ];
  // Nacrt podneska — prepoznaj po NAPOMENA SISTEMA markeru i odsustvu standardnih sekcija
  var isPodnesak = rawText.indexOf('NAPOMENA SISTEMA: Ovaj nacrt je generisan') !== -1
                && rawText.indexOf('PRAVNI ZAKLJUČAK:') === -1
                && rawText.indexOf('HIJERARHIJA IZVORA:') === -1;
  if (isPodnesak) {
    var highlighted = escHtml(rawText).replace(/\[([A-ZŠĐČĆŽ\s\-—]+?)\s*—\s*POPUNITI\]/g,
      '<span class="popuniti">[$1 — POPUNITI]</span>');
    return '<div class="resp-nacrt-podnesak">'+highlighted+'</div>';
  }
  var isStructured = defs.some(function(d){ return rawText.indexOf(d.key) !== -1; });
  if (!isStructured) return '<div class="resp-plain">'+escHtml(rawText)+'</div>';
  var found = []; var usedPos = {};
  defs.forEach(function(d){
    var idx = rawText.indexOf(d.key);
    if (idx !== -1 && !usedPos[idx]) {
      usedPos[idx] = true;
      found.push({ pos:idx, keyLen:d.key.length, cls:d.cls, lbl:d.lbl, icon:d.icon });
    }
  });
  found.sort(function(a,b){ return a.pos-b.pos; });

  // Izvuci vrednosti za akciona dugmad
  var citatVal = '', osnovVal = '', zakljucakVal = '';
  found.forEach(function(s,i){
    var start = s.pos + s.keyLen;
    var end = i+1 < found.length ? found[i+1].pos : rawText.length;
    var val = rawText.slice(start,end).trim();
    if (s.cls === 'resp-citat') citatVal = val;
    if (s.cls === 'resp-pravni-osnov') osnovVal = val;
    if (s.cls === 'resp-zakljucak') zakljucakVal = val;
  });

  // Odredi signal pouzdanosti
  var pouzdanostVal = '';
  found.forEach(function(s,i){
    if(s.cls === 'resp-pouzdanost'){
      var start = s.pos + s.keyLen;
      var end = i+1 < found.length ? found[i+1].pos : rawText.length;
      pouzdanostVal = rawText.slice(start,end).trim();
    }
  });
  var trustBadge;
  var isV2 = rawText.indexOf('⚡ TL;DR') !== -1;
  // Novi "---" format (PARNICA) — status badge dolazi iz STATUSNA POTVRDA sekcije, ne dupliraj
  var isNewFmt = rawText.indexOf('--- HIJERARHIJA IZVORA') !== -1 || rawText.indexOf('[✓] STATUSNA POTVRDA') !== -1 || rawText.indexOf('[~] STATUSNA POTVRDA') !== -1 || rawText.indexOf('[!] STATUSNA POTVRDA') !== -1;
  if (isNewFmt) {
    trustBadge = '';
  } else if (pouzdanostVal.indexOf('✅') !== -1 || pouzdanostVal.indexOf('Doslovno') !== -1 || pouzdanostVal.indexOf('Visoka') !== -1) {
    trustBadge = '<div class="trust-badge trust-high">✅ Doslovno citiran — član direktno pronađen u bazi zakona RS.</div>';
  } else if (pouzdanostVal.indexOf('📝') !== -1 || pouzdanostVal.indexOf('Parafrazirano') !== -1) {
    trustBadge = '<div class="trust-badge trust-mid">📝 Parafrazirano — sadržaj zakona potvrđen, nije doslovan citat.</div>';
  } else if (isV2) {
    trustBadge = '';
  } else {
    trustBadge = '<div class="trust-badge trust-low">⚠️ Opšta pravna logika — nije pronađen direktan član, odgovor baziran na principima prava.</div>';
  }

    var isHigh = pouzdanostVal.indexOf('✅') !== -1 || pouzdanostVal.indexOf('Doslovno') !== -1 || pouzdanostVal.indexOf('Visoka') !== -1;
  var verifiedBadge = isHigh ? '<span class="rag-verified">✓ RAG</span>' : '';

  // Detekcija tipa upita na osnovu HIJERARHIJA IZVORA sekcije — za dinamički prikaz
  var _tipUpita = 'obligaciono';
  found.forEach(function(s,i){
    if (s.cls === 'resp-hijerarhija') {
      var start = s.pos + s.keyLen;
      var end = i+1 < found.length ? found[i+1].pos : rawText.length;
      var hTxt = rawText.slice(start, end).toLowerCase();
      if (/krivic[nš]|krivicni zakonik|kz\s*čl|kz\s*cl/.test(hTxt)) {
        _tipUpita = 'krivicno';
      } else if (/porez|poresk|zpdg|pdv|zakon o porezu/.test(hTxt)) {
        _tipUpita = 'poresko';
      }
    }
  });
  // Sekcije koje se skrivaju po tipu — guardrail za slučaj kada AI generiše pogrešne sekcije
  var _skriveneZaTip = {
    krivicno: {'resp-steta':1, 'resp-procena':1},
    poresko:  {'resp-steta':1, 'resp-procena':1}
  };
  var _skrivene = _skriveneZaTip[_tipUpita] || {};

  var html = trustBadge;
  found.forEach(function(s,i){
    var start = s.pos + s.keyLen;
    var end = i+1 < found.length ? found[i+1].pos : rawText.length;
    var val = rawText.slice(start,end).trim();
    if (s.cls === 'resp-pouzdanost') return;
    if (s.cls === 'resp-disclaimer') return;
    if (_skrivene[s.cls]) return;
    var lbl = s.lbl;
    var bodyHtml;
    if (s.cls === 'resp-citat') {
      lbl = s.lbl + verifiedBadge;
      // Izvuci bold naslov — prva linija koja sadrži "Član X" ili naziv zakona
      var citatLines = val.split('\n').filter(function(l){ return l.trim(); });
      var titleLine = '';
      var bodyLines = citatLines;
      // Traži liniju oblika "Naziv zakona, član X..." ili "Član X ZOO"
      var titleMatch = val.match(/^["„]?([^:\n]{5,80}(?:član|Član|čl\.|member)\s*\d+[^\n]*)/i)
                    || val.match(/^["„]?((?:Zakon|ZOO|ZDI|ZOR|ZSPNFT|ZPDG)[^\n]{0,80})/i);
      if (titleMatch) {
        titleLine = titleMatch[1].replace(/^["„]+/, '').replace(/["]+$/, '').trim();
        bodyLines = citatLines.slice(1);
      } else if (citatLines.length > 0) {
        // Prva linija kao naslov ako izgleda kao reference (sadrži "član" ili broj)
        if (/član|Član|čl\.|zakon|Zakon/i.test(citatLines[0]) && citatLines[0].length < 100) {
          titleLine = citatLines[0].replace(/^["„]+/, '').replace(/[":]+$/, '').trim();
          bodyLines = citatLines.slice(1);
        }
      }
      var citatBody = bodyLines.join('\n').replace(/^["„\s]+|["„\s]+$/g,'').trim();
      var citatHtml = escHtml(citatBody).replace(/\n/g,'<br>');
      var lineCount = bodyLines.length;
      var titleHtml = titleLine ? '<div class="citat-clan-title">' + escHtml(titleLine) + '</div>' : '';
      if (lineCount > 3) {
        var uid = 'citat_' + i;
        bodyHtml = titleHtml +
          '<blockquote class="citat-blockquote citat-collapsed" id="' + uid + '">' + citatHtml + '</blockquote>' +
          '<button class="citat-toggle" onclick="toggleCitat(\'' + uid + '\',this)">Prikaži ceo tekst ▼</button>';
      } else {
        bodyHtml = titleHtml + '<blockquote class="citat-blockquote">' + citatHtml + '</blockquote>';
      }
    } else if (s.cls === 'resp-pravni-osnov') {
      bodyHtml = _linkGlasnik(val).replace(/\n/g,'<br>');
    } else if (s.cls === 'resp-izvor') {
      // Razdvoji zakone od disclaimera (linija koja počinje sa ⚠️)
      var discIdx = val.indexOf('\n⚠️');
      if (discIdx === -1) discIdx = val.indexOf('\n⚠ ');
      if (discIdx !== -1) {
        var izvorDeo = val.slice(0, discIdx).trim();
        var discDeo = val.slice(discIdx).trim();
        bodyHtml = _linkGlasnik(izvorDeo).replace(/\n/g,'<br>') +
          '<div class="resp-disclaimer-box">' + escHtml(discDeo) + '</div>';
      } else {
        bodyHtml = _linkGlasnik(val).replace(/\n/g,'<br>');
      }
    } else if (s.cls === 'resp-misljenje') {
      // Parse individual ministry opinions — each starts with "Mišljenje ..."
      var _mBlocks = val.split(/(?=Mišljenje\s+)/i).filter(function(b){ return b.trim(); });
      if (!_mBlocks.length) {
        bodyHtml = escHtml(val).replace(/\n/g,'<br>');
      } else {
        bodyHtml = _mBlocks.map(function(block) {
          var _mLines = block.split('\n');
          var _hdr = (_mLines[0] || '').trim(); // "Mišljenje MinRad, 011-00-152/2024, 15.03.2024:"
          var _hdrBody = _hdr.replace(/^Mišljenje\s*/i,'').replace(/:$/,'');
          var _parts = _hdrBody.split(/,\s*/);
          var _min  = _parts[0] || '';
          var _broj = _parts[1] || '';
          var _dat  = _parts.slice(2).join(', ');
          var _rest = _mLines.slice(1).filter(function(l){ return l.trim(); });
          var _naziv = _rest.length ? _rest[0].trim() : '';
          var _tekst = _rest.slice(1).join('\n').trim();
          var _preview = _tekst.length > 280 ? _tekst.slice(0,280)+'...' : _tekst;
          var _c = '<div class="misljenje-card">'
            + '<div class="misljenje-header">'
            + (_min  ? '<span class="misljenje-min">'+escHtml(_min)+'</span>' : '')
            + (_broj ? '<span class="misljenje-broj">'+escHtml(_broj)+'</span>' : '')
            + (_dat  ? '<span class="misljenje-datum">'+escHtml(_dat)+'</span>' : '')
            + '</div>'
            + (_naziv   ? '<div class="misljenje-naziv">'+escHtml(_naziv)+'</div>' : '')
            + (_preview ? '<div class="misljenje-tekst">'+escHtml(_preview)+'</div>' : '')
            + '</div>';
          return _c;
        }).join('');
      }
    } else {
      bodyHtml = escHtml(val).replace(/\n/g,'<br>');
    }
    html += '<div class="resp-section '+s.cls+'" style="animation-delay:'+(i*0.07)+'s">'+
            '<div class="resp-section-lbl">'+lbl+'</div>'+
            '<div class="resp-section-body">'+bodyHtml+'</div>'+
            '</div>';
  });

  if (!isNewFmt) {
    html += '<div class="resp-disclaimer-box">'+
      '<span class="disc-icon">ℹ</span>'+
      '<span class="disc-text">Ovaj izveštaj je generisan uz pomoć AI i služi isključivo kao pomoćno sredstvo u radu. '+
      'Konsultujte originalni tekst propisa u Službenom glasniku RS. '+
      'Nije pravni savet — podložno promenama u sudskoj praksi.</span>'+
      '</div>';
  }

  // Akciona dugmad
  var citatEnc = encodeURIComponent(citatVal);
  var osnovEnc = encodeURIComponent(osnovVal);
  var zakljucakEnc = encodeURIComponent(zakljucakVal);
  var fullEnc = encodeURIComponent(rawText);
  var osnovLabel = osnovVal ? osnovVal.replace(/\*\*/g,'').trim().substring(0,60) : 'Sl. glasnik';
  html += '<div class="resp-actions">'+
    '<button class="resp-action-btn" onclick="copyToClipboard(decodeURIComponent(\'' +citatEnc+ '\'),this)">📎 Kopiraj citat</button>'+
    '<button class="resp-action-btn" onclick="copyToClipboard(decodeURIComponent(\'' +osnovEnc+ '\'),this)">📋 Izvor: '+ osnovLabel +'</button>'+
    '<button class="resp-action-btn" style="background:rgba(74,168,255,0.07);border-color:rgba(74,168,255,0.25);color:#89c8ff;" onclick="exportPDF(decodeURIComponent(\'' +fullEnc+ '\'),this)">📄 Sačuvaj PDF</button>'+
    '<button class="resp-action-btn btn-word" onclick="exportujKaoWord(\'Pravno istraživanje\',_lastRawText,\'istrazivanje\')">📝 Word</button>'+
    '<button class="resp-action-btn follow-up-btn" id="followUpBtn_'+Date.now()+'" onclick="startFollowUp(this)">🔁 Follow-up</button>'+
    '</div>';
  html = _injectIzmeneBadges(html);
  return html;
}

function copyToClipboard(text, btn) {
  var clean = text.replace(/^"+|"+$/g,'').trim();
  if (!clean) { btn.textContent = '⚠ Nema citata'; setTimeout(function(){ btn.textContent = '📎 Kopiraj citat'; }, 2000); return; }
  navigator.clipboard.writeText(clean).then(function(){
    var orig = btn.textContent; btn.textContent = '✓ Kopirano!'; btn.disabled = true;
    setTimeout(function(){ btn.textContent = orig; btn.disabled = false; }, 2000);
  }).catch(function(){ btn.textContent = '⚠ Greška'; });
}

function copyZakljucak(text, btn) {
  var clean = text.replace(/^"+|"+$/g,'').trim();
  if (!clean) { btn.textContent = '⚠ Nema zaključka'; setTimeout(function(){ btn.textContent = '📋 Kopiraj zaključak'; }, 2000); return; }
  navigator.clipboard.writeText(clean).then(function(){
    var orig = btn.textContent; btn.textContent = '✓ Zaključak kopiran!'; btn.disabled = true;
    setTimeout(function(){ btn.textContent = orig; btn.disabled = false; }, 2000);
  }).catch(function(){ btn.textContent = '⚠ Greška'; });
}

function sazimiZaKlijenta(fullText, btn) {
  if (!currentSession) {
    showToast('Morate biti prijavljeni za ovu funkciju.', 'err');
    return;
  }
  var sel = document.createElement('div');
  sel.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:9999;display:flex;align-items:center;justify-content:center;';
  sel.innerHTML = '<div style="background:#1a1a2e;border:1px solid rgba(255,255,255,0.15);border-radius:12px;padding:1.8rem;max-width:420px;width:90%;">'
    + '<div style="font-size:0.65rem;text-transform:uppercase;letter-spacing:0.1em;color:rgba(255,255,255,0.4);margin-bottom:1rem;">✨ Sažetak za klijenta — odaberite format</div>'
    + '<div style="display:flex;flex-direction:column;gap:0.6rem;">'
    + '<button data-fmt="email" style="background:rgba(99,102,241,0.15);border:1px solid rgba(99,102,241,0.35);color:#a5b4fc;padding:0.7rem 1rem;border-radius:8px;cursor:pointer;font-family:inherit;font-size:0.85rem;text-align:left;">📧 Email — formalni, sa pozdravom</button>'
    + '<button data-fmt="viber" style="background:rgba(74,222,128,0.1);border:1px solid rgba(74,222,128,0.25);color:#4ade80;padding:0.7rem 1rem;border-radius:8px;cursor:pointer;font-family:inherit;font-size:0.85rem;text-align:left;">💬 Viber — kratak, neformalan (3-4 rečenice)</button>'
    + '<button data-fmt="pisano" style="background:rgba(251,191,36,0.1);border:1px solid rgba(251,191,36,0.25);color:#fbbf24;padding:0.7rem 1rem;border-radius:8px;cursor:pointer;font-family:inherit;font-size:0.85rem;text-align:left;">📄 Pisano obaveštenje — zvanično pismo</button>'
    + '</div>'
    + '<button onclick="this.closest(\'[style*=fixed]\').remove()" style="margin-top:1rem;background:none;border:none;color:rgba(255,255,255,0.3);cursor:pointer;font-family:inherit;font-size:0.8rem;">✕ Odustani</button>'
    + '</div>';
  sel.addEventListener('click', function(e){ if(e.target===sel) sel.remove(); });
  sel.querySelectorAll('[data-fmt]').forEach(function(b){
    b.addEventListener('click', function(){
      var fmt = b.getAttribute('data-fmt');
      sel.remove();
      _doSazmi(fullText, btn, fmt);
    });
  });
  document.body.appendChild(sel);
}

function _doSazmi(fullText, btn, fmt) {
  var orig = btn.textContent;
  btn.textContent = '⏳ Generišem...'; btn.disabled = true;
  var token = currentSession.access_token;
  fetch(BASE_URL + '/api/sazmi', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
    body: JSON.stringify({ odgovor: fullText.substring(0, 6000), format: fmt })
  })
  .then(function(r){ return r.json(); })
  .then(function(data){
    btn.textContent = orig; btn.disabled = false;
    var sazetak = data.sazetak || data.detail || 'Greška pri generisanju.';
    var fmtLabel = { email: '📧 Email', viber: '💬 Viber', pisano: '📄 Pisano obaveštenje' }[fmt] || '';
    var modal = document.createElement('div');
    modal.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:9999;display:flex;align-items:center;justify-content:center;';
    modal.innerHTML = '<div style="background:#1a1a2e;border:1px solid rgba(255,255,255,0.15);border-radius:12px;padding:2rem;max-width:560px;width:90%;max-height:80vh;overflow-y:auto;position:relative;">'
      + '<div style="font-size:0.65rem;text-transform:uppercase;letter-spacing:0.1em;color:rgba(255,255,255,0.4);margin-bottom:0.75rem;">✨ Verzija za klijenta — ' + fmtLabel + '</div>'
      + '<div style="font-size:0.9rem;line-height:1.7;color:rgba(255,255,255,0.85);white-space:pre-wrap;">' + escHtml(sazetak) + '</div>'
      + '<div style="display:flex;gap:0.6rem;margin-top:1.2rem;flex-wrap:wrap;">'
      + '<button onclick="navigator.clipboard.writeText(' + JSON.stringify(sazetak) + ').then(function(){this.textContent=\'✓ Kopirano!\';}.bind(this))" style="background:rgba(74,222,128,0.1);border:1px solid rgba(74,222,128,0.3);color:#4ade80;padding:0.4rem 1rem;border-radius:6px;cursor:pointer;font-family:inherit;font-size:0.75rem;">📋 Kopiraj tekst</button>'
      + '<button onclick="this.closest(\'[style*=fixed]\').remove()" style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.12);color:rgba(255,255,255,0.6);padding:0.4rem 1rem;border-radius:6px;cursor:pointer;font-family:inherit;font-size:0.75rem;">✕ Zatvori</button>'
      + '</div></div>';
    modal.addEventListener('click', function(e){ if(e.target===modal) modal.remove(); });
    document.body.appendChild(modal);
  })
  .catch(function(){ btn.textContent = '⚠ Greška'; btn.disabled = false; setTimeout(function(){ btn.textContent = orig; }, 2000); });
}
function showIzvor(text, btn) {
  var orig = btn.textContent;
  btn.textContent = text.length > 5 ? text.substring(0, 80) : 'Izvor nije dostupan';
  btn.style.whiteSpace = 'normal'; btn.style.maxWidth = '400px';
  setTimeout(function(){ btn.textContent = orig; btn.style.whiteSpace = ''; btn.style.maxWidth = ''; }, 4000);
}


function exportPDF(rawText, btn) {
  var orig = btn.textContent; btn.textContent = '\u23f3 Priprema PDF...'; btn.disabled = true;
  var firma = JSON.parse(localStorage.getItem('vindex_firma') || '{}');
  var datumObj = new Date();
  var datum = datumObj.toLocaleDateString('sr-Latn-RS', {day:'2-digit',month:'2-digit',year:'numeric'});
  var fileDate = [datumObj.getFullYear(), String(datumObj.getMonth()+1).padStart(2,'0'), String(datumObj.getDate()).padStart(2,'0')].join('_');
  var fileName = 'Vindex_Izvestaj_' + fileDate + '.pdf';
  var pitanje = lastPitanje || '';
  var title = 'Pravna analiza';
  if (pitanje.length > 5) title += ' \u2014 ' + pitanje.substring(0,80) + (pitanje.length>80?'...':'');
  var sectionDefs = [
    {key:'KRATAK ZAKLJU\u010cAK (TL;DR):', lbl:'TL;DR \u2014 Kratak zaklju\u010dak'},
    {key:'HIJERARHIJA IZVORA:', lbl:'Hijerarhija izvora'},
    {key:'PRAVNI ZAKLJU\u010cAK:', lbl:'Pravni zaklju\u010dak'},
    {key:'ANALIZA \u0160TETE:', lbl:'Analiza \u0161tete'},
    {key:'CITAT ZAKONA:', lbl:'Citat zakona'},
    {key:'CITAT IZ ZAKONA:', lbl:'Citat zakona'},
    {key:'PRAVNI OSNOV:', lbl:'Pravni osnov'},
    {key:'RIZICI I IZUZECI:', lbl:'Rizici i izuzeci'},
    {key:'KADA OVO NE VA\u017dI:', lbl:'Kada ovo ne va\u017ei'},
    {key:'PROCESNI KORACI:', lbl:'Procesni koraci'},
    {key:'KLJU\u010cNO PITANJE:', lbl:'Klju\u010dno pitanje'},
    {key:'DODATNA PITANJA:', lbl:'Dodatna pitanja'},
    {key:'SLU\u017dBENI IZVOR:', lbl:'Izvor'},
  ];
  var positions = sectionDefs.map(function(d){return{d:d,pos:rawText.indexOf(d.key)};}).filter(function(x){return x.pos!==-1;});
  positions.sort(function(a,b){return a.pos-b.pos;});
  var sectionsHtml = positions.map(function(x,i){
    var start=x.pos+x.d.key.length;
    var end=i+1<positions.length?positions[i+1].pos:rawText.length;
    var val=rawText.slice(start,end).trim();
    var lbl=x.d.lbl;
    if(_cyrillicOn && window.pretvoriUCirilicu){ val=pretvoriUCirilicu(val); lbl=pretvoriUCirilicu(lbl); }
    return '<div class="pdf-section"><div class="pdf-lbl">'+lbl.toUpperCase()+'</div><div class="pdf-val">'+val.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>')+'</div></div>';
  }).join('');

  var css = '@page{size:A4;margin:20mm 22mm;}body{font-family:Arial,sans-serif;font-size:10pt;color:#111;line-height:1.6;margin:0;}'
    +'.header{border-bottom:2px solid #1a1a3e;padding-bottom:8px;margin-bottom:16px;display:flex;justify-content:space-between;align-items:flex-end;}'
    +'.firma-naziv{font-size:13pt;font-weight:bold;color:#1a1a3e;}.firma-info{font-size:8.5pt;color:#555;line-height:1.5;}'
    +'.brand{font-size:8pt;color:#888;text-align:right;}'
    +'.title{font-size:14pt;font-weight:bold;color:#1a1a3e;margin:12px 0 4px;}'
    +'.datum{font-size:8.5pt;color:#888;margin-bottom:16px;border-bottom:1px solid #e0e0e0;padding-bottom:8px;}'
    +'.pdf-section{margin-bottom:14px;page-break-inside:avoid;}'
    +'.pdf-lbl{font-size:7.5pt;font-weight:bold;letter-spacing:0.1em;color:#1a1a3e;text-transform:uppercase;margin-bottom:3px;border-left:3px solid #1a1a3e;padding-left:6px;}'
    +'.pdf-val{font-size:9.5pt;color:#333;padding-left:9px;}'
    +'.disclaimer{background:#f8f8f8;border:1px solid #ddd;border-radius:4px;padding:8px 12px;font-size:8pt;color:#666;margin-top:20px;font-style:italic;}';

  var bodyHtml = '__CSS_REMOVED__'
    +'<div class="header"><div><div class="firma-naziv">'+(firma.naziv||'Vindex AI')+'</div>'
    +'<div class="firma-info">'+(firma.adresa?firma.adresa+'<br>':'')+(firma.pib?'PIB: '+firma.pib+'<br>':'')+(firma.kontakt||'')+'</div></div>'
    +'<div class="brand">Generisano putem<br><strong>Vindex AI</strong></div></div>'
    +'<div class="title">'+title.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</div>'
    +'<div class="datum">Datum generisanja: '+datum+'</div>'
    +sectionsHtml
    +'<div class="disclaimer">Ovaj izve\u0161taj je generisan uz pomo\u0107 ve\u0161ta\u010dke inteligencije i slu\u017ei isklju\u010divo kao pomo\u0107no sredstvo u radu. Konsultujte originalni tekst propisa u Slu\u017ebenom glasniku RS. Nije pravni savet.</div>';

  // ── html2pdf download ─────────────────────────────────────────────────────
  if (typeof html2pdf !== 'undefined') {
    var container = document.createElement('div');
    container.style.cssText = 'position:fixed;top:-9999px;left:-9999px;width:794px;background:#fff;';
    container.innerHTML = bodyHtml;
    document.body.appendChild(container);
    html2pdf().set({
      margin: [15, 20, 15, 20],
      filename: fileName,
      image: { type: 'jpeg', quality: 0.98 },
      html2canvas: { scale: 2, useCORS: true, backgroundColor: '#ffffff' },
      jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
    }).from(container).save().then(function(){
      document.body.removeChild(container);
      btn.textContent = orig; btn.disabled = false;
      showToast('\u2713 PDF preuzet: ' + fileName, 'ok');
    }).catch(function(){
      document.body.removeChild(container);
      btn.textContent = orig; btn.disabled = false;
      showToast('Gre\u0161ka pri generisanju PDF-a.', 'err');
    });
    return;
  }

  // ── Fallback: Blob download kao HTML ako html2pdf nije učitan ────────────
  setTimeout(function(){
    var fullHtml = '<!DOCTYPE html><html lang="sr"><head><meta charset="UTF-8"><title>Vindex AI \u2014 Pravna analiza</title></head><body>'+bodyHtml+'</body></html>';
    var blob = new Blob([fullHtml], {type: 'text/html;charset=utf-8'});
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = fileName.replace('.pdf', '.html');
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    btn.textContent = orig; btn.disabled = false;
    showToast('Izve\u0161taj preuzet (HTML format \u2014 otvorite u browser-u i koristite Ctrl+P za PDF).', 'info');
  }, 100);
}

function copyToMarkdown(rawText, btn) {
  var sectionDefs = [
    {key:'KRATAK ZAKLJU\u010cAK (TL;DR):', lbl:'## \u26a1 TL;DR \u2014 Kratak zaklju\u010dak'},
    {key:'HIJERARHIJA IZVORA:', lbl:'## \u2696 Hijerarhija izvora'},
    {key:'PRAVNI ZAKLJU\u010cAK:', lbl:'## \u2696\ufe0f Pravni zaklju\u010dak'},
    {key:'ANALIZA \u0160TETE:', lbl:'## \u2696 Analiza \u0161tete'},
    {key:'CITAT ZAKONA:', lbl:'## \ud83d\udcd6 Citat zakona'},
    {key:'CITAT IZ ZAKONA:', lbl:'## \ud83d\udcd6 Citat zakona'},
    {key:'PRAVNI OSNOV:', lbl:'## Pravni osnov'},
    {key:'RIZICI I IZUZECI:', lbl:'## \u26a0\ufe0f Rizici i izuzeci'},
    {key:'KADA OVO NE VA\u017dI:', lbl:'## \ud83d\udccd Kada ovo ne va\u017ei'},
    {key:'PROCESNI KORACI:', lbl:'## \u26a1 Procesni koraci'},
    {key:'KLJU\u010cNO PITANJE:', lbl:'## \ud83c\udfaf Klju\u010dno pitanje'},
    {key:'DODATNA PITANJA:', lbl:'## \ud83d\udd0d Dodatna pitanja'},
    {key:'SLU\u017dBENI IZVOR:', lbl:'## Izvor'},
  ];
  var positions = sectionDefs.map(function(d){return{d:d,pos:rawText.indexOf(d.key)};}).filter(function(x){return x.pos!==-1;});
  positions.sort(function(a,b){return a.pos-b.pos;});
  var md = '';
  if (lastPitanje) md += '# Pravna analiza\n\n**Pitanje:** ' + lastPitanje + '\n\n---\n\n';
  positions.forEach(function(x,i){
    var start=x.pos+x.d.key.length;
    var end=i+1<positions.length?positions[i+1].pos:rawText.length;
    var val=rawText.slice(start,end).trim();
    md += x.d.lbl + '\n\n' + val + '\n\n';
  });
  md += '---\n*Generisano putem Vindex AI | Nije pravni savet | ' + new Date().toLocaleDateString('sr-Latn-RS') + '*';
  navigator.clipboard.writeText(md).then(function(){
    var orig=btn.textContent; btn.textContent='\u2713 Markdown kopiran!'; btn.disabled=true;
    setTimeout(function(){btn.textContent=orig;btn.disabled=false;},2000);
    showToast('Markdown format kopiran u clipboard.','ok');
  }).catch(function(){showToast('Gre\u0161ka pri kopiranju.','err');});
}

function openSettings() {
  var s = JSON.parse(localStorage.getItem('vindex_firma')||'{}');
  ['naziv','adresa','pib','kontakt'].forEach(function(k){
    var el=document.getElementById('s-'+k); if(el) el.value=s[k]||'';
  });
  document.getElementById('settings-modal').classList.add('open');
  if (currentSession) tarife_loadSettings();
}
function closeSettings() {
  document.getElementById('settings-modal').classList.remove('open');
}
function saveSettings() {
  var firma={};
  ['naziv','adresa','pib','kontakt'].forEach(function(k){
    var el=document.getElementById('s-'+k); if(el) firma[k]=el.value.trim();
  });
  localStorage.setItem('vindex_firma',JSON.stringify(firma));
  closeSettings();
  showToast('Pode\u0161avanja sa\u010duvana.','ok');
}

// \u2500\u2500 Tarife settings \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
function _tarifeHdr() {
  return {'Authorization': 'Bearer ' + currentSession.access_token, 'Content-Type': 'application/json'};
}
function _tarifeStatus(id, msg, ok) {
  var el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg;
  el.style.color = ok ? '#4ade80' : '#ff8080';
  setTimeout(function(){ el.textContent = ''; }, 3000);
}

async function tarife_loadSettings() {
  if (!currentSession) return;
  try {
    var r1 = await fetch(BASE_URL + '/api/tarife/moja-satnica', {headers: _tarifeHdr()});
    if (r1.ok) {
      var d1 = await r1.json();
      var inp = document.getElementById('s-satnica');
      if (inp) inp.value = d1.source === 'custom' ? d1.tarifa_po_satu : '';
    }
  } catch(e) {}
  try {
    var r2 = await fetch(BASE_URL + '/api/tarife/stavke', {headers: _tarifeHdr()});
    if (r2.ok) {
      var d2 = await r2.json();
      tarife_renderStavke(d2.stavke || []);
    }
  } catch(e) {
    var el = document.getElementById('s-stavke-lista');
    if (el) el.innerHTML = '<div style="padding:1rem;font-size:0.72rem;color:rgba(255,80,80,0.5);">Gre\u0161ka pri u\u010ditavanju.</div>';
  }
}

function tarife_renderStavke(stavke) {
  var el = document.getElementById('s-stavke-lista');
  if (!el || !stavke.length) return;
  el.innerHTML = stavke.map(function(s) {
    var resetBtn = s.is_custom
      ? '<button class="tarife-reset-btn" title="Vrati na AKS default" onclick="tarife_resetStavka(\''+s.sifra+'\')">&#x21BA;</button>'
      : '<span style="width:24px;display:inline-block;"></span>';
    return '<div class="tarife-stavka-row">'
      + '<span class="tarife-stavka-kod">'+escHtml(s.sifra)+'</span>'
      + '<span class="tarife-stavka-naziv" title="'+escHtml(s.naziv)+'">'+escHtml(s.naziv)+'</span>'
      + '<input type="number" class="tarife-stavka-iznos" step="50" min="0"'
      + ' value="'+s.iznos_rsd+'" placeholder="'+s.aks_iznos+'"'
      + ' data-sifra="'+s.sifra+'" data-aks="'+s.aks_iznos+'"'
      + ' onchange="tarife_saveStavka(\''+s.sifra+'\', this.value)">'
      + resetBtn
      + '</div>';
  }).join('');
}

async function tarife_saveSatnica() {
  if (!currentSession) return;
  var inp = document.getElementById('s-satnica');
  var val = inp ? parseFloat(inp.value) : NaN;
  if (!val || val <= 0) { _tarifeStatus('s-satnica-status', 'Unesite satnicu > 0', false); return; }
  try {
    var r = await fetch(BASE_URL + '/api/tarife/moja-satnica', {
      method: 'PUT', headers: _tarifeHdr(),
      body: JSON.stringify({tarifa_po_satu: val})
    });
    if (r.ok) _tarifeStatus('s-satnica-status', 'Satnica sa\u010duvana \u2714', true);
    else { var e=await r.json(); _tarifeStatus('s-satnica-status', e.detail||'Gre\u0161ka', false); }
  } catch(e) { _tarifeStatus('s-satnica-status', 'Gre\u0161ka mre\u017ee', false); }
}

async function tarife_saveStavka(sifra, iznos) {
  if (!currentSession) return;
  var val = parseFloat(iznos);
  if (isNaN(val) || val < 0) return;
  try {
    var r = await fetch(BASE_URL + '/api/tarife/stavke/' + sifra, {
      method: 'PUT', headers: _tarifeHdr(),
      body: JSON.stringify({iznos: val})
    });
    _tarifeStatus('s-stavke-status', r.ok ? sifra + ' sa\u010duvano \u2714' : 'Gre\u0161ka', r.ok);
    if (r.ok) tarife_loadSettings();
  } catch(e) { _tarifeStatus('s-stavke-status', 'Gre\u0161ka mre\u017ee', false); }
}

async function tarife_resetStavka(sifra) {
  if (!currentSession) return;
  try {
    var r = await fetch(BASE_URL + '/api/tarife/stavke/' + sifra, {
      method: 'PUT', headers: _tarifeHdr(),
      body: JSON.stringify({iznos: null, naziv: null})
    });
    _tarifeStatus('s-stavke-status', r.ok ? sifra + ' vra\u0107eno na AKS default \u2714' : 'Gre\u0161ka', r.ok);
    if (r.ok) tarife_loadSettings();
  } catch(e) { _tarifeStatus('s-stavke-status', 'Gre\u0161ka mre\u017ee', false); }
}

// \u2500\u2500 CRM klijent tarifa \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
async function crmUcitajTarifu(klijentId) {
  if (!currentSession) return;
  try {
    var r = await fetch(BASE_URL + '/api/tarife/klijent/' + klijentId, {headers: _tarifeHdr()});
    if (!r.ok) return;
    var d = await r.json();
    var inp = document.getElementById('crm-tarifa-input');
    var rmBtn = document.getElementById('crm-tarifa-rm-btn');
    var sec = document.getElementById('crm-tarifa-section');
    if (sec) sec.style.display = 'block';
    if (inp) inp.value = d.source === 'custom' ? d.tarifa_po_satu : '';
    if (rmBtn) rmBtn.style.display = d.source === 'custom' ? 'inline-block' : 'none';
  } catch(e) {}
}

async function crmSacuvajTarifu() {
  if (!currentSession || !crmAktivniId) return;
  var inp = document.getElementById('crm-tarifa-input');
  var val = inp ? parseFloat(inp.value) : NaN;
  if (!val || val <= 0) { _tarifeStatus('crm-tarifa-status', 'Unesite satnicu > 0', false); return; }
  try {
    var r = await fetch(BASE_URL + '/api/tarife/klijent/' + crmAktivniId, {
      method: 'PUT', headers: _tarifeHdr(),
      body: JSON.stringify({tarifa_po_satu: val})
    });
    if (r.ok) {
      _tarifeStatus('crm-tarifa-status', 'Tarifa sa\u010duvana \u2714', true);
      var rmBtn = document.getElementById('crm-tarifa-rm-btn');
      if (rmBtn) rmBtn.style.display = 'inline-block';
    } else {
      var e = await r.json();
      _tarifeStatus('crm-tarifa-status', e.detail||'Gre\u0161ka', false);
    }
  } catch(e) { _tarifeStatus('crm-tarifa-status', 'Gre\u0161ka mre\u017ee', false); }
}

async function crmUkloniTarifu() {
  if (!currentSession || !crmAktivniId) return;
  try {
    var r = await fetch(BASE_URL + '/api/tarife/klijent/' + crmAktivniId, {
      method: 'PUT', headers: _tarifeHdr(),
      body: JSON.stringify({tarifa_po_satu: null})
    });
    if (r.ok) {
      var inp = document.getElementById('crm-tarifa-input');
      var rmBtn = document.getElementById('crm-tarifa-rm-btn');
      if (inp) inp.value = '';
      if (rmBtn) rmBtn.style.display = 'none';
      _tarifeStatus('crm-tarifa-status', 'Override uklonjen \u2714', true);
    }
  } catch(e) { _tarifeStatus('crm-tarifa-status', 'Gre\u0161ka mre\u017ee', false); }
}

function focusInput() {
  var el = document.getElementById('qi') || document.getElementById('ni') || document.getElementById('aitxt');
  if (el) { el.focus(); el.scrollIntoView({behavior:'smooth', block:'center'}); }
}

function toggleCitat(id, btn) {
  var bq = document.getElementById(id);
  if (!bq) return;
  var expanded = bq.classList.contains('citat-expanded');
  if (expanded) {
    bq.classList.remove('citat-expanded');
    bq.classList.add('citat-collapsed');
    btn.textContent = 'Prikaži ceo tekst ▼';
  } else {
    bq.classList.remove('citat-collapsed');
    bq.classList.add('citat-expanded');
    btn.textContent = 'Sakrij ▲';
  }
}

var _followUpUsed = false;
function startFollowUp(btn) {
  if (_followUpUsed) {
    // Novo pitanje — resetuj sesiju
    newChat();
    _followUpUsed = false;
    if (btn) btn.textContent = '🔁 Follow-up';
    return;
  }
  var el = document.getElementById('qi');
  if (!el) return;
  var prefix = 'Na osnovu prethodnog odgovora, imam dodatno pitanje: ';
  el.value = prefix;
  el.focus();
  el.setSelectionRange(prefix.length, prefix.length);
  el.scrollIntoView({behavior:'smooth', block:'center'});
  _followUpUsed = true;
  if (btn) btn.textContent = 'Novo pitanje ↺';
}

/* EXEC */
var _execInProgress = false;
async function execQuery() {
  console.log('[Vindex] execQuery: korisnik =', currentUser ? currentUser.email : 'nije ulogovan', '| krediti =', userCredits);
  if (!currentUser) { openModal(); return; }
  if (userCredits <= 0) {
    console.warn('[Vindex] execQuery: blokiran — 0 kredita');
    showPaywall(); return;
  }
  if (_execInProgress) { console.warn('[Vindex] execQuery: blokiran — upit u toku'); return; }
  _execInProgress = true;

  var resp   = document.getElementById('resp');
  var rb     = document.getElementById('rb');
  var btnLbl = document.getElementById('btn-lbl');
  var execBtn = document.getElementById('exec-btn');
  var orig   = btnLbl.textContent;

  execBtn.disabled = true;
  if (window.micStopAll) micStopAll();
  btnLbl.textContent = activeTab === 'n' ? 'Generišem nacrt...' : 'Vindex AI pretražuje bazu...';
  console.log('[Vindex] execQuery: šaljem upit na', activeTab);
  var _trackFeature = {q:'pravno_istrazivanje',n:'drafting',a:'dokument',s:'sudska_praksa'}[activeTab]||activeTab;
  piTrack(_trackFeature,'query',{tab:activeTab});
  resp.classList.remove('show');
  document.getElementById('podnesak-preview').style.display='none';
  var _wfDiv = document.getElementById('analiza-workflow'); if (_wfDiv) _wfDiv.style.display='none';
  rb.style.whiteSpace = '';

  var currentPitanje = activeTab === 'q' ? document.getElementById('qi').value : '';
  lastPitanje = currentPitanje;
  var _selectedTip = (document.getElementById('podnesak-tip') || {}).value || '';
  var _nEndpoint = _NACRT_API_TYPES.has(_selectedTip) ? BASE_URL+'/api/nacrt' : BASE_URL+'/api/podnesak';
  if (activeTab === 's') {
    _execInProgress = false;
    execBtn.disabled = false;
    btnLbl.textContent = orig;
    return;
  }
  if (activeTab === 'a') {
    _execInProgress = false;
    execBtn.disabled = false;
    btnLbl.textContent = orig;
    if (_docSessionId) {
      doc_ask_question();
    } else {
      resp.classList.add('show'); rb.style.whiteSpace = 'pre-wrap';
      rb.textContent = 'Prvo otpremite dokument klikom na upload zonu.';
    }
    return;
  }
  var eps = { q:BASE_URL+'/api/pitanje', n:_nEndpoint, a:BASE_URL+'/api/analiza' };
  var _qBody = { pitanje: currentPitanje, history: conversationHistory.slice(-3) };
  if (activePredmetId) _qBody.predmet_id = activePredmetId;
  var bodies = {
    q: _qBody,
    n: (function(){
      var b = { vrsta: _selectedTip, tip: _selectedTip, opis: document.getElementById('podnesak-opis').value };
      var sn = (document.getElementById('podnesak-sud-naziv') || {}).value;
      var sa = (document.getElementById('podnesak-sud-adresa') || {}).value;
      if (sn) { b.sud_naziv = sn; b.sud_adresa = sa || ''; }
      return b;
    })(),
    a: { tekst: document.getElementById('aitxt').value, pitanje: document.getElementById('aq').value }
  };

  // ── CHECKLIST FAZA (samo za nacrt tab, pre generisanja) ──────────────────
  if (activeTab === 'n' && _selectedTip) {
    var _clOpisVal = (document.getElementById('podnesak-opis') || {}).value || '';
    if (_clOpisVal.trim().length >= 20) {
      try {
        btnLbl.textContent = 'Proveravam kompletnost...';
        var _clR = await fetch(BASE_URL + '/api/nacrti/checklist', {
          method: 'POST',
          headers: { 'Content-Type':'application/json', 'Authorization':'Bearer '+currentSession.access_token },
          body: JSON.stringify({ tip: _selectedTip, cinjenice: _clOpisVal })
        });
        if (_clR.ok) {
          var _clD = await _clR.json();
          if (_clD.blokira_nastavak && _clD.nedostajuci_kriticni && _clD.nedostajuci_kriticni.length) {
            // Kritični elementi nedostaju — prikaži upozorenje ali dozvoli nastavak
            var _clMsg = '⚠️ Checklist upozorenje — nedostaju obavezni elementi:\n\n'
              + _clD.nedostajuci_kriticni.map(function(n){ return '• ' + n; }).join('\n')
              + '\n\nPokrivenost: ' + _clD.procenat_pokrivenosti + '%'
              + '\n\nŽelite li ipak da generišete nacrt?';
            if (!confirm(_clMsg)) {
              execBtn.disabled = false;
              btnLbl.textContent = orig;
              _execInProgress = false;
              return;
            }
          }
        }
      } catch(_clErr) { /* ignoriši greške checklista — nastavi sa generisanjem */ }
    }
  }

  var _maxRetries = 2;
  var _attempt = 0;

  try {
    while (true) {
      var r = await fetch(eps[activeTab], {
        method:  'POST',
        headers: { 'Content-Type':'application/json', 'Authorization':'Bearer '+currentSession.access_token },
        body:    JSON.stringify(bodies[activeTab])
      });

      console.log('[Vindex] execQuery: odgovor status =', r.status, '| pokušaj', _attempt+1);

      // Cold-start / gateway retry
      if ((r.status === 502 || r.status === 503) && _attempt < _maxRetries) {
        _attempt++;
        btnLbl.textContent = 'Uspostavljanje veze sa serverom...';
        await new Promise(function(res){ setTimeout(res, 4000); });
        continue;
      }

      if (r.status === 401) { closeModal(); openModal(); return; }
      if (r.status === 402) {
        console.warn('[Vindex] execQuery: 402 — nema kredita');
        userCredits = 0; updateCreditDisplay(); showPaywall(); return;
      }
      if (r.status === 403) {
        console.warn('[Vindex] execQuery: 403 — nije PRO');
        openProUpgradeModal(); return;
      }

      // Content-type guard — server vratio HTML (cold start, nginx greška)
      var _ct = r.headers.get('content-type');
      if (!_ct || !_ct.includes('application/json')) {
        if (_attempt < _maxRetries) {
          _attempt++;
          btnLbl.textContent = 'Uspostavljanje veze sa serverom...';
          await new Promise(function(res){ setTimeout(res, 4000); });
          continue;
        }
        resp.classList.add('show'); rb.style.whiteSpace='pre-wrap';
        rb.textContent = 'Server se pokreće, pokušajte za 5 sekundi...';
        return;
      }

      var d = await r.json();
      console.log('[Vindex] execQuery: kredit posle upita =', d.credits_remaining);
      if (d.credits_remaining !== undefined) { userCredits = d.credits_remaining; updateCreditDisplay(); }
      _renderRagConfidence(d);

      var text = d.odgovor || d.greska || 'Greška u odgovoru servera.';

      // Sačuvaj u in-memory i Supabase history
      if (d.odgovor) {
        var turnQ = activeTab === 'q' ? currentPitanje : ('[' + activeTab + '] ' + (document.getElementById('podnesak-opis') ? document.getElementById('podnesak-opis').value : '').substring(0,120));
        if (activeTab === 'q' && currentPitanje) {
          conversationHistory.push({ q: currentPitanje, a: d.odgovor.substring(0, 600) });
          if (conversationHistory.length > 3) conversationHistory.shift();
        }
        saveTurnToSupabase(turnQ, d.odgovor);
        // Dodaj u history panel
        if (turnQ) {
          _chatHistoryRows.push({ role:'user', content: turnQ });
          _chatHistoryRows.push({ role:'assistant', content: d.odgovor.substring(0,600) });
          renderChatHistory(_chatHistoryRows);
        }
      }

      _lastRawText = text;
      if (activeTab === 'n') {
        // PREVIEW mode za generisani podnesak
        resp.classList.remove('show');
        var previewEl = document.getElementById('podnesak-preview');
        var previewBody = document.getElementById('podnesak-preview-body');
        var highlighted = escHtml(text).replace(/\[([A-ZŠĐČĆŽ\s\-—]+?)\s*—\s*POPUNITI\]/g,
          '<span class="popuniti">[$1 — POPUNITI]</span>');
        previewBody.innerHTML = highlighted;
        previewEl.style.display = 'block';
      } else {
        resp.classList.add('show'); rb.textContent=''; rb.style.whiteSpace='pre-wrap'; rb.classList.add('resp-cursor');
        var i=0, speed=text.length>600?4:text.length>300?7:12;
        var _tabAtSend = activeTab;
        var iv=setInterval(function(){
          if(i>=text.length){
            clearInterval(iv); rb.classList.remove('resp-cursor'); rb.style.whiteSpace='';
            _followUpUsed = false;
            if (_tabAtSend === 'a') {
              var richHtml = analizaRenderRezultat(text);
              rb.innerHTML = richHtml + _feedbackBar('', text);
              analizaPrikaziWorkflow(text);
              if (_cyrillicOn) cirilicaElement(rb);
            } else {
              var parsedHtml = formatResponse(text);
              console.log('[Vindex] RAW odgovor (500):', text.substring(0,500));
              console.log('[Vindex] PARSED html (500):', parsedHtml ? parsedHtml.substring(0,500) : 'PRAZAN!');
              if (!parsedHtml || parsedHtml.trim() === '') {
                rb.style.whiteSpace = 'pre-wrap';
                rb.textContent = text;
              } else {
                rb.innerHTML = parsedHtml + _feedbackBar(currentPitanje, text);
              }
              if (_cyrillicOn) cirilicaElement(rb);
            }
            // Auto-čitanje kada je pitanje postavljeno glasom
            if (window._vxLastInputWasVoice) {
              window._vxLastInputWasVoice = false;
              setTimeout(function() { vx_tts_speak(_vxLastResponseText || text); }, 400);
            }
          } else { rb.textContent+=text[i]; i++; }
        },speed);
      }
      break;
    }
  } catch(e) {
    resp.classList.add('show'); rb.style.whiteSpace='pre-wrap';
    rb.textContent = 'Došlo je do greške: '+(e.message||'API nije dostupan. Proverite internet vezu i pokušajte ponovo.');
  } finally {
    _execInProgress = false;
    execBtn.disabled = false;
    btnLbl.textContent = orig;
  }
}

function _renderRagConfidence(d) {
  var badge = document.getElementById('rag-confidence-badge');
  var src   = document.getElementById('rag-source-info');
  if (!badge || !src) return;
  var conf = d.confidence || '';
  if (!conf) { badge.style.display='none'; src.style.display='none'; return; }
  var map = { HIGH: { label:'Visoka relevantnost', bg:'rgba(34,197,94,.18)', color:'#4ade80', border:'rgba(34,197,94,.3)' },
              MEDIUM: { label:'Srednja relevantnost', bg:'rgba(251,191,36,.13)', color:'#fbbf24', border:'rgba(251,191,36,.3)' },
              LOW: { label:'Niska relevantnost', bg:'rgba(239,68,68,.13)', color:'#f87171', border:'rgba(239,68,68,.3)' } };
  var meta = map[conf.toUpperCase()] || map.MEDIUM;
  badge.textContent = meta.label;
  badge.style.cssText = 'display:inline-block;font-size:.65rem;font-weight:700;padding:.15rem .5rem;border-radius:4px;letter-spacing:.04em;background:'+meta.bg+';color:'+meta.color+';border:1px solid '+meta.border+';';
  var parts = [];
  if (d.top_law) parts.push(d.top_law);
  if (d.top_article) parts.push(d.top_article);
  if (d.top_score !== undefined) parts.push('skor: ' + Math.round(d.top_score * 100) + '%');
  if (parts.length) { src.textContent = 'Najrelevantniji izvor: ' + parts.join(' · '); src.style.display='block'; }
  else src.style.display = 'none';
}

function _feedbackBar(pitanje, odgovor) {
  var p = encodeURIComponent(pitanje||'').substring(0,500);
  var o = encodeURIComponent(odgovor||'').substring(0,1000);
  _vxLastResponseText = odgovor || '';  // sačuvaj za TTS dugme
  return '<div class="feedback-bar">'
    + '<button class="vx-tts-btn" id="vx-tts-play-btn" onclick="vx_tts_toggle()">🔊 Pročitaj</button>'
    + '<button class="feedback-btn" id="fb-btn" onclick="sendFeedback(this,\''+p+'\',\''+o+'\')">⚑ Prijavi netačan odgovor</button>'
    + '</div>';
}

// ── ANALIZA RICH RENDER ───────────────────────────────────────────────────────

var _poslednja_analiza_tekst = '';

function analizaRenderRezultat(tekst) {
  if (!tekst) return '<div class="analiza-plain">Nema rezultata.</div>';

  var sekcije = {};
  var sectionRegex = /## ([^\n]+)\n([\s\S]*?)(?=\n## |$)/g;
  var m;
  while ((m = sectionRegex.exec(tekst)) !== null) {
    sekcije[m[1].trim()] = m[2].trim();
  }

  if (Object.keys(sekcije).length === 0) {
    return '<div class="analiza-plain">' + tekst.replace(/\n/g, '<br>') + '</div>';
  }

  var html = '';

  // ── IZVRŠNI REZIME ──
  var rez = sekcije['IZVRŠNI REZIME'];
  if (rez) {
    var procenaM   = rez.match(/Procena uspeha:\s*([^\n]+)/i);
    var rasponM    = rez.match(/Raspon:\s*([^\n]+)/i);
    var pouzdM     = rez.match(/Pouzdanost procene:\s*([^\n]+)/i);
    var argumentM  = rez.match(/Najjači argument:\s*([^\n]+)/i);
    var rizikM     = rez.match(/Najveći rizik:\s*([^\n]+)/i);
    var dokazM     = rez.match(/Ključni dokaz:\s*([^\n]+)/i);
    var korakM     = rez.match(/Sledeći korak:\s*([^\n]+)/i);

    var procena    = procenaM   ? procenaM[1].trim()  : '';
    var raspon     = rasponM    ? rasponM[1].trim()   : '';
    var pouzdanost = pouzdM     ? pouzdM[1].trim()    : '';
    var argument   = argumentM  ? argumentM[1].trim() : '';
    var rizik      = rizikM     ? rizikM[1].trim()    : '';
    var dokaz      = dokazM     ? dokazM[1].trim()    : '';
    var korak      = korakM     ? korakM[1].trim()    : '';

    var bojaCls = procena.indexOf('VISOKA') !== -1 ? 'score-ok' :
                  procena.indexOf('SREDNJA') !== -1 ? 'score-warning' : 'score-danger';

    html += '<div class="analiza-rezime">';
    html += '<div class="analiza-rezime-header">🎯 Izvršni rezime</div>';
    html += '<div class="analiza-rezime-body"><div class="analiza-procena-wrap">';
    html += '<div class="analiza-procena-krug ' + bojaCls + '">';
    html += '<span class="analiza-procena-label">' + escHtml(procena) + '</span>';
    if (raspon) html += '<span class="analiza-procena-raspon">' + escHtml(raspon) + '</span>';
    if (pouzdanost) html += '<span class="analiza-procena-pouzdanost">pouzdanost: ' + escHtml(pouzdanost) + '</span>';
    html += '</div>';
    html += '<div class="analiza-rezime-polja">';
    if (argument) html += '<div class="analiza-rezime-polje"><span class="analiza-rezime-ikona">💪</span><div><strong>Najjači argument</strong><p>' + escHtml(argument) + '</p></div></div>';
    if (rizik)    html += '<div class="analiza-rezime-polje"><span class="analiza-rezime-ikona">⚠️</span><div><strong>Najveći rizik</strong><p>' + escHtml(rizik) + '</p></div></div>';
    if (dokaz)    html += '<div class="analiza-rezime-polje"><span class="analiza-rezime-ikona">🔑</span><div><strong>Ključni dokaz</strong><p>' + escHtml(dokaz) + '</p></div></div>';
    if (korak)    html += '<div class="analiza-rezime-polje analiza-sledeci-korak"><span class="analiza-rezime-ikona">➡️</span><div><strong>Sledeći korak</strong><p>' + escHtml(korak) + '</p></div></div>';
    html += '</div></div></div></div>';
  }

  // ── CRVENE ZASTAVICE ──
  var zast = sekcije['CRVENE ZASTAVICE'];
  if (zast) {
    var lines = zast.split('\n').filter(function(l){ return l.trim().indexOf('🚨') !== -1; });
    if (lines.length) {
      html += '<div class="analiza-sekcija analiza-zastavice-wrap"><div class="analiza-sekcija-naslov">🚨 Crvene zastavice</div>';
      lines.forEach(function(l){ html += '<div class="analiza-zastavica">' + escHtml(l.trim()) + '</div>'; });
      html += '</div>';
    }
  }

  // ── DOKAZ KOJI MENJA SVE ──
  var dkm = sekcije['DOKAZ KOJI MENJA SVE'];
  if (dkm) {
    html += '<div class="analiza-sekcija analiza-dokaz-wrap"><div class="analiza-sekcija-naslov">🔄 Dokaz koji menja sve</div>';
    html += '<div class="analiza-dokaz-body">' + escHtml(dkm).replace(/\n/g, '<br>') + '</div></div>';
  }

  // ── OSTALE SEKCIJE ──
  var ostale = ['PRAVNI OSNOV', 'ANALIZA PREDMETA', 'SLABOSTI I RIZICI', 'STRATEGIJA I PREPORUKE', 'HRONOLOGIJA'];
  ostale.forEach(function(naziv) {
    if (sekcije[naziv]) {
      html += '<div class="analiza-sekcija"><div class="analiza-sekcija-naslov">' + naziv + '</div>';
      html += '<div class="analiza-sekcija-body">' + escHtml(sekcije[naziv]).replace(/\n/g, '<br>') + '</div></div>';
    }
  });

  return html;
}

function analizaPrikaziWorkflow(tekst) {
  _poslednja_analiza_tekst = tekst || '';
  var wf = document.getElementById('analiza-workflow');
  if (wf) wf.style.display = 'block';
}

function _analizaSwitchTab(t) {
  var btn = document.querySelector('.t-tab[onclick*="\'' + t + '\'"]');
  if (btn) setTab(btn, t);
}

function analizaSacuvajUPredmet() {
  _analizaSwitchTab('p');
  setTimeout(function() {
    var btn = document.getElementById('pred-novi-btn') ||
              document.querySelector('[onclick*="predmetNovi"], [onclick*="noviPredmet"]');
    if (btn) btn.click();
  }, 300);
}

function analizaGenerisiNacrt() {
  _analizaSwitchTab('n');
  var nacrtInput = document.querySelector('#tab-n textarea');
  if (nacrtInput && _poslednja_analiza_tekst) {
    nacrtInput.value = _poslednja_analiza_tekst.substring(0, 500);
  }
}

function analizaDodajUStrategiju() {
  _analizaSwitchTab('t');
  var stratTekst = document.getElementById('strat-tekst');
  if (stratTekst && _poslednja_analiza_tekst) {
    stratTekst.value = _poslednja_analiza_tekst.substring(0, 1000);
    var chars = document.getElementById('strat-chars');
    if (chars) chars.textContent = stratTekst.value.length;
  }
}

function analizaKopiraj(btn) {
  if (!_poslednja_analiza_tekst) return;
  navigator.clipboard.writeText(_poslednja_analiza_tekst).then(function() {
    if (btn) { btn.textContent = '✓ Kopirano'; setTimeout(function(){ btn.textContent = '📋 Kopiraj analizu'; }, 2000); }
  }).catch(function() {
    if (btn) btn.textContent = '✗ Greška';
  });
}


async function sendFeedback(btn, pitanjeEnc, odgovorEnc) {
  if (!currentSession || !currentUser) { showToast('Morate biti prijavljeni da biste prijavili grešku.', 'err'); return; }
  btn.textContent = '\u0160aljem...'; btn.disabled = true;
  try {
    var sb = getSupabase();
    var pitanje = decodeURIComponent(pitanjeEnc);
    var odgovor = decodeURIComponent(odgovorEnc);
    if (sb) {
      await sb.from('reported_errors').insert({
        user_id:         currentUser.id,
        original_prompt: pitanje.substring(0, 4000),
        ai_response:     odgovor.substring(0, 8000),
        timestamp:       new Date().toISOString()
      });
    }
    // Šalji i hash na backend (bez sadržaja, za serverski log)
    fetch(BASE_URL + '/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type':'application/json', 'Authorization':'Bearer '+currentSession.access_token },
      body: JSON.stringify({ pitanje: pitanje, odgovor: odgovor, tip: 'greska' })
    }).catch(function(){});
    btn.textContent = '\u2713 Prijavljeno \u2014 hvala'; btn.classList.add('sent'); btn.disabled = true;
  } catch(e) {
    console.error('[Vindex] sendFeedback greška:', e);
    btn.textContent = '\u26d1 Prijavi neta\u010dan odgovor'; btn.disabled = false;
  }
}

/* DEMO TYPEWRITER */
var demoAns='PRAVNI OSNOV: Zakon o radu, član 179, stav 1, tačka 1; član 180; član 185\n\nODGOVOR: Poslodavac može otkazati ugovor o radu zbog povrede radne obaveze isključivo uz prethodno pisano upozorenje. Upozorenje mora sadržati opis povrede, rok za otklanjanje (ne kraći od 8 dana) i pouku da će biti otkazan ugovor ako povreda bude ponovljena ili nastavljena. Bez pisanog upozorenja rešenje o otkazu je nezakonito.\n\nCITAT IZ ZAKONA: \"Poslodavac može zaposlenom da otkaže ugovor o radu ako zaposleni ne poštuje radnu disciplinu propisanu aktom poslodavca, odnosno ako ne izvršava obaveze određene ugovorom o radu.\"\n\nPRAVNA POSLEDICA: Rešenje o otkazu mora biti u pisanoj formi, obrazloženo i uručeno zaposlenom lično. Zaposleni ima pravo na žalbu u roku od 8 dana od dana prijema. Otkaz bez prethodnog pisanog upozorenja sud će poništiti kao nezakonit.\n\nPOUZDANOST: 82% — Čl. 179 i 185 ZOR direktno pokrivaju uslove i formu otkaza. Konkretna procena zavisna od okolnosti slučaja.\n\nSLUŽBENI IZVOR: Zakon o radu (Sl. glasnik RS, br. 24/2005, 61/2005, 54/2009, 32/2013, 75/2014, 13/2017, 113/2017, 95/2018)';
var dStarted=false;
var dObs=new IntersectionObserver(function(entries){if(entries[0].isIntersecting&&!dStarted){dStarted=true;var el=document.getElementById('demoTxt');if(!el)return;var i=0;el.textContent='';el.classList.add('resp-cursor');var conf=document.getElementById('demoConf');var iv=setInterval(function(){if(i>=demoAns.length){clearInterval(iv);el.classList.remove('resp-cursor');if(conf)conf.classList.add('show');}else{el.textContent=demoAns.slice(0,++i);}},14);}},{threshold:0.4});
var demSec=document.getElementById('demo');if(demSec)dObs.observe(demSec);

/* PRICING TOGGLE */
var annual=false;
function _setPrices(){
  var p1=document.getElementById('p1'),pp1=document.getElementById('pp1');
  var p2=document.getElementById('p2'),pp2=document.getElementById('pp2');
  if(annual){
    if(p1)p1.textContent='€17';if(pp1)pp1.textContent='/mesec, godišnje';
    if(p2)p2.textContent='€35';if(pp2)pp2.textContent='/mesec, godišnje';
  }else{
    if(p1)p1.textContent='€19';if(pp1)pp1.textContent='/mesec';
    if(p2)p2.textContent='€39';if(pp2)pp2.textContent='/mesec';
  }
}
function toggleAnnual(){annual=!annual;document.getElementById('tog').classList.toggle('on',annual);_setPrices();}

/* PRICING MODAL */
function openProModal() {
  document.getElementById('pro-modal').classList.add('open');
}
function closeProModal() {
  document.getElementById('pro-modal').classList.remove('open');
}
async function pricing_kontakt(plan) {
  var labels = { solo: 'Solo', pro: 'PRO', kancelarija: 'Kancelarija' };
  var emails = { solo: 'Počnite besplatno', pro: 'Aktivirajte PRO', kancelarija: 'Kontaktirajte nas' };
  var subject = encodeURIComponent('Vindex AI ' + (labels[plan] || plan) + ' plan');
  var body = encodeURIComponent('Zdravo,\n\nZainteresovan sam za ' + (labels[plan] || plan) + ' plan.\n\nMoje ime: \nBroj advokata: \nBroj korisnika: ');
  try {
    if (currentSession) {
      await fetch(BASE_URL + '/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type':'application/json', 'Authorization':'Bearer '+currentSession.access_token },
        body: JSON.stringify({ pitanje: 'PRICING_INTEREST: ' + plan, odgovor: '', tip: 'ostalo' })
      });
    }
  } catch(e) {}
  window.open('mailto:kontakt@vindex.ai?subject=' + subject + '&body=' + body);
  if (plan !== 'kancelarija') {
    closeProModal();
    showToast('Otvoren je vaš email klijent. Pošaljite nam poruku i aktiviraćemo vaš plan!');
  }
}

/* NAV SCROLL */
window.addEventListener('scroll',function(){var _n=document.getElementById('nav');if(_n)_n.classList.toggle('scrolled',scrollY>60);});

/* MODAL CLOSE ON BACKDROP */
(function(){
  var _am=document.getElementById('auth-modal'); if(_am) _am.addEventListener('click',function(e){if(e.target===this)closeModal();});
  var _pm=document.getElementById('paywall-modal'); if(_pm) _pm.addEventListener('click',function(e){if(e.target===this)closePaywall();});
  var _pr=document.getElementById('pro-modal'); if(_pr) _pr.addEventListener('click',function(e){if(e.target===this)closeProModal();});
})();

/* INIT */
window.addEventListener('DOMContentLoaded', function() {
  initChatSession();
  initAuth();
  _setPrices();
  document.getElementById('pred-list').addEventListener('click', function(e) {
    var item = e.target.closest('[data-predmet-id]');
    if (item) pred_select(item.getAttribute('data-predmet-id'));
  });
  document.getElementById('pred-istorija-list').addEventListener('click', function(e) {
    if (e.target.closest('.pred-tl-result')) return;
    var item = e.target.closest('[data-istor-idx]');
    if (!item) return;
    var hintDiv = item.querySelector('.pred-tl-hint');
    var resDiv  = item.querySelector('.pred-tl-result');
    if (resDiv) {
      var isOpen = resDiv.style.display !== 'none';
      resDiv.style.display = isOpen ? 'none' : 'block';
      if (hintDiv) hintDiv.textContent = isOpen ? 'Klikni za prikaz analize ▾' : 'Sakrij analizu ▴';
      return;
    }
    var idx = parseInt(item.getAttribute('data-istor-idx'), 10);
    var h = _predIstorijaData[idx];
    if (!h || !h.odgovor || !h.odgovor.trim()) return;
    var rndr = (h.odgovor.indexOf('1. REZIME PRESUDE') !== -1) ? pred_renderPresuda : pred_renderProcena;
    resDiv = document.createElement('div');
    resDiv.className = 'pred-tl-result';
    resDiv.innerHTML = rndr(h.odgovor);
    item.appendChild(resDiv);
    if (hintDiv) hintDiv.textContent = 'Sakrij analizu ▴';
  });
  // Supabase šalje recovery token kao URL hash fragment: #access_token=...&type=recovery
  var hash = window.location.hash;
  if (hash.indexOf('type=recovery') !== -1) {
    openModal();
    setAuthMode('reset');
  } else if (hash === '#register') {
    openModal();
    setAuthMode('register');
    history.replaceState(null, '', '/app');
  } else if (hash === '#login') {
    openModal();
    setAuthMode('login');
    history.replaceState(null, '', '/app');
  }

  // .terminal ima backdrop-filter:blur(20px) koja kreira containing block za position:fixed,
  // što znači da se overlay-i pozicioniraju relativno prema .terminal (ne viewport-u) i
  // bivaju klipovani od .terminal{overflow:hidden}. Fix: premesti ih na document.body.
  ['intake-overlay', 'crm-overlay', 'crm-conflict-overlay'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el && el.parentElement !== document.body) {
      document.body.appendChild(el);
    }
  });

  // Hash-based subtab navigation (Faza 2)
  window.addEventListener('popstate', function() {
    if (!activePredmetId) return;
    var h = window.location.hash.replace('#', '');
    var VPANES = ['pregled','dokumenti','ai-analiza','strategija','rokovi','naplata','komunikacija'];
    if (VPANES.indexOf(h) > -1) pred_subtabSwitch(h);
  });
});

/* ── SUDSKA PRAKSA ──────────────────────────────────────────────────────── */
var praksa_initialized = false;
var praksa_total = 0;
var praksa_offset = 0;
var praksa_limit = 10;
var praksa_last_req = {};

function praksa_show_state(state) {
  document.getElementById('praksa-loading').style.display        = state === 'loading' ? 'block' : 'none';
  document.getElementById('praksa-error').style.display          = state === 'error'   ? 'block' : 'none';
  document.getElementById('praksa-empty').style.display          = state === 'empty'   ? 'block' : 'none';
  document.getElementById('praksa-results-header').style.display = state === 'results' ? 'block' : 'none';
  document.getElementById('praksa-load-more').style.display      = 'none';
}

function praksa_render_card(d, idx) {
  var mBg  = { 'Građanska':'rgba(74,168,255,0.12)', 'Zaštita prava':'rgba(74,222,128,0.10)', 'Upravna':'rgba(240,180,41,0.10)', 'Krivična':'rgba(255,100,100,0.10)' };
  var mClr = { 'Građanska':'#4aa8ff', 'Zaštita prava':'#4ade80', 'Upravna':'#f0b429', 'Krivična':'rgba(255,140,140,0.9)' };
  var bg   = mBg[d.matter]  || 'rgba(255,255,255,0.06)';
  var clr  = mClr[d.matter] || 'rgba(255,255,255,0.45)';
  var esc = function(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); };
  var preview  = d.izreka_preview ? esc(d.izreka_preview) : '';
  var dateStr  = d.decision_date ? (d.decision_date+'').substring(0,10) : '';
  var expandId = 'praksa-expand-' + idx;
  var hasDetail = !!(d.izreka_full || d.obrazlozenje_full);
  var safeDn   = esc(d.decision_number);
  var jsDn     = (d.decision_number||'').replace(/\\/g,'\\\\').replace(/'/g,"\\'");
  var jsCourt  = (d.court||'').replace(/\\/g,'\\\\').replace(/'/g,"\\'");
  var h = '<div style="background:rgba(74,168,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:0.85rem 1rem;">';
  h += '<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:0.5rem;margin-bottom:0.45rem;">';
  h += '<span style="font-family:JetBrains Mono,monospace;font-size:0.74rem;font-weight:500;color:rgba(255,255,255,0.85);">' + safeDn + '</span>';
  h += '<span style="flex-shrink:0;padding:0.14rem 0.55rem;border-radius:999px;font-family:JetBrains Mono,monospace;font-size:0.55rem;letter-spacing:0.1em;background:' + bg + ';color:' + clr + ';">' + esc(d.matter) + '</span>';
  h += '</div>';
  h += '<div style="display:flex;gap:0.8rem;margin-bottom:0.5rem;flex-wrap:wrap;">';
  if (d.court) h += '<span style="font-family:JetBrains Mono,monospace;font-size:0.58rem;color:rgba(255,255,255,0.30);">' + esc(d.court) + '</span>';
  if (dateStr) h += '<span style="font-family:JetBrains Mono,monospace;font-size:0.58rem;color:rgba(255,255,255,0.25);">' + dateStr + '</span>';
  h += '</div>';
  if (preview) {
    h += '<div style="font-family:var(--font-serif);font-size:0.82rem;color:rgba(255,255,255,0.54);line-height:1.68;margin-bottom:0.5rem;letter-spacing:0.01em;">' + preview + (d.izreka_full && d.izreka_full.length > 200 ? '…' : '') + '</div>';
  }
  h += '<div class="ratio-box" id="ratio-' + idx + '" data-dn="' + esc(d.decision_number) + '" style="display:block">';
  h += '<div class="ratio-lbl">Pravni stav suda</div>';
  h += '<div class="ratio-text ratio-loading" id="ratio-text-' + idx + '">Učitavanje pravnog stava…</div>';
  h += '</div>';
  h += '<div style="display:flex;gap:0.45rem;flex-wrap:wrap;">';
  if (hasDetail) {
    h += '<button id="praksa-expand-btn-' + idx + '" onclick="praksa_expand_decision(' + idx + ')" style="padding:0.25rem 0.7rem;background:rgba(74,168,255,0.08);border:1px solid rgba(74,168,255,0.18);border-radius:6px;color:#4aa8ff;font-family:var(--font-ui);font-size:0.71rem;cursor:pointer;">▾ Prikaži odluku</button>';
  }
  h += '<button onclick="praksa_copy_citation(\'' + jsDn + '\',\'' + dateStr + '\',\'' + jsCourt + '\')" style="padding:0.25rem 0.7rem;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:6px;color:rgba(255,255,255,0.38);font-family:var(--font-ui);font-size:0.71rem;cursor:pointer;">Kopiraj citiranje</button>';
  h += '<label class="vx-compare-checkbox" data-odluka-id="' + safeDn + '" data-odluka-naziv="' + safeDn + '">';
  h += '<input type="checkbox" class="compare-check" value="' + safeDn + '">';
  h += '<span>Uporedi</span></label>';
  h += '</div>';
  if (hasDetail) {
    h += '<div id="' + expandId + '" style="display:none;margin-top:0.7rem;padding-top:0.7rem;border-top:1px solid rgba(255,255,255,0.06);">';
    if (d.izreka_full) {
      h += '<div style="font-family:JetBrains Mono,monospace;font-size:0.51rem;letter-spacing:0.18em;text-transform:uppercase;color:rgba(74,168,255,0.5);margin-bottom:0.3rem;">Izreka</div>';
      h += '<div style="font-family:var(--font-serif);font-size:0.84rem;color:rgba(255,255,255,0.72);line-height:1.75;margin-bottom:0.75rem;white-space:pre-wrap;letter-spacing:0.01em;">' + esc(d.izreka_full) + '</div>';
    }
    if (d.obrazlozenje_full) {
      h += '<div style="font-family:JetBrains Mono,monospace;font-size:0.51rem;letter-spacing:0.18em;text-transform:uppercase;color:rgba(74,168,255,0.5);margin-bottom:0.3rem;">Obrazloženje</div>';
      h += '<div style="font-family:var(--font-serif);font-size:0.82rem;color:rgba(255,255,255,0.62);line-height:1.72;white-space:pre-wrap;letter-spacing:0.01em;">' + esc(d.obrazlozenje_full) + '</div>';
    }
    h += '</div>';
  }
  h += '</div>';
  return h;
}

function praksa_render_results(decisions, append) {
  var list = document.getElementById('praksa-list');
  if (!append) list.innerHTML = '';
  var base = append ? list.children.length : 0;
  decisions.forEach(function(d, i) {
    var w = document.createElement('div');
    w.style.marginBottom = '0.55rem';
    w.innerHTML = praksa_render_card(d, base + i);
    list.appendChild(w);
  });
  // Phase 3.2: async ratio fetch for newly rendered decisions
  praksa_fetch_ratios(decisions, base);
  // Show ratio filter input once we have results
  document.getElementById('praksa-ratio-filter').style.display = 'block';
}

function praksa_expand_decision(idx) {
  var el  = document.getElementById('praksa-expand-' + idx);
  var btn = document.getElementById('praksa-expand-btn-' + idx);
  if (!el) return;
  var open = el.style.display !== 'none';
  el.style.display = open ? 'none' : 'block';
  if (btn) btn.innerHTML = open ? '▾ Prikaži odluku' : '▴ Sakrij odluku';
}

function praksa_copy_citation(dn, date, court) {
  var text = dn + (court ? ', ' + court : '') + (date ? ', ' + date : '');
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function() { showToast('Citiranje kopirano'); }).catch(function(){});
  } else {
    var ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); showToast('Citiranje kopirano'); } catch(e) {}
    document.body.removeChild(ta);
  }
}

function praksa_reset_filters() {
  document.getElementById('praksa-query').value = '';
  document.getElementById('praksa-matter').value = '';
  document.getElementById('praksa-court').value = '';
  document.getElementById('praksa-year-from').value = '';
  document.getElementById('praksa-year-to').value = '';
}

async function praksa_search() {
  var q      = (document.getElementById('praksa-query').value || '').trim();
  var matter = document.getElementById('praksa-matter').value;
  var court  = document.getElementById('praksa-court').value;
  var yfrom  = document.getElementById('praksa-year-from').value;
  var yto    = document.getElementById('praksa-year-to').value;
  praksa_offset   = 0;
  praksa_last_req = { query: q || null, matter: matter || null, court: court || null,
    year_from: yfrom ? parseInt(yfrom) : null, year_to: yto ? parseInt(yto) : null };
  praksa_show_state('loading');
  document.getElementById('praksa-list').innerHTML = '';
  var body = { limit: praksa_limit, offset: 0 };
  if (praksa_last_req.query)     body.query     = praksa_last_req.query;
  if (praksa_last_req.matter)    body.matter    = praksa_last_req.matter;
  if (praksa_last_req.court)     body.court     = praksa_last_req.court;
  if (praksa_last_req.year_from) body.year_from = praksa_last_req.year_from;
  if (praksa_last_req.year_to)   body.year_to   = praksa_last_req.year_to;
  try {
    var r = await fetch(BASE_URL + '/api/praksa/search', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    });
    if (!r.ok) {
      var ed = {}; try { ed = await r.json(); } catch(e) {}
      document.getElementById('praksa-error').textContent = ed.error || ('Greška servera: ' + r.status);
      praksa_show_state('error'); return;
    }
    var data = await r.json();
    praksa_total  = data.total || 0;
    praksa_offset = (data.decisions || []).length;
    if (praksa_total === 0 || !data.decisions || data.decisions.length === 0) {
      praksa_show_state('empty'); return;
    }
    praksa_show_state('results');
    document.getElementById('praksa-results-count').textContent = praksa_total + ' odluka pronađeno';
    praksa_render_results(data.decisions, false);
    document.getElementById('praksa-load-more').style.display = praksa_offset < praksa_total ? 'block' : 'none';
  } catch(e) {
    document.getElementById('praksa-error').textContent = 'Greška pri povezivanju sa serverom.';
    praksa_show_state('error');
  }
}

async function praksa_load_more() {
  var body = { limit: praksa_limit, offset: praksa_offset };
  if (praksa_last_req.query)     body.query     = praksa_last_req.query;
  if (praksa_last_req.matter)    body.matter    = praksa_last_req.matter;
  if (praksa_last_req.court)     body.court     = praksa_last_req.court;
  if (praksa_last_req.year_from) body.year_from = praksa_last_req.year_from;
  if (praksa_last_req.year_to)   body.year_to   = praksa_last_req.year_to;
  var btn = document.getElementById('praksa-load-more');
  btn.textContent = 'Učitavam…'; btn.disabled = true;
  try {
    var r = await fetch(BASE_URL + '/api/praksa/search', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    });
    if (r.ok) {
      var data = await r.json();
      if (data.decisions && data.decisions.length > 0) {
        praksa_render_results(data.decisions, true);
        praksa_offset += data.decisions.length;
      }
    }
  } catch(e) {}
  btn.textContent = 'Učitaj još odluka'; btn.disabled = false;
  btn.style.display = praksa_offset < praksa_total ? 'block' : 'none';
}

function praksa_load_initial() {
  if (praksa_initialized) return;
  praksa_initialized = true;
  praksa_search();
}

/* ── Phase 3.3: Upoređivanje presuda A vs B ──────────────────────────────── */
var compareSelection = []; // max 2 items [{id, naziv}]

document.addEventListener('change', function(e) {
  if (!e.target.classList.contains('compare-check')) return;
  var id    = e.target.value;
  var label = e.target.closest('.vx-compare-checkbox');
  var naziv = label ? (label.dataset.odlukaNaziv || id) : id;
  if (e.target.checked) {
    if (compareSelection.length >= 2) {
      e.target.checked = false;
      showToast('Možete odabrati maksimalno 2 presude za poređenje.', 'err');
      return;
    }
    compareSelection.push({ id: id, naziv: naziv });
  } else {
    compareSelection = compareSelection.filter(function(x) { return x.id !== id; });
  }
  updateCompareBar();
});

function updateCompareBar() {
  var bar   = document.getElementById('compare-bar');
  var cnt   = document.getElementById('compare-count');
  var names = document.getElementById('compare-names');
  var btn   = document.getElementById('btn-start-compare');
  if (!bar) return;
  if (compareSelection.length === 0) {
    bar.classList.add('hidden');
    return;
  }
  bar.classList.remove('hidden');
  cnt.textContent = compareSelection.length;
  names.textContent = compareSelection.map(function(x) { return x.naziv; }).join(' vs ');
  btn.disabled = compareSelection.length < 2;
}

function clearCompare() {
  compareSelection = [];
  document.querySelectorAll('.compare-check:checked').forEach(function(cb) { cb.checked = false; });
  updateCompareBar();
}

function openCompareModal() {
  document.getElementById('compare-modal').classList.remove('hidden');
}

function closeCompareModal() {
  document.getElementById('compare-modal').classList.add('hidden');
  document.getElementById('compare-result').innerHTML = '';
  document.getElementById('compare-loading').classList.add('hidden');
  document.getElementById('modal-tag-a').textContent = '—';
  document.getElementById('modal-tag-b').textContent = '—';
}

function _showCompareLoading(a, b) {
  document.getElementById('modal-tag-a').textContent = a || '—';
  document.getElementById('modal-tag-b').textContent = b || '—';
  document.getElementById('compare-loading').classList.remove('hidden');
  document.getElementById('compare-result').innerHTML = '';
}

function _hideCompareLoading() {
  document.getElementById('compare-loading').classList.add('hidden');
}

function _compareMarkdownToHtml(md) {
  if (!md) return '';
  var html = md
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^### (.+)$/gm, '<h2>$1</h2>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br>');
  return '<p>' + html + '</p>';
}

function _renderCompareResult(data) {
  document.getElementById('modal-tag-a').textContent = (data.odluka_a && data.odluka_a.broj) || '—';
  document.getElementById('modal-tag-b').textContent = (data.odluka_b && data.odluka_b.broj) || '—';
  document.getElementById('compare-result').innerHTML = _compareMarkdownToHtml(data.analiza || '');
  _hideCompareLoading();
}

function _showCompareError(msg) {
  _hideCompareLoading();
  document.getElementById('compare-result').innerHTML = '<div class="compare-error">' + (msg || 'Greška.') + '</div>';
}

async function _doCompare(dnA, dnB) {
  if (!currentSession) { openModal(); return; }
  openCompareModal();
  _showCompareLoading(dnA, dnB);
  try {
    var r = await fetch(BASE_URL + '/api/praksa/uporedi', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + currentSession.access_token },
      body: JSON.stringify({ odluka_a: dnA, odluka_b: dnB }),
    });
    var data = await r.json();
    if (data.error) { _showCompareError(data.error); return; }
    _renderCompareResult(data);
  } catch(e) {
    _showCompareError('Greška pri komunikaciji sa serverom.');
  }
}

function startCompare() {
  if (compareSelection.length !== 2) return;
  _doCompare(compareSelection[0].id, compareSelection[1].id);
}

function startManualCompare() {
  var a = (document.getElementById('manual-a').value || '').trim();
  var b = (document.getElementById('manual-b').value || '').trim();
  if (!a || !b) { showToast('Unesite oba broja odluke.', 'err'); return; }
  if (a.toLowerCase() === b.toLowerCase()) { showToast('Odaberite dve različite odluke.', 'err'); return; }
  _doCompare(a, b);
}

/* ── Phase 3.2: Ratio decidendi — fetch + fill + filter ──────────────────── */
async function praksa_fetch_ratios(decisions, startIdx) {
  if (!decisions || !decisions.length) return;
  var payload = decisions.map(function(d, i) {
    var text = (d.obrazlozenje_full || d.izreka_full || d.obraz_text || d.izreka_preview || '').substring(0, 3000);
    return { decision_number: d.decision_number, text: text, _idx: startIdx + i };
  }).filter(function(p) { return p.decision_number; });
  if (!payload.length) return;
  var dnToIdx = {};
  payload.forEach(function(p) { dnToIdx[p.decision_number] = p._idx; });
  var _setRatio = function(idx, ratio) {
    var box = document.getElementById('ratio-' + idx);
    var txt = document.getElementById('ratio-text-' + idx);
    if (!box || !txt) return;
    if (ratio === '__IZREKA_ONLY__') {
      txt.className = 'ratio-text ratio-loading';
      txt.textContent = 'Presuda sadrži samo izreku bez obrazloženja.';
    } else if (ratio) {
      txt.className = 'ratio-text';
      txt.textContent = ratio;
    } else {
      txt.className = 'ratio-text ratio-loading';
      txt.textContent = 'Pravni stav nije utvrđen iz dostavljenog teksta.';
    }
  };
  try {
    var r = await fetch(BASE_URL + '/api/praksa/ratio', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decisions: payload.map(function(p) {
        return { decision_number: p.decision_number, text: p.text };
      }) }),
    });
    if (!r.ok) {
      console.error('[ratio] HTTP ' + r.status);
      payload.forEach(function(p) { _setRatio(p._idx, null); });
      return;
    }
    var data = await r.json();
    var ratios = data.ratios || {};
    payload.forEach(function(p) { _setRatio(p._idx, ratios[p.decision_number] || null); });
  } catch(e) {
    console.error('[ratio] fetch error:', e);
    payload.forEach(function(p) { _setRatio(p._idx, null); });
  }
}

function praksa_ratio_filter_update() {
  var q = (document.getElementById('praksa-ratio-filter').value || '').trim().toLowerCase();
  [document.getElementById('praksa-list'), document.getElementById('praksa-grupisano-container')].forEach(function(container) {
    if (!container) return;
    container.querySelectorAll('[data-dn]').forEach(function(box) {
      // grupisano: ratio-box → .pg-decision-card
      // regular list: ratio-box → inner card div → outer wrapper w
      var card = box.closest('.pg-decision-card') || (box.parentElement && box.parentElement.parentElement);
      if (!card) return;
      if (!q) { card.style.display = ''; return; }
      var ratioEl = box.querySelector('.ratio-text');
      var ratioText = ratioEl ? (ratioEl.textContent || '').toLowerCase() : '';
      var dnText = (box.getAttribute('data-dn') || '').toLowerCase();
      card.style.display = (ratioText.indexOf(q) !== -1 || dnText.indexOf(q) !== -1) ? '' : 'none';
    });
  });
}

/* ── Phase 3.1: Grupisanje Za/Protiv ─────────────────────────────────────── */
async function praksa_load_grupisano() {
  var q = (document.getElementById('praksa-query').value || '').trim();
  if (!q) {
    document.getElementById('praksa-error').textContent = 'Unesite upit za grupisanu analizu.';
    praksa_show_state('error');
    return;
  }
  document.getElementById('praksa-grupisano-container').style.display = 'none';
  document.getElementById('praksa-grupisano-loading').style.display = 'block';
  document.getElementById('praksa-list').innerHTML = '';
  praksa_show_state('loading');
  var btn = document.getElementById('praksa-grupisano-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Analiziram…'; }
  try {
    var r = await fetch(BASE_URL + '/api/sudska-praksa/grupisano?query=' + encodeURIComponent(q));
    document.getElementById('praksa-grupisano-loading').style.display = 'none';
    if (!r.ok) {
      var ed = {}; try { ed = await r.json(); } catch(e) {}
      document.getElementById('praksa-error').textContent = ed.error || ('Greška servera: ' + r.status);
      praksa_show_state('error');
      return;
    }
    var data = await r.json();
    if (!data.total) { praksa_show_state('empty'); return; }
    praksa_show_state('results');
    document.getElementById('praksa-results-count').textContent = data.total + ' odluka analizirano';
    praksa_render_grupisano(data);
  } catch(e) {
    document.getElementById('praksa-grupisano-loading').style.display = 'none';
    document.getElementById('praksa-error').textContent = 'Greška pri povezivanju sa serverom.';
    praksa_show_state('error');
  }
  if (btn) { btn.disabled = false; btn.textContent = 'Za/Protiv'; }
}

function praksa_render_grupisano(data) {
  var s = data.statistika || {};
  var total = data.total || 1;
  var esc = function(v) { return (v||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); };

  var pTuzilac  = s.pct_tuzilac  || 0;
  var pTuzeni   = s.pct_tuzeni   || 0;
  var pMesovito = total > 0 ? Math.round(100 * (s.mesovito||0) / total * 10) / 10 : 0;
  var pNepoz    = total > 0 ? Math.round(100 * (s.nepoznato||0) / total * 10) / 10 : 0;

  var h = '';
  // Score row
  h += '<div class="pg-score-row">';
  h += '<span class="pg-score-item pg-score-tuzilac">▲ Za tužioca: ' + (s.tuzilac||0) + ' (' + pTuzilac + '%)</span>';
  h += '<span class="pg-score-item pg-score-tuzeni">▼ Za tuženog: ' + (s.tuzeni||0) + ' (' + pTuzeni + '%)</span>';
  if (s.mesovito) h += '<span class="pg-score-item pg-score-mesovito">≈ Mešovito: ' + s.mesovito + '</span>';
  if (s.nepoznato) h += '<span class="pg-score-item pg-score-nepoznato">? Nepoznato: ' + s.nepoznato + '</span>';
  h += '</div>';
  // Progress bar
  h += '<div class="pg-stat-bar">';
  if (pTuzilac > 0)  h += '<div class="pg-stat-tuzilac"  style="width:' + pTuzilac  + '%"></div>';
  if (pTuzeni > 0)   h += '<div class="pg-stat-tuzeni"   style="width:' + pTuzeni   + '%"></div>';
  if (pMesovito > 0) h += '<div class="pg-stat-mesovito" style="width:' + pMesovito + '%"></div>';
  if (pNepoz > 0)    h += '<div class="pg-stat-nepoznato" style="width:' + pNepoz   + '%"></div>';
  h += '</div>';

  // Groups
  var groups = [
    { key:'tuzilac', lbl:'Za tužioca — usvojen zahtev', icon:'✅', hdrCls:'pg-group-tuzilac', lblCls:'pg-group-lbl-tuzilac' },
    { key:'tuzeni',  lbl:'Za tuženog — odbijen zahtev',  icon:'❌', hdrCls:'pg-group-tuzeni',  lblCls:'pg-group-lbl-tuzeni'  },
    { key:'mesovito',lbl:'Mešovit ishod',                icon:'≈',  hdrCls:'pg-group-mesovito',lblCls:'pg-group-lbl-mesovito'},
    { key:'nepoznato',lbl:'Ishod neodređen',             icon:'?',  hdrCls:'pg-group-nepoznato',lblCls:'pg-group-lbl-nepoznato'},
  ];
  var grupe = data.grupe || {};
  var allDecisions = [];
  var ratioIdx = 0;
  groups.forEach(function(g) {
    var decisions = grupe[g.key] || [];
    if (!decisions.length) return;
    var gid = 'pg-group-body-' + g.key;
    h += '<div style="margin-bottom:0.5rem;">';
    h += '<div class="pg-group-header ' + g.hdrCls + '" onclick="var el=document.getElementById(\'' + gid + '\');el.style.display=el.style.display===\'none\'?\'block\':\'none\';">';
    h += '<span class="' + g.lblCls + '">' + g.icon + ' ' + g.lbl + '</span>';
    h += '<span class="pg-group-count">' + decisions.length + ' odluka ▾</span>';
    h += '</div>';
    h += '<div id="' + gid + '" style="padding:0.4rem 0;">';
    decisions.forEach(function(d) {
      var dateStr = d.decision_date ? (d.decision_date+'').substring(0,10) : '';
      var rid = 'g' + ratioIdx;
      h += '<div class="pg-decision-card">';
      h += '<div class="pg-decision-dn">' + esc(d.decision_number) + '</div>';
      h += '<div class="pg-decision-meta">' + esc(d.court) + (dateStr ? ' · ' + dateStr : '') + (d.matter ? ' · ' + esc(d.matter) : '') + '</div>';
      if (d.izreka_preview) h += '<div class="pg-decision-preview">' + esc(d.izreka_preview) + (d.izreka_preview.length >= 200 ? '…' : '') + '</div>';
      h += '<div class="ratio-box" id="ratio-' + rid + '" data-dn="' + esc(d.decision_number) + '" style="display:block">';
      h += '<div class="ratio-lbl">Pravni stav suda</div>';
      h += '<div class="ratio-text ratio-loading" id="ratio-text-' + rid + '">Učitavanje pravnog stava…</div>';
      h += '</div>';
      h += '</div>';
      allDecisions.push({ _rid: rid, decision_number: d.decision_number, obraz_text: d.obraz_text || '', izreka_preview: d.izreka_preview || '' });
      ratioIdx++;
    });
    h += '</div></div>';
  });

  var container = document.getElementById('praksa-grupisano-container');
  container.innerHTML = h;
  container.style.display = 'block';

  if (allDecisions.length) {
    (async function() {
      var payload = allDecisions.map(function(d) {
        return { decision_number: d.decision_number, text: (d.obraz_text || d.izreka_preview || '').substring(0, 3000) };
      });
      var _setG = function(rid, ratio) {
        var box = document.getElementById('ratio-' + rid);
        var txt = document.getElementById('ratio-text-' + rid);
        if (!box || !txt) return;
        if (ratio === '__IZREKA_ONLY__') {
          txt.className = 'ratio-text ratio-loading';
          txt.textContent = 'Presuda sadrži samo izreku bez obrazloženja.';
        } else if (ratio) {
          txt.className = 'ratio-text';
          txt.textContent = ratio;
        } else {
          txt.className = 'ratio-text ratio-loading';
          txt.textContent = 'Pravni stav nije utvrđen iz dostavljenog teksta.';
        }
      };
      try {
        var r = await fetch(BASE_URL + '/api/praksa/ratio', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decisions: payload }),
        });
        if (!r.ok) {
          console.error('[ratio/g] HTTP ' + r.status);
          allDecisions.forEach(function(d) { _setG(d._rid, null); });
          return;
        }
        var resp = await r.json();
        var ratios = resp.ratios || {};
        allDecisions.forEach(function(d) { _setG(d._rid, ratios[d.decision_number] || null); });
      } catch(e) {
        console.error('[ratio/g] fetch error:', e);
        allDecisions.forEach(function(d) { _setG(d._rid, null); });
      }
    })();
  }
}

/* ── Document Upload P2.6a ───────────────────────────────────── */
var _docSessionId  = null;
var _docUploadName = null;
var _docUploadSize = 0;

function doc_upload_trigger() {
  if (!currentSession) { openModal(); return; }
  document.getElementById('doc-upload-input').click();
}

function _doc_fmt_size(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes/1024).toFixed(1) + ' KB';
  return (bytes/1048576).toFixed(1) + ' MB';
}

function _doc_show_error(msg) {
  var z  = document.getElementById('doc-upload-zone');
  var ld = document.getElementById('doc-upload-loading');
  var er = document.getElementById('doc-upload-error');
  if (z)  z.style.display  = 'block';
  if (ld) ld.style.display = 'none';
  if (er) { er.style.display = 'block'; er.textContent = msg; }
}

function _doc_show_loading() {
  var z  = document.getElementById('doc-upload-zone');
  var ld = document.getElementById('doc-upload-loading');
  var er = document.getElementById('doc-upload-error');
  if (z)  z.style.display  = 'none';
  if (ld) ld.style.display = 'block';
  if (er) er.style.display = 'none';
}

function _doc_show_session(filename, sizeBytes, chunkCount) {
  document.getElementById('doc-upload-zone').style.display    = 'none';
  document.getElementById('doc-upload-loading').style.display = 'none';
  document.getElementById('doc-upload-error').style.display   = 'none';
  document.getElementById('doc-session-active').style.display = 'block';
  document.getElementById('doc-file-name').textContent = filename;
  document.getElementById('doc-file-meta').textContent = _doc_fmt_size(sizeBytes) + ' • ' + chunkCount + ' odeljka';
}

async function doc_upload_file(file) {
  if (!file) return;
  var ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
  if (['.pdf','.docx','.doc'].indexOf(ext) === -1) {
    _doc_show_error('Nepodržan format. Koristite PDF ili DOCX.');
    return;
  }
  if (file.size > 25 * 1024 * 1024) {
    _doc_show_error('Fajl je preko 25MB. Probajte manji.');
    return;
  }
  _doc_show_loading();
  try {
    var fd = new FormData();
    fd.append('file', file);
    var r = await fetch(BASE_URL + '/api/dokument/upload', { method: 'POST', headers: { 'Authorization': 'Bearer ' + currentSession.access_token }, body: fd });
    if (r.status === 422) {
      var _e422 = await r.json().catch(function(){ return {}; });
      _doc_show_error(_e422.detail || 'Dokument nije čitljiv. Pokušajte sa digitalnim PDF-om (300 DPI skeniranje ili dokument iz Word-a).');
      var _eb = document.getElementById('exec-btn');
      var _rb = document.getElementById('rb');
      var _rp = document.getElementById('resp');
      if (_eb) _eb.disabled = true;
      if (_rb) { _rb.textContent = ''; _rb.innerHTML = ''; }
      if (_rp) _rp.classList.remove('show');
      return;
    }
    if (r.status === 413) {
      _doc_show_error('Fajl je preko 25MB. Probajte manji.');
      return;
    }
    if (!r.ok) {
      _doc_show_error('Greška servera (' + r.status + '). Pokušajte ponovo.');
      return;
    }
    var d = await r.json();
    _docSessionId  = d.session_id;
    _docUploadName = file.name;
    _docUploadSize = file.size;
    _doc_show_session(file.name, file.size, d.chunk_count || 0);
    var _ocrW = document.getElementById('doc-ocr-warning');
    if (_ocrW) _ocrW.style.display = d.ocr_used ? 'block' : 'none';
    document.getElementById('doc-upload-input').value = '';
  } catch(e) {
    _doc_show_error('Nema veze sa serverom. Proverite konekciju.');
  }
}

async function doc_ask_question() {
  var aq = document.getElementById('aq');
  var pitanje = aq ? aq.value.trim() : '';
  var resp    = document.getElementById('resp');
  var rb      = document.getElementById('rb');
  var execBtn = document.getElementById('exec-btn');
  var btnLbl  = document.getElementById('btn-lbl');
  var orig    = btnLbl ? btnLbl.textContent : '';
  if (!_docSessionId) return;
  if (!pitanje) {
    resp.classList.add('show'); rb.style.whiteSpace = 'pre-wrap';
    rb.textContent = 'Unesite pitanje o dokumentu.';
    return;
  }
  if (execBtn) execBtn.disabled = true;
  if (btnLbl)  btnLbl.textContent = 'Analiziram dokument...';
  resp.classList.remove('show');
  try {
    var r = await fetch(BASE_URL + '/api/dokument/pitanje', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + currentSession.access_token },
      body:    JSON.stringify({ session_id: _docSessionId, pitanje: pitanje })
    });
    if (r.status === 404) {
      doc_clear_session();
      _doc_show_error('Sesija je istekla. Ponovo otpremite dokument.');
      return;
    }
    if (!r.ok) {
      resp.classList.add('show'); rb.style.whiteSpace = 'pre-wrap';
      rb.textContent = 'Greška servera (' + r.status + '). Pokušajte ponovo.';
      return;
    }
    var d = await r.json();
    if (d.credits_remaining !== undefined) {
      if (typeof userCredits !== 'undefined') userCredits = d.credits_remaining;
      if (typeof updateCreditDisplay === 'function') updateCreditDisplay();
    }
    var text = d.data || d.odgovor || d.greska || 'Greška u odgovoru servera.';
    resp.classList.add('show'); rb.textContent = ''; rb.style.whiteSpace = 'pre-wrap'; rb.classList.add('resp-cursor');
    var idx = 0, speed = text.length > 600 ? 4 : text.length > 300 ? 7 : 12;
    var iv = setInterval(function() {
      if (idx >= text.length) {
        clearInterval(iv); rb.classList.remove('resp-cursor'); rb.style.whiteSpace = '';
        var parsed = (typeof formatResponse === 'function') ? formatResponse(text) : null;
        if (parsed && parsed.trim()) { rb.innerHTML = parsed; } else { rb.style.whiteSpace = 'pre-wrap'; rb.textContent = text; }
        if (typeof _cyrillicOn !== 'undefined' && _cyrillicOn && typeof cirilicaElement === 'function') cirilicaElement(rb);
      } else { rb.textContent += text[idx]; idx++; }
    }, speed);
  } catch(e) {
    resp.classList.add('show'); rb.style.whiteSpace = 'pre-wrap';
    rb.textContent = 'Nema veze sa serverom. Proverite konekciju.';
  } finally {
    if (execBtn) execBtn.disabled = false;
    if (btnLbl)  btnLbl.textContent = orig;
  }
}

function doc_clear_session() {
  _docSessionId  = null;
  _docUploadName = null;
  _docUploadSize = 0;
  var sa = document.getElementById('doc-session-active');
  var z  = document.getElementById('doc-upload-zone');
  var ld = document.getElementById('doc-upload-loading');
  var er = document.getElementById('doc-upload-error');
  if (sa) sa.style.display = 'none';
  if (z)  z.style.display  = 'block';
  if (ld) ld.style.display = 'none';
  if (er) er.style.display = 'none';
  var _ocrW = document.getElementById('doc-ocr-warning');
  if (_ocrW) _ocrW.style.display = 'none';
  var aq  = document.getElementById('aq');
  var inp = document.getElementById('doc-upload-input');
  if (aq)  aq.value  = '';
  if (inp) inp.value = '';
  var rp  = document.getElementById('rokovi-panel');
  var rdi = document.getElementById('rok-datum-doc');
  var rdh = document.getElementById('rok-datum-hint');
  var btn = document.querySelector('.rokovi-btn');
  if (rp)  { rp.classList.remove('show'); document.getElementById('rokovi-lista').innerHTML = ''; }
  if (rdi) rdi.value = '';
  if (rdh) rdh.textContent = '';
  if (btn) btn.textContent = '📅 Prikaži rokove';
}

/* ── Forenzički audit (Executive Report) ───────────────────────── */

function _fa_esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

function _fa_severity_class(sev){
  var s=(sev||'').toLowerCase();
  if(s==='kritican'||s==='kritičan') return 'fa-sev-kritican';
  if(s==='visok') return 'fa-sev-visok';
  if(s==='srednji') return 'fa-sev-srednji';
  return 'fa-sev-nizak';
}

function _fa_score_class(score){
  if(score>=70) return 'fa-score-high';
  if(score>=40) return 'fa-score-med';
  return 'fa-score-low';
}

function renderForenzickiAudit(report, docType, segmentCount) {
  if(!report) return '<div class="analiza-plain">Nema izveštaja.</div>';

  // Fallback: ako je parse greška, prikaži legacy_text
  if(report._parse_error || !report.executive_summary) {
    var leg = _fa_esc(report.legacy_text || 'Analiza nije mogla biti strukturirana.');
    return '<div class="analiza-plain" style="white-space:pre-wrap">' + leg + '</div>';
  }

  var es = report.executive_summary;
  var score = es.overall_risk_score || 0;
  var scoreClass = _fa_score_class(score);
  var riskLabel = _fa_esc((es.risk_label||'').toUpperCase());

  var h = '';
  // ── Header ──────────────────────────────────────────────────────
  h += '<div class="fa-header">';
  h += '<div class="fa-score-row">';
  h += '<div class="fa-score-circle '+scoreClass+'">'+score+'</div>';
  h += '<div>';
  h += '<div class="fa-score-label '+scoreClass+'">'+riskLabel+' RIZIK</div>';
  var dtLabel = docType==='presuda'?'Presuda':docType==='ugovor'?'Ugovor':docType==='resenje'?'Rešenje':'Dokument';
  h += '<div style="font-size:.74rem;color:rgba(255,255,255,.4);margin-top:4px;">'+dtLabel+' &bull; '+segmentCount+' segmenata</div>';
  h += '</div></div>';

  // Chips
  h += '<div class="fa-chips">';
  if(es.critical_count>0) h += '<span class="fa-chip fa-chip-kritican">&#9888; '+es.critical_count+' kritičnih</span>';
  if(es.high_count>0)     h += '<span class="fa-chip fa-chip-high">'+es.high_count+' visokih</span>';
  if(es.missing_clauses_count>0) h += '<span class="fa-chip fa-chip-missing">'+es.missing_clauses_count+' nedostajućih klauzula</span>';
  if(es.financial_exposure_rsd) h += '<span class="fa-chip fa-chip-fin">'+Number(es.financial_exposure_rsd).toLocaleString('sr-RS')+' RSD izloženost</span>';
  h += '</div></div>';

  // ── Findings ────────────────────────────────────────────────────
  var findings = report.findings || [];
  if(findings.length > 0) {
    // Grupiši po kategoriji, sortiraj po severity_score opadajuće
    findings.sort(function(a,b){return (b.severity_score||0)-(a.severity_score||0);});
    h += '<div class="fa-section">';
    h += '<div class="fa-section-hdr fa-hdr-risk">&#9889; Identifikovani rizici ('+findings.length+')</div>';
    findings.forEach(function(f){
      var sevCls = _fa_severity_class(f.severity);
      h += '<div class="fa-finding">';
      h += '<div class="fa-finding-top">';
      h += '<span class="fa-severity-badge '+sevCls+'">'+_fa_esc(f.severity||'')+'</span>';
      h += '<div>';
      h += '<div class="fa-finding-text">'+_fa_esc(f.finding||'')+'</div>';
      var catLabel = (f.category||'').replace(/_/g,' ');
      h += '<div style="font-size:.7rem;color:rgba(255,255,255,.3);margin-top:2px;">'+_fa_esc(catLabel);
      if(f.clause_ref) h += ' &bull; ref: '+_fa_esc(f.clause_ref);
      h += '</div>';
      h += '</div></div>';
      if(f.clause_excerpt) h += '<div class="fa-excerpt">&ldquo;'+_fa_esc(f.clause_excerpt)+'&rdquo;</div>';
      if(f.law_ref){
        var lawCls = f.unverified_law_ref ? 'fa-law-ref fa-law-unverified' : 'fa-law-ref';
        h += '<div class="'+lawCls+'">&#128209; '+_fa_esc(f.law_ref)+(f.unverified_law_ref?' &#9888;':'')+'</div>';
      }
      if(f.suggested_fix) h += '<div class="fa-fix-box">&#10003; '+_fa_esc(f.suggested_fix)+'</div>';
      h += '</div>';
    });
    h += '</div>';
  }

  // ── Missing Clauses ─────────────────────────────────────────────
  var missing = report.missing_clauses || [];
  if(missing.length > 0) {
    h += '<div class="fa-section">';
    h += '<div class="fa-section-hdr fa-hdr-missing">&#9888; Nedostajuće klauzule ('+missing.length+')</div>';
    missing.forEach(function(mc){
      h += '<div class="fa-missing-item">';
      h += '<div class="fa-missing-name">'+_fa_esc(mc.clause_name||'')+'</div>';
      h += '<div class="fa-missing-why">'+_fa_esc(mc.why_it_matters||'')+'</div>';
      if(mc.suggested_text){
        h += '<details style="margin-top:5px;"><summary style="font-size:.72rem;color:rgba(255,255,255,.35);cursor:pointer;">Predlog teksta</summary>';
        h += '<div style="font-size:.76rem;color:rgba(255,255,255,.5);margin-top:4px;white-space:pre-wrap;">'+_fa_esc(mc.suggested_text)+'</div></details>';
      }
      h += '</div>';
    });
    h += '</div>';
  }

  // ── Financial Exposure ──────────────────────────────────────────
  var fe = report.financial_exposure || {};
  if(fe.max_total_exposure_rsd) {
    h += '<div class="fa-section">';
    h += '<div class="fa-section-hdr fa-hdr-fin">&#128181; Finansijska izloženost</div>';
    h += '<div class="fa-finding"><div class="fa-finding-text" style="font-size:.9rem;font-weight:700;color:#4ade80;">';
    h += 'Maksimalna izloženost: '+Number(fe.max_total_exposure_rsd).toLocaleString('sr-RS')+' RSD</div></div>';
    (fe.items||[]).forEach(function(item){
      h += '<div class="fa-finding"><div class="fa-finding-text">'+_fa_esc(item.type||'')+': '+_fa_esc(item.amount_or_formula||'');
      if(item.notes) h += ' — '+_fa_esc(item.notes);
      h += '</div></div>';
    });
    h += '</div>';
  }

  // ── Litigation Readiness ────────────────────────────────────────
  var litig = report.litigation_readiness || {};
  if(litig.applicable) {
    var litItems = [
      ...(litig.evidence_gaps||[]).map(function(i){return {label:'Dokazni problem',text:i.issue,ref:i.clause_ref};}),
      ...(litig.procedural_defects||[]).map(function(i){return {label:'Procesni nedostatak',text:i.issue,ref:i.clause_ref};}),
      ...(litig.deadline_risks||[]).map(function(i){return {label:'Rok',text:i.issue+(i.deadline_type?' ('+i.deadline_type+')':''),ref:i.clause_ref};}),
    ];
    if(litItems.length>0){
      h += '<div class="fa-section">';
      h += '<div class="fa-section-hdr fa-hdr-litig">&#9878; Sudska gotovost ('+litItems.length+' problema)</div>';
      litItems.forEach(function(item){
        h += '<div class="fa-finding"><div class="fa-finding-top">';
        h += '<span class="fa-severity-badge fa-sev-srednji">'+_fa_esc(item.label)+'</span>';
        h += '<div class="fa-finding-text">'+_fa_esc(item.text||'');
        if(item.ref) h += ' <span style="color:rgba(255,255,255,.3);font-size:.7rem;">['+_fa_esc(item.ref)+']</span>';
        h += '</div></div></div>';
      });
      h += '</div>';
    }
  }

  // ── Attack Surface ──────────────────────────────────────────────
  var attacks = report.attack_surface || [];
  if(attacks.length>0){
    h += '<div class="fa-section">';
    h += '<div class="fa-section-hdr fa-hdr-attack">&#128081; Napadne površine ('+attacks.length+')</div>';
    attacks.forEach(function(a){
      var sevCls = _fa_severity_class(a.severity);
      h += '<div class="fa-finding">';
      h += '<div class="fa-finding-top"><span class="fa-severity-badge '+sevCls+'">'+_fa_esc(a.severity||'')+'</span>';
      h += '<div class="fa-finding-text">'+_fa_esc(a.vulnerability||'');
      if(a.clause_ref) h += ' <span style="color:rgba(255,255,255,.3);font-size:.7rem;">['+_fa_esc(a.clause_ref)+']</span>';
      h += '</div></div></div>';
    });
    h += '</div>';
  }

  // ── Legacy text (collapsible) ───────────────────────────────────
  if(report.legacy_text){
    h += '<div class="fa-legacy-toggle" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display===\'none\'?\'block\':\'none\'">▼ Plain-text rezime (kompatibilnost)</div>';
    h += '<div class="fa-legacy-body">'+_fa_esc(report.legacy_text)+'</div>';
  }

  // ── Low confidence (ako postoje) ─────────────────────────────────
  var lc = report.low_confidence_findings || [];
  if(lc.length>0){
    h += '<div style="margin-top:6px;font-size:.7rem;color:rgba(255,255,255,.25);">'+lc.length+' nalaz(a) isključeno zbog niske pouzdanosti</div>';
  }

  return h;
}

async function doc_forensic_audit() {
  if(!_docSessionId) return;
  var btn = document.getElementById('forensic-audit-btn');
  var lbl = document.getElementById('forensic-btn-lbl');
  var result = document.getElementById('forensic-audit-result');
  if(!btn) return;

  btn.disabled = true;
  lbl.textContent = 'Forenzička analiza u toku... (30-60s)';
  result.style.display = 'none';
  result.innerHTML = '';

  try {
    var r = await fetch(BASE_URL + '/api/dokument/analiza', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + currentSession.access_token },
      body:    JSON.stringify({ session_id: _docSessionId, pitanje: '' })
    });

    if(r.status === 401){ closeModal(); openModal(); return; }
    if(r.status === 402){ userCredits=0; updateCreditDisplay(); showPaywall(); return; }
    if(r.status === 404){
      doc_clear_session();
      _doc_show_error('Sesija je istekla. Ponovo otpremite dokument.');
      return;
    }

    var d = await r.json();
    if(d.credits_remaining !== undefined){ userCredits=d.credits_remaining; updateCreditDisplay(); }

    var html;
    if(d.status === 'success' && d.report) {
      html = renderForenzickiAudit(d.report, d.doc_type, d.segment_count);
    } else {
      html = '<div class="analiza-plain">Greška: ' + _fa_esc(d.message || d.detail || 'Nepoznata greška') + '</div>';
    }

    result.innerHTML = html;
    result.style.display = 'block';
  } catch(e) {
    result.innerHTML = '<div class="analiza-plain">Greška pri komunikaciji sa serverom.</div>';
    result.style.display = 'block';
  } finally {
    btn.disabled = false;
    lbl.textContent = '🔬 Forenzička analiza dokumenta';
  }
}

/* ── Rokovi panel Phase 4.1 ───────────────────────────────────────── */
var _ROK_ICONS = { zastarelost:'⏰', otkaz:'📋', zalba:'⚖️', podnesak:'📝', isplata:'💰', ostalo:'📌' };
var _rokovi_debounce = null;

function _rok_render_alert(rok) {
  if (rok.dana_do_roka === null || rok.dana_do_roka === undefined) {
    if (rok.tip === 'relativni') {
      return '<div class="rok-nepoznat">📅 Datum dokumenta nepoznat — unesite ručno</div>';
    }
    return '';
  }
  var n = rok.dana_do_roka;
  if (rok.istekao) {
    return '<div class="rok-alert rok-istekao">⚠️ Rok istekao pre ' + Math.abs(n) + ' dana</div>';
  }
  if (n <= 7)  return '<div class="rok-alert rok-hitno">🔴 Ističe za ' + n + ' dan' + (n === 1 ? '' : 'a') + '</div>';
  if (n <= 30) return '<div class="rok-alert rok-upozorenje">🟡 Ističe za ' + n + ' dana</div>';
  return '<div class="rok-alert rok-ok">✅ Ističe za ' + n + ' dana</div>';
}

function _rok_build_card(rok) {
  var kat     = rok.kategorija || 'ostalo';
  var icon    = _ROK_ICONS[kat] || '📌';
  var ctx     = rok.kontekst ? rok.kontekst.replace(/</g,'&lt;').replace(/>/g,'&gt;') : '';
  var isoAttr = rok.konkretan_datum_iso ? ' data-rok-iso="' + rok.konkretan_datum_iso + '"' +
    ' data-rok-naslov="' + (kat + ': ' + rok.vrednost).replace(/"/g,'&quot;') + '"' +
    ' data-rok-opis="' + (ctx ? ctx.substring(0,120) : '').replace(/"/g,'&quot;') + '"' : '';
  var html = '<div class="rok-card ' + kat + (rok.istekao ? ' rok-card-istekao' : '') + '"' + isoAttr + '>' +
    '<div class="rok-icon">' + icon + '</div>' +
    '<div class="rok-body">' +
      '<span class="rok-vrednost">' + rok.vrednost + '</span>' +
      '<span class="rok-badge ' + rok.tip + '">' + rok.tip + '</span>';
  if (ctx) html += '<div class="rok-kontekst">' + ctx + '</div>';
  if (rok.konkretan_datum && rok.tip === 'relativni') {
    html += '<div class="rok-konkretan">📅 ' + rok.konkretan_datum + '</div>';
  }
  html += _rok_render_alert(rok);
  if (rok.konkretan_datum_iso && !rok.istekao) {
    var naslov  = (kat + ': ' + rok.vrednost).replace(/'/g,"\\'");
    var opisIcs = ctx ? ctx.substring(0,120).replace(/'/g,"\\'") : '';
    html += '<div style="display:flex;flex-wrap:wrap;gap:0.3rem;margin-top:0.4rem;">'
      + '<button class="btn-ics" onclick="dodajUKalendar(\'' + naslov + '\',\'' + rok.konkretan_datum_iso + '\',\'' + opisIcs + '\')">⬇ .ics</button>'
      + '<button class="btn-ics" style="background:rgba(66,133,244,0.08);border-color:rgba(66,133,244,0.35);color:#8ab4f8;" onclick="otvoriGoogleKalendar(\'' + naslov + '\',\'' + rok.konkretan_datum_iso + '\',\'' + opisIcs + '\')">📅 Google</button>'
      + '<button class="btn-ics" style="background:rgba(0,120,212,0.08);border-color:rgba(0,120,212,0.35);color:#60a5fa;" onclick="otvoriOutlookKalendar(\'' + naslov + '\',\'' + rok.konkretan_datum_iso + '\',\'' + opisIcs + '\')">📅 Outlook</button>'
      + '</div>';
  }
  html += '</div></div>';
  return html;
}

async function _doc_fetch_rokove() {
  if (!currentSession) return;
  var lista = document.getElementById('rokovi-lista');
  if (!lista) return;

  lista.innerHTML = '<div class="rokovi-loading"><span class="upload-spinner"></span> Tražim rokove...</div>';

  var tekst        = (document.getElementById('aitxt') || {}).value || '';
  var datumInput   = (document.getElementById('rok-datum-doc') || {}).value || '';
  var fetchBody    = { session_id: _docSessionId || '', tekst: tekst, datum_dokumenta: datumInput };

  try {
    var r = await fetch(BASE_URL + '/api/dokument/rokovi', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + currentSession.access_token },
      body: JSON.stringify(fetchBody)
    });
    if (!r.ok) { lista.innerHTML = '<div class="rokovi-empty">Greška pri učitavanju rokova.</div>'; return; }
    var d = await r.json();

    // Popuni datum input ako je auto-detektovan i input je prazan
    var hintEl = document.getElementById('rok-datum-hint');
    var inpEl  = document.getElementById('rok-datum-doc');
    if (d.datum_dokumenta && inpEl && !inpEl.value) {
      inpEl.value = d.datum_dokumenta;
    }
    if (hintEl) {
      if (d.datum_dokumenta_izvor === 'auto') {
        hintEl.textContent = '✓ Auto-detektovan';
      } else if (d.datum_dokumenta_izvor === 'korisnik') {
        hintEl.textContent = '';
      } else {
        hintEl.textContent = '';
      }
    }

    var rokovi = d.rokovi || [];
    var btnAll = document.getElementById('btn-ics-all');
    if (!rokovi.length) {
      lista.innerHTML = '<div class="rokovi-empty">Nisu pronađeni rokovi u dokumentu.</div>';
      if (btnAll) btnAll.style.display = 'none';
      return;
    }
    lista.innerHTML = rokovi.map(_rok_build_card).join('');
    // Prikaži "Izvezi sve" samo ako postoji bar jedan rok sa poznatim datumom
    var hasIso = rokovi.some(function(r){ return r.konkretan_datum_iso; });
    if (btnAll) btnAll.style.display = hasIso ? 'block' : 'none';
  } catch(e) {
    lista.innerHTML = '<div class="rokovi-empty">Nema veze sa serverom.</div>';
  }
}

async function doc_prikaži_rokove(btn) {
  if (!currentSession) { openModal(); return; }
  var panel = document.getElementById('rokovi-panel');
  var lista = document.getElementById('rokovi-lista');
  if (!panel || !lista) return;

  var isOpen = panel.classList.contains('show');
  if (isOpen) {
    panel.classList.remove('show');
    btn.textContent = '📅 Prikaži rokove';
    return;
  }

  panel.classList.add('show');
  btn.textContent = '📅 Sakrij rokove';
  await _doc_fetch_rokove();
}

function doc_rokovi_recalc() {
  // Debounce 650ms — re-fetch samo ako je panel otvoren
  clearTimeout(_rokovi_debounce);
  var panel = document.getElementById('rokovi-panel');
  if (!panel || !panel.classList.contains('show')) return;
  _rokovi_debounce = setTimeout(_doc_fetch_rokove, 650);
}

/* ── P2.1: Google Calendar / Outlook URL helpers ─────────────────── */
function _kalDatumGcal(iso) {
  /* YYYYMMDD → Google Calendar all-day format */
  return iso.replace(/-/g, '');
}

function _kalDatumOutlook(iso) {
  /* YYYY-MM-DD → Outlook ISO with time */
  return iso + 'T08:00:00';
}

function otvoriGoogleKalendar(naslov, datumIso, opis) {
  var d = _kalDatumGcal(datumIso);
  /* next day for end date (all-day) */
  var nextDay = new Date(datumIso);
  nextDay.setDate(nextDay.getDate() + 1);
  var d2 = nextDay.toISOString().slice(0,10).replace(/-/g,'');
  var url = 'https://calendar.google.com/calendar/render?action=TEMPLATE'
    + '&text=' + encodeURIComponent(naslov)
    + '&dates=' + d + '/' + d2
    + '&details=' + encodeURIComponent((opis || '') + '\n\nVindex AI — Pravni asistent')
    + '&location=Srbija';
  window.open(url, '_blank', 'noopener');
}

function otvoriOutlookKalendar(naslov, datumIso, opis) {
  var start = _kalDatumOutlook(datumIso);
  var url = 'https://outlook.live.com/calendar/0/deeplink/compose?subject='
    + encodeURIComponent(naslov)
    + '&startdt=' + encodeURIComponent(start)
    + '&body=' + encodeURIComponent((opis || '') + '\n\nVindex AI')
    + '&allday=true&path=/calendar/action/compose&rru=addevent';
  window.open(url, '_blank', 'noopener');
}

/* ── Phase 3.6: ICS export ───────────────────────────────────────── */
async function dodajUKalendar(naslov, datumIso, opis) {
  try {
    var res = await fetch(BASE_URL + '/rokovi/ics-export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rokovi: [{ naslov: naslov, datum_iso: datumIso, opis: opis || '' }] })
    });
    if (!res.ok) throw new Error('Server greška ' + res.status);
    var blob = await res.blob();
    var url  = URL.createObjectURL(blob);
    var a    = document.createElement('a');
    a.href = url; a.download = 'rok_' + datumIso + '.ics';
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
  } catch(e) {
    alert('Greška pri generisanju ICS fajla: ' + e.message);
  }
}

async function sviRokoviUKalendar() {
  var eventi = [];
  document.querySelectorAll('[data-rok-iso]').forEach(function(el) {
    eventi.push({ naslov: el.dataset.rokNaslov || 'Rok', datum_iso: el.dataset.rokIso, opis: el.dataset.rokOpis || '' });
  });
  if (!eventi.length) { alert('Nema rokova sa poznatim datumima za export.'); return; }
  try {
    var res = await fetch(BASE_URL + '/rokovi/ics-export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rokovi: eventi })
    });
    if (!res.ok) throw new Error('Server greška ' + res.status);
    var blob = await res.blob();
    var url  = URL.createObjectURL(blob);
    var a    = document.createElement('a');
    a.href = url; a.download = 'svi_rokovi_vindex.ics';
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
  } catch(e) {
    alert('Greška: ' + e.message);
  }
}

/* ── Phase 3.6: Zastarelost kalkulator ──────────────────────────── */
(function() {
  fetch(BASE_URL + '/zastarelost/tipovi')
    .then(function(r){ return r.json(); })
    .then(function(data) {
      var sel = document.getElementById('zast-tip');
      if (!sel) return;
      (data.tipovi || []).forEach(function(t) {
        var opt = document.createElement('option');
        opt.value = t.kljuc; opt.textContent = t.naziv + ' (' + t.osnov + ')'; opt.title = t.opis;
        sel.appendChild(opt);
      });
    })
    .catch(function(){});
})();

function zastToggle(btn) {
  var body = document.getElementById('zast-body');
  if (!body) return;
  var open = body.classList.toggle('show');
  btn.textContent = open ? '⏳ Sakrij kalkulator' : '⏳ Kalkulator zastarelosti';
}

function zastTipChange(sel) {
  var hint = document.getElementById('zast-osnov-hint');
  if (!hint) return;
  hint.textContent = sel.selectedOptions[0] ? (sel.selectedOptions[0].title || '') : '';
}

async function kalkulisiZastarelost() {
  var tip    = (document.getElementById('zast-tip')   || {}).value  || '';
  var datum  = (document.getElementById('zast-datum') || {}).value  || '';
  var rezDiv = document.getElementById('zast-rezultat');
  if (!rezDiv) return;

  if (!tip || !datum) {
    rezDiv.innerHTML = '<div class="rok-alert rok-hitno" style="display:block;margin-top:.5rem;">Izaberite tip i unesite datum početka.</div>';
    return;
  }
  rezDiv.innerHTML = '<div style="font-size:.8rem;color:rgba(255,255,255,0.4);margin-top:.5rem;">Računam...</div>';

  try {
    var res = await fetch(BASE_URL + '/zastarelost/kalkulisi', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tip: tip, datum_pocetka: datum })
    });
    if (!res.ok) {
      var err = await res.json().catch(function(){ return {detail:'Greška'}; });
      rezDiv.innerHTML = '<div class="rok-alert rok-hitno" style="display:block;margin-top:.5rem;">⚠ ' + _htmlEsc(err.detail || 'Server greška') + '</div>';
      return;
    }
    var d = await res.json();

    var cls = 'zc-ok';
    var statusTxt = '✅ Ističe za ' + d.dana_preostalo + ' dana';
    if (d.isteklo)               { cls = 'zc-isteklo'; statusTxt = '⚠️ Zastarelo pre ' + Math.abs(d.dana_preostalo) + ' dana'; }
    else if (d.dana_preostalo <= 7)  { cls = 'zc-hitno';  statusTxt = '🔴 HITNO — ističe za ' + d.dana_preostalo + ' dana'; }
    else if (d.dana_preostalo <= 30) { cls = 'zc-warn';   statusTxt = '🟡 Ističe za ' + d.dana_preostalo + ' dana'; }

    var napHtml = d.napomena ? '<div class="zast-napomena">ℹ️ ' + d.napomena + '</div>' : '';
    var _zastNaslov = 'Zastarelost: ' + d.tip_potrazivanja.replace(/'/g,"\\'");
    var _zastOsnov  = d.zakonski_osnov.replace(/'/g,"\\'");
    var icsBtnHtml = (!d.isteklo && d.datum_zastarelosti_iso)
      ? '<div style="display:flex;flex-wrap:wrap;gap:0.3rem;margin-top:0.5rem;">'
        + '<button class="btn-ics" onclick="dodajUKalendar(\'' + _zastNaslov + '\',\'' + d.datum_zastarelosti_iso + '\',\'' + _zastOsnov + '\')">⬇ .ics</button>'
        + '<button class="btn-ics" style="background:rgba(66,133,244,0.08);border-color:rgba(66,133,244,0.35);color:#8ab4f8;" onclick="otvoriGoogleKalendar(\'' + _zastNaslov + '\',\'' + d.datum_zastarelosti_iso + '\',\'' + _zastOsnov + '\')">📅 Google</button>'
        + '<button class="btn-ics" style="background:rgba(0,120,212,0.08);border-color:rgba(0,120,212,0.35);color:#60a5fa;" onclick="otvoriOutlookKalendar(\'' + _zastNaslov + '\',\'' + d.datum_zastarelosti_iso + '\',\'' + _zastOsnov + '\')">📅 Outlook</button>'
        + '</div>'
      : '';

    rezDiv.innerHTML = '<div class="zast-card ' + cls + '">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.5rem;">' +
        '<strong style="font-size:.88rem;">' + d.tip_potrazivanja + '</strong>' +
        '<span class="zast-osnov-badge">' + d.zakonski_osnov + '</span>' +
      '</div>' +
      '<div class="zast-row">Rok: <b>' + d.rok_opis + '</b></div>' +
      '<div class="zast-row">Početak: <b>' + d.datum_pocetka + '</b></div>' +
      '<div class="zast-row">Zastarelost: <b>' + d.datum_zastarelosti + '</b></div>' +
      '<div class="zast-status">' + statusTxt + '</div>' +
      napHtml + icsBtnHtml + '</div>';
  } catch(e) {
    rezDiv.innerHTML = '<div class="rok-alert rok-hitno" style="display:block;margin-top:.5rem;">Greška: ' + _htmlEsc(e.message) + '</div>';
  }
}

(function() {
  var zone = document.getElementById('doc-upload-zone');
  if (!zone) return;
  zone.addEventListener('dragover',  function(e) { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', function()  { zone.classList.remove('drag-over'); });
  zone.addEventListener('drop',      function(e) {
    e.preventDefault(); zone.classList.remove('drag-over');
    var files = e.dataTransfer && e.dataTransfer.files;
    if (files && files.length) doc_upload_file(files[0]);
  });
})();

/* ═══════════════════════════════════════════════════════════════
   ANIMACIJA 1 — § čestice u pozadini hero sekcije
═══════════════════════════════════════════════════════════════ */
(function(){
  var canvas = document.getElementById('para-canvas');
  if (!canvas) return;
  var ctx = canvas.getContext('2d');
  var mouse = {x: 0, y: 0};
  var W, H;
  var PARTICLE_COUNT = 70;
  var particles = [];

  function resize(){
    var hero = document.getElementById('hero');
    W = canvas.width  = hero ? hero.offsetWidth  : window.innerWidth;
    H = canvas.height = hero ? hero.offsetHeight : window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);

  document.addEventListener('mousemove', function(e){
    mouse.x = e.clientX;
    mouse.y = e.clientY + window.scrollY;
  });

  function rand(a, b){ return a + Math.random() * (b - a); }

  for (var i = 0; i < PARTICLE_COUNT; i++){
    particles.push({
      x:  rand(0, W),
      y:  rand(0, H),
      vx: rand(-0.18, 0.18),
      vy: rand(-0.12, 0.10),
      size: rand(8, 20),
      rot:  rand(0, Math.PI * 2),
      rotV: rand(-0.003, 0.003),
      alpha: rand(0.07, 0.22),
      ox: 0, oy: 0
    });
  }

  function draw(){
    ctx.clearRect(0, 0, W, H);
    var heroRect = canvas.getBoundingClientRect();
    var heroTop  = heroRect.top + window.scrollY;
    var cx = mouse.x - heroRect.left;
    var cy = mouse.y - heroTop;

    for (var i = 0; i < particles.length; i++){
      var p = particles[i];
      p.x += p.vx;
      p.y += p.vy;
      p.rot += p.rotV;
      if (p.x < -30) p.x = W + 20;
      if (p.x > W + 30) p.x = -20;
      if (p.y < -30) p.y = H + 20;
      if (p.y > H + 30) p.y = -20;

      // Parallax — soft push toward/away from mouse
      var dx = cx - p.x, dy = cy - p.y;
      var dist = Math.sqrt(dx*dx + dy*dy) || 1;
      var strength = Math.max(0, 1 - dist / 600);
      p.ox += (dx / dist * strength * 0.6 - p.ox) * 0.04;
      p.oy += (dy / dist * strength * 0.6 - p.oy) * 0.04;

      ctx.save();
      ctx.translate(p.x + p.ox, p.y + p.oy);
      ctx.rotate(p.rot);
      ctx.font = 'bold ' + p.size + 'px serif';
      ctx.fillStyle = 'rgba(59,130,246,' + p.alpha + ')';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('§', 0, 0);
      ctx.restore();
    }
    requestAnimationFrame(draw);
  }
  draw();
})();

/* ═══════════════════════════════════════════════════════════════
   ANIMACIJA 2 — Live stats ticker
═══════════════════════════════════════════════════════════════ */
(function(){
  var style = document.createElement('style');
  style.textContent = '@keyframes stat-bump{0%{transform:translateY(0)}40%{transform:translateY(-3px)}100%{transform:translateY(0)}}'+
    '.stat-bump{animation:stat-bump 0.35s ease}';
  document.head.appendChild(style);

  var targets = document.querySelectorAll('[data-target]');
  var values = [];
  targets.forEach(function(el, i){
    values[i] = parseInt(el.dataset.target, 10);
    el.textContent = values[i].toLocaleString('sr-Latn-RS');
  });

  function tickOne(){
    if (!targets.length) return;
    var idx = Math.floor(Math.random() * targets.length);
    values[idx]++;
    targets[idx].textContent = values[idx].toLocaleString('sr-Latn-RS');
    targets[idx].classList.remove('stat-bump');
    void targets[idx].offsetWidth; // reflow
    targets[idx].classList.add('stat-bump');
    setTimeout(tickOne, 4000 + Math.random() * 4000);
  }
  setTimeout(tickOne, 5000 + Math.random() * 3000);
})();

/* ═══════════════════════════════════════════════════════════════
   ANIMACIJA 3 — Typing indicator + typewriter u hero mockupu
═══════════════════════════════════════════════════════════════ */
(function(){
  var styleEl = document.createElement('style');
  styleEl.textContent = '@keyframes srp-bounce{0%,80%,100%{transform:translateY(0);opacity:0.7}40%{transform:translateY(-5px);opacity:1}}';
  document.head.appendChild(styleEl);

  var typing  = document.getElementById('srp-typing');
  var content = document.getElementById('srp-content');
  if (!typing || !content) return;

  // Collect all srp-text targets for typewriter
  var textEls = content.querySelectorAll('.srp-text, .srp-badge');
  var origTexts = [];
  textEls.forEach(function(el){
    origTexts.push(el.textContent);
    el.textContent = '';
  });

  setTimeout(function(){
    typing.style.display = 'none';
    content.style.display = '';

    // Typewriter — stagger each element
    var delay = 0;
    textEls.forEach(function(el, i){
      var txt = origTexts[i];
      var j = 0;
      setTimeout(function typeChar(){
        if (j < txt.length){
          el.textContent += txt[j++];
          setTimeout(typeChar, 22);
        }
      }, delay);
      delay += txt.length * 22 + 180;
    });
  }, 2000);
})();

/* ── F5: PREDMETI STATE + FUNCTIONS ─────────────────────────────────────── */
var activePredmetId   = null;
var activePredmetNaziv = '';
var _predmeti         = [];
var _copilotHistory   = [];  // last 5 copilot exchanges {q, a} for multi-turn context
var _predIstorijaData = [];
var _dashboardData    = {};   // predmet_id → {rizik_nivo, urgentni_rokovi_count, sledeci_rok}
var _predSort         = 'svi';
var _dashboardLists   = {};   // po_prioritetu, po_riziku, po_rokovima
var _notifData        = [];   // loaded notifications
var _notifRead        = new Set(JSON.parse(localStorage.getItem('vx_notif_read')||'[]'));

function _predAuthHdr() {
  return currentSession ? { 'Content-Type':'application/json', 'Authorization':'Bearer '+currentSession.access_token } : {};
}

async function pred_load() {
  if (!currentSession) return;
  try {
    var [r, rd] = await Promise.all([
      fetch(BASE_URL+'/api/predmeti',           { headers: { 'Authorization':'Bearer '+currentSession.access_token } }),
      fetch(BASE_URL+'/api/predmeti/dashboard', { headers: { 'Authorization':'Bearer '+currentSession.access_token } }),
    ]);
    // Fire portfolio, notifications and onboarding check in background (non-blocking)
    portfolio_load();
    notif_load();
    setTimeout(onboardingCheck, 1500);
    if (!r.ok) return;
    var d = await r.json();
    _predmeti = d.predmeti || [];
    if (rd.ok) {
      var dd = await rd.json();
      _dashboardLists = {
        po_prioritetu: dd.po_prioritetu || [],
        po_riziku:     dd.po_riziku     || [],
        po_rokovima:   dd.po_rokovima   || [],
      };
      _dashboardData = {};
      (dd.predmeti || []).forEach(function(e){ _dashboardData[e.id] = e; });
      // Show dashboard stats if there are alerts
      var stats = dd.statistike || {};
      if ((stats.visok_rizik || 0) > 0 || (stats.hitni_rokovi || 0) > 0) {
        var alertBar = document.getElementById('pred-dashboard-alert');
        if (alertBar) {
          var parts = [];
          if (stats.visok_rizik)  parts.push(stats.visok_rizik+' visok rizik');
          if (stats.hitni_rokovi) parts.push(stats.hitni_rokovi+' hitnih rokova');
          alertBar.textContent = '⚠ ' + parts.join(' · ');
          alertBar.style.display = 'block';
        }
      }
    }
    pred_renderList();
  } catch(e) {}
}

function pred_setSort(mode) {
  _predSort = mode;
  document.querySelectorAll('.pred-sort-btn').forEach(function(b){
    var isActive = b.dataset.sort === mode;
    b.style.background   = isActive ? 'rgba(74,168,255,.15)' : 'transparent';
    b.style.borderColor  = isActive ? 'rgba(74,168,255,.35)' : 'rgba(255,255,255,.1)';
    b.style.color        = isActive ? '#89c8ff' : 'rgba(255,255,255,.45)';
  });
  pred_renderList();
}

// ── Kancelarija Faza 2 — Firma predmeti ──────────────────────────────────────

var _predFirmaOpen  = false;
var _predFirmaData  = null;

async function predFirmaInit() {
  if (!currentSession) return;
  try {
    var r = await fetch('/api/kancelarija/moja', {headers:{'Authorization':'Bearer '+currentSession.access_token}});
    if (!r.ok) return;
    var d = await r.json();
    var btn = document.getElementById('pred-firma-toggle');
    if (btn && (d.status === 'aktivan' || d.status === 'pending_invite')) {
      btn.style.display = 'inline-block';
      if (d.status === 'aktivan') {
        btn.title = d.firma ? d.firma.naziv : 'Firma predmeti';
      }
    }
  } catch(e) {}
}

async function predFirmaToggle() {
  _predFirmaOpen = !_predFirmaOpen;
  var panel = document.getElementById('pred-firma-panel');
  var btn   = document.getElementById('pred-firma-toggle');
  if (!panel) return;
  if (!_predFirmaOpen) {
    panel.style.display = 'none';
    if (btn) { btn.style.background='transparent'; btn.style.borderColor='rgba(0,212,255,0.25)'; btn.style.color='rgba(0,212,255,0.6)'; }
    return;
  }
  panel.style.display = '';
  if (btn) { btn.style.background='rgba(0,212,255,0.12)'; btn.style.borderColor='rgba(0,212,255,0.4)'; btn.style.color='#00d4ff'; }
  await predFirmaLoad();
}

async function predFirmaLoad() {
  if (!currentSession) return;
  var listEl  = document.getElementById('pred-firma-list');
  var emptyEl = document.getElementById('pred-firma-empty');
  var lblEl   = document.getElementById('pred-firma-label');
  var cntEl   = document.getElementById('pred-firma-count');
  if (listEl) listEl.innerHTML = '<div style="font-size:0.73rem;color:rgba(255,255,255,0.3);">Učitavam...</div>';
  try {
    var r = await fetch('/api/kancelarija/predmeti', {headers:{'Authorization':'Bearer '+currentSession.access_token}});
    if (!r.ok) { if(listEl) listEl.innerHTML = '<div style="color:#f87171;font-size:0.73rem;">Greška pri učitavanju.</div>'; return; }
    var d = await r.json();
    _predFirmaData = d;
    if (lblEl && d.firma_naziv) lblEl.textContent = d.firma_naziv + ' — predmeti';
    var predmeti = d.predmeti || [];
    // Exclude own predmeti (already visible in main list)
    var tudjji = predmeti.filter(function(p){ return !p.je_moj; });
    if (cntEl) cntEl.textContent = tudjji.length || predmeti.length;
    if (!tudjji.length) {
      if(listEl) listEl.innerHTML = '';
      if(emptyEl) emptyEl.style.display = '';
      return;
    }
    if(emptyEl) emptyEl.style.display = 'none';
    var statColors = {aktivan:'#4ade80', arhiviran:'rgba(255,255,255,0.3)', zatvoren:'#f87171'};
    if (listEl) listEl.innerHTML = tudjji.map(function(p){
      var sc = statColors[p.status] || 'rgba(255,255,255,0.4)';
      var owner = (p.vlasnik_email || '').split('@')[0];
      var tipLabel = p.tip ? (' · ' + p.tip) : '';
      return '<div style="display:flex;align-items:center;gap:0.5rem;padding:0.35rem 0.55rem;background:rgba(0,212,255,0.03);border:1px solid rgba(0,212,255,0.08);border-radius:6px;">'
        +'<span style="width:6px;height:6px;border-radius:50%;background:'+sc+';flex-shrink:0;"></span>'
        +'<span style="flex:1;font-size:0.78rem;color:rgba(255,255,255,0.82);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="'+_htmlEsc(p.naziv)+'">'+_htmlEsc(p.naziv)+'</span>'
        +'<span style="font-size:0.62rem;color:rgba(0,212,255,0.45);white-space:nowrap;flex-shrink:0;">@'+_htmlEsc(owner)+'</span>'
        +'</div>';
    }).join('');
  } catch(e) { if(listEl) listEl.innerHTML = '<div style="color:#f87171;font-size:0.73rem;">Greška mreže.</div>'; }
}

function pred_renderList() {
  var el = document.getElementById('pred-list');
  if (!el) return;
  if (!_predmeti.length) {
    el.innerHTML = '<div style="font-size:0.78rem;color:rgba(255,255,255,0.3);text-align:center;padding:1.2rem 0;">Nemate predmeta. Kreirajte prvi.</div>';
    return;
  }

  // Determine sorted list
  var list;
  if (_predSort === 'prioritet' && _dashboardLists.po_prioritetu && _dashboardLists.po_prioritetu.length) {
    list = _dashboardLists.po_prioritetu;
  } else if (_predSort === 'rizik' && _dashboardLists.po_riziku && _dashboardLists.po_riziku.length) {
    list = _dashboardLists.po_riziku;
  } else if (_predSort === 'rokovi' && _dashboardLists.po_rokovima && _dashboardLists.po_rokovima.length) {
    list = _dashboardLists.po_rokovima;
  } else {
    list = _predmeti;
  }

  var _RIZIK_COLOR = {visok:'#ff9090', srednji:'#ffbb70', nizak:'#7de0a0'};

  el.innerHTML = list.map(function(p){
    var tipCls  = p.tip === 'radni' ? 'radni' : p.tip === 'privredni' ? 'privredni' : '';
    var active  = p.id === activePredmetId ? ' active' : '';
    var statusCls = p.status === 'aktivan' ? 'pred-status-aktivan' : 'pred-status-zatvoren';
    var statusLbl = (p.status || 'aktivan').toUpperCase();
    var di = _dashboardData[p.id] || {};
    var rizikHtml = '';
    if (di.rizik_nivo) {
      var rColor = _RIZIK_COLOR[di.rizik_nivo] || 'rgba(255,255,255,.4)';
      rizikHtml = '<span style="font-size:0.58rem;font-weight:700;color:'+rColor+';margin-left:0.3rem;letter-spacing:.04em;">'+di.rizik_nivo.toUpperCase()+'</span>';
    }
    var rokHtml = '';
    if (di.urgentni_rokovi_count && di.urgentni_rokovi_count > 0) {
      rokHtml = '<span style="font-size:0.58rem;color:#ffbb70;margin-left:0.25rem;" title="Hitnih rokova: '+di.urgentni_rokovi_count+'">⏰'+di.urgentni_rokovi_count+'</span>';
    }
    var chked = _selectedPredmeti.has(p.id) ? ' checked' : '';
    return '<div class="pred-item'+active+'" data-predmet-id="'+p.id+'">'
      +'<input type="checkbox" class="pred-chk"'+chked+' style="margin:0;cursor:pointer;flex-shrink:0;" onclick="event.stopPropagation();pred_toggleOznaci(\''+p.id+'\')">'
      +'<span class="pred-naziv" style="flex:1;cursor:pointer;" onclick="pred_select(\''+p.id+'\')">📁 '+escHtml(p.naziv)+'</span>'
      +'<span style="display:flex;align-items:center;gap:0;flex-shrink:0;">'
      +'<span class="pred-badge '+tipCls+'" style="margin-right:0.25rem;">'+escHtml(p.tip)+'</span>'
      +'<span class="'+statusCls+'" style="font-size:0.62rem;font-weight:700;letter-spacing:0.06em;">'+statusLbl+'</span>'
      +rizikHtml+rokHtml
      +'</span>'
      +'</div>';
  }).join('');
}

// ── Bulk operacije na predmetima ─────────────────────────────────────────────
var _selectedPredmeti = new Set();

function pred_toggleOznaci(id) {
  if (_selectedPredmeti.has(id)) _selectedPredmeti.delete(id);
  else _selectedPredmeti.add(id);
  pred_updateBulkBar();
}

function pred_updateBulkBar() {
  var bar   = document.getElementById('pred-bulk-bar');
  var count = document.getElementById('pred-bulk-count');
  var n = _selectedPredmeti.size;
  if (bar) bar.style.display = n > 0 ? 'flex' : 'none';
  if (count) count.textContent = n + ' predmet' + (n === 1 ? ' označen' : n < 5 ? 'a označena' : 'a označeno');
}

function pred_bulkOtkaziOznacavanje() {
  _selectedPredmeti.clear();
  pred_updateBulkBar();
  pred_renderList();
}

async function pred_bulkAkcija(akcija) {
  if (!currentSession || !_selectedPredmeti.size) return;
  var ids = Array.from(_selectedPredmeti);
  var labeli = {arhiviranje:'arhiviranje', aktiviranje:'aktiviranje'};
  if (!confirm('Promeniti status na \'' + (labeli[akcija]||akcija) + '\' za ' + ids.length + ' predmet(a)?')) return;
  try {
    var r = await fetch(BASE_URL+'/api/predmeti/bulk', {
      method: 'PATCH',
      headers: {'Content-Type':'application/json','Authorization':'Bearer '+currentSession.access_token},
      body: JSON.stringify({predmet_ids: ids, akcija: akcija})
    });
    var d = await r.json();
    if (!r.ok) { showToast(d.detail||'Greška.','err'); return; }
    showToast(d.poruka,'ok');
    _selectedPredmeti.clear();
    pred_updateBulkBar();
    pred_fetchList();
  } catch(e) { showToast('Greška veze.','err'); }
}

function pred_subtabSwitch(pane, btn) {
  var VALID = ['pregled','dokumenti','ai-analiza','strategija','rokovi','naplata','komunikacija','saradnja','timeline','dokazi','ccc','agenti'];
  if (VALID.indexOf(pane) === -1) pane = 'pregled';
  document.querySelectorAll('.pred-subtab-pane').forEach(function(p) { p.style.display = 'none'; });
  document.querySelectorAll('.pred-subtab-btn').forEach(function(b) { b.classList.remove('active'); });
  var el = document.getElementById('pred-pane-' + pane);
  if (el) el.style.display = 'block';
  if (btn) {
    btn.classList.add('active');
  } else {
    document.querySelectorAll('.pred-subtab-btn').forEach(function(b) {
      if ((b.getAttribute('onclick') || '').indexOf("'"+pane+"'") > -1) b.classList.add('active');
    });
  }
  // Ažuriraj "Više" btn: active samo kad je sekundarni tab otvoren
  var _moreBtn = document.getElementById('pred-more-btn');
  if (_moreBtn) {
    var _secondary = ['pregled','timeline','dokazi','graf','agenti','komunikacija','saradnja'];
    if (_secondary.indexOf(pane) > -1) _moreBtn.classList.add('active');
    else _moreBtn.classList.remove('active');
  }
  if (history.replaceState && activePredmetId) history.replaceState(null, '', '#' + pane);
  if (typeof lucide !== 'undefined') lucide.createIcons();
  // Lazy-load tabovi
  if (pane === 'saradnja' && activePredmetId) saradnja_load(activePredmetId);
  if (pane === 'timeline' && activePredmetId) timeline_load();
  if (pane === 'dokazi'   && activePredmetId) evidence_load();
  if (pane === 'graf'     && activePredmetId) kg_load();
  if (pane === 'ccc'      && activePredmetId) ccc_load();
}

/* ── "··· Više" dropdown toggle ─────────────────────────────────────────── */
function pred_more_toggle(e) {
  e.stopPropagation();
  var menu = document.getElementById('pred-more-menu');
  if (!menu) return;
  var open = menu.style.display !== 'none';
  if (open) {
    menu.style.display = 'none';
  } else {
    menu.style.display = 'block';
    // Zatvori klik van menija
    setTimeout(function() {
      document.addEventListener('click', pred_more_outside_, { once: true, capture: true });
    }, 0);
  }
}
function pred_more_outside_(e) {
  var wrap = document.getElementById('pred-more-wrap');
  if (wrap && !wrap.contains(e.target)) pred_more_close();
}
function pred_more_close() {
  var menu = document.getElementById('pred-more-menu');
  if (menu) menu.style.display = 'none';
  // Osvetli "··· Više" btn ako je aktivan sekundarni tab
  var moreBtn = document.getElementById('pred-more-btn');
  if (moreBtn) moreBtn.classList.remove('active');
}
/* Kad se bira sekundarni tab, označi "Više" kao aktivan */
function pred_more_select(pane) {
  pred_subtabSwitch(pane);
  pred_more_close();
  var moreBtn = document.getElementById('pred-more-btn');
  if (moreBtn) moreBtn.classList.add('active');
}

function pred_openStrat(modul) {
  openAITool('t');
  setTimeout(function() {
    var btn = document.querySelector('.strat-btn[data-modul="'+modul+'"]');
    if (btn) stratIzaberiModul(modul, btn);
  }, 150);
}

/* ── AI Centar Faza 3 — centralni input ─────────────────────────────────── */
async function aic3_submit() {
  if (!currentUser) { openModal(); return; }
  if (userCredits <= 0) { showPaywall(); return; }
  var qEl = document.getElementById('aic3-q');
  var q = qEl ? qEl.value.trim() : '';
  if (!q) return;
  var btn = document.getElementById('aic3-btn');
  var resultEl = document.getElementById('aic3-result');
  if (btn) { btn.disabled = true; btn.textContent = 'Istrazujem...'; }
  if (resultEl) { resultEl.className = 'aic3-result'; resultEl.textContent = ''; }
  try {
    var r = await fetch(BASE_URL + '/api/pitanje', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + currentSession.access_token },
      body: JSON.stringify({ pitanje: q, history: [] })
    });
    if (r.status === 401) { openModal(); return; }
    if (r.status === 402) { userCredits = 0; updateCreditDisplay(); showPaywall(); return; }
    if (r.status === 403) { openProUpgradeModal(); return; }
    var d = await r.json();
    if (d.credits_remaining !== undefined) { userCredits = d.credits_remaining; updateCreditDisplay(); }
    if (!r.ok) {
      var errText = d.greska || d.error
        || (typeof d.detail === 'string' ? d.detail : null)
        || ('Greška servera (' + r.status + ')');
      if (resultEl) { resultEl.textContent = errText; resultEl.classList.add('show'); }
      return;
    }
    var text = d.odgovor !== undefined ? d.odgovor : (d.greska || d.error || 'Greška: prazan odgovor servera.');
    var parsed = (typeof formatResponse === 'function') ? formatResponse(text) : null;
    if (resultEl) {
      if (parsed && parsed.trim()) { resultEl.innerHTML = parsed; resultEl.style.whiteSpace = ''; }
      else { resultEl.textContent = text; resultEl.style.whiteSpace = 'pre-wrap'; }
      resultEl.classList.add('show');
    }
  } catch (err) {
    if (resultEl) { resultEl.textContent = 'Greska: ' + (err.message || 'nepoznata'); resultEl.classList.add('show'); }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i data-lucide="sparkles" style="width:14px;height:14px;"></i> Istrazi';
      if (typeof lucide !== 'undefined') lucide.createIcons();
    }
  }
}

var _aicPendingSubtab = null;

function aicOtvoriPredmet(subtab) {
  _aicPendingSubtab = subtab || null;
  setTab(document.getElementById('tab-btn-p'), 'p');
}

function pred_select(id) {
  var predmetObj = _predmeti.find(function(p){ return p.id === id; }) || null;
  var naziv = predmetObj ? predmetObj.naziv : '';
  if (id !== activePredmetId) _copilotHistory = [];
  activePredmetId    = id;
  activePredmetNaziv = naziv;
  pred_renderList();
  pred_loadDetail(id);
  pred_updateIndicator();
  var detail = document.getElementById('pred-detail');
  if (detail) {
    detail.classList.add('show');
    setTimeout(function(){ detail.scrollIntoView({behavior:'smooth', block:'nearest'}); }, 50);
  }
  var nazivEl = document.getElementById('pred-detail-naziv');
  if (nazivEl) nazivEl.textContent = naziv;
  if (predmetObj) {
    var oblEl = document.getElementById('pred-s-oblast');
    if (oblEl) oblEl.textContent = (typeof _TIP_LABELS !== 'undefined' && _TIP_LABELS[predmetObj.tip]) || predmetObj.tip || '—';
  }
  if (history.pushState) history.pushState(null, '', '#pregled');
  var targetSubtab = _aicPendingSubtab || 'ccc';
  _aicPendingSubtab = null;
  pred_subtabSwitch(targetSubtab);
  // Auto-load Matter Intelligence bar (u Pregledu)
  setTimeout(function(){ matter_intel_load(); }, 400);
  var terminal = document.querySelector('.terminal');
  if (terminal && window.innerWidth > 900) terminal.style.overflow = 'visible';
  // Prikaži FAB za brze akcije
  pred_fab_show();
}

function pred_updateIndicator() {
  var el = document.getElementById('predmet-indicator');
  if (!el) return;
  if (activePredmetId && activePredmetNaziv) {
    el.textContent = '📁 Radite unutar predmeta: ' + activePredmetNaziv;
    el.classList.add('show');
  } else {
    el.classList.remove('show');
  }
}

function pred_renderCockpit(cockpit, urgentni) {
  var loadEl = document.getElementById('pck-loading');
  var bodyEl = document.getElementById('pck-body');
  if (!cockpit || !cockpit.ai_sazetak) {
    if (loadEl) loadEl.style.display = 'none';
    return;
  }
  if (loadEl) loadEl.style.display = 'none';
  if (bodyEl) bodyEl.style.display = 'block';

  var sazEl = document.getElementById('pck-sazetak-text');
  if (sazEl) sazEl.textContent = cockpit.ai_sazetak || '';

  var sa = cockpit.sledeca_akcija || {};
  var opEl = document.getElementById('pck-akcija-opis');
  if (opEl) opEl.textContent = sa.opis || '—';
  var rokEl = document.getElementById('pck-akcija-rok');
  if (rokEl) rokEl.textContent = sa.rok ? 'Rok: ' + sa.rok : '';
  var prioEl = document.getElementById('pck-akcija-prio');
  if (prioEl && sa.prioritet) {
    prioEl.textContent = sa.prioritet === 'hitan' ? '⚠ HITNO' : sa.prioritet;
    prioEl.className = 'pck-prio-badge ' + sa.prioritet;
    prioEl.style.display = 'inline-block';
  }

  var rz = cockpit.procena_rizika || {};
  var rzEl = document.getElementById('pck-rizik-badge');
  if (rzEl) {
    var nivo = rz.nivo || '';
    rzEl.textContent = nivo ? nivo.charAt(0).toUpperCase() + nivo.slice(1) + ' rizik' : '—';
    rzEl.className = 'pck-rizik-badge ' + nivo;
  }
  // Risk change indicator
  var prEl = document.getElementById('pck-rizik-promena');
  if (prEl) {
    var prm = cockpit.rizik_promena;
    if (prm && prm.prethodni && prm.trenutni) {
      var arrow = prm.trenutni === 'visok' ? '↑' : (prm.trenutni === 'nizak' ? '↓' : '→');
      var prmColor = prm.trenutni === 'visok' ? '#ff9090' : (prm.trenutni === 'nizak' ? '#7de0a0' : '#ffbb70');
      prEl.innerHTML = '<span style="font-size:0.62rem;color:'+prmColor+';font-weight:700;">'+arrow+' '+escHtml(prm.prethodni)+' → '+escHtml(prm.trenutni)+'</span>';
      prEl.style.display = 'block';
    } else {
      prEl.style.display = 'none';
    }
  }
  var fkEl = document.getElementById('pck-rizik-faktori');
  if (fkEl) {
    var html = '';
    (rz.faktori_plus || []).slice(0,2).forEach(function(f){
      html += '<div class="pck-faktor plus">+ '+escHtml(f)+'</div>';
    });
    (rz.faktori_minus || []).slice(0,2).forEach(function(f){
      html += '<div class="pck-faktor minus">− '+escHtml(f)+'</div>';
    });
    fkEl.innerHTML = html;
  }

  var rkEl = document.getElementById('pck-rokovi-list');
  if (rkEl) {
    var ur = (urgentni || []).slice(0,3);
    if (!ur.length) {
      rkEl.innerHTML = '<div style="font-size:.75rem;color:rgba(255,255,255,.28);">Nema hitnih rokova.</div>';
    } else {
      rkEl.innerHTML = ur.map(function(h){
        return '<div class="pck-rok-item">📅 '+escHtml(h.dogadjaj||'')+(h.datum_iso?' ('+h.datum_iso+')':'')+'</div>';
      }).join('');
    }
  }
}

function pred_renderCaseReadyScore(score, checklist, copilotPreporuka) {
  var wrap = document.getElementById('pred-crs-wrap');
  if (!wrap) return;
  var s = (typeof score === 'number' && score >= 0) ? score : 0;
  wrap.style.display = 'block'; // always show; button allows triggering pipeline

  var numEl = document.getElementById('pred-crs-num');
  if (numEl) numEl.textContent = s > 0 ? s : '—';

  var arc = document.getElementById('pred-crs-arc');
  if (arc) {
    var circ = 138.2;
    var offset = s > 0 ? circ - (circ * s / 100) : circ;
    arc.style.strokeDashoffset = offset;
    arc.style.stroke = s >= 70 ? '#7de0a0' : (s >= 40 ? '#ffbb70' : s > 0 ? '#ff9090' : 'rgba(255,255,255,.15)');
  }

  var stEl = document.getElementById('pred-crs-status');
  if (stEl) {
    if (s === 0) {
      stEl.textContent = 'Analiza nije pokrenuta';
      stEl.style.color = 'rgba(255,255,255,0.3)';
    } else {
      stEl.textContent = s >= 70 ? 'Predmet spreman za rad' : (s >= 40 ? 'Predmet delimično spreman' : 'Predmet zahteva dopunu');
      stEl.style.color = s >= 70 ? '#7de0a0' : (s >= 40 ? '#ffbb70' : '#ff9090');
    }
  }

  var clEl = document.getElementById('pred-crs-checklist');
  if (clEl) {
    var items = Array.isArray(checklist) ? checklist : [];
    clEl.innerHTML = items.map(function(it) {
      var done = it.done || it.ok;
      var color = done ? 'rgba(125,224,160,.75)' : 'rgba(255,255,255,.28)';
      var icon  = done ? '✓' : '○';
      return '<span style="font-size:.7rem;color:'+color+';display:inline-flex;align-items:center;gap:.22rem;">'
           + '<span>'+icon+'</span><span>'+escHtml(it.stavka||it.label||it.naziv||'')+'</span></span>';
    }).join('');
  }

  // Copilot preporuka (populated after pipeline run)
  var cpWrap = document.getElementById('pred-crs-copilot');
  var cpTxt  = document.getElementById('pred-crs-copilot-txt');
  if (copilotPreporuka && cpWrap && cpTxt) {
    cpTxt.textContent = copilotPreporuka;
    cpWrap.style.display = '';
  }
}

async function pred_runPipeline() {
  if (!activePredmetId || !currentSession) return;
  var btn = document.getElementById('pred-crs-run-btn');
  if (btn) { btn.disabled = true; btn.textContent = '⟳ Analiziram...'; }

  try {
    var r = await fetch(BASE_URL + '/api/predmeti/' + encodeURIComponent(activePredmetId) + '/pipeline', {
      method:  'POST',
      headers: {'Authorization': 'Bearer ' + currentSession.access_token},
    });
    var d = await r.json();
    if (!r.ok) {
      showToast(d.detail || 'Greška pri analizi.', 'error');
      return;
    }
    pred_renderCaseReadyScore(d.case_ready_score, d.checklist, d.copilot_preporuka);
    showToast('Analiza završena! Score: ' + d.case_ready_score, 'success');
    if (btn) { btn.textContent = '✓ Ažurirano'; btn.style.color = '#7de0a0'; btn.style.borderColor = 'rgba(125,224,160,.3)'; }
  } catch(e) {
    showToast('Greška pri analizi predmeta.', 'error');
    if (btn) { btn.disabled = false; btn.textContent = '↻ Analiziraj'; }
  }
}

// ── Saradnja ──────────────────────────────────────────────────────────────────

var _saradnjaOwner = false; // je li trenutni korisnik vlasnik

async function saradnja_load(predmetId) {
  if (!currentSession) return;
  var hdr = {'Authorization': 'Bearer ' + currentSession.access_token};

  // Dohvati moju ulogu
  try {
    var ur = await fetch(BASE_URL + '/api/saradnja/uloga/' + encodeURIComponent(predmetId), {headers: hdr});
    if (ur.ok) {
      var ud = await ur.json();
      _saradnjaOwner = (ud.uloga === 'vlasnik');
      var badgeEl = document.getElementById('saradnja-moja-uloga');
      var formaEl = document.getElementById('saradnja-forma-wrap');
      if (badgeEl) {
        if (ud.uloga && ud.uloga !== 'vlasnik') {
          var _ulogaLbl = {citanje:'👁 Čitanje', saradnja:'✏ Saradnja', vodenje:'⚙ Vođenje'};
          badgeEl.textContent = 'Vaša uloga: ' + (_ulogaLbl[ud.uloga] || ud.uloga);
          badgeEl.style.display = '';
        } else {
          badgeEl.style.display = 'none';
        }
      }
      if (formaEl) formaEl.style.display = _saradnjaOwner ? '' : 'none';
    }
  } catch(e) {}

  // Dohvati listu saradnika (samo vlasnik vidi)
  var listaEl = document.getElementById('saradnja-lista');
  if (!listaEl) return;

  if (!_saradnjaOwner) {
    listaEl.innerHTML = '<div style="font-size:.75rem;color:rgba(255,255,255,.3);">Samo vlasnik predmeta može videti listu saradnika.</div>';
    return;
  }

  try {
    var r = await fetch(BASE_URL + '/api/saradnja/saradnici/' + encodeURIComponent(predmetId), {headers: hdr});
    var d = await r.json();
    if (!r.ok) { listaEl.innerHTML = '<div style="font-size:.75rem;color:#ff9090;">'+(d.detail||'Greška')+'</div>'; return; }
    saradnja_renderLista(d.saradnici || [], predmetId);
  } catch(e) {
    listaEl.innerHTML = '<div style="font-size:.75rem;color:#ff9090;">Greška pri učitavanju.</div>';
  }
}

function saradnja_renderLista(saradnici, predmetId) {
  var el = document.getElementById('saradnja-lista');
  if (!el) return;
  if (!saradnici.length) {
    el.innerHTML = '<div style="font-size:.75rem;color:rgba(255,255,255,.3);">Nema saradnika na ovom predmetu.</div>';
    return;
  }
  var _ulogaBoja = {citanje:'rgba(137,200,255,.7)', saradnja:'rgba(255,187,112,.8)', vodenje:'rgba(125,224,160,.8)'};
  var _ulogaLbl  = {citanje:'Čitanje', saradnja:'Saradnja', vodenje:'Vođenje'};
  el.innerHTML = saradnici.map(function(s) {
    return '<div style="display:flex;align-items:center;gap:.55rem;padding:.5rem .6rem;background:rgba(255,255,255,.03);border-radius:8px;margin-top:.28rem;">'
      +'<i data-lucide="user" style="width:14px;height:14px;flex-shrink:0;color:rgba(137,200,255,.5);"></i>'
      +'<span style="flex:1;font-size:.78rem;color:rgba(255,255,255,.8);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+escHtml(s.email||s.saradnik_user_id||'—')+'</span>'
      +'<span style="font-size:.65rem;font-weight:700;color:'+(_ulogaBoja[s.uloga]||'rgba(255,255,255,.4)')+';">'+escHtml(_ulogaLbl[s.uloga]||s.uloga)+'</span>'
      +'<button onclick="saradnja_ukloni(\''+escHtml(s.saradnik_user_id)+'\',\''+escHtml(predmetId)+'\',this)" '
        +'style="flex-shrink:0;padding:.18rem .45rem;border:1px solid rgba(255,80,80,.25);border-radius:5px;background:rgba(255,80,80,.06);color:#ff9090;font-size:.65rem;cursor:pointer;" '
        +'title="Ukloni saradnika">✕</button>'
      +'</div>';
  }).join('');
  if (typeof lucide !== 'undefined') lucide.createIcons();
}

async function saradnja_dodaj() {
  if (!activePredmetId || !currentSession) return;
  var email  = (document.getElementById('saradnja-email')  || {}).value || '';
  var uloga  = (document.getElementById('saradnja-uloga')  || {}).value || 'saradnja';
  var errEl  = document.getElementById('saradnja-forma-err');
  email = email.trim();
  if (!email || !email.includes('@')) { if (errEl) { errEl.textContent = 'Unesite ispravnu email adresu.'; errEl.style.display = ''; } return; }
  if (errEl) errEl.style.display = 'none';

  try {
    var r = await fetch(BASE_URL + '/api/saradnja/dodaj/' + encodeURIComponent(activePredmetId), {
      method: 'POST',
      headers: {'Content-Type':'application/json','Authorization':'Bearer '+currentSession.access_token},
      body: JSON.stringify({saradnik_email: email, uloga: uloga})
    });
    var d = await r.json();
    if (!r.ok) {
      if (errEl) { errEl.textContent = d.detail || 'Greška pri dodavanju.'; errEl.style.display = ''; }
      return;
    }
    showToast('Saradnik dodat: ' + escHtml(email), 'success');
    var emailEl = document.getElementById('saradnja-email');
    if (emailEl) emailEl.value = '';
    saradnja_load(activePredmetId);
  } catch(e) {
    if (errEl) { errEl.textContent = 'Greška pri dodavanju saradnika.'; errEl.style.display = ''; }
  }
}

async function saradnja_ukloni(saradnikUid, predmetId, btn) {
  if (!currentSession) return;
  if (btn) { btn.disabled = true; btn.textContent = '...'; }
  try {
    var r = await fetch(
      BASE_URL + '/api/saradnja/ukloni/' + encodeURIComponent(predmetId) + '/' + encodeURIComponent(saradnikUid),
      {method: 'DELETE', headers: {'Authorization': 'Bearer ' + currentSession.access_token}}
    );
    if (!r.ok) { var d = await r.json(); showToast(d.detail || 'Greška.', 'error'); if (btn) { btn.disabled=false; btn.textContent='✕'; } return; }
    showToast('Saradnik uklonjen.', 'success');
    saradnja_load(predmetId);
  } catch(e) {
    showToast('Greška pri uklanjanju.', 'error');
    if (btn) { btn.disabled=false; btn.textContent='✕'; }
  }
}

// ── Pred-hub quick timer (localStorage-based, posts to /billing/entries) ──────
var _timerInterval = null;

function timer_showBar() {
  var bar = document.getElementById('pred-timer-bar');
  if (bar) bar.style.display = 'flex';
}

function timer_start() {
  if (!activePredmetId || !currentSession) return;
  var key = 'vx_timer_' + activePredmetId;
  // resume if already running (e.g. page reload)
  var existing = JSON.parse(localStorage.getItem(key) || 'null');
  if (!existing) {
    localStorage.setItem(key, JSON.stringify({start: Date.now()}));
  }
  var startBtn = document.getElementById('pred-timer-start-btn');
  var stopBtn  = document.getElementById('pred-timer-stop-btn');
  if (startBtn) startBtn.style.display = 'none';
  if (stopBtn)  stopBtn.style.display  = '';
  if (_timerInterval) clearInterval(_timerInterval);
  _timerInterval = setInterval(timer_tick, 1000);
  timer_tick();
}

function timer_tick() {
  if (!activePredmetId) return;
  var key  = 'vx_timer_' + activePredmetId;
  var data = JSON.parse(localStorage.getItem(key) || 'null');
  if (!data || !data.start) return;
  var elapsed = Math.floor((Date.now() - data.start) / 1000);
  var h = Math.floor(elapsed / 3600);
  var m = Math.floor((elapsed % 3600) / 60);
  var s = elapsed % 60;
  var el = document.getElementById('pred-timer-display');
  if (el) el.textContent = (h<10?'0':'')+h+':'+(m<10?'0':'')+m+':'+(s<10?'0':'')+s;
}

async function timer_stop() {
  if (!activePredmetId || !currentSession) return;
  var key  = 'vx_timer_' + activePredmetId;
  var data = JSON.parse(localStorage.getItem(key) || 'null');
  if (!data || !data.start) { timer_discard(); return; }

  var elapsed_s = Math.floor((Date.now() - data.start) / 1000);
  var elapsed_h = parseFloat((elapsed_s / 3600).toFixed(4));

  if (_timerInterval) { clearInterval(_timerInterval); _timerInterval = null; }
  localStorage.removeItem(key);

  var startBtn = document.getElementById('pred-timer-start-btn');
  var stopBtn  = document.getElementById('pred-timer-stop-btn');
  var dispEl   = document.getElementById('pred-timer-display');
  if (stopBtn)  stopBtn.style.display  = 'none';
  if (startBtn) startBtn.style.display = '';
  if (dispEl)   dispEl.textContent     = '00:00:00';

  if (elapsed_h < 0.0028) { // < ~10 sec — ignoriši
    showToast('Tajmer resetovan (trajanje prekratko).', 'info');
    return;
  }

  var hStr = elapsed_h < 1 ? Math.round(elapsed_h * 60) + ' min' : elapsed_h.toFixed(2) + ' h';

  try {
    var r = await fetch(BASE_URL + '/billing/entries', {
      method: 'POST',
      headers: {'Content-Type':'application/json','Authorization':'Bearer '+currentSession.access_token},
      body: JSON.stringify({
        predmet_id: activePredmetId,
        opis: 'Rad na predmetu (tajmer)',
        tip: 'satnica',
        sati: elapsed_h
      })
    });
    if (r.ok) {
      showToast('Tajmer zaustavljen — ' + hStr + '. Radnja dodata u naplatu.', 'ok');
    } else {
      var d = await r.json();
      showToast(d.detail || 'Tajmer zatvoren, greška pri čuvanju.', 'err');
    }
  } catch(e) {
    showToast('Greška veze — radnja nije sačuvana.', 'err');
  }
}

function timer_discard() {
  if (_timerInterval) { clearInterval(_timerInterval); _timerInterval = null; }
  if (activePredmetId) localStorage.removeItem('vx_timer_' + activePredmetId);
  var startBtn = document.getElementById('pred-timer-start-btn');
  var stopBtn  = document.getElementById('pred-timer-stop-btn');
  var dispEl   = document.getElementById('pred-timer-display');
  var bar      = document.getElementById('pred-timer-bar');
  if (stopBtn)  stopBtn.style.display  = 'none';
  if (startBtn) startBtn.style.display = '';
  if (dispEl)   dispEl.textContent     = '00:00:00';
  if (bar)      bar.style.display      = 'none';
}

// ── Mobile bottom nav helper ──────────────────────────────────────────────────
var _mobNavMap = {h:'h', p:'p', k:'k', kal:'kal', q:'q'};

function mobileNavGo(t) {
  var btn = document.getElementById('tab-btn-' + t);
  if (btn) {
    setTab(btn, t);
  }
  mobileNavUpdateActive(t);
}

function mobileNavUpdateActive(t) {
  // Map AI sub-tabs back to 'q' for the bottom nav highlight
  var highlight = (t === 'n' || t === 'a' || t === 's' || t === 'w') ? 'q' : t;
  Object.keys(_mobNavMap).forEach(function(key) {
    var el = document.getElementById('mob-btn-' + key);
    if (el) el.classList.toggle('active', _mobNavMap[key] === highlight);
  });
}

function pred_renderConfirmCard(predlozi, metadata) {
  var klijentItems = (predlozi || []).slice(0,3).map(function(p, i){
    var pct   = p.pouzdanost || 0;
    var pColor = pct >= 90 ? '#7de0a0' : '#ffbb70';
    var naziv = p.naziv || ((p.ime||'')+' '+(p.prezime||'')).trim() || p.firma || p.id || '?';
    return {html:
      '<div style="display:flex;align-items:center;gap:0.55rem;margin-bottom:0.38rem;">'
      +'<input type="checkbox" id="conf-kl-'+i+'" checked style="accent-color:#4aa8ff;width:14px;height:14px;">'
      +'<label for="conf-kl-'+i+'" style="font-size:0.78rem;color:#fff;flex:1;cursor:pointer;">'+escHtml(naziv)+'</label>'
      +'<span style="font-size:0.6rem;color:'+pColor+';font-family:var(--font-mono);">'+pct+'%</span>'
      +'</div>',
      id: p.id || p.klijent_id || '', idx: i
    };
  });
  var rokItems = [];
  var datumi = (metadata && metadata.datumi_kljucni) ? metadata.datumi_kljucni : [];
  if (datumi.length > 0) {
    var d0   = datumi[0];
    var rNaziv = d0.opis || d0.naziv || 'Rok iz dokumenta';
    var rDatum = d0.datum_iso || d0.datum || '';
    rokItems.push({html:
      '<div style="display:flex;align-items:center;gap:0.55rem;margin-bottom:0.38rem;">'
      +'<input type="checkbox" id="conf-rok-0" checked style="accent-color:#4aa8ff;width:14px;height:14px;">'
      +'<label for="conf-rok-0" style="font-size:0.78rem;color:#fff;flex:1;cursor:pointer;">Dodaj rok: '+escHtml(rNaziv)+(rDatum?' ('+rDatum+')':'')+'</label>'
      +'</div>',
      naziv: rNaziv, datum_iso: rDatum, vaznost: 'bitan'
    });
  }
  if (!klijentItems.length && !rokItems.length) return '';
  var kIds = JSON.stringify(klijentItems.map(function(k){ return {id: k.id, idx: k.idx}; }));
  var rData = rokItems.length ? JSON.stringify(rokItems[0]) : 'null';
  var html = '<div id="pred-confirm-card" style="margin-top:0.75rem;border:1px solid rgba(74,168,255,.22);border-radius:10px;background:rgba(74,168,255,.05);padding:0.8rem 1rem;">'
    +'<div style="font-size:0.6rem;letter-spacing:.1em;text-transform:uppercase;color:#4aa8ff;margin-bottom:0.6rem;font-weight:700;">⚡ AI Prepoznao</div>';
  klijentItems.forEach(function(k){ html += k.html; });
  rokItems.forEach(function(r){ html += r.html; });
  html += '<button onclick="pred_confirmLinks('+kIds+','+rData+')" style="margin-top:0.55rem;width:100%;padding:0.55rem;background:rgba(74,168,255,.12);border:1px solid rgba(74,168,255,.28);border-radius:7px;color:#89c8ff;font-size:0.78rem;font-weight:600;cursor:pointer;letter-spacing:.02em;">✓ Potvrdi i poveži</button>'
    +'</div>';
  return html;
}

async function pred_confirmLinks(klijentItems, rokData) {
  if (!currentSession || !activePredmetId) return;
  var selectedIds = (klijentItems||[])
    .filter(function(k){ var el = document.getElementById('conf-kl-'+k.idx); return el && el.checked; })
    .map(function(k){ return k.id; })
    .filter(Boolean);
  var dodajRok = null;
  if (rokData) {
    var rokEl = document.getElementById('conf-rok-0');
    if (rokEl && rokEl.checked) dodajRok = {naziv: rokData.naziv, datum_iso: rokData.datum_iso, vaznost: rokData.vaznost};
  }
  try {
    var r = await fetch(BASE_URL+'/api/predmeti/'+activePredmetId+'/confirm-links', {
      method: 'POST',
      headers: _predAuthHdr(),
      body: JSON.stringify({klijent_ids: selectedIds, dodaj_rok: dodajRok}),
    });
    var d = await r.json();
    if (d && d.success) {
      var card = document.getElementById('pred-confirm-card');
      if (card) card.innerHTML = '<div style="font-size:0.75rem;color:#7de0a0;padding:0.3rem 0;font-weight:600;">✓ Sačuvano.</div>';
      pred_loadDetail(activePredmetId);
    }
  } catch(e) {}
}

// ── Portfolio Intelligence ────────────────────────────────────────────────────

async function portfolio_load() {
  if (!currentSession) return;
  try {
    var r = await fetch(BASE_URL+'/portfolio/dashboard', { headers: { 'Authorization':'Bearer '+currentSession.access_token } });
    if (!r.ok) return;
    var d = await r.json();
    portfolio_render(d);
  } catch(e) {}
}

function portfolio_render(d) {
  var strip = document.getElementById('portfolio-strip');
  if (!strip) return;

  var aktivan    = d.ukupno_aktivnih    || 0;
  var rokovi7n   = (d.rokovi_7_dana     || []).length;
  var hitniN     = (d.hitni_rokovi      || []).length;
  var neaktivniN = (d.neaktivni_30_dana || []).length;
  var zatvoren   = (d.po_statusu && d.po_statusu.zatvoren) || 0;

  var _kpiDefs = [
    {label:'Aktivni',   val: aktivan,    color:'#89c8ff'},
    {label:'Hitni rokovi', val: hitniN,  color: hitniN>0?'#ff9090':'rgba(255,255,255,.4)'},
    {label:'Rokovi 7d', val: rokovi7n,   color: rokovi7n>0?'#ffbb70':'rgba(255,255,255,.4)'},
    {label:'Neaktivni', val: neaktivniN, color: neaktivniN>0?'#c0a0ff':'rgba(255,255,255,.4)'},
    {label:'Zatvoreni', val: zatvoren,   color:'rgba(255,255,255,.3)'},
  ];

  var kpiEl = document.getElementById('portfolio-kpi');
  if (kpiEl) {
    kpiEl.innerHTML = _kpiDefs.map(function(k){
      return '<div style="background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07);border-radius:7px;padding:0.42rem 0.55rem;text-align:center;">'
        +'<div style="font-size:1.1rem;font-weight:700;color:'+k.color+';line-height:1.2;">'+k.val+'</div>'
        +'<div style="font-size:0.57rem;color:rgba(255,255,255,.38);letter-spacing:.05em;text-transform:uppercase;margin-top:1px;">'+k.label+'</div>'
        +'</div>';
    }).join('');
  }

  // Hitni rokovi (kritičan vaznost, u 7 dana)
  var hitni    = d.hitni_rokovi || [];
  var hitniEl  = document.getElementById('portfolio-hitni');
  var hitniListEl = document.getElementById('portfolio-hitni-list');
  if (hitni.length > 0 && hitniEl && hitniListEl) {
    hitniEl.style.display = 'block';
    hitniListEl.innerHTML = hitni.map(function(h){
      return '<div style="display:flex;align-items:center;gap:0.5rem;padding:0.22rem 0;cursor:pointer;" onclick="pred_select(\''+h.predmet_id+'\')">'
        +'<span style="font-size:0.75rem;color:#fff;flex:1;">'+escHtml(h.predmet_naziv||h.dogadjaj)+'</span>'
        +'<span style="font-size:0.6rem;color:#ff9090;font-weight:700;flex-shrink:0;">'+h.datum_iso+'</span>'
        +'</div>';
    }).join('');
  }

  // Rokovi sledećih 7 dana
  var rokovi    = d.rokovi_7_dana || [];
  var rokEl     = document.getElementById('portfolio-rokovi');
  var rokListEl = document.getElementById('portfolio-rokovi-list');
  if (rokovi.length > 0 && rokEl && rokListEl) {
    rokEl.style.display = 'block';
    rokListEl.innerHTML = rokovi.map(function(h){
      return '<div style="display:flex;align-items:center;gap:0.5rem;padding:0.2rem 0;font-size:0.73rem;color:rgba(255,255,255,.8);">'
        +'<span style="color:#ffbb70;flex-shrink:0;font-family:monospace;">'+h.datum_iso+'</span>'
        +'<span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+escHtml(h.dogadjaj||'Rok')+'</span>'
        +(h.predmet_naziv?'<span style="font-size:0.62rem;color:rgba(255,255,255,.35);flex-shrink:0;max-width:80px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+escHtml(h.predmet_naziv)+'</span>':'')
        +'</div>';
    }).join('');
  }

  // Summary
  if (d.summary) {
    var sumEl = document.getElementById('portfolio-summary');
    if (sumEl) sumEl.textContent = d.summary;
  }

  strip.style.display = 'block';
}

// ── Opposing Counsel Tracker ─────────────────────────────────────────────────

var _opposingLoaded = false;

function opposing_toggle() {
  var panel = document.getElementById('opposing-counsel-panel');
  var chev  = document.getElementById('opposing-chevron');
  if (!panel) return;
  var open = panel.style.display !== 'none';
  panel.style.display = open ? 'none' : 'block';
  if (chev) chev.textContent = open ? '▶' : '▼';
  if (!open && !_opposingLoaded) opposing_load();
}

async function opposing_load() {
  if (!currentSession) return;
  var panel = document.getElementById('opposing-counsel-panel');
  if (!panel) return;
  panel.innerHTML = '<div style="font-size:0.68rem;color:rgba(255,255,255,0.3);padding:0.3rem 0;">Učitavam...</div>';
  try {
    var r = await fetch(BASE_URL+'/analytics/opposing-counsel', {
      headers: {'Authorization': 'Bearer '+currentSession.access_token}
    });
    if (!r.ok) { panel.innerHTML='<div style="color:rgba(255,100,100,0.5);font-size:0.68rem;">Greška pri učitavanju.</div>'; return; }
    var d = await r.json();
    _opposingLoaded = true;
    opposing_render(d, panel);
    var badge = document.getElementById('opposing-count-badge');
    if (badge && d.ukupno_protivnika > 0) {
      badge.textContent = d.ukupno_protivnika;
      badge.style.display = 'inline';
    }
  } catch(e) { panel.innerHTML='<div style="color:rgba(255,100,100,0.5);font-size:0.68rem;">Greška veze.</div>'; }
}

function opposing_render(d, panel) {
  var lista = d.suprotne_strane || [];
  if (!lista.length) {
    panel.innerHTML = '<div style="font-size:0.68rem;color:rgba(255,255,255,0.3);padding:0.2rem 0;">Nema podataka — dodajte uloge \'advokat protivne\' ili \'protivna strana\' klijentima u predmetima.</div>';
    return;
  }
  var _ishod_color = function(s){ return s > 0 ? '#4ade80' : s < 0 ? '#f87171' : 'rgba(255,255,255,.4)'; };
  var _ishod_lbl   = function(s){ return s > 0 ? '▲' : s < 0 ? '▼' : '—'; };
  var html = '<div style="display:flex;flex-direction:column;gap:0.3rem;">';
  lista.forEach(function(e){
    var ime   = escHtml(e.ime || e.firma || 'Nepoznat');
    var score = e.score || 0;
    var ishodi= e.ishodi || {};
    var aktv  = e.aktivni || 0;
    var zatv  = e.zatvoreni || 0;
    var tip   = e.dominantni_tip ? escHtml(e.dominantni_tip) : '';
    var winLoss = (ishodi.pobeda||0) + 'P / ' + (ishodi.poraz||0) + 'G'
      + (ishodi.nagodba ? ' / '+(ishodi.nagodba)+'N' : '');
    html += '<div style="display:flex;align-items:center;gap:0.5rem;padding:0.3rem 0.5rem;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:6px;">'
      +'<div style="flex:1;min-width:0;">'
        +'<div style="font-size:0.73rem;color:rgba(255,255,255,.8);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'+ime+'</div>'
        +(tip ? '<div style="font-size:0.58rem;color:rgba(255,255,255,.3);">'+tip+'</div>' : '')
      +'</div>'
      +'<div style="text-align:right;flex-shrink:0;">'
        +'<div style="font-size:0.62rem;color:rgba(255,255,255,.45);">'+e.ukupno_predmeta+' pred · '+aktv+' akt</div>'
        +(zatv ? '<div style="font-size:0.6rem;color:'+_ishod_color(score)+';">'+_ishod_lbl(score)+' '+winLoss+'</div>' : '')
      +'</div>'
    +'</div>';
  });
  html += '</div>';
  html += '<div style="font-size:0.58rem;color:rgba(255,255,255,.2);margin-top:0.4rem;text-align:right;">P=pobeda G=gubitak N=nagodba</div>';
  panel.innerHTML = html;
}

// ── Notifications ─────────────────────────────────────────────────────────────

async function notif_load() {
  if (!currentSession) return;
  try {
    var r = await fetch(BASE_URL+'/notifications', { headers: { 'Authorization':'Bearer '+currentSession.access_token } });
    if (!r.ok) return;
    var d  = await r.json();
    _notifData = d.notifications || [];
    notif_render();
  } catch(e) {}
}

function notif_render() {
  var bell     = document.getElementById('notif-bell');
  var badge    = document.getElementById('notif-badge');
  var dropdown = document.getElementById('notif-dropdown');
  if (!bell) return;

  var unread = _notifData.filter(function(n){ return !_notifRead.has(n.id); });
  bell.style.display = 'flex';

  if (unread.length > 0) {
    badge.textContent = unread.length > 9 ? '9+' : String(unread.length);
    badge.style.display = 'block';
  } else {
    badge.style.display = 'none';
  }

  if (!dropdown) return;
  var _TIP_LABEL = {
    rok_blizu:'📅 Rok', hitan_rok:'⚠ Hitan rok', rok:'📅 Rok',
    rizik_promena:'⚠ Rizik', bez_klijenta:'👤 Klijent', neaktivnost:'💤 Neaktivnost'
  };
  var _PRIO_COLOR = {
    visoka:'#ff9090', hitan:'#ff9090',
    srednja:'#ffbb70', normalan:'#ffbb70',
    niska:'rgba(255,255,255,.4)', info:'rgba(255,255,255,.4)'
  };

  var unreadCount = _notifData.filter(function(n){ return !_notifRead.has(n.id); }).length;
  var hdr = '<div style="padding:0.45rem 1rem 0.3rem;display:flex;justify-content:space-between;align-items:center;">'
    +'<span style="font-size:0.6rem;text-transform:uppercase;letter-spacing:.08em;color:rgba(255,255,255,.35);">Obaveštenja'+(unreadCount?' ('+unreadCount+')':'')+'</span>'
    +'<div style="display:flex;gap:0.5rem;">'
    +'<button onclick="notif_load()" title="Osveži" style="background:none;border:none;font-size:0.62rem;color:rgba(255,255,255,.35);cursor:pointer;padding:0;">↻</button>'
    +(unreadCount?'<button onclick="notif_markAllRead()" style="background:none;border:none;font-size:0.62rem;color:#4aa8ff;cursor:pointer;padding:0;">Označi sve</button>':'')
    +'</div></div>';

  if (!_notifData.length) {
    dropdown.innerHTML = hdr+'<div style="padding:0.8rem 1rem;font-size:0.75rem;color:rgba(255,255,255,.35);text-align:center;">Nema obaveštenja.</div>';
    return;
  }
  dropdown.innerHTML = hdr
    + _notifData.map(function(n){
      var isRead = _notifRead.has(n.id);
      var pColor = _PRIO_COLOR[n.prioritet]||'rgba(255,255,255,.4)';
      var tipLbl = n.naslov || _TIP_LABEL[n.tip] || 'ℹ Info';
      var bodyTxt = n.naslov ? n.poruka : n.poruka;
      return '<div onclick="notif_click(this,\''+escHtml(n.id)+'\',\''+escHtml(n.predmet_id||'')+'\')" style="padding:0.5rem 1rem;cursor:pointer;border-top:1px solid rgba(255,255,255,.05);opacity:'+(isRead?'0.45':'1')+';" onmouseover="this.style.background=\'rgba(74,168,255,.06)\'" onmouseout="this.style.background=\'none\'">'
        +'<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.18rem;">'
        +'<span style="font-size:0.62rem;color:'+pColor+';font-weight:700;">'+escHtml(tipLbl)+'</span>'
        +'<span style="font-size:0.6rem;color:rgba(255,255,255,.28);margin-left:auto;">'+escHtml((n.datum||'').slice(5))+'</span>'
        +'</div>'
        +'<div style="font-size:0.78rem;color:rgba(255,255,255,.82);margin-bottom:0.18rem;line-height:1.4;">'+escHtml(bodyTxt)+'</div>'
        +(n.predmet_naziv?'<div style="font-size:0.7rem;color:rgba(255,255,255,.4);display:flex;align-items:center;justify-content:space-between;margin-top:.1rem;">'+escHtml(n.predmet_naziv)+(n.predmet_id?'<span style="color:#89c8ff;font-size:.68rem;">Otvori →</span>':'')+'</div>':'')
        +'</div>';
    }).join('');
}

function notif_toggleDropdown() {
  var dd = document.getElementById('notif-dropdown');
  if (!dd) return;
  var showing = dd.style.display !== 'none';
  dd.style.display = showing ? 'none' : 'block';
  if (!showing) notif_render();
}

function notif_click(el, id, predmetId) {
  _notifRead.add(id);
  localStorage.setItem('vx_notif_read', JSON.stringify([..._notifRead]));
  el.style.opacity = '0.45';
  var badge = document.getElementById('notif-badge');
  var unread = _notifData.filter(function(n){ return !_notifRead.has(n.id); });
  if (badge) { if(unread.length){badge.textContent=unread.length>9?'9+':String(unread.length);badge.style.display='block';}else{badge.style.display='none';} }
  if (predmetId) {
    document.getElementById('notif-dropdown').style.display = 'none';
    var tabEl = document.querySelector('[onclick*="setTab"][onclick*="\'p\'"]');
    if (tabEl) setTab(tabEl,'p');
    setTimeout(function(){ pred_select(predmetId); }, 150);
  }
}

function notif_markAllRead() {
  _notifData.forEach(function(n){ _notifRead.add(n.id); });
  localStorage.setItem('vx_notif_read', JSON.stringify([..._notifRead]));
  var badge = document.getElementById('notif-badge');
  if (badge) badge.style.display = 'none';
  notif_render();
}

// Close dropdown on outside click
document.addEventListener('click', function(e) {
  var bell     = document.getElementById('notif-bell');
  var bellTab  = document.getElementById('tab-btn-notif');
  var dd       = document.getElementById('notif-dropdown');
  if (dd && dd.style.display !== 'none') {
    var inBell = (bell && bell.contains(e.target)) || (bellTab && bellTab.contains(e.target));
    if (!inBell && !dd.contains(e.target)) dd.style.display = 'none';
  }
});

// Auto-refresh every 15 minutes
setInterval(function() { if (currentSession) notif_load(); }, 15 * 60 * 1000);

// ── Phase 15: ZPP Lanac Rokova ───────────────────────────────────────────────

var _lanacTipovi = null;

async function lanac_toggleSection(btn) {
  var sec = document.getElementById('lanac-section');
  var chv = document.getElementById('lanac-chevron');
  if (!sec) return;
  var open = sec.style.display !== 'none';
  sec.style.display = open ? 'none' : 'block';
  if (chv) chv.textContent = open ? '▼' : '▲';
  if (!open && !_lanacTipovi) await lanac_loadTipovi();
}

async function lanac_loadTipovi() {
  try {
    var r = await fetch(BASE_URL + '/api/rokovi/tipovi-dogadjaja');
    if (!r.ok) return;
    var d = await r.json();
    _lanacTipovi = d.tipovi || [];
    var sel = document.getElementById('lanac-tip');
    if (!sel) return;
    _lanacTipovi.forEach(function(t) {
      var opt = document.createElement('option');
      opt.value = t.kljuc;
      opt.textContent = t.naziv;
      opt.dataset.opis = t.opis || '';
      sel.appendChild(opt);
    });
  } catch(e) {}
}

function lanac_tipChange() {
  var sel   = document.getElementById('lanac-tip');
  var opis  = document.getElementById('lanac-tip-opis');
  if (!sel || !opis) return;
  var opt = sel.options[sel.selectedIndex];
  opis.textContent = (opt && opt.dataset.opis) ? opt.dataset.opis : '';
}

async function lanac_kalkulisi() {
  var tipEl   = document.getElementById('lanac-tip');
  var datumEl = document.getElementById('lanac-datum');
  var resEl   = document.getElementById('lanac-result');
  if (!tipEl || !datumEl || !resEl) return;
  var tip   = tipEl.value;
  var datum = datumEl.value;
  if (!tip)   { showToast('Izaberite tip procesnog akta.', 'warn'); return; }
  if (!datum) { showToast('Unesite datum akta.', 'warn'); return; }
  if (!currentSession) { showToast('Prijavite se.', 'warn'); return; }
  resEl.innerHTML = '<div style="font-size:0.72rem;color:rgba(255,255,255,0.35);padding:0.3rem 0;">Računam rokove...</div>';
  try {
    var r = await fetch(BASE_URL + '/api/rokovi/lanac', {
      method:  'POST',
      headers: {'Content-Type':'application/json','Authorization':'Bearer '+currentSession.access_token},
      body:    JSON.stringify({tip_dogadjaja: tip, datum_pocetka: datum})
    });
    if (!r.ok) {
      var err = await r.json().catch(function(){return{};});
      resEl.innerHTML = '<div style="color:#f87171;font-size:0.72rem;">'+(err.detail||'Greška pri izračunu.')+'</div>';
      return;
    }
    var d = await r.json();
    lanac_renderResult(d);
  } catch(e) {
    resEl.innerHTML = '<div style="color:#f87171;font-size:0.72rem;">Greška pri izračunu.</div>';
  }
}

function lanac_renderResult(d) {
  var resEl = document.getElementById('lanac-result');
  if (!resEl) return;
  var _VC = {kritican:'#f87171', vazno:'#fb923c', info:'#89c8ff'};
  var _VL = {kritican:'KRITIČAN', vazno:'VAŽNO',  info:'INFO'};
  var html = '<div style="margin-top:0.3rem;">';
  html += '<div style="font-size:0.6rem;color:rgba(255,255,255,0.3);text-transform:uppercase;letter-spacing:0.07em;margin-bottom:0.45rem;">Počev od: '+escHtml(d.datum_pocetka_display)+' — '+escHtml(d.tip_naziv)+'</div>';
  (d.lanac || []).forEach(function(rok) {
    var c = _VC[rok.vaznost] || 'rgba(255,255,255,0.4)';
    var l = _VL[rok.vaznost] || 'INFO';
    html += '<div class="lanac-rok-card">';
    html += '<div class="lanac-rok-header">';
    html += '<span class="lanac-rok-datum">'+escHtml(rok.datum_display)+'</span>';
    html += '<span class="lanac-rok-badge" style="background:'+c+'22;color:'+c+';border-color:'+c+'44;">'+l+'</span>';
    html += '</div>';
    html += '<div class="lanac-rok-naziv">'+escHtml(rok.naziv)+'</div>';
    html += '<div class="lanac-rok-osnov">'+escHtml(rok.zakonski_osnov)+'</div>';
    html += '</div>';
  });
  if (activePredmetId) {
    var tipVal   = document.getElementById('lanac-tip')   ? document.getElementById('lanac-tip').value   : '';
    var datumVal = document.getElementById('lanac-datum') ? document.getElementById('lanac-datum').value : '';
    html += '<button class="lanac-save-btn" onclick="lanac_sacuvaj(\''+escHtml(tipVal)+'\',\''+escHtml(datumVal)+'\',this)">⛓ Sačuvaj u hronologiju predmeta →</button>';
  }
  html += '</div>';
  resEl.innerHTML = html;
}

async function lanac_sacuvaj(tip, datum, btn) {
  if (!activePredmetId || !currentSession) return;
  if (btn) { btn.disabled = true; btn.textContent = 'Čuvam...'; }
  try {
    var r = await fetch(BASE_URL + '/api/rokovi/lanac', {
      method:  'POST',
      headers: {'Content-Type':'application/json','Authorization':'Bearer '+currentSession.access_token},
      body:    JSON.stringify({tip_dogadjaja: tip, datum_pocetka: datum, predmet_id: activePredmetId})
    });
    if (!r.ok) {
      showToast('Greška pri čuvanju.', 'error');
      if (btn) { btn.disabled = false; btn.textContent = '⛓ Sačuvaj u hronologiju predmeta →'; }
      return;
    }
    var d = await r.json();
    if (d.sacuvano_u_predmet) {
      showToast('Rokovi sačuvani u hronologiju!', 'success');
      if (btn) { btn.textContent = '✓ Sačuvano'; btn.style.color = '#4ade80'; btn.style.borderColor = 'rgba(74,222,128,0.3)'; }
      pred_loadHronologija(activePredmetId);
    }
  } catch(e) {
    showToast('Greška pri čuvanju.', 'error');
    if (btn) { btn.disabled = false; btn.textContent = '⛓ Sačuvaj u hronologiju predmeta →'; }
  }
}

// ── Cross-doc analiza ─────────────────────────────────────────────────────────

var _crossdocSelected = {}; // { dokId: naziv }

function crossdoc_toggleSection(hd) {
  var body = document.getElementById('crossdoc-body');
  var chev = document.getElementById('crossdoc-chevron');
  if (!body) return;
  var open = body.style.display !== 'none';
  body.style.display = open ? 'none' : '';
  if (chev) chev.textContent = open ? '▼' : '▲';
}

function crossdoc_toggleDok(cb) {
  var row = cb.closest('[data-dok-id]');
  if (!row) return;
  var id = row.getAttribute('data-dok-id');
  var naziv = row.getAttribute('data-dok-naziv');
  if (cb.checked) {
    _crossdocSelected[id] = naziv;
    row.classList.add('cd-selected');
  } else {
    delete _crossdocSelected[id];
    row.classList.remove('cd-selected');
  }
  // Keep max 5
  if (Object.keys(_crossdocSelected).length > 5) {
    cb.checked = false;
    delete _crossdocSelected[id];
    row.classList.remove('cd-selected');
    showToast('Maksimalno 5 dokumenata za analizu.', 'error');
    return;
  }
  var cnt = Object.keys(_crossdocSelected).length;
  var countEl = document.getElementById('crossdoc-count');
  if (countEl) countEl.textContent = cnt + ' odabrano';
  // Auto-open section when first doc selected
  var body = document.getElementById('crossdoc-body');
  if (cnt >= 1 && body && body.style.display === 'none') {
    crossdoc_toggleSection(null);
  }
}

async function crossdoc_analiziraj() {
  var ids = Object.keys(_crossdocSelected);
  if (ids.length < 2) { showToast('Odaberi najmanje 2 dokumenta.', 'error'); return; }
  if (!activePredmetId || !currentSession) { showToast('Nema aktivnog predmeta.', 'error'); return; }
  var pitEl = document.getElementById('crossdoc-pitanje');
  var pitanje = pitEl ? pitEl.value.trim() : '';
  if (!pitanje || pitanje.length < 10) { showToast('Upiši pravno pitanje (min. 10 znakova).', 'error'); return; }

  var loadEl = document.getElementById('crossdoc-loading');
  var resEl  = document.getElementById('crossdoc-result');
  if (loadEl) loadEl.style.display = '';
  if (resEl)  resEl.innerHTML = '';

  try {
    var r = await fetch(BASE_URL + '/api/analiza/cross-doc/predmet', {
      method:  'POST',
      headers: {'Content-Type':'application/json','Authorization':'Bearer '+currentSession.access_token},
      body:    JSON.stringify({
        predmet_id:     activePredmetId,
        dokument_ids:   ids,
        pravno_pitanje: pitanje
      })
    });
    var d = await r.json();
    if (!r.ok) { if (resEl) resEl.innerHTML = '<div style="color:#ff9090;font-size:0.77rem;">'+(d.error||d.detail||'Greška pri analizi.')+'</div>'; return; }
    if (resEl) crossdoc_renderResult(d, resEl);
  } catch(e) {
    if (resEl) resEl.innerHTML = '<div style="color:#ff9090;font-size:0.77rem;">Greška pri analizi. Pokušajte ponovo.</div>';
  } finally {
    if (loadEl) loadEl.style.display = 'none';
  }
}

function crossdoc_renderResult(d, el) {
  var _OZB_CLS = { visoka:'crossdoc-konf-visoka', srednja:'crossdoc-konf-srednja', niska:'crossdoc-konf-niska' };
  var _OZB_LBL = { visoka:'⚠ VISOKA', srednja:'▲ SREDNJA', niska:'◦ NISKA' };
  var html = '';

  // Rezime
  if (d.rezime) {
    html += '<div style="font-size:0.78rem;color:rgba(255,255,255,0.7);margin-bottom:0.6rem;padding:0.5rem 0.7rem;background:rgba(255,255,255,0.03);border-radius:7px;">'+escHtml(d.rezime)+'</div>';
  }

  // Konflikti
  var konflikti = d.konflikti || [];
  html += '<div style="font-size:0.72rem;font-weight:700;color:rgba(255,255,255,0.5);text-transform:uppercase;letter-spacing:.05em;margin-bottom:0.2rem;">Konflikti ('+konflikti.length+')</div>';
  if (!konflikti.length) {
    html += '<div style="font-size:0.77rem;color:rgba(255,255,255,0.35);padding:0.35rem 0;">Nisu pronađeni konflikti između odabranih dokumenata.</div>';
  } else {
    konflikti.forEach(function(k) {
      var cls = _OZB_CLS[k.ozbiljnost] || 'crossdoc-konf-niska';
      var lbl = _OZB_LBL[k.ozbiljnost] || k.ozbiljnost;
      html += '<div class="crossdoc-konf-card '+cls+'">'
        +'<div class="crossdoc-konf-label" style="color:'+(k.ozbiljnost==='visoka'?'#f87171':k.ozbiljnost==='srednja'?'#fb923c':'#89c8ff')+';">'+lbl+'</div>'
        +'<div style="font-size:0.72rem;color:rgba(255,255,255,0.5);margin-bottom:0.2rem;">'+escHtml(k.dokument_a||'')+'  ←→  '+escHtml(k.dokument_b||'')+'</div>'
        +'<div style="font-size:0.77rem;color:rgba(255,255,255,0.82);">'+escHtml(k.opis||'')+'</div>'
        +'</div>';
    });
  }

  // Preporuke
  var preporuke = d.preporuke || [];
  if (preporuke.length) {
    html += '<div style="font-size:0.72rem;font-weight:700;color:rgba(255,255,255,0.5);text-transform:uppercase;letter-spacing:.05em;margin:0.75rem 0 0.2rem;">Preporuke</div>';
    preporuke.forEach(function(p) {
      html += '<div class="crossdoc-preporuka">'
        +'<span class="crossdoc-prio-badge">#'+p.prioritet+'</span>'
        +'<span style="font-size:0.77rem;color:rgba(255,255,255,0.85);">'+escHtml(p.akcija||'')+'</span>'
        +(p.obrazloženje ? '<div style="font-size:0.71rem;color:rgba(255,255,255,0.4);margin-top:0.2rem;">'+escHtml(p.obrazloženje)+'</div>' : '')
        +'</div>';
    });
  }

  // Pravni zaključak
  if (d.pravni_zakljucak) {
    html += '<div style="margin-top:0.75rem;padding:0.55rem 0.7rem;background:rgba(0,212,255,0.06);border:1px solid rgba(0,212,255,0.15);border-radius:7px;font-size:0.77rem;color:rgba(255,255,255,0.72);">'
      +'<span style="font-size:0.68rem;font-weight:700;color:#00d4ff;text-transform:uppercase;letter-spacing:.05em;display:block;margin-bottom:0.3rem;">Pravni zaključak</span>'
      +escHtml(d.pravni_zakljucak)
      +'</div>';
  }

  el.innerHTML = html;
}

// ── Copilot Agent Chat ─────────────────────────────────────────────────────────

function copilot_appendMsg(role, html) {
  var container = document.getElementById('pred-copilot-messages');
  if (!container) return;
  var div = document.createElement('div');
  div.style.cssText = role === 'user'
    ? 'background:rgba(74,168,255,.08);border:1px solid rgba(74,168,255,.15);border-radius:8px 8px 2px 8px;padding:0.45rem 0.65rem;font-size:0.76rem;color:rgba(255,255,255,.8);align-self:flex-end;max-width:85%;'
    : 'background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:2px 8px 8px 8px;padding:0.45rem 0.65rem;font-size:0.76rem;color:#e6edf3;align-self:flex-start;max-width:95%;';
  div.innerHTML = html;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function copilot_renderResponse(d) {
  var tip = d.tip || '';

  if (tip === 'DODAJ_ROK' || tip === 'KREIRAJ_BELEŠKU' || tip === 'POVEZI_KLIJENTA') {
    var icon = tip==='DODAJ_ROK'?'📅':tip==='KREIRAJ_BELEŠKU'?'📝':'🔗';
    var color = d.uspeh ? '#7de0a0' : '#ff9090';
    var html = '<div style="display:flex;align-items:flex-start;gap:0.4rem;">'
      +'<span style="font-size:0.9rem;flex-shrink:0;">'+icon+'</span>'
      +'<div><div style="font-size:0.76rem;color:'+color+';font-weight:600;">'+escHtml(d.odgovor||'')+'</div>';
    if (d.uspeh) {
      if (tip==='DODAJ_ROK' && d.datum) html += '<div style="font-size:0.66rem;color:rgba(255,255,255,.4);margin-top:2px;">'+escHtml(d.datum)+' · '+escHtml(d.vaznost||'')+'</div>';
      if (tip==='POVEZI_KLIJENTA' && d.klijent) html += '<div style="font-size:0.66rem;color:rgba(255,255,255,.4);margin-top:2px;">'+escHtml(d.klijent)+' · '+escHtml(d.uloga||'')+'</div>';
    }
    html += '</div></div>';
    copilot_appendMsg('bot', html);
    if (d.uspeh) setTimeout(function(){ pred_loadDetail(activePredmetId); }, 800);
    return;
  }

  if (tip === 'PLAN' && d.faze) {
    var html = '<div style="font-size:0.72rem;color:#4aa8ff;font-weight:700;margin-bottom:0.4rem;">📋 '+escHtml(d.cilj||'Akcioni plan')+'</div>';
    (d.faze||[]).forEach(function(f, fi){
      html += '<div style="margin-bottom:0.35rem;"><div style="font-size:0.7rem;font-weight:600;color:rgba(255,255,255,.7);">'+(fi+1)+'. '+escHtml(f.naziv||'')+(f.trajanje?' ('+f.trajanje+')':'')+'</div>';
      (f.koraci||[]).forEach(function(k){
        var pColor = k.prioritet==='hitan'?'#ff9090':k.prioritet==='normalan'?'#89c8ff':'rgba(255,255,255,.4)';
        html += '<div style="font-size:0.68rem;color:rgba(255,255,255,.65);padding-left:0.6rem;margin-top:0.15rem;">· '+escHtml(k.korak||'')
          +(k.rok?'<span style="color:rgba(255,255,255,.3);"> ('+k.rok+')</span>':'')
          +'<span style="color:'+pColor+';margin-left:0.3rem;font-size:0.6rem;">'+escHtml(k.prioritet||'')+'</span></div>';
      });
      html += '</div>';
    });
    if ((d.upozorenja||[]).length) {
      html += '<div style="margin-top:0.35rem;padding:0.3rem 0.5rem;background:rgba(255,187,112,.07);border-left:2px solid #ffbb70;border-radius:3px;font-size:0.67rem;color:#ffbb70;">';
      d.upozorenja.slice(0,2).forEach(function(u){ html += '⚠ '+escHtml(u)+'<br>'; });
      html += '</div>';
    }
    copilot_appendMsg('bot', html);
    return;
  }

  if (tip === 'ANALIZA_PREDMETA') {
    var html = (d.procena?'<div style="font-size:0.74rem;color:#e6edf3;margin-bottom:0.35rem;">'+escHtml(d.procena)+'</div>':'');
    if ((d.prednosti||[]).length) {
      html += '<div style="font-size:0.65rem;color:#7de0a0;margin-bottom:0.2rem;">';
      d.prednosti.slice(0,3).forEach(function(p){html+='+ '+escHtml(p)+'<br>';});
      html += '</div>';
    }
    if ((d.slabosti||[]).length) {
      html += '<div style="font-size:0.65rem;color:#ff9090;">';
      d.slabosti.slice(0,3).forEach(function(s){html+='− '+escHtml(s)+'<br>';});
      html += '</div>';
    }
    if (d.verovatnoca_uspeha != null) {
      var vc = d.verovatnoca_uspeha;
      var vcColor = vc>=60?'#7de0a0':vc>=40?'#ffbb70':'#ff9090';
      html += '<div style="margin-top:0.3rem;font-size:0.68rem;color:rgba(255,255,255,.4);">Verovatnoća uspeha: <span style="color:'+vcColor+';font-weight:700;">'+vc+'%</span></div>';
    }
    copilot_appendMsg('bot', html || escHtml(d.odgovor||'Analiza završena.'));
    return;
  }

  if (tip === 'SUDSKA_PRAKSA' && d.presude) {
    var html = '<div style="font-size:0.7rem;color:#4aa8ff;margin-bottom:0.3rem;">Pronađena sudska praksa:</div>';
    (d.presude||[]).slice(0,3).forEach(function(p){
      var m = p.metadata||p;
      html += '<div style="border:1px solid rgba(255,255,255,.08);border-radius:5px;padding:0.3rem 0.5rem;margin-bottom:0.25rem;">'
        +'<div style="font-size:0.68rem;color:#89c8ff;font-weight:600;">'+(m.decision_number||m.broj_odluke||'?')+'</div>'
        +'<div style="font-size:0.65rem;color:rgba(255,255,255,.55);">'+(m.izreka_preview||m.izreka||'').substring(0,100)+'…</div>'
        +'</div>';
    });
    copilot_appendMsg('bot', html);
    return;
  }

  // Default: text response
  copilot_appendMsg('bot', '<div>'+escHtml(d.odgovor||d.poruka||JSON.stringify(d)).replace(/\n/g,'<br>')+'</div>');
}

async function pred_copilotSubmit() {
  if (!currentSession || !activePredmetId) {
    copilot_appendMsg('bot', '<span style="color:#ff9090;">Otvorite predmet pre slanja poruke.</span>');
    return;
  }
  var inp = document.getElementById('pred-copilot-input');
  var poruka = (inp ? inp.value : '').trim();
  if (!poruka) return;
  if (inp) inp.value = '';
  copilot_appendMsg('user', escHtml(poruka));
  copilot_appendMsg('bot', '<span style="color:rgba(255,255,255,.3);font-style:italic;">Obrađujem…</span>');
  var msgContainer = document.getElementById('pred-copilot-messages');
  var loadingMsg   = msgContainer ? msgContainer.lastElementChild : null;
  piTrack('copilot','query',{predmet_id:activePredmetId});
  try {
    var r = await fetch(BASE_URL+'/copilot/chat', {
      method: 'POST',
      headers: _predAuthHdr(),
      body: JSON.stringify({
        poruka:     poruka,
        predmet_id: activePredmetId,
        history:    _copilotHistory.slice(-5),
      }),
    });
    var d = await r.json();
    if (loadingMsg) loadingMsg.remove();
    copilot_renderResponse(d);
    var odgovor = d.odgovor || d.poruka || '';
    if (odgovor) {
      _copilotHistory.push({ q: poruka, a: odgovor });
      if (_copilotHistory.length > 5) _copilotHistory.shift();
    }
  } catch(e) {
    if (loadingMsg) loadingMsg.remove();
    copilot_appendMsg('bot', '<span style="color:#ff9090;">Greška pri slanju. Proverite konekciju.</span>');
  }
}

var _TIP_LABELS = {parnicno:'Parnični postupak',krivicno:'Krivični postupak',upravno:'Upravni postupak',radno:'Radno pravo',porodicno:'Porodičnopravni',nasledjivanje:'Ostavinski postupak',privredno:'Privredno pravo',nepokretnosti:'Nepokretnosti',ostalo:'Ostalo'};

function _predInlineEdit(spanId, field, inputType) {
  if (!activePredmetId || !currentSession) return;
  var span = document.getElementById(spanId);
  if (!span || span.querySelector('input,select')) return; // already editing
  var curText = span.textContent.trim();
  var curVal = curText === '—' ? '' : curText;

  var inp;
  if (inputType === 'oblast-select') {
    inp = document.createElement('select');
    var tipOpts = [['parnicno','Parnični'],['krivicno','Krivični'],['upravno','Upravni'],['radno','Radno'],['porodicno','Porodičnopravni'],['nasledjivanje','Ostavinski'],['privredno','Privredno'],['nepokretnosti','Nepokretnosti'],['ostalo','Ostalo']];
    tipOpts.forEach(function(o){var el=document.createElement('option');el.value=o[0];el.textContent=o[1];if(o[0]===curVal||_TIP_LABELS[o[0]]===curText)el.selected=true;inp.appendChild(el);});
  } else if (inputType === 'rizik-select') {
    inp = document.createElement('select');
    [['','—'],['nizak','Nizak'],['srednji','Srednji'],['visok','Visok']].forEach(function(o){var el=document.createElement('option');el.value=o[0];el.textContent=o[1];if(o[0]===curVal.toLowerCase())el.selected=true;inp.appendChild(el);});
  } else {
    inp = document.createElement('input');
    inp.type = 'text';
    inp.value = curVal;
    inp.maxLength = 200;
  }
  var isSelect = inp.tagName === 'SELECT';
  inp.style.cssText = 'width:100%;max-width:150px;padding:2px 5px;background:' + (isSelect ? '#131929' : 'rgba(255,255,255,0.12)') + ';border:1px solid rgba(74,168,255,.5);border-radius:5px;color:#e2eeff;font-size:0.78rem;outline:none;box-sizing:border-box;';

  span.style.display = 'none';
  span.parentNode.insertBefore(inp, span.nextSibling);
  inp.focus();
  if (inp.tagName === 'INPUT' && inp.select) inp.select();

  var _done = false;
  async function doSave() {
    if (_done) return; _done = true;
    var val = inp.value !== undefined ? (typeof inp.value === 'string' ? inp.value.trim() : inp.value) : '';
    inp.remove();
    span.style.display = '';

    var body = {}; body[field] = val;
    try {
      var r = await fetch(BASE_URL+'/api/predmeti/'+encodeURIComponent(activePredmetId), {
        method:'PATCH',
        headers:{'Content-Type':'application/json','Authorization':'Bearer '+currentSession.access_token},
        body:JSON.stringify(body)
      });
      if (!r.ok) { showToast('Greška pri čuvanju.','error'); return; }
      if (field === 'tip') {
        var lbl = _TIP_LABELS[val] || val; span.textContent = lbl || '—';
        var badge = document.getElementById('pred-detail-badge');
        if (badge){badge.textContent=val;badge.className='pred-badge '+val;}
      } else if (field === 'rizik') {
        span.textContent = val ? val.charAt(0).toUpperCase()+val.slice(1) : '—';
        span.style.color = val==='visok'?'#ff9090':val==='srednji'?'#ffbb70':val==='nizak'?'#7de0a0':'rgba(255,255,255,.5)';
      } else {
        span.textContent = val || '—';
      }
      var flash = document.createElement('span');
      flash.textContent = ' Sačuvano ✓';
      flash.style.cssText = 'font-size:.65rem;color:#7de0a0;margin-left:3px;';
      span.parentNode.appendChild(flash);
      setTimeout(function(){flash.remove();}, 1500);
    } catch(e) { showToast('Greška pri čuvanju.','error'); }
  }
  inp.addEventListener('blur', doSave);
  inp.addEventListener('keydown', function(e){
    if (e.key==='Enter'){e.preventDefault();doSave();}
    if (e.key==='Escape'){_done=true;inp.remove();span.style.display='';}
  });
}

async function pred_loadDetail(id) {
  if (!currentSession) return;
  piTrack('predmeti','open',{predmet_id:id});
  // Reset cockpit to loading state
  var loadEl = document.getElementById('pck-loading');
  var bodyEl = document.getElementById('pck-body');
  if (loadEl) { loadEl.textContent = '⚡ Učitavam AI procenu predmeta...'; loadEl.style.display = 'block'; }
  if (bodyEl) bodyEl.style.display = 'none';

  try {
    var r = await fetch(BASE_URL+'/api/predmeti/'+id+'/workspace', { headers: { 'Authorization':'Bearer '+currentSession.access_token } });
    if (!r.ok) { if (loadEl) loadEl.style.display='none'; return; }
    var d = await r.json();
    window._predFull = d; // globalni snapshot za auto-fill generatora

    // Timer bar: show and auto-resume if a timer was running for this predmet
    timer_showBar();
    (function() {
      var key = 'vx_timer_' + id;
      var running = JSON.parse(localStorage.getItem(key) || 'null');
      if (running && running.start) {
        // Resume display without re-setting start
        var startBtn = document.getElementById('pred-timer-start-btn');
        var stopBtn  = document.getElementById('pred-timer-stop-btn');
        if (startBtn) startBtn.style.display = 'none';
        if (stopBtn)  stopBtn.style.display  = '';
        if (_timerInterval) clearInterval(_timerInterval);
        _timerInterval = setInterval(timer_tick, 1000);
        timer_tick();
      }
    })();

    // Badge
    var badge = document.getElementById('pred-detail-badge');
    if (badge && d.predmet) {
      badge.textContent = d.predmet.tip || '';
      badge.className = 'pred-badge ' + (d.predmet.tip || '');
    }

    // Hub header meta: klijent, updated_at
    var hubKlijentEl = document.getElementById('pred-hub-klijent');
    if (hubKlijentEl) {
      var _st0 = d.stranke && d.stranke[0];
      hubKlijentEl.textContent = _st0 ? ((((_st0.ime||'')+' '+(_st0.prezime||'')).trim()) || _st0.firma || '—') : '—';
    }
    var hubUpdEl = document.getElementById('pred-hub-updated');
    if (hubUpdEl && d.predmet && d.predmet.updated_at) {
      hubUpdEl.textContent = new Date(d.predmet.updated_at).toLocaleDateString('sr-Latn-RS',{day:'2-digit',month:'2-digit',year:'numeric'});
    }

    // Dokumenti lista u Dokumenti tabu
    var dokListEl = document.getElementById('pred-dok-lista');
    if (dokListEl) {
      if (!d.dokumenti || !d.dokumenti.length) {
        dokListEl.innerHTML = '<div style="font-size:0.75rem;color:rgba(255,255,255,0.3);margin-top:0.3rem;">Nema dokumenata.</div>';
      } else {
        dokListEl.innerHTML = d.dokumenti.map(function(dok) {
          return '<div class="pred-dok-item" id="cdrow-'+escHtml(dok.id||'')+'" data-dok-id="'+escHtml(dok.id||'')+'" data-dok-naziv="'+escHtml(dok.naziv_fajla||'')+'">'
            +'<input type="checkbox" class="pred-dok-item-cb" onchange="crossdoc_toggleDok(this)" title="Odaberi za cross-doc analizu">'
            +'<i data-lucide="file-text" style="width:14px;height:14px;flex-shrink:0;color:rgba(74,168,255,0.6);"></i>'
            +'<span class="pred-dok-item-name">'+escHtml(dok.naziv_fajla||'')+'</span>'
            +'<span class="pred-dok-item-status">'+escHtml(dok.status||'')+'</span>'
            +'</div>';
        }).join('');
        if (typeof lucide !== 'undefined') lucide.createIcons();
      }
    }
    // Cross-doc section (renders once; always present when docs exist)
    var cdSecEl = document.getElementById('crossdoc-section');
    if (cdSecEl) {
      cdSecEl.style.display = (d.dokumenti && d.dokumenti.length >= 1) ? '' : 'none';
    }

    // Status panel — fill with real data from workspace
    var tuzEl = document.getElementById('pred-s-tuzilac');
    if (tuzEl) {
      if (d.predmet && d.predmet.tuzilac) {
        tuzEl.textContent = d.predmet.tuzilac;
      } else {
        var st0 = d.stranke && d.stranke[0];
        tuzEl.textContent = st0 ? (((st0.ime||'')+' '+(st0.prezime||'')).trim() || st0.firma || '—') : '—';
      }
    }
    var tuzeniEl = document.getElementById('pred-s-tuzeni');
    if (tuzeniEl) {
      if (d.predmet && d.predmet.tuzeni) {
        tuzeniEl.textContent = d.predmet.tuzeni;
      } else {
        var ps0 = d.protivna_strana && d.protivna_strana[0];
        tuzeniEl.textContent = ps0 ? (((ps0.ime||'')+' '+(ps0.prezime||'')).trim() || ps0.firma || '—') : '—';
      }
    }
    var oblEl = document.getElementById('pred-s-oblast');
    if (oblEl && d.predmet) oblEl.textContent = (_TIP_LABELS && _TIP_LABELS[d.predmet.tip]) || d.predmet.tip || '—';
    var rizikEl = document.getElementById('pred-s-rizik');
    if (rizikEl) {
      var rn = (d.predmet && d.predmet.rizik) || (d.cockpit && d.cockpit.procena_rizika && d.cockpit.procena_rizika.nivo) || '';
      rizikEl.textContent = rn ? rn.charAt(0).toUpperCase()+rn.slice(1) : '—';
      rizikEl.style.color = rn==='visok'?'#ff9090':rn==='srednji'?'#ffbb70':rn==='nizak'?'#7de0a0':'rgba(255,255,255,.5)';
    }
    var dozEl = document.getElementById('pred-s-dokazi');
    if (dozEl) dozEl.textContent = d.statistike ? d.statistike.dokumenti_count+' dok.' : '—';
    var vsEl = document.getElementById('pred-s-vrednost');
    if (vsEl && d.predmet) vsEl.textContent = d.predmet.vrednost_spora || '—';

    // Beleške
    var belEl = document.getElementById('pred-beleske-list');
    if (belEl) {
      if (!d.beleske || !d.beleske.length) {
        belEl.innerHTML = '<div style="font-size:0.75rem;color:rgba(255,255,255,0.3);">Nema beleški.</div>';
      } else {
        belEl.innerHTML = d.beleske.map(function(b){ return '<div class="beleska-item">'+escHtml(b.sadrzaj)+'</div>'; }).join('');
      }
    }

    // Istorija — timeline format
    var istEl = document.getElementById('pred-istorija-list');
    if (istEl) {
      if (!d.istorija || !d.istorija.length) {
        _predIstorijaData = [];
        istEl.innerHTML = '<div style="font-size:0.75rem;color:rgba(255,255,255,0.3);">Nema istorije razgovora.</div>';
      } else {
        _predIstorijaData = d.istorija.slice(0,15);
        var tlHtml = '<div class="pred-timeline">';
        _predIstorijaData.forEach(function(h, idx) {
          var dt = h.created_at ? new Date(h.created_at).toLocaleDateString('sr-Latn-RS',{day:'2-digit',month:'2-digit',year:'2-digit',hour:'2-digit',minute:'2-digit'}) : '';
          var akcija = (h.pitanje||'').substring(0,60);
          var hasOdgovor = h.odgovor && h.odgovor.trim();
          tlHtml += '<div class="pred-tl-item'+(hasOdgovor?' pred-tl-clickable':'')+'" data-istor-idx="'+idx+'">'
            +(dt ? '<div class="pred-tl-date">'+dt+'</div>' : '')
            +'<div class="pred-tl-q">'+escHtml(akcija)+(h.pitanje && h.pitanje.length > 60 ? '…' : '')+'</div>'
            +(hasOdgovor ? '<div class="pred-tl-hint">Klikni za prikaz analize ▾</div>' : '')
            +'</div>';
        });
        tlHtml += '</div>';
        istEl.innerHTML = tlHtml;
      }
    }

    // Cockpit
    pred_renderCockpit(d.cockpit || {}, (d.rokovi && d.rokovi.urgentni) || []);

    // Case Ready Score
    pred_renderCaseReadyScore(d.case_ready_score, d.checklist, d.copilot_preporuka);

    pred_loadHronologija(id);
    ucitajKomentare(id);
    billing_load(id);
    pred_zatvoriRenderSection(d.predmet || null);
    var _rSec = document.getElementById('pred-rokovi-section');
    if (_rSec) {
      _rSec.style.display = 'block';
      document.getElementById('pred-rokovi-rezultat').style.display = 'none';
      pred_rokokiOtvoriFormu(false);
    }
    var _uSec = document.getElementById('pred-ugovor-section');
    if (_uSec) _uSec.style.display = 'block';
    portal_showSection();
  } catch(e) {
    if (loadEl) loadEl.style.display = 'none';
  }
}

async function pred_loadHronologija(predmetId) {
  var el = document.getElementById('pred-hronologija-list');
  if (!el || !currentSession) return;
  try {
    var r = await fetch(BASE_URL + '/api/predmeti/' + predmetId + '/hronologija', {
      headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
    });
    if (!r.ok) { el.innerHTML = ''; return; }
    var d = await r.json();
    var items = d.hronologija || [];
    if (!items.length) {
      el.innerHTML = '<div style="font-size:0.75rem;color:rgba(255,255,255,0.28);">Uploadujte dokument da biste generisali hronologiju.</div>';
      return;
    }
    var html = '<div class="hron-timeline">';
    items.forEach(function(ev) {
      var v = ev.vaznost || 'informativan';
      var cls = v === 'kritičan' ? 'kritican' : v === 'važan' ? 'vazan' : 'informativan';
      var bdg = v === 'kritičan' ? 'KRITIČAN' : v === 'važan' ? 'VAŽAN' : 'INFO';
      html += '<div class="hron-item ' + cls + '">';
      if (ev.datum) {
        html += '<div class="hron-item-date">' + escHtml(ev.datum)
              + '<span class="hron-badge ' + cls + '">' + bdg + '</span>';
        if (ev.dokument_naziv) {
          html += ' <span style="font-size:0.6rem;color:rgba(255,255,255,0.22);">— ' + escHtml(ev.dokument_naziv) + '</span>';
        }
        html += '</div>';
      }
      html += '<div class="hron-item-event">' + escHtml(ev.dogadjaj) + '</div>';
      if (ev.akter) html += '<div class="hron-item-akter">→ ' + escHtml(ev.akter) + '</div>';
      html += '</div>';
    });
    html += '</div>';
    html += '<button class="hron-export-btn" onclick="pred_exportHronologija()">↓ Izvezi PDF</button>';
    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = '';
  }
}

function pred_exportHronologija() {
  // Delegate to full PDF export (Phase 5.3)
  predmetPdfExport();
}

/* ── Phase 5.3: PDF Izveštaj predmeta ───────────────────────────────────── */
async function predmetPdfExport(btn) {
  if (!activePredmetId || !currentSession) { openModal(); return; }
  var btnEl = btn || document.getElementById('pred-pdf-export-btn');
  if (btnEl) { btnEl.disabled = true; btnEl.textContent = '⏳ Generišem...'; }
  try {
    var res = await fetch(
      BASE_URL + '/api/predmeti/' + encodeURIComponent(activePredmetId) + '/pdf-export',
      { headers: { 'Authorization': 'Bearer ' + currentSession.access_token } }
    );
    if (!res.ok) {
      var err = {}; try { err = await res.json(); } catch(e2) {}
      throw new Error(err.detail || 'HTTP ' + res.status);
    }
    var blob = await res.blob();
    var url  = URL.createObjectURL(blob);
    var a    = document.createElement('a');
    var safe = (activePredmetNaziv || 'predmet').replace(/[^\w\-]/g, '_').substring(0, 40);
    a.href = url;
    a.download = 'vindex_predmet_' + safe + '.pdf';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch(e) {
    alert('Greška pri generisanju PDF-a: ' + e.message);
  } finally {
    if (btnEl) { btnEl.disabled = false; btnEl.textContent = '📄 PDF Izveštaj'; }
  }
}

function pred_openNewModal() {
  if (!currentSession) { openModal(); return; }
  var m = document.getElementById('pred-new-modal');
  if (m) { m.classList.add('open'); document.getElementById('pred-new-naziv').value=''; document.getElementById('pred-new-opis').value=''; document.getElementById('pred-new-err').style.display='none'; }
}
function pred_closeNewModal() {
  var m = document.getElementById('pred-new-modal'); if (m) m.classList.remove('open');
}
async function pred_kreiraj() {
  var naziv = (document.getElementById('pred-new-naziv').value || '').trim();
  var errEl = document.getElementById('pred-new-err');
  if (!naziv) { if (errEl) { errEl.textContent='Naziv je obavezan.'; errEl.style.display='block'; } return; }
  try {
    var r = await fetch(BASE_URL+'/api/predmeti', {
      method:'POST', headers:_predAuthHdr(),
      body: JSON.stringify({ naziv: naziv, opis: document.getElementById('pred-new-opis').value, tip: document.getElementById('pred-new-tip').value })
    });
    var d = await r.json();
    if (!r.ok) { if (errEl) { errEl.textContent=d.detail||'Greška.'; errEl.style.display='block'; } return; }
    pred_closeNewModal();
    await pred_load();
    if (d.predmet) pred_select(d.predmet.id, d.predmet.naziv);
    setTab(document.querySelector('[onclick*="\'p\'"]'), 'p');
  } catch(e) {
    if (errEl) { errEl.textContent='Greška veze.'; errEl.style.display='block'; }
  }
}

// ─── Mod-showcase: 7-modular animated terminal preview ───────────────────────
(function() {
  var MOD_LABELS = [
    'vindex-ai — Pravno istraživanje',
    'vindex-ai — Analiza predmeta',
    'vindex-ai — Generisanje nacrta',
    'vindex-ai — Sudska praksa VKS',
    'vindex-ai — Upravljanje predmetima',
    'vindex-ai — Pravna strategija',
    'vindex-ai — Digitalna imovina'
  ];

  // Each array entry = array of [text, cssClass]
  // Classes: 'hi' (heading/white), 'ok' (green), 'warn' (amber), '' (default blue-grey)
  var MOD_CONTENT = [
    // 0 — Pravno istraživanje
    [
      ['$ pitanje: "Otkazni rok za zaposlenog sa 12 godina staža?"', 'hi'],
      ['', ''],
      ['  PRAVNI OSNOV', 'warn'],
      ['  Zakon o radu, čl. 189 st. 1 tač. 1)', ''],
      ['  "Sl. glasnik RS", br. 24/2005, 61/2005, 54/2009...', ''],
      ['', ''],
      ['  ZAKONSKI TEKST (doslovan citat)', 'warn'],
      ['  "Zaposleni koji je proveo na radu kod poslodavca', ''],
      ['   od 10 do 20 godina — otkazni rok je 20 radnih dana."', 'hi'],
      ['', ''],
      ['  PRIMENA NA VAŠ SLUČAJ', 'warn'],
      ['  Staž: 12 god → kategorija 10–20 god', ''],
      ['  Otkazni rok: 20 radnih dana (~4 nedelje)', 'ok'],
      ['  Počinje teći: od dostave rešenja o otkazu', ''],
      ['', ''],
      ['  POUZDANOST  ████████░░  HIGH', 'ok'],
      ['  Osnov: direktan, čl. 189 ZR, neizmenjeno', '']
    ],
    // 1 — Analiza predmeta
    [
      ['$ predmet: "Saobraćajna nezgoda, krivica sporna, 3 žrtve"', 'hi'],
      ['', ''],
      ['  1. PRAVNA KVALIFIKACIJA', 'warn'],
      ['  KZ čl. 297 st. 3 — teška tela povreda + smrt', ''],
      ['  Kazna: 2–12 god zatvora', 'hi'],
      ['', ''],
      ['  2. KRIVICA — ključna pitanja', 'warn'],
      ['  ▸ Brzina u trenutku udara (veštak!)', ''],
      ['  ▸ Stanje vozila (tehnički pregled)', ''],
      ['  ▸ Alkohol/droge — toksikolog', ''],
      ['', ''],
      ['  3. SUDSKA PRAKSA (5 relevantnih presuda)', 'warn'],
      ['  Rev2_1788_2024 — slučna krivica, st. 2 primenjen', 'ok'],
      ['  Rev2_3015_2024 — veštak oslobodio tuženog', 'ok'],
      ['', ''],
      ['  4. PREPORUČENA STRATEGIJA', 'warn'],
      ['  Zahtevaj veštačenje odmah — rok: 8 dana', 'hi'],
      ['', ''],
      ['  POUZDANOST  ████████░░  HIGH', 'ok']
    ],
    // 2 — Generisanje nacrta
    [
      ['$ nacrt: tip=tuzba, osnov="neplacena zakupnina"', 'hi'],
      ['', ''],
      ['  Generišem nacrt...  ████████████  100%', 'ok'],
      ['', ''],
      ['  OSNOVNOM SUDU U BEOGRADU', 'hi'],
      ['', ''],
      ['  TUŽBA', 'hi'],
      ['  Tužilac: [IME KLIJENTA], JMBG [JMBG]', ''],
      ['  Tuženi:  [IME TUŽENOG], ul. [ADRESA]', ''],
      ['', ''],
      ['  Tužbeni zahtev:', 'warn'],
      ['  Obavezuje se tuženi da isplati iznos od', ''],
      ['  [IZNOS] din., sa zakonskom zateznom kamatom', ''],
      ['  počev od [DATUM] do isplate, i troškove postupka.', ''],
      ['', ''],
      ['  Činjenično stanje:', 'warn'],
      ['  Na osnovu Ugovora o zakupu od [DATUM], čl. [X],', ''],
      ['  tuženi nije platio zakupninu za [PERIOD]...', ''],
      ['', ''],
      ['  Pravni osnov: ZOO čl. 567-590', 'ok'],
      ['  ▸ Spreman za Word/PDF export', 'hi']
    ],
    // 3 — Sudska praksa
    [
      ['$ praksa: "naknada štete, nematerijalna, saobraćaj"', 'hi'],
      ['', ''],
      ['  Pretraživanje 12.604 odluka VKS...', ''],
      ['  Pronađeno: 47 relevantnih presuda', 'ok'],
      ['', ''],
      ['  TOP 3 PO RELEVANTNOSTI', 'warn'],
      ['', ''],
      ['  [1] Rev2_1788_2024 — relevantnost: 94%', 'hi'],
      ['  Sud: Vrhovni kasacioni sud, građanska mat.', ''],
      ['  Ratio: "Visina naknade ne može biti ispod', ''],
      ['   minimalnog standarda dostojanstva ličnosti."', 'ok'],
      ['', ''],
      ['  [2] Rev_10285_2025 — relevantnost: 89%', 'hi'],
      ['  Ratio: "Bolovi i strah se odmah naknadjuju', ''],
      ['   — ne čeka se konačan ishod lečenja."', 'ok'],
      ['', ''],
      ['  [3] Prev_102_2025 — relevantnost: 81%', 'hi'],
      ['  ▸ 3 filtera: oblast / sud / period', ''],
      ['  ▸ Kopiraj citiranje jednim klikom', 'hi']
    ],
    // 4 — Upravljanje predmetima
    [
      ['$ folder: "Petrović v. Beograd, radni spor"', 'hi'],
      ['', ''],
      ['  Predmet: Petrović Nikola vs. Grad Beograd', 'hi'],
      ['  Tip: Radni spor | Status: Aktivan', ''],
      ['', ''],
      ['  AI MEMORIJA SESIJA  ████████░░  8 sesija', 'warn'],
      ['  ▸ Pamti sve prethodne analize za ovaj predmet', ''],
      ['  ▸ Kontekst aktivan u svakom sledećem pitanju', ''],
      ['', ''],
      ['  DOKUMENTI (3)', 'warn'],
      ['  ✓ Rešenje o otkazu — [DATUM]', 'ok'],
      ['  ✓ Ugovor o radu — [DATUM]', 'ok'],
      ['  ✓ Zapisnik sa saslušanja', 'ok'],
      ['', ''],
      ['  ROKOVI', 'warn'],
      ['  ! Žalba APB: 15 dana → ističe [DATUM+14]', 'hi'],
      ['  ✓ Odgovor na tužbu — podneto', 'ok'],
      ['', ''],
      ['  ▸ AI nastavlja od mesta gde ste stali', 'hi']
    ],
    // 5 — AI Strategija
    [
      ['$ strategija: "krivični, prodaja PAS, okr. poreklom iz EU"', 'hi'],
      ['', ''],
      ['  MODE: Red Team  ★ PRO', 'hi'],
      ['', ''],
      ['  SLABE TAČKE OPTUŽBE', 'warn'],
      ['  ▸ Dokaz o prodaji: audio snimak bez sudskog naloga', ''],
      ['    → ZKP čl. 232 — nezakonito pribavljen', 'ok'],
      ['  ▸ Svedok X je osuđivan za isti prekršaj', ''],
      ['    → kredibilitet osporen čl. 97 ZKP', 'ok'],
      ['', ''],
      ['  MODE: Simulator suđenja', 'warn'],
      ['  Tužilac će verovatno insistirati na:', ''],
      ['  "nameri prodaje" kao aggravating factor', ''],
      ['  Kontra-argument: 1. posedovanje nije prodaja,', ''],
      ['  2. EU dokument o terapijskoj upotrebi', 'hi'],
      ['', ''],
      ['  MODE: Sudija-perspektiva', 'warn'],
      ['  Šansa za oslobađanje: 62% pri odbrani dokaza', ''],
      ['  POUZDANOST  ███████░░░  MEDIUM', 'warn']
    ],
    // 6 — Digitalna imovina
    [
      ['$ crypto: "ICO token, srpski rezidenti, 2.5M EUR"', 'hi'],
      ['', ''],
      ['  ZDI ANALIZA  ████████░░  kompletirana', 'warn'],
      ['', ''],
      ['  KLASIFIKACIJA TOKENA', 'warn'],
      ['  ▸ Tip: Utility + Security hybrid', ''],
      ['  ▸ ZDI čl. 2 tač. 8 — digitalna imovina', 'hi'],
      ['  ▸ Requires NBRS registracija pre ponude', 'hi'],
      ['', ''],
      ['  MiCA OBAVEZE (EU)', 'warn'],
      ['  ▸ White paper: obavezan, čl. 19 MiCA', ''],
      ['  ▸ Minimalni kapital: €50,000', ''],
      ['  ▸ Rok publikacije white paper-a: T-20 dana', ''],
      ['', ''],
      ['  AML AUDIT', 'warn'],
      ['  ! KYC obavezan za transakcije > €1,000', 'hi'],
      ['  ! Travel Rule: primenjuje se od €1,000', 'hi'],
      ['  ✓ Freeze mehanizam: ZDI čl. 74 — implementiran', 'ok'],
      ['', ''],
      ['  POUZDANOST  ████████░░  HIGH', 'ok']
    ]
  ];

  var currentIdx = 0;
  var autoTimer = null;
  var typeTimer = null;

  function renderLines(idx) {
    var body = document.getElementById('modBody');
    var label = document.getElementById('modLabel');
    if (!body || !label) return;
    if (typeTimer) clearTimeout(typeTimer);
    body.innerHTML = '';
    label.textContent = MOD_LABELS[idx];
    var lines = MOD_CONTENT[idx];
    var delay = 0;
    for (var i = 0; i < lines.length; i++) {
      (function(line, d) {
        typeTimer = setTimeout(function() {
          var span = document.createElement('span');
          span.className = 'mline' + (line[1] ? ' ' + line[1] : '');
          span.style.animationDelay = '0ms';
          span.textContent = line[0];
          body.appendChild(span);
          // auto-scroll preview
          body.scrollTop = body.scrollHeight;
        }, d);
      })(lines[i], delay);
      delay += (lines[i][0] === '') ? 60 : 55 + Math.random() * 25;
    }
  }

  function activateTab(idx) {
    var tabs = document.querySelectorAll('#modTabs .mod-tab');
    tabs.forEach(function(t) { t.classList.remove('mod-active'); });
    if (tabs[idx]) tabs[idx].classList.add('mod-active');
    currentIdx = idx;
    renderLines(idx);
  }

  function startAuto() {
    stopAuto();
    autoTimer = setInterval(function() {
      activateTab((currentIdx + 1) % MOD_CONTENT.length);
    }, 4800);
  }

  function stopAuto() {
    if (autoTimer) { clearInterval(autoTimer); autoTimer = null; }
  }

  function initShowcase() {
    var showcase = document.getElementById('modShowcase');
    if (!showcase) return;
    var tabs = document.querySelectorAll('#modTabs .mod-tab');
    tabs.forEach(function(tab) {
      tab.addEventListener('click', function() {
        stopAuto();
        activateTab(parseInt(tab.getAttribute('data-idx'), 10));
        startAuto();
      });
    });
    showcase.addEventListener('mouseenter', stopAuto);
    showcase.addEventListener('mouseleave', startAuto);
    // Initial render
    renderLines(0);
    startAuto();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initShowcase);
  } else {
    initShowcase();
  }
})();

// ── Billing module ──────────────────────────────────────────────────────────
var _billingPredmetId      = null;
var _billingTimerSessionId = null;
var _billingTimerStart     = null;
var _billingTimerInterval  = null;
var _billingTarifa         = [];
var _billingEntries        = [];

function _fmtBillingH(h) {
  var total = Math.round((h || 0) * 60);
  if (!total) return '';
  var hours = Math.floor(total / 60);
  var mins  = total % 60;
  if (hours && mins) return hours + ' h ' + mins + ' min';
  if (hours) return hours + ' h';
  return mins + ' min';
}

async function billing_load(predmetId) {
  _billingPredmetId = predmetId;
  await Promise.all([billing_loadTarifa(), billing_loadTimerState(), billing_loadEntries()]);
}

async function billing_loadTarifa() {
  if (_billingTarifa.length || !currentSession) return;
  try {
    var r = await fetch(BASE_URL+'/billing/tarifa', {headers:{'Authorization':'Bearer '+currentSession.access_token}});
    if (!r.ok) return;
    var d = await r.json();
    _billingTarifa = d.tarifa || [];
    var sel = document.getElementById('billing-tarifa-sel');
    if (!sel) return;
    sel.innerHTML = '<option value="">-- Tarifna stavka --</option>';
    _billingTarifa.forEach(function(t) {
      var opt = document.createElement('option');
      opt.value = t.sifra;
      var nm = t.naziv.length > 42 ? t.naziv.substring(0,42)+'…' : t.naziv;
      opt.textContent = t.sifra+' — '+nm+' ('+Math.round(t.iznos_rsd).toLocaleString('sr-RS')+' RSD)';
      opt.dataset.iznos = t.iznos_rsd;
      opt.dataset.naziv = t.naziv;
      sel.appendChild(opt);
    });
  } catch(e) {}
}

async function billing_loadTimerState() {
  if (!currentSession) return;
  try {
    var r = await fetch(BASE_URL+'/billing/timer/aktivan', {headers:{'Authorization':'Bearer '+currentSession.access_token}});
    if (!r.ok) return;
    var d = await r.json();
    if (d.aktivan && d.timer) {
      _billingTimerSessionId = d.timer.id;
      _billingTimerStart     = new Date(d.timer.start_at);
      _billing_startClockTick();
      billing_renderTimerBar(true, d.timer.predmet_id === _billingPredmetId);
    } else {
      _billingTimerSessionId = null;
      _billingTimerStart     = null;
      billing_renderTimerBar(false, false);
    }
  } catch(e) {}
}

async function billing_loadEntries() {
  if (!currentSession || !_billingPredmetId) return;
  var listEl = document.getElementById('billing-entries-list');
  var barEl  = document.getElementById('billing-faktura-bar');
  var summEl = document.getElementById('billing-summary-bar');
  if (!listEl) return;
  try {
    var r = await fetch(BASE_URL+'/billing/entries?predmet_id='+encodeURIComponent(_billingPredmetId), {headers:{'Authorization':'Bearer '+currentSession.access_token}});
    if (!r.ok) { listEl.innerHTML = ''; return; }
    var d = await r.json();
    _billingEntries = d.entries || [];
    if (summEl) {
      if (_billingEntries.length) {
        summEl.style.display = '';
        var _hTot = d.ukupno_h || 0;
        var _hStr = _hTot > 0 ? ('<span class="billing-sum-sep">·</span><span class="billing-sum-lbl">Vreme:</span> <span class="billing-sum-val">'+_fmtBillingH(_hTot)+'</span>') : '';
        summEl.innerHTML = '<span class="billing-sum-lbl">Nenaplaćeno:</span> <span class="billing-sum-val">'+Math.round(d.neobracunato_rsd||0).toLocaleString('sr-RS')+' RSD</span><span class="billing-sum-sep">·</span><span class="billing-sum-lbl">Ukupno:</span> <span class="billing-sum-val">'+Math.round(d.ukupno_rsd||0).toLocaleString('sr-RS')+' RSD</span>'+_hStr;
      } else { summEl.style.display = 'none'; }
    }
    if (!_billingEntries.length) {
      listEl.innerHTML = '<div style="font-size:0.71rem;color:rgba(255,255,255,0.22);padding:0.25rem 0;">Nema unesenih radnji za ovaj predmet.</div>';
      if (barEl) barEl.style.display = 'none';
      return;
    }
    var html = '';
    _billingEntries.forEach(function(e) {
      var iznos = Math.round(e.iznos_rsd||0).toLocaleString('sr-RS');
      var badge = e.obracunato ? '<span class="billing-badge-ok">fakturisano</span>' : '<span class="billing-badge-open">nenaplaćeno</span>';
      var hBadge = (e.sati && e.sati > 0) ? ' · <span style="color:rgba(0,212,255,0.6);font-family:\'JetBrains Mono\',monospace;">⏱ '+escHtml(_fmtBillingH(e.sati))+'</span>' : '';
      html += '<div class="billing-entry-row">';
      html += '<div class="billing-entry-main"><div class="billing-entry-opis">'+escHtml(e.opis||'')+'</div>';
      html += '<div class="billing-entry-meta">'+escHtml(e.datum||'')+(e.tarifa_sifra?' · '+escHtml(e.tarifa_sifra):'')+hBadge+'&nbsp;'+badge+'</div></div>';
      html += '<div class="billing-entry-iznos">'+iznos+' <span style="font-size:0.62rem;color:rgba(255,255,255,0.28);">RSD</span></div>';
      if (!e.obracunato) {
        html += '<button onclick="billing_deleteEntry(\''+e.id+'\')" class="billing-del-btn" title="Obriši">✕</button>';
      }
      html += '</div>';
    });
    listEl.innerHTML = html;
    var neobr = _billingEntries.filter(function(e){ return !e.obracunato; });
    if (barEl) {
      if (neobr.length) {
        var neobrSum = Math.round(neobr.reduce(function(s,e){return s+(e.iznos_rsd||0);},0));
        barEl.style.display = '';
        barEl.innerHTML = '<button class="billing-faktura-btn" onclick="billing_generateFakturaPanel()">Generiši fakturu ('+neobr.length+' stavki · '+neobrSum.toLocaleString('sr-RS')+' RSD)</button>';
      } else { barEl.style.display = 'none'; }
    }
  } catch(e) { if (listEl) listEl.innerHTML = ''; }
}

function billing_renderTimerBar(aktivan, isCurrent) {
  var lbl = document.getElementById('billing-timer-label');
  var btn = document.getElementById('billing-timer-btn');
  var clk = document.getElementById('billing-timer-clock');
  if (!lbl || !btn) return;
  if (aktivan && isCurrent) {
    lbl.textContent = '⏱ Tajmer aktivan';
    btn.textContent = '⏹ Zaustavi tajmer';
    btn.className = 'billing-timer-btn-stop';
    if (clk) clk.style.display = '';
  } else if (aktivan && !isCurrent) {
    lbl.textContent = '⏱ Tajmer aktivan na drugom predmetu';
    btn.textContent = '⏹ Zaustavi i prebaci';
    btn.className = 'billing-timer-btn-stop';
    if (clk) clk.style.display = 'none';
  } else {
    lbl.textContent = '⏱ Tajmer nije aktivan';
    btn.textContent = '▶ Start tajmer';
    btn.className = 'billing-timer-btn-start';
    if (clk) { clk.style.display = 'none'; clk.textContent = '00:00:00'; }
  }
}

function _billing_startClockTick() {
  if (_billingTimerInterval) clearInterval(_billingTimerInterval);
  _billingTimerInterval = setInterval(function() {
    var clk = document.getElementById('billing-timer-clock');
    if (!clk || !_billingTimerStart) return;
    var elapsed = Math.floor((Date.now() - _billingTimerStart.getTime()) / 1000);
    var h = Math.floor(elapsed/3600), m = Math.floor((elapsed%3600)/60), s = elapsed%60;
    clk.textContent = (h<10?'0':'')+h+':'+(m<10?'0':'')+m+':'+(s<10?'0':'')+s;
  }, 1000);
}

async function billing_timerToggle() {
  if (!currentSession) return;
  var btn = document.getElementById('billing-timer-btn');
  if (btn) btn.disabled = true;
  try {
    if (_billingTimerSessionId) { await billing_timerStop_(); }
    else { await billing_timerStart_(); }
  } finally { if (btn) btn.disabled = false; }
}

async function billing_timerStart_() {
  if (!_billingPredmetId) return;
  try {
    var r = await fetch(BASE_URL+'/billing/timer/start', {
      method:'POST', headers:{'Content-Type':'application/json','Authorization':'Bearer '+currentSession.access_token},
      body: JSON.stringify({predmet_id: _billingPredmetId})
    });
    var d = await r.json();
    if (!r.ok) { showToast(d.detail||'Greška pri pokretanju tajmera.','err'); return; }
    _billingTimerSessionId = d.timer.id;
    _billingTimerStart     = new Date(d.timer.start_at);
    var clk = document.getElementById('billing-timer-clock');
    if (clk) clk.style.display = '';
    _billing_startClockTick();
    billing_renderTimerBar(true, true);
    showToast('Tajmer pokrenut.','ok');
  } catch(e) { showToast('Greška veze.','err'); }
}

async function billing_timerStop_() {
  try {
    var r = await fetch(BASE_URL+'/billing/timer/stop', {
      method:'POST', headers:{'Content-Type':'application/json','Authorization':'Bearer '+currentSession.access_token},
      body: JSON.stringify({kreiraj_entry: true})
    });
    var d = await r.json();
    if (!r.ok) { showToast(d.detail||'Greška.','err'); return; }
    if (_billingTimerInterval) { clearInterval(_billingTimerInterval); _billingTimerInterval = null; }
    _billingTimerSessionId = null;
    _billingTimerStart     = null;
    billing_renderTimerBar(false, false);
    var hStr = (d.trajanje_h||0) < 1 ? Math.round((d.trajanje_h||0)*60)+' min' : (d.trajanje_h||0).toFixed(2)+' h';
    showToast('Tajmer zaustavljen — '+hStr+'. Radnja dodata.','ok');
    await billing_loadEntries();
  } catch(e) { showToast('Greška veze.','err'); }
}

function billing_tipChange() {
  var tip = document.getElementById('billing-tip').value;
  var selWrap = document.getElementById('billing-tarifa-sel');
  if (selWrap) selWrap.style.display = tip==='tarifa' ? '' : 'none';
}

function billing_tarifaChange() {
  var sel  = document.getElementById('billing-tarifa-sel');
  var izEl = document.getElementById('billing-iznos');
  var opEl = document.getElementById('billing-opis');
  if (!sel) return;
  var opt = sel.options[sel.selectedIndex];
  if (opt && opt.dataset.iznos) {
    if (izEl && !izEl.value) izEl.value = opt.dataset.iznos;
    if (opEl && !opEl.value) opEl.value = opt.dataset.naziv || '';
  }
}

async function billing_addEntry() {
  if (!currentSession || !_billingPredmetId) return;
  var opis  = (document.getElementById('billing-opis').value||'').trim();
  var iznos = parseFloat(document.getElementById('billing-iznos').value)||0;
  var tip   = document.getElementById('billing-tip').value||'ostalo';
  var sifra = (document.getElementById('billing-tarifa-sel').value||'') || null;
  if (!opis) { showToast('Unesite opis radnje.','err'); return; }
  if (!iznos && !sifra) { showToast('Unesite iznos ili izaberite tarifnu stavku.','err'); return; }
  var addBtn = event && event.target ? event.target : null;
  if (addBtn) addBtn.disabled = true;
  try {
    var body = {predmet_id: _billingPredmetId, opis: opis, tip: tip};
    if (sifra)  body.tarifa_sifra = sifra;
    if (iznos)  body.iznos_rsd    = iznos;
    var r = await fetch(BASE_URL+'/billing/entries', {
      method:'POST', headers:{'Content-Type':'application/json','Authorization':'Bearer '+currentSession.access_token},
      body: JSON.stringify(body)
    });
    var d = await r.json();
    if (!r.ok) { showToast(d.detail||'Greška.','err'); return; }
    document.getElementById('billing-opis').value  = '';
    document.getElementById('billing-iznos').value = '';
    document.getElementById('billing-tarifa-sel').value = '';
    showToast('Radnja dodata.','ok');
    await billing_loadEntries();
  } catch(e) { showToast('Greška veze.','err'); }
  finally { if (addBtn) addBtn.disabled = false; }
}

async function billing_deleteEntry(entryId) {
  if (!confirm('Obrisati radnju?') || !currentSession) return;
  try {
    var r = await fetch(BASE_URL+'/billing/entries/'+entryId, {method:'DELETE', headers:{'Authorization':'Bearer '+currentSession.access_token}});
    if (!r.ok) { var d=await r.json(); showToast(d.detail||'Greška.','err'); return; }
    showToast('Radnja obrisana.','ok');
    await billing_loadEntries();
  } catch(e) { showToast('Greška veze.','err'); }
}

function billing_generateFakturaPanel() {
  var barEl = document.getElementById('billing-faktura-bar');
  if (!barEl) return;
  var neobr   = _billingEntries.filter(function(e){ return !e.obracunato; });
  var ukupno  = Math.round(neobr.reduce(function(s,e){return s+(e.iznos_rsd||0);},0));
  barEl.innerHTML =
    '<div class="billing-faktura-form">'+
    '<div style="font-size:0.7rem;color:rgba(255,255,255,0.4);margin-bottom:0.45rem;">'+neobr.length+' stavki · '+ukupno.toLocaleString('sr-RS')+' RSD (bez PDV)</div>'+
    '<input id="bf-klijent" class="t-input" placeholder="Naziv klijenta *" style="font-size:0.72rem;margin-bottom:0.3rem;" autocomplete="off">'+
    '<input id="bf-adresa" class="t-input" placeholder="Adresa klijenta (opciono)" style="font-size:0.72rem;margin-bottom:0.3rem;" autocomplete="off">'+
    '<div style="display:flex;gap:0.4rem;align-items:center;margin-bottom:0.35rem;">'+
    '<input id="bf-pib" class="t-input" placeholder="PIB" style="font-size:0.72rem;width:130px;" autocomplete="off">'+
    '<span style="font-size:0.7rem;color:rgba(255,255,255,0.4);">PDV %</span>'+
    '<input id="bf-pdv" class="t-input" type="number" min="0" max="100" value="0" style="font-size:0.72rem;width:65px;">'+
    '</div>'+
    '<div style="display:flex;gap:0.35rem;">'+
    '<button onclick="billing_doGenerateFaktura()" class="billing-faktura-btn" style="flex:1;">Kreiraj fakturu</button>'+
    '<button onclick="billing_loadEntries()" style="padding:0.5rem 0.75rem;background:transparent;border:1px solid rgba(255,255,255,0.1);border-radius:7px;color:rgba(255,255,255,0.38);font-size:0.72rem;cursor:pointer;font-family:inherit;">Otkaži</button>'+
    '</div>'+
    '</div>';
}

async function billing_doGenerateFaktura() {
  var klijent = (document.getElementById('bf-klijent').value||'').trim();
  if (!klijent) { showToast('Unesite naziv klijenta.','err'); return; }
  var adresa = (document.getElementById('bf-adresa').value||'').trim();
  var pib    = (document.getElementById('bf-pib').value||'').trim();
  var pdv    = parseFloat(document.getElementById('bf-pdv').value)||0;
  var neobr  = _billingEntries.filter(function(e){ return !e.obracunato; });
  if (!neobr.length) { showToast('Nema nenaplaćenih stavki.','err'); return; }
  var btn = document.querySelector('[onclick="billing_doGenerateFaktura()"]');
  if (btn) { btn.disabled=true; btn.textContent='Kreiram...'; }
  try {
    var r = await fetch(BASE_URL+'/billing/faktura', {
      method:'POST', headers:{'Content-Type':'application/json','Authorization':'Bearer '+currentSession.access_token},
      body: JSON.stringify({
        predmet_id: _billingPredmetId,
        entry_ids:  neobr.map(function(e){return e.id;}),
        klijent_naziv: klijent,
        klijent_adresa: adresa||null,
        klijent_pib:    pib||null,
        pdv_stopa: pdv
      })
    });
    var d = await r.json();
    if (!r.ok) { showToast(d.detail||'Greška.','err'); return; }
    var fakt = d.faktura;
    var pdfUrl = BASE_URL+'/billing/faktura/'+fakt.id+'/pdf';
    var barEl = document.getElementById('billing-faktura-bar');
    if (barEl) barEl.innerHTML = '<div class="billing-faktura-ok">✓ Faktura br. <b>'+escHtml(fakt.broj_fakture)+'</b> kreirana &mdash; <a href="'+pdfUrl+'" target="_blank" style="color:#89c8ff;">Preuzmi PDF</a>'
      +' &nbsp;<button onclick="billing_sendEmail(\''+escHtml(fakt.id)+'\')" style="padding:0.2rem 0.6rem;background:rgba(74,168,255,0.1);border:1px solid rgba(74,168,255,0.25);border-radius:5px;color:#89c8ff;font-size:0.68rem;cursor:pointer;font-family:inherit;">✉ Email</button>'
      +' <button onclick="sef_posalji(\''+escHtml(fakt.id)+'\')" style="padding:0.2rem 0.6rem;background:rgba(0,212,127,0.08);border:1px solid rgba(0,212,127,0.2);border-radius:5px;color:#00d47f;font-size:0.68rem;cursor:pointer;font-family:inherit;">⚡ SEF</button>'
      +' <button onclick="sef_preuzmiXml(\''+escHtml(fakt.id)+'\')" style="padding:0.2rem 0.6rem;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:5px;color:rgba(255,255,255,0.5);font-size:0.68rem;cursor:pointer;font-family:inherit;">⬇ XML</button>'
      +' <button onclick="sef_prikaziLog(\''+escHtml(fakt.id)+'\')" style="padding:0.2rem 0.6rem;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:5px;color:rgba(255,255,255,0.5);font-size:0.68rem;cursor:pointer;font-family:inherit;">📋 SEF log</button>'
      +'</div>';
    showToast('Faktura br. '+fakt.broj_fakture+' kreirana.','ok');
    await billing_loadEntries();
  } catch(e) { showToast('Greška veze.','err'); }
  finally { if (btn) { btn.disabled=false; btn.textContent='Kreiraj fakturu'; } }
}

// ── Ponavljajuće fakture ─────────────────────────────────────────────────────

function billing_toggleRecurring(btn) {
  var sec = document.getElementById('recurring-section');
  var chv = document.getElementById('recurring-chevron');
  if (sec.style.display === 'none') {
    sec.style.display = 'block';
    if (chv) chv.textContent = '▲';
    billing_loadRecurring();
  } else {
    sec.style.display = 'none';
    if (chv) chv.textContent = '▼';
  }
}

async function billing_loadRecurring() {
  var listEl = document.getElementById('recurring-list');
  if (!listEl || !currentSession) return;
  try {
    var r = await fetch(BASE_URL+'/billing/recurring', {headers:{Authorization:'Bearer '+currentSession.access_token}});
    var d = await r.json();
    if (!r.ok) { listEl.innerHTML='<div style="font-size:0.7rem;color:rgba(255,255,255,0.3);padding:0.3rem 0;">Greška učitavanja.</div>'; return; }
    var rows = d.templates || [];
    if (!rows.length) { listEl.innerHTML='<div style="font-size:0.7rem;color:rgba(255,255,255,0.3);padding:0.3rem 0;">Nema šablona.</div>'; return; }
    listEl.innerHTML = rows.map(function(t) {
      var aktBadge = t.aktivan
        ? '<span style="background:rgba(0,212,127,0.12);color:#00d47f;border:1px solid rgba(0,212,127,0.2);border-radius:4px;font-size:0.62rem;padding:0.1rem 0.3rem;">aktivan</span>'
        : '<span style="background:rgba(255,255,255,0.05);color:rgba(255,255,255,0.3);border:1px solid rgba(255,255,255,0.08);border-radius:4px;font-size:0.62rem;padding:0.1rem 0.3rem;">neaktivan</span>';
      var uc = {'mesecno':'Mes.','kvartalno':'Kvart.','godisnje':'God.'}[t.ucestalost]||t.ucestalost;
      return '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:7px;padding:0.45rem 0.6rem;display:flex;align-items:center;gap:0.5rem;">'
        +'<div style="flex:1;min-width:0;">'
        +'<div style="font-size:0.72rem;font-weight:600;color:rgba(255,255,255,0.85);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'+escHtml(t.naziv)+'</div>'
        +'<div style="font-size:0.66rem;color:rgba(255,255,255,0.4);margin-top:0.1rem;">'+uc+' · '+(t.iznos_rsd||0).toLocaleString('sr-RS')+' RSD · sledeci: '+(t.sledeci_datum||'—')+'</div>'
        +'</div>'
        +aktBadge
        +(t.aktivan ? '<button onclick="billing_generiši(\''+escHtml(t.id)+'\')" style="padding:0.2rem 0.55rem;background:rgba(74,168,255,0.1);border:1px solid rgba(74,168,255,0.2);border-radius:5px;color:#89c8ff;font-size:0.67rem;cursor:pointer;white-space:nowrap;font-family:inherit;">Generiši</button>' : '')
        +'<button onclick="billing_deactivateRecurring(\''+escHtml(t.id)+'\','+t.aktivan+')" style="padding:0.2rem 0.4rem;background:none;border:1px solid rgba(255,255,255,0.1);border-radius:5px;color:rgba(255,255,255,0.3);font-size:0.67rem;cursor:pointer;font-family:inherit;" title="'+(t.aktivan?'Deaktiviraj':'Aktiviraj')+'">'+(t.aktivan?'⏸':'▶')+'</button>'
        +'</div>';
    }).join('');
  } catch(e) { listEl.innerHTML='<div style="font-size:0.7rem;color:rgba(255,255,255,0.3);">Greška.</div>'; }
}

function billing_showRecurringForm() {
  var form = document.getElementById('recurring-form');
  var btn  = document.getElementById('btn-new-recurring');
  if (!form) return;
  // postavi podrazumevani datum na sledeći mesec
  var d = new Date(); d.setMonth(d.getMonth()+1); d.setDate(1);
  var dateEl = document.getElementById('rec-datum');
  if (dateEl) dateEl.value = d.toISOString().slice(0,10);
  form.style.display = 'block';
  if (btn) btn.style.display = 'none';
}

async function billing_saveRecurring() {
  var naziv = (document.getElementById('rec-naziv')||{}).value.trim();
  var uc    = (document.getElementById('rec-ucestalost')||{}).value;
  var iznos = parseFloat((document.getElementById('rec-iznos')||{}).value)||0;
  var opis  = (document.getElementById('rec-opis')||{}).value.trim();
  var datum = (document.getElementById('rec-datum')||{}).value;
  var pdv   = parseFloat((document.getElementById('rec-pdv')||{}).value)||0;
  if (!naziv||!opis||!datum||iznos<=0) { showToast('Popunite sva obavezna polja.','warn'); return; }
  if (!currentSession) return;
  try {
    var r = await fetch(BASE_URL+'/billing/recurring', {
      method:'POST',
      headers:{Authorization:'Bearer '+currentSession.access_token,'Content-Type':'application/json'},
      body: JSON.stringify({naziv:naziv,ucestalost:uc,iznos_rsd:iznos,opis:opis,sledeci_datum:datum,pdv_procenat:pdv,
                            predmet_id:_billingPredmetId||null})
    });
    var d = await r.json();
    if (!r.ok) { showToast(d.detail||'Greška.','err'); return; }
    showToast('Šablon kreiran.','ok');
    document.getElementById('recurring-form').style.display='none';
    document.getElementById('btn-new-recurring').style.display='';
    // reset form
    ['rec-naziv','rec-opis'].forEach(function(id){var el=document.getElementById(id);if(el)el.value='';});
    billing_loadRecurring();
  } catch(e) { showToast('Greška veze.','err'); }
}

async function billing_generiši(templateId) {
  if (!currentSession) return;
  var btn = event && event.target;
  if (btn) { btn.disabled=true; btn.textContent='...'; }
  try {
    var r = await fetch(BASE_URL+'/billing/recurring/'+templateId+'/generisi', {
      method:'POST',
      headers:{Authorization:'Bearer '+currentSession.access_token}
    });
    var d = await r.json();
    if (!r.ok) { showToast(d.detail||'Greška.','err'); return; }
    showToast('Faktura generisana. Sledeći datum: '+d.sledeci_datum,'ok');
    billing_loadRecurring();
    billing_loadEntries();
  } catch(e) { showToast('Greška veze.','err'); }
  finally { if (btn) { btn.disabled=false; btn.textContent='Generiši'; } }
}

async function billing_deactivateRecurring(templateId, currently_active) {
  if (!currentSession) return;
  var aktivan = !currently_active;
  try {
    var r = await fetch(BASE_URL+'/billing/recurring/'+templateId, {
      method:'PATCH',
      headers:{Authorization:'Bearer '+currentSession.access_token,'Content-Type':'application/json'},
      body: JSON.stringify({aktivan:aktivan})
    });
    if (!r.ok) { var d=await r.json(); showToast(d.detail||'Greška.','err'); return; }
    showToast(aktivan?'Šablon aktiviran.':'Šablon deaktiviran.','ok');
    billing_loadRecurring();
  } catch(e) { showToast('Greška veze.','err'); }
}

async function billing_sendEmail(fakturaId) {
  if (!currentSession) return;
  var btn = event && event.target;
  if (btn) { btn.disabled=true; btn.textContent='Šaljem...'; }
  try {
    var r = await fetch(BASE_URL+'/billing/faktura/'+fakturaId+'/posalji-email', {
      method:'POST',
      headers:{Authorization:'Bearer '+currentSession.access_token}
    });
    var d = await r.json();
    if (!r.ok) { showToast(d.detail||'Greška slanja.','err'); return; }
    showToast('Email poslat na '+d.poslato_na,'ok');
    if (btn) btn.textContent='✓ Poslato';
  } catch(e) { showToast('Greška veze.','err'); }
  finally { if (btn && btn.textContent!=='✓ Poslato') { btn.disabled=false; btn.textContent='✉ Pošalji email'; } }
}



/* ═══════════════════════════════ NEXT BLOCK ═══════════════════════════════ */


// ── Global Search (Ctrl+K) ───────────────────────────────────────────────────

var _srchTimer  = null;
var _srchFilter = 'sve';
var _srchFocusIdx = -1;

document.addEventListener('keydown', function(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); searchOpen(); }
  if (e.key === 'Escape') searchClose();
  if (document.getElementById('search-modal-overlay').style.display !== 'none') {
    if (e.key === 'ArrowDown') { e.preventDefault(); searchMoveFocus(1); }
    if (e.key === 'ArrowUp')   { e.preventDefault(); searchMoveFocus(-1); }
    if (e.key === 'Enter')     { e.preventDefault(); searchActivateFocus(); }
  }
});

function searchOpen() {
  var overlay = document.getElementById('search-modal-overlay');
  overlay.style.display = 'flex';
  setTimeout(function() { var inp = document.getElementById('search-input'); if (inp) inp.focus(); }, 60);
  _srchFocusIdx = -1;
}

function searchClose() {
  document.getElementById('search-modal-overlay').style.display = 'none';
  var inp = document.getElementById('search-input'); if (inp) inp.value = '';
  document.getElementById('search-results').innerHTML = '<div style="text-align:center;padding:1.5rem;font-size:0.78rem;color:rgba(255,255,255,0.2);">Ukucajte barem 2 karaktera za pretragu</div>';
  _srchFocusIdx = -1;
}

function searchChipClick(el) {
  document.querySelectorAll('.srch-chip').forEach(function(c){ c.classList.remove('srch-chip-active'); });
  el.classList.add('srch-chip-active');
  _srchFilter = el.dataset.tip;
  searchDebounce();
}

function searchDebounce() {
  clearTimeout(_srchTimer);
  _srchTimer = setTimeout(searchRun, 280);
}

async function searchRun() {
  var q = (document.getElementById('search-input')||{}).value.trim();
  var resEl = document.getElementById('search-results');
  if (!resEl) return;
  if (q.length < 2) {
    resEl.innerHTML = '<div style="text-align:center;padding:1.5rem;font-size:0.78rem;color:rgba(255,255,255,0.2);">Ukucajte barem 2 karaktera za pretragu</div>';
    return;
  }
  if (!currentSession) { resEl.innerHTML = '<div style="padding:1rem;font-size:0.78rem;color:rgba(255,255,255,0.3);">Prijavite se.</div>'; return; }
  resEl.innerHTML = '<div style="text-align:center;padding:1.5rem;font-size:0.78rem;color:rgba(255,255,255,0.25);">Pretražujem...</div>';

  var url = BASE_URL+'/api/search?q='+encodeURIComponent(q)+'&limit=6';
  if (_srchFilter !== 'sve') url += '&vrste='+encodeURIComponent(_srchFilter);

  try {
    var r = await fetch(url, {headers:{Authorization:'Bearer '+currentSession.access_token}});
    var d = await r.json();
    if (!r.ok) { resEl.innerHTML='<div style="padding:1rem;font-size:0.78rem;color:rgba(255,100,100,0.6);">'+(d.detail||'Greška.')+'</div>'; return; }
    searchRenderResults(d);
  } catch(e) { resEl.innerHTML='<div style="padding:1rem;font-size:0.78rem;color:rgba(255,100,100,0.6);">Greška veze.</div>'; }
}

var _SRCH_ICONS = {
  predmet:    {icon:'⚖️',  bg:'rgba(0,212,127,0.10)', label:'Predmet'},
  klijent:    {icon:'👤',  bg:'rgba(74,168,255,0.10)', label:'Klijent'},
  dokument:   {icon:'📄',  bg:'rgba(255,200,100,0.10)',label:'Dokument'},
  billing:    {icon:'💰',  bg:'rgba(0,212,255,0.10)',  label:'Billing'},
  hronologija:{icon:'📅',  bg:'rgba(200,100,255,0.10)',label:'Hronolog.'},
  beleska:    {icon:'📝',  bg:'rgba(255,255,255,0.06)',label:'Beleška'},
};
var _SRCH_ORDER = ['predmeti','klijenti','dokumenti','billing','hronologija','beleske'];
var _TIP_MAP    = {predmeti:'predmet',klijenti:'klijent',dokumenti:'dokument',billing:'billing',hronologija:'hronologija',beleske:'beleska'};

function searchRenderResults(d) {
  var resEl = document.getElementById('search-results');
  if (!resEl) return;
  if (!d.ukupno) {
    resEl.innerHTML='<div style="text-align:center;padding:2rem 1rem;font-size:0.78rem;color:rgba(255,255,255,0.2);">Nema rezultata za „'+escHtml(d.q)+'"</div>';
    return;
  }
  var html = '';
  _SRCH_ORDER.forEach(function(skupina) {
    var rows = d[skupina];
    if (!rows || !rows.length) return;
    var tipKey = _TIP_MAP[skupina];
    var meta   = _SRCH_ICONS[tipKey] || {icon:'📌',bg:'rgba(255,255,255,0.05)',label:skupina};
    html += '<div class="srch-group-hd">'+meta.label+' ('+rows.length+')</div>';
    rows.forEach(function(item) {
      var action = searchBuildAction(item);
      html += '<div class="srch-item" onclick="'+action+';searchClose()" data-action="'+escHtml(action)+'">'
        +'<div class="srch-item-icon" style="background:'+meta.bg+'">'+meta.icon+'</div>'
        +'<div class="srch-item-body">'
        +'<div class="srch-item-naziv">'+escHtml(item.naziv||'—')+'</div>'
        +(item.preview ? '<div class="srch-item-prev">'+escHtml(item.preview)+'</div>' : '')
        +'</div></div>';
    });
  });
  resEl.innerHTML = html;
  _srchFocusIdx = -1;
}

function searchBuildAction(item) {
  var pid = (item.meta||{}).predmet_id;
  if (item.tip === 'predmet')    return 'openPredmet(\''+item.id+'\')';
  if (item.tip === 'klijent')    return 'openCrmKlijent && openCrmKlijent(\''+item.id+'\')';
  if (pid)                       return 'openPredmet(\''+pid+'\')';
  return 'void 0';
}

function searchMoveFocus(dir) {
  var items = document.querySelectorAll('#search-results .srch-item');
  if (!items.length) return;
  items.forEach(function(el){ el.classList.remove('srch-focus'); });
  _srchFocusIdx = Math.max(0, Math.min(items.length-1, _srchFocusIdx + dir));
  var el = items[_srchFocusIdx];
  el.classList.add('srch-focus');
  el.scrollIntoView({block:'nearest'});
}

function searchActivateFocus() {
  var el = document.querySelector('#search-results .srch-item.srch-focus');
  if (el) el.click();
}

// ── Klijentski portal ────────────────────────────────────────────────────────

var _portalCurrentUrl = '';

function portal_showSection() {
  var sec = document.getElementById('pred-portal-section');
  if (sec) sec.style.display = 'block';
  portal_loadUploads();
}

function portal_toggleForm() {
  var form = document.getElementById('portal-form');
  var res  = document.getElementById('portal-result');
  if (!form) return;
  var open = form.style.display !== 'none';
  form.style.display  = open ? 'none' : 'block';
  if (res) res.style.display = 'none';
  if (!open) portal_loadTokens();
}

async function portal_generateLink() {
  if (!currentSession || !activePredmetId) return;
  var email = (document.getElementById('portal-email') || {}).value || '';
  var days  = parseInt((document.getElementById('portal-days') || {}).value || '30');
  var btn   = document.getElementById('portal-gen-btn');
  if (btn) { btn.disabled=true; btn.textContent='Generišem...'; }
  try {
    var r = await fetch(BASE_URL+'/api/client-portal/token/'+activePredmetId, {
      method:'POST', headers:{'Content-Type':'application/json','Authorization':'Bearer '+currentSession.access_token},
      body: JSON.stringify({klijent_email: email||null, valjanost_dana: days})
    });
    var d = await r.json();
    if (!r.ok) { showToast(d.detail||'Greška.','err'); return; }
    _portalCurrentUrl = d.portal_url;
    var urlEl = document.getElementById('portal-url-text');
    if (urlEl) urlEl.textContent = d.portal_url;
    var formEl = document.getElementById('portal-form');
    var resEl  = document.getElementById('portal-result');
    if (formEl) formEl.style.display = 'none';
    if (resEl)  resEl.style.display  = 'block';
    showToast('Portal link kreiran (važi '+days+' dana).','ok');
    await portal_loadTokens();
  } catch(e) { showToast('Greška veze.','err'); }
  finally { if (btn) { btn.disabled=false; btn.textContent='Generiši link'; } }
}

async function portal_loadTokens() {
  if (!currentSession || !activePredmetId) return;
  var listEl = document.getElementById('portal-tokens-list');
  if (!listEl) return;
  try {
    var r = await fetch(BASE_URL+'/api/client-portal/tokens/'+activePredmetId, {headers:{Authorization:'Bearer '+currentSession.access_token}});
    if (!r.ok) return;
    var d = await r.json();
    var tokeni = d.tokeni || [];
    if (!tokeni.length) { listEl.innerHTML='<div style="font-size:.68rem;color:rgba(255,255,255,.25);">Nema aktivnih linkova.</div>'; return; }
    listEl.innerHTML = tokeni.map(function(t){
      var aktivan = t.is_active;
      var exp = (t.expires_at||'').slice(0,10);
      var email = t.klijent_email ? (' · '+escHtml(t.klijent_email)) : '';
      return '<div style="display:flex;align-items:center;gap:.5rem;padding:.3rem 0;border-bottom:1px solid rgba(255,255,255,.04);">'
        +'<div style="flex:1;min-width:0;">'
        +'<span style="font-size:.67rem;color:'+(aktivan?'#00d47f':'rgba(255,255,255,.25)')+';">'+(aktivan?'● aktivan':'○ opozvan')+'</span>'
        +'<span style="font-size:.65rem;color:rgba(255,255,255,.3);">'+email+' · ističe '+exp+'</span>'
        +'</div>'
        +(aktivan ? '<button onclick="portal_revokeToken(\''+escHtml(t.id)+'\')" style="font-size:.62rem;color:rgba(255,80,80,.6);background:none;border:1px solid rgba(255,80,80,.15);border-radius:4px;padding:.15rem .4rem;cursor:pointer;white-space:nowrap;">Opozovi</button>' : '')
        +'</div>';
    }).join('');
  } catch(e) {}
}

function portal_copyLink() {
  if (!_portalCurrentUrl) return;
  navigator.clipboard.writeText(_portalCurrentUrl).then(function(){
    showToast('Link kopiran.','ok');
  }).catch(function(){
    prompt('Kopirajte link:', _portalCurrentUrl);
  });
}

async function portal_revokeToken(tokenId) {
  if (!currentSession || !confirm('Opozvati ovaj portal link? Klijent više neće moći da ga koristi.')) return;
  try {
    var r = await fetch(BASE_URL+'/api/client-portal/token/'+tokenId, {
      method:'DELETE', headers:{Authorization:'Bearer '+currentSession.access_token}
    });
    if (!r.ok) { showToast('Greška pri opozivanju.','err'); return; }
    showToast('Link opozvan.','ok');
    await portal_loadTokens();
  } catch(e) { showToast('Greška.','err'); }
}

async function portal_loadUploads() {
  if (!currentSession || !activePredmetId) return;
  var listEl = document.getElementById('portal-uploads-list');
  if (!listEl) return;
  listEl.textContent = 'Učitavam...';
  try {
    var r = await fetch(BASE_URL+'/api/client-portal/uploads/'+activePredmetId, {
      headers:{Authorization:'Bearer '+currentSession.access_token}
    });
    var d = await r.json();
    if (!r.ok) { listEl.textContent = d.detail || 'Greška.'; return; }
    var upl = d.uploadi || [];
    if (!upl.length) { listEl.innerHTML = '<div style="color:rgba(255,255,255,.25);">Nema dostavljenih dokumenata.</div>'; return; }
    listEl.innerHTML = upl.map(function(u){
      var pregBoja = u.pregledano ? 'rgba(255,255,255,.25)' : '#ffc864';
      var pregTxt  = u.pregledano ? 'pregledano' : '● novo';
      var datum    = (u.uploaded_at||'').slice(0,16).replace('T',' ');
      var velKB    = u.fajl_velicina ? Math.round(u.fajl_velicina/1024)+' KB' : '';
      return '<div style="padding:.35rem 0;border-bottom:1px solid rgba(255,255,255,.04);display:flex;align-items:flex-start;gap:.5rem;">'
        +'<div style="flex:1;min-width:0;">'
        +'<div style="font-size:.72rem;color:rgba(255,255,255,.7);font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">📄 '+escHtml(u.fajl_naziv||'dokument')+'</div>'
        +'<div style="font-size:.63rem;color:rgba(255,255,255,.3);margin-top:.1rem;">'+datum+(velKB?' · '+velKB:'')+'</div>'
        +(u.napomena?'<div style="font-size:.65rem;color:rgba(255,255,255,.4);margin-top:.1rem;font-style:italic;">'+escHtml(u.napomena)+'</div>':'')
        +'</div>'
        +'<div style="display:flex;flex-direction:column;align-items:flex-end;gap:.25rem;flex-shrink:0;">'
        +'<span style="font-size:.6rem;color:'+pregBoja+';">'+pregTxt+'</span>'
        +(u.download_url ? '<a href="'+u.download_url+'" target="_blank" rel="noopener" style="font-size:.62rem;color:#89c8ff;text-decoration:none;">⬇ Preuzmi</a>' : '')
        +(!u.pregledano ? '<button onclick="portal_oznacPregledano(\''+escHtml(u.id)+'\')" style="font-size:.6rem;color:rgba(0,212,127,.6);background:none;border:1px solid rgba(0,212,127,.15);border-radius:3px;padding:.1rem .3rem;cursor:pointer;">✓ Pregledano</button>' : '')
        +'<button onclick="portal_obrisiUpload(\''+escHtml(u.id)+'\')" style="font-size:.6rem;color:rgba(255,80,80,.5);background:none;border:none;cursor:pointer;padding:0;">🗑</button>'
        +'</div>'
        +'</div>';
    }).join('');
  } catch(e) { listEl.textContent = 'Greška veze.'; }
}

async function portal_oznacPregledano(uploadId) {
  if (!currentSession) return;
  try {
    await fetch(BASE_URL+'/api/client-portal/uploads/'+uploadId+'/pregledano', {
      method:'PATCH', headers:{Authorization:'Bearer '+currentSession.access_token}
    });
    await portal_loadUploads();
  } catch(e) {}
}

async function portal_obrisiUpload(uploadId) {
  if (!currentSession || !confirm('Obrisati ovaj dokument? Ova akcija je nepovratna.')) return;
  try {
    var r = await fetch(BASE_URL+'/api/client-portal/uploads/'+uploadId, {
      method:'DELETE', headers:{Authorization:'Bearer '+currentSession.access_token}
    });
    if (!r.ok) { showToast('Greška pri brisanju.','err'); return; }
    showToast('Dokument obrisan.','ok');
    await portal_loadUploads();
  } catch(e) { showToast('Greška.','err'); }
}

// ── Portal klijentski view ────────────────────────────────────────────────────

async function portal_init() {
  var params = new URLSearchParams(window.location.search);
  var token  = params.get('token');
  if (!token) return false;

  // Sakrij app, prikaži portal view
  var shell   = document.getElementById('vx-shell');
  var landing = document.getElementById('vx-landing');
  var view    = document.getElementById('portal-view');
  if (shell)   shell.style.display   = 'none';
  if (landing) landing.style.display = 'none';
  if (view)    view.style.display    = 'block';

  var loadingEl = document.getElementById('portal-loading');
  var errorEl   = document.getElementById('portal-error');
  var contentEl = document.getElementById('portal-content');

  try {
    var r = await fetch(BASE_URL+'/api/client-portal/view', {
      headers:{'X-Portal-Token': token}
    });
    var d = await r.json();
    if (!r.ok) {
      if (loadingEl) loadingEl.style.display = 'none';
      if (errorEl) { errorEl.style.display='block'; errorEl.textContent = d.detail || 'Token nije validan ili je istekao.'; }
      return true;
    }
    if (loadingEl) loadingEl.style.display = 'none';
    if (contentEl) contentEl.style.display = 'block';
    portal_renderView(d);
  } catch(e) {
    if (loadingEl) loadingEl.style.display = 'none';
    if (errorEl) { errorEl.style.display='block'; errorEl.textContent='Greška veze sa serverom.'; }
  }
  return true;
}

function portal_renderView(d) {
  var pred = d.predmet || {};
  var nazEl = document.getElementById('portal-pred-naziv');
  var staEl = document.getElementById('portal-pred-status');
  var tipEl = document.getElementById('portal-pred-tip');
  var opisEl= document.getElementById('portal-pred-opis');
  var expEl = document.getElementById('portal-exp');

  if (nazEl) nazEl.textContent  = pred.naziv || 'Predmet';
  if (opisEl) opisEl.textContent = pred.opis  || '';
  if (tipEl)  tipEl.textContent  = pred.tip   || '';
  if (expEl && d.token_expires_at) expEl.textContent = 'Pristup ističe: '+(d.token_expires_at||'').slice(0,10);

  var statusColor = {aktivan:'rgba(0,212,127,.15)',zatvoren:'rgba(255,255,255,.06)',arhiviran:'rgba(255,255,255,.04)'}[pred.status]||'rgba(74,168,255,.1)';
  var statusText  = {aktivan:'Aktivan',zatvoren:'Zatvoren',arhiviran:'Arhiviran'}[pred.status]||pred.status||'';
  if (staEl) { staEl.textContent=statusText; staEl.style.background=statusColor; staEl.style.color=pred.status==='aktivan'?'#00d47f':'rgba(255,255,255,.5)'; }

  // Ročišta
  var roc = d.rocista || [];
  if (roc.length) {
    var rocSec  = document.getElementById('portal-roc-section');
    var rocList = document.getElementById('portal-roc-list');
    if (rocSec) rocSec.style.display = 'block';
    if (rocList) rocList.innerHTML = roc.map(function(r){
      var boja = r.status==='zakazano'?'#ffbb70':'rgba(255,255,255,.4)';
      return '<div style="border:1px solid rgba(255,255,255,.07);border-radius:8px;padding:.6rem .8rem;margin-bottom:.4rem;">'
        +'<div style="display:flex;align-items:center;gap:.6rem;">'
        +'<span style="font-size:.75rem;font-weight:600;color:'+boja+';">'+escHtml(r.datum||'')+(r.vreme?' u '+escHtml(r.vreme):'')+'</span>'
        +'<span style="font-size:.65rem;color:rgba(255,255,255,.35);margin-left:auto;">'+escHtml(r.status||'')+'</span>'
        +'</div>'
        +'<div style="font-size:.78rem;color:rgba(255,255,255,.7);margin-top:.25rem;">'+escHtml(r.sud||'')+(r.sudnica?' — sudnica '+escHtml(r.sudnica):'')+'</div>'
        +(r.broj_predmeta_suda?'<div style="font-size:.67rem;color:rgba(255,255,255,.3);margin-top:.15rem;">Br. predmeta: '+escHtml(r.broj_predmeta_suda)+'</div>':'')
        +'</div>';
    }).join('');
  }

  // Hronologija
  var hron = d.hronologija || [];
  if (hron.length) {
    var hronSec  = document.getElementById('portal-hron-section');
    var hronList = document.getElementById('portal-hron-list');
    if (hronSec) hronSec.style.display = 'block';
    if (hronList) hronList.innerHTML = hron.map(function(h,i){
      var isLast = i === hron.length-1;
      return '<div style="display:flex;gap:.75rem;padding-bottom:.8rem;">'
        +'<div style="display:flex;flex-direction:column;align-items:center;flex-shrink:0;">'
        +'<div style="width:8px;height:8px;border-radius:50%;background:'+(isLast?'#00d4ff':'rgba(74,168,255,.4)')+';""></div>'
        +(isLast?'':'<div style="flex:1;width:1px;background:rgba(255,255,255,.07);margin-top:2px;"></div>')
        +'</div>'
        +'<div style="flex:1;min-width:0;padding-bottom:.2rem;">'
        +'<div style="font-size:.72rem;color:rgba(255,255,255,.35);margin-bottom:.15rem;">'+escHtml(h.datum_iso||h.datum||'')+'</div>'
        +'<div style="font-size:.82rem;color:#e6edf3;line-height:1.4;">'+escHtml(h.dogadjaj||'')+'</div>'
        +(h.akter?'<div style="font-size:.67rem;color:rgba(255,255,255,.3);margin-top:.1rem;">'+escHtml(h.akter)+'</div>':'')
        +'</div>'
        +'</div>';
    }).join('');
  }
}

// ── Portal upload (klijent šalje fajl advokatu) ───────────────────────────────

var _portalToken = null;
var _portalFile  = null;

(function() {
  var params = new URLSearchParams(window.location.search);
  _portalToken = params.get('token') || null;
})();

function portal_fileSelected(input) {
  var f = input.files && input.files[0];
  if (!f) return;
  _portalFile = f;
  var nameEl = document.getElementById('portal-file-name');
  var prevEl = document.getElementById('portal-file-preview');
  var btn    = document.getElementById('portal-upload-btn');
  if (nameEl) nameEl.textContent = f.name + ' (' + (f.size/1024).toFixed(0) + ' KB)';
  if (prevEl) prevEl.style.display = 'flex';
  if (btn)    { btn.disabled = false; btn.style.cursor = 'pointer'; btn.style.background = 'rgba(0,212,255,0.18)'; }
}

function portal_fileOtkazi() {
  _portalFile = null;
  var input  = document.getElementById('portal-file-input');
  var prevEl = document.getElementById('portal-file-preview');
  var btn    = document.getElementById('portal-upload-btn');
  if (input)  input.value = '';
  if (prevEl) prevEl.style.display = 'none';
  if (btn)    { btn.disabled = true; btn.style.cursor = 'not-allowed'; btn.style.background = 'rgba(0,212,255,0.12)'; }
}

async function portal_uploadFajl() {
  if (!_portalToken || !_portalFile) return;
  var btn    = document.getElementById('portal-upload-btn');
  var okEl   = document.getElementById('portal-upload-ok');
  var errEl  = document.getElementById('portal-upload-err');
  var napEl  = document.getElementById('portal-napomena');

  if (okEl)  okEl.style.display  = 'none';
  if (errEl) errEl.style.display = 'none';
  if (btn)   { btn.disabled = true; btn.textContent = 'Šaljem...'; }

  var napomena = napEl ? napEl.value.trim() : '';
  var fd = new FormData();
  fd.append('fajl', _portalFile);
  if (napomena) fd.append('napomena', napomena);

  try {
    var r = await fetch(BASE_URL + '/api/client-portal/dokument', {
      method: 'POST',
      headers: {'X-Portal-Token': _portalToken},
      body: fd,
    });
    var d = await r.json();
    if (!r.ok) {
      if (errEl) { errEl.style.display = 'block'; errEl.textContent = d.detail || 'Greška pri slanju.'; }
    } else {
      if (okEl) { okEl.style.display = 'block'; okEl.textContent = '✓ ' + (d.poruka || 'Dokument dostavljen advokatu.'); }
      portal_fileOtkazi();
      if (napEl) napEl.value = '';
    }
  } catch(e) {
    if (errEl) { errEl.style.display = 'block'; errEl.textContent = 'Greška veze. Pokušajte ponovo.'; }
  } finally {
    if (btn) { btn.textContent = '⬆ Pošalji dokument'; }
  }
}

// ── SEF e-Faktura ────────────────────────────────────────────────────────────

async function sef_loadSettings() {
  if (!currentSession) return;
  try {
    var r = await fetch(BASE_URL+'/api/sef/podesavanja', {headers:{Authorization:'Bearer '+currentSession.access_token}});
    if (!r.ok) return;
    var d = await r.json();
    var badge = document.getElementById('sef-status-badge');
    if (d.konfigurisano && d.podaci) {
      var p = d.podaci;
      var el = function(id, v) { var e = document.getElementById(id); if (e && v) e.value = v; };
      el('sef-pib',    p.seller_pib);
      el('sef-naziv',  p.seller_naziv);
      el('sef-adresa', p.seller_adresa);
      el('sef-mesto',  p.seller_mesto);
      if (badge) {
        badge.style.display = 'inline-block';
        badge.style.background = 'rgba(0,212,127,0.1)';
        badge.style.color = '#00d47f';
        badge.style.border = '1px solid rgba(0,212,127,0.2)';
        badge.textContent = '✓ KONFIGURISANO · ' + (p.api_key_preview || '');
      }
    } else {
      if (badge) {
        badge.style.display = 'inline-block';
        badge.style.background = 'rgba(255,187,112,0.08)';
        badge.style.color = '#ffbb70';
        badge.style.border = '1px solid rgba(255,187,112,0.2)';
        badge.textContent = '⚠ NIJE KONFIGURISANO';
      }
    }
  } catch(e) {}
}

async function sef_saveSettings() {
  if (!currentSession) return;
  var pib    = (document.getElementById('sef-pib')    || {}).value || '';
  var naziv  = (document.getElementById('sef-naziv')  || {}).value || '';
  var adresa = (document.getElementById('sef-adresa') || {}).value || '';
  var mesto  = (document.getElementById('sef-mesto')  || {}).value || 'Beograd';
  var apikey = (document.getElementById('sef-apikey') || {}).value || '';

  if (pib.length !== 9 || !/^\d{9}$/.test(pib)) { showToast('PIB mora biti tačno 9 cifara.','err'); return; }
  if (naziv.trim().length < 2) { showToast('Unesite naziv kancelarije.','err'); return; }

  // api_key je opcionalan ako je SEF već konfigurisan — backend čuva stari ključ
  var body = {seller_pib: pib, seller_naziv: naziv, seller_adresa: adresa, seller_mesto: mesto};
  if (apikey.trim()) body.api_key = apikey.trim();

  var btn = document.getElementById('sef-save-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Čuvam...'; }
  try {
    var r = await fetch(BASE_URL+'/api/sef/podesavanja', {
      method:'POST', headers:{'Content-Type':'application/json','Authorization':'Bearer '+currentSession.access_token},
      body: JSON.stringify(body)
    });
    var d = await r.json();
    if (!r.ok) { showToast(d.detail||'Greška.','err'); return; }
    showToast('SEF podešavanja sačuvana.','ok');
    var msg = document.getElementById('sef-save-msg');
    if (msg) { msg.style.display='flex'; setTimeout(function(){ msg.style.display='none'; }, 3000); }
    await sef_loadSettings();
    var apiEl = document.getElementById('sef-apikey');
    if (apiEl) apiEl.value = '';
  } catch(e) { showToast('Greška veze.','err'); }
  finally { if (btn) { btn.disabled=false; btn.textContent='Sačuvaj SEF'; } }
}

async function sef_posalji(fakturaId) {
  if (!currentSession || !fakturaId) return;
  if (!confirm('Poslati fakturu na SEF sistem e-faktura?')) return;
  showToast('Šaljem na SEF...','ok');
  try {
    var r = await fetch(BASE_URL+'/api/sef/posalji/'+fakturaId, {
      method:'POST', headers:{Authorization:'Bearer '+currentSession.access_token}
    });
    var d = await r.json();
    if (!r.ok) { showToast((d.detail||'SEF greška.'),'err'); return; }
    showToast('✓ SEF ID: '+d.sef_id+' — '+d.sef_status,'ok');
  } catch(e) { showToast('Greška veze.','err'); }
}

async function sef_preuzmiXml(fakturaId) {
  if (!currentSession || !fakturaId) return;
  try {
    var r = await fetch(BASE_URL+'/api/sef/pregled-xml/'+fakturaId, {
      headers:{Authorization:'Bearer '+currentSession.access_token}
    });
    if (!r.ok) {
      var d = await r.json().catch(function(){return {};});
      showToast(d.detail||'Greška pri generisanju XML-a.','err'); return;
    }
    var blob = await r.blob();
    var cd = r.headers.get('Content-Disposition') || '';
    var fname = 'sef_faktura.xml';
    var m = cd.match(/filename="([^"]+)"/);
    if (m) fname = m[1];
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = fname;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('UBL XML preuzet: '+fname,'ok');
  } catch(e) { showToast('Greška veze.','err'); }
}

async function sef_prikaziLog(fakturaId) {
  if (!currentSession || !fakturaId) return;
  try {
    var r = await fetch(BASE_URL+'/api/sef/log/'+fakturaId, {
      headers:{Authorization:'Bearer '+currentSession.access_token}
    });
    var d = await r.json();
    var log = d.log || [];
    if (!log.length) { showToast('Nema SEF log zapisa za ovu fakturu.','ok'); return; }
    var txt = log.map(function(l){
      return (l.poslato_at||'').slice(0,19).replace('T',' ')
        + ' — ' + (l.sef_status||'?')
        + (l.sef_id ? ' (ID: '+l.sef_id+')' : '')
        + (l.greska ? '\n   Greška: '+l.greska : '');
    }).join('\n');
    alert('SEF log (poslednih ' + log.length + '):\n\n' + txt);
  } catch(e) { showToast('Greška veze.','err'); }
}

// ── Billing Izveštaji ────────────────────────────────────────────────────────

function billing_toggleReports(btn) {
  var sec = document.getElementById('reports-section');
  var chv = document.getElementById('reports-chevron');
  if (!sec) return;
  var open = sec.style.display !== 'none';
  sec.style.display = open ? 'none' : 'block';
  if (chv) chv.textContent = open ? '▼' : '▲';
}

async function billing_openReport(tip) {
  var resEl = document.getElementById('billing-report-result');
  if (!resEl || !currentSession) return;
  resEl.style.display = 'block';
  resEl.innerHTML = '<div style="color:rgba(255,255,255,0.3);padding:0.5rem 0;">Učitavam...</div>';

  var today = new Date();
  var yr = today.getFullYear();
  var od  = yr + '-01-01';
  var url = '';
  if (tip === 'godisnji')   url = BASE_URL + '/billing/report/godisnji?godina=' + yr;
  if (tip === 'zastarele')  url = BASE_URL + '/billing/report/zastarele';
  if (tip === 'po-tipu')    url = BASE_URL + '/billing/report/po-tipu?od=' + od + '&do=' + today.toISOString().slice(0,10);
  if (tip === 'po-klijentu') url = BASE_URL + '/billing/report/po-klijentu?od=' + od + '&do=' + today.toISOString().slice(0,10);

  try {
    var r = await fetch(url, {headers:{Authorization:'Bearer '+currentSession.access_token}});
    var d = await r.json();
    if (!r.ok) { resEl.innerHTML='<div style="color:rgba(255,100,100,0.7);">'+(d.detail||'Greška.')+'</div>'; return; }
    resEl.innerHTML = billing_renderReport(tip, d);
  } catch(e) { resEl.innerHTML='<div style="color:rgba(255,100,100,0.7);">Greška veze.</div>'; }
}

function billing_renderReport(tip, d) {
  if (tip === 'godisnji') {
    return '<div style="font-weight:600;margin-bottom:0.35rem;color:rgba(255,255,255,0.7);">Godišnji izveštaj '+(d.godina||'')+'</div>'
      +'<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.25rem;margin-bottom:0.4rem;">'
      +'<div style="background:rgba(0,212,127,0.07);border:1px solid rgba(0,212,127,0.15);border-radius:6px;padding:0.35rem;"><div style="font-size:0.62rem;color:rgba(255,255,255,0.35);">Uneseno</div><div style="font-size:0.82rem;font-weight:700;color:#00d47f;">'+Math.round(d.ukupno_uneseno_rsd||0).toLocaleString('sr-RS')+' RSD</div></div>'
      +'<div style="background:rgba(74,168,255,0.07);border:1px solid rgba(74,168,255,0.15);border-radius:6px;padding:0.35rem;"><div style="font-size:0.62rem;color:rgba(255,255,255,0.35);">Naplaćeno</div><div style="font-size:0.82rem;font-weight:700;color:#89c8ff;">'+Math.round(d.ukupno_naplaceno_rsd||0).toLocaleString('sr-RS')+' RSD</div></div>'
      +'<div style="background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.1);border-radius:6px;padding:0.35rem;"><div style="font-size:0.62rem;color:rgba(255,255,255,0.35);">Fakturisano</div><div style="font-size:0.82rem;font-weight:600;color:#00d4ff;">'+Math.round(d.ukupno_fakturisano||0).toLocaleString('sr-RS')+' RSD</div></div>'
      +'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:6px;padding:0.35rem;"><div style="font-size:0.62rem;color:rgba(255,255,255,0.35);">Stopa naplate</div><div style="font-size:0.82rem;font-weight:600;color:rgba(255,255,255,0.7);">'+(d.stopa_naplate_pct||0)+'%</div></div>'
      +'</div>'
      +(d.top_klijenti && d.top_klijenti.length ? '<div style="font-size:0.65rem;color:rgba(255,255,255,0.35);margin-bottom:0.2rem;">TOP KLIJENTI</div>'
        +d.top_klijenti.slice(0,3).map(function(k){ return '<div style="display:flex;justify-content:space-between;padding:0.15rem 0;font-size:0.7rem;"><span style="color:rgba(255,255,255,0.6);">'+escHtml(k.naziv||'—')+'</span><span style="color:#89c8ff;font-weight:600;">'+Math.round(k.iznos).toLocaleString('sr-RS')+' RSD</span></div>'; }).join('') : '');
  }
  if (tip === 'zastarele') {
    var aging = d.aging || {};
    return '<div style="font-weight:600;margin-bottom:0.35rem;color:rgba(255,255,255,0.7);">Starele nenaplaćene stavke</div>'
      +'<div style="font-size:0.8rem;font-weight:700;color:#ff9966;margin-bottom:0.35rem;">Ukupno: '+Math.round(d.ukupno_nenaplaceno_rsd||0).toLocaleString('sr-RS')+' RSD</div>'
      +[['do_30_dana','0-30 dana','rgba(0,212,127,0.1)','#00d47f'],['31_60_dana','31-60 dana','rgba(255,200,100,0.08)','#ffc864'],['61_90_dana','61-90 dana','rgba(255,150,100,0.08)','#ff9664'],['starije_90','90+ dana','rgba(255,80,80,0.08)','#ff5050']].map(function(b){
        var bkt = aging[b[0]]||{};
        return '<div style="display:flex;justify-content:space-between;align-items:center;background:'+b[2]+';border-radius:5px;padding:0.25rem 0.4rem;margin-bottom:0.15rem;">'
          +'<span style="font-size:0.67rem;color:rgba(255,255,255,0.5);">'+b[1]+' ('+((bkt.stavki)||0)+' stav.)</span>'
          +'<span style="font-size:0.72rem;font-weight:600;color:'+b[3]+';">'+Math.round(bkt.iznos||0).toLocaleString('sr-RS')+' RSD</span></div>';
      }).join('');
  }
  if (tip === 'po-tipu') {
    var rows = d.po_tipu || [];
    return '<div style="font-weight:600;margin-bottom:0.35rem;color:rgba(255,255,255,0.7);">Prihodi po tipu predmeta</div>'
      +'<div style="font-size:0.8rem;font-weight:700;color:#00d4ff;margin-bottom:0.35rem;">Ukupno: '+Math.round(d.ukupno_rsd||0).toLocaleString('sr-RS')+' RSD</div>'
      +rows.slice(0,5).map(function(t){
        return '<div style="margin-bottom:0.3rem;">'
          +'<div style="display:flex;justify-content:space-between;font-size:0.7rem;margin-bottom:0.1rem;"><span style="color:rgba(255,255,255,0.65);text-transform:capitalize;">'+escHtml(t.tip||'ostalo')+'</span><span style="color:#89c8ff;font-weight:600;">'+Math.round(t.iznos_rsd).toLocaleString('sr-RS')+' RSD</span></div>'
          +'<div style="background:rgba(0,212,255,0.06);border-radius:3px;height:4px;"><div style="background:#00d4ff;border-radius:3px;height:4px;width:'+Math.min(100,(t.ucesce_pct||0))+'%;"></div></div>'
          +'</div>';
      }).join('');
  }
  if (tip === 'po-klijentu') {
    var rows = d.po_klijentu || [];
    if (!rows.length) return '<div style="color:rgba(255,255,255,0.35);padding:0.4rem 0;">Nema faktura za ovaj period.</div>';
    return '<div style="font-weight:600;margin-bottom:0.35rem;color:rgba(255,255,255,0.7);">Prihodi po klijentu</div>'
      +'<div style="font-size:0.8rem;font-weight:700;color:#00d4ff;margin-bottom:0.4rem;">Ukupno: '+Math.round(d.ukupno_rsd||0).toLocaleString('sr-RS')+' RSD</div>'
      +rows.slice(0,8).map(function(k){
        var placPct = k.ukupno_rsd > 0 ? Math.round(k.naplaceno_rsd/k.ukupno_rsd*100) : 0;
        var barColor = placPct >= 75 ? '#00d47f' : placPct >= 40 ? '#ffc864' : '#ff7766';
        return '<div style="margin-bottom:0.45rem;padding:0.3rem 0.4rem;background:rgba(255,255,255,0.02);border-radius:6px;border:1px solid rgba(255,255,255,0.05);">'
          +'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.15rem;">'
          +'<span style="font-size:0.7rem;color:rgba(255,255,255,0.75);font-weight:600;">'+escHtml(k.naziv||'—')+'</span>'
          +'<span style="font-size:0.67rem;color:#89c8ff;">'+k.broj_faktura+' fakt. &nbsp;|&nbsp; <b style="color:#00d4ff;">'+Math.round(k.ukupno_rsd).toLocaleString('sr-RS')+' RSD</b></span>'
          +'</div>'
          +'<div style="display:flex;align-items:center;gap:0.4rem;">'
          +'<div style="flex:1;background:rgba(255,255,255,0.05);border-radius:3px;height:5px;">'
          +'<div style="background:'+barColor+';border-radius:3px;height:5px;width:'+placPct+'%;transition:width 0.4s;"></div>'
          +'</div>'
          +'<span style="font-size:0.62rem;color:'+barColor+';white-space:nowrap;">'+placPct+'% napl.</span>'
          +'</div>'
          +'<div style="display:flex;gap:0.8rem;margin-top:0.1rem;font-size:0.63rem;">'
          +'<span style="color:rgba(0,212,127,0.7);">✓ '+Math.round(k.naplaceno_rsd).toLocaleString('sr-RS')+' RSD</span>'
          +'<span style="color:rgba(255,100,80,0.7);">✗ '+Math.round(k.neplaceno_rsd).toLocaleString('sr-RS')+' RSD</span>'
          +'</div>'
          +'</div>';
      }).join('');
  }
  return '<pre style="font-size:0.65rem;color:rgba(255,255,255,0.4);">'+JSON.stringify(d,null,2)+'</pre>';
}

async function billing_csvDownload() {
  if (!currentSession) return;
  var yr  = new Date().getFullYear();
  var url = BASE_URL+'/billing/report/csv?od='+yr+'-01-01&do='+yr+'-12-31';
  var r   = await fetch(url, {headers:{Authorization:'Bearer '+currentSession.access_token}});
  if (!r.ok) { showToast('Greška pri preuzimanju.','err'); return; }
  var blob = await r.blob();
  var a    = document.createElement('a');
  a.href   = URL.createObjectURL(blob);
  a.download = 'billing-'+yr+'.csv';
  a.click();
  URL.revokeObjectURL(a.href);
  showToast('CSV preuzet.','ok');
}



/* ═══════════════════════════════ NEXT BLOCK ═══════════════════════════════ */


/* ── Faza 1: Kalendar + Ročišta JS ──────────────────────────────────────── */

function kalendarLoad() {
  var bodyEl   = document.getElementById('kal-body');
  var loadEl   = document.getElementById('kal-loading');
  var praznoEl = document.getElementById('kal-prazno');
  if (!bodyEl) return;
  bodyEl.innerHTML = '';
  if (praznoEl) praznoEl.style.display = 'none';
  if (loadEl) loadEl.style.display = '';

  // Učitaj predmete za formu (koristimo globalni _predmeti ako postoji)
  if (typeof _predmeti !== 'undefined' && _predmeti.length) {
    _kalendarPredmeti = _predmeti;
  } else {
    fetch(BASE_URL + '/api/predmeti', { headers: { 'Authorization': 'Bearer ' + currentSession.access_token } })
      .then(function(r) { return r.json(); })
      .then(function(d) { _kalendarPredmeti = d.predmeti || []; })
      .catch(function() {});
  }

  fetch(BASE_URL + '/api/kalendar/pregled', {
    headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (loadEl) loadEl.style.display = 'none';
    var eventi = data.dogadjaji || [];
    if (!eventi.length) {
      if (praznoEl) praznoEl.style.display = '';
      return;
    }
    bodyEl.innerHTML = _kalendarRender(eventi);
  })
  .catch(function() {
    if (loadEl) loadEl.style.display = 'none';
    if (bodyEl) bodyEl.innerHTML = '<div class="kal-greska">Greška pri učitavanju kalendara.</div>';
  });
}

var _kalendarPredmeti = [];

function _kalendarRender(eventi) {
  var grouped = {};
  eventi.forEach(function(e) {
    var d = e.datum || '';
    if (!grouped[d]) grouped[d] = [];
    grouped[d].push(e);
  });
  var html = '';
  Object.keys(grouped).sort().forEach(function(datum) {
    var grupe = grouped[datum];
    html += '<div class="kal-dan-blok">';
    html += '<div class="kal-dan-header">' + _kalFmtDatum(datum) + '</div>';
    grupe.forEach(function(e) {
      var tipCls = e.tip === 'rociste' ? 'kal-ev-rociste'
                 : e.tip === 'rok_zastarelost' ? 'kal-ev-zast'
                 : 'kal-ev-dok';
      var vremeStr = e.vreme ? '<span class="kal-ev-vreme">' + _kalEsc(e.vreme) + '</span>' : '';
      var detStr = '';
      if (e.tip === 'rociste' && e.detalji) {
        var det = e.detalji;
        detStr += det.sud ? '<span class="kal-ev-det">' + _kalEsc(det.sud) + '</span>' : '';
        detStr += det.sudnica ? ' · <span class="kal-ev-det">' + _kalEsc(det.sudnica) + '</span>' : '';
        var stCls = 'kal-st-' + (det.status || 'zakazano');
        detStr += ' <span class="kal-ev-status ' + stCls + '">' + _kalEsc(det.status || 'zakazano') + '</span>';
        if (det.id) detStr += ' <button class="kal-ev-del" onclick="rocisteObrisi(\'' + _kalEsc(det.id) + '\')" title="Obriši">✕</button>';
      }
      html += '<div class="kal-ev-row ' + tipCls + '">';
      html += '<div class="kal-ev-naslov">' + _kalEsc(e.naslov) + vremeStr + '</div>';
      if (e.predmet_naziv) html += '<div class="kal-ev-pred">' + _kalEsc(e.predmet_naziv) + '</div>';
      if (detStr) html += '<div class="kal-ev-detalji">' + detStr + '</div>';
      html += '</div>';
    });
    html += '</div>';
  });
  return html;
}

function _kalFmtDatum(iso) {
  if (!iso) return iso;
  try {
    var d = new Date(iso + 'T00:00:00');
    var dani = ['ned','pon','uto','sre','čet','pet','sub'];
    var mes  = ['jan','feb','mar','apr','maj','jun','jul','avg','sep','okt','nov','dec'];
    return dani[d.getDay()] + ', ' + d.getDate() + '. ' + mes[d.getMonth()] + ' ' + d.getFullYear() + '.';
  } catch(e2) { return iso; }
}

function _kalEsc(str) {
  if (str == null) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ═══════════════════════════════════════════════════════════════
// CALENDAR — Monthly Grid View
// ═══════════════════════════════════════════════════════════════
var _kalView      = 'grid';
var _kalAllEvents = [];
var _kalGridDate  = new Date(); // active month for grid

var _KAL_MESECI = ['Januar','Februar','Mart','April','Maj','Jun','Jul','Avgust','Septembar','Oktobar','Novembar','Decembar'];
var _KAL_DANI   = ['Pon','Uto','Sre','Čet','Pet','Sub','Ned'];

function kalSetView(v) {
  _kalView = v;
  var gBtn = document.getElementById('kal-view-grid-btn');
  var lBtn = document.getElementById('kal-view-list-btn');
  var nav  = document.getElementById('kal-month-nav');
  if (gBtn) { gBtn.style.background = v === 'grid' ? 'rgba(74,168,255,0.2)' : 'transparent'; gBtn.style.color = v === 'grid' ? '#89c8ff' : 'rgba(255,255,255,0.4)'; }
  if (lBtn) { lBtn.style.background = v === 'list' ? 'rgba(74,168,255,0.2)' : 'transparent'; lBtn.style.color = v === 'list' ? '#89c8ff' : 'rgba(255,255,255,0.4)'; }
  if (nav)  nav.style.display = v === 'grid' ? 'flex' : 'none';
  var dd = document.getElementById('kal-day-detail');
  if (dd) dd.style.display = 'none';
  if (_kalAllEvents.length) _kalRenderActive();
}

function kalMesecPrev() {
  _kalGridDate = new Date(_kalGridDate.getFullYear(), _kalGridDate.getMonth() - 1, 1);
  _kalRenderGrid(_kalAllEvents);
}
function kalMesecNext() {
  _kalGridDate = new Date(_kalGridDate.getFullYear(), _kalGridDate.getMonth() + 1, 1);
  _kalRenderGrid(_kalAllEvents);
}
function kalMesecToday() {
  _kalGridDate = new Date();
  _kalRenderGrid(_kalAllEvents);
}

function _kalRenderActive() {
  if (_kalView === 'grid') _kalRenderGrid(_kalAllEvents);
  else {
    var bodyEl = document.getElementById('kal-body');
    if (bodyEl) bodyEl.innerHTML = _kalendarRender(_kalAllEvents);
  }
}

function _kalRenderGrid(eventi) {
  var bodyEl = document.getElementById('kal-body');
  if (!bodyEl) return;

  // Update month label
  var lbl = document.getElementById('kal-month-lbl');
  if (lbl) lbl.textContent = _KAL_MESECI[_kalGridDate.getMonth()] + ' ' + _kalGridDate.getFullYear() + '.';

  // Build event map by ISO date
  var byDate = {};
  (eventi || []).forEach(function(e) {
    var d = (e.datum || '').slice(0, 10);
    if (!d) return;
    if (!byDate[d]) byDate[d] = [];
    byDate[d].push(e);
  });

  var yr  = _kalGridDate.getFullYear();
  var mo  = _kalGridDate.getMonth();
  var firstDay = new Date(yr, mo, 1);
  var lastDay  = new Date(yr, mo + 1, 0);

  // Monday-first offset
  var startDow = (firstDay.getDay() + 6) % 7;
  var todayIso = new Date().toISOString().slice(0, 10);

  var html = '<div class="kal-grid-wrap">';
  // Day headers
  _KAL_DANI.forEach(function(d) { html += '<div class="kal-grid-hd">' + d + '</div>'; });

  // Empty cells before month start
  for (var i = 0; i < startDow; i++) html += '<div class="kal-grid-cell empty"></div>';

  // Day cells
  for (var day = 1; day <= lastDay.getDate(); day++) {
    var iso  = yr + '-' + String(mo + 1).padStart(2, '0') + '-' + String(day).padStart(2, '0');
    var evs  = byDate[iso] || [];
    var isToday = iso === todayIso;
    var hasCls  = evs.length ? ' has-events' : '';
    var todCls  = isToday ? ' today' : '';
    html += '<div class="kal-grid-cell' + hasCls + todCls + '" onclick="kalDayClick(\'' + iso + '\')">';
    html += '<div class="kal-grid-cell-num' + (isToday ? ' today' : '') + '">' + day + '</div>';
    if (evs.length) {
      html += '<div class="kal-grid-dots">';
      evs.slice(0, 3).forEach(function(e) {
        var col = e.tip === 'rociste' ? '#4aa8ff' : e.tip === 'rok_zastarelost' ? '#f87171' : '#fbbf24';
        html += '<span class="kal-grid-dot" style="background:' + col + ';"></span>';
      });
      if (evs.length > 3) html += '<span style="font-size:.52rem;color:rgba(255,255,255,.35);">+' + (evs.length - 3) + '</span>';
      html += '</div>';
    }
    html += '</div>';
  }

  // Trailing empties
  var totalCells = startDow + lastDay.getDate();
  var trailing = (7 - (totalCells % 7)) % 7;
  for (var j = 0; j < trailing; j++) html += '<div class="kal-grid-cell empty"></div>';

  html += '</div>';
  bodyEl.innerHTML = html;
}

function kalDayClick(iso) {
  var evs = _kalAllEvents.filter(function(e) { return (e.datum || '').slice(0, 10) === iso; });
  var detEl   = document.getElementById('kal-day-detail');
  var titleEl = document.getElementById('kal-day-detail-title');
  var bodyEl2 = document.getElementById('kal-day-detail-body');
  if (!detEl) return;
  if (!evs.length) { detEl.style.display = 'none'; return; }

  var d = new Date(iso + 'T12:00:00');
  var dani = ['ned','pon','uto','sre','čet','pet','sub'];
  var mes  = ['jan','feb','mar','apr','maj','jun','jul','avg','sep','okt','nov','dec'];
  if (titleEl) titleEl.textContent = dani[d.getDay()] + ', ' + d.getDate() + '. ' + mes[d.getMonth()] + ' ' + d.getFullYear() + '.';

  var html = '';
  evs.forEach(function(e) {
    var tipLabel = e.tip === 'rociste' ? '🏛 Ročište' : e.tip === 'rok_zastarelost' ? '⏳ Rok' : '📅 Rok';
    var col = e.tip === 'rociste' ? '#89c8ff' : e.tip === 'rok_zastarelost' ? '#f87171' : '#fbbf24';
    html += '<div style="padding:.4rem 0;border-bottom:1px solid rgba(255,255,255,.05);">';
    html += '<div style="font-size:.72rem;color:' + col + ';margin-bottom:.1rem;">' + tipLabel + (e.vreme ? ' · ' + _kalEsc(e.vreme) : '') + '</div>';
    html += '<div style="font-weight:600;font-size:.82rem;color:#e2e8f0;">' + _kalEsc(e.naslov) + '</div>';
    if (e.predmet_naziv) html += '<div style="font-size:.72rem;color:rgba(255,255,255,.45);margin-top:.1rem;">' + _kalEsc(e.predmet_naziv) + '</div>';
    if (e.detalji && e.detalji.sud) html += '<div style="font-size:.7rem;color:rgba(255,255,255,.3);margin-top:.1rem;">' + _kalEsc(e.detalji.sud) + (e.detalji.sudnica ? ' · ' + _kalEsc(e.detalji.sudnica) : '') + '</div>';
    html += '</div>';
  });
  if (bodyEl2) bodyEl2.innerHTML = html;
  detEl.style.display = '';
  detEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Override kalendarLoad to store events + render grid
var _kalendarLoad_orig = kalendarLoad;
kalendarLoad = function() {
  var bodyEl   = document.getElementById('kal-body');
  var loadEl   = document.getElementById('kal-loading');
  var praznoEl = document.getElementById('kal-prazno');
  if (!bodyEl) return;
  bodyEl.innerHTML = '';
  if (praznoEl) praznoEl.style.display = 'none';
  if (loadEl) loadEl.style.display = '';

  // Init view toggle state
  var nav = document.getElementById('kal-month-nav');
  if (nav) nav.style.display = _kalView === 'grid' ? 'flex' : 'none';

  if (typeof _predmeti !== 'undefined' && _predmeti.length) _kalendarPredmeti = _predmeti;

  fetch(BASE_URL + '/api/kalendar/pregled', {
    headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (loadEl) loadEl.style.display = 'none';
    _kalAllEvents = data.dogadjaji || [];
    if (!_kalAllEvents.length) {
      if (praznoEl) praznoEl.style.display = '';
      return;
    }
    _kalRenderActive();
  })
  .catch(function() {
    if (loadEl) loadEl.style.display = 'none';
    if (bodyEl) bodyEl.innerHTML = '<div class="kal-greska">Greška pri učitavanju kalendara.</div>';
  });
};

function kalendarIcsExport() {
  if (!currentSession) return;
  fetch(BASE_URL + '/api/kalendar/ics', {
    method: 'POST',
    headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
  })
  .then(function(r) {
    if (!r.ok) { showToast('Nema događaja za izvoz.', 'warn'); return null; }
    return r.blob();
  })
  .then(function(blob) {
    if (!blob) return;
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = 'vindex-kalendar.ics';
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
  })
  .catch(function() { showToast('Greška pri izvozu.', 'err'); });
}

async function kalendarGoogleExport() {
  if (!currentSession) return;
  try {
    var r = await fetch(BASE_URL + '/api/kalendar/pregled', {
      headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
    });
    if (!r.ok) { showToast('Nema događaja.', 'warn'); return; }
    var d = await r.json();
    var eventi = (d.dogadjaji || d.eventi || []);
    if (!eventi.length) { showToast('Nema nadolazećih događaja za Google Kalendar.', 'warn'); return; }
    var first = eventi[0];
    var datum = (first.datum || '').slice(0,10);
    var naslov = first.naslov || 'Vindex AI Rokovi';
    otvoriGoogleKalendar(naslov, datum, 'Vindex AI — pogledajte sve rokove u aplikaciji.');
  } catch(e) {
    showToast('Greška pri otvori Google Kalendar.', 'err');
  }
}

async function kalendarOutlookExport() {
  if (!currentSession) return;
  try {
    var r = await fetch(BASE_URL + '/api/kalendar/pregled', {
      headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
    });
    if (!r.ok) { showToast('Nema događaja.', 'warn'); return; }
    var d = await r.json();
    var eventi = (d.dogadjaji || d.eventi || []);
    if (!eventi.length) { showToast('Nema nadolazećih događaja za Outlook.', 'warn'); return; }
    var first = eventi[0];
    var datum = (first.datum || '').slice(0,10);
    var naslov = first.naslov || 'Vindex AI Rokovi';
    otvoriOutlookKalendar(naslov, datum, 'Vindex AI — pogledajte sve rokove u aplikaciji.');
  } catch(e) {
    showToast('Greška pri otvori Outlook Kalendar.', 'err');
  }
}

function rocisteOtvoriFormu() {
  var ov = document.getElementById('rociste-overlay');
  if (!ov) return;
  document.getElementById('rociste-edit-id').value = '';
  document.getElementById('rociste-sud').value = '';
  document.getElementById('rociste-datum').value = '';
  document.getElementById('rociste-vreme').value = '';
  document.getElementById('rociste-sudnica').value = '';
  document.getElementById('rociste-broj').value = '';
  document.getElementById('rociste-napomena').value = '';
  document.getElementById('rociste-greska').style.display = 'none';
  document.getElementById('rociste-modal-title').textContent = 'Novo ročište';
  var sel = document.getElementById('rociste-predmet-id');
  sel.innerHTML = '<option value="">— Izaberi predmet —</option>';
  (_kalendarPredmeti || []).forEach(function(p) {
    var opt = document.createElement('option');
    opt.value = p.id; opt.textContent = p.naziv || p.id;
    sel.appendChild(opt);
  });
  ov.classList.add('open');
}

function rocisteZatvoriFormu() {
  var ov = document.getElementById('rociste-overlay');
  if (ov) ov.classList.remove('open');
}

function rocisteSnimi() {
  var predmetId = document.getElementById('rociste-predmet-id').value;
  var sud       = document.getElementById('rociste-sud').value.trim();
  var datum     = document.getElementById('rociste-datum').value;
  var vreme     = document.getElementById('rociste-vreme').value || null;
  var sudnica   = document.getElementById('rociste-sudnica').value.trim() || null;
  var broj      = document.getElementById('rociste-broj').value.trim() || null;
  var napomena  = document.getElementById('rociste-napomena').value.trim() || null;
  var grEl      = document.getElementById('rociste-greska');
  if (!predmetId) { grEl.textContent = 'Izaberite predmet.'; grEl.style.display = ''; return; }
  if (!sud)       { grEl.textContent = 'Unesite naziv suda.'; grEl.style.display = ''; return; }
  if (!datum)     { grEl.textContent = 'Unesite datum ročišta.'; grEl.style.display = ''; return; }
  grEl.style.display = 'none';
  fetch(BASE_URL + '/api/rocista', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + currentSession.access_token },
    body: JSON.stringify({ predmet_id: predmetId, sud: sud, datum: datum, vreme: vreme, sudnica: sudnica, broj_predmeta_suda: broj, napomena: napomena }),
  })
  .then(function(r) { return r.json().then(function(d) { return { ok: r.ok, d: d }; }); })
  .then(function(res) {
    if (!res.ok) { grEl.textContent = (res.d && res.d.detail) || 'Greška pri snimanju.'; grEl.style.display = ''; return; }
    rocisteZatvoriFormu();
    showToast('Ročište sačuvano.', 'ok');
    kalendarLoad();
  })
  .catch(function() { grEl.textContent = 'Mrežna greška.'; grEl.style.display = ''; });
}

function rocisteObrisi(id) {
  if (!id || !currentSession) return;
  if (!confirm('Obrisati ovo ročište?')) return;
  fetch(BASE_URL + '/api/rocista/' + encodeURIComponent(id), {
    method: 'DELETE',
    headers: { 'Authorization': 'Bearer ' + currentSession.access_token },
  })
  .then(function(r) {
    if (r.ok) { showToast('Ročište obrisano.', 'ok'); kalendarLoad(); }
    else showToast('Greška pri brisanju.', 'err');
  })
  .catch(function() { showToast('Mrežna greška.', 'err'); });
}


/* ═══════════════════════════════ NEXT BLOCK ═══════════════════════════════ */


// ── Hearing Command Center ────────────────────────────────────────────────────
async function hccGeneriši() {
  if (!currentSession) { showToast('Niste prijavljeni.', 'err'); return; }
  var predmetId = activePredmetId;
  if (!predmetId) { showToast('Otvorite predmet pre generisanja brifinga.', 'err'); return; }
  var datum = document.getElementById('hcc-datum').value;
  var tip   = document.getElementById('hcc-tip').value;
  if (!datum) { showToast('Unesite datum ročišta.', 'err'); return; }

  var btn     = document.getElementById('hcc-btn');
  var loading = document.getElementById('hcc-loading');
  var errEl   = document.getElementById('hcc-error');
  var resEl   = document.getElementById('hcc-result');

  btn.disabled = true;
  loading.style.display = '';
  errEl.style.display   = 'none';
  resEl.style.display   = 'none';
  resEl.innerHTML       = '';

  piTrack('hearing_cc','generate',{predmet_id:predmetId});
  try {
    var r = await fetch(BASE_URL + '/api/rociste/command-center', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + currentSession.access_token,
      },
      body: JSON.stringify({ predmet_id: predmetId, datum_rocista: datum, tip_postupka: tip }),
    });
    var data = await r.json();
    if (!r.ok) {
      errEl.textContent = (data.detail && typeof data.detail === 'string') ? data.detail : 'Greška pri generisanju brifinga.';
      errEl.style.display = '';
      return;
    }
    hccRenderBrifing(resEl, data.brifing, data.krediti_preostalo);
    resEl.style.display = '';
  } catch(e) {
    errEl.textContent = 'Mrežna greška. Proverite vezu.';
    errEl.style.display = '';
  } finally {
    btn.disabled = false;
    loading.style.display = 'none';
  }
}

function hccRenderBrifing(el, b, krediti) {
  function _score(s) {
    var color = s >= 75 ? '#4ade80' : s >= 50 ? '#fbbf24' : '#f87171';
    return '<div style="display:flex;align-items:center;gap:0.5rem;margin:0.3rem 0;">'
      + '<div style="font-size:1.6rem;font-weight:800;color:' + color + ';">' + s + '</div>'
      + '<div style="font-size:0.65rem;color:rgba(255,255,255,0.4);line-height:1.3;">/ 100<br>Pripremljenost</div>'
      + '<div style="flex:1;height:6px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden;">'
      + '<div style="width:' + s + '%;height:100%;background:' + color + ';border-radius:3px;"></div></div></div>';
  }
  function _list(arr) {
    if (!Array.isArray(arr) || !arr.length) return '<div style="color:rgba(255,255,255,0.3);font-size:0.72rem;">—</div>';
    return '<ul style="margin:0.2rem 0 0;padding-left:1.1rem;">' + arr.map(function(x){
      return '<li style="font-size:0.76rem;color:rgba(255,255,255,0.75);margin-bottom:0.2rem;">' + _esc(String(x)) + '</li>';
    }).join('') + '</ul>';
  }
  function _txt(s) {
    return '<div style="font-size:0.76rem;color:rgba(255,255,255,0.75);line-height:1.55;white-space:pre-wrap;">' + _esc(String(s||'—')) + '</div>';
  }
  function _esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function _sec(icon, title, body) {
    return '<div style="margin-top:0.6rem;padding:0.6rem 0.75rem;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:8px;">'
      + '<div style="font-size:0.6rem;letter-spacing:.1em;text-transform:uppercase;color:rgba(255,255,255,0.35);margin-bottom:0.3rem;">' + icon + ' ' + title + '</div>'
      + body + '</div>';
  }

  var rb = b.risk_breakdown || {};
  var rbColor = rb.overall === 'VISOK' ? '#f87171' : rb.overall === 'SREDNJI' ? '#fbbf24' : '#4ade80';
  var wlm = b.win_lose_matrix || {};

  var html = '<div style="padding:0.1rem 0;">';

  // Score + executive brief
  html += _score(Number(b.hearing_score) || 0);
  html += _sec('📋', 'Izvršni sažetak', _txt(b.executive_brief));

  // Risk breakdown
  html += _sec('⚠', 'Procena rizika',
    '<span style="font-weight:700;color:' + rbColor + ';font-size:0.8rem;">' + _esc(rb.overall||'?') + '</span>'
    + _list(rb.factors));

  // Win/lose matrix
  html += _sec('⚖️', 'Matrica pobede / poraza',
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem;margin-top:0.2rem;">'
    + '<div><div style="font-size:0.6rem;color:#4ade80;letter-spacing:.08em;margin-bottom:0.1rem;">U PRILOG</div>' + _list(wlm.u_prilog) + '</div>'
    + '<div><div style="font-size:0.6rem;color:#f87171;letter-spacing:.08em;margin-bottom:0.1rem;">NA ŠTETU</div>' + _list(wlm.na_stetu) + '</div>'
    + '</div>');

  // Timeline
  html += _sec('📅', 'Hronologija', _list(b.timeline));

  // Judge attack
  html += _sec('⚔️', 'Napad pred sudom — pravni argumenti', _txt(b.judge_attack_mode));

  // Opposing counsel
  html += _sec('🎯', 'Strategija protivne strane', _txt(b.opposing_counsel));

  // Missing evidence
  html += _sec('🔍', 'Dokazi koji nedostaju', _list(b.missing_evidence));

  // Witness analysis
  html += _sec('👁', 'Analiza svedoka', _txt(b.witness_analysis));

  // Cross examination
  html += _sec('❓', 'Unakrsno ispitivanje', _list(b.cross_examination));

  // Practice pack
  html += _sec('📚', 'Sudska praksa', _txt(b.practice_pack));

  // Hearing checklist
  html += _sec('✅', 'Kontrolna lista za ročište', _list(b.hearing_checklist));

  if (krediti !== undefined) {
    html += '<div style="margin-top:0.5rem;font-size:0.65rem;color:rgba(255,255,255,0.25);text-align:right;">Preostalo kredita: ' + krediti + '</div>';
  }

  html += '</div>';
  el.innerHTML = html;
}


/* ═══════════════════════════════ NEXT BLOCK ═══════════════════════════════ */


// Tab scroll arrows
function tabsScroll(dir) {
  var el = document.getElementById('t-tabs-el');
  if (el) el.scrollBy({ left: dir * 180, behavior: 'smooth' });
}
function tabsUpdateArrows() {
  var el = document.getElementById('t-tabs-el');
  if (!el) return;
  var wrap = el.parentElement;
  if (!wrap || !wrap.classList.contains('t-tabs-wrap')) return;
  wrap.classList.toggle('at-start', el.scrollLeft <= 2);
  wrap.classList.toggle('at-end', el.scrollLeft >= el.scrollWidth - el.clientWidth - 2);
}
window.addEventListener('load', function() {
  var el = document.getElementById('t-tabs-el');
  if (el) {
    el.addEventListener('scroll', tabsUpdateArrows, { passive: true });
    tabsUpdateArrows();
    if (window.ResizeObserver) new ResizeObserver(tabsUpdateArrows).observe(el);
  }
});


/* ═══════════════════════════════ NEXT BLOCK ═══════════════════════════════ */


// ═══════════════════════════════════════════════════════════════
// PRODUCT INTELLIGENCE — Admin Panel
// ═══════════════════════════════════════════════════════════════

function _updateAdminTabUI() {
  var btn = document.getElementById('tab-btn-pi');
  if (btn) btn.style.display = currentUserIsFounder ? '' : 'none';
  var wlSection = document.getElementById('wl-admin-section');
  if (wlSection) {
    wlSection.style.display = currentUserIsFounder ? '' : 'none';
    if (currentUserIsFounder) wl_admin_load();
  }
  var corpusSection = document.getElementById('corpus-admin-section');
  if (corpusSection) corpusSection.style.display = currentUserIsFounder ? '' : 'none';
  var lawSection = document.getElementById('law-upload-section');
  if (lawSection) lawSection.style.display = currentUserIsFounder ? '' : 'none';
  var analyticsSection = document.getElementById('analytics-section');
  if (analyticsSection) {
    analyticsSection.style.display = currentUserIsFounder ? '' : 'none';
    if (currentUserIsFounder) analyticsLoad();
  }
}

/* ── Usage Analytics Dashboard ──────────────────────────────────────────────── */

async function analyticsLoad() {
  if (!currentSession) return;
  var period = (document.getElementById('analytics-period') || {}).value || '30';
  try {
    var r = await fetch('/analytics/usage?dana=' + period, { headers: { 'Authorization': 'Bearer ' + currentSession.access_token } });
    if (!r.ok) return;
    var d = await r.json();
    analyticsRender(d);
  } catch(e) {}
}

function analyticsRender(d) {
  var total    = d.ukupno_dogadjaja || 0;
  var features = d.top_funkcije || [];
  var predmeti = d.top_predmeti || [];
  var aktivnost = d.aktivnost_po_danu || [];

  var emptyEl = document.getElementById('analytics-empty');

  // KPI
  var kpiEl = document.getElementById('analytics-kpi');
  if (kpiEl) {
    kpiEl.innerHTML = [
      { label: 'Ukupno akcija', val: total, color: '#89c8ff' },
      { label: 'Funkcija korišćeno', val: features.length, color: '#4ade80' },
      { label: 'Period (dana)', val: d.period_dana || 30, color: 'rgba(255,255,255,0.4)' },
    ].map(function(k){
      return '<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);border-radius:7px;padding:0.5rem 0.6rem;text-align:center;">'
        +'<div style="font-size:1.1rem;font-weight:700;color:'+k.color+';line-height:1.2;">'+k.val+'</div>'
        +'<div style="font-size:0.57rem;color:rgba(255,255,255,0.38);text-transform:uppercase;letter-spacing:.05em;margin-top:1px;">'+k.label+'</div>'
        +'</div>';
    }).join('');
  }

  // Bar chart aktivnost
  var chartEl = document.getElementById('analytics-chart');
  if (chartEl && aktivnost.length) {
    var maxVal = Math.max.apply(null, aktivnost.map(function(a){ return a.count; })) || 1;
    chartEl.innerHTML = aktivnost.map(function(a){
      var pct = Math.round((a.count / maxVal) * 100);
      var dan = (a.datum || '').slice(5);
      return '<div style="display:flex;flex-direction:column;align-items:center;flex:1;gap:2px;" title="'+a.datum+': '+a.count+' akcija">'
        +'<div style="width:100%;background:rgba(74,168,255,0.5);border-radius:2px 2px 0 0;height:'+pct+'%;min-height:'+(a.count?2:0)+'px;"></div>'
        +'<div style="font-size:0.42rem;color:rgba(255,255,255,0.25);writing-mode:vertical-lr;transform:rotate(180deg);white-space:nowrap;">'+dan+'</div>'
        +'</div>';
    }).join('');
  } else if (chartEl) {
    chartEl.innerHTML = '<div style="color:rgba(255,255,255,0.2);font-size:0.75rem;width:100%;text-align:center;">Nema podataka</div>';
  }

  // Top funkcije
  var featEl = document.getElementById('analytics-features');
  if (featEl) {
    var maxF = features.length ? features[0].count : 1;
    featEl.innerHTML = features.slice(0, 8).map(function(f){
      var pct = Math.round((f.count / maxF) * 100);
      return '<div style="margin-bottom:2px;">'
        +'<div style="display:flex;justify-content:space-between;font-size:0.68rem;margin-bottom:1px;">'
        +'<span style="color:rgba(255,255,255,0.7);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:120px;">'+_htmlEsc(f.feature)+'</span>'
        +'<span style="color:rgba(255,255,255,0.4);flex-shrink:0;margin-left:4px;">'+f.count+'</span>'
        +'</div>'
        +'<div style="height:3px;background:rgba(255,255,255,0.06);border-radius:2px;">'
        +'<div style="height:100%;width:'+pct+'%;background:#4aa8ff;border-radius:2px;"></div>'
        +'</div></div>';
    }).join('') || '<div style="font-size:0.7rem;color:rgba(255,255,255,0.25);">Nema podataka</div>';
  }

  // Top predmeti
  var predEl = document.getElementById('analytics-predmeti');
  if (predEl) {
    predEl.innerHTML = predmeti.slice(0, 5).map(function(p, i){
      return '<div style="display:flex;align-items:center;gap:0.4rem;padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.04);">'
        +'<span style="font-size:0.6rem;color:rgba(255,255,255,0.3);flex-shrink:0;width:12px;">'+(i+1)+'.</span>'
        +'<span style="font-size:0.7rem;color:rgba(255,255,255,0.75);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+_htmlEsc(p.naziv||p.predmet_id)+'</span>'
        +'<span style="font-size:0.65rem;color:#89c8ff;flex-shrink:0;">'+p.pristupa+'×</span>'
        +'</div>';
    }).join('') || '<div style="font-size:0.7rem;color:rgba(255,255,255,0.25);">Nema podataka</div>';
  }

  if (emptyEl) emptyEl.style.display = total ? 'none' : 'block';
}

/* ── Law Upload Admin — Law database expansion ────────────────────────────── */

async function lawUploadRun() {
  if (!currentSession) return;
  var nazivInp  = document.getElementById('law-naziv-input');
  var slInp     = document.getElementById('law-sl-glasnik-input');
  var pdfInp    = document.getElementById('law-pdf-input');
  var statusEl  = document.getElementById('law-upload-status');
  var btn       = document.getElementById('law-upload-btn');

  var naziv = (nazivInp ? nazivInp.value.trim() : '');
  if (!naziv) { _lawStatus('Unesite naziv zakona.', '#f87171'); return; }
  if (!pdfInp || !pdfInp.files || !pdfInp.files.length) { _lawStatus('Izaberite PDF fajl.', '#f87171'); return; }

  var formData = new FormData();
  formData.append('naziv', naziv);
  formData.append('broj_sl_glasnika', slInp ? slInp.value.trim() : '');
  formData.append('pdf', pdfInp.files[0]);

  btn.disabled = true; btn.textContent = '⏳ Upload...';
  _lawStatus('Uploadujem i pokrećem ingest...', '#c9a84c');

  try {
    var r = await fetch('/api/admin/law/upload', {
      method: 'POST',
      headers: {'Authorization': 'Bearer ' + currentSession.access_token},
      body: formData
    });
    var d = await r.json();
    if (!r.ok) { _lawStatus(d.detail || 'Greška.', '#f87171'); }
    else {
      _lawStatus('✓ Ingest pokrenut za "' + naziv + '". Pratite status ispod.', '#4ade80');
      if (nazivInp) nazivInp.value = '';
      if (slInp)    slInp.value = '';
      if (pdfInp)   pdfInp.value = '';
      await lawListLoad();
    }
  } catch(e) { _lawStatus('Greška mreže.', '#f87171'); }
  finally { btn.disabled = false; btn.textContent = '⬆ Upload'; }
}

function _lawStatus(txt, color) {
  var el = document.getElementById('law-upload-status');
  if (!el) return;
  el.textContent = txt;
  el.style.color = color || '#fff';
  el.style.display = '';
  setTimeout(function(){ if(el.textContent === txt) el.style.display = 'none'; }, 6000);
}

async function lawListLoad() {
  if (!currentSession) return;
  var result = document.getElementById('law-lista-result');
  if (result) result.innerHTML = '<div style="color:rgba(255,255,255,0.35);">Učitavam...</div>';
  try {
    var r = await fetch('/api/admin/law/lista', {headers:{'Authorization':'Bearer '+currentSession.access_token}});
    if (!r.ok) { if(result) result.innerHTML = ''; return; }
    var d = await r.json();
    var zakoni = d.zakoni || [];
    if (!zakoni.length) { if(result) result.innerHTML = '<div style="color:rgba(255,255,255,0.3);">Nema uploadovanih zakona.</div>'; return; }
    var statIco = {pending:'⏳', running:'🔄', done:'✅', failed:'❌', obrisan:'🗑'};
    var statCol = {pending:'#c9a84c', running:'#89c8ff', done:'#4ade80', failed:'#f87171', obrisan:'rgba(255,255,255,0.25)'};
    if (result) result.innerHTML = zakoni.map(function(z){
      var ico = statIco[z.status] || '?';
      var col = statCol[z.status] || '#fff';
      var vek = z.vektori_upserted ? (' · ' + z.vektori_upserted + ' vektora') : '';
      var delBtn = z.status !== 'obrisan' ? '<button onclick="lawDelete(\''+z.id+'\',\''+_htmlEsc(z.naziv)+'\')" style="background:none;border:1px solid rgba(239,68,68,0.25);border-radius:4px;padding:1px 6px;color:rgba(239,68,68,0.6);font-size:0.68rem;cursor:pointer;font-family:inherit;margin-left:4px;">×</button>' : '';
      return '<div style="display:flex;align-items:center;gap:6px;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.05);">'
        +'<span style="color:'+col+';font-size:0.8rem;">'+ico+'</span>'
        +'<span style="flex:1;font-size:0.76rem;color:rgba(255,255,255,0.8);">'+_htmlEsc(z.naziv)+'<span style="color:rgba(255,255,255,0.3);font-size:0.68rem;">'+vek+'</span></span>'
        +delBtn+'</div>';
    }).join('');
  } catch(e) {}
}

async function lawDelete(docId, naziv) {
  if (!currentSession) return;
  if (!confirm('Soft-delete "' + naziv + '"?\n(Vektori u Pinecone ostaju — kontaktirajte admina za puno brisanje.)')) return;
  try {
    var r = await fetch('/api/admin/law/' + docId, {method:'DELETE', headers:{'Authorization':'Bearer '+currentSession.access_token}});
    if (!r.ok) { var d=await r.json(); showToast(d.detail||'Greška.','err'); return; }
    await lawListLoad();
  } catch(e) { showToast('Greška mreže.','err'); }
}

/* ── Corpus Admin — auto-scraper ─────────────────────────────────────────── */
async function corpusDiscoverRun() {
  var btn    = document.getElementById('corpus-discover-btn');
  var status = document.getElementById('corpus-discover-status');
  var result = document.getElementById('corpus-discover-result');
  btn.disabled = true; btn.textContent = '⏳ Tražim...';
  if (status) status.textContent = '';
  if (result) result.innerHTML = '<div style="color:rgba(255,255,255,0.4);">Crawlam VKS · AS Beograd · AS Niš · AS Kragujevac...</div>';
  try {
    var res = await fetch(BASE_URL + '/api/admin/ingest/discover', {
      method: 'POST',
      headers: {'Content-Type':'application/json','Authorization':'Bearer '+(currentSession ? currentSession.access_token : '')},
      body: JSON.stringify({courts:['vks','as_bg','as_nis','as_kg'], since_year:2024, use_html:true})
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    var data = await res.json();
    var n = data.new_count || 0;
    if (status) status.textContent = n === 0 ? 'Nema novih biltena.' : n + ' novih biltena!';
    if (result) {
      if (n === 0) {
        result.innerHTML = '<div style="color:rgba(255,255,255,0.35);padding:.5rem 0;">Svi bilteni su već u bazi.</div>';
      } else {
        var html = '<div style="margin-bottom:6px;color:#86efac;font-weight:600;">' + n + ' novih biltena pronađeno:</div>';
        (data.bilteni || []).forEach(function(b) {
          html += '<div style="padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.07);">';
          html += '<span style="color:rgba(255,255,255,0.5);font-size:.72rem;">[' + (b.court||'').toUpperCase() + ']</span> ';
          html += '<span style="color:rgba(255,255,255,0.85);">' + _htmlEsc(b.label || b.url) + '</span>';
          if (b.size_bytes) html += ' <span style="color:rgba(255,255,255,0.3);font-size:.7rem;">' + Math.round(b.size_bytes/1024) + ' KB</span>';
          html += '</div>';
        });
        html += '<div style="margin-top:8px;font-size:.72rem;color:rgba(255,255,255,0.35);">Pokrenite ingest script da ih unesete u Pinecone.</div>';
        result.innerHTML = html;
      }
    }
  } catch(e) {
    if (result) result.innerHTML = '<div style="color:#f87171;">Greška: ' + _htmlEsc(e.message) + '</div>';
  } finally {
    btn.disabled = false; btn.textContent = '🔍 Traži nove biltene';
  }
}

async function corpusListDiscovered() {
  var result = document.getElementById('corpus-discover-result');
  if (result) result.innerHTML = '<div style="color:rgba(255,255,255,0.4);">Učitavam...</div>';
  try {
    var res = await fetch(BASE_URL + '/api/admin/ingest/discovered', {
      headers: {'Authorization':'Bearer '+(currentSession ? currentSession.access_token : '')}
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    var data = await res.json();
    var rows = data.bilteni || [];
    if (!rows.length) {
      if (result) result.innerHTML = '<div style="color:rgba(255,255,255,0.35);">Nema otkrivenih biltena u bazi.</div>';
      return;
    }
    var html = '<div style="margin-bottom:6px;font-size:.73rem;color:rgba(255,255,255,0.5);">Ukupno: ' + data.total + '</div>';
    rows.forEach(function(b) {
      var statusColor = b.status==='ingested' ? '#86efac' : b.status==='failed' ? '#f87171' : 'rgba(255,255,255,0.6)';
      html += '<div style="padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.06);display:flex;gap:8px;align-items:center;">';
      html += '<span style="color:' + statusColor + ';font-size:.7rem;min-width:70px;">' + b.status + '</span>';
      html += '<span style="color:rgba(255,255,255,0.7);font-size:.73rem;">' + _htmlEsc(b.label) + '</span>';
      html += '<span style="color:rgba(255,255,255,0.3);font-size:.7rem;">' + (b.court||'').toUpperCase() + '</span>';
      html += '</div>';
    });
    if (result) result.innerHTML = html;
  } catch(e) {
    if (result) result.innerHTML = '<div style="color:#f87171;">Greška: ' + _htmlEsc(e.message) + '</div>';
  }
}

// ── Email notifikacije za rokove ─────────────────────────────────────────────

async function emailNotifLoad() {
  if (!currentSession) return;
  try {
    var r = await fetch('/email-notif/profil', {headers:{'Authorization':'Bearer '+currentSession.access_token}});
    if (!r.ok) return;
    var d = await r.json();
    var badge = document.getElementById('email-notif-badge');
    var addrEl = document.getElementById('email-notif-addr');
    var d7 = document.getElementById('en-dan-7');
    var d3 = document.getElementById('en-dan-3');
    var d1 = document.getElementById('en-dan-1');
    var testBtn  = document.getElementById('en-test-btn');
    var deakBtn  = document.getElementById('en-deaktiv-btn');
    var saveBtn  = document.getElementById('en-save-btn');
    if (addrEl) addrEl.textContent = d.email || '—';
    if (d7) d7.checked = !!d.dan_7;
    if (d3) d3.checked = !!d.dan_3;
    if (d1) d1.checked = !!d.dan_1;
    var dn = document.getElementById('en-nedeljni');
    if (dn) dn.checked = d.nedeljni !== false;
    if (badge) {
      if (d.aktivan) {
        badge.textContent = 'AKTIVNO'; badge.style.background='rgba(74,222,128,0.15)'; badge.style.color='#4ade80'; badge.style.display='inline';
      } else { badge.style.display='none'; }
    }
    if (testBtn)  testBtn.style.display  = d.aktivan ? 'inline-block' : 'none';
    if (deakBtn)  deakBtn.style.display  = d.aktivan ? 'inline-block' : 'none';
    if (saveBtn)  saveBtn.textContent    = d.aktivan ? 'Sačuvaj' : 'Aktiviraj';
    if (!d.smtp_ok) {
      var sec = document.getElementById('email-notif-section');
      if (sec) { var warn=document.createElement('div'); warn.style.cssText='font-size:.7rem;color:#f87171;margin-top:.3rem;'; warn.textContent='⚠ Email server nije konfigurisan (EMAIL_SMTP_HOST).'; sec.appendChild(warn); }
    }
  } catch(e) {}
}

function _enMsg(txt, color) {
  var el = document.getElementById('en-msg');
  if (!el) return;
  el.textContent = txt; el.style.color = color || '#4ade80'; el.style.display = '';
  setTimeout(function(){ if(el.textContent===txt) el.style.display='none'; }, 4000);
}

async function emailNotifSacuvaj() {
  if (!currentSession) return;
  var d7 = document.getElementById('en-dan-7');
  var d3 = document.getElementById('en-dan-3');
  var d1 = document.getElementById('en-dan-1');
  try {
    var r = await fetch('/email-notif/profil', {
      method:'POST', headers:{'Authorization':'Bearer '+currentSession.access_token,'Content-Type':'application/json'},
      body: JSON.stringify({aktivan:true, dan_7: d7?!!d7.checked:true, dan_3: d3?!!d3.checked:true, dan_1: d1?!!d1.checked:true, nedeljni: !!(document.getElementById('en-nedeljni')||{}).checked})
    });
    var d = await r.json();
    if (!r.ok) { _enMsg(d.detail||'Greška.','#f87171'); return; }
    _enMsg('✓ Email notifikacije aktivirane.');
    await emailNotifLoad();
  } catch(e) { _enMsg('Greška mreže.','#f87171'); }
}

async function emailNotifTest() {
  if (!currentSession) return;
  try {
    var r = await fetch('/email-notif/test', {method:'POST', headers:{'Authorization':'Bearer '+currentSession.access_token}});
    var d = await r.json();
    if (!r.ok) { _enMsg(d.detail||'Greška.','#f87171'); return; }
    _enMsg('✓ Test email poslat na ' + d.poslato_na);
  } catch(e) { _enMsg('Greška mreže.','#f87171'); }
}

async function emailNotifDeaktivaj() {
  if (!currentSession || !confirm('Deaktivirati email notifikacije?')) return;
  try {
    await fetch('/email-notif/profil', {method:'DELETE', headers:{'Authorization':'Bearer '+currentSession.access_token}});
    _enMsg('Email notifikacije deaktivirane.');
    await emailNotifLoad();
  } catch(e) { _enMsg('Greška mreže.','#f87171'); }
}

// ── Global Search (⌘K) ───────────────────────────────────────────────────────

var _gsOpen      = false;
var _gsTimer     = null;
var _gsVrste     = 'predmeti,klijenti,hronologija,beleske,dokumenti,billing';
var _gsResults   = [];
var _gsFocusIdx  = -1;

function gsOpen() {
  if (!currentSession) return;
  _gsOpen = true;
  var overlay = document.getElementById('gs-overlay');
  var modal   = document.getElementById('gs-modal');
  var inp     = document.getElementById('gs-input');
  if (overlay) overlay.style.display = '';
  if (modal)   modal.style.display = '';
  if (inp)     { inp.value = ''; inp.focus(); }
  gsRender([]);
}

function gsClose() {
  _gsOpen = false;
  var overlay = document.getElementById('gs-overlay');
  var modal   = document.getElementById('gs-modal');
  if (overlay) overlay.style.display = 'none';
  if (modal)   modal.style.display = 'none';
  _gsFocusIdx = -1;
  if (_gsTimer) { clearTimeout(_gsTimer); _gsTimer = null; }
}

function gsSetFilter(btn) {
  document.querySelectorAll('.gs-filter').forEach(function(b){
    b.style.background   = 'transparent';
    b.style.borderColor  = 'rgba(255,255,255,0.12)';
    b.style.color        = 'rgba(255,255,255,0.45)';
    b.classList.remove('active');
  });
  btn.style.background  = 'rgba(74,168,255,0.12)';
  btn.style.borderColor = 'rgba(74,168,255,0.3)';
  btn.style.color       = '#89c8ff';
  btn.classList.add('active');
  _gsVrste = btn.dataset.vrste;
  var inp = document.getElementById('gs-input');
  if (inp && inp.value.trim().length >= 2) gsQuery(inp.value);
}

function gsQuery(val) {
  if (_gsTimer) clearTimeout(_gsTimer);
  if (!val || val.trim().length < 2) { gsRender([]); return; }
  _gsTimer = setTimeout(function(){ _gsFetch(val.trim()); }, 260);
}

async function _gsFetch(q) {
  if (!currentSession) return;
  var resEl = document.getElementById('gs-results');
  if (resEl) resEl.innerHTML = '<div style="padding:0.8rem 1rem;font-size:0.8rem;color:rgba(255,255,255,0.3);">Tražim...</div>';
  try {
    var url = '/api/search?q=' + encodeURIComponent(q) + '&vrste=' + encodeURIComponent(_gsVrste) + '&limit=6';
    var r   = await fetch(url, {headers:{'Authorization':'Bearer '+currentSession.access_token}});
    if (!r.ok) { gsRender([]); return; }
    var d = await r.json();
    _gsResults  = d.rezultati || [];
    _gsFocusIdx = _gsResults.length ? 0 : -1;
    gsRender(_gsResults);
  } catch(e) { gsRender([]); }
}

var _GS_ICONS = {predmet:'📁', klijent:'👤', dokument:'📄', billing:'💰', hronologija:'⏰', beleska:'📝'};
var _GS_COLORS = {predmet:'#89c8ff', klijent:'#4ade80', dokument:'#c9a84c', billing:'#a78bfa', hronologija:'#f97316', beleska:'#94a3b8'};

function gsRender(items) {
  var el = document.getElementById('gs-results');
  if (!el) return;
  if (!items.length) {
    var inp = document.getElementById('gs-input');
    el.innerHTML = inp && inp.value.trim().length >= 2
      ? '<div style="padding:1.2rem 1rem;font-size:0.8rem;color:rgba(255,255,255,0.3);text-align:center;">Nema rezultata.</div>'
      : '<div style="padding:1rem 1rem;font-size:0.8rem;color:rgba(255,255,255,0.25);text-align:center;">Ukucajte barem 2 slova...</div>';
    return;
  }
  el.innerHTML = items.map(function(item, i){
    var ico   = _GS_ICONS[item.tip]  || '·';
    var col   = _GS_COLORS[item.tip] || '#94a3b8';
    var focus = (i === _gsFocusIdx) ? 'background:rgba(74,168,255,0.09);' : '';
    return '<div class="gs-item" data-idx="'+i+'" onclick="gsSelect('+i+')" onmouseover="gsFocus('+i+')"'
      +' style="display:flex;align-items:center;gap:0.65rem;padding:0.55rem 1rem;cursor:pointer;'+focus+'">'
      +'<span style="font-size:1rem;flex-shrink:0;">'+ico+'</span>'
      +'<div style="flex:1;min-width:0;">'
      +'<div style="font-size:0.82rem;color:#e2e8f0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+_htmlEsc(item.naziv)+'</div>'
      +(item.preview ? '<div style="font-size:0.7rem;color:rgba(255,255,255,0.38);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+_htmlEsc(item.preview)+'</div>' : '')
      +'</div>'
      +'<span style="font-size:0.62rem;color:'+col+';flex-shrink:0;letter-spacing:.05em;text-transform:uppercase;">'+item.tip+'</span>'
      +'</div>';
  }).join('');
}

function gsFocus(idx) {
  _gsFocusIdx = idx;
  document.querySelectorAll('.gs-item').forEach(function(el, i){
    el.style.background = (i === idx) ? 'rgba(74,168,255,0.09)' : '';
  });
}

function gsKeyNav(e) {
  if (e.key === 'Escape') { gsClose(); return; }
  if (!_gsResults.length) return;
  if (e.key === 'ArrowDown') { e.preventDefault(); gsFocus(Math.min(_gsFocusIdx + 1, _gsResults.length - 1)); }
  if (e.key === 'ArrowUp')   { e.preventDefault(); gsFocus(Math.max(_gsFocusIdx - 1, 0)); }
  if (e.key === 'Enter' && _gsFocusIdx >= 0) { e.preventDefault(); gsSelect(_gsFocusIdx); }
}

function gsSelect(idx) {
  var item = _gsResults[idx];
  if (!item) return;
  gsClose();
  if (item.tip === 'predmet') {
    setTab(document.getElementById('tab-btn-p'), 'p');
    setTimeout(function(){ pred_select(item.id); }, 300);
  } else if (item.tip === 'klijent') {
    setTab(document.getElementById('tab-btn-k'), 'k');
    setTimeout(function(){ if(typeof klijentOtvori==='function') klijentOtvori(item.id); }, 400);
  } else if (item.tip === 'dokument' || item.tip === 'billing' || item.tip === 'hronologija' || item.tip === 'beleska') {
    var predId = item.meta && item.meta.predmet_id;
    if (predId) {
      setTab(document.getElementById('tab-btn-p'), 'p');
      setTimeout(function(){ pred_select(predId); }, 300);
    }
  }
}

// ⌘K / Ctrl+K keyboard shortcut
document.addEventListener('keydown', function(e) {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    if (_gsOpen) gsClose(); else gsOpen();
  }
  if (e.key === 'Escape' && _gsOpen) gsClose();
});

// ── Intake Faza 2 — Template predmeti ───────────────────────────────────────

var _intakeTplData = null;

async function intakeTemplateOpen() {
  var overlay = document.getElementById('intake-tpl-overlay');
  if (overlay) { overlay.style.display = 'flex'; }
  var listEl = document.getElementById('intake-tpl-list');
  if (listEl) listEl.innerHTML = '<div style="padding:1rem;text-align:center;font-size:0.8rem;color:rgba(255,255,255,0.35);">Učitavam šablone...</div>';
  if (!_intakeTplData) {
    try {
      var r = await fetch('/api/intake/templates', { headers: { 'Authorization': 'Bearer ' + currentSession.access_token } });
      var d = await r.json();
      _intakeTplData = d.templates || [];
    } catch(e) { _intakeTplData = []; }
  }
  _intakeRenderTpl();
}

function intakeTemplateClose() {
  var overlay = document.getElementById('intake-tpl-overlay');
  if (overlay) overlay.style.display = 'none';
}

function _intakeRenderTpl() {
  var listEl = document.getElementById('intake-tpl-list');
  if (!listEl) return;
  if (!_intakeTplData || !_intakeTplData.length) {
    listEl.innerHTML = '<div style="padding:1rem;text-align:center;font-size:0.8rem;color:rgba(255,255,255,0.35);">Nema šablona.</div>';
    return;
  }
  var _TIP_COLOR = { gradjansko:'#89c8ff', radno:'#4ade80', porodicno:'#f97316', krivicno:'#f87171', privredno:'#a78bfa', upravno:'#94a3b8', izvrsenje:'#fbbf24' };
  listEl.innerHTML = _intakeTplData.map(function(t){
    var col = _TIP_COLOR[t.tip] || '#94a3b8';
    var docs = (t.potrebni_dokumenti || []).slice(0,3).join(', ');
    return '<div onclick="intakeTemplateIzaberi(\''+_htmlEsc(t.id)+'\',\''+_htmlEsc(t.naziv)+'\')" style="display:flex;align-items:flex-start;gap:0.75rem;padding:0.7rem 0.85rem;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:8px;cursor:pointer;transition:border-color .15s;" onmouseover="this.style.borderColor=\'rgba(74,168,255,0.25)\'" onmouseout="this.style.borderColor=\'rgba(255,255,255,0.07)\'">'
      +'<div style="flex:1;min-width:0;">'
      +'<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.25rem;">'
      +'<span style="font-size:0.82rem;font-weight:600;color:#e2e8f0;">'+_htmlEsc(t.naziv)+'</span>'
      +'<span style="font-size:0.58rem;padding:1px 6px;border-radius:4px;background:rgba(255,255,255,0.06);color:'+col+';text-transform:uppercase;letter-spacing:.05em;flex-shrink:0;">'+_htmlEsc(t.tip)+'</span>'
      +'</div>'
      +(docs ? '<div style="font-size:0.7rem;color:rgba(255,255,255,0.35);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">📎 '+_htmlEsc(docs)+(t.potrebni_dokumenti.length>3?' ...':'')+'</div>' : '')
      +'</div>'
      +'<span style="font-size:0.7rem;color:rgba(74,168,255,0.6);flex-shrink:0;align-self:center;">Izaberi →</span>'
      +'</div>';
  }).join('');
}

function intakeTemplateIzaberi(tplId, tplNaziv) {
  intakeTemplateClose();
  var nazEl = document.getElementById('intake-opis');
  window._selectedTplId    = tplId;
  window._selectedTplNaziv = tplNaziv;
  var step2 = document.getElementById('intake-s2');
  if (step2) {
    step2.querySelector && (step2.querySelector('.intake-step-heading') || {}).textContent;
    if (document.getElementById('intake-s1').style.display !== 'none') {
      intakeNext();
    }
  }
  if (nazEl && !nazEl.value) {
    nazEl.value = 'Predmet po šablonu: ' + tplNaziv;
    var ev = new Event('input'); nazEl.dispatchEvent(ev);
  }
  showToast('Šablon "' + tplNaziv + '" izabran — predmet će biti kreiran sa predefinisanom hronologijom.', 'info');
}

// ── Document Templates ───────────────────────────────────────────────────────

var _doctplSabloni  = null;
var _doctplAktivni  = null;

async function docTplOpen() {
  var overlay = document.getElementById('doctpl-overlay');
  if (overlay) overlay.style.display = 'flex';
  if (!_doctplSabloni) {
    try {
      var r = await fetch('/api/doc-templates/lista', { headers: { 'Authorization': 'Bearer ' + currentSession.access_token } });
      var d = await r.json();
      _doctplSabloni = d.sabloni || [];
    } catch(e) { _doctplSabloni = []; }
  }
  _doctplRenderLista();
  _doctplLoadPredmeti();
}

async function _doctplLoadPredmeti() {
  if (!currentSession) return;
  var sel = document.getElementById('doctpl-predmet-id');
  if (!sel) return;
  try {
    var r = await fetch('/api/predmeti?limit=100', { headers: { 'Authorization': 'Bearer ' + currentSession.access_token } });
    if (!r.ok) return;
    var d = await r.json();
    var lista = d.predmeti || d || [];
    sel.innerHTML = '<option value="">— Izaberi predmet —</option>'
      + lista.filter(function(p){ return p.status !== 'zatvoren' && p.status !== 'arhiviran'; })
             .slice(0, 50)
             .map(function(p){ return '<option value="'+p.id+'">'+_htmlEsc(p.naziv||'Bez naziva')+'</option>'; })
             .join('');
  } catch(e) {}
}

function docTplClose() {
  var overlay = document.getElementById('doctpl-overlay');
  if (overlay) overlay.style.display = 'none';
}

var _DOCTPL_TIP_ICO = { tuzba:'⚖️', zalba:'📨', punomocje:'✍️', opomena:'⚠️', ugovor:'📝' };

function _doctplRenderLista() {
  var el = document.getElementById('doctpl-list');
  if (!el || !_doctplSabloni) return;
  el.innerHTML = _doctplSabloni.map(function(s, i){
    var ico = _DOCTPL_TIP_ICO[s.tip] || '📄';
    return '<div onclick="docTplIzaberi('+i+')" style="padding:0.6rem 0.85rem;cursor:pointer;border-left:2px solid transparent;transition:all .15s;" onmouseover="this.style.background=\'rgba(74,168,255,0.06)\'" onmouseout="if(docTplGetAktivniIdx()!=='+i+')this.style.background=\'\';" id="doctpl-item-'+i+'">'
      +'<div style="font-size:0.75rem;font-weight:600;color:#e2e8f0;margin-bottom:2px;">'+ico+' '+_htmlEsc(s.naziv)+'</div>'
      +'<div style="font-size:0.62rem;color:rgba(255,255,255,0.32);">'+_htmlEsc(s.opis)+'</div>'
      +'</div>';
  }).join('');
}

function docTplGetAktivniIdx() {
  return _doctplAktivni ? _doctplSabloni.indexOf(_doctplAktivni) : -1;
}

function docTplIzaberi(idx) {
  _doctplAktivni = _doctplSabloni[idx];
  document.querySelectorAll('[id^="doctpl-item-"]').forEach(function(el, i){
    el.style.background = (i === idx) ? 'rgba(74,168,255,0.08)' : '';
    el.style.borderLeftColor = (i === idx) ? '#4aa8ff' : 'transparent';
  });

  var titleEl   = document.getElementById('doctpl-form-title');
  var fieldsEl  = document.getElementById('doctpl-fields');
  var genBtn    = document.getElementById('doctpl-gen-btn');
  var predRow   = document.getElementById('doctpl-predmet-row');
  var resultWrap = document.getElementById('doctpl-result-wrap');
  var loadingEl = document.getElementById('doctpl-loading');

  if (titleEl)    { titleEl.textContent = _doctplAktivni.naziv; titleEl.style.display = 'block'; }
  if (genBtn)     genBtn.style.display = 'flex';
  if (predRow)    predRow.style.display = 'flex';
  if (resultWrap) resultWrap.style.display = 'none';
  if (loadingEl)  loadingEl.style.display = 'none';

  var _FIELD_LABELS = {
    ime_tuzitelja:'Ime tužioca', adresa_tuzitelja:'Adresa tužioca', ime_tuzenog:'Ime tuženog',
    adresa_tuzenog:'Adresa tuženog', cinjenice:'Činjenični opis', vrednost_spora_rsd:'Vrednost spora (RSD)',
    datum:'Datum', ime_stranke:'Ime stranke', broj_predmeta:'Broj predmeta', naziv_suda:'Naziv suda',
    datum_presude:'Datum presude', razlozi_zalbe:'Razlozi žalbe', ime_vlastodavca:'Ime vlastodavca',
    jmbg_vlastodavca:'JMBG vlastodavca', adresa_vlastodavca:'Adresa vlastodavca',
    ime_punomoćnika:'Ime punomoćnika (advokat)', ime_poverioca:'Ime poverioca',
    ime_duznika:'Ime dužnika', adresa_duznika:'Adresa dužnika', iznos_rsd:'Iznos (RSD)',
    osnov_duga:'Osnov duga', rok_dana:'Rok za plaćanje (dana)', ime_narucioca:'Ime naručioca',
    adresa_narucioca:'Adresa naručioca', ime_izvodjaca:'Ime izvođača', adresa_izvodjaca:'Adresa izvođača',
    opis_posla:'Opis posla', rok_izvrsenja:'Rok izvršenja', naknada_rsd:'Naknada (RSD)',
    ime_zajmodavca:'Ime zajmodavca', ime_zajmoprimca:'Ime zajmoprimca', iznos_rsd:'Iznos (RSD)',
    rok_vracanja:'Rok vraćanja', kamata_posto:'Kamata (%)', ime_trazioca:'Tražilac izvršenja',
    adresa_trazioca:'Adresa tražioca', izvrsna_isprava:'Izvršna isprava', nacin_izvrsenja:'Način izvršenja'
  };

  var today = new Date().toISOString().slice(0,10);
  if (fieldsEl) {
    fieldsEl.innerHTML = (_doctplAktivni.polja || []).map(function(f){
      var isMultiline = f === 'cinjenice' || f === 'razlozi_zalbe' || f === 'opis_posla' || f === 'osnov_duga';
      var lbl = _FIELD_LABELS[f] || f;
      var defaultVal = f === 'datum' ? today : '';
      return '<div style="display:flex;flex-direction:column;gap:3px;">'
        +'<label style="font-size:0.68rem;color:rgba(255,255,255,0.45);">'+_htmlEsc(lbl)+'</label>'
        +(isMultiline
          ? '<textarea id="dtf-'+f+'" rows="3" style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:7px 10px;color:#e2e8f0;font-size:0.78rem;font-family:inherit;outline:none;resize:vertical;">'+defaultVal+'</textarea>'
          : '<input id="dtf-'+f+'" type="text" value="'+_htmlEsc(defaultVal)+'" style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:7px 10px;color:#e2e8f0;font-size:0.78rem;font-family:inherit;outline:none;">')
        +'</div>';
    }).join('');
  }
}

async function docTplGeneriši() {
  if (!_doctplAktivni || !currentSession) return;
  var polja = {};
  (_doctplAktivni.polja || []).forEach(function(f){
    var el = document.getElementById('dtf-'+f);
    if (el) polja[f] = el.value.trim();
  });
  var genBtn   = document.getElementById('doctpl-gen-btn');
  var loadEl   = document.getElementById('doctpl-loading');
  var resultWr = document.getElementById('doctpl-result-wrap');
  if (genBtn)  genBtn.style.display = 'none';
  if (loadEl)  loadEl.style.display = 'block';
  try {
    var r = await fetch('/api/doc-templates/generisi', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + currentSession.access_token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ sablon_id: _doctplAktivni.id, polja: polja }),
    });
    var d = await r.json();
    if (!r.ok) { showToast(d.detail || 'Greška pri generisanju', 'error'); return; }
    var txtEl = document.getElementById('doctpl-result-txt');
    if (txtEl) txtEl.value = d.sadrzaj || '';
    if (resultWr) resultWr.style.display = 'block';
  } catch(e) {
    showToast('Greška: ' + e.message, 'error');
  } finally {
    if (loadEl)  loadEl.style.display = 'none';
    if (genBtn)  genBtn.style.display = 'flex';
  }
}

function docTplKopiraj() {
  var el = document.getElementById('doctpl-result-txt');
  if (!el) return;
  navigator.clipboard.writeText(el.value).then(function(){ showToast('Dokument kopiran!', 'success'); });
}

async function docTplSacuvaj() {
  if (!currentSession) return;
  var txtEl   = document.getElementById('doctpl-result-txt');
  var predEl  = document.getElementById('doctpl-predmet-id');
  if (!txtEl || !txtEl.value.trim()) { showToast('Nema dokumenta za čuvanje', 'info'); return; }
  var predId  = predEl ? predEl.value : '';
  if (!predId) { showToast('Izaberite predmet iz liste', 'info'); return; }
  try {
    var r = await fetch('/api/doc-templates/sacuvaj', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + currentSession.access_token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ predmet_id: predId, naziv: _doctplAktivni ? _doctplAktivni.naziv : 'Dokument', sadrzaj: txtEl.value, sablon_id: _doctplAktivni ? _doctplAktivni.id : '' }),
    });
    var d = await r.json();
    if (!r.ok) { showToast(d.detail || 'Greška', 'error'); return; }
    showToast('Dokument sačuvan uz predmet!', 'success');
  } catch(e) { showToast('Greška: ' + e.message, 'error'); }
}

// ── Onboarding Welcome Flow ──────────────────────────────────────────────────

function onboardingCheck() {
  if (!currentSession || !currentUser) return;
  var uid = currentUser.id || currentUser.user_id || '';
  var key = 'vx_onboarded_' + uid.slice(0, 8);
  if (localStorage.getItem(key)) return;
  var createdAt = currentUser.created_at || '';
  var isNew = !createdAt || (Date.now() - new Date(createdAt).getTime()) < 7 * 24 * 60 * 60 * 1000;
  if (!isNew) { localStorage.setItem(key, '1'); return; }
  var overlay = document.getElementById('onboarding-overlay');
  if (overlay) overlay.style.display = 'flex';
}

function onboardingDismiss() {
  var overlay = document.getElementById('onboarding-overlay');
  if (overlay) overlay.style.display = 'none';
  if (!currentUser) return;
  var uid = currentUser.id || currentUser.user_id || '';
  localStorage.setItem('vx_onboarded_' + uid.slice(0, 8), '1');
}

function onboardingStep(step) {
  onboardingDismiss();
  if (step === 1) {
    var tabBtn = document.getElementById('tab-btn-k');
    if (tabBtn) setTab(tabBtn, 'k');
    setTimeout(function(){
      var addBtn = document.querySelector('.crm-add-btn');
      if (addBtn) addBtn.click();
    }, 400);
  } else if (step === 2) {
    intakeOtvori();
  } else if (step === 3) {
    var tabBtn = document.getElementById('tab-btn-q');
    if (tabBtn) setTab(tabBtn, 'q');
    setTimeout(function(){
      var inp = document.getElementById('qi');
      if (inp) inp.focus();
    }, 300);
  }
}

// ── Integracije — Phase 5.5 ──────────────────────────────────────────────────

function integr_copy(tip) {
  var base = window.location.origin;
  var urls = {
    analyze: base + '/v1/analyze',
    predmeti: base + '/v1/predmeti',
    clio:    base + '/v1/webhook/clio',
    imanage: base + '/v1/webhook/imanage',
  };
  var url = urls[tip] || '';
  if (!url) return;
  navigator.clipboard.writeText(url).then(function(){
    showToast('URL kopiran: ' + url, 'ok');
  }).catch(function(){ showToast('Kopiranje nije uspelo.', 'err'); });
}

/* ── Waitlist Admin ────────────────────────────────────────────────────────── */
var _wlAdminData = [];

function wl_admin_load() {
  if (!currentSession || !currentUserIsFounder) return;
  var emptyEl = document.getElementById('wl-admin-empty');
  var tableEl = document.getElementById('wl-admin-table');
  if (emptyEl) emptyEl.textContent = 'Učitavam...';
  if (tableEl) tableEl.style.display = 'none';

  fetch('/waitlist/admin/lista', {
    headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
  }).then(function(r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }).then(function(d) {
    _wlAdminData = d.prijave || [];
    _wl_admin_render(d);
  }).catch(function(e) {
    if (emptyEl) emptyEl.textContent = 'Greška: ' + e.message;
  });
}

function _wl_admin_render(d) {
  var statsEl = document.getElementById('wl-admin-stats');
  var emptyEl = document.getElementById('wl-admin-empty');
  var tableEl = document.getElementById('wl-admin-table');
  var tbodyEl = document.getElementById('wl-admin-tbody');

  if (statsEl) {
    var statColor = { pending: '#ffaa40', contacted: '#4aa8ff', active: '#4ade80' };
    statsEl.innerHTML = [
      { label: 'Ukupno', val: d.total || 0, color: 'rgba(255,255,255,0.5)' },
      { label: 'Na čekanju', val: d.pending || 0, color: '#ffaa40' },
      { label: 'Aktivni', val: d.active || 0, color: '#4ade80' },
    ].map(function(s) {
      return '<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:6px 12px;text-align:center;">'
        + '<div style="font-size:1.1rem;font-weight:700;color:' + s.color + ';">' + s.val + '</div>'
        + '<div style="font-size:.65rem;color:rgba(255,255,255,0.35);margin-top:1px;">' + s.label + '</div>'
        + '</div>';
    }).join('');
  }

  if (!_wlAdminData.length) {
    if (emptyEl) emptyEl.textContent = 'Nema prijava još.';
    if (tableEl) tableEl.style.display = 'none';
    return;
  }

  if (emptyEl) emptyEl.textContent = '';
  if (tableEl) tableEl.style.display = 'table';

  var statusColors = { pending: '#ffaa40', contacted: '#4aa8ff', active: '#4ade80' };
  var statusLabels = { pending: 'Na čekanju', contacted: 'Kontaktiran', active: 'Aktivan' };

  tbodyEl.innerHTML = _wlAdminData.map(function(p) {
    var dt = p.created_at ? new Date(p.created_at).toLocaleDateString('sr-Latn-RS') : '—';
    var st = p.status || 'pending';
    var col = statusColors[st] || '#888';
    var options = ['pending','contacted','active'].map(function(s) {
      return '<option value="' + s + '"' + (s === st ? ' selected' : '') + '>' + (statusLabels[s] || s) + '</option>';
    }).join('');
    return '<tr style="border-top:1px solid rgba(255,255,255,0.05);">'
      + '<td style="padding:6px 8px;color:rgba(255,255,255,0.85);">' + escHtml(p.ime || '') + '</td>'
      + '<td style="padding:6px 8px;"><a href="mailto:' + escHtml(p.email) + '" style="color:#4aa8ff;">' + escHtml(p.email) + '</a></td>'
      + '<td style="padding:6px 8px;color:rgba(255,255,255,0.55);">' + escHtml(p.firma || '—') + '</td>'
      + '<td style="padding:6px 8px;color:rgba(255,255,255,0.45);max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + escHtml(p.poruka || '') + '">' + escHtml((p.poruka || '—').substring(0, 40)) + '</td>'
      + '<td style="padding:6px 8px;color:rgba(255,255,255,0.35);">' + dt + '</td>'
      + '<td style="padding:6px 8px;">'
      + '<select onchange="wl_admin_set_status(\'' + p.id + '\', this.value)" '
      + 'style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:5px;color:' + col + ';font-size:.72rem;padding:2px 5px;cursor:pointer;">'
      + options + '</select></td>'
      + '</tr>';
  }).join('');
}

function wl_admin_set_status(id, status) {
  if (!currentSession) return;
  fetch('/waitlist/admin/' + id + '/status?status=' + encodeURIComponent(status), {
    method: 'PATCH',
    headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
  }).then(function(r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    showToast('Status ažuriran.', 'ok');
    var entry = _wlAdminData.find(function(p) { return p.id === id; });
    if (entry) entry.status = status;
  }).catch(function(e) {
    showToast('Greška: ' + e.message, 'err');
    wl_admin_load();
  });
}

// ── Tracking helper ──────────────────────────────────────────
function piTrack(feature, action, metadata) {
  if (!currentSession) return;
  try {
    fetch(BASE_URL + '/analytics/track', {
      method: 'POST',
      headers: {'Content-Type':'application/json','Authorization':'Bearer '+currentSession.access_token},
      body: JSON.stringify({feature: feature, action: action, metadata: metadata || null})
    }).catch(function(){});
  } catch(e) {}
}

// ── Helpers ──────────────────────────────────────────────────
function _piTrend(str) {
  if (!str) return '';
  var up = str.startsWith('+') && str !== '+0%';
  var dn = str.startsWith('-');
  var cls = up ? 'up' : (dn ? 'down' : 'flat');
  return '<span class="pi-kpi-trend '+cls+'">'+escHtml(str)+'</span>';
}

function _piColor(pct) {
  if (pct === null || pct === undefined) return 'rgba(255,255,255,0.06)';
  if (pct >= 70) return 'rgba(74,222,128,0.55)';
  if (pct >= 40) return 'rgba(74,168,255,0.45)';
  if (pct >= 20) return 'rgba(251,146,60,0.45)';
  return 'rgba(248,113,113,0.35)';
}

function _piFormatMin(min) {
  if (min < 1)   return '<1m';
  if (min < 60)  return Math.round(min) + 'm';
  return (min/60).toFixed(1) + 'h';
}

// ── SVG Line chart ────────────────────────────────────────────
function _piLineChart(timeline, field, color, height) {
  height = height || 60;
  var w = 600, h = height;
  if (!timeline || !timeline.length) return '<svg viewBox="0 0 '+w+' '+h+'"></svg>';
  var vals = timeline.map(function(d){return d[field]||0;});
  var maxV = Math.max.apply(null, vals) || 1;
  var pts  = vals.map(function(v,i){
    var x = (i/(vals.length-1||1))*w;
    var y = h - (v/maxV)*(h-4) - 2;
    return x.toFixed(1)+','+y.toFixed(1);
  }).join(' ');
  var fill = vals.map(function(v,i){
    var x = (i/(vals.length-1||1))*w;
    var y = h - (v/maxV)*(h-4) - 2;
    return x.toFixed(1)+','+y.toFixed(1);
  });
  fill.push(w+','+h); fill.unshift('0,'+h);
  var fillPts = fill.join(' ');
  return '<svg viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">'
    + '<defs><linearGradient id="piFill" x1="0" y1="0" x2="0" y2="1">'
    + '<stop offset="0%" stop-color="'+color+'" stop-opacity="0.25"/>'
    + '<stop offset="100%" stop-color="'+color+'" stop-opacity="0.02"/>'
    + '</linearGradient></defs>'
    + '<polygon points="'+fillPts+'" fill="url(#piFill)"/>'
    + '<polyline points="'+pts+'" fill="none" stroke="'+color+'" stroke-width="2"/>'
    + '</svg>';
}

// ── Render overview section ───────────────────────────────────
function _piRenderOverview(ov, tl) {
  var h = '';
  h += '<div class="pi-kpi-grid">';
  h += '<div class="pi-kpi">'+_piTrend('')+'<div class="pi-kpi-val">'+(ov.dau||0)+'</div><div class="pi-kpi-lbl">DAU · hoje</div></div>';
  h += '<div class="pi-kpi">'+_piTrend('')+'<div class="pi-kpi-val">'+(ov.wau||0)+'</div><div class="pi-kpi-lbl">WAU · 7 dana</div></div>';
  h += '<div class="pi-kpi">'+_piTrend(ov.mau_trend)+'<div class="pi-kpi-val">'+(ov.mau||0)+'</div><div class="pi-kpi-lbl">MAU · 30 dana</div></div>';
  h += '<div class="pi-kpi"><div class="pi-kpi-val">'+(ov.total_korisnika_90d||0)+'</div><div class="pi-kpi-lbl">Korisnika · 90d</div></div>';
  h += '</div>';
  // Stats row
  h += '<div class="pi-stats-row" style="margin-bottom:1.5rem;">';
  h += '<div class="pi-stat"><div class="pi-stat-val">'+_piFormatMin(ov.avg_session_minutes||0)+'</div><div class="pi-stat-lbl">Prosečna sesija</div></div>';
  h += '<div class="pi-stat"><div class="pi-stat-val">'+(ov.total_sessions_90d||0)+'</div><div class="pi-stat-lbl">Sesija · 90d</div></div>';
  h += '<div class="pi-stat"><div class="pi-stat-val">'+(ov.total_events_30d||0)+'</div><div class="pi-stat-lbl">Događaja · 30d</div></div>';
  h += '</div>';
  // DAU timeline chart
  if (tl && tl.timeline && tl.timeline.length) {
    h += '<div class="pi-section">';
    h += '<div class="pi-section-hd"><span>Dnevno aktivni korisnici (DAU)</span><span style="color:rgba(255,255,255,0.2);font-size:0.5rem;">poslednji '+tl.period_dana+' dana · peak='+tl.peak_dau+' ('+escHtml(tl.peak_datum||'-')+')</span></div>';
    h += '<div class="pi-chart-wrap">'+_piLineChart(tl.timeline,'dau','#4aa8ff',80)+'</div>';
    h += '<div style="display:flex;justify-content:space-between;margin-top:0.3rem;">';
    h += '<span style="font-family:JetBrains Mono,monospace;font-size:0.46rem;color:rgba(255,255,255,0.22);">'+(tl.timeline[0]||{}).datum+'</span>';
    h += '<span style="font-family:JetBrains Mono,monospace;font-size:0.46rem;color:rgba(255,255,255,0.22);">'+(tl.timeline[tl.timeline.length-1]||{}).datum+'</span>';
    h += '</div></div>';
    // Events chart
    h += '<div class="pi-section">';
    h += '<div class="pi-section-hd">Događaji po danu (Events)</div>';
    h += '<div class="pi-chart-wrap">'+_piLineChart(tl.timeline,'events','#c9a84c',60)+'</div>';
    h += '</div>';
  }
  return h;
}

// ── Render features section ───────────────────────────────────
function _piRenderFeatures(fd) {
  var h = '';
  var top = fd.top_features || [];
  var least = fd.least_used || [];
  var maxEv = top.length ? top[0].events : 1;

  h += '<div class="pi-section">';
  h += '<div class="pi-section-hd"><span>Najkorišćenije funkcije</span>';
  h += '<span style="color:rgba(255,255,255,0.2);font-size:0.5rem;">Ukupno kredita: <b style="color:#c9a84c">'+(fd.total_credits_spent||0)+'</b></span></div>';
  top.forEach(function(f){
    var barPct = maxEv ? Math.round(f.events/maxEv*100) : 0;
    h += '<div class="pi-feat-row">';
    h += '<div class="pi-feat-name" title="'+escHtml(f.feature)+'">'+escHtml(f.feature)+'</div>';
    h += '<div class="pi-feat-bar-wrap"><div class="pi-feat-bar" style="width:'+barPct+'%"></div></div>';
    h += '<div class="pi-feat-cnt">'+f.events+'</div>';
    if (f.credits_spent>0) h += '<div class="pi-feat-cred">'+f.credits_spent+'cr</div>';
    else h += '<div class="pi-feat-cred" style="color:rgba(255,255,255,0.15)">-</div>';
    h += '</div>';
  });
  h += '</div>';

  // Least used
  if (least.length) {
    h += '<div class="pi-section">';
    h += '<div class="pi-section-hd">Najmanje korišćene funkcije <span class="pi-least-badge">Šansa za poboljšanje</span></div>';
    least.forEach(function(f){
      h += '<div class="pi-feat-row">';
      h += '<div class="pi-feat-name">'+escHtml(f.feature)+'</div>';
      h += '<div class="pi-feat-bar-wrap"><div class="pi-feat-bar" style="width:'+(f.events/maxEv*100)+'%;background:linear-gradient(90deg,rgba(251,146,60,0.4),rgba(251,146,60,0.2))"></div></div>';
      h += '<div class="pi-feat-cnt">'+f.events+'</div>';
      h += '<div class="pi-feat-cred" style="color:rgba(255,255,255,0.2)">'+f.unique_users+'u</div>';
      h += '</div>';
    });
    h += '</div>';
  }
  return h;
}

// ── Render retention heatmap ──────────────────────────────────
function _piRenderRetention(ret) {
  var h = '';
  var cohorts = ret.cohorts || [];
  var d7  = ret.d7_rate;
  var d30 = ret.d30_rate;

  // D7/D30 rate pills
  h += '<div style="display:flex;gap:1rem;margin-bottom:1.2rem;">';
  h += '<div class="pi-stat" style="flex:1"><div class="pi-stat-val" style="color:'+(d7>=40?'#4ade80':'#fb923c')+'">'+(d7!==null?d7+'%':'N/A')+'</div><div class="pi-stat-lbl">D7 Retention</div></div>';
  h += '<div class="pi-stat" style="flex:1"><div class="pi-stat-val" style="color:'+(d30>=20?'#4ade80':'#fb923c')+'">'+(d30!==null?d30+'%':'N/A')+'</div><div class="pi-stat-lbl">D30 Retention</div></div>';
  h += '</div>';

  if (!cohorts.length) {
    h += '<div class="pi-empty">Nema dovoljno podataka za kohortnu analizu.</div>';
    return h;
  }

  // Header
  h += '<div class="pi-ret-head">';
  h += '<div class="pi-ret-head-cell" style="text-align:left">Nedelja</div>';
  h += '<div class="pi-ret-head-cell">W0 (100%)</div>';
  h += '<div class="pi-ret-head-cell">W1</div>';
  h += '<div class="pi-ret-head-cell">W2</div>';
  h += '<div class="pi-ret-head-cell">W3</div>';
  h += '<div class="pi-ret-head-cell">W4</div>';
  h += '</div>';

  cohorts.slice(-8).forEach(function(c){
    h += '<div class="pi-ret-row">';
    h += '<div class="pi-ret-week">'+c.week.slice(5)+'</div>';
    // W0 = 100%
    h += '<div class="pi-ret-cell" style="background:rgba(74,168,255,0.5);color:rgba(255,255,255,0.9)">'+c.users+'u</div>';
    ['W1','W2','W3','W4'].forEach(function(w){
      var v = c[w];
      var txt = v===null||v===undefined ? '–' : v+'%';
      var bg  = v===null||v===undefined ? 'rgba(255,255,255,0.03)' : _piColor(v);
      h += '<div class="pi-ret-cell" style="background:'+bg+';color:rgba(255,255,255,'+(v===null?'0.15':'0.85')+')">'+txt+'</div>';
    });
    h += '</div>';
  });
  return h;
}

// ── Render funnels ────────────────────────────────────────────
var _piFunnelIdx = 0;
function _piRenderFunnels(fd) {
  var funnels = fd.funnels || [];
  var h = '';
  if (!funnels.length) return '<div class="pi-empty">Nema funnel podataka.</div>';

  h += '<div class="pi-funnel-tabs">';
  funnels.forEach(function(f,i){
    h += '<button class="pi-ftab'+(i===_piFunnelIdx?' active':'')+'" onclick="_piSelectFunnel('+i+')">'+escHtml(f.naziv)+'</button>';
  });
  h += '</div>';
  h += '<div id="pi-funnel-body">';
  h += _piRenderOneFunnel(funnels[_piFunnelIdx] || funnels[0]);
  h += '</div>';
  return h;
}

function _piSelectFunnel(idx) {
  _piFunnelIdx = idx;
  var tabs = document.querySelectorAll('.pi-ftab');
  tabs.forEach(function(t,i){t.classList.toggle('active',i===idx);});
  var body = document.getElementById('pi-funnel-body');
  if (!body || !window._piFunnelData) return;
  body.innerHTML = _piRenderOneFunnel(window._piFunnelData[idx]);
}

function _piRenderOneFunnel(f) {
  if (!f) return '';
  var h = '';
  var maxN = (f.koraci && f.koraci[0]) ? f.koraci[0].korisnici : 1;
  h += '<div style="margin-bottom:0.6rem;font-family:JetBrains Mono,monospace;font-size:0.56rem;color:rgba(255,255,255,0.3);">';
  h += 'Ukupna konverzija: <b style="color:#4aa8ff">'+(f.ukupna_konverzija||0)+'%</b> · Korisnika: <b style="color:rgba(255,255,255,0.6)">'+(f.ukupno_korisnika||0)+'</b>';
  h += '</div>';
  h += '<div class="pi-funnel">';
  (f.koraci||[]).forEach(function(k){
    var barPct = maxN ? Math.round(k.korisnici/maxN*100) : 0;
    h += '<div class="pi-funnel-step">';
    h += '<div class="pi-funnel-label">'+escHtml(k.label)+'</div>';
    h += '<div class="pi-funnel-bar-wrap"><div class="pi-funnel-bar" style="width:'+barPct+'%"></div>';
    h += '<span class="pi-funnel-pct">'+k.konverzija+'%</span></div>';
    h += '<div class="pi-funnel-n">'+k.korisnici+'</div>';
    h += '</div>';
  });
  h += '</div>';
  return h;
}

// ── Main load function ────────────────────────────────────────
async function piLoad() {
  if (!currentSession) return;
  var body = document.getElementById('pi-body');
  if (!body) return;
  body.innerHTML = '<div class="pi-empty">Učitavam podatke...</div>';
  piTrack('dashboard_pi','view');

  var hdr = {'Authorization':'Bearer '+currentSession.access_token};
  try {
    var [ovR, featR, retR, funR, tlR, plR] = await Promise.all([
      fetch(BASE_URL+'/admin/pi/overview',  {headers:hdr}),
      fetch(BASE_URL+'/admin/pi/features',  {headers:hdr}),
      fetch(BASE_URL+'/admin/pi/retention', {headers:hdr}),
      fetch(BASE_URL+'/admin/pi/funnels',   {headers:hdr}),
      fetch(BASE_URL+'/admin/pi/timeline',  {headers:hdr}),
      fetch(BASE_URL+'/admin/pi/plans',     {headers:hdr}),
    ]);

    if (ovR.status===403) {
      body.innerHTML='<div class="pi-empty">Pristup odbijen — admin only.</div>';
      return;
    }

    var ov   = ovR.ok   ? await ovR.json()   : {};
    var feat = featR.ok ? await featR.json()  : {};
    var ret  = retR.ok  ? await retR.json()   : {};
    var fun  = funR.ok  ? await funR.json()   : {};
    var tl   = tlR.ok   ? await tlR.json()    : {};
    var pl   = plR.ok   ? await plR.json()    : {};

    window._piFunnelData = fun.funnels || [];

    var h = '';

    // Plan distribucija + MRR (na vrhu — najvažniji business metric)
    h += _piRenderPlans(pl);

    // Overview KPIs + charts
    h += _piRenderOverview(ov, tl);

    // Features
    h += '<div class="pi-section">';
    h += '<div class="pi-section-hd"><span>Analiza funkcija</span>';
    h += '<select class="pi-period-sel" onchange="piReloadFeatures(this.value)">';
    ['7','14','30','60','90'].forEach(function(d){h+='<option value="'+d+'"'+(d==='30'?' selected':'')+'>'+d+'d</option>';});
    h += '</select></div>';
    h += _piRenderFeatures(feat);
    h += '</div>';

    // Retention
    h += '<div class="pi-section">';
    h += '<div class="pi-section-hd">Kohortna retencija korisnika</div>';
    h += _piRenderRetention(ret);
    h += '</div>';

    // Funnels
    h += '<div class="pi-section">';
    h += '<div class="pi-section-hd">Funnel analiza konverzije</div>';
    h += _piRenderFunnels(fun);
    h += '</div>';

    body.innerHTML = h;
  } catch(e) {
    body.innerHTML = '<div class="pi-empty">Greška: '+escHtml(String(e))+'</div>';
  }
}

function _piRenderPlans(pl) {
  if (!pl || !pl.plan_distribucija) return '';
  var dist = pl.plan_distribucija || {};
  var total = pl.ukupno_korisnika || 0;
  var h = '';

  // MRR / ARR header row
  h += '<div class="pi-section" style="background:linear-gradient(135deg,rgba(30,58,95,0.6),rgba(13,39,68,0.4));border:1px solid rgba(74,168,255,0.15);border-radius:10px;padding:1rem 1.1rem;margin-bottom:1rem;">';
  h += '<div style="font-size:0.6rem;color:rgba(255,255,255,0.35);text-transform:uppercase;letter-spacing:.1em;font-weight:700;margin-bottom:0.7rem;">Revenue · Planovi · AI Usage</div>';

  // KPI row
  h += '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:0.5rem;margin-bottom:1rem;">';
  var mrr = (pl.mrr_eur||0).toFixed(0);
  var arr = (pl.arr_eur||0).toFixed(0);
  var paid = pl.placajuci || 0;
  var cvr = total > 0 ? (paid/total*100).toFixed(1) : '0';
  h += '<div class="pi-kpi" style="background:rgba(74,168,255,0.06);"><div class="pi-kpi-val" style="color:#4aa8ff;">€'+mrr+'</div><div class="pi-kpi-lbl">MRR procena</div></div>';
  h += '<div class="pi-kpi" style="background:rgba(74,168,255,0.06);"><div class="pi-kpi-val" style="color:#4ade80;">€'+arr+'</div><div class="pi-kpi-lbl">ARR procena</div></div>';
  h += '<div class="pi-kpi" style="background:rgba(74,168,255,0.06);"><div class="pi-kpi-val">'+paid+'</div><div class="pi-kpi-lbl">Plaćajućih</div></div>';
  h += '<div class="pi-kpi" style="background:rgba(74,168,255,0.06);"><div class="pi-kpi-val" style="color:'+(parseFloat(cvr)>=5?'#4ade80':'#fb923c')+';">'+cvr+'%</div><div class="pi-kpi-lbl">Konverzija</div></div>';
  h += '</div>';

  // Plan distribucija bars
  h += '<div style="font-size:0.55rem;color:rgba(255,255,255,0.3);text-transform:uppercase;letter-spacing:.08em;font-weight:600;margin-bottom:0.5rem;">Distribucija planova</div>';
  var planColors = {free:'rgba(148,163,184,0.4)', advokat:'rgba(74,168,255,0.6)', pro:'rgba(201,168,76,0.7)', firma:'rgba(139,92,246,0.7)'};
  var planLabels = {free:'Besplatno', advokat:'Advokat €19', pro:'Pro €39', firma:'Firma €59'};
  ['free','advokat','pro','firma'].forEach(function(pt){
    var n = dist[pt] || 0;
    var pct = total > 0 ? Math.round(n/total*100) : 0;
    h += '<div class="pi-feat-row" style="margin-bottom:0.3rem;">';
    h += '<div class="pi-feat-name" style="min-width:90px;color:rgba(255,255,255,0.7);">'+planLabels[pt]+'</div>';
    h += '<div class="pi-feat-bar-wrap"><div class="pi-feat-bar" style="width:'+pct+'%;background:'+planColors[pt]+';"></div></div>';
    h += '<div class="pi-feat-cnt">'+n+'</div>';
    h += '<div class="pi-feat-cred" style="color:rgba(255,255,255,0.3);">'+pct+'%</div>';
    h += '</div>';
  });

  // AI Usage ovog meseca
  var ai = pl.ai_usage_ovaj_mesec || {};
  h += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:0.4rem;margin-top:0.8rem;">';
  h += '<div class="pi-stat"><div class="pi-stat-val">'+(ai.ai_queries||0)+'</div><div class="pi-stat-lbl">AI upita · ovaj mesec</div></div>';
  h += '<div class="pi-stat"><div class="pi-stat-val">'+(ai.doc_analyses||0)+'</div><div class="pi-stat-lbl">Analiza dok. · ovaj mesec</div></div>';
  h += '<div class="pi-stat"><div class="pi-stat-val">'+(ai.strategies||0)+'</div><div class="pi-stat-lbl">Strategija · ovaj mesec</div></div>';
  h += '</div>';

  // Onboarding email funnel
  var ob = pl.onboarding_emails || {};
  var obr = pl.onboarding_rates || {};
  h += '<div style="margin-top:0.8rem;padding-top:0.7rem;border-top:1px solid rgba(255,255,255,0.06);">';
  h += '<div style="font-size:0.55rem;color:rgba(255,255,255,0.3);text-transform:uppercase;letter-spacing:.08em;font-weight:600;margin-bottom:0.4rem;">Onboarding email sekvenca</div>';
  h += '<div style="display:flex;gap:1.5rem;">';
  [['welcome','Welcome',obr.welcome_rate],['day1','Day 1',obr.day1_rate],['day3','Day 3',obr.day3_rate]].forEach(function(item){
    h += '<div style="text-align:center;">';
    h += '<div style="font-size:0.85rem;font-weight:700;color:#4aa8ff;">'+(ob[item[0]]||0)+'</div>';
    h += '<div style="font-size:0.52rem;color:rgba(255,255,255,0.35);">'+item[1]+' · '+(item[2]||0)+'%</div>';
    h += '</div>';
  });
  h += '</div>';
  h += '</div>';

  h += '</div>'; // end pi-section
  return h;
}

async function piReloadFeatures(dana) {
  if (!currentSession) return;
  var hdr = {'Authorization':'Bearer '+currentSession.access_token};
  try {
    var r = await fetch(BASE_URL+'/admin/pi/features?dana='+dana, {headers:hdr});
    if (!r.ok) return;
    var feat = await r.json();
    // Find features section and update just the inner part
    var body = document.getElementById('pi-body');
    if (!body) return;
    // Re-render only features portion — find the existing section by recreating
    var featEl = body.querySelector('.pi-section');
    if (!featEl) return;
    // Simple approach: full reload
    piLoad();
  } catch(e) {}
}


/* ═══════════════════════════════ NEXT BLOCK ═══════════════════════════════ */


// F6 — PWA Service Worker registracija
if ('serviceWorker' in navigator) {
  window.addEventListener('load', function() {
    navigator.serviceWorker.register('/static/sw.js')
      .then(function(reg) { console.log('[Vindex] SW registered:', reg.scope); })
      .catch(function(err) { console.warn('[Vindex] SW registration failed:', err); });
  });
}


/* ═══════════════════════════════ NEXT BLOCK ═══════════════════════════════ */


// ═══════════════════════════════════════════════════════════════
// VOICE COMMAND ENGINE
// ═══════════════════════════════════════════════════════════════
var _voiceRec = null;
var _voiceActive = false;
var _voiceTextSent = false;  // guard: ne zatvaraj modal ako je execute već poslat

function _voice_close_modal() {
  var modal = document.getElementById('voice-modal');
  if (modal) modal.style.display = 'none';
  var btn = document.getElementById('voice-cmd-btn');
  if (btn) btn.classList.remove('voice-active');
  _voiceActive = false;
}

function voice_start() {
  if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    showToast('Glasovne komande zahtevaju Chrome ili Edge browser.', 'warn');
    return;
  }
  if (window.location.protocol !== 'https:' && window.location.hostname !== 'localhost') {
    showToast('Glasovne komande zahtevaju HTTPS konekciju.', 'warn');
    return;
  }
  // Zaustavi prethodno snimanje ako postoji
  if (_voiceRec) { try { _voiceRec.abort(); } catch(e){} _voiceRec = null; }

  var modal = document.getElementById('voice-modal');
  modal.style.display = 'flex';
  document.getElementById('voice-transcript').textContent = 'Izgovorite komandu...';
  document.getElementById('voice-status').textContent = '';
  var cmdBtn = document.getElementById('voice-cmd-btn');
  if (cmdBtn) cmdBtn.classList.add('voice-active');

  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  _voiceRec = new SpeechRecognition();
  _voiceRec.lang = 'sr-RS';
  _voiceRec.continuous = false;
  _voiceRec.interimResults = true;
  _voiceActive = true;
  _voiceTextSent = false;

  _voiceRec.onresult = function(e) {
    var transcript = '';
    for (var i = e.resultIndex; i < e.results.length; i++) {
      transcript += e.results[i][0].transcript;
    }
    document.getElementById('voice-transcript').textContent = transcript;
    if (e.results[e.results.length - 1].isFinal && transcript.trim()) {
      _voiceTextSent = true;
      voice_execute(transcript.trim());
    }
  };

  _voiceRec.onerror = function(e) {
    if (e.error === 'no-speech' || e.error === 'aborted') {
      // Tiho zatvori — nije greška, korisnik nije govorio
      _voice_close_modal();
      return;
    }
    var msgs = {
      'not-allowed':    '🔒 Dozvolite mikrofon u podešavanjima browsera.',
      'audio-capture':  '🎙 Mikrofon nije pronađen.',
      'network':        '🌐 Nema internet konekcije za glasovni unos.',
    };
    showToast(msgs[e.error] || ('Greška mikrofona: ' + e.error), 'err');
    _voice_close_modal();
  };

  _voiceRec.onend = function() {
    // Zatvorimo modal samo ako execute nije već preuzeo kontrolu
    if (!_voiceTextSent) {
      _voice_close_modal();
    }
  };

  try {
    _voiceRec.start();
  } catch(e) {
    showToast('Nije moguće pokrenuti mikrofon: ' + e.message, 'err');
    _voice_close_modal();
  }
}

function voice_stop() {
  if (_voiceRec) { try { _voiceRec.abort(); } catch(e){} _voiceRec = null; }
  _voice_close_modal();
}

function voice_execute(text) {
  if (!text) { _voice_close_modal(); return; }
  if (!currentSession) {
    _voice_close_modal();
    showToast('Prijavite se da biste koristili glasovne komande.', 'warn');
    openModal();
    return;
  }
  document.getElementById('voice-status').textContent = '⏳ Interpretiram komandu...';
  fetch('/api/voice/command', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + currentSession.access_token },
    body: JSON.stringify({ text: text }),
  }).then(function(r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }).then(function(d) {
    _voice_close_modal();
    voice_doAction(d.action, d.params || {});
    if (d.followup) { setTimeout(function() { voice_doAction(d.followup, {}); }, 900); }
  }).catch(function(e) {
    _voice_close_modal();
    showToast('Greška glasovne komande: ' + e.message, 'err');
  });
}

function voice_doAction(action, params) {
  if (!action) return;
  switch(action) {

    case 'navigate_predmet':
      var q = (params.query || '').trim().toLowerCase();
      if (!q) { showToast('Nije prepoznat naziv predmeta', 'warn'); break; }

      // 1. Pretraži _predmeti[] niz po nazivu, tužiocu ili tuženom
      var found = null;
      if (typeof _predmeti !== 'undefined' && _predmeti.length) {
        found = _predmeti.find(function(p) {
          return (p.naziv       || '').toLowerCase().includes(q) ||
                 (p.tuzilac     || '').toLowerCase().includes(q) ||
                 (p.tuzeni      || '').toLowerCase().includes(q) ||
                 (p.opis        || '').toLowerCase().includes(q);
        }) || null;
      }

      if (found) {
        // Prebaci na tab Predmeti pa otvori predmet
        setTab(document.getElementById('tab-btn-p'), 'p');
        setTimeout(function() { pred_select(found.id); }, 120);
        showToast('📂 Otvarám predmet: ' + found.naziv);
      } else {
        // Nije pronađen lokalno — otvori search modal i popuni query
        searchOpen();
        setTimeout(function() {
          var inp = document.getElementById('search-input');
          if (inp) {
            inp.value = params.query || q;
            inp.dispatchEvent(new Event('input'));
            searchDebounce();
          }
        }, 80);
        showToast('🔍 Tražim predmet: ' + (params.query || q), 'info');
      }
      break;

    case 'analyze_predmet':
      if (activePredmetId) { pred_subtabSwitch('ai-analiza'); pred_submitProcena && pred_submitProcena(); }
      else showToast('Najpre otvorite predmet', 'warn');
      break;

    case 'ask_question':
      var txt = params.text || '';
      if (txt) {
        var inp = document.getElementById('agent-input') || document.getElementById('pitanje-input');
        if (inp) { inp.value = txt; inp.dispatchEvent(new Event('input')); }
        if (typeof setTab === 'function') setTab(document.getElementById('tab-btn-agent'),'agent');
      }
      break;

    case 'generate_document':
      if (typeof setTab === 'function') setTab(document.getElementById('tab-btn-alati'),'alati');
      break;

    case 'show_tab':
      if (activePredmetId && params.tab) pred_subtabSwitch(params.tab);
      else if (!activePredmetId) showToast('Najpre otvorite predmet', 'warn');
      break;

    case 'start_timer':
      if (!activePredmetId) {
        showToast('Otvorite predmet pre pokretanja tajmera', 'warn');
        break;
      }
      // Koristi billing tajmer (API). Ako _billingPredmetId nije setovan, postavi ga.
      if (typeof _billingPredmetId !== 'undefined' && !_billingPredmetId) {
        _billingPredmetId = activePredmetId;
      }
      if (typeof billing_timerToggle === 'function') {
        // Pokreni samo ako tajmer nije već aktivan
        if (!_billingTimerSessionId) { billing_timerToggle(); }
        else showToast('Tajmer već radi', 'info');
      } else {
        showToast('Modul naplata nije učitan', 'warn');
      }
      break;

    case 'stop_timer':
      if (typeof _billingTimerSessionId !== 'undefined' && _billingTimerSessionId) {
        if (typeof billing_timerToggle === 'function') billing_timerToggle();
      } else if (typeof timer_stop === 'function' && activePredmetId) {
        timer_stop();
      } else {
        showToast('Tajmer nije aktivan', 'warn');
      }
      break;

    case 'show_dashboard':
      if (typeof setTab === 'function') setTab(document.getElementById('tab-btn-home'),'home');
      break;

    case 'show_klijenti':
      if (typeof setTab === 'function') setTab(document.getElementById('tab-btn-klijenti'),'klijenti');
      break;

    case 'search':
      if (params.query) {
        searchOpen();
        setTimeout(function() {
          var inp = document.getElementById('search-input');
          if (inp) { inp.value = params.query; inp.dispatchEvent(new Event('input')); searchDebounce(); }
        }, 80);
      }
      break;

    case 'procena_rizika':
      if (activePredmetId) { pred_subtabSwitch('ai-analiza'); pred_submitProcena && pred_submitProcena(); }
      else showToast('Najpre otvorite predmet', 'warn');
      break;

    case 'red_team':
      if (activePredmetId) pred_subtabSwitch('strategija');
      else showToast('Najpre otvorite predmet', 'warn');
      break;

    case 'hearing_prep':
      if (activePredmetId) pred_subtabSwitch('rokovi');
      else showToast('Najpre otvorite predmet', 'warn');
      break;

    default:
      showToast('Nisam razumeo: "' + (params.text||action) + '"', 'warn');
  }
}

// Alt+V shortcut
document.addEventListener('keydown', function(e) {
  if (e.altKey && (e.key === 'v' || e.key === 'V')) { e.preventDefault(); voice_start(); }
});

// voiceStart alias — topbar "🎤 Govori" dugme koristi voice_start (Phase 2 komande)
window.voiceStart = voice_start;

/* ── TTS — čitanje odgovora glasom (Web Speech API) ──────────────────────── */
var _ttsUtterance = null;
var _vxLastResponseText = '';  // globalna referenca — dugme čita odavde, bez inline teksta

function _tts_clean(text) {
  return (text || '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/#{1,6}\s*/g, '')
    .replace(/\*{1,2}([^*]+)\*{1,2}/g, '$1')
    .replace(/_{1,2}([^_]+)_{1,2}/g, '$1')
    .replace(/`[^`]+`/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/\n{2,}/g, '. ')
    .replace(/\n/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function _tts_pick_voice() {
  var voices = window.speechSynthesis.getVoices();
  return voices.find(function(v) { return v.lang.startsWith('sr'); })
      || voices.find(function(v) { return v.lang.startsWith('hr') || v.lang.startsWith('bs'); })
      || null;
}

function _tts_update_btn(speaking) {
  var btn = document.getElementById('vx-tts-play-btn');
  if (!btn) return;
  if (speaking) { btn.classList.add('speaking'); btn.innerHTML = '⏹ Zaustavi'; }
  else          { btn.classList.remove('speaking'); btn.innerHTML = '🔊 Pročitaj'; }
}

function vx_tts_speak(text) {
  if (!window.speechSynthesis) { showToast('Vaš browser ne podržava čitanje teksta.', 'warn'); return; }
  vx_tts_stop();
  var clean = _tts_clean(text);
  if (!clean) return;

  function _doSpeak() {
    _ttsUtterance = new SpeechSynthesisUtterance(clean);
    _ttsUtterance.lang = 'sr-RS';
    _ttsUtterance.rate = 0.92;
    _ttsUtterance.pitch = 1.0;
    var v = _tts_pick_voice();
    if (v) _ttsUtterance.voice = v;
    _ttsUtterance.onend = function() { _ttsUtterance = null; _tts_update_btn(false); };
    _ttsUtterance.onerror = function() { _ttsUtterance = null; _tts_update_btn(false); };
    window.speechSynthesis.speak(_ttsUtterance);
    _tts_update_btn(true);
  }

  // Glasovi se možda još učitavaju — sačekaj ako je lista prazna
  if (window.speechSynthesis.getVoices().length === 0) {
    window.speechSynthesis.onvoiceschanged = function() { window.speechSynthesis.onvoiceschanged = null; _doSpeak(); };
  } else {
    _doSpeak();
  }
}

function vx_tts_stop() {
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  _ttsUtterance = null;
  _tts_update_btn(false);
}

function vx_tts_toggle() {
  if (_ttsUtterance) { vx_tts_stop(); }
  else { vx_tts_speak(_vxLastResponseText); }
}

// ═══════════════════════════════════════════════════════════════
// TIMELINE ENGINE
// ═══════════════════════════════════════════════════════════════
function timeline_load() {
  if (!activePredmetId || !currentSession) return;
  var container = document.getElementById('timeline-container');
  if (!container) return;
  container.innerHTML = '<div style="color:rgba(255,255,255,.3);font-size:.8rem;">Učitavam...</div>';

  fetch('/api/predmeti/' + activePredmetId + '/hronologija', {
    headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
  }).then(function(r){ return r.json(); }).then(function(d) {
    var events = d.hronologija || d.dogadjaji || (Array.isArray(d) ? d : []);
    if (!Array.isArray(events) || !events.length) {
      container.innerHTML = '<div style="color:rgba(255,255,255,.25);font-size:.8rem;text-align:center;padding:1.5rem 0;">Hronologija je prazna.<br><span style="font-size:.72rem;">Uploadujte dokument da biste automatski generisali hronologiju.</span></div>';
      return;
    }
    var html = '<div class="timeline-wrap">';
    events.forEach(function(ev) {
      var vaznost = ev.vaznost || 'informativan';
      html += '<div class="timeline-item">'
        + '<div class="timeline-dot ' + vaznost + '"></div>'
        + '<div class="timeline-card">'
        + (ev.datum ? '<div class="timeline-date">' + ev.datum + '</div>' : '')
        + '<div class="timeline-event">' + escHtml(ev.dogadjaj || '') + '</div>'
        + (ev.akter ? '<div class="timeline-akter">— ' + escHtml(ev.akter) + '</div>' : '')
        + (ev.dokument_naziv ? '<div class="timeline-akter">📎 ' + escHtml(ev.dokument_naziv) + '</div>' : '')
        + '</div></div>';
    });
    html += '</div>';
    html += '<div style="margin-top:.6rem;display:flex;gap:.5rem;font-size:.65rem;color:rgba(255,255,255,.3);">'
      + '<span style="display:flex;align-items:center;gap:.3rem;"><span style="width:8px;height:8px;border-radius:50%;background:#ff6060;display:inline-block;"></span>Kritičan</span>'
      + '<span style="display:flex;align-items:center;gap:.3rem;"><span style="width:8px;height:8px;border-radius:50%;background:#ffaa40;display:inline-block;"></span>Važan</span>'
      + '<span style="display:flex;align-items:center;gap:.3rem;"><span style="width:8px;height:8px;border-radius:50%;background:#4aa8ff;display:inline-block;"></span>Informativan</span>'
      + '</div>';
    container.innerHTML = html;
  }).catch(function(e) {
    container.innerHTML = '<div style="color:#ff9090;font-size:.8rem;">Greška: ' + e.message + '</div>';
  });
}

// ═══════════════════════════════════════════════════════════════
// EVIDENCE VAULT
// ═══════════════════════════════════════════════════════════════
var _TIP_DOKAZA_LABELS = {
  'sudska_odluka': 'Sudska odluka', 'podnesak': 'Podnesak', 'ugovor': 'Ugovor',
  'dopis': 'Dopis', 'medicinska_dokumentacija': 'Med. dokumentacija',
  'finansijska_dokumentacija': 'Fin. dokumentacija', 'javna_isprava': 'Javna isprava',
  'vestacki_nalaz': 'Veštački nalaz', 'ostalo': 'Ostalo'
};

function evidence_load() {
  if (!activePredmetId || !currentSession) return;
  var dokDiv = document.getElementById('evidence-dokumenti');
  var matDiv = document.getElementById('evidence-matrica');
  var statDiv = document.getElementById('evidence-stat');
  if (!dokDiv) return;
  dokDiv.innerHTML = '<div style="color:rgba(255,255,255,.3);font-size:.8rem;">Učitavam...</div>';

  fetch('/api/evidence/predmeti/' + activePredmetId, {
    headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
  }).then(function(r){ return r.json(); }).then(function(d) {
    // Stat
    statDiv.innerHTML = ''
      + '<div style="background:rgba(74,168,255,.07);border:1px solid rgba(74,168,255,.15);border-radius:7px;padding:.45rem .6rem;text-align:center;">'
      + '<div style="font-size:1.1rem;font-weight:700;color:#89c8ff;">' + (d.ukupno_dok||0) + '</div>'
      + '<div style="font-size:.62rem;color:rgba(255,255,255,.35);">Dokumenata</div></div>'
      + '<div style="background:rgba(74,255,120,.06);border:1px solid rgba(74,255,120,.15);border-radius:7px;padding:.45rem .6rem;text-align:center;">'
      + '<div style="font-size:1.1rem;font-weight:700;color:#7de0a0;">' + (d.klasifikovano||0) + '</div>'
      + '<div style="font-size:.62rem;color:rgba(255,255,255,.35);">Klasifikovano</div></div>'
      + '<div style="background:rgba(255,200,60,.06);border:1px solid rgba(255,200,60,.15);border-radius:7px;padding:.45rem .6rem;text-align:center;">'
      + '<div style="font-size:1.1rem;font-weight:700;color:#ffcc50;">' + ((d.dokazi||[]).length) + '</div>'
      + '<div style="font-size:.62rem;color:rgba(255,255,255,.35);">Dokaza</div></div>';

    // Dokumenti
    var docs = d.dokumenti || [];
    if (!docs.length) {
      dokDiv.innerHTML = '<div style="color:rgba(255,255,255,.25);font-size:.78rem;">Nema uploadovanih dokumenata.</div>';
    } else {
      dokDiv.innerHTML = docs.map(function(doc) {
        var tip = doc.tip_dokaza || 'neklafikovan';
        var tipLabel = _TIP_DOKAZA_LABELS[tip] || tip;
        var elementi = (doc.pravni_elementi || []).slice(0,3).join(', ');
        return '<div class="evidence-dok-card">'
          + '<span class="evidence-tip-badge evidence-tip-' + tip + '">' + tipLabel + '</span>'
          + '<div style="flex:1;min-width:0;">'
          + '<div style="font-size:.78rem;color:rgba(255,255,255,.8);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + escHtml(doc.naziv_fajla||'') + '</div>'
          + (elementi ? '<div style="font-size:.67rem;color:rgba(255,255,255,.35);margin-top:.15rem;">' + escHtml(elementi) + '</div>' : '')
          + '</div>'
          + (tip === 'neklafikovan' ? '<button onclick="evidence_reklasifikuj(\'' + doc.id + '\')" style="font-size:.62rem;padding:.15rem .4rem;border:1px solid rgba(255,255,255,.15);border-radius:4px;background:transparent;color:rgba(255,255,255,.35);cursor:pointer;white-space:nowrap;">Klasifikuj</button>' : '')
          + '</div>';
      }).join('');
    }

    // Matrica dokaza
    var dokazi = d.dokazi || [];
    if (!dokazi.length) {
      matDiv.innerHTML = '<div style="color:rgba(255,255,255,.2);font-size:.75rem;padding:.4rem 0;">Nema evidentiranih dokaza. Dodajte manuelno ili uploadujte dokument za automatsku ekstrakciju.</div>';
    } else {
      matDiv.innerHTML = dokazi.map(function(dz) {
        return '<div class="dokaz-row">'
          + '<div class="dokaz-snaga-' + (dz.snaga||'srednja') + '"></div>'
          + '<div style="flex:1;">'
          + '<div style="font-size:.78rem;color:rgba(255,255,255,.8);">' + escHtml(dz.tvrdnja||'') + '</div>'
          + (dz.pravni_element ? '<div style="font-size:.65rem;color:rgba(74,168,255,.6);margin-top:.1rem;">' + escHtml(dz.pravni_element) + '</div>' : '')
          + '</div>'
          + '<button onclick="evidence_deleteDokaz(\'' + dz.id + '\')" style="font-size:.62rem;color:rgba(255,255,255,.2);background:transparent;border:none;cursor:pointer;padding:.1rem .3rem;">✕</button>'
          + '</div>';
      }).join('');
    }
  }).catch(function(e) {
    if (dokDiv) dokDiv.innerHTML = '<div style="color:#ff9090;font-size:.8rem;">Greška: ' + e.message + '</div>';
  });
}

function evidence_reklasifikuj(dokId) {
  if (!activePredmetId || !currentSession) return;
  fetch('/api/evidence/predmeti/' + activePredmetId + '/reklasifikuj/' + dokId, {
    method: 'POST',
    headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
  }).then(function(){ showToast('Klasifikacija pokrenuta...'); setTimeout(evidence_load, 3000); });
}

function evidence_addDokaz() {
  var tvrdnja = prompt('Unesite dokaznu stavku (tvrdnju, činjenicu, dokaz):');
  if (!tvrdnja || !activePredmetId || !currentSession) return;
  fetch('/api/evidence/predmeti/' + activePredmetId + '/dokaz', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + currentSession.access_token },
    body: JSON.stringify({ tvrdnja: tvrdnja })
  }).then(function(r){ return r.json(); }).then(function(){ evidence_load(); showToast('Dokaz dodat ✓'); });
}

function evidence_deleteDokaz(dokazId) {
  if (!activePredmetId || !currentSession) return;
  fetch('/api/evidence/predmeti/' + activePredmetId + '/dokaz/' + dokazId, {
    method: 'DELETE',
    headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
  }).then(function(){ evidence_load(); });
}

// ═══════════════════════════════════════════════════════════════
// LAW FIRM BRAIN
// ═══════════════════════════════════════════════════════════════
function brain_load() {
  if (!activePredmetId || !currentSession) return;
  var rez = document.getElementById('brain-rezultat');
  var lod = document.getElementById('brain-loading');
  var btn = document.getElementById('brain-load-btn');
  if (!rez) return;
  rez.style.display = 'none';
  lod.style.display = 'block';
  if (btn) btn.disabled = true;

  fetch('/api/precedenti/predmeti/' + activePredmetId, {
    headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
  }).then(function(r){ return r.json(); }).then(function(d) {
    lod.style.display = 'none';
    if (btn) btn.disabled = false;
    var tekst = d.analiza || 'Nema podataka.';
    if (d.ukupno_slicnih > 0) {
      tekst += '\n\n📁 Pronađeno ' + d.ukupno_slicnih + ' sličnih predmeta tipa "' + (d.tip||'') + '" u kancelariji.';
    }
    rez.textContent = tekst;
    rez.style.display = 'block';
  }).catch(function(e) {
    lod.style.display = 'none';
    if (btn) btn.disabled = false;
    rez.textContent = 'Greška: ' + e.message;
    rez.style.display = 'block';
  });
}

// Hronologija i Trezor dokaza se lazy-loaduju direktno iz pred_subtabSwitch.

// ═══════════════════════════════════════════════════════════════
// MATTER INTELLIGENCE BAR
// ═══════════════════════════════════════════════════════════════
function matter_intel_load() {
  if (!activePredmetId || !currentSession) return;
  var bar = document.getElementById('matter-intel-bar');
  if (!bar) return;

  fetch('/api/matter-intel/predmeti/' + activePredmetId, {
    headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
  }).then(function(r){ return r.json(); }).then(function(d) {
    bar.style.display = 'block';
    var rizikColor = d.rizik_boja === 'green' ? '#4ade80' : d.rizik_boja === 'red' ? '#f87171' : '#fbbf24';
    var snagaColor = d.snaga_dokaza === 'Jaka' ? '#4ade80' : d.snaga_dokaza === 'Slaba' ? '#f87171' : '#fbbf24';

    document.getElementById('mi-snaga').textContent    = d.snaga_dokaza || '—';
    document.getElementById('mi-snaga').style.color    = snagaColor;
    document.getElementById('mi-rizik').textContent    = d.procesni_rizik || '—';
    document.getElementById('mi-rizik').style.color    = rizikColor;
    document.getElementById('mi-nedostaje').textContent = (d.nedostajuci_count || 0) + ' tip(a)';
    document.getElementById('mi-rokovi').textContent   = (d.predstojeći_rokovi || 0) + ' / 30d';
    var healthEl = document.getElementById('mi-health');
    if (healthEl) { healthEl.textContent = (d.health_score || 0) + '%'; }
    var trendEl = document.getElementById('mi-trend');
    if (trendEl && d.trend) {
      var tMap = { raste: { icon: '↑', color: '#4ade80' }, stagnira: { icon: '→', color: '#fbbf24' }, opada: { icon: '↓', color: '#f87171' } };
      var tm = tMap[d.trend] || null;
      if (tm) { trendEl.textContent = tm.icon; trendEl.style.color = tm.color; trendEl.style.display = 'inline'; }
      else trendEl.style.display = 'none';
    } else if (trendEl) { trendEl.style.display = 'none'; }

    var sl = document.getElementById('mi-sledeca');
    if (d.sledeca_radnja && sl) {
      sl.style.display = 'block';
      sl.innerHTML = '💡 <b>Preporučena radnja:</b> ' + _htmlEsc(d.sledeca_radnja.replace('SLEDEĆA RADNJA: ','').split('\n')[0]);
    }
  }).catch(function(e){ console.warn('[MI] load greška:', e); });
}

// ═══════════════════════════════════════════════════════════════
// CASE COMMAND CENTER
// ═══════════════════════════════════════════════════════════════
function ccc_load() {
  if (!activePredmetId || !currentSession) return;
  var container = document.getElementById('ccc-container');
  if (!container) return;
  container.innerHTML = '<div style="text-align:center;padding:2rem;color:rgba(74,168,255,.5);">⏳ Učitavam komandni centar...</div>';

  fetch('/api/ccc/predmeti/' + activePredmetId, {
    headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
  }).then(function(r){ return r.json(); }).then(function(d) {
    _ccc_render(container, d);
  }).catch(function(e){
    container.innerHTML = '<div style="padding:1rem;color:#f87171;">Greška: ' + e.message + '</div>';
  });
}

function _ccc_render(el, d) {
  var p   = d.predmet    || {};
  var dok = d.dok_stats  || {};
  var bil = d.billing    || {};
  var hs  = d.health_score || 0;
  var hsColor = hs >= 70 ? '#4ade80' : hs >= 45 ? '#fbbf24' : '#f87171';

  var _TL = { parnicno:'Parnica', krivicno:'Krivično', radno:'Radno pravo',
    upravno:'Upravni postupak', porodicno:'Porodično', nasledjivanje:'Nasleđivanje',
    privredno:'Privredno', nepokretnosti:'Nepokretnosti', ostalo:'Ostalo' };
  var tipStr = _TL[p.tip] || p.tip || '';

  var klijentiStr = (d.klijenti || []).map(function(k){ return k.ime; }).join(', ') || '';

  // ── SMART ACTION CHIPS ──────────────────────────────────────────────────
  var chips = [];
  // 1. Kritičan rok (≤7 dana) — CRVENA
  var kr = d.kritican_rok;
  if (kr) {
    var dana = kr.dana_ostalo;
    var tag  = dana === 0 ? 'DANAS' : dana + 'd';
    chips.push({ cls:'chip-red', icon:'🔴', text: tag+' — '+(_htmlEsc((kr.naziv||'Rok').slice(0,30))), action:"pred_subtabSwitch('rokovi')" });
  }
  // 2. Predmeti bez dokumenta — CRVENA
  if ((dok.ukupno||0) === 0) {
    chips.push({ cls:'chip-red', icon:'📤', text:'Uploaduj prvi dokument', action:"pred_subtabSwitch('dokumenti')" });
  }
  // 3. Nedostajući dokaz — ŽUTA
  var nedo = (d.nedostajuci || []);
  if (nedo.length > 0) {
    var _DL = { sudska_odluka:'sudsku odluku', podnesak:'podnesak', ugovor:'ugovor',
      dopis:'pisanu komunikaciju', medicinska_dokumentacija:'medicinski nalaz',
      finansijska_dokumentacija:'fin. dokumentaciju', javna_isprava:'javnu ispravu',
      vestacki_nalaz:'nalaz veštaka' };
    chips.push({ cls:'chip-yellow', icon:'📄', text:'Pribavi '+(_DL[nedo[0]]||nedo[0]), action:"pred_subtabSwitch('dokazi')" });
  }
  // 4. Nenaplaćeni iznos — ŽUTA
  if ((bil.nenaplaceno||0) > 0) {
    chips.push({ cls:'chip-yellow', icon:'💰', text: Math.round(bil.nenaplaceno/1000)+'k RSD nenaplaćeno', action:"pred_subtabSwitch('naplata')" });
  }
  // 5. Preporučena AI analiza — PLAVA (uvek)
  chips.push({ cls:'chip-blue', icon:'🧠', text:'Pokreni AI analizu', action:"pred_subtabSwitch('ai-analiza')" });
  // 6. Ako nema rokova — PLAVA
  if (!kr && (d.predstojeći||0) === 0 && (d.rokovi||[]).length === 0) {
    chips.push({ cls:'chip-blue', icon:'⏰', text:'Evidentiraj rokove', action:"pred_subtabSwitch('rokovi')" });
  }
  // Ograniči na 4 chipa
  chips = chips.slice(0, 4);

  var chips_html = '';
  chips.forEach(function(c) {
    chips_html += '<button class="smart-chip '+c.cls+'" onclick="'+c.action+'">'+c.icon+' '+c.text+'</button>';
  });

  // ── ROKOVI ──────────────────────────────────────────────────────────────
  var rokovi_html = '';
  (d.rokovi || []).slice(0,5).forEach(function(r) {
    var dana = r.dana_ostalo;
    var boja = dana === null ? '#aaa' : dana < 0 ? '#f87171' : dana <= 7 ? '#f87171' : dana <= 14 ? '#fbbf24' : '#4ade80';
    var tag  = dana === null ? '?' : dana < 0 ? 'Istekao' : dana === 0 ? 'Danas' : dana + 'd';
    rokovi_html += '<div class="ccc-rok-item"><span style="color:'+boja+';font-weight:700;min-width:44px;font-size:.78rem;">'+tag+'</span><span style="flex:1;font-size:.78rem;">'+_htmlEsc((r.naziv||'Rok').slice(0,34))+'</span></div>';
  });
  if (!rokovi_html) rokovi_html = '<div style="color:rgba(255,255,255,.22);font-size:.78rem;padding:.5rem 0;">Nema evidentiranih rokova.<br><span style="font-size:.7rem;opacity:.7;">Dodajte rokove u tabu ⏰ Rokovi.</span></div>';

  // ── AKTIVNOSTI ───────────────────────────────────────────────────────────
  var akt_html = '';
  (d.aktivnosti || []).slice(0,5).forEach(function(a) {
    akt_html += '<div class="ccc-act-item"><span style="opacity:.4;flex-shrink:0;font-size:.72rem;">'+(a.datum||'').slice(5,10)+'</span><span style="flex:1;font-size:.78rem;">'+_htmlEsc((a.dogadjaj||'').slice(0,65))+'</span></div>';
  });
  if (!akt_html) akt_html = '<div style="color:rgba(255,255,255,.22);font-size:.78rem;padding:.5rem 0;">Nema zabeleženih aktivnosti.</div>';

  el.innerHTML = [
    // ── HEADER ─────────────────────────────────────────────────────────────
    '<div style="display:flex;align-items:center;gap:.8rem;margin-bottom:.75rem;padding:.75rem 1rem;',
      'background:linear-gradient(135deg,rgba(74,168,255,.07),rgba(167,139,250,.04));',
      'border:1px solid rgba(74,168,255,.18);border-radius:12px;">',
      '<div style="flex:1;min-width:0;">',
        '<div style="font-size:1rem;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'+_htmlEsc(p.naziv||'Predmet')+'</div>',
        '<div style="display:flex;gap:.6rem;margin-top:.25rem;flex-wrap:wrap;">',
          tipStr ? '<span style="font-size:.7rem;padding:.1rem .5rem;background:rgba(74,168,255,.12);border-radius:10px;color:#89c8ff;">'+_htmlEsc(tipStr)+'</span>' : '',
          p.status ? '<span style="font-size:.7rem;padding:.1rem .5rem;background:rgba(255,255,255,.06);border-radius:10px;color:rgba(255,255,255,.55);">'+_htmlEsc(p.status)+'</span>' : '',
          klijentiStr ? '<span style="font-size:.7rem;color:rgba(255,255,255,.4);">👤 '+_htmlEsc(klijentiStr.slice(0,30))+'</span>' : '',
        '</div>',
      '</div>',
      '<div style="text-align:center;flex-shrink:0;padding:.4rem .7rem;background:rgba(255,255,255,.04);border-radius:8px;min-width:60px;">',
        '<div style="font-size:1.5rem;font-weight:800;line-height:1;color:'+hsColor+';">'+hs+'</div>',
        '<div style="font-size:.58rem;color:rgba(255,255,255,.3);margin-top:.15rem;">Health</div>',
      '</div>',
    '</div>',

    // ── SMART ACTION CHIPS ─────────────────────────────────────────────────
    '<div class="smart-chips-wrap">',
      '<div class="smart-chips-title">💡 Šta trebate uraditi</div>',
      '<div class="smart-chips-row">',
        chips_html,
      '</div>',
    '</div>',

    // ── DOKAZI + FINANSIJE ─────────────────────────────────────────────────
    '<div class="ccc-grid" style="margin-bottom:.65rem;">',
      '<div class="ccc-block">',
        '<div class="ccc-block-hd">🔒 Dokazi</div>',
        '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:.4rem;margin-bottom:.5rem;">',
          '<div class="ccc-metric"><div class="ccc-metric-val" style="color:#4ade80;">'+(dok.jaka||0)+'</div><div class="ccc-metric-lbl">Jaki</div></div>',
          '<div class="ccc-metric"><div class="ccc-metric-val" style="color:#fbbf24;">'+(dok.srednja||0)+'</div><div class="ccc-metric-lbl">Srednji</div></div>',
          '<div class="ccc-metric"><div class="ccc-metric-val" style="color:#f87171;">'+(dok.slaba||0)+'</div><div class="ccc-metric-lbl">Slabi</div></div>',
        '</div>',
        '<div class="health-bar-wrap"><div class="health-bar-fill" style="width:'+
          Math.min(100, dok.ukupno ? Math.round(dok.jaka/dok.ukupno*100) : 0)+
          '%;background:linear-gradient(90deg,#4ade80,#22c55e);"></div></div>',
        '<button onclick="pred_subtabSwitch(\'dokazi\')" style="margin-top:.5rem;width:100%;font-size:.7rem;background:none;border:1px solid rgba(255,255,255,.08);border-radius:6px;color:rgba(255,255,255,.35);padding:.25rem;cursor:pointer;">Otvori trezor dokaza →</button>',
      '</div>',
      '<div class="ccc-block">',
        '<div class="ccc-block-hd">💰 Finansije (RSD)</div>',
        '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:.4rem;margin-bottom:.5rem;">',
          '<div class="ccc-metric"><div class="ccc-metric-val" style="color:#89c8ff;font-size:1rem;">'+(Math.round((bil.uneseno||0)/1000)||0)+'k</div><div class="ccc-metric-lbl">Uneseno</div></div>',
          '<div class="ccc-metric"><div class="ccc-metric-val" style="color:#fbbf24;font-size:1rem;">'+(Math.round((bil.nenaplaceno||0)/1000)||0)+'k</div><div class="ccc-metric-lbl">Neplaćeno</div></div>',
          '<div class="ccc-metric"><div class="ccc-metric-val" style="color:#4ade80;font-size:1rem;">'+(Math.round((bil.naplaceno||0)/1000)||0)+'k</div><div class="ccc-metric-lbl">Naplaćeno</div></div>',
        '</div>',
        '<div class="health-bar-wrap"><div class="health-bar-fill" style="width:'+
          (bil.uneseno ? Math.min(100,Math.round(bil.naplaceno/bil.uneseno*100)) : 0)+
          '%;background:linear-gradient(90deg,#4ade80,#16a34a);"></div></div>',
        '<button onclick="pred_subtabSwitch(\'naplata\')" style="margin-top:.5rem;width:100%;font-size:.7rem;background:none;border:1px solid rgba(255,255,255,.08);border-radius:6px;color:rgba(255,255,255,.35);padding:.25rem;cursor:pointer;">Otvori Naplatu →</button>',
      '</div>',
    '</div>',

    // ── ROKOVI + AKTIVNOSTI ────────────────────────────────────────────────
    '<div class="ccc-grid" style="margin-bottom:.65rem;">',
      '<div class="ccc-block">',
        '<div class="ccc-block-hd">⏰ Predstojeći rokovi</div>',
        rokovi_html,
        '<button onclick="pred_subtabSwitch(\'rokovi\')" style="margin-top:.5rem;width:100%;font-size:.7rem;background:none;border:1px solid rgba(255,255,255,.08);border-radius:6px;color:rgba(255,255,255,.35);padding:.25rem;cursor:pointer;">Svi rokovi →</button>',
      '</div>',
      '<div class="ccc-block">',
        '<div class="ccc-block-hd">📋 Aktivnosti</div>',
        akt_html,
        '<button onclick="pred_subtabSwitch(\'timeline\')" style="margin-top:.5rem;width:100%;font-size:.7rem;background:none;border:1px solid rgba(255,255,255,.08);border-radius:6px;color:rgba(255,255,255,.35);padding:.25rem;cursor:pointer;">Puna hronologija →</button>',
      '</div>',
    '</div>',

    // ── BRZE AKCIJE ───────────────────────────────────────────────────────
    '<div style="display:flex;flex-wrap:wrap;gap:.4rem;">',
      '<button onclick="pred_subtabSwitch(\'ai-analiza\')" class="smart-chip chip-blue">🧠 AI Analiza</button>',
      '<button onclick="pred_subtabSwitch(\'strategija\')" class="smart-chip" style="background:rgba(167,139,250,.1);border-color:rgba(167,139,250,.3);color:#a78bfa;">⚔️ Strategija</button>',
      '<button onclick="pred_subtabSwitch(\'agenti\')" class="smart-chip" style="background:rgba(99,102,241,.1);border-color:rgba(99,102,241,.3);color:#818cf8;">🤖 AI Pomoćnici</button>',
      '<button onclick="pred_subtabSwitch(\'dokumenti\')" class="smart-chip" style="background:rgba(255,255,255,.05);border-color:rgba(255,255,255,.12);color:rgba(255,255,255,.55);">📁 Dokumenti</button>',
      '<button onclick="if(typeof billing_timerToggle===\'function\'){if(!_billingPredmetId)_billingPredmetId=activePredmetId;billing_timerToggle();}" class="smart-chip" style="background:rgba(240,192,64,.1);border-color:rgba(240,192,64,.3);color:#f0c040;">⏱ Tajmer</button>',
      '<button onclick="pred_subtabSwitch(\'graf\')" class="smart-chip" style="background:rgba(103,232,249,.08);border-color:rgba(103,232,249,.2);color:#67e8f9;">🕸 Mapa veza</button>',
    '</div>',
  ].join('');
}

// ═══════════════════════════════════════════════════════════════
// OUTCOME INTELLIGENCE
// ═══════════════════════════════════════════════════════════════
function outcome_intel_panel_show() {
  var panel = document.getElementById('outcome-intel-panel');
  if (!panel) return;
  panel.style.display = 'block';
  var loading = document.getElementById('outcome-intel-loading');
  var result  = document.getElementById('outcome-intel-result');
  var stats   = document.getElementById('outcome-intel-stats');
  if (loading) loading.style.display = 'block';
  if (result)  result.style.display  = 'none';
  if (stats)   stats.style.display   = 'none';

  if (!activePredmetId || !currentSession) {
    if (loading) loading.textContent = 'Otvorite predmet da biste videli analizu.';
    return;
  }

  fetch('/api/outcome-intel/predmeti/' + activePredmetId, {
    headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
  }).then(function(r){ return r.json(); }).then(function(d) {
    if (loading) loading.style.display = 'none';
    if (result) {
      result.style.display = 'block';
      result.textContent = d.analiza || 'Nema podataka.';
    }
    if (stats && d.ukupno_predmeta) {
      var shtml = '';
      shtml += '<div style="padding:.35rem .7rem;background:rgba(255,255,255,.04);border-radius:6px;font-size:.72rem;text-align:center;"><div style="font-size:1.1rem;font-weight:700;color:#89c8ff;">'+d.ukupno_predmeta+'</div><div style="color:rgba(255,255,255,.4);">Ukupno predmeta</div></div>';
      shtml += '<div style="padding:.35rem .7rem;background:rgba(255,255,255,.04);border-radius:6px;font-size:.72rem;text-align:center;"><div style="font-size:1.1rem;font-weight:700;color:#4ade80;">'+d.zatvoreni+'</div><div style="color:rgba(255,255,255,.4);">Zatvorenih</div></div>';
      if (d.avg_vrednost) {
        shtml += '<div style="padding:.35rem .7rem;background:rgba(255,255,255,.04);border-radius:6px;font-size:.72rem;text-align:center;"><div style="font-size:1.1rem;font-weight:700;color:#f0c040;">'+Math.round(d.avg_vrednost/1000)+'k</div><div style="color:rgba(255,255,255,.4);">Prosečna vrednost</div></div>';
      }
      stats.innerHTML = shtml;
      stats.style.display = 'flex';
      stats.style.gap = '.5rem';
    }
  }).catch(function(e) {
    if (loading) loading.textContent = 'Greška: ' + e.message;
  });
}

// ═══════════════════════════════════════════════════════════════
// CONFLICT CHECK — ažuriran da zove novi endpoint
// ═══════════════════════════════════════════════════════════════
async function crmPokreniKonfliktNovi() {
  var ime_prez = ((document.getElementById('cf-ime')||{}).value||'').trim() + ' ' +
                 ((document.getElementById('cf-prezime')||{}).value||'').trim();
  ime_prez = ime_prez.trim();
  var firma = ((document.getElementById('cf-firma')||{}).value||'').trim();
  if (!ime_prez && !firma) { showToast('Unesite ime ili naziv firme za proveru', 'warn'); return; }
  var rez = document.getElementById('cf-rezultat');
  if (rez) rez.innerHTML = '<div style="color:rgba(255,255,255,.4);font-size:.82rem;">⏳ Proveravam...</div>';
  try {
    var r = await fetch('/api/conflict-check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + currentSession.access_token },
      body: JSON.stringify({ ime_prezime: ime_prez || null, firma: firma || null }),
    });
    var d = await r.json();
    var html = '';
    if (d.status === 'clear') {
      html = '<div class="cc-clear">✅ <b>Nema konflikta</b><br><span style="font-size:.8rem;">'+_htmlEsc(d.poruka)+'</span></div>';
    } else if (d.status === 'conflict') {
      html = '<div class="cc-modal" style="background:rgba(248,113,113,.06);border-color:rgba(248,113,113,.3);border-radius:8px;padding:.8rem;margin-bottom:.5rem;">⛔ <b style="color:#f87171;">KONFLIKT INTERESA!</b><br><span style="font-size:.8rem;color:rgba(255,255,255,.6);">'+_htmlEsc(d.poruka)+'</span></div>';
    } else {
      html = '<div class="cc-review">⚠️ <b>Preporučena provera</b><br><span style="font-size:.8rem;">'+_htmlEsc(d.poruka)+'</span></div>';
    }
    if (d.konflikti && d.konflikti.length) {
      html += '<div style="margin-top:.6rem;font-size:.72rem;color:rgba(255,255,255,.4);text-transform:uppercase;letter-spacing:.08em;margin-bottom:.3rem;">Pronađeni predmeti:</div>';
      d.konflikti.forEach(function(k) {
        var boja = k.tip_konflikta === 'tuzilac' || k.tip_konflikta === 'tuzeni' ? '#f87171' : '#fbbf24';
        html += '<div class="cc-conflict-item"><div style="font-size:.78rem;font-weight:600;color:'+boja+';">'+_htmlEsc(k.predmet_naziv||'')+'</div>';
        html += '<div style="font-size:.72rem;color:rgba(255,255,255,.45);">'+_htmlEsc(k.opis||'')+'</div>';
        html += '<div style="font-size:.68rem;color:rgba(255,255,255,.3);margin-top:.2rem;">Status: '+_htmlEsc(k.predmet_status||'')+'</div></div>';
      });
    }
    if (rez) rez.innerHTML = html;
  } catch(e) {
    if (rez) rez.innerHTML = '<div style="color:#f87171;font-size:.82rem;">Greška: ' + _htmlEsc(e.message) + '</div>';
  }
}

// Override stare funkcije sa novom
window.crmPokreniKonflikt = crmPokreniKonfliktNovi;

// ═══════════════════════════════════════════════════════════════
// MULTI-AGENT CENTAR
// ═══════════════════════════════════════════════════════════════
var _selectedAgent = null;

function agent_select(agentId, cardEl) {
  _selectedAgent = agentId;
  document.querySelectorAll('.agent-card').forEach(function(c){ c.classList.remove('active'); });
  if (cardEl) cardEl.classList.add('active');
  var badge = document.getElementById('agent-selected-badge');
  var icons = {'intake':'📥','research':'🔍','drafting':'✍️','litigation':'⚔️','billing':'💰','deadline':'⏰'};
  var names = {'intake':'Intake Agent','research':'Research Agent','drafting':'Drafting Agent','litigation':'Litigation Agent','billing':'Billing Agent','deadline':'Deadline Agent'};
  if (badge) {
    badge.style.display = 'block';
    badge.textContent   = (icons[agentId]||'🤖') + ' ' + (names[agentId]||agentId) + ' — aktivan';
  }
}

async function agent_run() {
  var task = (document.getElementById('agent-task-input')||{}).value || '';
  task = task.trim();
  if (!task) { showToast('Unesite zadatak za agenta', 'warn'); return; }
  if (!currentSession) { showToast('Prijavite se', 'warn'); return; }

  var loading = document.getElementById('agent-loading');
  var wrap    = document.getElementById('agent-result-wrap');
  var result  = document.getElementById('agent-result');
  var badge   = document.getElementById('agent-result-badge');
  if (loading) loading.style.display = 'block';
  if (wrap)    wrap.style.display    = 'none';

  try {
    var body = { task: task };
    if (_selectedAgent)  body.agent      = _selectedAgent;
    if (activePredmetId) body.predmet_id = activePredmetId;

    var r = await fetch('/api/agents/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + currentSession.access_token },
      body: JSON.stringify(body),
    });
    var d = await r.json();
    if (!r.ok) { showToast(d.detail || 'Greška', 'err'); return; }

    if (loading) loading.style.display = 'none';
    if (badge)   badge.textContent = (d.ikona||'🤖') + ' ' + (d.naziv||d.agent) + ' odgovorio:';
    if (result)  result.textContent = d.odgovor || '—';
    if (wrap)    wrap.style.display = 'block';
  } catch(e) {
    if (loading) loading.style.display = 'none';
    showToast('Greška: ' + e.message, 'err');
  }
}

// ─── Knowledge Graph ──────────────────────────────────────────────────────────
var _kg_loaded = false;

function kg_load() {
  if (!activePredmetId || !currentSession) return;
  _kg_loaded = true;

  var container = document.getElementById('kg-container');
  var tooltip   = document.getElementById('kg-tooltip');
  if (!container) return;

  container.innerHTML = '<div style="padding:2rem;text-align:center;color:#89c8ff;opacity:.6;">Učitavam graf...</div>';

  fetch('/api/knowledge-graph/predmeti/' + activePredmetId, {
    headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
  })
  .then(function(r){ return r.json(); })
  .then(function(data){ _kg_render(container, tooltip, data); })
  .catch(function(e){
    container.innerHTML = '<div style="padding:2rem;text-align:center;color:#f87171;">Greška pri učitavanju grafa: ' + e.message + '</div>';
  });
}

function _kg_render(container, tooltip, data) {
  var nodes = data.nodes || [];
  var edges = data.edges || [];

  if (!nodes.length) {
    container.innerHTML = '<div style="padding:2rem;text-align:center;color:#aaa;">Nema podataka za prikaz.</div>';
    return;
  }

  var W = container.offsetWidth  || 700;
  var H = container.offsetHeight || 420;

  // Assign initial positions in a circle
  var cx = W / 2, cy = H / 2;
  var R  = Math.min(W, H) * 0.35;
  nodes.forEach(function(n, i) {
    if (n.id.startsWith('predmet_')) { n.x = cx; n.y = cy; }
    else {
      var angle = (2 * Math.PI * i) / nodes.length;
      n.x = cx + R * Math.cos(angle) + (Math.random() - 0.5) * 40;
      n.y = cy + R * Math.sin(angle) + (Math.random() - 0.5) * 40;
    }
    n.vx = 0; n.vy = 0;
  });

  // Build index for fast lookup
  var nodeById = {};
  nodes.forEach(function(n){ nodeById[n.id] = n; });

  // Resolve edge references to node objects
  var validEdges = edges.filter(function(e){
    return nodeById[e.from] && nodeById[e.to] && e.from !== e.to;
  });

  // ─── Force simulation (simple, no D3 dependency) ─────────────────────────
  var ITER = 120;
  var K    = 60; // spring rest length
  for (var it = 0; it < ITER; it++) {
    // Repulsion between all pairs
    for (var a = 0; a < nodes.length; a++) {
      for (var b = a + 1; b < nodes.length; b++) {
        var na = nodes[a], nb = nodes[b];
        var dx = nb.x - na.x, dy = nb.y - na.y;
        var dist = Math.sqrt(dx*dx + dy*dy) || 1;
        var force = 2200 / (dist * dist);
        var fx = force * dx / dist, fy = force * dy / dist;
        na.vx -= fx; na.vy -= fy;
        nb.vx += fx; nb.vy += fy;
      }
    }
    // Spring attraction along edges
    validEdges.forEach(function(e) {
      var na = nodeById[e.from], nb = nodeById[e.to];
      var dx = nb.x - na.x, dy = nb.y - na.y;
      var dist = Math.sqrt(dx*dx + dy*dy) || 1;
      var strength = e.strength === 'strong' ? 0.08 : 0.04;
      var fx = (dx - K * dx / dist) * strength;
      var fy = (dy - K * dy / dist) * strength;
      na.vx += fx; na.vy += fy;
      nb.vx -= fx; nb.vy -= fy;
    });
    // Gravity toward center
    nodes.forEach(function(n) {
      n.vx += (cx - n.x) * 0.012;
      n.vy += (cy - n.y) * 0.012;
    });
    // Apply velocity with damping
    var damping = 0.82;
    nodes.forEach(function(n) {
      n.vx *= damping; n.vy *= damping;
      n.x  += n.vx;   n.y  += n.vy;
      // Clamp to bounds
      var pad = (n.radius || 12) + 4;
      n.x = Math.max(pad, Math.min(W - pad, n.x));
      n.y = Math.max(pad, Math.min(H - pad, n.y));
    });
  }

  // ─── Build SVG ────────────────────────────────────────────────────────────
  var svgNS = 'http://www.w3.org/2000/svg';
  var svg   = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('width',  W);
  svg.setAttribute('height', H);
  svg.style.cssText = 'position:absolute;top:0;left:0;';

  // Defs: arrowhead marker
  var defs   = document.createElementNS(svgNS, 'defs');
  var marker = document.createElementNS(svgNS, 'marker');
  marker.setAttribute('id', 'kg-arrow');
  marker.setAttribute('markerWidth',  '6');
  marker.setAttribute('markerHeight', '6');
  marker.setAttribute('refX', '6');
  marker.setAttribute('refY', '3');
  marker.setAttribute('orient', 'auto');
  var poly = document.createElementNS(svgNS, 'polygon');
  poly.setAttribute('points', '0 0, 6 3, 0 6');
  poly.setAttribute('fill', 'rgba(255,255,255,.25)');
  marker.appendChild(poly);
  defs.appendChild(marker);
  svg.appendChild(defs);

  // Draw edges
  validEdges.forEach(function(e) {
    var na = nodeById[e.from], nb = nodeById[e.to];
    // Shorten line to edge of circle
    var dx = nb.x - na.x, dy = nb.y - na.y;
    var dist = Math.sqrt(dx*dx + dy*dy) || 1;
    var ra = na.radius || 12, rb = nb.radius || 12;
    var x1 = na.x + dx/dist * ra;
    var y1 = na.y + dy/dist * ra;
    var x2 = nb.x - dx/dist * (rb + 6);
    var y2 = nb.y - dy/dist * (rb + 6);

    var line = document.createElementNS(svgNS, 'line');
    line.setAttribute('x1', x1); line.setAttribute('y1', y1);
    line.setAttribute('x2', x2); line.setAttribute('y2', y2);
    var strokeW = e.strength === 'strong' ? '1.5' : '1';
    line.setAttribute('stroke', 'rgba(255,255,255,.18)');
    line.setAttribute('stroke-width', strokeW);
    line.setAttribute('marker-end', 'url(#kg-arrow)');
    svg.appendChild(line);

    // Edge label (only for strong links, not too cluttered)
    if (e.strength === 'strong' && e.label) {
      var mx = (na.x + nb.x) / 2, my = (na.y + nb.y) / 2;
      var lt = document.createElementNS(svgNS, 'text');
      lt.setAttribute('x', mx); lt.setAttribute('y', my - 4);
      lt.setAttribute('text-anchor', 'middle');
      lt.setAttribute('font-size', '9');
      lt.setAttribute('fill', 'rgba(255,255,255,.35)');
      lt.textContent = e.label.slice(0, 16);
      svg.appendChild(lt);
    }
  });

  // Draw nodes
  nodes.forEach(function(n) {
    var r = n.radius || 12;
    var g = document.createElementNS(svgNS, 'g');
    g.style.cursor = 'pointer';

    // Circle
    var circ = document.createElementNS(svgNS, 'circle');
    circ.setAttribute('cx', n.x); circ.setAttribute('cy', n.y); circ.setAttribute('r', r);
    circ.setAttribute('fill', n.color || '#666');
    circ.setAttribute('stroke', 'rgba(255,255,255,.3)');
    circ.setAttribute('stroke-width', '1.5');
    g.appendChild(circ);

    // Label
    var lbl = document.createElementNS(svgNS, 'text');
    lbl.setAttribute('x', n.x); lbl.setAttribute('y', n.y + r + 12);
    lbl.setAttribute('text-anchor', 'middle');
    lbl.setAttribute('font-size', '10');
    lbl.setAttribute('fill', 'rgba(255,255,255,.75)');
    lbl.textContent = n.label;
    g.appendChild(lbl);

    // Tooltip on hover
    g.addEventListener('mouseenter', function(ev) {
      if (!tooltip) return;
      var meta = n.meta || {};
      var lines = ['<b>' + n.label + '</b>', 'Tip: ' + n.tip];
      Object.keys(meta).forEach(function(k){ if (meta[k]) lines.push(k + ': ' + meta[k]); });
      tooltip.innerHTML = lines.join('<br>');
      tooltip.style.display = 'block';
      tooltip.style.left = (ev.offsetX + 12) + 'px';
      tooltip.style.top  = (ev.offsetY + 12) + 'px';
    });
    g.addEventListener('mousemove', function(ev) {
      if (!tooltip) return;
      tooltip.style.left = (ev.offsetX + 12) + 'px';
      tooltip.style.top  = (ev.offsetY + 12) + 'px';
    });
    g.addEventListener('mouseleave', function() {
      if (tooltip) tooltip.style.display = 'none';
    });

    svg.appendChild(g);
  });

  container.innerHTML = '';
  container.appendChild(svg);
}

/* ══════════════════════════════════════════════════
   PROMENA 5 — Svetla tema JS
   ══════════════════════════════════════════════════ */
function toggleLightTheme() {
  var body = document.body;
  var isLight = body.classList.toggle('light-theme');
  localStorage.setItem('vx_theme', isLight ? 'light' : 'dark');
  var ico = document.getElementById('theme-toggle-ico');
  var lbl = document.getElementById('theme-toggle-lbl');
  if (ico) ico.textContent = isLight ? '🌙' : '☀️';
  if (lbl) lbl.textContent = isLight ? 'Tamna tema' : 'Svetla tema';
}
(function() {
  if (localStorage.getItem('vx_theme') === 'light') {
    document.body.classList.add('light-theme');
    document.addEventListener('DOMContentLoaded', function() {
      var ico = document.getElementById('theme-toggle-ico');
      var lbl = document.getElementById('theme-toggle-lbl');
      if (ico) ico.textContent = '🌙';
      if (lbl) lbl.textContent = 'Tamna tema';
    });
  }
})();

/* ══════════════════════════════════════════════════
   PROMENA 7 — Print JS
   ══════════════════════════════════════════════════ */
function pred_print() {
  var allPanes = document.querySelectorAll('.pred-subtab-pane');
  var prev = [];
  allPanes.forEach(function(p) { prev.push(p.style.display); p.style.display = 'none'; });
  var ccc = document.getElementById('pred-pane-ccc');
  if (ccc) ccc.style.display = 'block';
  window.print();
  allPanes.forEach(function(p, i) { p.style.display = prev[i]; });
}

/* ══════════════════════════════════════════════════
   PROMENA 8 — FAB JS
   ══════════════════════════════════════════════════ */
function pred_fab_toggle() {
  var menu = document.getElementById('pred-fab-menu');
  if (!menu) return;
  var open = menu.style.display !== 'none';
  menu.style.display = open ? 'none' : 'block';
  var btn = document.getElementById('pred-fab-btn');
  if (btn) btn.textContent = open ? '+' : '×';
}
function pred_fab_close() {
  var menu = document.getElementById('pred-fab-menu');
  if (menu) menu.style.display = 'none';
  var btn = document.getElementById('pred-fab-btn');
  if (btn) btn.textContent = '+';
}
function pred_fab_show() { var f = document.getElementById('pred-fab'); if (f) f.style.display = 'block'; }
function pred_fab_hide() { var f = document.getElementById('pred-fab'); if (f) { f.style.display = 'none'; pred_fab_close(); } }

/* ══════════════════════════════════════════════════
   PROMENA 9 — Onboarding wizard JS
   ══════════════════════════════════════════════════ */
var _onboardStep = 0;
var _onboardSteps = [
  { icon: '⚖️', title: 'Dobrodošli u Vindex AI', body: 'Vaš digitalni pravni asistent. Upravljajte predmetima, rokovima i dokumentima — sve na jednom mestu.' },
  { icon: '📁', title: 'Dodajte prvi predmet', body: 'Kliknite "+ Novi predmet" na komandnom centru i unesite naziv, klijenta i tip spora. Vindex AI će pratiti sve rokove i dokumente automatski.' },
  { icon: '🎤', title: 'Govorite — Vindex sluša', body: 'Kliknite dugme 🎤 Govori u gornjem desnom uglu i recite: "otvori predmet Marković" ili "uključi tajmer". Ne morate ništa da kucate.' },
  { icon: '💡', title: 'Vindex vam govori šta da radite', body: 'Kad otvorite predmet, videćete obojene preporuke: 🔴 hitno, 🟡 pažnja, 🔵 savet. Jedan klik — odlazite tačno tamo gde treba.' },
];
function onboard_show() {
  /* deaktivirano — onboardingCheck() je jedini onboarding flow */
}
function onboard_render() {
  var s = _onboardSteps[_onboardStep];
  var content = document.getElementById('onboard-step-content');
  if (content) content.innerHTML =
    '<div style="font-size:3rem;margin-bottom:1rem;">' + s.icon + '</div>' +
    '<div style="font-size:1.2rem;font-weight:700;margin-bottom:.75rem;color:#fff;">' + s.title + '</div>' +
    '<div style="font-size:14px;color:rgba(255,255,255,.65);line-height:1.7;">' + s.body + '</div>';
  var dots = document.getElementById('onboard-dots');
  if (dots) dots.innerHTML = _onboardSteps.map(function(_, i) {
    return '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' +
      (i === _onboardStep ? '#4aa8ff' : 'rgba(255,255,255,.2)') + ';margin:0 3px;"></span>';
  }).join('');
  var prev = document.getElementById('onboard-prev');
  var next = document.getElementById('onboard-next');
  if (prev) prev.style.display = _onboardStep > 0 ? 'inline-block' : 'none';
  if (next) next.textContent = _onboardStep === _onboardSteps.length - 1 ? 'Počnimo! 🚀' : 'Nastavi →';
}
function onboard_next() {
  if (_onboardStep < _onboardSteps.length - 1) { _onboardStep++; onboard_render(); }
  else { localStorage.setItem('vx_onboarded', '1'); var el = document.getElementById('onboard-overlay'); if (el) el.style.display = 'none'; }
}
function onboard_prev() { if (_onboardStep > 0) { _onboardStep--; onboard_render(); } }

async function pred_dodajBelesku() {
  if (!activePredmetId || !currentSession) return;
  var inp = document.getElementById('pred-beleska-input');
  var sadrzaj = (inp ? inp.value : '').trim();
  if (!sadrzaj) return;
  try {
    var r = await fetch(BASE_URL+'/api/predmeti/'+activePredmetId+'/beleske', {
      method:'POST', headers:_predAuthHdr(),
      body: JSON.stringify({ sadrzaj: sadrzaj })
    });
    if (r.ok) { if (inp) inp.value = ''; pred_loadDetail(activePredmetId); }
  } catch(e) {}
}

function pred_upload_trigger() {
  var inp = document.getElementById('pred-upload-input');
  if (inp) inp.click();
}

async function pred_upload_doc(file) {
  if (!file || !activePredmetId || !currentSession) return;
  var ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
  var zone    = document.getElementById('pred-upload-zone');
  var loading = document.getElementById('pred-upload-loading');
  var errEl   = document.getElementById('pred-upload-error');
  var resEl   = document.getElementById('pred-procena-result');
  var inp     = document.getElementById('pred-upload-input');
  if (errEl) errEl.style.display = 'none';
  if (['.pdf','.docx','.doc'].indexOf(ext) === -1) {
    if (errEl) { errEl.textContent = 'Podržani formati: PDF, DOCX'; errEl.style.display = 'block'; }
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    if (errEl) { errEl.textContent = 'Fajl je preko 10MB.'; errEl.style.display = 'block'; }
    return;
  }
  if (zone) zone.style.display = 'none';
  if (loading) loading.style.display = 'block';
  if (resEl) resEl.innerHTML = '<div style="font-size:0.78rem;color:rgba(255,255,255,0.4);padding:0.4rem 0;"><span class="upload-spinner"></span>Analiziram predmet...</div>';
  try {
    var fd = new FormData();
    fd.append('file', file);
    var r = await fetch(BASE_URL + '/api/predmeti/' + activePredmetId + '/upload', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + currentSession.access_token },
      body: fd
    });
    if (loading) loading.style.display = 'none';
    if (zone) zone.style.display = '';
    if (inp) inp.value = '';
    if (r.status === 415 || r.status === 422) {
      var msg = r.status === 422 ? 'Skenirani PDF — uploadujte digitalni PDF.' : 'Podržani formati: PDF, DOCX';
      if (errEl) { errEl.textContent = msg; errEl.style.display = 'block'; }
      if (resEl) resEl.innerHTML = '';
      return;
    }
    if (r.status === 413) {
      if (errEl) { errEl.textContent = 'Fajl je preko 10MB.'; errEl.style.display = 'block'; }
      if (resEl) resEl.innerHTML = '';
      return;
    }
    if (!r.ok) {
      if (errEl) { errEl.textContent = 'Greška servera (' + r.status + '). Pokušajte ponovo.'; errEl.style.display = 'block'; }
      if (resEl) resEl.innerHTML = '';
      return;
    }
    var d = await r.json();
    var mainHtml = '';
    if (d.procena) {
      var _rndr = (d.doc_type === 'presuda') ? pred_renderPresuda : pred_renderProcena;
      mainHtml = _rndr(d.procena);
    } else {
      mainHtml = '<div style="color:rgba(255,255,255,0.4);font-size:0.78rem;">Dokument je učitan. Analiza nije generisana — pokušajte ručni unos.</div>';
    }
    // Wall 4: confirm card for auto-link suggestions
    var confirmHtml = '';
    var hasPredlozi = d.predlozi_povezivanja && d.predlozi_povezivanja.length > 0;
    var hasDatumi   = d.metadata && d.metadata.datumi_kljucni && d.metadata.datumi_kljucni.length > 0;
    if (hasPredlozi || hasDatumi) {
      confirmHtml = pred_renderConfirmCard(d.predlozi_povezivanja || [], d.metadata || {});
    }
    if (resEl) resEl.innerHTML = mainHtml + confirmHtml;
    pred_loadDetail(activePredmetId);
    pred_loadHronologija(activePredmetId);
    setTimeout(function(){ pred_loadHronologija(activePredmetId); }, 3500);
  } catch(e) {
    if (loading) loading.style.display = 'none';
    if (zone) zone.style.display = '';
    if (errEl) { errEl.textContent = 'Nema veze sa serverom. Proverite konekciju.'; errEl.style.display = 'block'; }
    if (resEl) resEl.innerHTML = '';
  }
}

async function pred_submitProcena() {
  if (!currentSession) return;
  var cinjenice = (document.getElementById('pred-cinjenice').value || '').trim();
  if (!cinjenice) return;
  var resEl = document.getElementById('pred-procena-result');
  if (resEl) resEl.innerHTML = '<div style="font-size:0.78rem;color:rgba(255,255,255,0.4);">Generiše se procena...</div>';
  try {
    var body = { cinjenice: cinjenice };
    if (activePredmetId) body.predmet_id = activePredmetId;
    var r = await fetch(BASE_URL+'/api/procena', {
      method:'POST', headers:_predAuthHdr(), body: JSON.stringify(body)
    });
    var d = await r.json();
    var tekst = d.procena || '';
    if (!tekst) { if (resEl) resEl.innerHTML = '<div style="color:#ff9090;font-size:0.78rem;">Greška pri generisanju procene.</div>'; return; }
    if (resEl) resEl.innerHTML = pred_renderProcena(tekst);
    if (activePredmetId) pred_loadDetail(activePredmetId);
  } catch(e) {
    if (resEl) resEl.innerHTML = '<div style="color:#ff9090;font-size:0.78rem;">Greška veze sa serverom.</div>';
  }
}

function pred_renderProcena(tekst) {
  var sekcije = [
    {k:'1. PRAVNI OSNOV',                    icon:'⚖️',  lbl:'Pravni osnov',                   special:''},
    {k:'2. ARGUMENTI ZA TUŽIOCA',            icon:'✅',  lbl:'Argumenti tužioca',               special:''},
    {k:'3. SLABOSTI U POZICIJI TUŽIOCA',     icon:'⚠️',  lbl:'Slabosti tužioca',                special:'slabosti'},
    {k:'4. POTENCIJALNI ARGUMENTI TUŽENOG',  icon:'🛡️',  lbl:'Argumenti tuženog',               special:''},
    {k:'5. STRATEGIJA ZA TUŽIOCA',           icon:'🗺️',  lbl:'Strategija tužioca',              special:'strategija'},
    {k:'6. STRATEGIJA ZA TUŽENOG',           icon:'🛡️',  lbl:'Strategija tuženog',              special:'strategija'},
    {k:'7. PREDVIĐENI ARGUMENTI TUŽENOG',    icon:'🧩',  lbl:'Predviđeni argumenti tuženog',    special:'predvidjeni'},
    {k:'8. FAKTORI KOJI UTIČU NA ISHOD',     icon:'⚡',  lbl:'Faktori koji utiču na ishod',     special:'faktori'},
    {k:'9. SPORNE TAČKE',                    icon:'🔍',  lbl:'Sporne tačke',                    special:''},
    {k:'10. NEDOSTAJUĆE ČINJENICE',          icon:'❓',  lbl:'Nedostajuće činjenice',            special:'nedostajuce'},
    {k:'11. CRVENE ZASTAVICE',               icon:'🚨',  lbl:'Crvene zastavice',                special:'zastavice'},
    {k:'12. POTREBNI DOKAZI',                icon:'📋',  lbl:'Potrebni dokazi',                 special:'dokazi'},
    {k:'13. KOMPLETIRANOST PREDMETA',        icon:'📊',  lbl:'Kompletiranost',                  special:'kompletiranost'},
    {k:'14. PROCENA RIZIKA',                 icon:'🎯',  lbl:'Procena rizika',                  special:'rizik'},
    {k:'15. RELEVANTNA PRAKSA',              icon:'📚',  lbl:'Relevantna praksa',               special:'praksa'},
    {k:'17. PITANJA ZA KLIJENTA',            icon:'💬',  lbl:'Pitanja za klijenta',             special:'pitanja'},
    {k:'18. POUZDANOST PROCENE',             icon:'🔬',  lbl:'Pouzdanost procene',              special:'pouzdanost'},
    // v2 extended sections (Phase 3.4)
    {k:'19. ŽALBENI OSNOVI',                 icon:'⚖️',  lbl:'Žalbeni osnovi',                  special:''},
    {k:'20. SLEDEĆI KORACI',                 icon:'🚀',  lbl:'Sledeći koraci',                  special:'sledeci_koraci'},
    {k:'21. PROCENA USPEHA',                 icon:'🎯',  lbl:'Procena uspeha',                  special:'uspeh'},
    {k:'22. RELEVANTNA SUDSKA PRAKSA',       icon:'📚',  lbl:'Relevantna sudska praksa',         special:'praksa'},
    // legacy v6 16-section fallback
    {k:'9. NEDOSTAJUĆE ČINJENICE',           icon:'❓',  lbl:'Nedostajuće činjenice',            special:'nedostajuce'},
    {k:'10. POTREBNI DOKAZI',                icon:'📋',  lbl:'Potrebni dokazi',                 special:'dokazi'},
    {k:'11. KOMPLETIRANOST PREDMETA',        icon:'📊',  lbl:'Kompletiranost',                  special:'kompletiranost'},
    {k:'12. PROCENA RIZIKA',                 icon:'🎯',  lbl:'Procena rizika',                  special:'rizik'},
    {k:'13. RELEVANTNA PRAKSA',              icon:'📚',  lbl:'Relevantna praksa',               special:'praksa'},
    {k:'15. PITANJA ZA KLIJENTA',            icon:'💬',  lbl:'Pitanja za klijenta',             special:'pitanja'},
    {k:'16. POUZDANOST PROCENE',             icon:'🔬',  lbl:'Pouzdanost procene',              special:'pouzdanost'},
    // legacy v5 14-section fallback
    {k:'9. POTREBNI DOKAZI',                 icon:'📋',  lbl:'Potrebni dokazi',                 special:'dokazi'},
    {k:'10. KOMPLETIRANOST PREDMETA',        icon:'📊',  lbl:'Kompletiranost',                  special:'kompletiranost'},
    {k:'11. PROCENA RIZIKA',                 icon:'🎯',  lbl:'Procena rizika',                  special:'rizik'},
    {k:'12. RELEVANTNA PRAKSA',              icon:'📚',  lbl:'Relevantna praksa',               special:'praksa'},
    {k:'14. POUZDANOST PROCENE',             icon:'🔬',  lbl:'Pouzdanost procene',              special:'pouzdanost'},
    // legacy v4 13-section fallback
    {k:'7. KLJUČNA ČINJENICA',               icon:'🔑',  lbl:'Ključna činjenica',               special:'kljucna'},
    {k:'8. SPORNE TAČKE',                    icon:'🔍',  lbl:'Sporne tačke',                    special:''},
    // legacy v3 12-section fallback
    {k:'6. KLJUČNA ČINJENICA',               icon:'🔑',  lbl:'Ključna činjenica',               special:'kljucna'},
    // legacy v2 fallback
    {k:'6. SPORNE TAČKE',                    icon:'🔍',  lbl:'Sporne tačke',                    special:''},
    {k:'7. POTREBNI DOKAZI',                 icon:'📋',  lbl:'Potrebni dokazi',                 special:'dokazi'},
    {k:'8. KOMPLETIRANOST PREDMETA',         icon:'📊',  lbl:'Kompletiranost',                  special:'kompletiranost'},
    {k:'9. PROCENA RIZIKA',                  icon:'🎯',  lbl:'Procena rizika',                  special:'rizik'},
    {k:'10. RELEVANTNA PRAKSA',              icon:'📚',  lbl:'Relevantna praksa',               special:'praksa'},
    // legacy v1 6-section fallback
    {k:'4. SPORNE TAČKE',                    icon:'🔍',  lbl:'Sporne tačke',                    special:''},
    {k:'5. NEDOSTAJUĆI DOKAZI',              icon:'📋',  lbl:'Potrebni dokazi',                 special:'dokazi'},
    {k:'6. PROCENA RIZIKA',                  icon:'🎯',  lbl:'Procena rizika',                  special:'rizik'},
  ];
  // Try to find sections without number prefix as fallback (GPT sometimes omits numbers)
  var _fallbackSek = [
    {k:'FAKTORI KOJI UTIČU NA ISHOD',    icon:'⚡',  lbl:'Faktori koji utiču na ishod',   special:'faktori'},
    {k:'SLABOSTI U POZICIJI TUŽIOCA',    icon:'⚠️',  lbl:'Slabosti tužioca',              special:'slabosti'},
    {k:'POTENCIJALNI ARGUMENTI TUŽENOG', icon:'🛡️',  lbl:'Argumenti tuženog',             special:''},
    {k:'CRVENE ZASTAVICE',               icon:'🚨',  lbl:'Crvene zastavice',              special:'zastavice'},
    {k:'NEDOSTAJUĆE ČINJENICE',          icon:'❓',  lbl:'Nedostajuće činjenice',          special:'nedostajuce'},
    {k:'KLJUČNA ČINJENICA',              icon:'🔑',  lbl:'Ključna činjenica',              special:'kljucna'},
    {k:'KOMPLETIRANOST PREDMETA',        icon:'📊',  lbl:'Kompletiranost',                 special:'kompletiranost'},
    {k:'PROCENA RIZIKA',                 icon:'🎯',  lbl:'Procena rizika',                 special:'rizik'},
    {k:'RELEVANTNA PRAKSA',              icon:'📚',  lbl:'Relevantna praksa',              special:'praksa'},
    {k:'PITANJA ZA KLIJENTA',            icon:'💬',  lbl:'Pitanja za klijenta',            special:'pitanja'},
    {k:'POUZDANOST PROCENE',             icon:'🔬',  lbl:'Pouzdanost procene',             special:'pouzdanost'},
    {k:'ŽALBENI OSNOVI',                 icon:'⚖️',  lbl:'Žalbeni osnovi',                 special:''},
    {k:'SLEDEĆI KORACI',                 icon:'🚀',  lbl:'Sledeći koraci',                 special:'sledeci_koraci'},
    {k:'PROCENA USPEHA',                 icon:'🎯',  lbl:'Procena uspeha',                 special:'uspeh'},
    {k:'RELEVANTNA SUDSKA PRAKSA',       icon:'📚',  lbl:'Relevantna sudska praksa',        special:'praksa'},
    {k:'STRATEGIJA ZA TUŽIOCA',          icon:'🗺️',  lbl:'Strategija tužioca',             special:'strategija'},
    {k:'STRATEGIJA ZA TUŽENOG',          icon:'🛡️',  lbl:'Strategija tuženog',             special:'strategija'},
    {k:'PREDVIĐENI ARGUMENTI TUŽENOG',   icon:'🧩',  lbl:'Predviđeni argumenti tuženog',   special:'predvidjeni'},
  ];
  var positions = [];
  sekcije.forEach(function(s) {
    var pos = tekst.indexOf(s.k);
    if (pos !== -1) positions.push({s:s, pos:pos});
  });
  positions.sort(function(a,b){return a.pos-b.pos;});
  var deduped = [];
  positions.forEach(function(p) {
    if (!deduped.length || p.pos - deduped[deduped.length-1].pos > 5) deduped.push(p);
  });
  // If critical sections are missing, try number-agnostic fallbacks
  var _foundLbls = {};
  deduped.forEach(function(d){ _foundLbls[d.s.lbl] = true; });
  _fallbackSek.forEach(function(s) {
    if (_foundLbls[s.lbl]) return;
    var pos = tekst.indexOf(s.k);
    if (pos !== -1) deduped.push({s:s, pos:pos});
  });
  deduped.sort(function(a,b){return a.pos-b.pos;});
  var _deduped2 = [];
  deduped.forEach(function(p) {
    if (!_deduped2.length || p.pos - _deduped2[_deduped2.length-1].pos > 5) _deduped2.push(p);
  });
  deduped = _deduped2;
  if (!deduped.length) return '<pre style="font-size:0.78rem;white-space:pre-wrap;color:rgba(255,255,255,0.72);">'+escHtml(tekst)+'</pre>';

  var html = '';
  deduped.forEach(function(x,i) {
    var start    = x.pos + x.s.k.length;
    var end      = i+1 < deduped.length ? deduped[i+1].pos : tekst.length;
    var body     = tekst.slice(start, end).replace(/^\s*\n?/, '').trimEnd();
    var extraCls = '';
    var bodyHtml = '';

    if (x.s.special === 'rizik') {
      // Determine header color from split risks — use highest severity
      var _rizikLevel = /VISOK/i.test(body) ? 'VISOK' : (/SREDNJI/i.test(body) ? 'SREDNJI' : 'NIZAK');
      if (_rizikLevel === 'VISOK')        { extraCls = ' risk-visok';   _pred_setRizik('VISOK'); }
      else if (_rizikLevel === 'SREDNJI') { extraCls = ' risk-srednji'; _pred_setRizik('SREDNJI'); }
      else                               { extraCls = ' risk-nizak';   _pred_setRizik('NIZAK'); }
      // Render split risk lines with colored badges
      var rLines = body.split('\n').map(function(ln) {
        var rM = ln.match(/^(Rizik za (?:tužioca|tuženog)):\s*(NIZAK|SREDNJI|VISOK)\s*[—-]\s*(.+)/i);
        if (rM) {
          var rc = /VISOK/i.test(rM[2]) ? '#f87171' : (/SREDNJI/i.test(rM[2]) ? '#facc15' : '#4ade80');
          return '<div style="display:flex;align-items:baseline;gap:0.5rem;margin:0.15rem 0;">'
            +'<span style="font-size:0.74rem;color:rgba(255,255,255,0.5);min-width:9rem;">'+escHtml(rM[1])+':</span>'
            +'<span style="font-weight:700;color:'+rc+';font-size:0.78rem;min-width:4.5rem;">'+escHtml(rM[2])+'</span>'
            +'<span style="font-size:0.74rem;color:rgba(255,255,255,0.6);">'+escHtml(rM[3])+'</span>'
            +'</div>';
        }
        return escHtml(ln) ? '<div style="font-size:0.77rem;color:rgba(255,255,255,0.65);">'+escHtml(ln)+'</div>' : '';
      }).join('');
      bodyHtml = rLines || escHtml(body);

    } else if (x.s.special === 'dokazi') {
      var dokaziCount = (body.match(/^\s*[-•🔴🟡🟢\d\.]/gmu) || []).length || (body.trim() ? 1 : 0);
      _pred_setDokazi(dokaziCount);
      bodyHtml = escHtml(body);

    } else if (x.s.special === 'strategija') {
      // Highlight Snaga argumenta line with colored badge
      var lines = body.split('\n');
      var rendered = lines.map(function(ln) {
        var m = ln.match(/^(Snaga argumenta|Verovatnoća uspeha|Najjači napad|Najjača odbrana|Zašto|Dokaz koji odlučuje spor|Napomena za radne sporove):\s*(.+)/i);
        if (!m) return escHtml(ln);
        var label = m[1]; var val = m[2].trim();
        if (/Snaga argumenta|Verovatnoća uspeha/i.test(label)) {
          var vc = /VISOKA/i.test(val) ? '#4ade80' : (/NISKA/i.test(val) ? '#f87171' : '#facc15');
          return '<span style="color:rgba(255,255,255,0.45);font-size:0.72rem;">'+escHtml(label)+': </span>'
            +'<span style="color:'+vc+';font-weight:700;">'+escHtml(val)+'</span>';
        }
        if (/Napomena za radne sporove/i.test(label)) {
          return '<div style="margin-top:0.4rem;padding:0.3rem 0.6rem;background:rgba(250,204,21,0.07);border-left:2px solid rgba(250,204,21,0.4);font-size:0.72rem;color:rgba(250,204,21,0.75);">'
            +'<span style="font-weight:600;">'+escHtml(label)+':</span> '+escHtml(val)+'</div>';
        }
        return '<span style="color:rgba(255,255,255,0.45);font-size:0.72rem;">'+escHtml(label)+': </span>'
          +'<span style="color:rgba(255,255,255,0.82);">'+escHtml(val)+'</span>';
      });
      bodyHtml = rendered.join('\n');

    } else if (x.s.special === 'predvidjeni') {
      // Render each argument with danger badge
      var lines = body.split('\n');
      var argHtml = '';
      lines.forEach(function(ln) {
        var argM = ln.match(/^-\s*(Argument\s*\d+):\s*(.+)/i);
        if (argM) {
          argHtml += '<div style="font-weight:600;color:#e0e4f0;margin-top:0.45rem;">'+escHtml(argM[1])+': <span style="font-weight:400;color:rgba(255,255,255,0.75);">'+escHtml(argM[2])+'</span></div>';
          return;
        }
        var opM = ln.match(/^\s+Procena opasnosti:\s*(VISOKA|SREDNJA|NISKA)\s*[—-]\s*(.+)/i);
        if (opM) {
          var oc = /VISOKA/i.test(opM[1]) ? '#f87171' : (/NISKA/i.test(opM[1]) ? '#4ade80' : '#facc15');
          argHtml += '<div style="padding-left:0.75rem;font-size:0.75rem;margin-top:0.1rem;">'
            +'<span style="color:rgba(255,255,255,0.4);">Procena opasnosti: </span>'
            +'<span style="color:'+oc+';font-weight:700;">'+escHtml(opM[1])+'</span>'
            +'<span style="color:rgba(255,255,255,0.5);"> — '+escHtml(opM[2])+'</span></div>';
          return;
        }
        if (ln.trim()) argHtml += '<div style="color:rgba(255,255,255,0.6);font-size:0.78rem;">'+escHtml(ln)+'</div>';
      });
      bodyHtml = argHtml || escHtml(body);

    } else if (x.s.special === 'faktori') {
      // Render factor | impact | status | source table
      var lines = body.split('\n');
      var rows = lines.map(function(ln) {
        var m = ln.match(/^Faktor:\s*(.+?)\s*\|\s*Uticaj:\s*(VEOMA VISOK|VISOK|SREDNJI|NIZAK)(?:\s*\|\s*Status:\s*([^|]+?))?(?:\s*\|\s*Izvor:\s*([^\n]+?))?\s*$/i);
        if (!m) return ln.trim() ? '<div style="color:rgba(255,255,255,0.45);font-size:0.72rem;margin-top:0.15rem;">'+escHtml(ln)+'</div>' : '';
        var fc = /VEOMA VISOK/i.test(m[2]) ? '#f87171' : (/VISOK/i.test(m[2]) ? '#fbbf24' : (/SREDNJI/i.test(m[2]) ? '#60a5fa' : 'rgba(255,255,255,0.4)'));
        var s3 = m[3] ? m[3].trim() : '';
        var sc = s3 ? (/^Potv/i.test(s3) ? '#4ade80' : (/^Nepotv/i.test(s3) ? '#f87171' : '#facc15')) : '';
        var statusHtml = s3 ? '<span style="font-size:0.67rem;color:'+sc+';margin-left:0.25rem;padding:0.07rem 0.32rem;background:'+sc+'1a;border-radius:3px;white-space:nowrap;">'+escHtml(s3)+'</span>' : '';
        var s4 = m[4] ? m[4].trim() : '';
        var ic = s4 ? (/Dostavljen dokument/i.test(s4) ? '#4ade80' : (/Dokument nije/i.test(s4) ? '#f87171' : (/Izjava/i.test(s4) ? '#89c8ff' : '#a78bfa'))) : '';
        var izvorHtml = s4 ? '<span style="font-size:0.66rem;color:'+ic+';margin-left:0.25rem;padding:0.07rem 0.32rem;background:'+ic+'18;border-radius:3px;white-space:nowrap;">'+escHtml(s4)+'</span>' : '';
        return '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:0.25rem;padding:0.25rem 0;border-bottom:1px solid rgba(255,255,255,0.05);">'
          +'<span style="flex:1;min-width:8rem;font-size:0.78rem;color:rgba(255,255,255,0.78);">'+escHtml(m[1])+'</span>'
          +'<span style="font-size:0.7rem;font-weight:700;color:'+fc+';white-space:nowrap;">'+escHtml(m[2])+'</span>'
          +statusHtml+izvorHtml
          +'</div>';
      }).join('');
      bodyHtml = rows || escHtml(body);

    } else if (x.s.special === 'slabosti') {
      // Render plaintiff weaknesses as orange bullet list
      var lines = body.split('\n');
      bodyHtml = lines.map(function(ln) {
        var m = ln.match(/^[-\u2022\d\.]+\s*(.+)/);
        if (m) return '<div style="display:flex;gap:0.5rem;padding:0.18rem 0;font-size:0.78rem;">'
          +'<span style="color:#fb923c;flex-shrink:0;">&#9888;</span>'
          +'<span style="color:rgba(255,200,150,0.85);">'+escHtml(m[1])+'</span>'
          +'</div>';
        return ln.trim() ? '<div style="font-size:0.74rem;color:rgba(255,255,255,0.4);">'+escHtml(ln)+'</div>' : '';
      }).join('');
      if (!bodyHtml.trim()) bodyHtml = escHtml(body);

    } else if (x.s.special === 'kljucna') {
      // Render DA/NE blocks as structured cards (legacy v3/v4)
      var blocks = body.split(/(?=Ključna činjenica \d+:)/);
      bodyHtml = blocks.map(function(blk) {
        if (!blk.trim()) return '';
        var lines = blk.split('\n');
        var out = lines.map(function(ln) {
          if (/^Ključna činjenica \d+:/i.test(ln)) {
            return '<div style="font-weight:600;color:#e0e4f0;margin-top:0.3rem;">'+escHtml(ln)+'</div>';
          } else if (/^Ako DA/i.test(ln)) {
            return '<div style="color:#4ade80;font-size:0.75rem;padding-left:0.6rem;">'+escHtml(ln)+'</div>';
          } else if (/^Ako NE/i.test(ln)) {
            return '<div style="color:#f87171;font-size:0.75rem;padding-left:0.6rem;">'+escHtml(ln)+'</div>';
          }
          return escHtml(ln) ? '<div style="color:rgba(255,255,255,0.65);">'+escHtml(ln)+'</div>' : '';
        }).join('');
        return '<div style="margin-bottom:0.5rem;">'+out+'</div>';
      }).join('');
      if (!bodyHtml.trim()) bodyHtml = escHtml(body);

    } else if (x.s.special === 'kompletiranost') {
      var pctMatch = body.match(/KOMPLETIRANOST:\s*(\d+)%/i);
      var pct = pctMatch ? parseInt(pctMatch[1], 10) : 0;
      var barCls = pct >= 70 ? '' : (pct >= 40 ? ' mid' : ' low');
      bodyHtml = '<div class="procena-progress-wrap"><div class="procena-progress-bar'+barCls+'" style="width:'+Math.min(100,pct)+'%"></div></div>'
        + '<div style="font-size:0.72rem;color:rgba(255,255,255,0.45);margin-bottom:0.3rem;">'+pct+'% kompletno</div>'
        + escHtml(body.replace(/KOMPLETIRANOST:\s*\d+%\s*/i, ''));

    } else if (x.s.special === 'pouzdanost') {
      var pMatch = body.match(/POUZDANOST:\s*(\d+)%/i);
      var ppct = pMatch ? parseInt(pMatch[1], 10) : 0;
      var pBarCls = ppct >= 70 ? '' : (ppct >= 40 ? ' mid' : ' low');
      var cleanBody = body.replace(/POUZDANOST:\s*\d+%\s*/i, '');
      var pLines = cleanBody.split('\n').map(function(ln) {
        var plus = ln.match(/\(\s*\+(\d+)%\s*\)/);
        var minus = ln.match(/\(\s*-(\d+)%\s*\)/);
        if (plus)  return '<div style="font-size:0.74rem;color:#4ade80;">'+escHtml(ln)+'</div>';
        if (minus) return '<div style="font-size:0.74rem;color:#f87171;">'+escHtml(ln)+'</div>';
        return escHtml(ln) ? '<div style="font-size:0.74rem;color:rgba(255,255,255,0.55);">'+escHtml(ln)+'</div>' : '';
      }).join('');
      bodyHtml = '<div class="procena-progress-wrap"><div class="procena-progress-bar'+pBarCls+'" style="width:'+Math.min(100,ppct)+'%"></div></div>'
        + '<div style="font-size:0.72rem;color:rgba(255,255,255,0.45);margin-bottom:0.4rem;">'+ppct+'% pouzdano</div>'
        + pLines;

    } else if (x.s.special === 'sledeci') {
      // Render document list with +XX% badges, plus arrow forecast
      var lines = body.split('\n');
      var sHtml = lines.map(function(ln) {
        var docM = ln.match(/^-\s*(.+?)\s*→\s*povećanje:\s*\+(\d+)%/i);
        if (docM) {
          return '<div style="display:flex;align-items:baseline;gap:0.5rem;padding:0.2rem 0;">'
            +'<span style="flex:1;font-size:0.78rem;color:rgba(255,255,255,0.78);">'+escHtml(docM[1])+'</span>'
            +'<span style="font-size:0.72rem;font-weight:700;color:#4ade80;white-space:nowrap;">+'+escHtml(docM[2])+'%</span>'
            +'</div>';
        }
        var fwdM = ln.match(/(?:Trenutna pouzdanost:\s*(\d+)%\s*→\s*Očekivana nakon dokumenata:\s*(\d+)%|Očekivana pouzdanost nakon uploada:\s*(\d+)%\s*→\s*(\d+)%)/i);
        if (fwdM) {
          var _from = fwdM[1] || fwdM[3]; var _to = fwdM[2] || fwdM[4];
          return '<div style="margin-top:0.5rem;padding:0.3rem 0.65rem;background:rgba(74,222,128,0.07);border-left:2px solid rgba(74,222,128,0.4);font-size:0.75rem;">'
            +'<span style="color:rgba(255,255,255,0.45);">Pouzdanost: </span>'
            +'<span style="color:#f87171;font-weight:600;">'+escHtml(_from)+'%</span>'
            +'<span style="color:rgba(255,255,255,0.35);"> → </span>'
            +'<span style="color:#4ade80;font-weight:700;">'+escHtml(_to)+'%</span>'
            +'</div>';
        }
        return ln.trim() ? '<div style="font-size:0.75rem;color:rgba(255,255,255,0.5);">'+escHtml(ln)+'</div>' : '';
      }).join('');
      bodyHtml = sHtml || escHtml(body);

    } else if (x.s.special === 'praksa') {
      // Each decision starts with "• [" — split into cards
      var chunks = body.split(/(?=•\s*\[)/);
      var cards = chunks.map(function(c) {
        if (!c.trim()) return '';
        var lines = c.split('\n');
        var out = lines.map(function(ln) {
          var simM = ln.match(/Sličnost sa predmetom:\s*(\d+)%/i);
          if (simM) {
            var sim = parseInt(simM[1], 10);
            var sc = sim >= 70 ? '#4ade80' : (sim >= 40 ? '#facc15' : 'rgba(255,255,255,0.5)');
            return '<span style="color:rgba(255,255,255,0.45);font-size:0.7rem;">Sličnost: </span>'
              +'<span style="color:'+sc+';font-weight:700;">'+sim+'%</span>';
          }
          if (/^Pravni stav:/i.test(ln)) {
            return '<div style="color:#89c8ff;font-style:italic;font-size:0.74rem;margin:0.15rem 0;">'+escHtml(ln)+'</div>';
          }
          if (/^Zašto je relevantna:/i.test(ln)) {
            return '<div style="color:rgba(255,255,255,0.5);font-size:0.72rem;">'+escHtml(ln)+'</div>';
          }
          if (/^Poklapanja:/i.test(ln)) {
            return '<div style="color:#4ade80;font-size:0.72rem;margin-top:0.1rem;">'+escHtml(ln)+'</div>';
          }
          if (/^Razlike:/i.test(ln)) {
            return '<div style="color:#f87171;font-size:0.72rem;margin-top:0.1rem;">'+escHtml(ln)+'</div>';
          }
          if (/^Ako sud usvoji isti pravni stav/i.test(ln)) {
            return '<div style="margin-top:0.2rem;padding:0.25rem 0.55rem;background:rgba(167,139,250,0.08);border-left:2px solid rgba(167,139,250,0.4);font-size:0.72rem;color:rgba(167,139,250,0.85);">'+escHtml(ln)+'</div>';
          }
          var podM = ln.match(/^Podržava:\s*(Tužioca|Tuženog|Neutralno)/i);
          if (podM) {
            var pc = /Tužioca/i.test(podM[1]) ? '#4ade80' : (/Tuženog/i.test(podM[1]) ? '#f87171' : '#94a3b8');
            return '<div style="margin-top:0.15rem;display:inline-flex;align-items:center;gap:0.35rem;font-size:0.72rem;">'
              +'<span style="color:rgba(255,255,255,0.4);">Podržava:</span>'
              +'<span style="font-weight:700;color:'+pc+';padding:0.1rem 0.45rem;background:'+pc+'1a;border-radius:3px;">'+escHtml(podM[1])+'</span>'
              +'</div>';
          }
          if (/^•/.test(ln.trim())) {
            return '<div style="font-weight:600;color:#e0e4f0;margin-bottom:0.15rem;">'+escHtml(ln)+'</div>';
          }
          return escHtml(ln) ? '<div>'+escHtml(ln)+'</div>' : '';
        }).join('');
        return '<div class="procena-praksa-item">'+out+'</div>';
      }).join('');
      bodyHtml = cards || escHtml(body);

    } else if (x.s.special === 'zastavice') {
      // Render red flag critical issues
      var lines = body.split('\n');
      bodyHtml = lines.map(function(ln) {
        var m = ln.match(/^[-\u2022]\s*(?:\uD83D\uDEA8\s*)?(.+)/);
        if (m) return '<div style="display:flex;gap:0.5rem;padding:0.2rem 0;font-size:0.78rem;border-bottom:1px solid rgba(248,113,113,0.1);">'
          +'<span style="flex-shrink:0;">&#128680;</span>'
          +'<span style="color:#fca5a5;font-weight:500;">'+escHtml(m[1])+'</span>'
          +'</div>';
        return ln.trim() ? '<div style="font-size:0.74rem;color:rgba(255,255,255,0.35);">'+escHtml(ln)+'</div>' : '';
      }).join('');
      if (!bodyHtml.trim()) bodyHtml = escHtml(body);

    } else if (x.s.special === 'nedostajuce') {
      // Render unknown-fact questions as amber bullet list
      var lines = body.split('\n');
      bodyHtml = lines.map(function(ln) {
        var m = ln.match(/^-\s*(.+)/);
        if (m) return '<div style="display:flex;gap:0.5rem;padding:0.18rem 0;font-size:0.78rem;">'
          +'<span style="color:#facc15;flex-shrink:0;">?</span>'
          +'<span style="color:rgba(255,255,255,0.75);">'+escHtml(m[1])+'</span>'
          +'</div>';
        return ln.trim() ? '<div style="font-size:0.74rem;color:rgba(255,255,255,0.4);">'+escHtml(ln)+'</div>' : '';
      }).join('');
      if (!bodyHtml.trim()) bodyHtml = escHtml(body);

    } else if (x.s.special === 'pitanja') {
      // Render client questions — supports → or - prefix
      var lines = body.split('\n');
      bodyHtml = lines.map(function(ln) {
        var m = ln.match(/^(?:\u2192|->|-|\u2022)\s*(.+)/);
        if (m) return '<div style="display:flex;gap:0.5rem;padding:0.18rem 0;font-size:0.78rem;">'
          +'<span style="color:#60a5fa;flex-shrink:0;font-weight:700;">&rarr;</span>'
          +'<span style="color:rgba(255,255,255,0.78);">'+escHtml(m[1])+'</span>'
          +'</div>';
        return ln.trim() ? '<div style="font-size:0.74rem;color:rgba(255,255,255,0.4);">'+escHtml(ln)+'</div>' : '';
      }).join('');
      if (!bodyHtml.trim()) bodyHtml = escHtml(body);

    } else if (x.s.special === 'sledeci_koraci') {
      // Render numbered process steps
      var lines = body.split('\n');
      var sHtml = lines.map(function(ln) {
        var m = ln.match(/^(\d+)\.\s+(.+)/);
        if (m) return '<div style="display:flex;gap:0.6rem;padding:0.22rem 0;align-items:baseline;border-bottom:1px solid rgba(255,255,255,0.04);">'
          +'<span style="font-size:0.7rem;font-weight:700;color:#4aa8ff;min-width:1.3rem;flex-shrink:0;">'+escHtml(m[1])+'.</span>'
          +'<span style="font-size:0.78rem;color:rgba(255,255,255,0.82);">'+escHtml(m[2])+'</span>'
          +'</div>';
        return ln.trim() ? '<div style="font-size:0.74rem;color:rgba(255,255,255,0.4);">'+escHtml(ln)+'</div>' : '';
      }).join('');
      bodyHtml = sHtml || escHtml(body);

    } else if (x.s.special === 'uspeh') {
      // Render PROCENA USPEHA: XX% with progress bar
      var uMatch = body.match(/PROCENA USPEHA:\s*(\d+)%/i);
      var upct = uMatch ? parseInt(uMatch[1], 10) : 0;
      var uBarCls = upct >= 65 ? '' : (upct >= 40 ? ' mid' : ' low');
      var uClean = body.replace(/PROCENA USPEHA:\s*\d+%\s*/i, '');
      var uLines = uClean.split('\n').map(function(ln) {
        if (/^Faktori koji povećavaju šanse:/i.test(ln)) {
          return '<div style="font-size:0.74rem;color:#4ade80;margin-top:0.35rem;font-weight:600;">'+escHtml(ln)+'</div>';
        }
        if (/^Faktori koji smanjuju šanse:/i.test(ln)) {
          return '<div style="font-size:0.74rem;color:#f87171;margin-top:0.35rem;font-weight:600;">'+escHtml(ln)+'</div>';
        }
        var bM = ln.match(/^-\s*(.+)/);
        if (bM) return '<div style="font-size:0.74rem;color:rgba(255,255,255,0.68);padding-left:0.5rem;padding:0.1rem 0 0.1rem 0.5rem;">'+escHtml(ln)+'</div>';
        return ln.trim() ? '<div style="font-size:0.74rem;color:rgba(255,255,255,0.58);">'+escHtml(ln)+'</div>' : '';
      }).join('');
      bodyHtml = '<div class="procena-progress-wrap"><div class="procena-progress-bar'+uBarCls+'" style="width:'+Math.min(100,upct)+'%"></div></div>'
        + '<div style="font-size:0.72rem;color:rgba(255,255,255,0.45);margin-bottom:0.4rem;">'+upct+'% verovatnoća uspeha tužioca</div>'
        + uLines;

    } else {
      bodyHtml = escHtml(body);
    }

    var openCls = (x.s.special === 'kompletiranost' || x.s.special === 'rizik' || x.s.special === 'pouzdanost' || x.s.special === 'zastavice' || x.s.special === 'uspeh') ? ' open' : '';
    html += '<div class="procena-section">'
      +'<div class="procena-section-hdr'+extraCls+'" onclick="this.nextElementSibling.classList.toggle(\'open\')">'
      +'<span class="sec-icon">'+x.s.icon+'</span>'+escHtml(x.s.lbl)+' <span>▾</span></div>'
      +'<div class="procena-section-body'+openCls+'">'+bodyHtml+'</div></div>';
  });
  return html;
}

function pred_renderPresuda(tekst) {
  var sekcije = [
    {k:'1. REZIME PRESUDE',              icon:'📄', lbl:'Rezime presude',        isZalba:false},
    {k:'2. KLJUČNI ARGUMENTI SUDA',      icon:'⚖️',  lbl:'Argumenti suda',        isZalba:false},
    {k:'3. PRIMENJENI PROPISI',          icon:'📋', lbl:'Primenjeni propisi',     isZalba:false},
    {k:'4. POTENCIJALNI ŽALBENI OSNOVI', icon:'🔍', lbl:'Žalbeni osnovi',         isZalba:false},
    {k:'5. PROCENA IZGLEDA ŽALBE',       icon:'🎯', lbl:'Procena izgleda žalbe', isZalba:true},
  ];
  var positions = [];
  sekcije.forEach(function(s) {
    var pos = tekst.indexOf(s.k);
    if (pos !== -1) positions.push({s:s, pos:pos});
  });
  positions.sort(function(a,b){return a.pos-b.pos;});
  var deduped = [];
  positions.forEach(function(p) {
    if (!deduped.length || p.pos - deduped[deduped.length-1].pos > 5) deduped.push(p);
  });
  if (!deduped.length) return '<pre style="font-size:0.78rem;white-space:pre-wrap;color:rgba(255,255,255,0.72);">'+escHtml(tekst)+'</pre>';
  var html = '<div style="font-size:0.67rem;font-weight:700;letter-spacing:.07em;color:rgba(255,255,255,0.28);text-transform:uppercase;margin-bottom:0.5rem;padding-bottom:0.3rem;border-bottom:1px solid rgba(255,255,255,0.06);">📄 Analiza presude</div>';
  deduped.forEach(function(x,i) {
    var start = x.pos + x.s.k.length;
    var end   = i+1 < deduped.length ? deduped[i+1].pos : tekst.length;
    var body  = tekst.slice(start, end).replace(/^\s*\n?/, '').trimEnd();
    var extraCls = '';
    var badgeHtml = '';
    if (x.s.isZalba) {
      var ocena = '';
      if (/\bVISOK\b/.test(body))   { ocena = 'VISOK';   extraCls = ' risk-visok'; }
      else if (/\bSREDNJI\b/.test(body)) { ocena = 'SREDNJI'; extraCls = ' risk-srednji'; }
      else if (/\bNIZAK\b/.test(body))   { ocena = 'NIZAK';   extraCls = ' risk-nizak'; }
      _pred_setRizik(ocena || 'SREDNJI');
      if (ocena) {
        var bg, cl, bc;
        if (ocena === 'VISOK')        { bg='rgba(74,222,128,0.12)';  cl='#4ade80'; bc='rgba(74,222,128,0.35)'; }
        else if (ocena === 'SREDNJI') { bg='rgba(250,204,21,0.12)';  cl='#facc15'; bc='rgba(250,204,21,0.35)'; }
        else                          { bg='rgba(248,113,113,0.12)'; cl='#f87171'; bc='rgba(248,113,113,0.35)'; }
        badgeHtml = '<div style="display:inline-flex;align-items:baseline;gap:0.45rem;background:'+bg+';border:1px solid '+bc+';border-radius:8px;padding:0.3rem 0.9rem;margin-bottom:0.55rem;">'
          +'<span style="font-size:1.05rem;font-weight:800;color:'+cl+';">'+ocena+'</span>'
          +'<span style="font-size:0.67rem;color:'+cl+';opacity:0.75;font-weight:500;">izgled žalbe</span>'
          +'</div>';
      }
    }
    html += '<div class="procena-section">'
      +'<div class="procena-section-hdr'+extraCls+'" onclick="this.nextElementSibling.classList.toggle(\'open\')">'
      +'<span class="sec-icon">'+x.s.icon+'</span>'+escHtml(x.s.lbl)+' <span>▾</span></div>'
      +'<div class="procena-section-body'+(x.s.isZalba?' open':'')+'">'+badgeHtml+escHtml(body)+'</div></div>';
  });
  return html;
}

function _pred_setRizik(val) {
  var el = document.getElementById('pred-s-rizik');
  if (!el) return;
  var cls = val === 'NIZAK' ? 'risk-nizak' : val === 'VISOK' ? 'risk-visok' : 'risk-srednji';
  el.innerHTML = '<span class="'+cls+'">'+val+'</span>';
}
function _pred_setDokazi(n) {
  var el = document.getElementById('pred-s-dokazi');
  if (el) el.textContent = n > 0 ? n : '—';
}

// ─── Intake Wizard ───────────────────────────────────────────────────────────
var _iStep = 1;
var _iKlijentId   = null;
var _iKlijentName = '';
var _iSessionId   = null;   // uploaded doc session_id
var _iFiles       = [];     // [{name, sessionId}]
var _iAnaliza     = null;   // ekstrakcija result
var _iDirty       = false;
var _iSearchTimer = null;

var _INTAKE_STEP_LABELS = ['Klijent','Opis problema','Dokumenti','AI analiza','Predlog'];

function intakeOtvori() {
  if (!currentSession) { openModal(); return; }
  _iStep = 1; _iKlijentId = null; _iKlijentName = ''; _iSessionId = null;
  _iFiles = []; _iAnaliza = null; _iDirty = false;
  document.getElementById('intake-overlay').classList.add('open');
  _intakeRenderStep();
  document.getElementById('intake-klijent-search').value = '';
  document.getElementById('intake-klijent-results').innerHTML = '';
  document.getElementById('intake-klijent-selected').style.display = 'none';
  document.getElementById('intake-opis').value = '';
  document.getElementById('intake-opis-counter').textContent = '0 / 4000';
  document.getElementById('intake-opis-warn').style.display = 'none';
  document.getElementById('intake-files-list').innerHTML = '';
  document.getElementById('intake-upload-status').textContent = '';
  document.getElementById('intake-ai-result').style.display = 'none';
  document.getElementById('intake-ai-loading').style.display = 'block';
}

function intakeZatvori() {
  _iDirty = false;
  document.getElementById('intake-overlay').classList.remove('open');
  // Reset pipeline screen for next open
  var prs = document.getElementById('intake-pipeline-result');
  if (prs) prs.classList.remove('active');
  var pll = document.getElementById('intake-pipeline-loading');
  if (pll) pll.style.display = 'none';
  var footer = document.getElementById('intake-panel-footer');
  if (footer) footer.style.display = '';
  var preporukaWrap = document.getElementById('pipeline-preporuka-wrap');
  if (preporukaWrap) preporukaWrap.style.display = 'none';
}

function intakeConfirmClose() {
  if (_iDirty && !confirm('Imate nesačuvane izmene. Zatvoriti wizard?')) return;
  intakeZatvori();
}

function intakeNoviKlijentOpen() {
  crmOtvoriFormu();
}

function _intakeRenderStep() {
  ['intake-s1','intake-s2','intake-s3','intake-s4','intake-s5'].forEach(function(id, i){
    document.getElementById(id).style.display = (i + 1 === _iStep) ? '' : 'none';
  });
  for (var i = 0; i < 5; i++) {
    var dot = document.getElementById('isb-' + i);
    dot.className = 'intake-step-dot' + (i + 1 < _iStep ? ' done' : i + 1 === _iStep ? ' active' : '');
  }
  var lbl = document.getElementById('intake-step-label');
  if (lbl) lbl.textContent = 'Korak ' + _iStep + ' / 5 — ' + _INTAKE_STEP_LABELS[_iStep - 1];

  var backBtn = document.getElementById('intake-btn-back');
  var nextBtn = document.getElementById('intake-btn-next');
  backBtn.style.display = _iStep > 1 ? '' : 'none';
  nextBtn.textContent = _iStep === 5 ? 'Kreiraj predmet' : 'Dalje →';
  nextBtn.disabled = false;

  if (_iStep === 4 && !_iAnaliza) {
    nextBtn.disabled = true;
    _intakeRunEkstrakcija();
  }
}

async function intakeNext() {
  if (_iStep === 1) {
    if (!_iKlijentId) { alert('Izaberite klijenta pre nastavka.'); return; }
    _iDirty = true;
  }
  if (_iStep === 2) {
    var opis = (document.getElementById('intake-opis').value || '').trim();
    if (opis.length < 20) {
      document.getElementById('intake-opis-warn').style.display = 'block';
      return;
    }
  }
  if (_iStep === 4) {
    if (!_iAnaliza) { return; }
  }
  if (_iStep === 5) {
    await _intakeKreiraj();
    return;
  }
  _iStep++;
  _intakeRenderStep();
}

function intakeBack() {
  if (_iStep > 1) { _iStep--; _intakeRenderStep(); }
}

function intakeOpisChange() {
  var v = (document.getElementById('intake-opis').value || '');
  document.getElementById('intake-opis-counter').textContent = v.length + ' / 4000';
  if (v.trim().length >= 20) document.getElementById('intake-opis-warn').style.display = 'none';
}

async function intakeKlijentSearch(q) {
  clearTimeout(_iSearchTimer);
  var res = document.getElementById('intake-klijent-results');
  if (!q || q.length < 2) { res.innerHTML = ''; return; }
  _iSearchTimer = setTimeout(async function() {
    try {
      var r = await fetch(BASE_URL + '/klijenti?pretraga=' + encodeURIComponent(q), {
        headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
      });
      var d = await r.json();
      var html = '';
      (d.klijenti || []).slice(0, 8).forEach(function(k) {
        var name = [k.ime, k.prezime, k.firma].filter(Boolean).join(' ');
        var sub  = k.email || k.telefon || k.tip || '';
        html += '<div class="intake-klijent-result' + (k.id === _iKlijentId ? ' selected' : '') + '"'
             +  ' onclick="intakeKlijentSelect(\'' + k.id + '\',\'' + (name.replace(/'/g,"&#39;")) + '\')">'
             +  '<div class="intake-klijent-name">' + name + '</div>'
             +  (sub ? '<div class="intake-klijent-sub">' + sub + '</div>' : '')
             +  '</div>';
      });
      if (!html && q.length > 1) html = '<div style="font-size:0.78rem;color:rgba(255,255,255,0.35);padding:8px 4px;">Nije pronađen klijent za "' + q + '"</div>';
      res.innerHTML = html;
    } catch(e) {}
  }, 300);
}

function intakeKlijentSelect(id, name) {
  _iKlijentId   = id;
  _iKlijentName = name;
  document.querySelectorAll('.intake-klijent-result').forEach(function(el){ el.classList.remove('selected'); });
  var sel = document.getElementById('intake-klijent-selected');
  sel.style.display = '';
  document.getElementById('intake-klijent-selected-name').textContent = name;
}

async function intakeUploadFile(file) {
  if (!file) return;
  var status = document.getElementById('intake-upload-status');
  status.textContent = 'Učitavam ' + file.name + '...';
  try {
    var fd = new FormData();
    fd.append('file', file);
    var r = await fetch(BASE_URL + '/api/dokument/upload', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + currentSession.access_token },
      body: fd
    });
    document.getElementById('intake-file-input').value = '';
    if (!r.ok) {
      var err = await r.json().catch(function(){ return {}; });
      status.textContent = 'Greška: ' + (err.detail || r.status);
      status.style.color = '#ff9090';
      return;
    }
    var d = await r.json();
    _iFiles.push({ name: file.name, sessionId: d.session_id, chunks: d.chunk_count });
    status.textContent = '';
    status.style.color = '';
    _intakeRenderFileList();
  } catch(e) {
    status.textContent = 'Greška pri uploadu.';
    status.style.color = '#ff9090';
  }
}

function intakeDropFile(e) {
  e.preventDefault();
  document.getElementById('intake-upload-zone').classList.remove('dragover');
  var file = e.dataTransfer.files && e.dataTransfer.files[0];
  if (file) intakeUploadFile(file);
}

function _intakeRenderFileList() {
  var html = '';
  _iFiles.forEach(function(f, i) {
    html += '<div class="intake-file-item">'
         +  '<span class="intake-file-name">📄 ' + f.name + ' <span style="color:rgba(255,255,255,0.3);font-size:0.7rem;">(' + f.chunks + ' segmenata)</span></span>'
         +  '<button class="intake-file-rm" onclick="intakeRemoveFile(' + i + ')">✕</button>'
         +  '</div>';
  });
  document.getElementById('intake-files-list').innerHTML = html;
}

function intakeRemoveFile(i) {
  _iFiles.splice(i, 1);
  _intakeRenderFileList();
}

async function _intakeRunEkstrakcija() {
  var opis = (document.getElementById('intake-opis').value || '').trim();
  var nextBtn = document.getElementById('intake-btn-next');
  nextBtn.disabled = true;
  document.getElementById('intake-ai-loading').style.display = 'block';
  document.getElementById('intake-ai-result').style.display = 'none';

  var body = { opis_problema: opis, analiza_results: null };

  if (_iFiles.length > 0) {
    try {
      var ar = await fetch(BASE_URL + '/api/dokument/analiza', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + currentSession.access_token },
        body: JSON.stringify({ session_id: _iFiles[0].sessionId, tekst: '', pitanje: '' })
      });
      if (ar.ok) {
        var ad = await ar.json();
        body.analiza_results = (ad.report && ad.report.findings) || [];
      }
    } catch(e) {}
  }

  try {
    var r = await fetch(BASE_URL + '/api/intake/ekstrakcija', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + currentSession.access_token },
      body: JSON.stringify(body)
    });
    if (!r.ok) { throw new Error('HTTP ' + r.status); }
    _iAnaliza = await r.json();
    _intakeShowAiResult(_iAnaliza);
    nextBtn.disabled = false;
  } catch(e) {
    document.getElementById('intake-ai-loading').innerHTML = '<div style="color:#ff9090;font-size:0.82rem;">Greška pri AI analizi. Kliknite "Dalje" da preskočite.</div>';
    _iAnaliza = { predlog_naziva_predmeta: '', vrsta_spora: '', protivna_strana: null, vrednost_spora: null, prvi_rok: null, rok_opis: null, potrebni_dokumenti: [] };
    nextBtn.disabled = false;
  }
}

function _intakeShowAiResult(a) {
  var html = '';
  var fields = [
    ['Predlog naziva', a.predlog_naziva_predmeta],
    ['Vrsta spora',    a.vrsta_spora],
    ['Protivna strana', a.protivna_strana],
    ['Vrednost spora',  a.vrednost_spora],
    ['Prvi rok',        a.prvi_rok],
  ];
  fields.forEach(function(f) {
    if (f[1]) {
      html += '<div class="intake-ai-card"><div class="intake-ai-card-label">' + f[0] + '</div>'
           +  '<div class="intake-ai-card-val">' + f[1] + '</div></div>';
    }
  });
  if (a.potrebni_dokumenti && a.potrebni_dokumenti.length) {
    html += '<div class="intake-ai-card"><div class="intake-ai-card-label">Preporučena dokumentacija</div>';
    a.potrebni_dokumenti.forEach(function(d){ html += '<div class="intake-ai-card-val" style="margin-top:3px;">• ' + d + '</div>'; });
    html += '</div>';
  }
  document.getElementById('intake-ai-loading').style.display = 'none';
  var el = document.getElementById('intake-ai-result');
  el.innerHTML = html || '<div style="color:rgba(255,255,255,0.4);font-size:0.82rem;">AI nije mogao da ekstrahuje podatke — ručno popunite polja u sledećem koraku.</div>';
  el.style.display = '';

  // Pre-fill step 5 fields
  document.getElementById('intake-f-naziv').value    = a.predlog_naziva_predmeta || '';
  document.getElementById('intake-f-opis').value     = (document.getElementById('intake-opis').value || '').trim();
  document.getElementById('intake-f-protivna').value = a.protivna_strana || '';
  document.getElementById('intake-f-vrsta').value    = a.vrsta_spora || '';
  document.getElementById('intake-f-vrednost').value = a.vrednost_spora || '';
  document.getElementById('intake-f-rok').value      = a.prvi_rok || '';
  document.getElementById('intake-f-rok-opis').value = a.rok_opis || '';

  var docsEl = document.getElementById('intake-potrebni-docs');
  var docsListEl = document.getElementById('intake-potrebni-docs-list');
  if (a.potrebni_dokumenti && a.potrebni_dokumenti.length) {
    docsListEl.innerHTML = a.potrebni_dokumenti.map(function(d){ return '<li>' + escHtml(d) + '</li>'; }).join('');
    docsEl.style.display = '';
  } else {
    docsEl.style.display = 'none';
  }
}

async function _intakeKreiraj() {
  var naziv = (document.getElementById('intake-f-naziv').value || '').trim();
  var errEl = document.getElementById('intake-kreiraj-err');
  errEl.style.display = 'none';
  if (!naziv) { errEl.textContent = 'Naziv predmeta je obavezan.'; errEl.style.display = 'block'; return; }
  if (!_iKlijentId) { errEl.textContent = 'Klijent nije izabran.'; errEl.style.display = 'block'; return; }

  var nextBtn = document.getElementById('intake-btn-next');
  nextBtn.disabled = true;
  nextBtn.textContent = 'Proveravam sukob interesa...';

  // --- Conflict of interest check before creating ---
  var _protivna = (document.getElementById('intake-f-protivna').value || '').trim();
  var _conflictWarningEl = document.getElementById('intake-conflict-warning');
  if (_conflictWarningEl) _conflictWarningEl.style.display = 'none';

  try {
    var _cfRes = await fetch(BASE_URL + '/api/intake/conflict-check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + currentSession.access_token },
      body: JSON.stringify({
        novi_klijent_ime:   _iKlijentName || 'Klijent',
        novi_klijent_firma: '',
        protivna_strana:    _protivna,
      })
    });
    if (_cfRes.ok) {
      var _cfData = await _cfRes.json();
      if (_cfData.conflict_detected) {
        var _cfSeverity = _cfData.has_blocker ? 'BLOKIRAJUCI' : 'UPOZORENJE';
        var _cfMsgs = (_cfData.conflicts || []).slice(0, 3).map(function(c){ return '• ' + _htmlEsc(c.opis); }).join('<br>');
        var _cfColor = _cfData.has_blocker ? 'rgba(255,80,80,0.15)' : 'rgba(255,180,0,0.12)';
        var _cfBorder = _cfData.has_blocker ? 'rgba(255,80,80,0.4)' : 'rgba(255,180,0,0.35)';
        var _cfTextColor = _cfData.has_blocker ? '#ff6b6b' : '#ffd166';
        var _cfIcon = _cfData.has_blocker ? '🚫' : '⚠️';
        if (_conflictWarningEl) {
          _conflictWarningEl.innerHTML = '<b>' + _cfIcon + ' Sukob interesa — ' + _cfSeverity + '</b><br>' + _cfMsgs + '<br><small style="opacity:0.8;">' + _htmlEsc(_cfData.preporuka) + '</small>';
          _conflictWarningEl.style.background = _cfColor;
          _conflictWarningEl.style.border = '1px solid ' + _cfBorder;
          _conflictWarningEl.style.color = _cfTextColor;
          _conflictWarningEl.style.display = 'block';
        }
        if (_cfData.has_blocker) {
          nextBtn.disabled = false;
          nextBtn.textContent = 'Kreiraj predmet';
          return;
        }
        // Warning only — give user 2s to see it, then proceed
        await new Promise(function(r){ setTimeout(r, 2000); });
      }
    }
  } catch(_cfe) { /* Conflict check failure is non-blocking */ }

  nextBtn.textContent = 'Kreiranje...';

  var rokVal = (document.getElementById('intake-f-rok').value || '').trim();
  var body = {
    klijent_id:      _iKlijentId,
    naziv:           naziv,
    opis:            (document.getElementById('intake-f-opis').value || '').trim(),
    tip:             document.getElementById('intake-f-tip').value || 'opsti',
    vrsta_spora:     (document.getElementById('intake-f-vrsta').value || '').trim(),
    vrednost_spora:  (document.getElementById('intake-f-vrednost').value || '').trim(),
    protivna_strana: (document.getElementById('intake-f-protivna').value || '').trim(),
    prvi_rok:        rokVal || null,
    rok_opis:        (document.getElementById('intake-f-rok-opis').value || '').trim() || null,
  };

  try {
    var r = await fetch(BASE_URL + '/api/intake/kreiraj', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + currentSession.access_token },
      body: JSON.stringify(body)
    });
    var d = await r.json();
    if (!r.ok) { errEl.textContent = d.detail || 'Greška pri kreiranju.'; errEl.style.display = 'block'; nextBtn.disabled = false; nextBtn.textContent = 'Kreiraj predmet'; return; }

    var newPredmetId = d.predmet_id;
    _intakePipelinePredmetId = newPredmetId;

    // Show pipeline loading state
    document.getElementById('intake-s5').style.display = 'none';
    document.getElementById('intake-panel-footer').style.display = 'none';
    document.getElementById('intake-pipeline-loading').style.display = 'flex';

    // Run pipeline
    var pr = null;
    try {
      var pRes = await fetch(BASE_URL + '/api/predmeti/' + newPredmetId + '/pipeline', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
      });
      if (pRes.ok) pr = await pRes.json();
    } catch(_e) { /* pipeline failed — still show completion */ }

    // Show result screen
    document.getElementById('intake-pipeline-loading').style.display = 'none';
    _intakeShowPipelineResult(pr);

    // Background: load predmeti list
    pred_load();
  } catch(e) {
    errEl.textContent = 'Greška veze.';
    errEl.style.display = 'block';
    nextBtn.disabled = false;
    nextBtn.textContent = 'Kreiraj predmet';
  }
}

var _intakePipelinePredmetId = null;

function _intakeShowPipelineResult(pr) {
  var screen = document.getElementById('intake-pipeline-result');
  var scoreNum = document.getElementById('pipeline-score-num');
  var scoreArc = document.getElementById('pipeline-score-arc');
  var scoreStatus = document.getElementById('pipeline-score-status');
  var checklistEl = document.getElementById('pipeline-checklist');
  var preporukaWrap = document.getElementById('pipeline-preporuka-wrap');
  var preporukaTxt = document.getElementById('pipeline-preporuka-txt');

  var score = pr ? (pr.case_ready_score || 0) : 0;
  var checklist = pr ? (pr.checklist || []) : [];
  var preporuka = pr ? (pr.copilot_preporuka || '') : '';

  // Animate score ring
  scoreNum.textContent = score + '%';
  var circumference = 251.2;
  scoreArc.style.strokeDashoffset = String(circumference - (circumference * score / 100));
  scoreArc.style.stroke = score >= 70 ? '#4aa8ff' : score >= 40 ? '#f0ad4e' : '#e05252';

  var statusMap = {70:'Predmet spreman za rad', 40:'Predmet delimično spreman', 0:'Predmet u pripremi'};
  var statusKey = score >= 70 ? 70 : score >= 40 ? 40 : 0;
  scoreStatus.textContent = 'Case Ready Score: ' + score + '% — ' + statusMap[statusKey];

  // Checklist
  checklistEl.innerHTML = checklist.map(function(item) {
    return '<div class="pipeline-check-item ' + (item.ok ? 'ok' : '') + '">'
      + '<span class="pipeline-check-icon">' + (item.ok ? '✓' : '□') + '</span>'
      + '<span>' + escHtml(item.stavka || '') + '</span>'
      + '</div>';
  }).join('');

  // Copilot preporuka
  if (preporuka) {
    preporukaTxt.textContent = preporuka;
    preporukaWrap.style.display = 'block';
  }

  screen.classList.add('active');
}

function intakePipelineDone() {
  intakeZatvori();
  var tabEl = document.querySelector('[onclick*="setTab"][onclick*="\'p\'"]');
  if (tabEl) setTab(tabEl, 'p');
  if (_intakePipelinePredmetId) pred_select(_intakePipelinePredmetId);
  _intakePipelinePredmetId = null;
}

// ── Zatvaranje predmeta ────────────────────────────────────────────────────

function pred_zatvoriOtvori() {
  document.getElementById('pred-zatvori-form').style.display = 'block';
  document.getElementById('pred-zatvori-trigger').style.display = 'none';
  document.getElementById('pred-zatvori-err').style.display = 'none';
  document.getElementById('pred-zatvori-ishod').value = '';
  document.getElementById('pred-zatvori-zakljucak').value = '';
}

function pred_zatvoriCancel() {
  document.getElementById('pred-zatvori-form').style.display = 'none';
  document.getElementById('pred-zatvori-trigger').style.display = 'block';
}

async function pred_zatvoriPredmet() {
  if (!activePredmetId || !currentSession) return;
  var ishod = document.getElementById('pred-zatvori-ishod').value;
  var errEl = document.getElementById('pred-zatvori-err');
  errEl.style.display = 'none';
  if (!ishod) { errEl.textContent = 'Izaberite ishod.'; errEl.style.display = 'block'; return; }

  var btn = document.getElementById('pred-zatvori-btn');
  btn.disabled = true;
  btn.textContent = 'Zatvaranje...';

  try {
    var r = await fetch(BASE_URL + '/api/predmeti/' + activePredmetId + '/zatvori', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + currentSession.access_token },
      body: JSON.stringify({
        ishod:     ishod,
        zakljucak: (document.getElementById('pred-zatvori-zakljucak').value || '').trim(),
      })
    });
    var d = await r.json();
    if (!r.ok) { errEl.textContent = d.detail || 'Greška.'; errEl.style.display = 'block'; btn.disabled = false; btn.textContent = 'Potvrdi zatvaranje'; return; }

    // Success — update UI
    document.getElementById('pred-zatvori-form').style.display = 'none';
    document.getElementById('pred-zatvori-trigger').style.display = 'none';
    var _dispEl = document.getElementById('pred-ishod-display');
    if (_dispEl) {
      _dispEl.innerHTML = '<div style="display:flex;align-items:center;gap:.5rem;">'
        + '<span style="font-size:.85rem;">✓</span>'
        + '<span style="font-size:.78rem;color:rgba(255,255,255,0.5);">Predmet zatvoren — Ishod: <b style="color:#4ade80;">' + _htmlEsc(d.ishod_label || ishod) + '</b></span>'
        + '</div>';
      _dispEl.style.display = 'block';
    }

    // Update list
    pred_load();
    var badge = document.getElementById('pred-detail-badge');
    if (badge) badge.textContent = 'zatvoren';

    // Outcome Intelligence feedback — pokreni u pozadini
    _outcome_feedback_show(activePredmetId);
  } catch(e) {
    errEl.textContent = 'Greška veze.';
    errEl.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'Potvrdi zatvaranje';
  }
}

function pred_zatvoriRenderSection(predmetData) {
  var section = document.getElementById('pred-zatvori-section');
  var trigger = document.getElementById('pred-zatvori-trigger');
  var dispEl  = document.getElementById('pred-ishod-display');
  if (!section) return;
  if (!predmetData) return;

  var status = predmetData.status;
  document.getElementById('pred-zatvori-form').style.display = 'none';

  if (status === 'zatvoren') {
    // Show ishod from opis
    if (dispEl) {
      var opis = predmetData.opis || '';
      var ishod_match = opis.match(/Ishod: ([^\n]+)/);
      var ishod_str = ishod_match ? ishod_match[1].trim() : 'Zatvoreno';
      dispEl.innerHTML = '<div style="display:flex;align-items:center;gap:.5rem;">'
        + '<span style="font-size:.85rem;">✓</span>'
        + '<span style="font-size:.78rem;color:rgba(255,255,255,0.5);">Predmet zatvoren — Ishod: <b style="color:#4ade80;">' + _htmlEsc(ishod_str) + '</b></span>'
        + '</div>';
      dispEl.style.display = 'block';
    }
    if (trigger) trigger.style.display = 'none';
  } else {
    if (dispEl) dispEl.style.display = 'none';
    if (trigger) trigger.style.display = 'block';
  }
}

/* OUTCOME INTELLIGENCE FEEDBACK — prikazuje se odmah posle zatvaranja predmeta */
async function _outcome_feedback_show(predmetId) {
  if (!predmetId || !currentSession) return;
  // Pokušaj da dohvati analizu — neće uvek imati dovoljno podataka
  try {
    var r = await fetch(BASE_URL + '/api/outcome-intel/predmeti/' + predmetId, {
      headers: { 'Authorization': 'Bearer ' + currentSession.access_token }
    });
    if (!r.ok) return;
    var d = await r.json();
    if (!d.analiza || d.ukupno_predmeta < 2) return; // nema dovoljno istorije

    // Prikaži modal sa analizom
    var winBadge = '';
    if (d.win_rate !== null && d.win_rate !== undefined) {
      var wc = d.win_rate >= 60 ? '#4ade80' : d.win_rate >= 40 ? '#facc15' : '#f87171';
      winBadge = '<span style="background:rgba(0,0,0,0.3);border:1px solid ' + wc + ';color:' + wc + ';border-radius:6px;padding:.15rem .5rem;font-size:.72rem;font-weight:700;margin-left:.5rem;">Win rate ' + d.win_rate + '%</span>';
    }
    var html = '<div style="position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:9999;display:flex;align-items:center;justify-content:center;padding:1rem;" onclick="if(event.target===this)this.remove()">'
      + '<div style="background:#0f1623;border:1px solid rgba(74,168,255,.25);border-radius:14px;padding:1.5rem;max-width:480px;width:100%;position:relative;">'
      + '<button onclick="this.closest(\'[style*=fixed]\').remove()" style="position:absolute;top:.75rem;right:.75rem;background:none;border:none;color:rgba(255,255,255,.4);font-size:1.1rem;cursor:pointer;line-height:1;">✕</button>'
      + '<div style="font-size:.68rem;letter-spacing:.1em;text-transform:uppercase;color:#89c8ff;margin-bottom:.4rem;">Outcome Intelligence</div>'
      + '<div style="font-size:1rem;font-weight:700;color:#fff;margin-bottom:.25rem;">Analiza kancelarije — tip: ' + _htmlEsc(d.tip) + winBadge + '</div>'
      + '<div style="font-size:.72rem;color:rgba(255,255,255,.4);margin-bottom:1rem;">'
        + (d.zatvoreni || 0) + ' zatvorenih predmeta · ' + (d.pobede || 0) + ' pobeda · ' + (d.porazi || 0) + ' poraza'
      + '</div>'
      + '<div style="font-size:.8rem;color:rgba(255,255,255,.8);white-space:pre-wrap;line-height:1.6;max-height:280px;overflow-y:auto;">' + _htmlEsc(d.analiza) + '</div>'
      + '</div>'
      + '</div>';

    var el = document.createElement('div');
    el.innerHTML = html;
    document.body.appendChild(el.firstElementChild);
  } catch(e) {}
}

function pred_rokokiToggle() {
  pred_rokokiOtvoriFormu(true);
}
function pred_rokokiOtvoriFormu(show) {
  var form = document.getElementById('pred-rokovi-form');
  var btn  = document.getElementById('pred-rokovi-toggle-btn');
  var err  = document.getElementById('pred-rokovi-err');
  if (!form) return;
  if (show) {
    form.style.display = 'block';
    if (btn) btn.style.display = 'none';
    if (err) err.style.display = 'none';
  } else {
    form.style.display = 'none';
    if (btn) btn.style.display = 'inline';
  }
}
async function pred_rokokiGeneriši(sacuvaj) {
  if (!currentSession) return;
  var tip   = document.getElementById('pred-rokovi-tip').value;
  var datum = document.getElementById('pred-rokovi-datum').value;
  var errEl = document.getElementById('pred-rokovi-err');
  var rezEl = document.getElementById('pred-rokovi-rezultat');
  if (!tip)   { if (errEl) { errEl.textContent = 'Izaberite procesni akt.'; errEl.style.display = 'block'; } return; }
  if (!datum) { if (errEl) { errEl.textContent = 'Unesite datum dostave.'; errEl.style.display = 'block'; } return; }
  if (errEl) errEl.style.display = 'none';
  var btn = document.getElementById('pred-rokovi-btn');
  if (btn) btn.disabled = true;
  try {
    var body = { tip_dogadjaja: tip, datum_pocetka: datum };
    if (sacuvaj && activePredmetId) body.predmet_id = activePredmetId;
    var r = await fetch('/api/rokovi/lanac', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + currentSession.access_token },
      body: JSON.stringify(body)
    });
    var d = await r.json().catch(function(){ return {}; });
    if (!r.ok) { if (errEl) { errEl.textContent = d.detail || 'Greška pri generisanju rokova.'; errEl.style.display = 'block'; } return; }
    pred_rokokiOtvoriFormu(false);
    if (rezEl) {
      var _vaznostColor = { kritican: '#ff9090', vazno: '#fbbf24', info: 'rgba(255,255,255,0.35)' };
      var _vaznostLabel = { kritican: 'KRITIČAN', vazno: 'VAŽNO', info: 'INFO' };
      var html = '<div style="font-size:.72rem;color:rgba(255,255,255,0.4);margin-bottom:.5rem;">'
        + _htmlEsc(d.tip_naziv) + ' · ' + _htmlEsc(d.datum_pocetka_display)
        + (d.sacuvano_u_predmet ? ' · <span style="color:#4ade80;">Sačuvano u hronologiji</span>' : '') + '</div>';
      html += '<div style="display:flex;flex-direction:column;gap:.4rem;">';
      (d.lanac || []).forEach(function(r) {
        var col = _vaznostColor[r.vaznost] || 'rgba(255,255,255,0.4)';
        var lbl = _vaznostLabel[r.vaznost] || r.vaznost;
        html += '<div style="display:flex;align-items:flex-start;gap:.6rem;padding:.4rem .5rem;background:rgba(255,255,255,0.03);border-radius:7px;border-left:2px solid ' + col + ';">'
          + '<div style="flex:1;min-width:0;">'
          + '<div style="font-size:.76rem;font-weight:600;color:rgba(255,255,255,0.85);">' + _htmlEsc(r.naziv) + '</div>'
          + '<div style="font-size:.7rem;color:rgba(255,255,255,0.35);">' + _htmlEsc(r.zakonski_osnov) + '</div>'
          + '</div>'
          + '<div style="text-align:right;flex-shrink:0;">'
          + '<div style="font-size:.78rem;font-weight:600;color:' + col + ';">' + _htmlEsc(r.datum_display) + '</div>'
          + '<div style="font-size:.67rem;color:' + col + ';opacity:.7;">' + lbl + '</div>'
          + '</div>'
          + '</div>';
      });
      html += '</div>';
      rezEl.innerHTML = html;
      rezEl.style.display = 'block';
    }
  } catch(e) {
    if (errEl) { errEl.textContent = 'Mrežna greška.'; errEl.style.display = 'block'; }
  } finally {
    if (btn) btn.disabled = false;
  }
}

function ugovor_openModal() {
  var m = document.getElementById('ugovor-modal');
  if (!m) return;
  m.style.display = 'flex';
  document.getElementById('uz-err').style.display = 'none';

  // Pre-fill advokat from firma settings
  var firma = {};
  try { firma = JSON.parse(localStorage.getItem('vindex_firma') || '{}'); } catch(e) {}
  var advokatEl = document.getElementById('uz-advokat-ime');
  var adresaEl  = document.getElementById('uz-advokat-adresa');
  if (advokatEl && !advokatEl.value && firma.naziv) advokatEl.value = firma.naziv;
  if (adresaEl  && !adresaEl.value  && firma.adresa) adresaEl.value = firma.adresa;

  // Pre-fill today's date if empty
  var datumEl = document.getElementById('uz-datum');
  if (datumEl && !datumEl.value) datumEl.value = new Date().toISOString().slice(0, 10);

  // Pre-fill predmet opis from active predmet name
  var opisEl = document.getElementById('uz-predmet-opis');
  if (opisEl && !opisEl.value && activePredmetNaziv) opisEl.value = activePredmetNaziv;

  // Pre-fill klijent fields from active predmet workspace snapshot
  var predFull = window._predFull;
  if (predFull && predFull.stranke && predFull.stranke.length > 0) {
    var k = predFull.stranke[0];
    var kImeEl   = document.getElementById('uz-klijent-ime');
    var kFirmaEl = document.getElementById('uz-klijent-firma');
    if (kImeEl && !kImeEl.value) {
      var fullName = ((k.ime || '') + ' ' + (k.prezime || '')).trim();
      if (fullName) kImeEl.value = fullName;
      else if (k.firma) kImeEl.value = k.firma;
    }
    if (kFirmaEl && !kFirmaEl.value && k.firma) kFirmaEl.value = k.firma;
  }
}
function ugovor_closeModal() {
  var m = document.getElementById('ugovor-modal');
  if (m) m.style.display = 'none';
  var rez = document.getElementById('ugovor-result-modal');
  if (rez) rez.style.display = 'none';
}
async function ugovor_generiši(sacuvaj) {
  if (!currentSession) return;
  var ime     = (document.getElementById('uz-klijent-ime').value || '').trim();
  var advokat = (document.getElementById('uz-advokat-ime').value || '').trim();
  var opis    = (document.getElementById('uz-predmet-opis').value || '').trim();
  var errEl   = document.getElementById('uz-err');
  if (!ime)     { errEl.textContent = 'Unesite ime klijenta.'; errEl.style.display = 'block'; return; }
  if (!advokat) { errEl.textContent = 'Unesite ime advokata.'; errEl.style.display = 'block'; return; }
  if (!opis || opis.length < 5) { errEl.textContent = 'Opis predmeta mora imati min. 5 znakova.'; errEl.style.display = 'block'; return; }
  errEl.style.display = 'none';
  var btn = document.getElementById('uz-btn');
  if (btn) btn.disabled = true;
  try {
    var body = {
      klijent_ime_prezime: ime,
      klijent_adresa: (document.getElementById('uz-klijent-adresa').value || '').trim(),
      klijent_firma:  (document.getElementById('uz-klijent-firma').value || '').trim(),
      advokat_ime:    advokat,
      advokat_adresa: (document.getElementById('uz-advokat-adresa').value || '').trim(),
      predmet_opis:   opis,
      oblast_prava:   document.getElementById('uz-oblast').value,
      nagrada_tip:    document.getElementById('uz-nagrada-tip').value,
      nagrada_iznos:  (document.getElementById('uz-nagrada-iznos').value || '').trim(),
      datum_zakljucenja: document.getElementById('uz-datum').value || null,
    };
    if (sacuvaj && activePredmetId) body.predmet_id = activePredmetId;
    var r = await fetch(BASE_URL + '/api/ugovor-zastupanja/generi%C5%A1i', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + currentSession.access_token },
      body: JSON.stringify(body)
    });
    var d = await r.json().catch(function(){ return {}; });
    if (!r.ok) { errEl.textContent = d.detail || 'Greška pri generisanju.'; errEl.style.display = 'block'; return; }
    ugovor_closeModal();
    ugovor_showResult(d);
    if (d.sacuvano_u_predmet) {
      var info = document.getElementById('pred-ugovor-poslednji');
      if (info) { info.textContent = 'Poslednji: Ugovor br. ' + d.broj + ' · ' + d.datum_zakljucenja + ' · Sačuvano u hronologiji'; info.style.display = 'block'; }
    }
  } catch(e) {
    errEl.textContent = 'Mrežna greška.'; errEl.style.display = 'block';
  } finally {
    if (btn) btn.disabled = false;
  }
}
function ugovor_showResult(d) {
  var existing = document.getElementById('ugovor-result-modal');
  if (existing) existing.remove();
  var overlay = document.createElement('div');
  overlay.id = 'ugovor-result-modal';
  overlay.style.cssText = 'position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,0.8);display:flex;align-items:center;justify-content:center;';
  overlay.onclick = function(e){ if(e.target===overlay) overlay.remove(); };
  overlay.innerHTML = '<div style="background:#0f172a;border:1px solid rgba(255,255,255,0.12);border-radius:14px;padding:1.5rem;width:92%;max-width:680px;max-height:88vh;overflow-y:auto;position:relative;">'
    + '<button onclick="document.getElementById(\'ugovor-result-modal\').remove()" style="position:absolute;top:.8rem;right:.8rem;background:none;border:none;color:rgba(255,255,255,0.4);font-size:1.1rem;cursor:pointer;">&#x2715;</button>'
    + '<div style="font-size:.85rem;font-weight:700;color:#00d4ff;margin-bottom:.3rem;">Ugovor br. ' + _htmlEsc(d.broj) + '</div>'
    + '<div style="font-size:.72rem;color:rgba(255,255,255,0.35);margin-bottom:.8rem;">'
    + d.datum_zakljucenja + (d.sacuvano_u_predmet ? ' · <span style="color:#4ade80;">Sačuvano u hronologiji</span>' : '') + '</div>'
    + '<pre style="white-space:pre-wrap;word-break:break-word;font-family:monospace;font-size:.72rem;line-height:1.55;color:rgba(255,255,255,0.75);background:rgba(0,0,0,0.3);padding:.8rem;border-radius:8px;border:1px solid rgba(255,255,255,0.07);">' + _htmlEsc(d.ugovor_tekst) + '</pre>'
    + '<div style="display:flex;gap:.5rem;margin-top:.8rem;">'
    + '<button onclick="ugovor_kopiraj()" style="flex:1;padding:.5rem;background:rgba(0,212,255,0.08);border:1px solid rgba(0,212,255,0.2);border-radius:8px;color:#00d4ff;font-size:.78rem;cursor:pointer;" id="uz-copy-btn">📋 Kopiraj tekst</button>'
    + '<button onclick="ugovor_stampaj()" style="flex:1;padding:.5rem;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:rgba(255,255,255,0.55);font-size:.78rem;cursor:pointer;">🖨 Štampaj / PDF</button>'
    + '</div>'
    + '</div>';
  document.body.appendChild(overlay);
  window._ugovorTekst = d.ugovor_tekst;
}
async function ugovor_kopiraj() {
  try {
    await navigator.clipboard.writeText(window._ugovorTekst || '');
    var b = document.getElementById('uz-copy-btn');
    if (b) { b.textContent = '✓ Kopirano!'; setTimeout(function(){ b.textContent = '📋 Kopiraj tekst'; }, 2000); }
  } catch(e) {}
}

function ugovor_stampaj() {
  var tekst = window._ugovorTekst || '';
  var w = window.open('', '_blank');
  if (!w) return;
  w.document.write('<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Ugovor o zastupanju</title>'
    + '<style>body{font-family:"Courier New",monospace;font-size:11pt;line-height:1.6;padding:2.5cm;max-width:800px;margin:0 auto;color:#111;}pre{white-space:pre-wrap;word-break:break-word;}@media print{body{padding:1.5cm;}button{display:none!important;}}</style>'
    + '</head><body><button onclick="window.print()" style="position:fixed;top:1rem;right:1rem;padding:.5rem 1rem;background:#333;color:#fff;border:none;border-radius:5px;cursor:pointer;">Štampaj / PDF</button>'
    + '<pre>' + tekst.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</pre>'
    + '</body></html>');
  w.document.close();
  setTimeout(function(){ w.print(); }, 400);
}
