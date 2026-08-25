from datetime import date, timedelta

import duckdb

from .cekirdek import adaylar as adaylar_mod
from .cekirdek import terazi, veri
from .cekirdek.parametreler import Parametreler
from .cozuculer import greedy, mip
from .cozuculer.tip import Plan

COZUCULER = {"greedy": greedy.cozumle, "mip": mip.cozumle}


def ozetle(plan: Plan, p: Parametreler) -> dict:
    h = plan.hareketler
    rota_sayisi = len(h.groupby(["verici", "alici"])) if len(h) else 0
    return {
        "option_sayisi": int(len(h)),
        "tasinan_adet": int(h.adet.sum()) if len(h) else 0,
        "bosalan_magaza": int(h.verici.nunique()) if len(h) else 0,
        "net_kazanc_tl": round(float(h.w.sum()) - rota_sayisi * p.rota_sabiti_tl, 2),
        "sure_sn": round(plan.sure_sn, 3),
    }


def kayip_satis_yakalama(
    plan: Plan, con: duckdb.DuckDBPyConnection, karar: date, pencere_hafta: int = 8
) -> float:
    """kayip_satis YALNIZ burada okunur (spec §2): çözüm girdisi değil, ölçüttür."""
    baslangic = karar - timedelta(weeks=pencere_hafta)
    df = con.execute(
        """
        select k.magaza_id, u.option_id, sum(k.kayip_adet) as kayip
        from kayip_satis k join urun u using (urun_id)
        where k.tarih >= ? and k.tarih < ?
        group by 1, 2
        """,
        [baslangic, karar],
    ).df()
    toplam = df.kayip.sum()
    if toplam == 0:
        return 0.0
    alicilar = set(zip(plan.hareketler.alici, plan.hareketler.option_id))
    adreslenen = df[
        df.apply(lambda s: (s.magaza_id, s.option_id) in alicilar, axis=1)
    ].kayip.sum()
    return float(adreslenen / toplam)


def boru_hatti(
    con: duckdb.DuckDBPyConnection, karar: date, p: Parametreler, yontem: str
) -> tuple[Plan, dict]:
    """Adaylar → terazi → çözücü → özet. Senaryoların ve testlerin tek kapısı."""
    df = terazi.agirliklandir(adaylar_mod.uret(con, karar, p), p)
    kapasite = adaylar_mod.kapasite_boslugu(con, karar)
    plan = COZUCULER[yontem](df, kapasite, p)
    return plan, ozetle(plan, p)
