"""`kiriklik.olcutler`: korunum ve ölçüm tanımları oyuncak koşularla (`motor.Kosu`), KÜÇÜK dünyada kesilen plan
satırı ve ölçümün yapısı (`veri`).

**Oyuncak dünya** (AW24: karar 2024-12-09 pazartesi, indirim 2025-01-02 perşembe, çıkış 2025-02-24 pazartesi; outlet
penceresi 2025-05-19'a kadar). Mağazalar S1 AVM (alıcı), S2 Cadde ve S3 AVM (verici), OUT Outlet, ONL Online.
Option'lar: `A`, `B` (AW24 Collection, beş beden; A liste 500 / alış 200, B 400 / 150), `STD` (AW24 Collection
Standart: kapsam dışı), `Z` (SS24 Collection: test dışı).

**Plan** (3 hareket, 4 adet, 2 rota): A-2 S2 → S1 (2), A-3 S3 → S1 (1), B-2 S2 → S1 (1). S2 → S1 rotası iki option
taşır (kargo bir kez). Planın satırları karar günü `sevkiyat`'ında `elle_transfer`, varış 2024-12-12; iki koşuda da
Lumoda'nın bir elle transferi (S3 → S2, Z-1, 4) var.
"""

import json
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from allocation import motor

import kiriklik
from kiriklik import olcu, olcutler, plan as plan_modulu, sabitler, simulasyon
from kiriklik.plan import Plan

SEZON = "AW24"
KARAR = sabitler.KARAR[SEZON]


def _t(s) -> pd.Timestamp:
    return pd.Timestamp(s)


def _df(satirlar, sutunlar, tarihler=()) -> pd.DataFrame:
    df = pd.DataFrame(satirlar, columns=sutunlar)
    for s in tarihler:
        df[s] = pd.to_datetime(df[s])
    return df


# ---------------------------------------------------------------------------
# Oyuncak dünya
# ---------------------------------------------------------------------------

_OPTIONLAR = [  # option_id, line, sezon, beden_seti, beden sayısı, liste, alış
    ("A", "Collection", "AW24", "Kadın Harf", 5, 500.0, 200.0),
    ("B", "Collection", "AW24", "Kadın Harf", 5, 400.0, 150.0),
    ("STD", "Collection", "AW24", "Standart", 1, 100.0, 40.0),
    ("Z", "Collection", "SS24", "Kadın Harf", 5, 600.0, 250.0),
]


def _urun() -> pd.DataFrame:
    return _df([(f"{o}-{i}", o, line, sezon, seti, i, liste, alis)
                for o, line, sezon, seti, n, liste, alis in _OPTIONLAR for i in range(1, n + 1)],
               ["urun_id", "option_id", "line", "sezon_kodu", "beden_seti", "beden_sira", "liste_fiyati",
                "alis_fiyati"])


def _magaza() -> pd.DataFrame:
    return _df([("S1", "AVM"), ("S2", "Cadde"), ("S3", "AVM"), ("OUT", "Outlet"), ("ONL", "Online")],
               ["magaza_id", "tip"])


def _sezon() -> pd.DataFrame:
    return _df([("AW24", 1, "2024-08-19", "2025-01-02", "2025-02-24"),
                ("AW24", 2, "2024-09-16", "2025-01-02", "2025-02-24"),
                ("SS24", 1, "2024-02-19", "2024-06-27", "2024-08-26")],
               ["sezon_kodu", "dalga", "lansman_tarihi", "indirim_baslangic", "cikis_tarihi"],
               ["lansman_tarihi", "indirim_baslangic", "cikis_tarihi"])


SATIS = ["tarih", "magaza_id", "urun_id", "adet", "tutar"]
SEVK = ["tarih", "varis_tarihi", "kaynak", "hedef", "urun_id", "adet", "tip", "paket_id"]
STOK = ["tarih", "magaza_id", "urun_id", "adet", "stoklu_gun"]
DEPO = ["tarih", "urun_id", "adet"]
GERCEK = ["tarih", "magaza_id", "urun_id", "talep", "kendi_satis", "karsilanmayan", "ikameye_giden", "kalici_kayip"]

_ORTAK_SATIS = [
    ("2024-12-05", "S1", "A-1", 1, 500.0),          # karardan önce
    ("2024-12-10", "S1", "A-2", 1, 500.0),          # alıcı hücrede varıştan önce (iki koşuda aynı)
    ("2024-12-20", "ONL", "A-1", 1, 500.0),         # online
    ("2024-12-20", "S1", "Z-1", 2, 1200.0),         # test dışı
]
_LUMODA_SATIS = [
    ("2024-12-15", "S2", "A-2", 2, 1000.0),         # verici Lumoda'da 2 satar
    ("2025-03-10", "OUT", "A-4", 1, 150.0),         # outlet penceresi
]
_KOL_SATIS = [
    ("2024-12-14", "S1", "A-2", 3, 1500.0),         # alınan 2: saha min(3, 2) = 2
    ("2024-12-20", "S1", "A-2", -1, -500.0),        # iade: saha brüt pozitif satışla, etki net
    ("2025-01-10", "S1", "A-2", 1, 350.0),          # indirim penceresi
    ("2025-01-15", "S1", "A-3", 1, 350.0),          # alınan 1: indirime 0, çıkışa 1
    ("2024-12-20", "S1", "B-2", 1, 400.0),          # alınan 1: indirime 1
    ("2024-12-15", "S2", "A-2", 1, 500.0),          # verici kolda 1 satar (−1)
    ("2024-12-21", "S1", "Z-1", 1, 300.0),          # test dışı ciro farkı +300
    ("2025-06-01", "S1", "Z-1", 1, 300.0),          # pencere dışı
]


