"""Stok-satış simülasyonu.

Bu modül veri setinin kalbidir. Kayıp satış, ölü stok ve beden
dengesizliği burada **türetilmiş sonuç** olarak doğar; sonradan
eklenmez. Transfer probleminin anlamlı olması buna bağlıdır.

Günlük döngü şu sırayla ilerler ve sıra tesadüfi değildir:

    1. Haftalık stok fotoğrafı  — ikmalden ÖNCE çekilir; sevkiyat
       gelmeden önceki raf durumu transfer kararının baktığı tablodur
    2. İkmal                    — hedef seviyeye tamamlama, sevkiyat kaydı
    3. İade                     — geçmiş satışların bir kısmı geri döner
    4. Talep ve satış           — stok kısıtı altında; aşan kısım kayıp satış

Dört tablo üretir: satis, stok, sevkiyat, kayip_satis.
"""

import numpy as np
import pandas as pd

from . import sabitler, talep

# Mağaza tipine göre taşınan model oranı: hiçbir mağaza tüm çeşidi
# taşımaz, transfer ihtiyacı büyük ölçüde buradan doğar
CESIT_ORANI = {"AVM": 0.45, "Cadde": 0.30, "Outlet": 0.55}

# İki haftada bir ikmal, altı haftalık hedef. Bu ikili tarandı:
# dört haftalık aralıkta kayıp satış %22'ye çıkıyor (kötü yönetilen
# zincir), tek haftalıkta dengesizlik siliniyor.
IKMAL_HAFTA_ARALIGI = 2   # kaç haftada bir ikmal yapılır
IKMAL_HEDEF_HAFTA = 6     # kaç haftalık talebi karşılayacak stok

INDIRIM_OLASILIGI = 0.18
INDIRIM_ORANI = 0.30

# Mağaza içi iade oranı ve iadenin satıştan kaç gün sonra geldiği
IADE_ORANI = 0.06
IADE_GECIKME_GUN = 7

# --- Planın yereli tutturamaması ---------------------------------------
# Transfer probleminin varlık sebebi budur. İkmal, zincir genelinde
# kurulmuş bir plana göre yapılır: "bu tip mağazada bu üründen haftada
# şu kadar satar". Gerçek talep ise yereldir — bir option bir mağazada
# tutar, diğerinde hiç tutmaz; beden eğrisi semtten semte değişir.
# Plan ile gerçek arasındaki bu fark, bir yerde ölü stok bir yerde
# stoksuzluk üretir. İkmal her mağazayı kendi GERÇEK talebine göre
# doldursaydı plan hep doğru çıkar ve transfer edilecek bir şey olmazdı.
YEREL_TALEP_SAPMASI = 0.50    # (mağaza × option) lognormal sapması
OLU_OPTION_OLASILIGI = 0.08   # bir option'ın o mağazada hiç tutmama olasılığı
OLU_OPTION_CARPANI = 0.03
BEDEN_EGRISI_SAPMASI = 0.30   # mağazanın beden eğrisinin zincirden sapması

# Kasten üretilen kirli kayıtlar (spec bölüm 6). Sentetik verinin klasik
# tuzağı fazla temiz olmasıdır; bu kayıtlar analistin gerçek hayatta
# karşılaşacağı temizlik işini veriye geri koyar.
MUKERRER_KAYIT = 40        # çift girilmiş satış satırı
BEDELSIZ_KAYIT = 25        # adet dolu, tutar sıfır (manuel giriş hatası)
HAYALET_STOK_KAYDI = 30    # mağazanın çeşidinde olmayan üründe stok görünmesi


