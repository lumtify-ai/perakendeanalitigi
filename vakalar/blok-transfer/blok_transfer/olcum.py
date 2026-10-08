"""İleriye bakan ölçüm (spec §4.1–4.2): plan, karar anından sonraki pencerede ne kurtardı?

Plan karar anındaki bilgiyle kurulur; ölçüt pencerenin içindeki kayıptır. Dört parça:

    tasinan         planın taşıdığı mal, SKU düzeyinde (vericinin karar fotoğrafı)
    kayip_tablosu   penceredeki kayıp, hücre başına (Basit ya da hakem tablosu, argüman)
    verici_satisi   vericilerin pencerede ne sattığı (kaybedilen satışın bedeli)
    olc             üçünü birleştirir → `Olcum`

Bu modül hakemi tanımaz: hakem tablosu çağıran koddan `kayip` argümanı olarak gelir
(`tests/test_sizinti.py`). Kimlikler (mağaza, ürün) birleşimlerden önce `str`'e çevrilir:
parquet/hakem tabloları `category`, DuckDB sonuçları `object` döndürür ve ikisinin
birleşimi sessizce yanlış eşleşir ya da hata verir.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from .hazirla import pencere as _pencere

TASINAN_KOLONLARI = ["verici", "alici", "option_id", "urun_id", "adet"]
KAYIP_KOLONLARI = ["magaza_id", "urun_id", "kayip"]


def pencere(karar: date, hafta: int = 8) -> tuple[date, date]:
    """Ölçüm penceresi `[karar, karar + 7·hafta gün)`; ikinci uç dahil değil.
    Tanım `hazirla.pencere`dedir: ön hazırlık ile ölçüm aynı pencereyi kullanır."""
    return _pencere(karar, hafta)


def _metin(df: pd.DataFrame, kolonlar: list[str]) -> pd.DataFrame:
    """Kopya; verilen kolonlar düz `str` (category/object farkı birleşimi bozmasın)."""
    df = df.copy()
    for kolon in kolonlar:
        df[kolon] = df[kolon].astype(str)
    return df


def tasinan(con, hareketler: pd.DataFrame, karar: date) -> pd.DataFrame:
    """Planın taşıdığı mal: her hareketin vericisinin KARAR GÜNÜ fotoğrafındaki, o
    option'a ait SKU adetleri (adet > 0). Bir hareket blok demektir: vericinin o
    option'daki bütün stoku tek hedefe gider, bu yüzden hareketin `adet`i SKU
    adetlerinin toplamına eşittir.

    Sütunlar `verici, alici, option_id, urun_id, adet`. `bt_stok` görünümü kurulu olmalı."""
    if not len(hareketler):
        return pd.DataFrame(columns=TASINAN_KOLONLARI)
    bloklar = _metin(hareketler[["verici", "alici", "option_id"]], ["verici", "alici", "option_id"])
    con.register("_bt_bloklar", bloklar.drop_duplicates())
    try:
        sonuc = con.execute(
            """
            select b.verici, b.alici, b.option_id, s.urun_id, sum(s.adet) as adet
            from _bt_bloklar b
            join urun u on u.option_id = b.option_id
            join bt_stok s on s.urun_id = u.urun_id and s.magaza_id = b.verici
            where s.tarih = ?::timestamp
            group by b.verici, b.alici, b.option_id, s.urun_id
            having sum(s.adet) > 0
            order by b.verici, b.alici, b.option_id, s.urun_id
            """,
            [karar.isoformat()],
        ).df()
    finally:
        con.unregister("_bt_bloklar")
    sonuc["adet"] = sonuc["adet"].astype("int64")
    return sonuc[TASINAN_KOLONLARI]


def kayip_tablosu(
    kayip: pd.DataFrame,
    karar: date,
    hafta: int,
    evren: set[str],
    sutun: str,
    hucreler: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Pencere içi, evren içi kayıp: `[magaza_id, urun_id, kayip]`, hücre başına toplam.

    `kayip` tablosunda `tarih, magaza_id, urun_id` ve `sutun` olmalı; Basit için
    `sutun="kayip"`, hakem tablosu için `"karsilanmayan"`. Pencere `pencere(karar, hafta)`;
    `evren` dışı mağazalar (ONL dahil) düşer. `hucreler` (`magaza_id, urun_id`) verilirse
    yalnız o hücreler kalır: hakem kaybı Basit'in baktığı hücre evrenine indirgenip
    aynı zeminde karşılaştırılsın diye. Süzgeç evren süzgecini kaldırmaz, ikisi birlikte
    uygulanır."""
    bas, bit = pencere(karar, hafta)
    t = _metin(kayip[["tarih", "magaza_id", "urun_id", sutun]], ["magaza_id", "urun_id"])
    tarih = pd.to_datetime(t["tarih"])
    t = t[(tarih >= pd.Timestamp(bas)) & (tarih < pd.Timestamp(bit))]
    t = t[t["magaza_id"].isin({str(m) for m in evren})]
    if hucreler is not None:
        h = _metin(hucreler[["magaza_id", "urun_id"]], ["magaza_id", "urun_id"]).drop_duplicates()
        t = t.merge(h, on=["magaza_id", "urun_id"], how="inner")
    t = (t.groupby(["magaza_id", "urun_id"], as_index=False, observed=True)[sutun].sum()
         .rename(columns={sutun: "kayip"}))
    t["kayip"] = t["kayip"].astype("int64")
    return t[KAYIP_KOLONLARI].reset_index(drop=True)


