"""Kalibrasyon: ön oyun penceresinde (2025-05-05 – 2025-08-31) parametre
seçimi, oyun dönemine (2025-09-01'den sonrasına) hiçbir şekilde bakmadan.

`kalibre_et` yalnız yol 0'ı, İlkbahar/Yaz planını ve %80 alım oranını
kullanarak sırayla: özel gün katsayılarını, (koli kuralı "yok", açık
kapasite sınırsız altında) hedef bulunabilirliği, sabit/ros ızgaralarından
bu hedefe en yakın değeri, üç güvenlik stoku ailesi içinden ön oyun sonu
mağaza stokunu en küçültüğünü (`varsayilan_ss`), gerçek açık kapasite
altında A/B koli ızgaralarından maliyeti en düşüğü (bulunabilirliği
ızgaradaki en iyinin 1 puanından fazla düşürmeyenler arasında) ve son
olarak Task 8'in LightGBM hiperparametrelerini seçer.

`acik_kapasite` gerçek oyun dönemi sevkiyatından (`kaynak.
haftalik_sevkiyat_ortalamasi`) türetilir — bu, ön oyun sonucu değil,
global bir sabitin (spec §Genel Kısıtlar) hesabıdır; ön oyunun kendisine
sızmaz çünkü ön oyun günleri bu ortalamaya girmez.
"""

from dataclasses import dataclass
from math import floor

from . import kaynak, sabitler
from .dagitim import KoliKurali
from .dunya import Dunya
from .ihtiyac import GuvenlikStoku, magaza_beden_paylari, ozel_gun_katsayilari
from .motor import baslangic_durumu
from .oyun import OyunAyari, oyna
from .politika import KuralPolitikasi
from .tahmin import hiperparametre_sec

SABIT_IZGARA = (1, 2, 3, 4, 6, 8)
ROS_IZGARA = (1, 2, 3, 5, 7, 10, 14)
ALFA_IZGARA = (0.4, 0.6, 0.8)
BETA_IZGARA = (1, 2, 3)
GAMA_IZGARA = (0.5, 0.6, 0.75)

# "Sınırsız" açık kapasite: hiçbir gerçekçi ön oyun senaryosunda bağlayıcı
# olmayacak kadar büyük bir tavan (gerçek limit yerine).
_SINIRSIZ_KAPASITE = 10**9
_ON_OYUN_ALIM_ORANI = 0.80


@dataclass(frozen=True)
class Kalibrasyon:
    katsayilar: dict[str, float]
    ss: dict[str, GuvenlikStoku]     # "sabit" | "ros" | "istatistik"
    varsayilan_ss: str               # ön oyunda en az stokla hedef bulunabilirliğe ulaşan
    koli: dict[str, KoliKurali]      # "A" | "B" | "C"
    hedef_bulunabilirlik: float
    acik_kapasite: int
    tahmin_parametreleri: dict
    tablo: list[dict]                # rapor için bütün ön oyun satırları


def en_yakin(degerler: dict, hedef: float):
    """`degerler` (anahtar → ölçüm) içinden `hedef`'e en yakın anahtarı
    döner; eşitlikte küçük anahtar kazanır (artan sırada tarama + katı
    `<` karşılaştırması)."""
    en_iyi_anahtar = None
    en_iyi_fark = None
    for anahtar in sorted(degerler):
        fark = abs(degerler[anahtar] - hedef)
        if en_iyi_fark is None or fark < en_iyi_fark:
            en_iyi_fark = fark
            en_iyi_anahtar = anahtar
    return en_iyi_anahtar


def maliyet_secimi(satirlar: list[dict]) -> dict:
    """Bulunabilirliği ızgaradaki en iyisinin 1 puan altına düşmeyen
    satırlar arasından `toplama_maliyeti_tl`'si en küçük olanı döner."""
    en_iyi_bulunabilirlik = max(s["bulunabilirlik"] for s in satirlar)
    esik = en_iyi_bulunabilirlik - 1.0
    adaylar = [s for s in satirlar if s["bulunabilirlik"] >= esik]
    return min(adaylar, key=lambda s: s["toplama_maliyeti_tl"])


def _on_oyun_girdileri(dunya: Dunya, con):
    """(talep, geçmiş satış, başlangıç stoku, iade kuyruğu tohumu,
    gözlenen satış) — ön oyunun 2025-05-05 sabahındaki hâli.

    `gozlenen`, katsayı/hiperparametre seçimi için TAM gerçek satış
    geçmişidir (peek yok: her ikisi de kendi bit_gunu'nde kırpar).
    `gecmis_satis`, oyun motoruna geçmiş olarak verilen, ön oyun ve sonrası
    sıfırlanmış kopyadır (spec: "geçmiş satış = gözlenen satış, ön oyun
    günleri sıfırlanmış")."""
    talep = kaynak.kahin_talep(con, dunya)
    gozlenen = kaynak.gozlenen_satis(con, dunya)

    bas_gunu = dunya.gun(sabitler.ON_OYUN_BAS)
    gecmis_satis = gozlenen.copy()
    gecmis_satis[bas_gunu:] = 0

    stok = kaynak.stok_fotografi(con, dunya, sabitler.ON_OYUN_BAS)
    son_7 = list(gecmis_satis[bas_gunu - sabitler.IADE_GECIKME : bas_gunu])
    return talep, gecmis_satis, stok, son_7, gozlenen