def cesit_ata(
    rng: np.random.Generator, magazalar: pd.DataFrame, urunler: pd.DataFrame
) -> pd.DataFrame:
    """Her mağazaya kısmi bir SKU çeşidi atar.

    Atama **model düzeyinde** yapılır: bir mağaza bir modeli taşıyorsa o
    modelin tüm renk ve bedenlerini taşır. Beden bütünlüğü moda
    perakendesinin temel kuralıdır ve transfer probleminin çerçevesini
    kurar — yarım beden setiyle mağaza açılmaz.
    """
    modeller = urunler["model_kodu"].unique()
    model_urunleri = urunler.groupby("model_kodu")["urun_id"].apply(list)

    satirlar = []
    for magaza_id, tip in zip(magazalar["magaza_id"], magazalar["tip"]):
        adet = int(len(modeller) * CESIT_ORANI[tip])
        secilen = rng.choice(modeller, size=adet, replace=False)
        urun_idleri = [u for model in secilen for u in model_urunleri[model]]
        satirlar.append(
            pd.DataFrame({"magaza_id": magaza_id, "urun_id": urun_idleri})
        )
    return pd.concat(satirlar, ignore_index=True)


def _magaza_beden_egrileri(
    rng: np.random.Generator, magazalar: pd.DataFrame
) -> dict[str, dict[str, float]]:
    """Her mağazaya kendi beden eğrisini verir.

    Zincir tek bir beden eğrisiyle planlar; mağazanın müşterisi ise
    semtine göre farklıdır. Kırıklık — ara bedenlerin tükenip uçların
    kalması — büyük ölçüde bu farktan doğar.
    """
    zincir_payi = talep.beden_dagilimi()
    bedenler = list(zincir_payi)
    taban = np.array([zincir_payi[beden] for beden in bedenler])

    egriler = {}
    for magaza_id in magazalar["magaza_id"]:
        pay = taban * np.exp(rng.normal(0.0, BEDEN_EGRISI_SAPMASI, size=len(bedenler)))
        egriler[str(magaza_id)] = dict(zip(bedenler, pay / pay.sum()))
    return egriler


def _yerel_option_carpani(
    rng: np.random.Generator, cesit_magaza: pd.DataFrame, cesit_urun: pd.DataFrame
) -> np.ndarray:
    """(mağaza × option) düzeyinde yerel talep çarpanı.

    Aynı option'ın tüm bedenleri aynı çarpanı alır: bir ürün bir
    mağazada tutuyorsa bütün bedenleriyle tutar.
    """
    anahtar = (
        cesit_magaza.index.to_numpy().astype(str)
        + "|"
        + cesit_urun["option_id"].to_numpy().astype(str)
    )
    benzersiz, ters = np.unique(anahtar, return_inverse=True)

    carpan = rng.lognormal(0.0, YEREL_TALEP_SAPMASI, size=len(benzersiz))
    olu = rng.random(len(benzersiz)) < OLU_OPTION_OLASILIGI
    carpan[olu] = OLU_OPTION_CARPANI
    return carpan[ters]


def _beklenen_talep(
    rng: np.random.Generator,
    magazalar: pd.DataFrame,
    cesit_urun: pd.DataFrame,
    cesit_magaza: pd.DataFrame,
) -> tuple[dict, dict]:
    """Sezon bazında (plan talebi, gerçek talep) çiftini hesaplar.

    Plan ikmalin hedefini belirler ve zincir genelinin bilgisini taşır.
    Gerçek talep satışı üretir ve yerel sapmaları içerir. İkisi arasındaki
    fark, veri setindeki dengesizliğin tek kaynağıdır.
    """
    ortak = (
        cesit_urun["ana_kategori"].map(talep.TABAN_TALEP).to_numpy()
        * cesit_urun["cinsiyet"].map(talep.CINSIYET_CARPANLARI).to_numpy()
        * cesit_magaza["tip"].map(talep.MAGAZA_TIPI_CARPANLARI).to_numpy()
    )

    zincir_payi = talep.beden_dagilimi()
    beden_sayisi = len(zincir_payi)
    plan_statik = ortak * cesit_urun["beden"].map(zincir_payi).to_numpy() * beden_sayisi

    egriler = _magaza_beden_egrileri(rng, magazalar)
    yerel_beden_payi = np.array(
        [
            egriler[magaza][beden]
            for magaza, beden in zip(cesit_magaza.index, cesit_urun["beden"])
        ]
    )
    gercek_statik = (
        ortak
        * yerel_beden_payi
        * beden_sayisi
        * _yerel_option_carpani(rng, cesit_magaza, cesit_urun)
    )

    plan, gercek = {}, {}
    for sezon in ("İlkbahar/Yaz", "Sonbahar/Kış"):
        carpan = np.array(
            [
                talep.mevsimsellik_carpani(mevsim, kategori, sezon)
                for mevsim, kategori in zip(
                    cesit_urun["mevsimsellik"], cesit_urun["ana_kategori"]
                )
            ]
        )
        plan[sezon] = plan_statik * carpan
        gercek[sezon] = gercek_statik * carpan
    return plan, gercek