def _foto(tarih, hucreler: dict) -> list[tuple]:
    """{(mağaza, option): beden stokları} → stok satırları (sıfır bedenler satırsız)."""
    return [(tarih, m, f"{o}-{i + 1}", a, 7) for (m, o), st in hucreler.items() for i, a in enumerate(st) if a]


_KARAR_FOTO = {("S1", "A"): (1, 0, 0, 1, 1), ("S2", "A"): (1, 2, 0, 1, 1), ("S3", "A"): (0, 0, 1, 0, 0),
               ("S1", "B"): (1, 0, 2, 0, 1), ("S2", "B"): (0, 1, 0, 0, 0), ("S3", "B"): (1, 2, 2, 1, 1),
               ("OUT", "A"): (3, 0, 0, 0, 0), ("S1", "STD"): (5,)}
_KOL_VARIS_FOTO = {("S1", "A"): (1, 2, 1, 1, 1), ("S2", "A"): (1, 0, 0, 1, 1), ("S1", "B"): (1, 1, 2, 0, 1),
                   ("S3", "B"): (1, 2, 2, 1, 1), ("OUT", "A"): (3, 0, 0, 0, 0)}


def _stok(kol: bool) -> list[tuple]:
    satir = _foto("2024-12-02", _KARAR_FOTO) + _foto("2024-12-09", _KARAR_FOTO)
    satir += _foto("2024-12-16", _KOL_VARIS_FOTO if kol else _KARAR_FOTO)
    satir += [("2025-02-17", "OUT", "A-1", 2, 7)] + ([] if kol else [("2025-02-17", "S2", "A-2", 1, 7)])
    return satir


def _depo(kol: bool) -> list[tuple]:
    """Ölü stok günü çıkış + 120 = 2025-06-24; 2025-08-01 kapsamın son depo fotoğrafıdır (ölü stok sayılmaz)."""
    return [("2024-12-09", "A-1", 5), ("2025-02-17", "A-1", 5), ("2025-06-24", "A-1", 3 if kol else 4),
            ("2025-06-24", "Z-1", 9), ("2025-08-01", "A-1", 1)]


PLAN_SATIRLARI = [  # option_id, urun_id, beden_sira, verici, alici, adet
    ("A", "A-2", 2, "S2", "S1", 2), ("A", "A-3", 3, "S3", "S1", 1), ("B", "B-2", 2, "S2", "S1", 1)]


def _plan(satirlar=PLAN_SATIRLARI, kol="kural", bilgi=None) -> Plan:
    return Plan(kol=kol, sezon=SEZON, hareketler=pd.DataFrame(satirlar, columns=plan_modulu.KOLONLAR),
                bilgi=bilgi or {})


def _elle(satirlar, tarih="2024-12-09", varis="2024-12-12") -> list[tuple]:
    return [(tarih, varis, k, h, u, a, "elle_transfer", None) for k, h, u, a in satirlar]


_LUMODA_ELLE = [("S3", "S2", "Z-1", 4)]


def _plan_sevki(plan: Plan) -> list[tuple]:
    return [(r.verici, r.alici, r.urun_id, int(r.adet)) for r in plan.hareketler.itertuples()]


def _sevkiyat(kol: bool, karar_satirlari=None) -> list[tuple]:
    karar = _plan_sevki(_plan()) + _LUMODA_ELLE if kol else _LUMODA_ELLE
    satir = _elle(karar if karar_satirlari is None else karar_satirlari)
    satir += _elle([("S1", "S2", "A-5", 1)], tarih="2024-12-02", varis="2024-12-05")      # karardan önce
    satir += [("2024-12-16", "2024-12-17", "DEPO", "S2", "A-3", 3 if kol else 2, "replenishment", None),
              ("2024-12-16", "2024-12-17", "DEPO", "S1", "Z-1", 1, "replenishment", None)]
    if not kol:
        satir += _elle([("S2", "S3", "A-1", 1)], tarih="2024-12-23", varis="2024-12-25")
        satir += [("2025-02-24", "2025-02-25", "S2", "OUT", "A-2", 1, "outlet_akisi", None)]
    return satir


def _gercek(kol: bool) -> list[tuple]:
    return [("2024-12-20", "S1", "A-2", 3, 0 if not kol else 3, 3 if not kol else 0, 1, 2),
            ("2024-12-20", "ONL", "A-1", 5, 0, 5 if kol else 2, 0, 2),             # online: kapsam dışı
            ("2024-12-01", "S1", "A-1", 1, 1, 0, 0, 0)]


def _kayitlar(rpt=((1, 0, 10),)) -> dict:
    return {"rpt": _df(list(rpt), ["gun", "indis", "deger"]),
            "markdown": _df([(1, 0, 0, 0.3)], ["gun", "indis", "sutun", "deger"]),
            "ilk_dagitim": _df([(0, 1, 2)], ["gun", "indis", "deger"])}


def _siparis(adet=10, ek=(), kimlik="P1") -> pd.DataFrame:
    """Bir RPT siparişi (`kimlik`; adet `adet`) ve `ek` satırları (sürekli tedarik siparişleri gibi)."""
    return _df([(kimlik, "rpt", "A", "A-1", "2024-10-01", "2024-11-01", adet), *ek],
               ["siparis_id", "tip", "option_id", "urun_id", "siparis_tarihi", "gerceklesen_teslim", "adet"],
               ["siparis_tarihi", "gerceklesen_teslim"])


