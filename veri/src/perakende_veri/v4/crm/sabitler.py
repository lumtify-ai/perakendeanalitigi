"""B'nin sabitleri. A her zaman `v4.sabitler.TOHUM` (2026) ile kurulur."""

import numpy as np

from .. import sabitler as _a

CRM_TOHUM = 4242

# ---------------------------------------------------------------------------
# Müşteri nüfusu (Görev 2, spec §2). Bütün sayısal değerler KALİBRASYON
# (Görev 14 ayarlar); gerekçeler satır yorumlarında. Karışım tutarlılığı
# `nufus.karisim_ozeti()` ile ölçülür (test_nufus.test_karisim_hedefleri):
# nüfus ortalaması yıllık ziyaret ~3, mağaza sepeti ~2,2, online ~1,8, kart
# okutma (mağaza ziyareti ağırlıklı) %50–60.
# ---------------------------------------------------------------------------

ARKETIPLER = [
    "trend_avcisi", "indirim_avcisi", "klasik_temelci", "aile_alisverisci",
    "premium_sadik", "online_tutkunu", "gelip_gecen",
]

# A'nın 17 alt kategorisi, `KATEGORILER` sırasıyla (tercih_kat sütunları).
ALT_KATEGORILER: list[str] = [a for alts in _a.KATEGORILER.values() for a in alts]
KALIPLAR: list[str] = list(_a.OZNITELIKLER["kalip"])        # slim, regular, relaxed, oversize
DESENLER: list[str] = list(_a.OZNITELIKLER["desen"])        # düz, çizgili, kareli, baskılı, çiçekli
FIYAT_SEGMENTLERI: list[str] = list(_a.OZNITELIKLER["fiyat_segmenti"])  # giris, orta, premium

YAS_GRUPLARI = ["18-24", "25-34", "35-44", "45-54", "55+"]
CINSIYETLER = ["Kadın", "Erkek"]
KAYIT_KANALLARI = ["magaza", "online"]   # kayit_kanali 0 / 1

# Zincirin genel alt kategori popülerliği (A'nın çeşit derinliğine kabaca
# uyar: tişört/jean/pantolon geniş, tulum/şal/kemer dar). Arketip vektörü =
# bu taban × arketip eğimi. KALİBRASYON
_KAT_TABAN = {
    "Tişört": 1.4, "Gömlek": 1.0, "Bluz": 0.9, "Kazak": 0.9, "Sweatshirt": 0.9,
    "Pantolon": 1.1, "Jean": 1.2, "Etek": 0.6, "Şort": 0.6,
    "Elbise": 0.9, "Tulum": 0.3,
    "Mont": 0.5, "Ceket": 0.5, "Trençkot": 0.3,
    "Çanta": 0.5, "Şal": 0.3, "Kemer": 0.3,
}


def _kat(**egim: float) -> list[float]:
    """Taban popülerlik × arketip eğimi (verilmeyen alt kategori 1)."""
    return [_KAT_TABAN[a] * egim.get(a, 1.0) for a in ALT_KATEGORILER]


