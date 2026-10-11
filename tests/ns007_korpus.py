"""NS007 — lažan Pinecone indeks korpusa sudskih odluka (samo `query` sa filterom po broju odluke, kao
`routers/praksa._fetch_decision_chunks`). Sve iznad indeksa je STVARNI kod."""
import types

ODLUKA = "Rev 1234/2023"
TEKST_IZREKA = "Revizija tužioca se usvaja. Rok za tužbu radi poništaja rešenja o otkazu teče od dana dostavljanja rešenja zaposlenom."
TEKST_OBRAZLOZENJE = ("Dostavljanje rešenja o otkazu smatra se izvršenim tek kada zaposleni primi rešenje lično, "
                      "a dan uručenja utvrđen u dostavnici ima prednost nad datumom navedenim u samom rešenju. "
                      "Poslodavac snosi teret dokazivanja da je dostava uredno izvršena.")


class LazanIndeks:
    def __init__(self):
        self.korpus = {ODLUKA: {"court": "Vrhovni sud", "decision_date": "2023-05-10", "matter": "radno pravo",
                                "delovi": [("HEADER", f"Vrhovni sud, {ODLUKA}, 10.05.2023."),
                                           ("IZREKA", TEKST_IZREKA), ("OBRAZLOŽENJE", TEKST_OBRAZLOZENJE)]}}
        self.nedostupan = False
        self.upiti = []

    def query(self, vector=None, top_k=10, namespace=None, include_metadata=True, filter=None):
        self.upiti.append((namespace, filter))
        if self.nedostupan:
            raise ConnectionError("pinecone nedostupan (test)")
        dn = ((filter or {}).get("decision_number") or {}).get("$eq")
        o = self.korpus.get(dn) if namespace == "sudska_praksa" else None
        if not o:
            return types.SimpleNamespace(matches=[])
        return types.SimpleNamespace(matches=[
            types.SimpleNamespace(score=0.9, metadata={"decision_number": dn, "court": o["court"], "decision_date": o["decision_date"],
                                                       "matter": o["matter"], "section": s, "text": t, "chunk_index": i})
            for i, (s, t) in enumerate(o["delovi"])])


def postavi(monkeypatch) -> LazanIndeks:
    import app.services.retrieve as rt
    ind = LazanIndeks()
    monkeypatch.setattr(rt, "_get_index", lambda: ind)
    return ind