def _kosu(kol: bool, plan: Plan | None = None, *, satis=None, stok=None, depo=None, sevkiyat=None, kayitlar=None,
          fiyat_orani=0.3, siparis=None, kalite=None, gercek=None, meta_ek=None) -> motor.Kosu:
    satis = _ORTAK_SATIS + (_KOL_SATIS if kol else _LUMODA_SATIS) if satis is None else satis
    tablolar = {
        "urun": _urun(), "magaza": _magaza(), "sezon": _sezon(),
        "satis": _df(satis, SATIS, ["tarih"]),
        "stok": _df(_stok(kol) if stok is None else stok, STOK, ["tarih"]),
        "depo_stok": _df(_depo(kol) if depo is None else depo, DEPO, ["tarih"]),
        "sevkiyat": _df(_sevkiyat(kol) if sevkiyat is None else sevkiyat, SEVK, ["tarih", "varis_tarihi"]),
        "fiyat": _df([("2024-12-30", "A", "normal", fiyat_orani)], ["hafta_baslangic", "option_id", "hat",
                                                                      "indirim_orani"], ["hafta_baslangic"]),
        "siparis": _siparis() if siparis is None else siparis,
        "kalite_kontrol": _df([("P1", 1)] if kalite is None else kalite, ["siparis_id", "hatali"]),
    }
    for ad in ("satis", "stok", "sevkiyat"):
        tablolar[ad] = tablolar[ad].sort_values(["tarih"], kind="stable").reset_index(drop=True)
    meta = {"olcek": "kucuk", "gun_sayisi": None, "parametreler": {"yol": 0}, "turler": {},
            "anahtar": "lumoda" + "0" * 58}
    if kol:
        plan = _plan() if plan is None else plan
        meta.update(turler={"elle_transfer": "KirikTransfer", "rpt": "Kaydedici", "markdown": "Kaydedici"},
                    parametreler={"sezon": SEZON, "kol": plan.kol, "yol": 0}, anahtar="kol" + "0" * 61,
                    politikalar={"elle_transfer": {"parametreler": {"plan": plan.kimlik, "karar_gun": 1}}})
    meta.update(meta_ek or {})
    return motor.Kosu(tablolar=tablolar, gercek=_df(_gercek(kol) if gercek is None else gercek, GERCEK, ["tarih"]),
                      meta=meta, kayitlar=_kayitlar() if kayitlar is None else kayitlar)


@pytest.fixture(scope="module")
def lum():
    return _kosu(False)


@pytest.fixture(scope="module")
def kol():
    return _kosu(True)


@pytest.fixture(scope="module")
def olcum(kol, lum):
    return olcutler.olc(kol, lum, _plan(), SEZON)


# ---------------------------------------------------------------------------
# Satışa dönüş
# ---------------------------------------------------------------------------


def test_saha_olcusu_alinanla_sinirli(olcum):
    """Saha ölçüsü = Σ min(alıcı hücrenin varıştan [kesit) brüt pozitif satışı, alınan) ÷ Σ alınan: A-2 (alınan 2)
    varıştan indirime 3 satar → 2 sayılır, iade düşülmez, varıştan önceki satış girmez; A-3 (1) indirime 0, çıkışa 1;
    B-2 (1) indirime 1. İndirime (2 + 0 + 1) ÷ 4, çıkışa (2 + 1 + 1) ÷ 4."""
    s = olcum["satisa_donus"]
    assert s["alinan_adet"] == 4
    assert s["indirime_satilan"] == 3 and s["cikisa_satilan"] == 4
    assert s["saha_indirime"] == pytest.approx(0.75) and s["saha_cikisa"] == pytest.approx(1.0)


def test_etki_vericiyi_icerir(olcum):
    """Gerçek etki = transfer edilen option'ların bütün mağaza ve kanallardaki net satış farkı (kol − lumoda), pencere
    pencere: tam (alıcı +2 net, B +1, verici −1) = 2, indirim 2, outlet −1 (kolda outlet'e daha az mal kaldı) → 3; oran
    3 ÷ 4. Vericide kaybedilen −1, alıcıda kazanılan 5; saha yalnız alıcıyı görür."""
    s = olcum["satisa_donus"]
    assert s["etki_adet"] == {"tam": 2, "indirim": 2, "outlet": -1, "toplam": 3}
    assert s["etki_adet_fiziksel"] == {"tam": 2, "indirim": 2, "outlet": 0, "toplam": 4}
    assert s["etki_oran"] == pytest.approx(0.75)
    assert s["vericide_kayip_adet"] == -1 and s["alicida_kazanc_adet"] == 5
    # fiziksel sezon içi etki = alıcı kazancı + verici kaybı (oyuncakta başka hücre değişmez)
    f = s["etki_adet_fiziksel"]
    assert f["tam"] + f["indirim"] == s["alicida_kazanc_adet"] + s["vericide_kayip_adet"]


# ---------------------------------------------------------------------------
# Para ve maliyet
# ---------------------------------------------------------------------------


def test_para_pencereleri_ve_brut_kar(olcum):
    """Ciro farkı net TL (iade dahil): tam 1.900 − 1.000 = 900, indirim 700, outlet −150; sezon kapsamı aynı (öteki
    sezon option'ı Z kapsam dışı). Brüt kâr farkı = ciro farkı − Σ alış × net adet farkı
    = 1.450 − (2 × 200 + 1 × 150)."""
    c = olcum["para"]["ciro"]
    beklenen = {"tam": 900.0, "indirim": 700.0, "outlet": -150.0, "toplam": 1450.0}
    assert c["transfer_edilen"]["fark"] == beklenen and c["sezon"]["fark"] == beklenen
    assert c["sezon"]["lumoda"]["tam"] == pytest.approx(500.0 + 500.0 + 1000.0)       # 12-05 karardan önce
    assert olcum["para"]["brut_kar_farki"] == {"transfer_edilen": 900.0, "sezon": 900.0}