# Anahtarlar:
#   ziyaret_gamma      (şekil, ölçek) yıllık ziyaret hızı (bütün kanallar);
#                      ortalama = şekil × ölçek
#   sepet_ort          mağaza fişi başına ortalama adet; bireysel
#                      1 + Gamma(SEPET_SEKIL, (sepet_ort − 1)/SEPET_SEKIL)
#   kart_beta          (a, b) mağazada kart okutma olasılığı
#   online_beta        (a, b) ziyaretlerin online payı
#   terk_beta          (a, b) aylık terk olasılığı
#   indirim_beta       (a, b) indirim duyarlılığı [0, 1]
#   fiyat_segment      giris/orta/premium eğilim ortası (Dirichlet)
#   kategori           17 alt kategori ağırlığı (Dirichlet ortası, normalize edilir)
#   kalip, desen       öznitelik eğilim ortaları (KALIPLAR, DESENLER sırası)
#   beden_dagin        beden sırası sapmasının ölçeği (sıra birimi; aile
#                      yüksek: başkası için de alır)
#   yas                YAS_GRUPLARI olasılıkları
ARKETIP_PARAMETRE: dict[str, dict] = {
    # Genç, sık gelen, yeniliğe duyarlı; baskılı/oversize, bluz, elbise,
    # sweatshirt, jean. Online'a yatkın, terki orta.
    "trend_avcisi": {
        "ziyaret_gamma": (2.0, 2.0),        # KALİBRASYON ort. 4,0/yıl
        "sepet_ort": 2.2,                   # KALİBRASYON
        "kart_beta": (5.0, 4.5),            # KALİBRASYON ort. 0,53
        "online_beta": (3.0, 5.0),          # KALİBRASYON ort. 0,38
        "terk_beta": (2.0, 60.0),           # KALİBRASYON ort. 0,032/ay
        "indirim_beta": (2.0, 5.0),         # KALİBRASYON ort. 0,29
        "fiyat_segment": [0.25, 0.50, 0.25],  # KALİBRASYON
        "kategori": _kat(Bluz=1.5, Elbise=1.6, Sweatshirt=1.5, Jean=1.3, Tulum=1.8,
                         Şort=1.4, Gömlek=0.7, Pantolon=0.7, Trençkot=0.7),  # KALİBRASYON
        "kalip": [0.25, 0.15, 0.20, 0.40],  # KALİBRASYON oversize/slim
        "desen": [0.20, 0.15, 0.10, 0.35, 0.20],  # KALİBRASYON baskılı
        "beden_dagin": 0.35,                # KALİBRASYON
        "yas": [0.40, 0.38, 0.14, 0.06, 0.02],
    },
    # Kampanya ve outlet peşinde; büyük sepet, giriş segmenti; kartı
    # okutur (sadakat indirimi).
    "indirim_avcisi": {
        "ziyaret_gamma": (1.5, 1.8),        # KALİBRASYON ort. 2,7/yıl
        "sepet_ort": 2.4,                   # KALİBRASYON
        "kart_beta": (6.0, 4.0),            # KALİBRASYON ort. 0,60
        "online_beta": (2.0, 7.0),          # KALİBRASYON ort. 0,22
        "terk_beta": (2.0, 50.0),           # KALİBRASYON ort. 0,038/ay
        "indirim_beta": (8.0, 2.0),         # KALİBRASYON ort. 0,80
        "fiyat_segment": [0.55, 0.37, 0.08],  # KALİBRASYON
        "kategori": _kat(Tişört=1.2, Jean=1.2, Mont=1.3, Kazak=1.2, Trençkot=0.6),  # KALİBRASYON
        "kalip": [0.20, 0.40, 0.25, 0.15],  # KALİBRASYON
        "desen": [0.35, 0.20, 0.15, 0.18, 0.12],  # KALİBRASYON
        "beden_dagin": 0.45,                # KALİBRASYON
        "yas": [0.18, 0.30, 0.26, 0.17, 0.09],
    },
    # Temel parçalar: tişört, gömlek, pantolon, jean, kazak; düz, regular;
    # sadık ama seyrek, düşük terk; mağazacı.
    "klasik_temelci": {
        "ziyaret_gamma": (3.0, 0.9),        # KALİBRASYON ort. 2,7/yıl
        "sepet_ort": 2.0,                   # KALİBRASYON
        "kart_beta": (5.0, 5.0),            # KALİBRASYON ort. 0,50
        "online_beta": (1.5, 9.0),          # KALİBRASYON ort. 0,14
        "terk_beta": (2.0, 90.0),           # KALİBRASYON ort. 0,022/ay
        "indirim_beta": (3.0, 5.0),         # KALİBRASYON ort. 0,38
        "fiyat_segment": [0.30, 0.55, 0.15],  # KALİBRASYON
        "kategori": _kat(Tişört=1.3, Gömlek=1.6, Pantolon=1.5, Jean=1.2, Kazak=1.3,
                         Kemer=1.5, Bluz=0.6, Elbise=0.5, Tulum=0.3, Şort=0.7),  # KALİBRASYON
        "kalip": [0.15, 0.55, 0.22, 0.08],  # KALİBRASYON regular
        "desen": [0.55, 0.18, 0.15, 0.07, 0.05],  # KALİBRASYON düz
        "beden_dagin": 0.30,                # KALİBRASYON
        "yas": [0.05, 0.20, 0.30, 0.27, 0.18],
    },
    # Aile için alır: büyük sepet, dağınık beden, giriş/orta segment,
    # geniş kategori; indirime orta-yüksek duyarlı.
    "aile_alisverisci": {
        "ziyaret_gamma": (2.0, 1.4),        # KALİBRASYON ort. 2,8/yıl
        "sepet_ort": 2.7,                   # KALİBRASYON
        "kart_beta": (6.0, 4.5),            # KALİBRASYON ort. 0,57
        "online_beta": (2.0, 8.0),          # KALİBRASYON ort. 0,20
        "terk_beta": (2.0, 80.0),           # KALİBRASYON ort. 0,024/ay
        "indirim_beta": (5.0, 4.0),         # KALİBRASYON ort. 0,56
        "fiyat_segment": [0.48, 0.44, 0.08],  # KALİBRASYON
        "kategori": _kat(Tişört=1.3, Sweatshirt=1.3, Şort=1.3, Pantolon=1.2, Mont=1.2,
                         Trençkot=0.5, Şal=0.7),  # KALİBRASYON
        "kalip": [0.12, 0.45, 0.33, 0.10],  # KALİBRASYON
        "desen": [0.35, 0.20, 0.15, 0.20, 0.10],  # KALİBRASYON
        "beden_dagin": 1.40,                # KALİBRASYON yüksek (spec §2)
        "yas": [0.02, 0.22, 0.44, 0.24, 0.08],
    },
    # Yüksek gelirli, sık gelen, sadık; premium segment, ceket/trençkot/
    # gömlek/çanta; kartı hemen hep okutur, indirime duyarsız, terk düşük.
    "premium_sadik": {
        "ziyaret_gamma": (3.0, 1.5),        # KALİBRASYON ort. 4,5/yıl
        "sepet_ort": 2.0,                   # KALİBRASYON
        "kart_beta": (7.0, 3.0),            # KALİBRASYON ort. 0,70
        "online_beta": (3.0, 6.0),          # KALİBRASYON ort. 0,33
        "terk_beta": (1.5, 110.0),          # KALİBRASYON ort. 0,013/ay
        "indirim_beta": (2.0, 8.0),         # KALİBRASYON ort. 0,20
        "fiyat_segment": [0.05, 0.35, 0.60],  # KALİBRASYON
        "kategori": _kat(Ceket=2.0, Trençkot=2.5, Gömlek=1.4, Çanta=1.8, Şal=1.6,
                         Elbise=1.2, Tişört=0.7, Sweatshirt=0.5, Şort=0.6),  # KALİBRASYON
        "kalip": [0.40, 0.40, 0.15, 0.05],  # KALİBRASYON slim/regular
        "desen": [0.50, 0.20, 0.15, 0.05, 0.10],  # KALİBRASYON
        "beden_dagin": 0.30,                # KALİBRASYON
        "yas": [0.04, 0.24, 0.34, 0.26, 0.12],
    },
    # Ağırlıkla online; küçük sepet (online fiş ~1,8), sık ziyaret, kartı
    # mağazada seyrek okutur; terki görece yüksek.
    "online_tutkunu": {
        "ziyaret_gamma": (2.0, 2.0),        # KALİBRASYON ort. 4,0/yıl
        "sepet_ort": 2.0,                   # KALİBRASYON
        "kart_beta": (4.0, 4.0),            # KALİBRASYON ort. 0,50
        "online_beta": (8.0, 2.0),          # KALİBRASYON ort. 0,80
        "terk_beta": (2.0, 55.0),           # KALİBRASYON ort. 0,035/ay
        "indirim_beta": (4.0, 4.0),         # KALİBRASYON ort. 0,50
        "fiyat_segment": [0.30, 0.50, 0.20],  # KALİBRASYON
        "kategori": _kat(Elbise=1.3, Bluz=1.2, Tişört=1.2, Çanta=1.3, Mont=0.8),  # KALİBRASYON
        "kalip": [0.25, 0.30, 0.25, 0.20],  # KALİBRASYON
        "desen": [0.25, 0.15, 0.10, 0.25, 0.25],  # KALİBRASYON
        "beden_dagin": 0.40,                # KALİBRASYON
        "yas": [0.28, 0.40, 0.20, 0.09, 0.03],
    },
    # Bir iki kez gelir (turist, hediye, tesadüf): düşük hız, yüksek terk,
    # kartı az okutur; tercihleri tabana yakın.
    "gelip_gecen": {
        "ziyaret_gamma": (1.2, 1.2),        # KALİBRASYON ort. 1,44/yıl
        "sepet_ort": 1.8,                   # KALİBRASYON
        "kart_beta": (3.0, 5.0),            # KALİBRASYON ort. 0,38
        "online_beta": (1.5, 7.0),          # KALİBRASYON ort. 0,18
        "terk_beta": (2.0, 16.0),           # KALİBRASYON ort. 0,11/ay
        "indirim_beta": (3.0, 4.0),         # KALİBRASYON ort. 0,43
        "fiyat_segment": [0.38, 0.45, 0.17],  # KALİBRASYON
        "kategori": _kat(Şal=1.5, Çanta=1.3, Tişört=1.2, Şort=1.3),  # KALİBRASYON
        "kalip": [0.25, 0.35, 0.25, 0.15],  # KALİBRASYON
        "desen": [0.30, 0.18, 0.14, 0.20, 0.18],  # KALİBRASYON
        "beden_dagin": 0.45,                # KALİBRASYON
        "yas": [0.22, 0.30, 0.22, 0.16, 0.10],
    },
}

