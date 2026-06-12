# VINDEX 100Q TEST

Datum: 2026-06-04 | Cache: BYPASS

---

## Q1. Koja je kazna za osnovnu krađu?

**Pouzdanost:** HIGH | **Score:** 0.6547 | **Vreme:** 24.0s

**Meta:** `KZ` | `Član 210`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik (KZ) ima prednost za krivična dela.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za kaznu za sitnu krađu prema Krivičnom zakoniku, član 210, stav 1, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: krivična. Podnosilac mora dokazat
```

**Eval:** ✅ — HIGH: tačan član 203 citiran

---

## Q2. Koja je kazna za tešku krađu?

**Pouzdanost:** HIGH | **Score:** 0.6618 | **Vreme:** 19.3s

**Meta:** `KZ` | `Član 379`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik (KZ) ima prednost za krivična dela, uključujući tešku krađu.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za kaznu zatvora od jedne do osam godina za tešku krađu prema KZ čl. 204, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: kr
```

**Eval:** ✅ — HIGH: tačan član 204 citiran

---

## Q3. Šta je razbojništvo i koja je kazna?

**Pouzdanost:** MEDIUM | **Score:** 0.5987 | **Vreme:** 15.5s

**Meta:** `KZ` | `Član 294`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik (KZ) ima prednost za krivična dela, uključujući razbojništvo.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za krivično delo razbojništva prema Krivičnom zakoniku čl. 206, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: krivična. P
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 294 | očekivano: Član 206

---

## Q4. Šta je razbojnička krađa?

**Pouzdanost:** HIGH | **Score:** 0.7052 | **Vreme:** 19.1s

**Meta:** `KZ` | `Član 302`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik (KZ) ima prednost za krivična dela.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za krivično delo razbojničke krađe prema Krivičnom zakoniku, član 206, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: krivična. Podnosilac mora doka
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 302 citiran=['206', '206', '206'] očekivano=Član 205

---

## Q5. Koja je kazna za prevaru?

**Pouzdanost:** HIGH | **Score:** 0.6502 | **Vreme:** 15.8s

**Meta:** `KZ` | `Član 210`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik (KZ) ima prednost za krivična dela prevare.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za krivično gonjenje za prevaru prema KZ čl. 208, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: krivična. Podnosilac mora dokazati nameru d
```

**Eval:** ✅ — HIGH: tačan član 208 citiran

---

## Q6. Šta je pronevera i koja je kazna?

**Pouzdanost:** LOW | **Score:** 0.6362 | **Vreme:** 18.1s

**Meta:** `zakonik o krivicnom postupku` | `Član 512`

**Response:**

```
[!] STATUSNA POTVRDA: Opšta pravna logika — nema direktnog člana u bazi za ovo pitanje.  
  
--- HIJERARHIJA IZVORA  
Sistem nije mogao da verifikuje navedene pravne reference u dostupnoj bazi zakona RS.  
  
--- PRAVNI ZAKLJUČAK  
Odgovor je blokiran jer su detektovane pravne reference koje nisu potkrepljene direktnim citatom iz indeksiranih zakona. Vindex AI primenjuje politiku nultog tolerancija na neprove
```

**Eval:** ✅ — LOW: pouzdan odmah odbio (score=0.636)

---

## Q7. Koja je kazna za utaju poreza?

**Pouzdanost:** MEDIUM | **Score:** 0.6344 | **Vreme:** 21.3s

**Meta:** `zakonik o krivicnom postupku` | `Član 143`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik ima prednost za krivična dela utaje poreza.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za kaznu zatvora i novčanu kaznu za utaju poreza prema Krivičnom zakoniku čl. 226, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: krivična. 
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 143 | očekivano: Član 229

---

## Q8. Šta je iznuda i koja je kazna?

**Pouzdanost:** MEDIUM | **Score:** 0.6080 | **Vreme:** 19.9s

**Meta:** `KZ` | `Član 134`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik (KZ) ima prednost za krivična dela kao što je iznuda.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za krivično delo iznude prema Krivičnom zakoniku čl. 214, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: krivična. Podnosilac mora
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 134 | očekivano: Član 214

---

## Q9. Koja je kazna za falsifikovanje isprave?

**Pouzdanost:** HIGH | **Score:** 0.7070 | **Vreme:** 19.3s

**Meta:** `KZ` | `Član 355`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik (KZ) ima prednost za krivična dela.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za kaznu zatvora do tri godine za falsifikovanje isprave prema Krivičnom zakoniku, član 355, stav 1. Ako je delo učinjeno u pogledu javne isprave ili sli
```

**Eval:** ✅ — HIGH: tačan član 355 citiran

---

## Q10. Šta je zelenaštvo?

**Pouzdanost:** HIGH | **Score:** 0.6962 | **Vreme:** 13.6s

**Meta:** `zakon o obligacionim odnosima` | `Član 788`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Poseban propis: ZOO — matični zakon za obligacione odnose.  
  
--- PRAVNI ZAKLJUČAK  
Zelenaštvo je definisano kao ništav ugovor kojim neko koristi stanje nužde ili teškog materijalnog stanja druge strane da ugovori korist koja je u očiglednoj nesrazmeri sa onim što je dao ili
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 788 citiran=['141', '141', '141'] očekivano=Član 216

---

## Q11. Koja je kazna za neovlašćeno korišćenje tuđeg vozila?

**Pouzdanost:** HIGH | **Score:** 0.7427 | **Vreme:** 20.6s

**Meta:** `KZ` | `Član 213`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik (KZ) ima prednost za krivična dela.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za izricanje kazne za neovlašćeno korišćenje tuđeg vozila prema Krivičnom zakoniku, član 213. Učiniocu se može izreći novčana kazna ili kazna zatvora do 
```

**Eval:** ✅ — HIGH: tačan član 213 citiran

---

## Q12. Koja je kazna za uništenje tuđe imovine?

**Pouzdanost:** HIGH | **Score:** 0.6964 | **Vreme:** 19.4s

**Meta:** `KZ` | `Član 212`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik (KZ) ima prednost za krivična dela uništenja imovine.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za krivično gonjenje za uništenje tuđe imovine prema KZ čl. 212. U zavisnosti od visine štete, kazna može biti novčana ili zatvorska do
```

**Eval:** ✅ — HIGH: tačan član 212 citiran

---

## Q13. Šta je pranje novca?

**Pouzdanost:** MEDIUM | **Score:** 0.5924 | **Vreme:** 25.4s

**Meta:** `zakon o sprecavanju pranja novca i finansiranja terorizma` | `Član 2`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o sprečavanju pranja novca i finansiranja terorizma ima prednost za definisanje pranja novca.  
  
--- PRAVNI ZAKLJUČAK  
Pranje novca, prema Zakonu o sprečavanju pranja novca i finansiranja terorizma, obuhvata konverziju ili prenos imovine stečene izvršenjem
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 2 | očekivano: Član 231

---

## Q14. Koja je kazna za utaju?

**Pouzdanost:** MEDIUM | **Score:** 0.6091 | **Vreme:** 18.6s

