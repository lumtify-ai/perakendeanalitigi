"""B'nin sabitleri. A her zaman `v4.sabitler.TOHUM` (2026) ile kurulur."""

import numpy as np

from .. import sabitler as _a

CRM_TOHUM = 4242

# ---------------------------------------------------------------------------
# Müşteri nüfusu (Görev 2, spec §2). Bütün sayısal değerler KALİBRASYON
# (Görev 14 ayarlar); gerekçeler satır yorumlarında. Karışım tutarlılığı
# `nufus.karisim_ozeti()` ile ölçülür (test_nufus.test_karisim_hedefleri):
# nüfus ortalaması gizli yıllık ziyaret hızı ~4,1 (anonim ziyaretler dahil;
# Görev 14), mağaza sepeti ~2,2, online ~1,8, kart okutma (mağaza ziyareti
# ağırlıklı) %50–60.
#
# Görev 14 (çok tohumlu kalibrasyon, spec §8): ziyaret hızı ölçekleri ×1,4,
# aylık terk ortalamaları ×1,8 (arketipler arası oranlar korunarak). Önce
# (TAM) kartlı müşteri yıllık ziyareti ~2,4, yeni müşteri payı ~%21: nüfus
# fiş talebine göre fazla kalabalık ve seyrek geliyordu. Hız ölçeği
# başlangıç tabanını küçültür (taban beklenen ziyareti 1,2 × talep olacak
# kadar), yüksek terk + aynı katılış daha küçük, daha sık gelen ve daha hızlı
# yenilenen bir nüfus verir: KUCUK 5 tohum ziyaret ~2,98, dönme ~%55, yeni
# payı ~%31; nüfus 2023–2025 satışla birlikte (~%18) büyür.
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
        "ziyaret_gamma": (2.0, 3.23),       # KALİBRASYON ort. 6,5/yıl
        "sepet_ort": 2.17,                  # KALİBRASYON
        "kart_beta": (5.0, 4.5),            # KALİBRASYON ort. 0,53
        "online_beta": (2.12, 5.88),        # KALİBRASYON ort. 0,27
        "terk_beta": (2.0, 32.4),           # KALİBRASYON ort. 0,058/ay
        "indirim_beta": (0.97, 6.03),       # KALİBRASYON ort. 0,14
        "fiyat_segment": [0.10, 0.80, 0.10],  # KALİBRASYON
        "kategori": _kat(Bluz=3.4, Elbise=4.1, Sweatshirt=3.4, Jean=2.2, Tulum=5.8,
                         Şort=2.7, Gömlek=0.34, Pantolon=0.34, Trençkot=0.34),  # KALİBRASYON
        "kalip": [0.25, 0.15, 0.20, 0.40],  # KALİBRASYON oversize/slim
        "desen": [0.20, 0.15, 0.10, 0.35, 0.20],  # KALİBRASYON baskılı
        "beden_dagin": 0.35,                # KALİBRASYON
        "yas": [0.40, 0.38, 0.14, 0.06, 0.02],
    },
    # Kampanya ve outlet peşinde; büyük sepet, giriş segmenti; kartı
    # okutur (sadakat indirimi).
    "indirim_avcisi": {
        "ziyaret_gamma": (1.5, 1.96),       # KALİBRASYON ort. 2,9/yıl
        "sepet_ort": 2.6,                   # KALİBRASYON
        "kart_beta": (6.0, 4.0),            # KALİBRASYON ort. 0,60
        "online_beta": (0.68, 8.32),        # KALİBRASYON ort. 0,08
        "terk_beta": (2.0, 26.9),           # KALİBRASYON ort. 0,069/ay
        "indirim_beta": (9.41, 0.59),       # KALİBRASYON ort. 0,94
        "fiyat_segment": [0.76, 0.23, 0.01],  # KALİBRASYON
        "kategori": _kat(Tişört=1.73, Jean=1.73, Mont=2.2, Kazak=1.73, Trençkot=0.22),  # KALİBRASYON
        "kalip": [0.20, 0.40, 0.25, 0.15],  # KALİBRASYON
        "desen": [0.35, 0.20, 0.15, 0.18, 0.12],  # KALİBRASYON
        "beden_dagin": 0.45,                # KALİBRASYON
        "yas": [0.18, 0.30, 0.26, 0.17, 0.09],
    },
    # Temel parçalar: tişört, gömlek, pantolon, jean, kazak; düz, regular;
    # sadık ama seyrek, düşük terk; mağazacı.
    "klasik_temelci": {
        "ziyaret_gamma": (3.0, 0.98),       # KALİBRASYON ort. 2,9/yıl
        "sepet_ort": 1.82,                  # KALİBRASYON
        "kart_beta": (5.0, 5.0),            # KALİBRASYON ort. 0,50
        "online_beta": (0.28, 10.22),       # KALİBRASYON ort. 0,03
        "terk_beta": (2.0, 49.1),           # KALİBRASYON ort. 0,039/ay
        "indirim_beta": (2.12, 5.88),       # KALİBRASYON ort. 0,27
        "fiyat_segment": [0.14, 0.84, 0.02],  # KALİBRASYON
        "kategori": _kat(Tişört=2.2, Gömlek=4.1, Pantolon=3.4, Jean=1.73, Kazak=2.2,
                         Kemer=3.4, Bluz=0.22, Elbise=0.125, Tulum=0.027, Şort=0.34),  # KALİBRASYON
        "kalip": [0.15, 0.55, 0.22, 0.08],  # KALİBRASYON regular
        "desen": [0.55, 0.18, 0.15, 0.07, 0.05],  # KALİBRASYON düz
        "beden_dagin": 0.30,                # KALİBRASYON
        "yas": [0.05, 0.20, 0.30, 0.27, 0.18],
    },
    # Aile için alır: büyük sepet, dağınık beden, giriş/orta segment,
    # geniş kategori; indirime orta-yüksek duyarlı.
    "aile_alisverisci": {
        "ziyaret_gamma": (2.0, 1.58),       # KALİBRASYON ort. 3,2/yıl
        "sepet_ort": 3.36,                  # KALİBRASYON
        "kart_beta": (6.0, 4.5),            # KALİBRASYON ort. 0,57
        "online_beta": (0.59, 9.41),        # KALİBRASYON ort. 0,06
        "terk_beta": (2.0, 43.6),           # KALİBRASYON ort. 0,044/ay
        "indirim_beta": (5.49, 3.51),       # KALİBRASYON ort. 0,61
        "fiyat_segment": [0.56, 0.43, 0.01],  # KALİBRASYON
        "kategori": _kat(Tişört=2.2, Sweatshirt=2.2, Şort=2.2, Pantolon=1.73, Mont=1.73,
                         Trençkot=0.125, Şal=0.34),  # KALİBRASYON
        "kalip": [0.12, 0.45, 0.33, 0.10],  # KALİBRASYON
        "desen": [0.35, 0.20, 0.15, 0.20, 0.10],  # KALİBRASYON
        "beden_dagin": 1.40,                # KALİBRASYON yüksek (spec §2)
        "yas": [0.02, 0.22, 0.44, 0.24, 0.08],
    },
    # Yüksek gelirli, sık gelen, sadık; premium segment, ceket/trençkot/
    # gömlek/çanta; kartı hemen hep okutur, indirime duyarsız, terk düşük.
    "premium_sadik": {
        "ziyaret_gamma": (3.0, 2.73),       # KALİBRASYON ort. 8,2/yıl
        "sepet_ort": 1.82,                  # KALİBRASYON
        "kart_beta": (7.0, 3.0),            # KALİBRASYON ort. 0,70
        "online_beta": (1.8, 7.2),          # KALİBRASYON ort. 0,20
        "terk_beta": (1.5, 60.4),           # KALİBRASYON ort. 0,024/ay
        "indirim_beta": (0.59, 9.41),       # KALİBRASYON ort. 0,06
        "fiyat_segment": [0.01, 0.17, 0.82],  # KALİBRASYON
        "kategori": _kat(Ceket=8.0, Trençkot=15.6, Gömlek=2.74, Çanta=5.8, Şal=4.1,
                         Elbise=1.73, Tişört=0.34, Sweatshirt=0.125, Şort=0.22),  # KALİBRASYON
        "kalip": [0.40, 0.40, 0.15, 0.05],  # KALİBRASYON slim/regular
        "desen": [0.50, 0.20, 0.15, 0.05, 0.10],  # KALİBRASYON
        "beden_dagin": 0.30,                # KALİBRASYON
        "yas": [0.04, 0.24, 0.34, 0.26, 0.12],
    },
    # Ağırlıkla online; küçük sepet (online fiş ~1,8), sık ziyaret, kartı
    # mağazada seyrek okutur; terki görece yüksek.
    "online_tutkunu": {
        "ziyaret_gamma": (2.0, 3.23),       # KALİBRASYON ort. 6,5/yıl
        "sepet_ort": 1.82,                  # KALİBRASYON
        "kart_beta": (4.0, 4.0),            # KALİBRASYON ort. 0,50
        "online_beta": (9.41, 0.59),        # KALİBRASYON ort. 0,94
        "terk_beta": (2.0, 29.7),           # KALİBRASYON ort. 0,063/ay
        "indirim_beta": (4.0, 4.0),         # KALİBRASYON ort. 0,50
        "fiyat_segment": [0.17, 0.78, 0.05],  # KALİBRASYON
        "kategori": _kat(Elbise=2.2, Bluz=1.73, Tişört=1.73, Çanta=2.2, Mont=0.51),  # KALİBRASYON
        "kalip": [0.25, 0.30, 0.25, 0.20],  # KALİBRASYON
        "desen": [0.25, 0.15, 0.10, 0.25, 0.25],  # KALİBRASYON
        "beden_dagin": 0.40,                # KALİBRASYON
        "yas": [0.28, 0.40, 0.20, 0.09, 0.03],
    },
    # Bir iki kez gelir (turist, hediye, tesadüf): düşük hız, yüksek terk,
    # kartı az okutur; tercihleri tabana yakın.
    "gelip_gecen": {
        "ziyaret_gamma": (1.2, 0.70),       # KALİBRASYON ort. 0,84/yıl
        "sepet_ort": 1.52,                  # KALİBRASYON
        "kart_beta": (3.0, 5.0),            # KALİBRASYON ort. 0,38
        "online_beta": (0.37, 8.13),        # KALİBRASYON ort. 0,04
        "terk_beta": (2.0, 8.0),            # KALİBRASYON ort. 0,20/ay
        "indirim_beta": (2.52, 4.48),       # KALİBRASYON ort. 0,36
        "fiyat_segment": [0.36, 0.60, 0.04],  # KALİBRASYON
        "kategori": _kat(Şal=3.4, Çanta=2.2, Tişört=1.73, Şort=2.2),  # KALİBRASYON
        "kalip": [0.25, 0.35, 0.25, 0.15],  # KALİBRASYON
        "desen": [0.30, 0.18, 0.14, 0.20, 0.18],  # KALİBRASYON
        "beden_dagin": 0.45,                # KALİBRASYON
        "yas": [0.22, 0.30, 0.22, 0.16, 0.10],
    },
}