# Bireysel heterojenlik (Dirichlet toplam yoğunluğu: küçük = dağınık).
KATEGORI_YOGUNLUK = 10.0   # KALİBRASYON 17 kategori; tipler ayrışsın ama bireyler dağınık
OZNITELIK_YOGUNLUK = 8.0   # KALİBRASYON kalıp, desen
FIYAT_YOGUNLUK = 10.0      # KALİBRASYON
SEPET_SEKIL = 4.0          # KALİBRASYON sepet_ort − 1 ~ Gamma(4, ·): CV 0,5
BEDEN_DAGIN_SIGMA = 0.25   # KALİBRASYON bireysel beden_dagin lognormal σ
ALT_BEDEN_KAYMA = [0.2, 0.6, 0.2]  # KALİBRASYON alt beden = üst + (−1, 0, +1)
ONLINE_SEPET_CARPANI = 0.82  # KALİBRASYON online fiş ≈ mağaza sepeti × 0,82 (2,2 → 1,8)
ERKEK_KADIN_KAT_CARPANI = 0.1  # KALİBRASYON erkek müşteride yalnız-kadın alt kategoriler (hediye)
ONL_KADIN_PAYI = 0.58      # KALİBRASYON ONL üyelerinde kadın payı (zincirin kadın ürün payına yakın)