def _kirlet(
    rng: np.random.Generator,
    satis: pd.DataFrame,
    stok: pd.DataFrame,
    magaza_idleri: np.ndarray,
    urun_idleri: np.ndarray,
    cesit_anahtarlari: set,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Az sayıda gerçekçi kirli kayıt enjekte eder."""
    # 1) Çift girilmiş satırlar
    gercek = satis.index[satis["adet"] > 0].to_numpy()
    mukerrer = satis.loc[rng.choice(gercek, size=MUKERRER_KAYIT, replace=False)]
    satis = pd.concat([satis, mukerrer], ignore_index=True)

    # 2) Adet dolu ama tutar sıfır
    bedelsiz = rng.choice(
        satis.index[satis["adet"] > 0].to_numpy(), size=BEDELSIZ_KAYIT, replace=False
    )
    satis.loc[bedelsiz, ["tutar", "indirim_tutari"]] = 0.0

    # 3) Mağazanın çeşidinde olmayan üründe hayalet stok
    pazartesiler = stok["tarih"].unique()
    hayalet = []
    while len(hayalet) < HAYALET_STOK_KAYDI:
        magaza = str(rng.choice(magaza_idleri))
        urun = str(rng.choice(urun_idleri))
        if (magaza, urun) in cesit_anahtarlari:
            continue
        hayalet.append(
            {
                "tarih": pazartesiler[rng.integers(len(pazartesiler))],
                "magaza_id": magaza,
                "urun_id": urun,
                "adet": int(rng.integers(1, 4)),
            }
        )
    stok = pd.concat([stok, pd.DataFrame(hayalet)], ignore_index=True)
    return satis, stok


def simule_et(
    rng: np.random.Generator,
    magazalar: pd.DataFrame,
    urunler: pd.DataFrame,
    takvim: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Günlük döngüde talebi üretip stok kısıtı altında satışa çevirir."""
    cesit = cesit_ata(rng, magazalar, urunler)
    cesit_urun = urunler.set_index("urun_id").loc[cesit["urun_id"]]
    cesit_magaza = magazalar.set_index("magaza_id").loc[cesit["magaza_id"]]

    magaza_id = cesit["magaza_id"].to_numpy()
    urun_id = cesit["urun_id"].to_numpy()
    liste_fiyati = cesit_urun["liste_fiyati"].to_numpy()

    plan_sezon, talep_sezon = _beklenen_talep(
        rng, magazalar, cesit_urun, cesit_magaza
    )
    # İkmal hedefi PLAN talebinden kurulur, gerçek talepten değil
    hedef_sezon = {
        sezon: np.rint(plan * 7 * IKMAL_HEDEF_HAFTA).astype(np.int64)
        for sezon, plan in plan_sezon.items()
    }

    stok_durumu = np.zeros(len(cesit), dtype=np.int64)
    gecmis_satislar: list[np.ndarray] = []

    satis_p: list[tuple] = []
    stok_p: list[tuple] = []
    sevkiyat_p: list[tuple] = []
    kayip_p: list[tuple] = []

    for gun in takvim.itertuples(index=False):
        tarih, sezon = gun.tarih, gun.sezon
        beklenen = talep_sezon[sezon]
        pazartesi = tarih.dayofweek == 0
        acilis = tarih == pd.Timestamp(sabitler.BASLANGIC)

        # 1) Fotoğraf — ikmalden ÖNCE
        if pazartesi:
            stok_p.append((tarih, np.arange(len(stok_durumu)), stok_durumu.copy()))

        # 2) İkmal
        if acilis or (pazartesi and (int(gun.hafta) - 1) % IKMAL_HAFTA_ARALIGI == 0):
            eksik = np.maximum(hedef_sezon[sezon] - stok_durumu, 0)
            gonderilen = np.flatnonzero(eksik > 0)
            if gonderilen.size:
                sevkiyat_p.append((tarih, gonderilen, eksik[gonderilen]))
                stok_durumu += eksik

        # 3) İade — IADE_GECIKME_GUN önceki satışların bir kısmı geri döner
        if len(gecmis_satislar) >= IADE_GECIKME_GUN:
            iade = rng.binomial(gecmis_satislar[-IADE_GECIKME_GUN], IADE_ORANI)
            donen = np.flatnonzero(iade > 0)
            if donen.size:
                stok_durumu[donen] += iade[donen]
                satis_p.append(
                    (
                        tarih,
                        donen,
                        -iade[donen],
                        -np.round(liste_fiyati[donen] * iade[donen], 2),
                        np.zeros(donen.size),
                    )
                )

        # 4) Talep → satış; stoğu aşan kısım kayıp satıştır
        gun_c = talep.gun_carpani(tarih.dayofweek, bool(gun.tatil_mi))
        istenen = rng.poisson(beklenen * gun_c)
        satilan = np.minimum(istenen, stok_durumu)
        kayip = istenen - satilan
        stok_durumu -= satilan

        satan = np.flatnonzero(satilan > 0)
        if satan.size:
            indirimli = rng.random(satan.size) < INDIRIM_OLASILIGI
            birim = liste_fiyati[satan] * np.where(indirimli, 1 - INDIRIM_ORANI, 1.0)
            satis_p.append(
                (
                    tarih,
                    satan,
                    satilan[satan],
                    np.round(birim * satilan[satan], 2),
                    np.round((liste_fiyati[satan] - birim) * satilan[satan], 2),
                )
            )

        kayip_olan = np.flatnonzero(kayip > 0)
        if kayip_olan.size:
            kayip_p.append((tarih, kayip_olan, kayip[kayip_olan]))

        gecmis_satislar.append(satilan)
        if len(gecmis_satislar) > IADE_GECIKME_GUN + 1:
            gecmis_satislar.pop(0)

    def _birlestir(parcalar: list[tuple], deger_adlari: list[str]) -> pd.DataFrame:
        tarihler = np.concatenate(
            [np.repeat(np.datetime64(t, "ns"), len(indis)) for t, indis, *_ in parcalar]
        )
        indisler = np.concatenate([indis for _, indis, *_ in parcalar])
        tablo = {
            "tarih": tarihler,
            "magaza_id": magaza_id[indisler],
            "urun_id": urun_id[indisler],
        }
        for sira, ad in enumerate(deger_adlari):
            tablo[ad] = np.concatenate([parca[2 + sira] for parca in parcalar])
        return pd.DataFrame(tablo)

    satis = _birlestir(satis_p, ["adet", "tutar", "indirim_tutari"])
    stok = _birlestir(stok_p, ["adet"])
    sevkiyat = _birlestir(sevkiyat_p, ["adet"])
    kayip_satis = _birlestir(kayip_p, ["kayip_adet"])

    satis, stok = _kirlet(
        rng,
        satis,
        stok,
        magazalar["magaza_id"].to_numpy(),
        urunler["urun_id"].to_numpy(),
        set(zip(magaza_id, urun_id)),
    )

    siralama = ["tarih", "magaza_id", "urun_id"]
    return {
        "satis": satis.sort_values(siralama).reset_index(drop=True),
        "stok": stok.sort_values(siralama).reset_index(drop=True),
        "sevkiyat": sevkiyat.sort_values(siralama).reset_index(drop=True),
        "kayip_satis": kayip_satis.sort_values(siralama).reset_index(drop=True),
    }
