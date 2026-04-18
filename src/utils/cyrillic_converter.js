// Srpska ćirilica — Vukova azbuka
(function(global) {
  'use strict';

  // Dvoznaci moraju biti pre jednoznaka
  var MAP = [
    ['lj', '\u0459'], ['Lj', '\u0409'], ['LJ', '\u0409'],
    ['nj', '\u045a'], ['Nj', '\u040a'], ['NJ', '\u040a'],
    ['\u0064\u017e', '\u045f'], ['\u0044\u017e', '\u040f'], ['\u0044\u017d', '\u040f'],
    // Jednoznaci
    ['a', '\u0430'], ['A', '\u0410'],
    ['b', '\u0431'], ['B', '\u0411'],
    ['v', '\u0432'], ['V', '\u0412'],
    ['g', '\u0433'], ['G', '\u0413'],
    ['d', '\u0434'], ['D', '\u0414'],
    ['\u0111', '\u0452'], ['\u0110', '\u0402'],
    ['e', '\u0435'], ['E', '\u0415'],
    ['\u017e', '\u0436'], ['\u017d', '\u0416'],
    ['z', '\u0437'], ['Z', '\u0417'],
    ['i', '\u0438'], ['I', '\u0418'],
    ['j', '\u0458'], ['J', '\u0408'],
    ['k', '\u043a'], ['K', '\u041a'],
    ['l', '\u043b'], ['L', '\u041b'],
    ['m', '\u043c'], ['M', '\u041c'],
    ['n', '\u043d'], ['N', '\u041d'],
    ['o', '\u043e'], ['O', '\u041e'],
    ['p', '\u043f'], ['P', '\u041f'],
    ['r', '\u0440'], ['R', '\u0420'],
    ['s', '\u0441'], ['S', '\u0421'],
    ['t', '\u0442'], ['T', '\u0422'],
    ['\u0107', '\u045b'], ['\u0106', '\u040b'],
    ['\u010d', '\u0447'], ['\u010c', '\u0427'],
    ['\u0161', '\u0448'], ['\u0160', '\u0428'],
    ['u', '\u0443'], ['U', '\u0423'],
    ['f', '\u0444'], ['F', '\u0424'],
    ['h', '\u0445'], ['H', '\u0425'],
    ['c', '\u0446'], ['C', '\u0426'],
  ];

  // Konvertuje jednu "čistu" reč/frazu bez HTML/Markdown
  function _convertSegment(text) {
    var result = text;
    for (var i = 0; i < MAP.length; i++) {
      result = result.split(MAP[i][0]).join(MAP[i][1]);
    }
    return result;
  }

  /**
   * pretvoriUCirilicu(tekst) — konvertuje latinicu u srpsku ćirilicu.
   * Preskače:
   *   - HTML tagove  (<...>)
   *   - Markdown linkove — URL deo  ([tekst](url)) → konvertuje samo 'tekst'
   *   - Kodne blokove  (``` ... ```)
   *   - Inline kod  (`...`)
   */
  function pretvoriUCirilicu(tekst) {
    if (!tekst || typeof tekst !== 'string') return tekst;

    // Tokenizujemo tekst: svaki token je ili "zaštićen" (ne konvertuje se) ili "slobodan"
    var tokens = [];
    var remaining = tekst;

    // Regex koji hvata sve zaštićene segmente u prioritetnom redosledu:
    // 1. Fenced code block  ```...```
    // 2. Inline code  `...`
    // 3. Markdown link  [tekst](url)  — hvata ceo obrazac
    // 4. HTML tag  <...>
    var PROTECTED = /(```[\s\S]*?```|`[^`]*`|\[[^\]]*\]\([^)]*\)|<[^>]+>)/g;
    var lastIndex = 0;
    var match;

    PROTECTED.lastIndex = 0;
    while ((match = PROTECTED.exec(remaining)) !== null) {
      // Slobodan segment pre match-a
      if (match.index > lastIndex) {
        tokens.push({ protect: false, text: remaining.slice(lastIndex, match.index) });
      }
      // Zaštićeni segment
      var full = match[0];
      // Markdown link: konvertuj samo tekst deo [tekst](url)
      if (full[0] === '[') {
        var inner = full.match(/^\[([^\]]*)\]\(([^)]*)\)$/);
        if (inner) {
          tokens.push({ protect: false, text: '[' });
          tokens.push({ protect: false, text: inner[1] });   // tekst — konvertuje se
          tokens.push({ protect: true,  text: '](' + inner[2] + ')' }); // url — ne konvertuje se
        } else {
          tokens.push({ protect: true, text: full });
        }
      } else {
        tokens.push({ protect: true, text: full });
      }
      lastIndex = match.index + full.length;
    }
    // Ostatak posle poslednjeg match-a
    if (lastIndex < remaining.length) {
      tokens.push({ protect: false, text: remaining.slice(lastIndex) });
    }

    return tokens.map(function(t) {
      return t.protect ? t.text : _convertSegment(t.text);
    }).join('');
  }

  global.pretvoriUCirilicu = pretvoriUCirilicu;

})(typeof window !== 'undefined' ? window : this);