**Meta:** `KZ` | `Član 210`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik ima prednost za krivična dela utaje.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za kaznu za utaju prema Krivičnom zakoniku čl. 226, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: krivična. Podnosilac mora dokazati nameru da izb
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 210 | očekivano: Član 210

---

## Q15. Šta je sitna krađa?

**Pouzdanost:** HIGH | **Score:** 0.6912 | **Vreme:** 14.8s

**Meta:** `KZ` | `Član 210`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik (KZ) ima prednost za krivična dela, uključujući sitnu krađu.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za gonjenje za sitnu krađu prema Krivičnom zakoniku, član 210, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: krivična. Pod
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 210 citiran=['210', '210'] očekivano=Član 203

---

## Q16. Koja je kazna za vožnju u pijanom stanju?

**Pouzdanost:** MEDIUM | **Score:** 0.6029 | **Vreme:** 19.0s

**Meta:** `zakonik o krivicnom postupku` | `Član 512`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik (KZ) ima prednost nad ZOO za krivična dela.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za izricanje kazne za vožnju u pijanom stanju prema Krivičnom zakoniku, čl. 53 i čl. 295. Kazna može uključivati zatvor, novčanu kaznu, rad u jav
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 512 | očekivano: Član 289

---

## Q17. Koja je kazna za tešku telesnu povredu?

**Pouzdanost:** MEDIUM | **Score:** 0.6367 | **Vreme:** 16.5s

**Meta:** `KZ` | `Član 323`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik ima prednost za krivična dela nad ZOO.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za kaznu zatvora za tešku telesnu povredu prema Krivičnom zakoniku, član 121, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: krivična. Podnosilac
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 323 | očekivano: Član 122

---

## Q18. Šta je krivično delo nasilja u porodici?

**Pouzdanost:** HIGH | **Score:** 0.6736 | **Vreme:** 16.1s

**Meta:** `KZ` | `Član 194`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik ima prednost za krivična dela nasilja u porodici.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za krivično delo nasilja u porodici prema Krivičnom zakoniku čl. 194, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: krivična. Podnosi
```

**Eval:** ✅ — HIGH: tačan član 194 citiran

---

## Q19. Koja je kazna za nedozvoljeno držanje oružja?

**Pouzdanost:** HIGH | **Score:** 0.6726 | **Vreme:** 21.3s

**Meta:** `KZ` | `Član 348`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik (KZ) je primarni zakon za krivična dela vezana za oružje.  
  
--- PRAVNI ZAKLJUČAK  
Entitet: Fizičko lice | Jurisdikcija: Republika Srbija | Ekstrateritorijalnost: N/A  
Visoka verovatnoća obaveze prema KZ čl. 348, st. 1. za nedozvoljeno držanje or
```

**Eval:** ✅ — HIGH: tačan član 348 citiran

---

## Q20. Šta je krivično delo primanja mita?

**Pouzdanost:** MEDIUM | **Score:** 0.6008 | **Vreme:** 17.7s

**Meta:** `KZ` | `Član 366`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik (KZ) ima prednost za krivična dela, uključujući primanje mita.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za krivično delo primanja mita prema Krivičnom zakoniku, čl. 366, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: krivična
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 366 | očekivano: Član 367

---

## Q21. Koja je kazna za davanje lažnog iskaza?

**Pouzdanost:** MEDIUM | **Score:** 0.6419 | **Vreme:** 17.2s

**Meta:** `KZ` | `Član 336`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik (KZ) ima prednost za krivična dela, uključujući davanje lažnog iskaza.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za kaznu zatvora za davanje lažnog iskaza prema Krivičnom zakoniku, član 335. U zavisnosti od konteksta, kazna može bi
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 336 | očekivano: Član 335

---

## Q22. Šta je krivično delo uznemiravanja?

**Pouzdanost:** MEDIUM | **Score:** 0.6455 | **Vreme:** 15.4s

**Meta:** `KZ` | `Član 182a`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik (KZ) ima prednost za krivična dela.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za gonjenje za krivično delo polnog uznemiravanja prema Krivičnom zakoniku, član 182a. Vrsta odgovornosti: krivična. Podnosilac mora dokazati da je ponaš
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 182a | očekivano: Član 138

---

## Q23. Koja je kazna za trgovinu ljudima?

**Pouzdanost:** HIGH | **Score:** 0.6699 | **Vreme:** 18.7s

**Meta:** `KZ` | `Član 388`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik (KZ) ima prednost za krivična dela trgovine ljudima.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za kaznu zatvora za trgovinu ljudima prema Krivičnom zakoniku čl. 388, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: krivična. Pod
```

**Eval:** ✅ — HIGH: tačan član 388 citiran

---

## Q24. Šta je nužna odbrana?

**Pouzdanost:** HIGH | **Score:** 0.6667 | **Vreme:** 16.0s

**Meta:** `KZ` | `Član 19`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Krivični zakonik (KZ) ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Nužna odbrana je odbrana koja je neophodno potrebna da se odbije istovremen protivpravan napad na svoje ili tuđe dobro.  
  
--- PRAVNA DEFINICIJA  
Nužna odbrana je definisana u Krivičnom zako
```

**Eval:** ✅ — HIGH: tačan član 19 citiran

---

## Q25. Koja je kazna za zapuštanje deteta?

**Pouzdanost:** MEDIUM | **Score:** 0.6133 | **Vreme:** 16.3s

**Meta:** `porodicni zakon` | `Član 81`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Porodični zakon ima prednost nad ZOO za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za lišenje roditeljskog prava zbog zapuštanja deteta prema Porodičnom zakonu, član 81. Roditelj može biti potpuno lišen roditeljskog prava ako grubo zanem
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 81 | očekivano: Član 193

---

## Q26. Koji je opšti rok zastarelosti po ZOO?

**Pouzdanost:** HIGH | **Score:** 0.7477 | **Vreme:** 16.9s

**Meta:** `zakon o obligacionim odnosima` | `Član 379`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Poseban propis: Zakon o obligacionim odnosima — matični zakon za obligacione odnose.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za primenu opšteg roka zastarelosti od deset godina prema članu 371 ZOO, uz uslov da nije određen neki drugi rok zastarelosti za konkret
```

**Eval:** ✅ — HIGH: tačan član 371 citiran

---

## Q27. Šta je ugovorna odgovornost za štetu?

**Pouzdanost:** HIGH | **Score:** 0.7625 | **Vreme:** 16.5s

**Meta:** `zakon o obligacionim odnosima` | `Član 263`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Poseban propis: Zakon o obligacionim odnosima — matični zakon za ugovorne odnose.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za naknadu štete zbog neispunjenja ugovorne obaveze prema Zakonu o obligacionim odnosima, čl. 262, uz ispunjenje zakonskih uslova. Vrsta od
```

**Eval:** ✅ — HIGH: tačan član 262 citiran

---

## Q28. Kada nastaje pravo na raskid ugovora?

**Pouzdanost:** HIGH | **Score:** 0.6905 | **Vreme:** 14.1s

**Meta:** `zakon o obligacionim odnosima` | `Član 811`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Poseban propis: ZOO — matični zakon za obligacione odnose.  
  
