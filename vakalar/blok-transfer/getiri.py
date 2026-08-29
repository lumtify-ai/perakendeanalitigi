"""Bir transferin parasal getirisini hesaplar (spec 2026-08-28).

Model DEĞİŞMEZ. Bu dosya `degerlendirme.boru_hatti`'nın ürettiği planı okur
ve üstüne fayda hesabı geçer; çekirdeğe hiç dokunmaz. Sebebi şu: dizinin altı
yazısı "hangi mal nereye" sorusunu çözdü, bu hesap "o hareket para olarak ne
ediyor" sorusunu ayrı bir katmanda cevaplıyor.
"""
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

import senaryolar
from blok_transfer import degerlendirme
from blok_transfer.cekirdek.parametreler import Parametreler


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

PARAMETRELER = [
    {
        "ad": "alici_ihtimal",
        "etiket": "Alıcı mağazada satma ihtimali (%)",
        "degerler": [50, 60, 70, 80],
    },
    {
        "ad": "verici_ihtimal",
        "etiket": "Kalsaydı satma ihtimali (%)",
        "degerler": [0, 5, 10, 20],
    },
    {
        "ad": "maliyet_paketi",
        "etiket": "Toplama + kargo + yıpranma",
        "degerler": ["dusuk", "orta", "yuksek"],
        "deger_etiketleri": {"dusuk": "düşük", "orta": "orta", "yuksek": "yüksek"},
    },
]

HEDEF = (
    Path(__file__).resolve().parents[2]
    / "site" / "src" / "data" / "senaryolar" / "transfer-getirisi.json"
)


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
        # İki ayrı başabaş sayısı, karıştırılmasınlar diye ayrı ayrı duruyor.
        #
        # Fark: maliyeti karşılamak için alıcının vericiden kaç puan iyi
        # olması gerektiği. Yalnız maliyet paketine bağlıdır; iki olasılık
        # kadranından da bağımsızdır. Yönetsel kural budur.
        "basabas_fark_puan": round(maliyet / brut_kar * 100.0, 1),
        # İhtimal: aynı eşiğin mutlak hâli, yani seçilen vericinin üstüne
        # binmiş hâli. Okuyucunun seçtiği alıcı ihtimali bu barajı geçiyorsa
        # hücre kârlıdır. Verici kadranı çevrildikçe bu sayı da kayar.
        "basabas_ihtimal_yuzde": round(verici_ihtimal + maliyet / brut_kar * 100.0, 1),
    }


def hareketleri_getir(con, karar) -> pd.DataFrame:
    """Referans planın hareketlerini fiyat bilgisiyle zenginleştirir.

    Alış ve liste fiyatı `urun` tablosundan gelir; ikisi de ölçülen sayıdır,
    yani brüt kâr uydurma değildir.
    """
    plan, _ = degerlendirme.boru_hatti(con, karar, Parametreler(), "greedy")
    fiyatlar = con.execute(
        "select option_id, any_value(liste_fiyati) as liste, "
        "any_value(alis_fiyati) as alis from urun group by 1"
    ).df()
    zengin = plan.hareketler[["verici", "alici", "option_id", "adet"]].merge(
        fiyatlar, on="option_id", how="left"
    )
    # `how="left"` fiyatı bulunamayan option'ı sessizce NaN'a çevirir; brüt kâr
    # NaN olur, `net_kar_tl <= 0` gibi kontroller NaN'da sessizce geçer ve
    # yayımlanan sayı fark edilmeden bozulur. Erken ve anlaşılır patlasın.
    eksik = zengin[zengin.liste.isna() | zengin.alis.isna()]
    if len(eksik):
        ornek = sorted(set(eksik.option_id))[:5]
        raise ValueError(
            f"{len(eksik)} harekette fiyat bulunamadı (urun tablosunda karşılığı "
            f"yok): option {ornek}"
        )
    return zengin


def uret(con, karar) -> dict:
    hareketler = hareketleri_getir(con, karar)
    sonuclar = {}
    for alici in PARAMETRELER[0]["degerler"]:
        for verici in PARAMETRELER[1]["degerler"]:
            for paket_adi in PARAMETRELER[2]["degerler"]:
                ozet = hesapla(
                    hareketler, MALIYET_PAKETLERI[paket_adi], float(alici), float(verici)
                )
                sonuclar[f"{alici}|{verici}|{paket_adi}"] = {
                    "ozet": ozet,
                    "satirlar": [],
                }
    return {
        "surum": senaryolar._surum(),
        "parametreler": PARAMETRELER,
        "sonuclar": sonuclar,
    }


if __name__ == "__main__":
    from blok_transfer.cekirdek import veri

    baglanti = veri.baglan()
    senaryolar.yaz(uret(baglanti, veri.karar_tarihi(baglanti)), HEDEF)
    print(f"yazildi: {HEDEF}")