# Bireysel heterojenlik (Dirichlet toplam yoğunluğu: küçük = dağınık).
KATEGORI_YOGUNLUK = 100.0  # KALİBRASYON 17 kategori (Görev 5c: 10 → 100, arketip farkı bireysel dağınıklıkta kaybolmasın)
OZNITELIK_YOGUNLUK = 8.0   # KALİBRASYON kalıp, desen
FIYAT_YOGUNLUK = 50.0      # KALİBRASYON (Görev 5c: 10 → 50)
SEPET_SEKIL = 4.0          # KALİBRASYON sepet_ort − 1 ~ Gamma(4, ·): CV 0,5
BEDEN_DAGIN_SIGMA = 0.25   # KALİBRASYON bireysel beden_dagin lognormal σ
ALT_BEDEN_KAYMA = [0.2, 0.6, 0.2]  # KALİBRASYON alt beden = üst + (−1, 0, +1)
ONLINE_SEPET_CARPANI = 0.82  # KALİBRASYON online fiş ≈ mağaza sepeti × 0,82 (2,2 → 1,8)
ERKEK_KADIN_KAT_CARPANI = 0.1  # KALİBRASYON erkek müşteride yalnız-kadın alt kategoriler (hediye)
# Müşteri × ürün cinsiyeti (Görev 5b). Eşleştirme puanında çapraz cinsiyet
# (kadın müşteri × Erkek ürün ya da tersi; Unisex cezasız) log-cezası;
# aksesuarda (A'da cinsiyeti var, beden yok) yarısı. KALİBRASYON hedef:
# cinsiyeti belli giyim birimlerinde çapraz (hediye) payı %8–15. Kartlı,
# kotayla: KUCUK −2,5 → %14,2 (4 B tohumu %14,15–14,19), −3,0 → %11,8,
# −3,5 → %10,0; TAM −2,5 → %9,7, −3,0 → %7,4 (TAM'da kadın ürün payı daha
# yüksek, çapraz erkek ürün arzıyla sınırlı). Kotasız KUCUK −3,5 → %14,3,
# −8 → %10,4: taban ziyaretçi cinsiyeti gürültüsüydü. Görev 5c (sivri arketip
# kategori eğimleri + indirim terimi) −2,5'te KUCUK'u %15,06'ya çıkardı; −2,7.
CAPRAZ_CINSIYET_CEZA = -2.7
CAPRAZ_CINSIYET_AKSESUAR_KAT = 0.5
# Nüfusun kadın payı mağaza başına A'nın o mağazadaki satışından: Kadın /
# (Kadın + Erkek) birim payı + bu düzeltme; günlük ziyaretçi kotası da aynı
# düzeltmeyi alır. 0: "bir cinsiyet daha çok hediye alır" varsayımı yok;
# KUCUK'ta çapraz birimler iki yöne kabaca eşit bölünür (kadın → Erkek ürün
# %6,5, erkek → Kadın ürün %5,3 (−3,0'da); hepsinin payı olarak). KALİBRASYON
KADIN_HEDIYE_DUZELTME = 0.0
# Mağaza kadın payının zincir payına büzülmesi: (kad + α·p_zincir) /
# (kad + erk + α), α birim (nufus.kadin_payi_buzul). KALİBRASYON
KADIN_PAYI_BUZULME = 200.0
# Ziyaretçi cinsiyet kotası: mağaza-gün başına k fiş için ceil(KOTA_FAZLA ×
# k) + KOTA_EK aday çekilir, kotaya göre k'sı alınır (ziyaretci.py). KUCUK:
# kotadan sapan fiş %0,35.
KOTA_FAZLA = 1.5
KOTA_EK = 8
# Müşteri × indirimli SKU-gün satırı (Görev 5c). Aşama 1'in grup anahtarı
# (mağaza, tip, ürün cinsiyeti, indirimli); indirimli = A satırının
# `indirim_tutari > 0` (markdown, kampanya ya da işlem indirimi). Müşteri
# başına log-terim INDIRIM_AGIRLIGI × indirim_duyarlilik × indirimli (grup
# içinde sabit; Gumbel-max + log n kesin kalır). Önce indirim duyarlılığı
# yalnız aşama 2'de (tip içinde SKU) etkiliydi: indirimli satır payıyla
# korelasyon 0,01 (Görev 15). KALİBRASYON
INDIRIM_AGIRLIGI = 15.0

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
# kapanır. Görev 14: TABAN aynı kaldı; terk ×1,8 ile yeni müşteri payı
# bandın ortasına (%25–40 → ~%31) geldi (nüfus taban altından başlayıp
# katılış = terk dengesine yaklaşır).
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