# Mağaza segmenti (A §2.3) + online → arketip olasılıkları (ARKETIPLER
# sırası). İlişkili ama birebir değil: her segmentin baskın tipi ayrı, hiçbiri
# %60'ı geçmez. KALİBRASYON
#                           trend indirim klasik aile premium online gelip
SEGMENT_ARKETIP_KARISIM: dict[str, np.ndarray] = {
    "metropol_premium": np.array([0.18, 0.07, 0.18, 0.10, 0.30, 0.07, 0.10]),
    "metropol_genc":    np.array([0.34, 0.13, 0.12, 0.08, 0.08, 0.10, 0.15]),
    "anadolu_aile":     np.array([0.08, 0.18, 0.22, 0.32, 0.04, 0.04, 0.12]),
    "sicak_sahil":      np.array([0.15, 0.14, 0.16, 0.14, 0.08, 0.04, 0.29]),
    "soguk_iklim":      np.array([0.08, 0.16, 0.34, 0.24, 0.05, 0.03, 0.10]),
    "outlet":           np.array([0.06, 0.42, 0.14, 0.20, 0.02, 0.03, 0.13]),
    "online":           np.array([0.18, 0.14, 0.08, 0.06, 0.08, 0.38, 0.08]),
}

# --- nufus_baslat boyutu (spec §2) --------------------------------------------
BASLAT_GUN = 28            # ısınmanın ilk 28 günü
BASLAT_PAYI = 1.2          # beklenen ziyaret ≥ 1,2 × fiş talebi
SEPET_HEDEF_MAGAZA = 2.2   # spec §2, §8 (Görev 5'in fiş sayısı hedefiyle aynı)
SEPET_HEDEF_ONLINE = 1.8
KAYIT_GECMISI_UST_GUN = 3650  # başlangıç tabanında kayıt en çok 10 yıl önce

