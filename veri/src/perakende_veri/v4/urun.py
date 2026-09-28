"""v4 ürün evreni: hiyerarşi, öznitelikler, option/SKU, fiyat, paket.

marka (Lumoda) > cinsiyet > üst kategori > alt kategori > line > model >
option > SKU. `model` tasarım kararının birimidir (fiyat, kumaş, kalıp,
desen, detay burada sabitlenir); `option` model × renk (planlama birimi);
`SKU` option × beden (en alt stok birimi).

Hacim (bkz. sabitler): sezon başına Collection ~210 + Outlet ~40 option,
devamlı Basic 80 + NOS 40 option; `option_carpani` (`Olcek`) hepsini
ölçekler. Her (line, sezon-tipi) grubunda alt kategori başına hedef
option sayısı ağırlıklı dağıtılır (`_dagit`, en az 1 — pozitif ağırlıklı
her alt kategori en az bir option alır); bu hedefe ulaşana kadar model
üretilir, her modelin renk sayısı (2-4 Collection/Outlet, 3 Basic, 2 NOS)
kalan hedefe göre kırpılır — toplam option sayısı böylece HER ZAMAN tam
hedefe eşittir (rastgelelik model sayısını ve hangi alt kategorinin hangi
modeli aldığını etkiler, toplamı değil).

Controller kararı: AW22 de üretilir (Ocak-Şubat 2023'te indirimde satar);
bu yüzden toplam option sayısı brief'in ~1.700 değil ~1.870 civarındadır
(bkz. test_urun.test_hacim_tam, sınır 1.820-1.920).

v4 hiçbir v2/v3/kök modülünü içe aktarmaz.

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §3
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-5-brief.md
"""

import numpy as np
import pandas as pd

from . import sabitler
from .magaza import Olcek
from .takvim import gun_indisi

# --- Yeniden dışa aktarılan sabitler (brief'in "Produces" listesi) --------
KATEGORILER = sabitler.KATEGORILER
YALNIZ_KADIN = sabitler.YALNIZ_KADIN
AKSESUAR = sabitler.AKSESUAR
BEDEN_SETLERI = sabitler.BEDEN_SETLERI
OZNITELIKLER = sabitler.OZNITELIKLER
DETAY = sabitler.DETAY
GECERLI_KUMAS = sabitler.GECERLI_KUMAS

_ALT_TO_UST = {alt: ust for ust, altlar in sabitler.KATEGORILER.items() for alt in altlar}

# Gün indisi sentinel'i (v3'ün DEVAMLI kuralı): devamlı option'lar hiçbir
# zaman planlı indirime girmez / çıkmaz.
_BUYUK = 10**6


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def _beden_seti(cinsiyet: str, ust_kategori: str) -> tuple[str, list[str]]:
    """Aksesuar cinsiyetten bağımsız tek beden (STD); diğerleri v2 mantığı."""
    if ust_kategori == "Aksesuar":
        return sabitler.AKSESUAR_BEDEN_SETI
    return sabitler.BEDEN_SETLERI[(cinsiyet, ust_kategori)]


def _dagit(toplam: int, agirliklar: dict[str, float]) -> dict[str, int]:
    """`toplam` option'ı, pozitif ağırlıklı alt kategoriler arasında en
    büyük kalan yöntemiyle dağıtır; her aktif alt kategori en az 1 alır
    (toplam aktif sayıdan azsa bu taban aşılamaz, toplam hedefi geçebilir
    — sessizce alt kategori düşürmek yerine hedefi hafifçe aşmak tercih
    edilir). Sonuç tam `toplam`'a eşittir (bu istisna dışında)."""
    aktif = {k: v for k, v in agirliklar.items() if v > 0}
    if not aktif or toplam <= 0:
        return {}
    n = len(aktif)
    toplam_agirlik = sum(aktif.values())
    ham = {k: v / toplam_agirlik * toplam for k, v in aktif.items()}
    taban = {k: max(1, int(np.floor(h))) for k, h in ham.items()}
    fark = toplam - sum(taban.values())
    anahtarlar = list(aktif)

    if fark > 0:
        sira = sorted(anahtarlar, key=lambda k: ham[k] - np.floor(ham[k]), reverse=True)
        i = 0
        while fark > 0:
            taban[sira[i % n]] += 1
            fark -= 1
            i += 1
    elif fark < 0:
        sira = sorted(anahtarlar, key=lambda k: taban[k], reverse=True)
        i, tur = 0, 0
        while fark < 0 and tur < 10 * n:
            k = sira[i % n]
            if taban[k] > 1:
                taban[k] -= 1
                fark += 1
            i += 1
            tur += 1
    return taban


