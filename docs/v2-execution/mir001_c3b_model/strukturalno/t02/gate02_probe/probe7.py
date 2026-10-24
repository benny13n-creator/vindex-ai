import sys; sys.path.insert(0, ".")
from shared import nacrt_za_sud as NZ, procesno_stanje as PS
from tests.test_mir001_c3b_procesno_stanje_ugovor import DOK06, ZAPISNIK, PREDUJAM, _d
st = lambda *d: PS.utvrdi(list(d), predmet_id="pred-1", user_id="user-A")
A = st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK))
H2 = st(_d("DOK-07", PREDUJAM))
TA = """PRIVREDNOM SUDU U PRIMERGRADU
Broj predmeta: P 9901/2026

PODNESAK TUŽIOCA
povodom izjašnjenja tuženog na nalaz veštaka

Tužilac se ovim podneskom izjašnjava na navode tuženog iz izjašnjenja [[PS-02]].
Tuženi u izjašnjenju (DOK-06) osporava nalaz veštaka od 15.06.2026. godine.
Tužilac smatra da je nalaz veštaka potpun, jasan i u skladu sa pravilima struke.
Veštak je u nalazu dao jasne odgovore na sva postavljena pitanja.
Uzrok prokišnjavanja je neodgovarajuće izvedena hidroizolacija, što tuženi ne osporava.
Iako je sud [[PS-04]], tužilac predlaže da sud prilikom ocene dopunskog nalaza ima u vidu da je osnovni nalaz potpun.
Tužilac ističe da građevinski dnevnik, koji je sud naložio tuženom da dostavi [[PS-05]], treba da potvrdi redosled izvođenja radova.
Tužilac predlaže da sud, nakon što tuženi postupi po nalogu [[PS-05]], omogući strankama da se izjasne o dnevniku.
Tužilac ostaje pri tužbenom zahtevu kako je preciziran na ročištu (DOK-07), na iznos od 3.150.000 dinara.
Tužilac predlaže da sud tuženog obaveže da naknadi troškove postupka.

U Primergradu, 01.09.2026. godine
Punomoćnik tužioca"""
TH = """Tužilac se izjašnjava povodom zapisnika [[PS-02]].
Tužilac moli sud da mu, iz opravdanih razloga, produži rok za uplatu predujma [[PS-02]] za 8 dana.
Tužilac ističe da je spreman da snosi troškove dopune veštačenja.
Tužilac ostaje pri predlogu da se dopuna veštačenja sprovede u celosti."""
for s, t in [(A, TA), (H2, TH)]:
    k = NZ.zastiti(t, s)
    print(len(k["izostavljeno"]), "izostavljeno")
    for i in k["izostavljeno"]: print("  ", i["id"], i["razlog"][:60], "|", i["recenica"][:110])