def kalibre_et(dunya: Dunya, con) -> Kalibrasyon:
    talep, gecmis_satis, stok, son_7, gozlenen = _on_oyun_girdileri(dunya, con)

    bas_gunu = dunya.gun(sabitler.ON_OYUN_BAS)
    katsayilar = ozel_gun_katsayilari(gozlenen, dunya, bas_gunu)
    paylar = magaza_beden_paylari(gecmis_satis, dunya, bas_gunu)

    acik_kapasite_gercek = floor(
        kaynak.haftalik_sevkiyat_ortalamasi(
            con, sabitler.OYUN_BAS, sabitler.OYUN_BIT, sabitler.KARAR_SAYISI
        )
        * sabitler.ACIK_KAPASITE_ORANI
    )

    tablo: list[dict] = []

    def _kos(ss: GuvenlikStoku, kural: KoliKurali, acik_kapasite: int) -> dict:
        baslangic = baslangic_durumu(stok, son_7)
        politika = KuralPolitikasi(ss, katsayilar)
        ayar = OyunAyari(
            alim_orani=_ON_OYUN_ALIM_ORANI,
            kural=kural,
            acik_kapasite=acik_kapasite,
            bas=sabitler.ON_OYUN_BAS,
            bit=sabitler.ON_OYUN_BIT,
        )
        return oyna(dunya, talep, gecmis_satis, baslangic, politika, ayar, paylar).olcutler

    # --- Adım 2: hedef bulunabilirlik (istatistik ailesi, koli yok, kapasite sınırsız) ---
    istatistik_ss = GuvenlikStoku("istatistik")
    istatistik_olcut = _kos(istatistik_ss, KoliKurali("yok"), _SINIRSIZ_KAPASITE)
    hedef_bulunabilirlik = istatistik_olcut["bulunabilirlik"]
    tablo.append({"asama": "hedef_bulunabilirlik", "ss": "istatistik", **istatistik_olcut})

    # --- Adım 3: sabit ve ros ızgaraları, aynı koşulla ---
    sabit_bulunabilirlik = {}
    for deger in SABIT_IZGARA:
        olcut = _kos(GuvenlikStoku("sabit", deger), KoliKurali("yok"), _SINIRSIZ_KAPASITE)
        sabit_bulunabilirlik[deger] = olcut["bulunabilirlik"]
        tablo.append({"asama": "sabit_izgara", "deger": deger, **olcut})
    sabit_secilen_deger = en_yakin(sabit_bulunabilirlik, hedef_bulunabilirlik)
    sabit_ss = GuvenlikStoku("sabit", sabit_secilen_deger)
    sabit_olcut = _kos(sabit_ss, KoliKurali("yok"), _SINIRSIZ_KAPASITE)

    ros_bulunabilirlik = {}
    for deger in ROS_IZGARA:
        olcut = _kos(GuvenlikStoku("ros", deger), KoliKurali("yok"), _SINIRSIZ_KAPASITE)
        ros_bulunabilirlik[deger] = olcut["bulunabilirlik"]
        tablo.append({"asama": "ros_izgara", "deger": deger, **olcut})
    ros_secilen_deger = en_yakin(ros_bulunabilirlik, hedef_bulunabilirlik)
    ros_ss = GuvenlikStoku("ros", ros_secilen_deger)
    ros_olcut = _kos(ros_ss, KoliKurali("yok"), _SINIRSIZ_KAPASITE)

    # --- Adım 4: varsayılan aile = en küçük ön oyun sonu mağaza stoku ---
    aile_stok_son = {
        "sabit": sabit_olcut["magaza_stok_son"],
        "ros": ros_olcut["magaza_stok_son"],
        "istatistik": istatistik_olcut["magaza_stok_son"],
    }
    varsayilan_ss = min(aile_stok_son, key=lambda a: aile_stok_son[a])
    ss_ailesi = {"sabit": sabit_ss, "ros": ros_ss, "istatistik": istatistik_ss}
    ss_secilen = ss_ailesi[varsayilan_ss]

    # --- Adım 5: koli (varsayılan ss, gerçek açık kapasite) ---
    a_satirlar = []
    for alfa in ALFA_IZGARA:
        for beta in BETA_IZGARA:
            kural = KoliKurali("A", alfa=alfa, beta=beta)
            olcut = _kos(ss_secilen, kural, acik_kapasite_gercek)
            satir = {"alfa": alfa, "beta": beta, **olcut}
            a_satirlar.append(satir)
            tablo.append({"asama": "koli_a", **satir})
    a_secilen = maliyet_secimi(a_satirlar)
    koli_a = KoliKurali("A", alfa=a_secilen["alfa"], beta=a_secilen["beta"])

    b_satirlar = []
    for gama in GAMA_IZGARA:
        kural = KoliKurali("B", gama=gama)
        olcut = _kos(ss_secilen, kural, acik_kapasite_gercek)
        satir = {"gama": gama, **olcut}
        b_satirlar.append(satir)
        tablo.append({"asama": "koli_b", **satir})
    b_secilen = maliyet_secimi(b_satirlar)
    koli_b = KoliKurali("B", gama=b_secilen["gama"])

    koli_c = KoliKurali("C", alfa=koli_a.alfa, beta=koli_a.beta, gama=koli_b.gama)

    # --- Adım 7: LightGBM hiperparametreleri (oyun başlangıcından öncesi) ---
    tahmin_parametreleri = hiperparametre_sec(gozlenen, dunya, dunya.gun(sabitler.OYUN_BAS))

    return Kalibrasyon(
        katsayilar=katsayilar,
        ss={"sabit": sabit_ss, "ros": ros_ss, "istatistik": istatistik_ss},
        varsayilan_ss=varsayilan_ss,
        koli={"A": koli_a, "B": koli_b, "C": koli_c},
        hedef_bulunabilirlik=hedef_bulunabilirlik,
        acik_kapasite=acik_kapasite_gercek,
        tahmin_parametreleri=tahmin_parametreleri,
        tablo=tablo,
    )