def _renk_gruplari(hedef: int, alt: int, ust: int, rng: np.random.Generator) -> list[int]:
    """Hedef option sayısını modellere böler; her modelin renk sayısı
    [alt, ust] aralığından çekilir, son model kalan miktara kırpılır.
    Toplam tam `hedef`'e eşittir."""
    gruplar = []
    kalan = hedef
    while kalan > 0:
        n = int(rng.integers(alt, ust + 1))
        n = min(n, kalan)
        gruplar.append(n)
        kalan -= n
    return gruplar


def _cinsiyet_sec(rng: np.random.Generator, alt_kategori: str) -> str:
    if alt_kategori in sabitler.YALNIZ_KADIN:
        return "Kadın"
    return str(rng.choice(sabitler.CINSIYETLER, p=sabitler.CINSIYET_PAYLARI))


# ---------------------------------------------------------------------------
# Model üretimi
# ---------------------------------------------------------------------------


def _model_uret(
    rng: np.random.Generator,
    sira: int,
    alt_kategori: str,
    line: str,
    renk_sayisi: int,
    renk_havuzu: list[str],
    sezon_kodu: str,
    dalga: int,
    lansman,
    cikis,
) -> dict:
    ust_kategori = _ALT_TO_UST[alt_kategori]
    cinsiyet = _cinsiyet_sec(rng, alt_kategori)
    beden_seti, bedenler = _beden_seti(cinsiyet, ust_kategori)

    kumaslar = sabitler.GECERLI_KUMAS[alt_kategori]
    genislik = sabitler.KUMAS_AKIS_GENISLIGI.get(alt_kategori)
    if genislik is None:
        kumas = str(rng.choice(kumaslar))
    else:
        # Daraltılmış havuz: eski genişlikte bir çekiliş tüketilir (bkz.
        # sabitler.KUMAS_AKIS_GENISLIGI), akışın geri kalanı kaymaz.
        kumas = str(kumaslar[int(rng.integers(genislik)) % len(kumaslar)])
    kalip = str(rng.choice(sabitler.OZNITELIKLER["kalip"]))
    desen = str(rng.choice(sabitler.OZNITELIKLER["desen"]))
    if alt_kategori in sabitler.DETAY:
        detay_alani, degerler = sabitler.DETAY[alt_kategori]
        detay = str(rng.choice(degerler))
    else:
        detay_alani, detay = None, None
    fiyat_segmenti = str(
        rng.choice(sabitler.OZNITELIKLER["fiyat_segmenti"], p=sabitler.FIYAT_SEGMENTI_PAYLARI)
    )

    alis = (
        sabitler.TABAN_FIYAT[alt_kategori]
        * sabitler.KUMAS_CARPANI[kumas]
        * sabitler.SEGMENT_ALIS_CARPANI[fiyat_segmenti]
        * float(rng.lognormal(0.0, sabitler.ALIS_FIYATI_SIGMA))
    )

    kesim = str(rng.choice(sabitler.KESIMLER[alt_kategori]))

    secilen = rng.choice(len(renk_havuzu), size=renk_sayisi, replace=False)
    renkler = [renk_havuzu[i] for i in sorted(secilen)]

    return {
        "model_kodu": f"MDL{sira:04d}",
        "model_adi": f"{kesim} {alt_kategori}",
        "cinsiyet": cinsiyet,
        "ust_kategori": ust_kategori,
        "alt_kategori": alt_kategori,
        "line": line,
        "beden_seti": beden_seti,
        "bedenler": bedenler,
        "renkler": renkler,
        "kumas": kumas,
        "kalip": kalip,
        "desen": desen,
        "detay": detay,
        "detay_alani": detay_alani,
        "fiyat_segmenti": fiyat_segmenti,
        "alis_fiyati": round(alis, 2),
        "sezon_kodu": sezon_kodu,
        "dalga": dalga,
        "lansman_tarihi": lansman,
        "cikis_tarihi": cikis,
    }


