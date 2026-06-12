# web3_integracija — Queue-Based Blockchain Event Adapter

**Status: Extension modul — nije u produkcijskom API-ju**

Ovaj modul pretvara blockchain događaje u asinhrone pravne upite prema Vindex AI analizi.
Dizajniran kao posredni sloj između blockchain event listenera i Vindex RAG engine-a.

## Šta radi
- `Web3QueueEngine` — asinhron queue processor koji prima blockchain evente i prosleđuje ih
  kao pravne upite prema `/api/pitanje`
- `Web3LegalEvent` — dataclass za standardizaciju blockchain event payloada
- `ZOO_KATALOG` — mapa blockchain event tipova na relevantne ZOO/ZDI pravne oblasti

## Kako se razlikuje od `vindex_web3/`
| Modul | Pristup | Kleros | Status |
|-------|---------|--------|--------|
| `vindex_web3/` | Direktna pipeline analiza | Da | Extension |
| `web3_integracija/` | Queue adapter → `/api/pitanje` | Ne | Extension |
| `web3_compliance.py` | Direktan OpenAI poziv | Ne | **U produkciji** |

## Produkcijska integracija
Produkcijski `/web3/*` endpointi koriste `web3_compliance.py`.
Ovaj modul je naprednija implementacija za event-driven arhitekturu — nije integrisan.

## Kako integrisati
Queue engine pretpostavlja da `/api/pitanje` endpoint postoji i prima `{"pitanje": str}`.
Integracija zahteva: pokretanje queue workera kao posebnog procesa + konfiguraciju event subscriptiona.