def test_olcum_rota_tekil(olcum):
    """Rota tekil (verici, alıcı) mağaza çiftidir, bütün option'lar üzerinden: S2 → S1 iki option taşır, kargo bir kez
    (2 rota, 3 değil). Maliyet = toplama × adet + kargo × rota + yıpranma × Σ alış × adet; net = sezon ciro farkı −
    maliyet."""
    p = olcum["plan"]
    assert p["rota"] == 2 and p["hareket"] == 3 and p["adet"] == 4
    alis = 2 * 200.0 + 1 * 200.0 + 1 * 150.0
    for ad, paket in sabitler.MALIYET_PAKETLERI.items():
        m = olcum["para"]["maliyet"][ad]
        assert m["kargo"] == pytest.approx(paket.kargo_rota_tl * 2)
        assert m["toplam"] == pytest.approx(paket.toplama_birim_tl * 4 + paket.kargo_rota_tl * 2
                                            + paket.yipranma_orani * alis)
        assert olcum["para"]["net"][ad] == pytest.approx(1450.0 - m["toplam"])
    assert olcum["para"]["net"]["orta"] == pytest.approx(1450.0 - (40.0 + 1000.0 + 37.5))
    # aynı adet, her hareket ayrı rotada olsaydı kargo üç kez
    ayri = olcutler.olc(_kosu(True, _plan([("A", "A-2", 2, "S2", "S1", 2), ("A", "A-3", 3, "S3", "S1", 1),
                                           ("B", "B-2", 2, "S2", "S3", 1)])), _kosu(False),
                        _plan([("A", "A-2", 2, "S2", "S1", 2), ("A", "A-3", 3, "S3", "S1", 1),
                               ("B", "B-2", 2, "S2", "S3", 1)]), SEZON)
    assert ayri["plan"]["rota"] == 3 and ayri["para"]["maliyet"]["orta"]["kargo"] == pytest.approx(1500.0)


def test_maliyet_paketleri_blok_ile_ayni():
    """`sabitler.MALIYET_PAKETLERI` Blok Transfer'in `getiri.MALIYET_PAKETLERI`'nin kopyasıdır: o dosya metin olarak
    okunur (içe aktarılmaz) ve üç `Paket(...)` sabiti karşılaştırılır."""
    getiri = Path(kiriklik.__file__).resolve().parents[2] / "blok-transfer" / "getiri.py"
    metin = getiri.read_text(encoding="utf-8")
    blok = re.search(r"MALIYET_PAKETLERI\s*=\s*\{(.*?)\}", metin, re.S)
    assert blok, "getiri.py'de MALIYET_PAKETLERI yok"
    paketler = {ad: tuple(float(x) for x in arg.split(","))
                for ad, arg in re.findall(r'"(\w+)"\s*:\s*Paket\(([^)]*)\)', blok.group(1))}
    assert paketler == {ad: (p.toplama_birim_tl, p.kargo_rota_tl, p.yipranma_orani)
                        for ad, p in sabitler.MALIYET_PAKETLERI.items()}
    assert sorted(paketler) == ["dusuk", "orta", "yuksek"]


# ---------------------------------------------------------------------------
# Kırıklık, stok, yan etki, plan
# ---------------------------------------------------------------------------


def test_kesit_tarihleri(olcum):
    """Kesitler: karar sabahı, karar + 7'den sonraki ilk pazartesi, indirimden önceki son pazartesi (indirim perşembe),
    çıkış − 7 pazartesisi."""
    assert {k: v["tarih"] for k, v in olcum["kiriklik"].items()} == {
        "karar": "2024-12-09", "varis_sonrasi": "2024-12-16", "indirim_oncesi": "2024-12-30",
        "cikis_oncesi": "2025-02-17"}
    assert olcum["tarihler"] == {"karar": "2024-12-09", "indirim": "2025-01-02", "cikis": "2025-02-24",
                                 "outlet_sonu": "2025-05-19", "son_gun": "2025-12-31"}


def test_kiriklik_kapsamlari(olcum):
    """Varış sonrası kesitte: alıcı çiftleri (S1-A, S1-B) Lumoda'da 4 kırık beden, kolda 1; verici çiftleri (S2-A, S3-A,
    S2-B) 9 → 2 (S3-A ve S2-B boşalıp paydadan çıkar: stoklu çift 3 → 1); bütün kapsam fiziksel mağazalar ve Standart
    dışı (OUT ve S1-STD girmez). Her özet `olcu.ozet`; fark mutlak sayılarda kol − lumoda."""
    k = olcum["kiriklik"]["varis_sonrasi"]["kapsamlar"]
    a, v, t, b = (k[x] for x in ("transfer_edilen_alici", "transfer_edilen_verici", "transfer_edilen", "butun"))
    assert (a["lumoda"]["kirik_beden"], a["kol"]["kirik_beden"], a["kol"]["kirik_cift"]) == (4, 1, 1)
    assert a["fark"] == {"kirik_beden": -3, "kirik_cift": -1, "stoklu_cift": 0,
                         "eksik_adet": a["kol"]["eksik_adet"] - a["lumoda"]["eksik_adet"]}
    assert (v["lumoda"]["kirik_beden"], v["kol"]["kirik_beden"]) == (9, 2)
    assert (v["lumoda"]["stoklu_cift"], v["kol"]["stoklu_cift"]) == (3, 1)
    assert (t["lumoda"]["kirik_beden"], t["kol"]["kirik_beden"]) == (13, 3)
    assert (b["lumoda"]["stoklu_cift"], b["kol"]["stoklu_cift"]) == (6, 4)
    assert b["lumoda"]["kirik_beden"] == 13
    hucre = pd.DataFrame([("S1", "A", i + 1, s) for i, s in enumerate((1, 0, 0, 1, 1))],
                         columns=["magaza_id", "option_id", "beden_sira", "stok"])
    karar_alici = olcum["kiriklik"]["karar"]["kapsamlar"]["transfer_edilen_alici"]["lumoda"]
    assert karar_alici["kirik_beden"] == 4 and set(karar_alici) == set(olcu.ozet(olcu.cift_tablosu(hucre)))
    # karar sabahı iki koşuda aynı
    assert all(v == 0 for x in olcum["kiriklik"]["karar"]["kapsamlar"].values() for v in x["fark"].values())


