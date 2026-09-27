"""v4 kampanya takvimi, gizli esneklik ve günün fiyatı.

Fiyat üç kaynaktan oynar (spec §5.2): **markdown** (Lumoda kuralı, içsel,
Görev 10), **kampanya** (dışsal, bu modül) ve **işlem indirimi** (tam
fiyatlı satışta rastgele, v3'teki gibi). Kampanya takvimi kasıtlı olarak
**talepten bağımsız** çekilir — kendi alt rng'sini alır (dünya akışından
değil; Görev 11 dünya rng'sinden ayrı bir çocuk üreteç `spawn()`lar) — ki
gelecekteki bir esneklik kestirimi kampanyayı temiz (dışsal) fiyat
varyasyonu olarak kullanabilsin; markdown bilerek içsel kalır (spec'in
"esneklik tuzağı" örneği).

Gizli esneklik ε kategori × gelir düzeyine bağlıdır ve hiçbir dışa
aktarılan tabloya girmez (yalnız iç hesaplamada, `fiyat_carpani` ile
talebe uygulanır).

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §5.2
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-9-brief.md

v4 hiçbir v2/v3/kök modülünü içe aktarmaz.
"""

import bisect
from datetime import date
from typing import Callable

import numpy as np
import pandas as pd

from . import sabitler
from .takvim import gun_indisi

# ---------------------------------------------------------------------------
# kampanyalari_uret
# ---------------------------------------------------------------------------

# Simülasyonun dokunduğu her takvim yılı için pencere ve o yılın hedef
# sayılarının payı (2022 yalnız ısınmanın ikinci yarısı, "yarım yıl" —
# controller kararı: BF tam, kategori/ikinci ürün yarı sayıda).
_YIL_PENCERELERI: dict[int, tuple[date, date, float]] = {
    2022: (date(2022, 7, 1), date(2022, 12, 31), 0.5),
    2023: (date(2023, 1, 1), date(2023, 12, 31), 1.0),
    2024: (date(2024, 1, 1), date(2024, 12, 31), 1.0),
    2025: (date(2025, 1, 1), date(2025, 12, 31), 1.0),
}

# Black Friday tarihleri yıl → tarih (sabitler.BLACK_FRIDAY sırayla 2022-2025).
_BF_YIL: dict[int, date] = {2022 + i: d for i, d in enumerate(sabitler.BLACK_FRIDAY)}


def _yillik_hedef(taban: int, pay: float) -> int:
    return max(0, round(taban * pay))


def _kategori_kampanyalari(
    rng: np.random.Generator,
    yil: int,
    pencere_bas: date,
    pencere_son: date,
    adet: int,
    ust_kategoriler: list[str],
    bolgeler: list[str],
    sira_baslangic: int,
) -> list[dict]:
    """`adet` kategori kampanyası: rastgele üst kategori × rastgele 2-4
    bölge, 7-14 gün, oran %20/30/40; yarısı yalnız Basic/NOS ile
    sınırlıdır (kapsam_line)."""
    pencere_bas = pd.Timestamp(pencere_bas)
    pencere_gun = (pencere_son - pencere_bas.date()).days + 1
    alt, ust = sabitler.KAMPANYA_KATEGORI_GUN_ARALIGI
    bolge_alt, bolge_ust = sabitler.KAMPANYA_KATEGORI_BOLGE_ARALIGI
    yalniz_basic_nos_sayisi = adet // 2

    satirlar = []
    for i in range(adet):
        sure = int(rng.integers(alt, ust + 1))
        ofset = int(rng.integers(0, max(1, pencere_gun - sure + 1)))
        baslangic = pencere_bas + pd.Timedelta(int(ofset), unit="D")
        bitis = baslangic + pd.Timedelta(int(sure - 1), unit="D")

        ust_kat = str(rng.choice(ust_kategoriler))
        n_bolge = int(rng.integers(bolge_alt, bolge_ust + 1))
        secilen_bolge = sorted(
            rng.choice(bolgeler, size=min(n_bolge, len(bolgeler)), replace=False)
        )

        kapsam_line = "Basic,NOS" if i < yalniz_basic_nos_sayisi else ""
        oran = float(rng.choice(sabitler.KAMPANYA_KATEGORI_ORANLARI))

        satirlar.append(
            {
                "kampanya_id": f"KAT{yil}_{sira_baslangic + i:02d}",
                "tip": "kategori",
                "baslangic": pd.Timestamp(baslangic),
                "bitis": pd.Timestamp(bitis),
                "kapsam_ust_kategori": ust_kat,
                "kapsam_line": kapsam_line,
                "kapsam_bolge": ",".join(secilen_bolge),
                "oran": oran,
            }
        )
    return satirlar