def verici_satisi(con, karar: date, hafta: int) -> pd.DataFrame:
    """`bt_satis`'in pencere içi NET satışı (iade düşülmüş): `[magaza_id, urun_id, adet]`.
    Net toplam negatif olabilir; kırpma `olc`tadır. Görünüm tarih sınırı koymaz, pencere
    burada konur."""
    bas, bit = pencere(karar, hafta)
    sonuc = con.execute(
        """
        select magaza_id, urun_id, sum(adet) as adet
        from bt_satis
        where tarih >= ?::timestamp and tarih < ?::timestamp
        group by magaza_id, urun_id
        order by magaza_id, urun_id
        """,
        [bas.isoformat(), bit.isoformat()],
    ).df()
    sonuc["adet"] = sonuc["adet"].astype("int64")
    return sonuc


@dataclass(frozen=True)
class Olcum:
    tasinan_adet: int      # planın taşıdığı toplam adet
    kurtarilan: float      # taşınan malın penceredeki kaybı karşıladığı adet
    payda: float           # penceredeki toplam kayıp (evren içi)
    yakalama: float        # kurtarilan / payda (payda 0 → 0)
    p_alici: float         # kurtarilan / tasinan_adet: taşınan mal gerçekten kayba mı gitti
    p_verici: float        # taşınan malın vericide de satılan payı (vericinin bedeli)


def olc(tasinan: pd.DataFrame, kayip: pd.DataFrame, satis: pd.DataFrame) -> Olcum:
    """`tasinan`, `kayip_tablosu` ve `verici_satisi` çıktılarından ölçüm.

    kurtarilan  Σ_(alıcı, SKU) min(Σ_verici taşınan, kayıp): aynı alıcı SKU'suna birden
                çok vericiden mal giderse önce toplanır, sonra kayıpla sınırlanır; aynı
                kayıp iki kez kurtarılmış sayılmaz. Beden eşleşmesi SKU düzeyindedir
                (XS taşınır, kayıp M'deyse kurtarılan 0).
    payda       kayip.kayip.sum()
    p_alici     kurtarilan / tasinan_adet
    p_verici    Σ_(verici, SKU) min(taşınan, max(0, satış)) / tasinan_adet: taşınan malın
                ne kadarı vericide de pencerede satıldı (vericinin bedeli). İade net
                satışı eksiye düşürse de kırpma 0'da durur.
    Plan boşsa (tasinan_adet 0) bütün oranlar 0."""
    payda = float(kayip["kayip"].sum()) if len(kayip) else 0.0
    adet = int(tasinan["adet"].sum()) if len(tasinan) else 0
    if adet == 0:
        return Olcum(0, 0.0, payda, 0.0, 0.0, 0.0)

    t = _metin(tasinan[["verici", "alici", "urun_id", "adet"]], ["verici", "alici", "urun_id"])

    alici = (t.groupby(["alici", "urun_id"], as_index=False)["adet"].sum()
             .rename(columns={"alici": "magaza_id"}))
    k = _metin(kayip[["magaza_id", "urun_id", "kayip"]], ["magaza_id", "urun_id"])
    k = k.groupby(["magaza_id", "urun_id"], as_index=False)["kayip"].sum()
    alici = alici.merge(k, on=["magaza_id", "urun_id"], how="left")
    kurtarilan = float(alici[["adet", "kayip"]].astype("float64").fillna(0).min(axis=1).sum())

    verici = (t.groupby(["verici", "urun_id"], as_index=False)["adet"].sum()
              .rename(columns={"verici": "magaza_id"}))
    s = _metin(satis[["magaza_id", "urun_id", "adet"]], ["magaza_id", "urun_id"])
    s = s.groupby(["magaza_id", "urun_id"], as_index=False)["adet"].sum()
    verici = verici.merge(s, on=["magaza_id", "urun_id"], how="left", suffixes=("", "_satis"))
    satilan = verici["adet_satis"].astype("float64").fillna(0).clip(lower=0)
    sat_pay = float(pd.concat([verici["adet"], satilan], axis=1).min(axis=1).sum())

    return Olcum(
        tasinan_adet=adet,
        kurtarilan=kurtarilan,
        payda=payda,
        yakalama=kurtarilan / payda if payda else 0.0,
        p_alici=kurtarilan / adet,
        p_verici=sat_pay / adet,
    )