def test_stok_cikista_kalan_outlet_olu(olcum):
    """Çıkışta kalan = çıkış − 7 fotoğrafında mağaza (bütün mağaza tipleri, İndirim Takvimi tanımı) + depo; outlet'e
    giden `sevkiyat` tip `outlet_akisi`; ölü stok = çıkış + 120 gününde depo (son depo fotoğrafı değil)."""
    s = olcum["stok"]["sezon"]
    assert s["cikista_kalan"]["lumoda"] == {"magaza_adet": 3, "depo_adet": 5, "adet": 8, "liste": 4000.0,
                                            "alis": 1600.0}
    assert s["cikista_kalan"]["fark"]["adet"] == -1 and s["cikista_kalan"]["fark"]["alis"] == -200.0
    assert s["outlete_giden"]["lumoda"]["adet"] == 1 and s["outlete_giden"]["fark"] == {
        "adet": -1, "liste": -500.0, "alis": -200.0}
    assert s["olu_stok"]["lumoda"]["adet"] == 4 and s["olu_stok"]["fark"] == {"adet": -1, "alis": -200.0}
    assert olcum["stok"]["tarihler"] == {"cikis_fotografi": "2025-02-17", "olu_stok": "2025-06-24"}


def test_olu_stok_gunu_kapsanmazsa_none():
    """Koşu çıkış + 120'yi kapsamıyorsa ölü stok ölçülmez (iki koşuda None, tarih None); kısa koşunun son depo
    fotoğrafına düşülmez. Çıkış − 7 fotoğrafı kapsandığı için çıkışta kalan ölçülür."""
    son = (pd.Timestamp("2025-05-31") - pd.Timestamp("2022-07-04")).days + 1      # 2025-05-31 dahil
    o = olcutler.olc(_kosu(True, meta_ek={"gun_sayisi": son}), _kosu(False, meta_ek={"gun_sayisi": son}),
                     _plan(), SEZON)
    s = o["stok"]["sezon"]
    assert s["olu_stok"] is None and o["stok"]["tarihler"]["olu_stok"] is None
    assert s["cikista_kalan"]["lumoda"]["adet"] == 8


def test_yan_etki(olcum):
    """Replenishment adet farkı (sezon kapsamı ve bütün SKU'lar), Lumoda'nın elle transferinin farkı planın kendi
    satırları düşülerek, gizli kayıp farkı (fiziksel mağazalar; online girmez), test dışı ciro farkı
    [karar, çıkış + 84)."""
    y = olcum["yan_etki"]
    assert y["replenishment_adet_farki"] == {"sezon": 1, "tum": 1}
    assert y["elle_transfer_adet_farki"] == {"sezon": -1, "tum": -1}
    assert y["gizli_kayip_farki"] == -3 and y["gizli_kayip_lumoda"] == 3
    assert y["test_disi_ciro_farki"] == pytest.approx(300.0)
    assert y["test_disi_ciro_lumoda"] == pytest.approx(1200.0)


def test_elle_transfer_farki_sevk_edilen_plan_adediyle():
    """Lumoda'nın elle transfer farkından planın karar günü gerçekten sevk edilen satırları düşülür (planlanan adet
    değil): A-2 satırı 2 yerine 1 sevk edilirse kolun elle transferi 1 azalır ve düşülen de 1 azalır; fark yine −1
    (Lumoda'nın kendi elle transferinin farkı)."""
    kesik = [("S2", "S1", "A-2", 1)] + _plan_sevki(_plan())[1:] + _LUMODA_ELLE
    o = olcutler.olc(_kosu(True, sevkiyat=_sevkiyat(True, kesik)), _kosu(False), _plan(), SEZON)
    assert o["yan_etki"]["elle_transfer_adet_farki"] == {"sezon": -1, "tum": -1}


def test_plan_ozeti(olcum):
    """Hareket, rota, adet, option, alıcı ve verici çifti; tamamlanan set (karar sabahı stoğu + alınan, her beden ≥ 1:
    S1-A tamamlanır, S1-B'nin dördüncü bedeni boş kalır); alıcı başına verici medyanı (2 ve 1), rota başına adet
    medyanı (3 ve 1); çözücü alanları yoksa boş."""
    p = olcum["plan"]
    assert {k: p[k] for k in ("hareket", "adet", "rota", "option", "alici_cift", "alici_magaza", "verici_cift",
                              "verici_magaza", "tamamlanan_set")} == {
        "hareket": 3, "adet": 4, "rota": 2, "option": 2, "alici_cift": 2, "alici_magaza": 1, "verici_cift": 3,
        "verici_magaza": 2, "tamamlanan_set": 1}
    assert p["alici_basina_verici_medyan"] == 1.5 and p["rota_basina_adet_medyan"] == 2.0
    assert p["cozucu"] == {}
    bilgi = {"durum": "Optimal", "gap": np.float64(0.011), "kaynak": "daraltilmis", "puanlar": [1, 2]}
    o = olcutler.olc(_kosu(True, _plan(bilgi=bilgi)), _kosu(False), _plan(bilgi=bilgi), SEZON)
    assert o["plan"]["cozucu"] == {"durum": "Optimal", "gap": 0.011, "kaynak": "daraltilmis"}


