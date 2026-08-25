from datetime import date, timedelta

import duckdb
import pandas as pd

from .parametreler import Parametreler


def hizlar(con: duckdb.DuckDBPyConnection, karar: date, pencere_hafta: int) -> pd.DataFrame:
    """Stoklu haftaların ortalama net satışı (option düzeyi). Stoksuz hafta
    ortalamayı kirletmez; iade (negatif adet) netlenir."""
    baslangic = karar - timedelta(weeks=pencere_hafta)
    return con.execute(
        """
        with stoklu as (
            select st.tarih as hafta, st.magaza_id, u.option_id
            from stok st join urun u using (urun_id)
            where st.tarih >= ? and st.tarih < ?
            group by 1, 2, 3
            having sum(st.adet) > 0
        ),
        haftalik_satis as (
            select date_trunc('week', s.tarih) as hafta, s.magaza_id, u.option_id,
                   sum(s.adet) as adet
            from satis s join urun u using (urun_id)
            where s.tarih >= ? and s.tarih < ?
            group by 1, 2, 3
        )
        select k.magaza_id, k.option_id,
               coalesce(sum(hs.adet), 0)::double / count(*) as hiz
        from stoklu k
        left join haftalik_satis hs
          on hs.hafta = k.hafta and hs.magaza_id = k.magaza_id and hs.option_id = k.option_id
        group by 1, 2
        """,
        [baslangic, karar, baslangic, karar],
    ).df()


def stok_fotografi(con, karar: date) -> pd.DataFrame:
    return con.execute(
        """
        select st.magaza_id, u.option_id, sum(st.adet) as adet
        from stok st join urun u using (urun_id)
        where st.tarih = ?
        group by 1, 2
        having sum(st.adet) > 0
        """,
        [karar],
    ).df()


def kiriklar(con, karar: date) -> pd.DataFrame:
    """Toplam stok > 0 iken ara kademelerden (sıra 2-4) en az biri sıfır."""
    return con.execute(
        """
        select st.magaza_id, u.option_id
        from stok st join urun u using (urun_id)
        where st.tarih = ?
        group by 1, 2
        having sum(st.adet) > 0
           and count(*) filter (where st.adet = 0 and u.beden_sira in (2, 3, 4)) > 0
        """,
        [karar],
    ).df()


def coverlar(con, karar: date, p: Parametreler) -> pd.DataFrame:
    stok = stok_fotografi(con, karar)
    hiz = hizlar(con, karar, p.hiz_penceresi_hafta)
    df = stok.merge(hiz, on=["magaza_id", "option_id"], how="left")
    df["hiz"] = df["hiz"].fillna(0.0)
    df["cover"] = df.apply(
        lambda s: s.adet / s.hiz if s.hiz > 0 else p.buyuk_cover, axis=1
    )
    return df


def strler(con, karar: date) -> pd.DataFrame:
    return con.execute(
        """
        with sevk as (
            select sv.magaza_id, u.option_id, sum(sv.adet) as sevk_adet
            from sevkiyat sv join urun u using (urun_id)
            where sv.tarih <= ?
            group by 1, 2
        ),
        net_satis as (
            select s.magaza_id, u.option_id, sum(s.adet) as satis_adet
            from satis s join urun u using (urun_id)
            where s.tarih <= ?
            group by 1, 2
        )
        select sevk.magaza_id, sevk.option_id,
               coalesce(net_satis.satis_adet, 0)::double / sevk.sevk_adet as str_orani
        from sevk
        left join net_satis using (magaza_id, option_id)
        where sevk.sevk_adet > 0
        """,
        [karar, karar],
    ).df()