--- PRAVNI ZAKLJUČAK  
Pravo na raskid ugovora nastaje kada jedna strana ne ispuni svoju obavezu, a druga strana može zahtevati ispunjenje ili raskinuti ugovor pod uslovima predviđenim zakonom.  
  
--- PRAVNA DEFINICI
```

**Eval:** ✅ — HIGH: tačan član 124 citiran

---

## Q29. Šta je viša sila u obligacionom pravu?

**Pouzdanost:** MEDIUM | **Score:** 0.5931 | **Vreme:** 18.1s

**Meta:** `zakon o obligacionim odnosima` | `Član 145`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Poseban propis: ZOO — matični zakon za obligacione odnose.  
  
--- PRAVNI ZAKLJUČAK  
Viša sila u obligacionom pravu odnosi se na događaje koji čine ispunjenje obaveze nemogućim, a za koje nijedna strana nije odgovorna.  
  
--- PRAVNA DEFINICIJA  
Viša sila u obligacionom pravu je 
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 145 | očekivano: Član 263

---

## Q30. Koja je kamata za docnju?

**Pouzdanost:** MEDIUM | **Score:** 0.5943 | **Vreme:** 14.8s

**Meta:** `zakon o obligacionim odnosima` | `Član 399`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Poseban propis: ZOO — matični zakon za obligacione odnose.  
  
--- PRAVNI ZAKLJUČAK  
Kamata za docnju je zatezna kamata po stopi utvrđenoj saveznim zakonom.  
  
--- PRAVNA DEFINICIJA  
Zatezna kamata je kamata koju dužnik duguje pored glavnice kada zadocni sa ispunjenjem novčane o
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 399 | očekivano: Član 277

---

## Q31. Kada se može tražiti poništaj ugovora zbog prevare?

**Pouzdanost:** HIGH | **Score:** 0.6662 | **Vreme:** 13.5s

**Meta:** `zakon o obligacionim odnosima` | `Član 61`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Poseban propis: ZOO — matični zakon za obligacione odnose.  
  
--- PRAVNI ZAKLJUČAK  
Poništaj ugovora zbog prevare može se tražiti kada jedna strana izazove zabludu kod druge strane ili je održava u zabludi u nameri da je time navede na zaključenje ugovora, čak i kada zabluda
```

**Eval:** ✅ — HIGH: tačan član 65 citiran

---

## Q32. Šta je cesija i kako se vrši?

**Pouzdanost:** HIGH | **Score:** 0.6533 | **Vreme:** 12.6s

**Meta:** `zakon o obligacionim odnosima` | `Član 436`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Poseban propis: ZOO — matični zakon za obligacione odnose.  
  
--- PRAVNI ZAKLJUČAK  
Cesija je prenos potraživanja sa poverioca na treće lice putem ugovora, bez potrebe za pristankom dužnika, ali uz obavezu obaveštavanja dužnika o ustupanju.  
  
--- PRAVNA DEFINICIJA  
Cesija, pre
```

**Eval:** ✅ — HIGH: tačan član 436 citiran

---

## Q33. Koja su prava kupca kod materijalnih nedostataka?

**Pouzdanost:** HIGH | **Score:** 0.7086 | **Vreme:** 14.8s

**Meta:** `zakon o obligacionim odnosima` | `Član 486`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Poseban propis: ZOO — matični zakon za obligacione odnose.  
  
--- PRAVNI ZAKLJUČAK  
Kupac ima pravo na naknadu štete, sniženje cene, raskid ugovora i druge pravne lekove u slučaju materijalnih nedostataka.  
  
--- PRAVNA DEFINICIJA  
Prava kupca kod materijalnih nedostataka uključu
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 486 citiran=['486', '486'] očekivano=Član 488

---

## Q34. Šta je prekomerno oštećenje?

**Pouzdanost:** HIGH | **Score:** 0.7313 | **Vreme:** 17.8s

**Meta:** `zakon o obligacionim odnosima` | `Član 191`

**Response:**

```
[!] STATUSNA POTVRDA: STATUSNA POTVRDA: Opšta pravna logika — nema direktnog člana u bazi za ovo pitanje.  
  
--- HIJERARHIJA IZVORA  
Poseban propis: ZOO — matični zakon za obligacione odnose.  
  
--- PRAVNI ZAKLJUČAK  
Pojam nije direktno definisan u dostavljenim izvorima — videti PRAVNI OSNOV.  
  
--- PRAVNA DEFINICIJA  
Prekomerno oštećenje nije eksplicitno definisano u Zakonu o obligacionim odnosima. U kont
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 191 citiran=['156'] očekivano=Član 139

---

## Q35. Kada nastaje obaveza naknade štete?

**Pouzdanost:** HIGH | **Score:** 0.7155 | **Vreme:** 17.5s

**Meta:** `zakon o obligacionim odnosima` | `Član 186`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Poseban propis: Zakon o obligacionim odnosima — matični zakon za naknadu štete.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za naknadu štete prema Zakonu o obligacionim odnosima, čl. 186, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: vanugovorna. Podnosilac m
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 186 citiran=['186', '186'] očekivano=Član 154

---

## Q36. Šta je solidarna odgovornost?

**Pouzdanost:** MEDIUM | **Score:** 0.6207 | **Vreme:** 15.9s

**Meta:** `zakon o obligacionim odnosima` | `Član 166`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Poseban propis: Zakon o obligacionim odnosima — matični zakon za obligacione odnose.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za solidarnu odgovornost prema Zakonu o obligacionim odnosima, čl. 206, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: vanugovorna.
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 166 | očekivano: Član 414

---

## Q37. Koji je rok zastarelosti za naknadu štete?

**Pouzdanost:** HIGH | **Score:** 0.7858 | **Vreme:** 18.0s

**Meta:** `zakon o obligacionim odnosima` | `Član 376`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Poseban propis: Zakon o obligacionim odnosima — matični zakon za naknadu štete.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za potraživanje naknade štete prema Zakonu o obligacionim odnosima čl. 376, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: vanugovorna. 
```

**Eval:** ✅ — HIGH: tačan član 376 citiran

---

## Q38. Šta je ugovor o zakupu?

**Pouzdanost:** HIGH | **Score:** 0.6850 | **Vreme:** 12.9s

**Meta:** `zakon o obligacionim odnosima` | `Član 567`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Poseban propis: ZOO — matični zakon za obligacione odnose.  
  
--- PRAVNI ZAKLJUČAK  
Ugovor o zakupu je ugovor kojim se zakupodavac obavezuje da preda određenu stvar zakupcu na upotrebu, a zakupac se obavezuje da plaća određenu zakupninu.  
  
--- PRAVNA DEFINICIJA  
Ugovor o zakupu 
```

**Eval:** ✅ — HIGH: tačan član 567 citiran

---

## Q39. Kada se može tražiti vraćanje datog bez osnova?

**Pouzdanost:** MEDIUM | **Score:** 0.6374 | **Vreme:** 18.0s

**Meta:** `zakon o obligacionim odnosima` | `Član 214`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Poseban propis: ZOO — matični zakon za obligacione odnose.  
  
--- PRAVNI ZAKLJUČAK  
Vraćanje datog bez osnova može se tražiti kada je imovina jednog lica prešla na drugo lice bez pravnog osnova.  
  