def test_lumoda_farklari_sifir(lum):
    """`olc(lumoda, lumoda, bos)`: her fark sıfır, maliyet sıfır, oranlar tanımsız (None); çıktı JSON'a döner."""
    o = olcutler.olc(lum, lum, plan_modulu.bos("lumoda", SEZON, {}), SEZON)
    json.dumps(o, allow_nan=False)

    def farklar(x, yol=""):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "fark" or k.endswith("_farki") or k in ("etki_adet", "etki_adet_fiziksel", "net",
                                                                 "vericide_kayip_adet", "alicida_kazanc_adet"):
                    yield from _sayilar(v, f"{yol}.{k}")
                else:
                    yield from farklar(v, f"{yol}.{k}")

    bulunan = list(farklar(o))
    assert len(bulunan) > 50
    assert all(v == 0 for _, v in bulunan), [(y, v) for y, v in bulunan if v != 0]
    assert all(m["toplam"] == 0 for m in o["para"]["maliyet"].values())
    assert o["satisa_donus"]["saha_indirime"] is None and o["satisa_donus"]["etki_oran"] is None
    assert o["plan"]["hareket"] == 0 and o["plan"]["alici_basina_verici_medyan"] is None
    assert all(olcutler.korunum(lum, lum, plan_modulu.bos("lumoda", SEZON, {}), KARAR).values())


def _sayilar(x, yol):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _sayilar(v, f"{yol}.{k}")
    else:
        yield yol, x


def test_olcum_dogrulamalari(kol, lum):
    """Yanlış girdi `ValueError`: Lumoda olmayan taban, planın kimliği koşununkinden farklı, sezon uyuşmazlığı,
    ölçek ya da gün sayısı farklı, Lumoda koşusu kol yerine verilip plan boş değil."""
    with pytest.raises(ValueError, match="Lumoda"):
        olcutler.olc(kol, kol, _plan(), SEZON)
    with pytest.raises(ValueError, match="kimli"):
        olcutler.olc(kol, lum, _plan(PLAN_SATIRLARI[:2]), SEZON)
    with pytest.raises(ValueError, match="sezon"):
        olcutler.olc(kol, lum, _plan(), "SS25")
    with pytest.raises(ValueError, match="gun_sayisi"):
        olcutler.olc(_kosu(True, meta_ek={"gun_sayisi": 900}), lum, _plan(), SEZON)
    with pytest.raises(ValueError, match="boş"):
        olcutler.olc(lum, lum, _plan(), SEZON)
    with pytest.raises(ValueError, match="karar"):
        olcutler.korunum(kol, lum, _plan(), date(2024, 12, 16))


def test_kisa_kosuda_kapsanmayan_alanlar_none():
    """Koşunun son gününden sonraya uzanan pencere ve kesit ölçülmez (None); kapsananlar ölçülür."""
    son = (pd.Timestamp("2024-12-20") - pd.Timestamp("2022-07-04")).days + 1      # 2024-12-20 dahil
    o = olcutler.olc(_kosu(True, meta_ek={"gun_sayisi": son}), _kosu(False, meta_ek={"gun_sayisi": son}),
                     _plan(), SEZON)
    assert o["tarihler"]["son_gun"] == "2024-12-20"
    assert o["kiriklik"]["varis_sonrasi"]["kapsamlar"] is not None
    assert o["kiriklik"]["indirim_oncesi"]["kapsamlar"] is None
    assert o["satisa_donus"]["saha_indirime"] is None and o["satisa_donus"]["etki_adet"]["tam"] is None
    assert o["para"]["net"]["orta"] is None and o["stok"]["sezon"]["cikista_kalan"] is None
    json.dumps(o, allow_nan=False)


# ---------------------------------------------------------------------------
# Korunum
# ---------------------------------------------------------------------------


def test_korunum_oyuncak(kol, lum):
    """Oyuncak kolda beş koşul da tutar; her biri kendi bozulmasıyla düşer."""
    sonuc = olcutler.korunum(kol, lum, _plan(), KARAR)
    assert tuple(sonuc) == olcutler.KORUNUM_KOSULLARI and all(sonuc.values())

    def k(**ek):
        return olcutler.korunum(_kosu(True, **ek), lum, _plan(), KARAR)

    satis = _ORTAK_SATIS + _KOL_SATIS
    assert not k(satis=[("2024-12-08", "S1", "A-1", 1, 500.0)] + satis)["oncesi_birebir"]   # karar öncesi satış
    assert k(satis=[("2024-12-09", "S1", "A-1", 1, 500.0)] + satis)["oncesi_birebir"]       # karar günü dışarıda
    stok = _stok(True)
    assert not k(stok=stok + [("2024-12-09", "S2", "B-5", 1, 7)])["oncesi_birebir"]         # karar sabahı fotoğrafı
    assert not k(gercek=_gercek(True) + [("2024-12-02", "S1", "A-2", 1, 0, 1, 0, 1)])["oncesi_birebir"]
    assert not k(kayitlar=_kayitlar(rpt=((1, 0, 10), (500, 0, 3))))["rpt_birebir"]           # kısa ya da yabancı takvim
    assert not k(fiyat_orani=0.4)["fiyat_birebir"]
    md = _kayitlar()
    md["markdown"] = _df([(1, 0, 0, 0.5)], ["gun", "indis", "sutun", "deger"])
    assert not k(kayitlar=md)["fiyat_birebir"]
    assert not k(siparis=_siparis(adet=11))["siparis_birebir"]
    assert not k(depo=_depo(True) + [("2024-12-09", "B-1", 2)])["oncesi_birebir"]         # karar sabahı depo
    assert not k(sevkiyat=_sevkiyat(True) + [("2024-12-06", "2024-12-08", "DEPO", "S1", "B-1", 1, "replenishment",
                                              None)])["oncesi_birebir"]                    # karardan önce sevkiyat
    assert not k(kalite=[("P1", 0)])["siparis_birebir"]                                    # kalite kontrol


