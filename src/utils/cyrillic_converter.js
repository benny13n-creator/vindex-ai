// Srpska ćirilica — Vukova azbuka
// NAPOMENA: ovaj fajl nije direktno seriran — kod je inline u index.html
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

  function _applyEnum(text){
    // (x) — slovo u zagradi
    text=text.replace(/\(([a-zA-Z])\)/g,function(m,ch){
      var r=_enumCyr(ch); return r?'('+r+')':m;
    });
    // x. ili x) na početku reda ili posle novog reda
    text=text.replace(/(^|\n)([ \t]*)([a-zA-Z])([.)]) /g,function(m,nl,sp,ch,punct){
      var r=_enumCyr(ch); return r?nl+sp+r+punct+' ':m;
    });
    return text;
  }

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

  function cirilicaElement(el){if(el) _walkNode(el);}

  function pretvoriUCirilicu(tekst){
    if(!tekst||typeof tekst!=='string') return tekst;
    var d=document.createElement('div');
    d.innerHTML=tekst;
    _walkNode(d);
    return d.innerHTML;
  }

  global.pretvoriUCirilicu=pretvoriUCirilicu;
  global.cirilicaElement=cirilicaElement;
})(typeof window!=='undefined'?window:this);
