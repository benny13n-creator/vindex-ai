# Vindex AI — Word Add-in: lokalno testiranje i sideload

Status: KORAK C implementiran i **live verifikovan** 2026-07-25 (v.
`scripts/run_word_addin_dev.py`, `tests/test_word_addin_taskpane.py`,
`tests/test_copilot_ambient.py` — 20/20 testova prolazi).

## 1. Pokretanje lokalnog HTTPS servera

```
python scripts/run_word_addin_dev.py
```

Ovo pokreće CEO FastAPI app (`api.py`) preko `https://127.0.0.1:8000`, sa
samopotpisanim TLS sertifikatom generisanim automatski pri prvom pokretanju
(`scripts/word_addin_dev_certs/` — lokalno, nikad u git-u). Taskpane,
adapter.js, ikone i `POST /api/copilot/ambient/analyze` su svi servirani sa
istog origina, pa nema CORS problema ni lokalno ni u produkciji.

Provera da server radi (u drugom terminalu):

```
curl -k https://127.0.0.1:8000/word_addin/manifest.xml
```

## 2. Sideload u Word Desktop (Windows)

1. Word → **Insert** (Umetanje) → **Add-ins** (Dodaci) → **My Add-ins** →
   ozupčanik/strelica → **Upload My Add-in** (Otpremi moj dodatak).
2. Izaberi `integrations/word_addin/manifest.xml` sa lokalnog diska.
3. Ako Word/WebView2 prijavi da sertifikat nije poverljiv: najpouzdanije
   rešenje je Microsoft-ov zvanični alat —
   ```
   npx office-addin-dev-certs install
   ```
   (Node v24 je dostupan u ovom okruženju). On instalira OS-nivo poverljiv
   lokalni sertifikat tačno za ovu namenu. Restartuj
   `scripts/run_word_addin_dev.py` posle instalacije, ili prosledi
   `--regenerate-cert` da ponovo generiše par ako se pređe na taj alat.
4. Na traci (ribbon) → **Home** tab → grupa **Vindex AI** → dugme
   **Ambient Copilot** otvara taskpane sa desne strane.

## 3. Sideload u Word on the Web (Office 365)

Word on the Web ne može direktno da učita `manifest.xml` sa lokalnog diska
za `localhost` domen bez dodatnog koraka — potrebno je da manifest bude
dostupan na javno dostupnom (ili barem mrežno dostupnom) URL-u, ili da se
koristi **Microsoft 365 Admin Center → Integrated Apps** za organizacioni
upload. Za brzo lokalno testiranje, Word Desktop (korak 2) je preporučeni
put; Word on the Web sideload ima smisla tek kad `manifest.xml` bude
ažuriran da pokazuje na `https://vindex.rs/word_addin/...` (v. napomena u
vrhu `manifest.xml`) i deployovan u produkciju.

## 4. Šta testirati u taskpane-u

1. Login view: unesi Vindex AI kredencijale (koristi isti auth kao web app).
2. Main view: kucaj/selektuj pasus teksta u Word dokumentu — adapter.js-ov
   `watchParagraphChanges` debounce-uje i šalje `POST
   /api/copilot/ambient/analyze`.
3. Sugestije (članovi zakona, sudska praksa, upozorenja) treba da se pojave
   u taskpane-u u roku od par sekundi po prestanku kucanja.
4. Kratki pasusi (ispod praga dužine) namerno preskaču analizu bez greške
   — v. `test_short_passage_skips_analysis_entirely`.

## 5. Pre produkcione distribucije (NIJE URAĐENO — otvoreno)

`manifest.xml` je trenutno **lokalni dev manifest** sa hardkodovanim
`https://localhost:8000/...` URL-ovima i placeholder `<Id>`
(`00000000-0000-0000-0000-000000000000`). Pre bilo kakvog javnog
sideload-a/AppSource objavljivanja:

- Generisati pravi GUID za `<Id>`.
- Zameniti sve `https://localhost:8000/word_addin/...` sa
  `https://vindex.rs/word_addin/...`.
- Ukloniti `https://localhost:8000` iz `<AppDomains>`.
- Zameniti placeholder ikone (`icon-16/32/80.png`, generisane programski
  ovom sesijom) pravim dizajniranim ikonama ako se ide u javnu distribuciju.