def test_surekli_tedarik_tepkili():
    """Basic/NOS sürekli tedarik (`tip == "surekli"`) motorun içinde zincir satışına tepki verir (yuva değildir): kolda
    farklı bir sürekli sipariş ve onun kalite kontrolü korunumu bozmaz, yan etkide `surekli_siparis_adet_farki` olarak
    görünür. `siparis_id` sıra numarasıdır (sürekli siparişler araya girince kayar): ilk ve RPT siparişleri içerikle
    karşılaştırılır; RPT siparişinin içeriği ya da kalite kontrolü değişirse korunum bozulur."""
    lum = _kosu(False, siparis=_siparis(kimlik="P2"), kalite=[("P2", 1)])
    surekli = [("P1", "surekli", "N", "N-1", "2025-01-06", "2025-03-03", 5)]
    kol = _kosu(True, siparis=_siparis(ek=surekli, kimlik="P2"), kalite=[("P2", 1), ("P1", 3)])
    sonuc = olcutler.korunum(kol, lum, _plan(), KARAR)
    assert all(sonuc.values()), sonuc
    assert olcutler.olc(kol, lum, _plan(), SEZON)["yan_etki"]["surekli_siparis_adet_farki"] == 5
    assert olcutler.olc(_kosu(True), _kosu(False), _plan(), SEZON)["yan_etki"]["surekli_siparis_adet_farki"] == 0
    assert not olcutler.korunum(_kosu(True, siparis=_siparis(adet=11, ek=surekli, kimlik="P2"),
                                      kalite=[("P2", 1), ("P1", 3)]), lum, _plan(), KARAR)["siparis_birebir"]
    assert not olcutler.korunum(_kosu(True, siparis=_siparis(ek=surekli, kimlik="P2"),
                                      kalite=[("P2", 2), ("P1", 3)]), lum, _plan(), KARAR)["siparis_birebir"]


def _tembel(kosu: motor.Kosu, dizin: Path) -> motor.KosuKaydi:
    """Oyuncak koşuyu motorun yazıcısıyla Parquet'e yazar, tembel kayıt olarak okur."""
    meta = {**kosu.meta, "tablolar": sorted(kosu.tablolar), "kayitlar": sorted(kosu.kayitlar)}
    motor._yaz(dizin, motor.Kosu(tablolar=kosu.tablolar, gercek=kosu.gercek, meta=meta, kayitlar=kosu.kayitlar))
    return motor._oku_tembel(dizin, meta["anahtar"])


def test_tembel_kayit_ayni_sonuc(tmp_path, kol, lum, olcum):
    """Tembel kayıtla (Parquet, DuckDB görünümü ve Arrow hızlı yolu) ölçüm ve korunum bellekteki koşuyla aynı; satır
    sırası farklı ama çoklu kümesi aynı tablo birebir sayılır, bir satırı farklı tablo sayılmaz."""
    tk, tl = _tembel(kol, tmp_path / "kol"), _tembel(lum, tmp_path / "lum")
    assert olcutler.olc(tk, tl, _plan(), SEZON) == olcum
    assert all(olcutler.korunum(tk, tl, _plan(), KARAR).values())
    karisik = _kosu(True)
    karisik.tablolar["satis"] = karisik.tablolar["satis"].iloc[::-1].reset_index(drop=True)
    assert all(olcutler.korunum(_tembel(karisik, tmp_path / "karisik"), tl, _plan(), KARAR).values())
    bozuk = _kosu(True, satis=[("2024-12-06", "S2", "B-1", 1, 400.0)] + _ORTAK_SATIS[1:] + _KOL_SATIS)
    assert not olcutler.korunum(_tembel(bozuk, tmp_path / "bozuk"), tl, _plan(), KARAR)["oncesi_birebir"]


def test_plan_kesilmedi_coklu_kume(lum):
    """Kolun karar günü `elle_transfer` satırları = planın satırları + Lumoda'nın (kesilmiş olabilir) satırları.
    Kesilen, atılan ya da yönü değişen plan satırı False; planın stoğu tükettiği için kesilen Lumoda satırı (K6'nın tepkisi)
    True."""
    tam = _plan_sevki(_plan())

    def k(karar_satirlari):
        return olcutler.korunum(_kosu(True, sevkiyat=_sevkiyat(True, karar_satirlari)), lum, _plan(),
                                KARAR)["plan_kesilmedi"]

    assert k(tam + _LUMODA_ELLE)
    assert not k([("S2", "S1", "A-2", 1)] + tam[1:] + _LUMODA_ELLE)        # kesildi
    assert not k(tam[1:] + _LUMODA_ELLE)                                  # atıldı
    assert not k([("S2", "S3", "A-2", 2)] + tam[1:] + _LUMODA_ELLE)        # başka hedefe
    assert not k(tam + _LUMODA_ELLE + [("S1", "S2", "A-1", 1)])            # fazladan satır
    # Lumoda'nın aynı kaynaktan satırı planın arkasında kesildi: plan tam uygulandı
    lum2 = _kosu(False, sevkiyat=_sevkiyat(False, [("S2", "S3", "A-2", 3)] + _LUMODA_ELLE))
    kol2 = _kosu(True, sevkiyat=_sevkiyat(True, tam + [("S2", "S3", "A-2", 1)] + _LUMODA_ELLE))
    assert olcutler.korunum(kol2, lum2, _plan(), KARAR)["plan_kesilmedi"]
    kol3 = _kosu(True, sevkiyat=_sevkiyat(True, tam + _LUMODA_ELLE))                         # tamamen kesildi
    assert olcutler.korunum(kol3, lum2, _plan(), KARAR)["plan_kesilmedi"]
    kol4 = _kosu(True, sevkiyat=_sevkiyat(True, tam + [("S2", "S3", "A-2", 4)] + _LUMODA_ELLE))  # Lumoda'dan fazla
    assert not olcutler.korunum(kol4, lum2, _plan(), KARAR)["plan_kesilmedi"]