--- PRAVNA DEFINICIJA  
Prema Zakonu o obligacionim odnosima, vraćanje datog bez 
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 214 | očekivano: Član 210

---

## Q40. Šta je ugovor o jemstvu?

**Pouzdanost:** HIGH | **Score:** 0.7160 | **Vreme:** 14.0s

**Meta:** `zakon o obligacionim odnosima` | `Član 997`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Poseban propis: Zakon o obligacionim odnosima — matični zakon za ugovorne odnose.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za zaključenje ugovora o jemstvu prema Zakonu o obligacionim odnosima čl. 997, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: ugovorna
```

**Eval:** ✅ — HIGH: tačan član 997 citiran

---

## Q41. Koji je maksimalni otkazni rok po Zakonu o radu?

**Pouzdanost:** MEDIUM | **Score:** 0.6327 | **Vreme:** 20.5s

**Meta:** `zakon o radu` | `Član 189`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost nad ZOO za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za otkazni rok do 30 dana prema Zakonu o radu, član 189, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: ugovorna. Podnosilac mora dokazati da je otkazni
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 189 | očekivano: Član 189

---

## Q42. Kada poslodavac može dati otkaz bez otkaznog roka?

**Pouzdanost:** MEDIUM | **Score:** 0.6402 | **Vreme:** 18.4s

**Meta:** `zakon o radu` | `Član 184`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost nad ZOO za oblast radnih odnosa.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za otkaz bez otkaznog roka ako zaposleni učini povredu radne obaveze ili ne poštuje radnu disciplinu prema Zakonu o radu čl. 179. Poslodavac mora d
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 184 | očekivano: Član 179

---

## Q43. Koliko dana godišnjeg odmora ima zaposleni?

**Pouzdanost:** MEDIUM | **Score:** 0.6908 | **Vreme:** 21.7s

**Meta:** `zakon o radu` | `Član 69`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Zaposleni ima pravo na godišnji odmor od najmanje 20 radnih dana godišnje, uz mogućnost uvećanja po osnovu različitih kriterijuma.  
  
--- PRAVNA DEFINICIJA  
Prema Zakonu o radu, član 69, zaposleni im
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 69 | očekivano: Član 68

---

## Q44. Šta je mobbing i kako se dokazuje?

**Pouzdanost:** LOW | **Score:** 0.5684 | **Vreme:** 17.8s

**Meta:** `zakon o sprecavanju pranja novca i finansiranja terorizma` | `Član 93`

**Response:**

```
[!] STATUSNA POTVRDA: Opšta pravna logika — nema direktnog člana u bazi za ovo pitanje.  
  
--- HIJERARHIJA IZVORA  
Sistem nije mogao da verifikuje navedene pravne reference u dostupnoj bazi zakona RS.  
  
--- PRAVNI ZAKLJUČAK  
Odgovor je blokiran jer su detektovane pravne reference koje nisu potkrepljene direktnim citatom iz indeksiranih zakona. Vindex AI primenjuje politiku nultog tolerancija na neprove
```

**Eval:** ✅ — LOW: pouzdan odmah odbio (score=0.568)

---

## Q45. Koja je maksimalna dužina radnog vremena?

**Pouzdanost:** MEDIUM | **Score:** 0.6287 | **Vreme:** 13.3s

**Meta:** `zakon o radu` | `Član 53`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Maksimalna dužina radnog vremena, uključujući prekovremeni rad, ne može biti duža od 60 časova nedeljno u slučaju preraspodele radnog vremena.  
  
--- PRAVNA DEFINICIJA  
Prema Zakonu o radu, puno radn
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 53 | očekivano: Član 50

---

## Q46. Kada se isplaćuje otpremnina?

**Pouzdanost:** HIGH | **Score:** 0.6698 | **Vreme:** 16.5s

**Meta:** `zakon o radu` | `Član 158`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Otpremnina se isplaćuje pre otkaza ugovora o radu.  
  
--- PRAVNA DEFINICIJA  
Otpremnina se isplaćuje zaposlenom pre otkaza ugovora o radu, u skladu sa članom 158 Zakona o radu. Visina otpremnine se u
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 158 citiran=['158', '158'] očekivano=Član 119

---

## Q47. Šta su prava zaposlene žene za vreme trudnoće?

**Pouzdanost:** HIGH | **Score:** 0.6862 | **Vreme:** 13.4s

**Meta:** `zakon o radu` | `Član 12`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Zaposlena žena ima pravo na posebnu zaštitu za vreme trudnoće, uključujući zabranu otkaza, pravo na porodiljsko odsustvo i plaćeno odsustvo za zdravstvene preglede.  
  
--- PRAVNA DEFINICIJA  
Zaposlen
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 12 citiran=['12'] očekivano=Član 94

---

## Q48. Koji je rok za sudsku zaštitu kod nezakonitog otkaza?

**Pouzdanost:** MEDIUM | **Score:** 0.6591 | **Vreme:** 27.9s

**Meta:** `zakon o radu` | `Član 195`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost nad ZOO za oblast radnih odnosa.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za pokretanje spora zbog nezakonitog otkaza prema Zakonu o radu, član 195, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: radni spor. Zaposlen
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 195 | očekivano: Član 195

---

## Q49. Šta je zabrana konkurencije?

**Pouzdanost:** HIGH | **Score:** 0.6929 | **Vreme:** 17.9s

**Meta:** `zakon o radu` | `Član 161`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost nad ZOO za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za utvrđivanje zabrane konkurencije prema Zakonu o radu čl. 161, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: ugovorna. Podnosilac mora dokazati posto
```

**Eval:** ✅ — HIGH: tačan član 161 citiran

---

## Q50. Kada poslodavac može uvesti prekovremeni rad?

**Pouzdanost:** HIGH | **Score:** 0.6521 | **Vreme:** 17.5s

**Meta:** `zakon o radu` | `Član 57`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Poslodavac može uvesti prekovremeni rad u slučaju više sile, iznenadnog povećanja obima posla i kada je neophodno da se u određenom roku završi posao koji nije planiran.  
  
--- PRAVNA DEFINICIJA  
P
```

**Eval:** ✅ — HIGH: tačan član 53 citiran

---

## Q51. Koja su prava zaposlenog kod povrede na radu?

**Pouzdanost:** HIGH | **Score:** 0.6605 | **Vreme:** 17.2s

**Meta:** `zakon o radu` | `Član 164`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Zaposleni ima pravo na naknadu štete zbog povrede na radu, koju je poslodavac dužan da isplati u skladu sa zakonom i opštim aktom.  
  
--- PRAVNA DEFINICIJA  
Zakon o radu propisuje da zaposleni koji
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 164 citiran=['164', '164'] očekivano=Član 33

---

## Q52. Koji su razlozi za otkaz ugovora o radu?

**Pouzdanost:** MEDIUM | **Score:** 0.6713 | **Vreme:** 29.4s

**Meta:** `zakon o radu` | `Član 179`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost nad ZOO za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za otkaz ugovora o radu prema Zakonu o radu čl. 179, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: radnopravna. Poslodavac mora dokazati postojanje opr
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 179 | očekivano: Član 179

---

## Q53. Šta je minimalac i kako se određuje?

**Pouzdanost:** HIGH | **Score:** 0.6562 | **Vreme:** 14.6s

**Meta:** `zakon o radu` | `Član 111`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Minimalna zarada je zakonski utvrđena najniža zarada koju poslodavac mora isplatiti zaposlenom za standardni učinak i vreme provedeno na radu.  
  
--- PRAVNA DEFINICIJA  
Minimalna zarada se određuje n
```

