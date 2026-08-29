"""Bir transferin parasal getirisini hesaplar (spec 2026-08-28).

Model DEĞİŞMEZ. Bu dosya `degerlendirme.boru_hatti`'nın ürettiği planı okur
ve üstüne fayda hesabı geçer; çekirdeğe hiç dokunmaz. Sebebi şu: dizinin altı
yazısı "hangi mal nereye" sorusunu çözdü, bu hesap "o hareket para olarak ne
ediyor" sorusunu ayrı bir katmanda cevaplıyor.
"""
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Paket:
    """Bir transferin birim maliyetleri.

    Toplama ve kargo varsayımdır (veride karşılığı yok, okuyucu kadrandan
    seçer). Yıpranma oranı saha kalibrasyonudur: bir ürün her transferde
    maliyet değerinin yaklaşık %5'i kadar değer kaybeder.
    """
    toplama_birim_tl: float
    kargo_rota_tl: float
    yipranma_orani: float       # maliyet değerinin oranı


MALIYET_PAKETLERI = {
    "dusuk": Paket(5.0, 300.0, 0.03),
    "orta": Paket(10.0, 500.0, 0.05),
    "yuksek": Paket(20.0, 900.0, 0.08),
}


def hesapla(
    hareketler: pd.DataFrame, paket: Paket, alici_ihtimal: float, verici_ihtimal: float
) -> dict[str, float]:
    """Planın getirisi: olasılık farkı × brüt kâr − maliyetler.

    Olasılıklar kadrandan gelir, adetler ve fiyatlar gerçek plandan. Kadran
    bu yüzden uydurma bir örneği değil, yayımlanmış planın kendisini yeniden
    değerler.
    """
    if not len(hareketler):
        raise ValueError("Getiri hesaplanamaz: hareket listesi boş.")

    adet = hareketler.adet
    brut_kar = float((adet * (hareketler.liste - hareketler.alis)).sum())
    ciro = float((adet * hareketler.liste).sum())
    maliyet_degeri = float((adet * hareketler.alis).sum())
    rota_sayisi = len(hareketler.groupby(["verici", "alici"]))

    maliyet = (
        paket.toplama_birim_tl * int(adet.sum())
        + paket.kargo_rota_tl * rota_sayisi
        + paket.yipranma_orani * maliyet_degeri
    )
    fark = (alici_ihtimal - verici_ihtimal) / 100.0
    net = fark * brut_kar - maliyet

    return {
        "net_kar_tl": round(net, 2),
        "ciro_etkisi_tl": round(fark * ciro, 2),
        "hareket_basina_kar_tl": round(net / len(hareketler), 2),
        # Başabaş, alıcı kadranından bağımsızdır: maliyeti karşılamak için
        # alıcının vericiden kaç puan iyi olması gerektiğini söyler.
        "basabas_ihtimal_yuzde": round(verici_ihtimal + maliyet / brut_kar * 100.0, 1),
    }