# --- Günlük ayrıştırma (Görev 5, spec §3) ---------------------------------------
# Ziyaretçi ağırlığı (fiziksel mağaza m): ziyaret_hizi × (1 − online_payi) ×
# (ev mağazası m ise 1, aynı ildeki başka müşteri IL_ICI_AGIRLIK); ONL:
# ziyaret_hizi × online_payi. Kapanmış ev mağazasının satışı olmadığından
# ağırlığı fiilen 0.
IL_ICI_AGIRLIK = 0.15            # KALİBRASYON spec §3 "il içi diğerleri hafif"
ADAY_YENIDEN_KUR_GUN = 28        # aday yapısı en geç bu kadar günde bir baştan kurulur
ZIYARET_RET_SINIRI = 4           # çekiliş > sınır × k + 64 ise Gumbel-top-k yedeği
SEPET_BF_CARPANI = 1.3           # Black Friday günlerinde sepet hedefi ×1,3 (spec §3)
FIS_EN_COK = 8                   # fiş başına adet 1–8 (spec §3)
FIS_EK_SEKIL = 1.0               # KALİBRASYON fiş ek adedi ağırlığı (sepet_ort − 1) × Gamma(1, 1): çarpık (üstel)
ESLESTIRME_TUR = 5               # çapa / tamamlayıcı / aşama 2 çakışma turları
TEKRAR_TAMPON = 8                # müşteri başına son alınan option sayısı (halka)
TEKRAR_BONUS = 0.8               # KALİBRASYON tamponda olan option'a log-bonus (aşama 2)
TEKRAR_BONUS_DEVAMLI = 1.2       # KALİBRASYON Basic/NOS option'da
# Fiş saati (dakika, gün içi). Mağaza 10:00–22:00: hafta içi 19:00 tepeli
# (σ 1,2 sa), hafta sonu 15:30 tepeli (σ 1,5 sa) normal + düzgün karışım;
# ONL 24 saat: 21:00 tepeli (σ 3 sa, gece yarısında sarılır) + düzgün.
SAAT_ACILIS, SAAT_KAPANIS = 10.0, 22.0
SAAT_HAFTA_ICI = (19.0, 1.2, 0.55)   # (tepe, σ, tepe payı) KALİBRASYON
SAAT_HAFTA_SONU = (15.5, 1.5, 0.60)  # KALİBRASYON
SAAT_ONLINE = (21.0, 3.0, 0.60)      # KALİBRASYON
# Tamamlayıcı adımı dalgalarla: bir turda fiş başına en çok DALGA birim kabul
# edilir (son tur hariç), böylece sonraki birimler sepete eklenenleri görür.
TAMAMLAYICI_TUR = 8
TAMAMLAYICI_DALGA = 1
# Dalgalardan sonra yalnız fiş kapasitesiyle sınırlı artık turlar (kalan
# birimler × kapasiteli fişler yeniden çekilir, fiş seçimine log(kalan
# kapasite) eklenir); rastgele yerleşim yalnız son çare. Görev 5c: 3 → 4
# (indirim durumu grup anahtarına girince gruplar küçüldü, KUCUK 60 günde
# rastgele yerleşen pay %0,59'a çıkmıştı; 4 turla < %0,5).
TAMAMLAYICI_ARTIK_TUR = 4

