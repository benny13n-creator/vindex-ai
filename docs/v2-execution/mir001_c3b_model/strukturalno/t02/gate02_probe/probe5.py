import sys; sys.path.insert(0, ".")
from shared import nacrt_za_sud as NZ, procesno_stanje as PS
from tests.test_mir001_c3b_procesno_stanje_ugovor import DOK06, ODUSTANAK, PREDUJAM, ZAPISNIK, BEZ_ZAPISNIKA, _d
st = lambda *d: PS.utvrdi(list(d), predmet_id="pred-1", user_id="user-A")
A = st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK))
C1 = st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK), _d("DOK-08", ODUSTANAK))
H2 = st(_d("DOK-07", PREDUJAM))
for g,s,t in [
 ("H2",H2,"Tužilac ističe da je predujam uplatio [[PS-02]]."),
 ("H2",H2,"Tužilac ističe da je uplatio predujam (DOK-07)."),
 ("H2",H2,"Tužilac u podnesku (DOK-99) navodi da je uplatio predujam."),
 ("H2",H2,"Tužilac navodi da je predujam uplaćen u ostavljenom roku (DOK-07)."),
 ("H2",H2,"Kako tužilac ističe, predujam je uplaćen [[PS-02]]."),
 ("A",A,"Tužilac ističe da je tuženi dostavio građevinski dnevnik (DOK-07)."),
 ("A",A,"Tužilac ističe da je rok za dostavu dnevnika istekao [[PS-05]]."),
 ("A",A,"Tužilac ističe da tuženi nije postupio po nalogu [[PS-05]]."),
 ("A",A,"Tuženi tvrdi da je dnevnik dostavio (DOK-06)."),
 ("A",A,"Tužilac ističe da je dopuna veštačenja nepotrebna (DOK-07)."),
 ("C1",C1,"Tužilac ističe da je odustankom tuženog [[PS-09]] nalog prestao da važi."),
 ("C1",C1,"Tuženi je odustao [[PS-09]], kako navodi tužilac, pa dopuna neće biti sprovedena."),
 ("A",A,"Tužilac navodi da je veštak dopunu već sproveo (DOK-07)."),
]:
    k=NZ.zastiti(t,s); print("OMIT" if k["izostavljeno"] else "KEEP", f"[{g}]", repr(t), [i["razlog"][:40] for i in k["izostavljeno"]])