# --- Katılış (spec §4) --------------------------------------------------------
# λ_m(d) = TABAN × V28_m(d) × çarpan_m(d); V28 = son 28 günün (bugün dahil,
# mağazanın açılışından önceki günler sayılmaz) günlük ortalama adedi × 28.
# Kararlı durumda katılış terki karşılamalı: yıllık terk ≈ 12 × E[terk] ≈
# 0,45 (karışım), nüfus ≈ yıllık fiş / E[hız] ≈ V_yıl / (2,2 × 3) →
# yıllık katılış ≈ 0,45 V_yıl / 6,6 ≈ 0,068 V_yıl; Σ_yıl V28 ≈ 28 V_yıl,
# ortalama çarpan ~1,15 → TABAN ≈ 0,068 / 28 / 1,15 ≈ 0,0021. Zincir %6
# büyüdüğünden eksik kalan Görev 5'in "uygun müşteri yetmezse ekle" yoluyla
# kapanır; Görev 14 yeni müşteri payı bandına (%25–40) göre ayarlar.
KATILIS_TABAN = 0.0021         # KALİBRASYON mağaza, adet başına
KATILIS_TABAN_ONLINE = 0.0021  # KALİBRASYON ONL, adet başına
KATILIS_PENCERE = 28
KATILIS_BF_CARPANI = 3.0       # KALİBRASYON BF kampanya günleri (Cuma–Pazartesi)
KATILIS_KAMPANYA_CARPANI = 1.5  # KALİBRASYON mağazanın bölgesini kapsayan herhangi bir kampanya
KATILIS_ACILIS_CARPANI = 3.0   # KALİBRASYON açılışın ilk KATILIS_ACILIS_HAFTA haftası
KATILIS_ACILIS_HAFTA = 12

# --- Yaşam döngüsü (Görev 4, spec §4) -------------------------------------------
# Aylık terk çekilişinin tetik çarpanları (çarpılır, p en çok TERK_P_UST).
# Değerler spec'ten (global kısıtlar), kalibrasyon düğmesi değil.
STOKSUZLUK_GUN = 60          # stoksuzluktan sonra pencere (gün, dahil)
STOKSUZLUK_CARPANI = 1.5
IADE_GUN = 90                # son iadeden sonra pencere (gün, dahil)
IADE_CARPANI = 1.2
BEDEN_UYUMSUZ_ESIGI = 2      # tekrarlayan beden uyumsuzluğu (≥ 2)
BEDEN_UYUMSUZ_CARPANI = 1.3
EV_KAPANIS_CARPANI = 2.0     # ev mağazası kapandı, geçiş yapmadı
TERK_P_UST = 0.95
EV_GECIS_OLASILIGI = 0.6     # KALİBRASYON ilde açık mağaza varsa en yakınına geçiş
EV_KAPANIS_ONLINE_CARPANI = 2.0  # geçmeyenin online payı ×2 (en çok 1)