# ---------------------------------------------------------------------------
# KÜÇÜK dünya (veri): kesilen plan satırı ve ölçümün yapısı
# ---------------------------------------------------------------------------

KARAR_GUNU = simulasyon.karar_gun(SEZON)
GUN_SAYISI = KARAR_GUNU + 10          # varış sonrası kesit (karar + 7) kapsanır


@pytest.fixture(scope="module")
def onbellek(tmp_path_factory):
    return tmp_path_factory.mktemp("kosular")


@pytest.fixture(scope="module")
def k_lum(onbellek):
    return simulasyon.kos("lumoda", parametreler={}, onbellek=onbellek, gun_sayisi=GUN_SAYISI, olcek="kucuk")


def _kucuk_plan(lumoda, fazla: int = 0, satir: int = 2) -> Plan:
    """Karar günü fotoğrafında en az 2 adedi olan (fiziksel mağaza, AW24 Collection SKU) hücrelerinden 1'er adet
    (ilk satırda `fazla` kadar daha: vericinin stoğunu aşar), aynı SKU'nun hücresi olan başka bir fiziksel mağazaya."""
    karar = pd.Timestamp(KARAR)
    magaza, urun, stok = lumoda.tablo("magaza"), lumoda.tablo("urun"), lumoda.tablo("stok")
    fiz = set(magaza.loc[magaza["tip"].isin(sabitler.FIZIKSEL_TIPLER), "magaza_id"].astype(str))
    u = urun.astype({"urun_id": str, "option_id": str})
    u = u[(u["sezon_kodu"] == SEZON) & (u["line"] == sabitler.LINE) & (u["beden_seti"] != sabitler.STANDART_BEDEN_SETI)]
    st = stok[stok["tarih"] == karar].astype({"magaza_id": str, "urun_id": str})
    st = st[st["magaza_id"].isin(fiz) & st["urun_id"].isin(set(u["urun_id"]))].sort_values(["urun_id", "magaza_id"])
    satirlar, kullanilan = [], set()
    for r in st[st["adet"] >= 2].itertuples():
        alici = sorted(set(st.loc[st["urun_id"] == r.urun_id, "magaza_id"]) - {r.magaza_id})
        bilgi = u[u["urun_id"] == r.urun_id].iloc[0]
        if alici and bilgi.option_id not in kullanilan:
            adet = 1 + (fazla + int(r.adet) if fazla and not satirlar else 0)
            satirlar.append((bilgi.option_id, r.urun_id, int(bilgi.beden_sira), r.magaza_id, alici[0], adet))
            kullanilan.add(bilgi.option_id)
        if len(satirlar) == satir:
            break
    assert len(satirlar) == satir, "karar günü fotoğrafında yeterli hücre yok"
    return _plan(satirlar, kol="oyuncak")


def _kucuk_kol(ad, plan, lumoda, onbellek):
    return simulasyon.kos(ad, plan=simulasyon.transfer_plani(plan, motor.dunya("kucuk")),
                          takvim=simulasyon.takvim(lumoda), karar_gun=KARAR_GUNU,
                          parametreler={"sezon": SEZON, "kol": plan.kol}, onbellek=onbellek, gun_sayisi=GUN_SAYISI,
                          olcek="kucuk")


@pytest.mark.veri
def test_kesilen_plan_satiri_korunumu_bozar(k_lum, onbellek):
    """KÜÇÜK yol 0, AW24: planın bir satırı vericinin karar günü stoğundan fazla → motor satırı keser; `plan_kesilmedi`
    False (koşu ölçülmez), öteki koşullar tutar (karar sabahına kadar dünya ve aynı mal birebir)."""
    plan = _kucuk_plan(k_lum, fazla=50)
    k = _kucuk_kol("kesik", plan, k_lum, onbellek)
    sonuc = olcutler.korunum(k, k_lum, plan, KARAR)
    assert sonuc == {"oncesi_birebir": True, "rpt_birebir": True, "fiyat_birebir": True, "siparis_birebir": True,
                     "plan_kesilmedi": False}


@pytest.mark.veri
def test_kucuk_olcum(k_lum, onbellek):
    """KÜÇÜK yol 0, AW24, karar + 10 güne kısa koşu: korunum hepsi True; ölçümün bölümleri yerinde; varış sonrası kesit
    ölçülür, sonraki pencereler None; JSON'a döner. Lumoda kendine karşı sıfır fark."""
    plan = _kucuk_plan(k_lum)
    k = _kucuk_kol("oyuncak", plan, k_lum, onbellek)
    assert all(olcutler.korunum(k, k_lum, plan, KARAR).values())
    o = olcutler.olc(k, k_lum, plan, SEZON)
    json.dumps(o, allow_nan=False)
    assert set(o) == {"sezon", "tarihler", "kiriklik", "satisa_donus", "para", "stok", "yan_etki", "plan"}
    assert o["plan"]["hareket"] == 2 and o["plan"]["adet"] == 2
    v = o["kiriklik"]["varis_sonrasi"]["kapsamlar"]
    assert v is not None and v["butun"]["lumoda"]["stoklu_cift"] > 10
    assert v["transfer_edilen"]["lumoda"]["stoklu_cift"] >= 2
    assert o["kiriklik"]["cikis_oncesi"]["kapsamlar"] is None
    assert o["satisa_donus"]["saha_indirime"] is None and o["para"]["net"]["orta"] is None
    sifir = olcutler.olc(k_lum, k_lum, plan_modulu.bos("lumoda", SEZON, {}), SEZON)
    assert sifir["kiriklik"]["varis_sonrasi"]["kapsamlar"]["butun"]["fark"] == {
        "kirik_beden": 0, "kirik_cift": 0, "stoklu_cift": 0, "eksik_adet": 0}