def _sezonluk_modeller(
    rng: np.random.Generator,
    sira: int,
    line: str,
    agirliklar: dict[str, float],
    hedef: int,
    renk_havuzu: list[str],
    sezon_kodu: str,
    dalgalar: list,
    cikis,
) -> tuple[list[dict], int]:
    """Bir sezon × line (Collection/Outlet) için modelleri üretir; dalga
    modeller arasında sırayla (round-robin) dağıtılır."""
    dagilim = _dagit(hedef, agirliklar)
    alt_r, ust_r = sabitler.RENK_SAYISI_ARALIGI[line]
    modeller = []
    model_sayaci = 0
    for alt_kategori in sorted(dagilim):
        for renk_n in _renk_gruplari(dagilim[alt_kategori], alt_r, ust_r, rng):
            dalga = (model_sayaci % 3) + 1
            modeller.append(
                _model_uret(
                    rng, sira, alt_kategori, line, renk_n, renk_havuzu,
                    sezon_kodu, dalga, pd.Timestamp(dalgalar[dalga - 1]), pd.Timestamp(cikis),
                )
            )
            sira += 1
            model_sayaci += 1
    return modeller, sira


def _devamli_modeller(
    rng: np.random.Generator, sira: int, line: str, agirliklar: dict[str, float], hedef: int
) -> tuple[list[dict], int]:
    dagilim = _dagit(hedef, agirliklar)
    alt_r, ust_r = sabitler.RENK_SAYISI_ARALIGI[line]
    modeller = []
    for alt_kategori in sorted(dagilim):
        for renk_n in _renk_gruplari(dagilim[alt_kategori], alt_r, ust_r, rng):
            modeller.append(
                _model_uret(
                    rng, sira, alt_kategori, line, renk_n, sabitler.DEVAMLI_RENK_HAVUZU,
                    sabitler.DEVAMLI, 0,
                    pd.Timestamp(sabitler.ISINMA_BASLANGIC), pd.NaT,
                )
            )
            sira += 1
    return modeller, sira


def _modelleri_uret(rng: np.random.Generator, olcek: Olcek) -> list[dict]:
    carpan = olcek.option_carpani
    modeller: list[dict] = []
    sira = 1

    for line, hedef_taban in (
        ("Basic", sabitler.DEVAMLI_BASIC_OPTION),
        ("NOS", sabitler.DEVAMLI_NOS_OPTION),
    ):
        hedef = round(hedef_taban * carpan)
        yeni, sira = _devamli_modeller(rng, sira, line, sabitler.ALT_KATEGORI_AGIRLIK[line], hedef)
        modeller.extend(yeni)

    tum_renkler = list(sabitler.RENKLER)
    for kod, s in sabitler.SEZONLAR.items():
        tip = kod[:2]  # "AW" | "SS"
        agirliklar = sabitler.ALT_KATEGORI_AGIRLIK[tip]
        for line, hedef_taban in (
            ("Collection", sabitler.SEZON_COLLECTION_OPTION),
            ("Outlet", sabitler.SEZON_OUTLET_OPTION),
        ):
            hedef = round(hedef_taban * carpan)
            yeni, sira = _sezonluk_modeller(
                rng, sira, line, agirliklar, hedef, tum_renkler, kod, s["dalgalar"], s["cikis"]
            )
            modeller.extend(yeni)
    return modeller


# ---------------------------------------------------------------------------
# option / SKU tabloları
# ---------------------------------------------------------------------------


