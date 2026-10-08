from datetime import date, timedelta

import duckdb
import pandas as pd

from . import metrikler
from .parametreler import Parametreler


KOLONLAR = ["verici", "alici", "option_id", "adet", "hiz_verici", "hiz_alici", "fiyat", "alis"]


def kapasite_boslugu(con: duckdb.DuckDBPyConnection, karar: date, tepe_hafta: int = 52) -> dict[str, int]:
    """Mağaza başına boş yer: `max(0, tepe − stok(karar))` (spec §3.3).

    tepe   `[karar − tepe_hafta hafta, karar)` içindeki fotoğraflarda mağaza
           toplamının en büyüğü (karar günü ve sonrası tepeye girmez)
    stok   karar günü fotoğrafındaki mağaza toplamı

    Mağazanın kapasite kolonu kullanılmaz: gözlenen en yüksek stok, mağazanın
    fiilen taşıdığı yükün kanıtıdır. Geçmişi olmayan mağazanın tepesi 0, boşluğu 0.
    Yalnız evren (`bt_magaza`) mağazaları döner."""
    baslangic = karar - timedelta(weeks=tepe_hafta)
    df = con.execute(
        """
        with foto as (
            select tarih, magaza_id, sum(adet) as toplam
            from bt_stok
            where tarih >= ? and tarih < ?
            group by 1, 2
        ),
        tepe as (select magaza_id, max(toplam) as tepe from foto group by 1),
        bugun as (
            select magaza_id, sum(adet) as stok
            from bt_stok
            where tarih = ?
            group by 1
        )
        select m.magaza_id,
               greatest(0, coalesce(t.tepe, 0) - coalesce(b.stok, 0)) as bosluk
        from bt_magaza m
        left join tepe t using (magaza_id)
        left join bugun b using (magaza_id)
        """,
        [baslangic, karar, karar],
    ).df()
    return dict(zip(df.magaza_id, df.bosluk.astype(int)))


def _sogumada(con, karar: date, soguma_hafta: int) -> set[tuple[str, str]]:
    """Varışı `(karar − soguma_hafta, karar]` içinde olan (mağaza, option) hücreleri.

    Her sevkiyat türü (replenishment, elle transfer...) sayılır; ölçüt sevk
    değil VARIŞ tarihidir, yolda kalanlar (varışı boş) `bt_sevkiyat`ta yoktur.
    Karar sonrası varışlar soğuma sayılmaz."""
    esik = karar - timedelta(weeks=soguma_hafta)
    df = con.execute(
        """
        select distinct sv.magaza_id, u.option_id
        from bt_sevkiyat sv join urun u using (urun_id)
        where sv.tarih > ? and sv.tarih <= ?
        """,
        [esik, karar],
    ).df()
    return set(zip(df.magaza_id, df.option_id))


def uret(con, karar: date, p: Parametreler) -> pd.DataFrame:
    coverlar = metrikler.coverlar(con, karar, p)          # yalnız stok > 0 hücreler
    hizlar = metrikler.hizlar(con, karar, p.hiz_penceresi_hafta)
    kiriklar = metrikler.kiriklar(con, karar)
    stok = metrikler.stok_fotografi(con, karar)

    urunler = con.execute(
        "select option_id, any_value(line) as line, any_value(liste_fiyati) as fiyat, "
        "any_value(alis_fiyati) as alis from urun group by 1"
    ).df()
    tipler = dict(con.execute("select magaza_id, tip from bt_magaza").fetchall())

    soguma = _sogumada(con, karar, p.soguma_hafta)
    vericiler = coverlar[coverlar.cover >= p.verici_cover_esigi].copy()
    if len(vericiler):
        vericiler = vericiler[
            ~vericiler.apply(lambda s: (s.magaza_id, s.option_id) in soguma, axis=1)
        ]

    kirik_kume = set(zip(kiriklar.magaza_id, kiriklar.option_id))
    # Karar R4: kırık hücre verici olamaz. Kırığın satışı durur, cover → ∞
    # görünür; cover tek başına onu verici sayardı. Kırık rafı doldurmak
    # gerekir, boşaltmak değil (alıcı tarafıyla aynı tanım: `metrikler.kiriklar`).
    if len(vericiler):
        vericiler = vericiler[
            ~vericiler.apply(lambda s: (s.magaza_id, s.option_id) in kirik_kume, axis=1)
        ]
    stoklu_kume = set(zip(stok.magaza_id, stok.option_id))
    # Alıcı cover'ı: stoklu hücrede hesaplanmış cover, stoksuz hücrede
    # tanımı gereği 0. Sözlükte olmayan hücre stoksuzdur.
    cover_haritasi = {
        (m, o): c for m, o, c in zip(coverlar.magaza_id, coverlar.option_id, coverlar.cover)
    }
    alicilar = hizlar[hizlar.hiz >= p.min_satis].copy()
    if len(alicilar):
        # Üç kapılı birleşim: yapısal ihtiyaç (kırık ya da stoksuz) YA DA
        # hız ihtiyacı (satıyor ama malı tavanın altında kalacak kadar az).
        # Tavan 0 iken üçüncü kapı hiçbir yeni alıcı getirmez — stoklu
        # hücrede cover her zaman > 0'dır — yani bugünkü model korunur.
        alicilar = alicilar[
            alicilar.apply(
                lambda s: (s.magaza_id, s.option_id) in kirik_kume
                or (s.magaza_id, s.option_id) not in stoklu_kume   # stoksuz
                or cover_haritasi.get((s.magaza_id, s.option_id), 0.0)
                <= p.alici_cover_tavani,
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