**Eval:** ✅ — HIGH: tačan član 112 citiran

---

## Q54. Koja su prava zaposlenog na bolovanju?

**Pouzdanost:** MEDIUM | **Score:** 0.6013 | **Vreme:** 15.0s

**Meta:** `zakon o radu` | `Član 183`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Zaposleni na bolovanju ima pravo na naknadu zarade i dužan je da poslodavcu dostavi potvrdu o privremenoj sprečenosti za rad.  
  
--- PRAVNA DEFINICIJA  
Zaposleni koji je privremeno sprečen za rad z
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 183 | očekivano: Član 77

---

## Q55. Kada se može tražiti vraćanje na posao?

**Pouzdanost:** MEDIUM | **Score:** 0.6051 | **Vreme:** 15.5s

**Meta:** `zakon o radu` | `Član 191`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Zaposleni može tražiti vraćanje na posao ako sud utvrdi da je prestanak radnog odnosa bio bez pravnog osnova.  
  
--- PRAVNA DEFINICIJA  
Prema članu 191 Zakona o radu, zaposleni može tražiti vraćanj
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 191 | očekivano: Član 191

---

## Q56. Šta je kolektivni ugovor?

**Pouzdanost:** MEDIUM | **Score:** 0.5304 | **Vreme:** 22.9s

**Meta:** `zakon o obligacionim odnosima` | `Član 103`

**Response:**

```
[!] STATUSNA POTVRDA: STATUSNA POTVRDA: Opšta pravna logika — nema direktnog člana u bazi za ovo pitanje.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Pojam nije direktno definisan u dostavljenim izvorima — videti PRAVNI OSNOV.  
  
--- PRAVNA DEFINICIJA  
Kolektivni ugovor je pravni akt kojim se uređuju prava, obaveze i odgovornosti iz radnog odn
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 103 | očekivano: Član 253

---

## Q57. Koja su prava sindikalnog predstavnika?

**Pouzdanost:** HIGH | **Score:** 0.6795 | **Vreme:** 13.0s

**Meta:** `zakon o radu` | `Član 239`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Prava sindikalnog predstavnika uključuju pravo na kolektivno pregovaranje, zaštitu od otkaza zbog sindikalnog delovanja i učešće u radu tripartitnih tela.  
  
--- PRAVNA DEFINICIJA  
Sindikalni preds
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 239 citiran=['239'] očekivano=Član 188

---

## Q58. Šta je probni rad i koliko traje?

**Pouzdanost:** MEDIUM | **Score:** 0.6098 | **Vreme:** 14.8s

**Meta:** `zakon o radu` | `Član 36`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Probni rad je period tokom kojeg se procenjuju radne i stručne sposobnosti zaposlenog, a može trajati najduže šest meseci.  
  
--- PRAVNA DEFINICIJA  
Probni rad je period koji se može ugovoriti ugovor
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 36 | očekivano: Član 36

---

## Q59. Kada zaposleni ima pravo na jubilarnu nagradu?

**Pouzdanost:** MEDIUM | **Score:** 0.6238 | **Vreme:** 13.7s

**Meta:** `zakon o radu` | `Član 120`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Pojam nije direktno definisan u dostavljenim izvorima — videti PRAVNI OSNOV.  
  
--- PRAVNA DEFINICIJA  
Pravo na jubilarnu nagradu može biti utvrđeno opštim aktom ili ugovorom o radu, prema članu 12
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 120 | očekivano: Član 118

---

## Q60. Šta je disciplinska odgovornost zaposlenog?

**Pouzdanost:** MEDIUM | **Score:** 0.6171 | **Vreme:** 18.6s

**Meta:** `zakon o radu` | `Član 169`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost nad ZOO za oblast radnih odnosa.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za disciplinsku odgovornost zaposlenog prema Zakonu o radu, čl. 179, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: disciplinska. Zaposleni 
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 169 | očekivano: Član 179

---

## Q61. Koji su zakonski naslednici prvog naslednog reda?

**Pouzdanost:** HIGH | **Score:** 0.6662 | **Vreme:** 13.1s

**Meta:** `zakon o nasledjivanju` | `Član 8`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o nasledjivanju ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Prvi nasledni red čine ostaviočevi potomci i njegov bračni drug.  
  
--- PRAVNA DEFINICIJA  
Prvi nasledni red prema Zakonu o nasledjivanju čine ostaviočevi potomci i njegov bračni drug. Ostav
```

**Eval:** ✅ — HIGH: tačan član 9 citiran

---

## Q62. Šta je nužni deo u naslednom pravu?

**Pouzdanost:** HIGH | **Score:** 0.6784 | **Vreme:** 16.6s

**Meta:** `zakon o nasledjivanju` | `Član 40`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o nasleđivanju ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Nužni deo je deo zaostavštine kojim ostavilac nije mogao raspolagati i koji pripada nužnim naslednicima.  
  
--- PRAVNA DEFINICIJA  
Nužni deo je zakonom zaštićeni deo zaostavštine koji pripada
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 40 citiran=['40', '40'] očekivano=Član 39

---

## Q63. Kada se može poništiti testament?

**Pouzdanost:** HIGH | **Score:** 0.6804 | **Vreme:** 14.1s

**Meta:** `zakon o vanparnicnom postupku` | `Član 109`

**Response:**

```
[!] STATUSNA POTVRDA: STATUSNA POTVRDA: Opšta pravna logika — nema direktnog člana u bazi za ovo pitanje.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o nasleđivanju ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Pojam nije direktno definisan u dostavljenim izvorima — videti PRAVNI OSNOV.  
  
--- PRAVNA DEFINICIJA  
Poništaj testamenta može se tražiti ako testament nije sačinjen u skladu sa zakonom,
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 109 citiran=[] očekivano=Član 80

---

## Q64. Šta je zajednička imovina supružnika?

**Pouzdanost:** HIGH | **Score:** 0.7126 | **Vreme:** 13.0s

**Meta:** `porodicni zakon` | `Član 171`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Porodični zakon ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Zajednička imovina supružnika je imovina koju su supružnici stekli radom tokom trajanja zajednice života u braku.  
  
--- PRAVNA DEFINICIJA  
Zajednička imovina supružnika, prema Porodičnom zakonu, 
```

**Eval:** ✅ — HIGH: tačan član 171 citiran

---

## Q65. Kada se može tražiti razvod braka?

**Pouzdanost:** MEDIUM | **Score:** 0.6358 | **Vreme:** 12.4s

**Meta:** `porodicni zakon` | `Član 41`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Porodični zakon ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Razvod braka može se tražiti ako su bračni odnosi ozbiljno i trajno poremećeni ili ako se zajednica života supružnika objektivno ne može ostvarivati.  
  
--- PRAVNA DEFINICIJA  
Prema Porodičnom zak
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 41 | očekivano: Član 41