def _optionlari_kur(modeller: list[dict]) -> pd.DataFrame:
    satirlar = []
    for model in modeller:
        for renk in model["renkler"]:
            renk_kodu = sabitler.RENKLER[renk]
            satirlar.append(
                {
                    "option_id": f"{model['model_kodu']}-{renk_kodu}",
                    "model_kodu": model["model_kodu"],
                    "model_adi": model["model_adi"],
                    "marka": sabitler.MARKA,
                    "cinsiyet": model["cinsiyet"],
                    "ust_kategori": model["ust_kategori"],
                    "alt_kategori": model["alt_kategori"],
                    "line": model["line"],
                    "sezon_kodu": model["sezon_kodu"],
                    "dalga": model["dalga"],
                    "renk": renk,
                    "renk_kodu": renk_kodu,
                    "beden_seti": model["beden_seti"],
                    "kumas": model["kumas"],
                    "kalip": model["kalip"],
                    "desen": model["desen"],
                    "detay": model["detay"],
                    "detay_alani": model["detay_alani"],
                    "fiyat_segmenti": model["fiyat_segmenti"],
                    "alis_fiyati": model["alis_fiyati"],
                    "lansman_tarihi": model["lansman_tarihi"],
                    "cikis_tarihi": model["cikis_tarihi"],
                    "tedarikci_id": None,
                    "_bedenler": model["bedenler"],
                }
            )
    opt = pd.DataFrame(satirlar)
    opt["dalga"] = opt["dalga"].astype("Int64")
    opt["lansman_tarihi"] = pd.to_datetime(opt["lansman_tarihi"])
    opt["cikis_tarihi"] = pd.to_datetime(opt["cikis_tarihi"])

    opt["liste_fiyati"] = liste_fiyati(
        opt["alis_fiyati"].to_numpy(), opt["fiyat_segmenti"].to_numpy()
    )

    sezonluk = opt["sezon_kodu"] != sabitler.DEVAMLI
    indirim_tarihi = opt["sezon_kodu"].map(
        {k: pd.Timestamp(s["indirim"]) for k, s in sabitler.SEZONLAR.items()}
    )
    cikis_gun_sezonluk = opt["cikis_tarihi"].apply(
        lambda t: gun_indisi(t) if pd.notna(t) else _BUYUK
    )
    opt["sezonluk"] = sezonluk
    opt["lansman_gun"] = opt["lansman_tarihi"].apply(gun_indisi)
    opt["indirim_gun"] = np.where(
        sezonluk, indirim_tarihi.apply(lambda t: gun_indisi(t) if pd.notna(t) else _BUYUK), _BUYUK
    )
    opt["cikis_gun"] = np.where(sezonluk, cikis_gun_sezonluk, _BUYUK)
    return opt


def _urunleri_kur(optionlar: pd.DataFrame) -> pd.DataFrame:
    satirlar = []
    for _, o in optionlar.iterrows():
        for beden_sira, beden in enumerate(o["_bedenler"], start=1):
            satirlar.append(
                {
                    "urun_id": f"{o['option_id']}-{beden}",
                    "option_id": o["option_id"],
                    "model_kodu": o["model_kodu"],
                    "model_adi": o["model_adi"],
                    "ad": f"{o['cinsiyet']} {o['line']} {o['model_adi']} {o['renk']} {beden}",
                    "marka": o["marka"],
                    "cinsiyet": o["cinsiyet"],
                    "ust_kategori": o["ust_kategori"],
                    "alt_kategori": o["alt_kategori"],
                    "line": o["line"],
                    "sezon_kodu": o["sezon_kodu"],
                    "dalga": o["dalga"],
                    "renk": o["renk"],
                    "renk_kodu": o["renk_kodu"],
                    "beden_seti": o["beden_seti"],
                    "beden": beden,
                    "beden_sira": beden_sira,
                    "kumas": o["kumas"],
                    "kalip": o["kalip"],
                    "desen": o["desen"],
                    "detay": o["detay"],
                    "detay_alani": o["detay_alani"],
                    "fiyat_segmenti": o["fiyat_segmenti"],
                    "alis_fiyati": o["alis_fiyati"],
                    "liste_fiyati": o["liste_fiyati"],
                    "lansman_tarihi": o["lansman_tarihi"],
                    "cikis_tarihi": o["cikis_tarihi"],
                    "tedarikci_id": o["tedarikci_id"],
                }
            )
    df = pd.DataFrame(satirlar)
    df["dalga"] = df["dalga"].astype("Int64")
    df["lansman_tarihi"] = pd.to_datetime(df["lansman_tarihi"])
    df["cikis_tarihi"] = pd.to_datetime(df["cikis_tarihi"])
    return df