def _ikinci_urun_kampanyalari(
    rng: np.random.Generator,
    yil: int,
    pencere_bas: date,
    pencere_son: date,
    adet: int,
    sira_baslangic: int,
) -> list[dict]:
    """`adet` "ikinci ürüne" kampanyası: 10 gün, bütün kapsam boş (zincir
    genelinde); `oran` etkin değeri (%25) saklanır, tip (`ikinci_urun`)
    mekaniği anlatır."""
    pencere_bas = pd.Timestamp(pencere_bas)
    pencere_gun = (pencere_son - pencere_bas.date()).days + 1
    sure = sabitler.KAMPANYA_IKINCI_URUN_GUN

    satirlar = []
    for i in range(adet):
        ofset = int(rng.integers(0, max(1, pencere_gun - sure + 1)))
        baslangic = pencere_bas + pd.Timedelta(int(ofset), unit="D")
        bitis = baslangic + pd.Timedelta(int(sure - 1), unit="D")
        satirlar.append(
            {
                "kampanya_id": f"IKI{yil}_{sira_baslangic + i:02d}",
                "tip": "ikinci_urun",
                "baslangic": pd.Timestamp(baslangic),
                "bitis": pd.Timestamp(bitis),
                "kapsam_ust_kategori": "",
                "kapsam_line": "",
                "kapsam_bolge": "",
                "oran": sabitler.KAMPANYA_IKINCI_URUN_ORAN_ETKIN,
            }
        )
    return satirlar


def _black_friday_kampanyasi(yil: int) -> dict:
    """4 gün (Cuma..Pazartesi dahil), %30, tüm zincir ve online (kapsam
    boş)."""
    cuma = pd.Timestamp(_BF_YIL[yil])
    pazartesi = cuma + pd.Timedelta(int(sabitler.KAMPANYA_BF_GUN - 1), unit="D")
    return {
        "kampanya_id": f"BF{yil}",
        "tip": "black_friday",
        "baslangic": pd.Timestamp(cuma),
        "bitis": pd.Timestamp(pazartesi),
        "kapsam_ust_kategori": "",
        "kapsam_line": "",
        "kapsam_bolge": "",
        "oran": sabitler.KAMPANYA_BF_ORANI,
    }