# --- İade, işlem indirimi, boş ziyaret (Görev 6, spec §3.4–3.5, §4) ------------
# İade birimi, iade gününden 7 (ONL 10) gün önceki aynı hücrenin satış
# satırlarından birine bağlanır; birim ağırlığı 1 + IADE_BEDEN_AGIRLIK ×
# (satır beden uyumsuz).
IADE_BEDEN_AGIRLIK = 4.0
# Gizli kayıp biriminin o gün o mağazada fişi olan müşteriye yazılma
# olasılığı (kalanı fişsiz boş ziyaretçiye). Fişsiz ziyaretçi sayısı mağaza
# başına max(1, round(birim / sepet hedefi)).
BOS_FISLI_PAY = 0.5

# --- Online liste, sıralama, tıklama, olay kaydı (Görev 9, spec §5) ------------
LISTE_UZUNLUGU = 48              # liste başına gösterilen sıra (2 × 24)
SATIS_PENCERE_GUN = 7            # Lumoda kategori sıralaması: son 7 günün ONL satışı
YENI_GELEN_GUN = 28              # "yeni_gelenler": son 28 günde lansman
BAKILMA_US = 0.8                 # gizli bakılma eğrisi 1 / (1 + sıra)^0,8
ILGI_INDIRIM = 0.5               # gizli ilgi: + 0,5 × arketip indirim duyarlılığı ort. × oran
GORUNTULEME_FIS = 30.0           # KALİBRASYON günlük liste görüntüleme = ONL satış fişi × 30
LISTE_TRAFIK_PAYI = {            # KALİBRASYON görüntülemelerin liste türlerine payı
    "kategori": 0.55, "arama": 0.25, "yeni_gelenler": 0.10, "indirim": 0.10,
}
TIKLAMA_GORUNTULEME = 0.8       # KALİBRASYON liste görüntüleme başına beklenen tıklama (sıra × ilgiyle paylaşılır)
TIKLAMA_UST = 0.9                # hücre tıklama olasılığı üst sınırı
SEPET_ORANI = 0.25               # sepete ekleme ≈ tıklama × 0,25
ARAMA_EK_TIKLAMA = 3.0           # KALİBRASYON listede olmayan option: tıklama = alım + Poisson(3 × alım)
OTURUM_GORUNTULEME = 3.0         # KALİBRASYON günlük oturum = görüntüleme / 3
OTURUM_EN_COK = 6                # oturum başına 1–6 liste görüntüleme
GIRIS_PAYI = 0.60                # oturumların giriş yapmış payı
OLAY_ARALIK_SN = 40.0            # KALİBRASYON oturum içi ardışık olaylar arası ortalama (üstel) saniye