def urunleri_uret(rng: np.random.Generator, olcek: Olcek) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`urunler` (SKU düzeyi) ve `optionlar` tablolarını üretir.

    `tedarikci_id` burada boştur (Görev 6 doldurur); `alis_fiyati`
    tedarikçi çarpanını içermez (Görev 6 uygular ve `liste_fiyati` ile
    yeniden hesaplar).
    """
    modeller = _modelleri_uret(rng, olcek)
    optionlar = _optionlari_kur(modeller)
    urunler = _urunleri_kur(optionlar)
    optionlar = optionlar.drop(columns=["_bedenler"]).reset_index(drop=True)
    return urunler, optionlar


# ---------------------------------------------------------------------------
# Fiyat, paket
# ---------------------------------------------------------------------------


def liste_fiyati(alis: np.ndarray, segment: np.ndarray) -> np.ndarray:
    """Lumoda liste fiyatı kuralı: alış × segment çarpanı, ",99"a
    yuvarlanır (`ceil(x/10)*10 - 0.01`). Saf fonksiyon — Görev 6 tedarikçi
    çarpanı uygulanmış alışla yeniden çağırır."""
    alis = np.asarray(alis, dtype=float)
    segment = np.asarray(segment, dtype=object)
    bilinmeyen = set(segment.ravel().tolist()) - set(sabitler.LISTE_FIYATI_CARPANI)
    if bilinmeyen:
        raise ValueError(f"liste_fiyati: bilinmeyen fiyat segmenti {sorted(map(str, bilinmeyen))}")
    carpan = np.vectorize(sabitler.LISTE_FIYATI_CARPANI.get)(segment).astype(float)
    ham = alis * carpan
    return np.ceil(ham / 10.0) * 10.0 - 0.01


def paketleri_uret() -> pd.DataFrame:
    """`paket` tablosu: her beden setine tek standart paket
    ([1, 2, 2, 1, 1]); Aksesuar (Standart, STD) koli adediyle (× 6)."""
    # Beden seti adı → bedenler; BEDEN_SETLERI'nin (cinsiyet, üst kategori)
    # anahtarları aynı isme birden fazla kez işaret eder (ör. Kadın Harf),
    # burada isim başına tek satır kalsın diye tekilleştirilir.
    setler: dict[str, list[str]] = {}
    for isim, bedenler in sabitler.BEDEN_SETLERI.values():
        setler.setdefault(isim, bedenler)
    setler.setdefault(sabitler.AKSESUAR_BEDEN_SETI[0], sabitler.AKSESUAR_BEDEN_SETI[1])

    satirlar = []
    for i, (isim, bedenler) in enumerate(sorted(setler.items()), start=1):
        paket_id = f"PKT{i:02d}"
        if isim == sabitler.AKSESUAR_BEDEN_SETI[0]:
            satirlar.append(
                {
                    "paket_id": paket_id,
                    "beden_seti": isim,
                    "beden_sira": 1,
                    "adet": sabitler.AKSESUAR_KOLI_ADEDI,
                }
            )
            continue
        for beden_sira, adet in enumerate(sabitler.PAKET_ADETLERI, start=1):
            satirlar.append(
                {"paket_id": paket_id, "beden_seti": isim, "beden_sira": beden_sira, "adet": adet}
            )
    return pd.DataFrame(satirlar)