def kampanyalari_uret(
    rng: np.random.Generator, magazalar: pd.DataFrame, optionlar: pd.DataFrame
) -> pd.DataFrame:
    """`kampanya` tablosu: Black Friday + kategori + "ikinci ürün"
    kampanyaları, simülasyonun dokunduğu her takvim yılı için (2022'nin
    ikinci yarısı dahil).

    Takvim **talepten tamamen bağımsız** çekilir: `rng` dünya akışından
    değil, kendine özgü bir alt üreteçtir (bkz. modül docstring'i);
    indirim dönemleriyle (markdown) çakışmaya kasıtlı olarak izin verilir.
    """
    ust_kategoriler = sorted(optionlar["ust_kategori"].unique())
    bolgeler = sorted(magazalar.loc[magazalar.tip != "Online", "bolge"].unique())

    satirlar: list[dict] = []
    for yil in sorted(_YIL_PENCERELERI):
        pencere_bas, pencere_son, pay = _YIL_PENCERELERI[yil]

        satirlar.append(_black_friday_kampanyasi(yil))

        kategori_adet = _yillik_hedef(sabitler.KAMPANYA_KATEGORI_YIL, pay)
        satirlar.extend(
            _kategori_kampanyalari(
                rng, yil, pencere_bas, pencere_son, kategori_adet,
                ust_kategoriler, bolgeler, sira_baslangic=1,
            )
        )

        ikinci_adet = _yillik_hedef(sabitler.KAMPANYA_IKINCI_URUN_YIL, pay)
        satirlar.extend(
            _ikinci_urun_kampanyalari(
                rng, yil, pencere_bas, pencere_son, ikinci_adet, sira_baslangic=1,
            )
        )

    df = pd.DataFrame(satirlar)
    df["baslangic"] = pd.to_datetime(df["baslangic"])
    df["bitis"] = pd.to_datetime(df["bitis"])
    return df.sort_values("baslangic").reset_index(drop=True)


# ---------------------------------------------------------------------------
# esneklik
# ---------------------------------------------------------------------------


def esneklik(gizli_magaza: pd.DataFrame, optionlar: pd.DataFrame) -> np.ndarray:
    """`[M, O]` gizli fiyat esnekliği ε.

    ε = ESNEKLIK_UST[ust_kategori] × ESNEKLIK_GELIR[gelir]; outlet
    segmentinde ayrıca × ESNEKLIK_OUTLET_CARPANI. ONL zaten `gelir="orta"`
    taşır (bkz. `magaza.magazalari_uret`), ayrı bir özel durum gerekmez.
    Hiçbir dışa aktarılan tabloya girmez.
    """
    ust_carpan = optionlar["ust_kategori"].map(sabitler.ESNEKLIK_UST).to_numpy(dtype=float)
    gelir_carpan = gizli_magaza["gelir"].map(sabitler.ESNEKLIK_GELIR).to_numpy(dtype=float)
    outlet_mi = (gizli_magaza["segment"] == "outlet").to_numpy()
    gelir_carpan = np.where(outlet_mi, gelir_carpan * sabitler.ESNEKLIK_OUTLET_CARPANI, gelir_carpan)
    return np.outer(gelir_carpan, ust_carpan)


# ---------------------------------------------------------------------------
# kampanya_orani / kampanya_takvimi
# ---------------------------------------------------------------------------


def _kapsam_maskesi(degerler: np.ndarray, kapsam: str) -> np.ndarray:
    """Boş kapsam = hepsi; aksi halde virgülle ayrılmış kümeye üyelik."""
    if not kapsam:
        return np.ones(len(degerler), dtype=bool)
    kume = set(kapsam.split(","))
    return np.isin(degerler, list(kume))


def kampanya_orani(
    kampanya: pd.DataFrame, d: int, magazalar: pd.DataFrame, optionlar: pd.DataFrame
) -> np.ndarray:
    """`[M, O]` o gün geçerli en yüksek kampanya oranı (seyrek işlem; Black
    Friday'in trafik çarpanı Görev 8'de, burada değil).

    Bölgesel kapsam (`kapsam_bolge` boş değilse) yalnız fiziksel mağazalara
    uygulanır — boş kapsam (= hepsi) dışında ONL hiçbir bölgesel kampanyaya
    girmez (controller kararı)."""
    M, O = len(magazalar), len(optionlar)
    oran = np.zeros((M, O), dtype=float)

    tarih = pd.Timestamp(sabitler.ISINMA_BASLANGIC) + pd.Timedelta(int(d), unit="D")
    aktif = kampanya[(kampanya.baslangic <= tarih) & (kampanya.bitis >= tarih)]
    if aktif.empty:
        return oran

    bolge = magazalar["bolge"].to_numpy()
    online_mi = (magazalar["tip"] == "Online").to_numpy()
    ust_kat = optionlar["ust_kategori"].to_numpy()
    line = optionlar["line"].to_numpy()

    for k in aktif.itertuples():
        if k.kapsam_bolge:
            m_maske = _kapsam_maskesi(bolge, k.kapsam_bolge) & ~online_mi
        else:
            m_maske = np.ones(M, dtype=bool)
        o_maske = _kapsam_maskesi(ust_kat, k.kapsam_ust_kategori) & _kapsam_maskesi(
            line, k.kapsam_line
        )
        if not m_maske.any() or not o_maske.any():
            continue
        hucre = np.ix_(m_maske, o_maske)
        oran[hucre] = np.maximum(oran[hucre], k.oran)
    return oran