---

## Q66. Koja su prava deteta nakon razvoda?

**Pouzdanost:** MEDIUM | **Score:** 0.5678 | **Vreme:** 13.0s

**Meta:** `porodicni zakon` | `Član 65`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Porodični zakon ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Prava deteta nakon razvoda uključuju pravo na život sa roditeljima, pravo na održavanje ličnih odnosa sa roditeljem sa kojim ne živi, pravo na izražavanje mišljenja i pravo na izdržavanje.  
  
---
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 65 | očekivano: Član 61

---

## Q67. Šta je alimentacija i kako se određuje?

**Pouzdanost:** MEDIUM | **Score:** 0.5590 | **Vreme:** 17.4s

**Meta:** `porodicni zakon` | `Član 160`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Porodični zakon ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Alimentacija se određuje prema potrebama poverioca i mogućnostima dužnika, uzimajući u obzir minimalnu sumu izdržavanja.  
  
--- PRAVNA DEFINICIJA  
Alimentacija, ili izdržavanje, prema Porodičnom
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 160 | očekivano: Član 160

---

## Q68. Ko može biti staratelj?

**Pouzdanost:** HIGH | **Score:** 0.6668 | **Vreme:** 12.5s

**Meta:** `porodicni zakon` | `Član 126`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Porodični zakon ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Staratelj može biti lice koje ima potrebna lična svojstva i sposobnosti, a pristalo je da bude staratelj, prvenstveno supružnik, srodnik ili hranitelj štićenika, osim ako interes štićenika nala
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 126 citiran=['126', '126'] očekivano=Član 127

---

## Q69. Šta je posvojenje i koji su uslovi?

**Pouzdanost:** HIGH | **Score:** 0.6613 | **Vreme:** 13.8s

**Meta:** `porodicni zakon` | `Član 312`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Porodični zakon ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Posvojenje je pravni institut kojim se zasniva odnos roditeljstva između usvojitelja i usvojenika, a uslovi su definisani Porodičnim zakonom.  
  
--- PRAVNA DEFINICIJA  
Posvojenje je pravni institu
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 312 citiran=['312'] očekivano=Član 89

---

## Q70. Koji je rok za prihvatanje nasleđa?

**Pouzdanost:** HIGH | **Score:** 0.6635 | **Vreme:** 11.8s

**Meta:** `zakon o nasledjivanju` | `Član 209`

**Response:**

```
[!] STATUSNA POTVRDA: STATUSNA POTVRDA: Opšta pravna logika — nema direktnog člana u bazi za ovo pitanje.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o nasledjivanju ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Pojam nije direktno definisan u dostavljenim izvorima — videti PRAVNI OSNOV.  
  
--- PRAVNA DEFINICIJA  
Zakon o nasledjivanju ne sadrži eksplicitnu odredbu o roku za prihvatanje nasleđa. 
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 209 citiran=['209'] očekivano=Član 213

---

## Q71. Šta je odricanje od nasleđa?

**Pouzdanost:** HIGH | **Score:** 0.6591 | **Vreme:** 13.6s

**Meta:** `zakon o nasledjivanju` | `Član 214`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o nasledjivanju ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Odricanje od nasleđa je izjava naslednika da se odriče prava na nasleđe, koja je neopoziva i ne može biti delimična.  
  
--- PRAVNA DEFINICIJA  
Odricanje od nasleđa je pravni institut kojim n
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 214 citiran=['214'] očekivano=Član 216

---

## Q72. Kada dete može tražiti izdržavanje od roditelja?

**Pouzdanost:** HIGH | **Score:** 0.6913 | **Vreme:** 14.0s

**Meta:** `porodicni zakon` | `Član 155`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Porodični zakon ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Dete može tražiti izdržavanje od roditelja ako je punoletno i nesposobno za rad ili se redovno školuje, a najkasnije do 26. godine života.  
  
--- PRAVNA DEFINICIJA  
Prema Porodičnom zakonu, punole
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 155 citiran=['155', '155'] očekivano=Član 154

---

## Q73. Šta je bračni ugovor?

**Pouzdanost:** LOW | **Score:** 0.4983 | **Vreme:** 9.6s

**Meta:** `zakon o obligacionim odnosima` | `Član 141`

**Response:**

```
Nemam pouzdan odgovor na ovo pitanje u trenutnoj bazi zakona.  
  
Mogući razlozi: pitanje izlazi iz indeksiranih oblasti, ili specifičnost pitanja zahteva ekspertski sud.  
  
Preporučujem konsultaciju sa advokatom specijalistom.  
  
---  
📊 Pouzdanost: NISKA | Score: 0.498  
  
---  
  
⚠️ **Pravna napomena:** Vindex AI pruža informacije zasnovane na zakonskim tekstovima Republike Srbije i ne predstavlja pravni save
```

**Eval:** ✅ — LOW: pouzdan odmah odbio (score=0.498)

---

## Q74. Kako se deli zajednička imovina pri razvodu?

**Pouzdanost:** MEDIUM | **Score:** 0.6491 | **Vreme:** 17.1s

**Meta:** `porodicni zakon` | `Član 171`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Porodični zakon ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Zajednička imovina supružnika se deli prema pretpostavci o jednakim udelima, osim ako sud ne utvrdi drugačije na osnovu doprinosa svakog supružnika.  
  
--- PRAVNA DEFINICIJA  
Zajednička imovina su
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 171 | očekivano: Član 177

---

## Q75. Šta je pravo preče kupovine između suvlasnika?

**Pouzdanost:** HIGH | **Score:** 0.7121 | **Vreme:** 12.8s

**Meta:** `zakon o obligacionim odnosima` | `Član 527`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o obligacionim odnosima ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Pravo preče kupovine između suvlasnika omogućava suvlasnicima da kupe deo nepokretnosti pre nego što se proda trećem licu, pod istim uslovima.  
  
--- PRAVNA DEFINICIJA  
Pravo preče
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 527 citiran=['533', '533', '533'] očekivano=Član 194

---

## Q76. Koji su osnivački akti DOO?

**Pouzdanost:** HIGH | **Score:** 0.6563 | **Vreme:** 15.4s

**Meta:** `zakon o privrednim drustvima` | `Član 11`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o privrednim društvima ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Osnivački akt DOO je konstitutivni akt društva koji može biti odluka o osnivanju ili ugovor o osnivanju, zavisno od broja osnivača.  
  
--- PRAVNA DEFINICIJA  
Osnivački akt društva sa 
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 11 citiran=['11', '11'] očekivano=Član 139

---

## Q77. Šta je odgovornost direktora DOO?

**Pouzdanost:** MEDIUM | **Score:** 0.6353 | **Vreme:** 19.7s

**Meta:** `zakon o privrednim drustvima` | `Član 415`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o privrednim društvima ima prednost nad ZOO za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za odgovornost direktora prema Zakonu o privrednim društvima, član 415, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: vanugovorna. Podn
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 415 | očekivano: Član 61

---

## Q78. Šta je postupak likvidacije DOO?

**Pouzdanost:** MEDIUM | **Score:** 0.6104 | **Vreme:** 18.9s

**Meta:** `zakon o privrednim drustvima` | `Član 596`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o privrednim društvima ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Postupak likvidacije društva sa ograničenom odgovornošću (DOO) je proces kojim se društvo zatvara i briše iz registra privrednih subjekata nakon izmirenja svih obaveza prema pove
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 596 | očekivano: Član 524

---

## Q79. Koja su prava manjinskih akcionara?

**Pouzdanost:** MEDIUM | **Score:** 0.6463 | **Vreme:** 12.3s

**Meta:** `zakon o privrednim drustvima` | `Član 376`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o privrednim društvima ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Prava manjinskih akcionara uključuju pravo na pobijanje odluka skupštine, pravo na otkup akcija i pravo na učešće u radu skupštine.  
  
--- PRAVNA DEFINICIJA  
Prava manjinskih akcionar
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 376 | očekivano: Član 276

---

## Q80. Šta je stečajni postupak?

**Pouzdanost:** MEDIUM | **Score:** 0.5423 | **Vreme:** 18.7s

**Meta:** `zakon o opstem upravnom postupku` | `Član 100`

**Response:**

```
[~] STATUSNA POTVRDA: [~] STATUSNA POTVRDA: Parafrazirano na osnovu člana [X] — sistem prilagođava tekst.  
  
