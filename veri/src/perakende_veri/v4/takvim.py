"""v4 takvimi ve sezon tablosu.

İki takvim vardır: simülasyonun yürüdüğü tam takvim (ısınma + uzatma dahil)
ve dışa aktarılan pencere. Gün indisi her yerde TAM takvimin indisidir
(0 = ISINMA_BASLANGIC); vakalar da aynı indisle çalışır.

v4 hiçbir v2/v3/kök modülünü içe aktarmaz: `ILKBAHAR_YAZ_AYLARI` kök
`perakende_veri.takvim`'den değil, burada yeniden tanımlanır.
"""

import numpy as np
import pandas as pd

from . import sabitler

ILKBAHAR_YAZ_AYLARI = {3, 4, 5, 6, 7, 8}

# Isınmadan pencere sonuna (BITIS) kadar simüle edilen gün sayısı, dahil.
D = (sabitler.BITIS - sabitler.ISINMA_BASLANGIC).days + 1


def sezon_tablosu() -> pd.DataFrame:
    """`sezon` tablosu: sezon × dalga başına bir satır.

    AW22 yalnız ısınmanın referans sezonudur (bkz. sabitler.SEZONLAR); dışa
    aktarılan tabloya girmez (6 sezon × 3 dalga = 18 satır).
    """
    satirlar = []
    for kod, s in sabitler.SEZONLAR.items():
        if kod == "AW22":
            continue
        for dalga, lansman in enumerate(s["dalgalar"], start=1):
            satirlar.append(
                {
                    "sezon_kodu": kod,
                    "dalga": dalga,
                    "lansman_tarihi": pd.Timestamp(lansman),
                    "indirim_baslangic": pd.Timestamp(s["indirim"]),
                    "cikis_tarihi": pd.Timestamp(s["cikis"]),
                }
            )
    return pd.DataFrame(satirlar)


def _ticari_sezon(tarihler: pd.DatetimeIndex) -> list[str]:
    """Tarihin ticari sezon kodu: son ilk dalgası başlamış sezon.

    Örn. SS24, 2024-02-12'de ilk dalgası mağazaya girdiği gün başlar ve
    AW24'ün ilk dalgasına kadar sürer. İndirimdeki eski sezonun ürünü
    rafta dursa da ticari takvim yeni sezondadır. Hiçbir sezon henüz
    başlamadıysa (ısınmanın ilk haftaları) en erken sezona (AW22) düşer.
    """
    baslangiclar = sorted(
        (pd.Timestamp(s["dalgalar"][0]), kod) for kod, s in sabitler.SEZONLAR.items()
    )
    kodlar = []
    for t in tarihler:
        uygun = [kod for bas, kod in baslangiclar if bas <= t]
        kodlar.append(uygun[-1] if uygun else baslangiclar[0][1])
    return kodlar


def _indirim_donemi(tarihler: pd.DatetimeIndex) -> np.ndarray:
    """Herhangi bir sezonun planlı indirimindeyse True (indirim ≤ t < çıkış)."""
    sonuc = np.zeros(len(tarihler), dtype=bool)
    for s in sabitler.SEZONLAR.values():
        sonuc |= (tarihler >= pd.Timestamp(s["indirim"])) & (
            tarihler < pd.Timestamp(s["cikis"])
        )
    return sonuc


def _takvim_uret(baslangic, bitis) -> pd.DataFrame:
    """Tüm sütunları içeren ham takvim; `takvim_tablosu`/`simulasyon_takvimi`
    kendi alt kümesini seçer."""
    tarihler = pd.date_range(baslangic, bitis, freq="D")
    black_friday = {pd.Timestamp(b) for b in sabitler.BLACK_FRIDAY}
    return pd.DataFrame(
        {
            "tarih": tarihler,
            "hafta": tarihler.isocalendar().week.astype(int).to_numpy(),
            "ay": tarihler.month,
            "yil": tarihler.year,
            "sezon": [
                "İlkbahar/Yaz" if ay in ILKBAHAR_YAZ_AYLARI else "Sonbahar/Kış"
                for ay in tarihler.month
            ],
            "sezon_kodu": _ticari_sezon(tarihler),
            "pazartesi_mi": tarihler.weekday == 0,
            "tatil_mi": [t.strftime("%Y-%m-%d") in sabitler.TATILLER for t in tarihler],
            "black_friday_mi": [t in black_friday for t in tarihler],
            "indirim_donemi_mi": _indirim_donemi(tarihler),
        }
    )


def takvim_tablosu() -> pd.DataFrame:
    """Yayımlanan takvim: yalnız pencere (BASLANGIC–BITIS, 1096 gün)."""
    tam = _takvim_uret(sabitler.BASLANGIC, sabitler.BITIS)
    return tam[
        ["tarih", "hafta", "ay", "yil", "sezon", "sezon_kodu", "tatil_mi", "indirim_donemi_mi"]
    ].reset_index(drop=True)


def simulasyon_takvimi() -> pd.DataFrame:
    """Isınma + uzatma dahil tam takvim; satır indisi = gün indisi.

    `D + UZATMA_GUN` satır: ısınmadan (0 = ISINMA_BASLANGIC) pencere
    sonundan UZATMA_GUN gün sonrasına kadar.
    """
    bitis_uzatilmis = sabitler.BITIS + pd.Timedelta(days=sabitler.UZATMA_GUN)
    tam = _takvim_uret(sabitler.ISINMA_BASLANGIC, bitis_uzatilmis)
    return tam[
        ["tarih", "hafta", "ay", "yil", "pazartesi_mi", "tatil_mi", "black_friday_mi"]
    ].reset_index(drop=True)


def gun_indisi(tarih) -> int:
    """Tarihin tam takvimdeki indisi (0 = ISINMA_BASLANGIC). Pencere dışı olabilir."""
    return int((pd.Timestamp(tarih) - pd.Timestamp(sabitler.ISINMA_BASLANGIC)).days)