def kampanya_takvimi(
    kampanya: pd.DataFrame, magazalar: pd.DataFrame, optionlar: pd.DataFrame, gun_sayisi: int
) -> Callable[[int], np.ndarray]:
    """`kampanya_orani`nin gün başına yeniden hesaplanmasını önlemek için:
    yalnız kampanya başlangıç/bitişlerinde değişen değerleri önceden
    hesaplar, gün sorgusunu en yakın (≤ d) değişim gününe eşler.

    Dönen dizi salt okunurdur (paylaşılan önbellek, motor değiştirmemeli).
    """
    degisim_gunleri = {0}
    for row in kampanya.itertuples():
        bas_gun = gun_indisi(row.baslangic)
        bit_gun = gun_indisi(row.bitis) + 1  # kampanya biter, oran düşebilir
        if 0 <= bas_gun < gun_sayisi:
            degisim_gunleri.add(bas_gun)
        if 0 <= bit_gun < gun_sayisi:
            degisim_gunleri.add(bit_gun)
    sirali_gunler = sorted(degisim_gunleri)

    onbellek: dict[int, np.ndarray] = {}
    for g in sirali_gunler:
        arr = kampanya_orani(kampanya, g, magazalar, optionlar)
        arr.setflags(write=False)
        onbellek[g] = arr

    def sorgula(d: int) -> np.ndarray:
        idx = bisect.bisect_right(sirali_gunler, d) - 1
        idx = max(idx, 0)
        return onbellek[sirali_gunler[idx]]

    return sorgula


# ---------------------------------------------------------------------------
# gunun_fiyati / fiyat_carpani
# ---------------------------------------------------------------------------


def gunun_fiyati(
    liste: np.ndarray, md: np.ndarray, kamp: np.ndarray, islem: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Günün birim fiyatı ve uygulanan indirim oranı.

    `oran = max(md, kamp)`; markdown ve kampanya toplanmaz, en yükseği
    geçerli olur. Bu ikisi de 0 ise (tam fiyat) `islem` (rastgele işlem
    indirimi) devreye girer: `ISLEM_INDIRIM_ORANI` (%30). `birim =
    liste × (1 − oran)`.
    """
    liste = np.asarray(liste, dtype=float)
    md = np.asarray(md, dtype=float)
    kamp = np.asarray(kamp, dtype=float)
    islem = np.asarray(islem, dtype=bool)

    oran = np.maximum(md, kamp)
    oran = np.where(oran > 0, oran, np.where(islem, sabitler.ISLEM_INDIRIM_ORANI, 0.0))
    birim = liste * (1.0 - oran)
    return birim, oran


def fiyat_carpani(oran: np.ndarray, eps: np.ndarray) -> np.ndarray:
    """`(1 − oran)^(−eps)`: fiyat düştükçe (oran arttıkça) talep çarpanı
    büyür (eps > 0 için); ε burada dışarıdan (gizli `esneklik`ten) gelir."""
    oran = np.asarray(oran, dtype=float)
    eps = np.asarray(eps, dtype=float)
    return np.power(1.0 - oran, -eps)