--- HIJERARHIJA IZVORA  
Opšti principi: primenjena opšta građanskopravna načela — nije identifikovan poseban zakon.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za pokretanje stečajnog postupka prema Zakonu o stečaju, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: vanugovorna. Pod
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 100 | očekivano: Član 1

---

## Q81. Kada se otvara stečaj?

**Pouzdanost:** LOW | **Score:** 0.5914 | **Vreme:** 19.6s

**Meta:** `zakon o privrednim drustvima` | `Član 539`

**Response:**

```
[!] STATUSNA POTVRDA: Opšta pravna logika — nema direktnog člana u bazi za ovo pitanje.  
  
--- HIJERARHIJA IZVORA  
Sistem nije mogao da verifikuje navedene pravne reference u dostupnoj bazi zakona RS.  
  
--- PRAVNI ZAKLJUČAK  
Odgovor je blokiran jer su detektovane pravne reference koje nisu potkrepljene direktnim citatom iz indeksiranih zakona. Vindex AI primenjuje politiku nultog tolerancija na neprove
```

**Eval:** ✅ — LOW: pouzdan odmah odbio (score=0.591)

---

## Q82. Šta su razlučni poverioci?

**Pouzdanost:** LOW | **Score:** 0.5408 | **Vreme:** 16.8s

**Meta:** `zakon o digitalnoj imovini` | `Član 103`

**Response:**

```
[!] STATUSNA POTVRDA: Opšta pravna logika — nema direktnog člana u bazi za ovo pitanje.  
  
--- HIJERARHIJA IZVORA  
Sistem nije mogao da verifikuje navedene pravne reference u dostupnoj bazi zakona RS.  
  
--- PRAVNI ZAKLJUČAK  
Odgovor je blokiran jer su detektovane pravne reference koje nisu potkrepljene direktnim citatom iz indeksiranih zakona. Vindex AI primenjuje politiku nultog tolerancija na neprove
```

**Eval:** ✅ — LOW: pouzdan odmah odbio (score=0.541)

---

## Q83. Koja je odgovornost osnivača DOO?

**Pouzdanost:** MEDIUM | **Score:** 0.6134 | **Vreme:** 16.8s

**Meta:** `zakon o privrednim drustvima` | `Član 85`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o privrednim društvima ima prednost nad ZOO za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za odgovornost osnivača DOO prema Zakonu o privrednim društvima, čl. 46, uz ispunjenje zakonskih uslova. Osnivači odgovaraju za obaveze prema
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 85 | očekivano: Član 18

---

## Q84. Šta je preduzetnik i koja je njegova odgovornost?

**Pouzdanost:** HIGH | **Score:** 0.6500 | **Vreme:** 26.7s

**Meta:** `zakon o zastiti potrosaca` | `Član 5`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o privrednim društvima ima prednost nad ZOO za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za odgovornost preduzetnika za obaveze nastale u vezi sa obavljanjem delatnosti prema Zakonu o privrednim društvima, čl. 85. Preduzetnik odgo
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 5 citiran=['85'] očekivano=Član 83

---

## Q85. Kada nastaje obaveza revizije finansijskih izveštaja?

**Pouzdanost:** MEDIUM | **Score:** 0.6409 | **Vreme:** 18.6s

**Meta:** `zakon o privrednim drustvima` | `Član 453`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o privrednim društvima ima prednost nad ZOO za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za obavezu revizije finansijskih izveštaja javnih akcionarskih društava prema Zakonu o privrednim društvima, član 453. Obaveza revizije nasta
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 453 | očekivano: Član 369

---

## Q86. Koji je opšti rok za žalbu?

**Pouzdanost:** HIGH | **Score:** 0.7051 | **Vreme:** 13.0s

**Meta:** `zakon o opstem upravnom postupku` | `Član 153`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakonik o krivičnom postupku ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Opšti rok za žalbu protiv presude donete u prvom stepenu je 15 dana od dana dostavljanja prepisa presude, osim ako zakonom nije drugačije propisano.  
  
--- PRAVNA DEFINICIJA  
Opšti ro
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 153 citiran=['367', '432', '432'] očekivano=Član 373

---

## Q87. Kada nastaje pravosnažnost presude?

**Pouzdanost:** HIGH | **Score:** 0.6884 | **Vreme:** 15.5s

**Meta:** `zakonik o krivicnom postupku` | `Član 275`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakonik o krivičnom postupku ima prednost za pitanja pravnosnažnosti presude u krivičnim postupcima.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za utvrđivanje pravnosnažnosti presude kada se više ne može pobijati žalbom ili kada žalba nije dozvoljen
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 275 citiran=['275', '275', '367'] očekivano=Član 364

---

## Q88. Šta je vanredna revizija?

**Pouzdanost:** MEDIUM | **Score:** 0.5838 | **Vreme:** 16.0s

**Meta:** `zakon o privrednim drustvima` | `Član 455`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o privrednim društvima ima prednost nad ZOO za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za sprovođenje vanredne revizije finansijskih izveštaja prema Zakonu o privrednim društvima, član 455, uz ispunjenje zakonskih uslova. Vanugo
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 455 | očekivano: Član 404

---

## Q89. Koji su uslovi za određivanje privremene mere?

**Pouzdanost:** HIGH | **Score:** 0.6920 | **Vreme:** 17.6s

**Meta:** `zakon o parnicnom postupku` | `Član 439`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o izvršenju i obezbeđenju ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Uslovi za određivanje privremene mere uključuju verovatnoću postojanja potraživanja i opasnost po potraživanje, uz mogućnost polaganja jemstva.  
  
--- PRAVNA DEFINICIJA  
Privreme
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 439 citiran=['449', '449'] očekivano=Član 435

---

## Q90. Šta je predlog za ponavljanje postupka?

**Pouzdanost:** HIGH | **Score:** 0.6947 | **Vreme:** 17.1s

**Meta:** `zakon o parnicnom postupku` | `Član 434`

**Response:**

