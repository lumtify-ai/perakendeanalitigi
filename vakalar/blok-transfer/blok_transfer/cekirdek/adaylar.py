from datetime import date, timedelta

import duckdb
import pandas as pd

from . import metrikler
from .parametreler import Parametreler


KOLONLAR = ["verici", "alici", "option_id", "adet", "hiz_verici", "hiz_alici", "fiyat"]


def kapasite_boslugu(con: duckdb.DuckDBPyConnection, karar: date) -> dict[str, int]:
    df = con.execute(
        """
        select m.magaza_id,
               greatest(0, m.kapasite - coalesce(sum(st.adet), 0)) as bosluk
        from magaza m
        left join stok st on st.magaza_id = m.magaza_id and st.tarih = ?
        group by m.magaza_id, m.kapasite
        """,
        [karar],
    ).df()
    return dict(zip(df.magaza_id, df.bosluk.astype(int)))


def _sogumada(con, karar: date, soguma_hafta: int) -> set[tuple[str, str]]:
    esik = karar - timedelta(weeks=soguma_hafta)
    df = con.execute(
        """
        select distinct sv.magaza_id, u.option_id
        from sevkiyat sv join urun u using (urun_id)
        where sv.tarih > ?
        """,
        [esik],
    ).df()
    return set(zip(df.magaza_id, df.option_id))


def uret(con, karar: date, p: Parametreler) -> pd.DataFrame:
    coverlar = metrikler.coverlar(con, karar, p)          # yalnız stok > 0 hücreler
    hizlar = metrikler.hizlar(con, karar, p.hiz_penceresi_hafta)
    kiriklar = metrikler.kiriklar(con, karar)
    stok = metrikler.stok_fotografi(con, karar)

    urunler = con.execute(
        "select option_id, any_value(line) as line, any_value(liste_fiyati) as fiyat "
        "from urun group by 1"
    ).df()
    tipler = dict(con.execute("select magaza_id, tip from magaza").fetchall())

    soguma = _sogumada(con, karar, p.soguma_hafta)
    vericiler = coverlar[coverlar.cover >= p.cover_esigi].copy()
    if len(vericiler):
        vericiler = vericiler[
            ~vericiler.apply(lambda s: (s.magaza_id, s.option_id) in soguma, axis=1)
        ]

    kirik_kume = set(zip(kiriklar.magaza_id, kiriklar.option_id))
    stoklu_kume = set(zip(stok.magaza_id, stok.option_id))
    alicilar = hizlar[hizlar.hiz >= p.min_satis].copy()
    if len(alicilar):
        alicilar = alicilar[
            alicilar.apply(
                lambda s: (s.magaza_id, s.option_id) in kirik_kume
                or (s.magaza_id, s.option_id) not in stoklu_kume,   # stoksuz
                axis=1,
            )
        ]

    # Sıkı eşiklerde taraflardan biri tamamen boşalabilir; merge o durumda
    # kolon adlarını kaybettiği için burada erken dönülür.
    if not len(vericiler) or not len(alicilar):
        return pd.DataFrame(columns=KOLONLAR)

    df = vericiler.merge(
        alicilar, on="option_id", suffixes=("_verici", "_alici")
    ).merge(urunler, on="option_id")
    df = df[df.magaza_id_verici != df.magaza_id_alici]
    df = df[
        (df.line != "Outlet")
        | (df.magaza_id_alici.map(tipler) == "Outlet")
    ]
    df = df.rename(
        columns={"magaza_id_verici": "verici", "magaza_id_alici": "alici"}
    )
    df["hiz_verici"] = df["hiz_verici"].fillna(0.0)
    # Sıralama şart: DuckDB sorgularında ORDER BY yok, satır sırası koşudan
    # koşuya değişebilir. Sıra değişince MIP'in değişken adlandırması değişir
    # ve çözücü eşit değerli optimumlar arasında başka birini döndürür —
    # amaç değeri aynı kalsa da plan oynar. Determinizm güven meselesidir.
    return df[KOLONLAR].sort_values(["verici", "alici", "option_id"]).reset_index(drop=True)
