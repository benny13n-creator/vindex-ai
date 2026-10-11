# RH001 — rezime za foundera

**Ukratko:** NS006 je spreman za vašu odluku o spajanju. NS007 i NS008 su ojačani, ali NS007 i dalje čeka migraciju 136 i Cron. Pronađen je **jedan ozbiljan bezbednosni propust koji postoji u produkciji danas**, a popravka je spremna na zasebnoj grani. Ništa nije spojeno, deployovano ni migrirano.

## Šta je pronađeno i popravljeno

1. **Kolega je mogao da vidi vaše poverljive beleške (u produkciji).**
   Advokat iz iste kancelarije, bez delegacije, dobijao je beleške vezane za vaše predmete i klijente, sa nazivom predmeta, sadržajem beleške i ishodom. Dobijao ih je kroz stare stranice „memorija kancelarije“ i „graf“, i to **direktno u AI chat odgovore**. Mogao je i da potvrdi ili deaktivira vašu belešku.
   Dokazano testom na pravom kodu produkcije. Popravka koristi isto pravilo kao Law Brain: belešku o predmetu vidi samo onaj ko sme da vidi predmet. Opšte beleške kancelarije (npr. o sudiji) i dalje vide svi.
2. **Priprema za ročište je mogla da tvrdi pravo bez izvora.**
   „Vrhovni sud smatra da…“ ili „Teret dokazivanja je uvek na tuženom“ prolazilo je provere. Sada AI sme da piše samo pitanja i zadatke za pripremu („Proverite…“, „Pribavite…“), a tvrdnje o praksi, sudovima i zakonu se odbacuju. Ista rupa je zatvorena i u Law Brain analizi.
3. **Automatske provere ekrana (V2) se u CI-ju nikad nisu izvršavale** za NS006–NS008, jer je jedan raniji korak uvek padao. Sada se izvršavaju i prolaze.

## Šta je provereno i u redu je

- **NS006 Docker:** raniji neuspeh je bio samo pad Docker Hub servisa. Ponovljeno: slika se gradi, aplikacija se podiže, srpski OCR radi i Python je 3.11. Nema nijednog novog pada u odnosu na main.
- **CI na GitHub-u (NS007, NS008 i hotfix grana):** nijedan nov pad u odnosu na main, i na Python 3.11 i 3.13 i u produkcionom kontejneru. Docker slika se gradi na sve tri. Ekranski testovi (V2 NG) su zeleni.
- **Povučeni overeni nacrti** se ne pojavljuju ni na jednom mestu u aplikaciji. Fizički i dalje postoje u Pinecone-u.
- **Pad rasporedivača** u najgorem slučaju gubi jedan sat (ili jednu noć). Sledeće pokretanje sve nadoknađuje, bez duplog rada.

## Vaše odluke

1. **Odobrite produkcioni hotfix** za propust iz tačke 1 (grana `hotfix/rh001-memory-acl`). **Ovo je najhitnije.**
2. Da li je „profil klijenta“ (npr. „klijent nikad ne prihvata nagodbu“) namerno deljen sa celom kancelarijom?
3. Stare funkcije sa „procenom uspeha u %“ (broj izmišlja AI) još postoje na nelinkovanoj adresi `/app-legacy` i kroz API. Da li ih ukinuti?
4. Da li brisati povučene nacrte iz Pinecone-a? Dizajn postoji i ne traži novu bazu.
5. Uključite zaštitu grana na GitHub-u (sada je nema ni na `main`).

## Statusi

- **NS006:** PASS — Docker i testovi dokazani na tačnom commit-u. Spreman za vašu odluku o spajanju.
- **NS007:** BLOCKED — kod je ojačan, ali migracija 136, Render Cron i izbor kadence nisu urađeni (namerno).
- **NS008:** PASS uz uslov — bezbednosna popravka je na grani `feature/vindex-v2-rh001-ns008`, ne na originalnoj NS008 grani. Draft PR #10 je otvoren.
- **Beta:** NO-GO dok se ne odluči o hotfix-u iz tačke 1 i dok NS007 ne dobije migraciju i Cron.

**Sledeći korak:** pregledati i spojiti `hotfix/rh001-memory-acl` u main kao poseban hotfix.

Detalji: `docs/v2-recovery/RH001_RELEASE_HARDENING_EVIDENCE.md`.