```
[!] STATUSNA POTVRDA: STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o parničnom postupku ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Predlog za ponavljanje postupka je pravni lek kojim stranka traži ponovno vođenje postupka zbog novih okolnosti ili dokaza.  
  
--- PRAVNA DEFINICIJA  
Predlog za ponavljanje postupka podno
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 434 citiran=['429', '429'] očekivano=Član 426

---

## Q91. Ko snosi troškove parničnog postupka?

**Pouzdanost:** HIGH | **Score:** 0.6861 | **Vreme:** 19.1s

**Meta:** `zakon o parnicnom postupku` | `Član 167`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o parničnom postupku ima prednost nad ZOO za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov da stranka koja izgubi parnicu snosi troškove postupka prema Zakonu o parničnom postupku, član 153. Stranka koja u celini izgubi parnicu dužna 
```

**Eval:** ✅ — HIGH: tačan član 153 citiran

---

## Q92. Šta je tužba za utvrđenje?

**Pouzdanost:** HIGH | **Score:** 0.6806 | **Vreme:** 20.4s

**Meta:** `zakon o parnicnom postupku` | `Član 194`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Poseban propis: Zakon o parničnom postupku — matični zakon za parnične postupke.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za podnošenje tužbe za utvrđenje prema Zakonu o parničnom postupku, član 194, uz ispunjenje zakonskih uslova. Vrsta odgovornosti: vanugovorn
```

**Eval:** ✅ — HIGH: tačan član 194 citiran

---

## Q93. Kada se može tražiti obezbeđenje dokaza?

**Pouzdanost:** MEDIUM | **Score:** 0.5826 | **Vreme:** 14.0s

**Meta:** `zakon o izvrsenju i obezbedjenju` | `Član 415`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o izvršenju i obezbeđenju ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Obezbeđenje dokaza može se tražiti kada postoje zakonski razlozi za obezbeđenje i kada su činjenice i dokazi verovatni.  
  
--- PRAVNA DEFINICIJA  
Postupak obezbeđenja dokaza pokreć
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 415 | očekivano: Član 274

---

## Q94. Šta je izvršna isprava?

**Pouzdanost:** MEDIUM | **Score:** 0.5674 | **Vreme:** 14.4s

**Meta:** `zakon o izvrsenju i obezbedjenju` | `Član 40`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o izvršenju i obezbeđenju ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Izvršna isprava je dokument na osnovu kojeg se može doneti rešenje o izvršenju, pod uslovom da sadrži sve potrebne podatke o poveriocu, dužniku i obavezi.  
  
--- PRAVNA DEFINICI
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 40 | očekivano: Član 23

---

## Q95. Šta je litispendencija?

**Pouzdanost:** MEDIUM | **Score:** 0.6279 | **Vreme:** 17.1s

**Meta:** `zakon o parnicnom postupku` | `Član 432`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o parničnom postupku ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Litispendencija je situacija kada se vodi više postupaka o istom zahtevu među istim strankama, što je zabranjeno.  
  
--- PRAVNA DEFINICIJA  
Litispendencija je pravni institut koji spreč
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 432 | očekivano: Član 298

---

## Q96. Koja je maksimalna dužina zabrane konkurencije?

**Pouzdanost:** MEDIUM | **Score:** 0.6424 | **Vreme:** 17.5s

**Meta:** `zakon o radu` | `Član 162`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost nad ZOO za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za ugovaranje zabrane konkurencije u trajanju do dve godine po prestanku radnog odnosa prema Zakonu o radu, član 162, uz ispunjenje zakonskih uslova. Vrsta o
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 162 | očekivano: Član 161

---

## Q97. Kada zaposleni može da radi kod konkurenta?

**Pouzdanost:** MEDIUM | **Score:** 0.6909 | **Vreme:** 23.0s

**Meta:** `zakon o radu` | `Član 161`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Zaposleni može da radi kod konkurenta samo ako nije ugovorena zabrana konkurencije ili ako poslodavac da pismenu saglasnost.  
  
--- PRAVNA DEFINICIJA  
Zabrana konkurencije je klauzula u ugovoru o r
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 161 | očekivano: Član 161

---

## Q98. Šta je nelojalna konkurencija?

**Pouzdanost:** HIGH | **Score:** 0.6543 | **Vreme:** 21.2s

**Meta:** `zakon o radu` | `Član 257`

**Response:**

```
[!] STATUSNA POTVRDA: Opšta pravna logika — nema direktnog člana u bazi za ovo pitanje.  
  
--- HIJERARHIJA IZVORA  
Opšti principi: primenjena opšta građanskopravna načela — nije identifikovan poseban zakon.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za utvrđivanje nelojalne konkurencije prema opštim načelima zaštite konkurencije. Vrsta odgovornosti: vanugovorna. Podnosilac mora dokazati pos
```

**Eval:** ❌ — HIGH + POGREŠAN ČLAN: meta=Član 257 citiran=['21'] očekivano=Član 1

---

## Q99. Koja je naknada za zabranu konkurencije?

**Pouzdanost:** HIGH | **Score:** 0.6676 | **Vreme:** 16.9s

**Meta:** `zakon o radu` | `Član 161`

**Response:**

```
[✓] STATUSNA POTVRDA: ✓ STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o radu ima prednost nad ZOO za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Postoji verovatan pravni osnov za zahtev za naknadu štete zbog povrede zabrane konkurencije prema Zakonu o radu, član 161. Poslodavac može zahtevati naknadu štete ako zaposleni prekrši zab
```

**Eval:** ✅ — HIGH: tačan član 161 citiran

---

## Q100. Šta je poslovna tajna?

**Pouzdanost:** MEDIUM | **Score:** 0.6286 | **Vreme:** 13.7s

**Meta:** `KZ` | `Član 337`

**Response:**

```
[✓] STATUSNA POTVRDA: [✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.  
  
--- HIJERARHIJA IZVORA  
Lex specialis: Zakon o privrednim društvima ima prednost za ovu oblast.  
  
--- PRAVNI ZAKLJUČAK  
Poslovna tajna je podatak koji može naneti štetu društvu ako se saopšti trećem licu, ima ekonomsku vrednost jer nije opšte poznat, i zaštićen je merama tajnosti.  
  
--- PRAVNA DEFI
```

**Eval:** ⚠️ — MEDIUM: hedged | meta-član: Član 337 | očekivano: Član 51

---

# SUMMARY

**Ukupno:** 100 | ✅ 31 | ⚠️ 44 | ❌ 25

**Uspešnost:** 31.0%

**Halucinacije:** 25 ❌

## Po kategorijama

| Kategorija | ✅ | ⚠️ | ❌ |
|---|---|---|---|
| Krivično pravo — imovinski delikti | 7 | 5 | 3 |
| Krivično pravo — ostalo | 4 | 6 | 0 |
| Obligaciono pravo (ZOO) | 8 | 4 | 3 |
| Radno pravo | 4 | 12 | 4 |
| Porodično pravo i nasleđivanje | 3 | 4 | 8 |
| Privredno pravo | 2 | 6 | 2 |
| Procesno pravo (ZPP) | 2 | 4 | 4 |
| Zabrana konkurencije | 1 | 3 | 1 |
