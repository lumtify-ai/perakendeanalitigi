"""Oyun: kolları v4 motorunda koşturur ve ölçer (spec §4.5). Görev 7 yalnız `kalibrasyon` alt
komutunu kurar (Ruling R22); Görev 8 ızgarayı ve `olcutler`'i ekler.

    .venv/Scripts/python -m allocation.oyun kalibrasyon      # cikti/kalibrasyon.json (Görev 7)

Bu modül koşu dışıdır (`motor.KOSU_DISI`): motoru içe aktarır, gizli gerçeği okur
(`tests/test_sizinti.py` izinli listesi). Kalibrasyon karar modülüdür; koşuyu ve ölçümü bu
modülün `kalibrasyon_kosucusu`'na bırakır (DM R5 kalıbı).

**Kalibrasyon** (`kalibrasyon_kos`). Yol 0, TAM: dünya (`motor.dunya`), yayımlanan tablolar
(`kaynak.yayimlanan_tablolar`) → `kalibrasyon.kosusuz` (tablolar sonra bellekten bırakılır) →
`kalibrasyon.simulasyon(kalibrasyon_kosucusu(...))` → `cikti/kalibrasyon.json`. Koşular sıralı,
önbellekli (`cikti/kosular/`, tembel); yeniden başlatılan iş önbellekten sürer (öğrenilen
nesnelerin kimliği içerikten: aynı veri aynı anahtar). `lumoda` referansı yayımlanan dünyadır
(`motor.kos(ad="lumoda", parametreler={})`, eşdeğerlik testiyle aynı anahtar). Kol koşusunda
kalibrasyon sezonunun option'larına süzülmüş `kirpma_tablosu` boş olmalı (Ruling R21: kollar U'ya
sığar; motor kırparsa koşu geçersiz, `RuntimeError`). Biten her koşu `cikti/ilerleme.jsonl`'a.

**Kalibrasyon ölçütleri** (Ruling R23: gizli gerçeği okuyan ölçüt karar modülünde değil, burada;
Görev 8'in `olcutler.hesapla`'sı aynı tanımları taşır). Sezonun `LINE` option'ları, fiziksel
mağazalar (`Harita.magaza_fiziksel`: Online ve Outlet tipi hariç):

    bulunabilirlik          100 × |talep > 0 ∧ kendi_satis > 0| ÷ |talep > 0| (DM R22): gizli
                            gerçeğin hücre-günleri, option'ın ilk dağıtım varışının ilk gününden
                            (koşunun `sevkiyat`'ı) çıkış gününe (hariç; o gün outlet akışı)
    sezon_sonu_kalan_yuzde  100 × (Σ `outlet_akisi` + Σ fiziksel mağazadan `stok_devri`) ÷
                            (teslim alınan ilk alım + RPT). Pay: çıkışta mağaza ve depo
                            stoğunun outlet'e akışı ile çıkıştan sonra fiziksel hücrelerden
                            depoya devredilen (iade, geç varış); outlet mağazasının outlet
                            penceresi sonundaki `stok_devri` outlet akışının kalanıdır, ikinci
                            kez sayılmaz. Payda: `siparis`'in teslim edilmiş (`gerceklesen_teslim`
                            dolu) `ilk` ve `rpt` satırlarının adedi − `kalite_kontrol`'ün o
                            siparişlerdeki `hatali` adedi (depoya giren)
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from allocation import kalibrasyon, kaynak, motor, sabitler

ILERLEME = sabitler.CIKTI / "ilerleme.jsonl"


def uyanik_tut() -> None:
    """Windows'ta süreç sürdükçe sistem uykusunu engeller (başka yerde etkisiz)."""
    if sys.platform == "win32":
        import ctypes

        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


def _ilerleme(ad: str, sn: float, onbellekten: bool, dosya: Path | None = ILERLEME, **ek) -> None:
    satir = {"ad": ad, "sn": round(float(sn), 1), "onbellekten": bool(onbellekten),
             "zaman": time.strftime("%Y-%m-%dT%H:%M:%S"), **ek}
    print(json.dumps(satir, ensure_ascii=False, default=str), flush=True)
    if dosya is not None:
        Path(dosya).parent.mkdir(parents=True, exist_ok=True)
        with open(dosya, "a", encoding="utf-8") as f:
            f.write(json.dumps(satir, ensure_ascii=False, default=str) + "\n")


# ---------------------------------------------------------------------------
# Kalibrasyon ölçütleri
# ---------------------------------------------------------------------------


def _skular(w, optionlar) -> np.ndarray:
    """Option'ların SKU kimlikleri (str)."""
    return w.urunler["urun_id"].astype(str).to_numpy()[np.isin(np.asarray(w.sku_option),
                                                                 np.asarray(optionlar, dtype=np.int64))]


def _option_id(w, urun_id: pd.Series) -> np.ndarray:
    """SKU kimliğinden option indisi (evren dışı -1)."""
    sku = pd.Index(w.urunler["urun_id"].astype(str)).get_indexer(urun_id.astype(str))
    return np.where(sku >= 0, np.asarray(w.sku_option)[np.maximum(sku, 0)], -1)


def _fiziksel(w, harita, magaza_id: pd.Series) -> np.ndarray:
    m = pd.Index(w.magazalar["magaza_id"].astype(str)).get_indexer(magaza_id.astype(str))
    return (m >= 0) & np.asarray(harita.magaza_fiziksel)[np.maximum(m, 0)]


def bulunabilirlik(gercek: pd.DataFrame, sevkiyat: pd.DataFrame, w, harita, optionlar) -> float:
    """Modül notu. `gercek`: `tarih, magaza_id, urun_id, talep, kendi_satis`; `sevkiyat`: koşunun
    `sevkiyat`'ı (en az `tarih, varis_tarihi, hedef, urun_id, tip`). Talepli hücre-gün yoksa 0."""
    optionlar = np.asarray(optionlar, dtype=np.int64)
    sv = sevkiyat[(sevkiyat["tip"] == "ilk_dagitim").fillna(False).to_numpy(dtype=bool)
                  & sevkiyat["varis_tarihi"].notna().to_numpy()]
    so = _option_id(w, sv["urun_id"])
    bas = pd.Series(pd.to_datetime(sv["varis_tarihi"]).dt.normalize().to_numpy(), index=so).groupby(level=0).min()
    cikis = pd.to_datetime(w.optionlar["cikis_tarihi"]).dt.normalize().to_numpy()

    o = _option_id(w, gercek["urun_id"])
    secili = np.isin(o, optionlar) & np.isin(o, bas.index.to_numpy()) & _fiziksel(w, harita, gercek["magaza_id"])
    g, o = gercek[secili], o[secili]
    tarih = pd.to_datetime(g["tarih"]).dt.normalize().to_numpy()
    icinde = (tarih >= bas.reindex(o).to_numpy()) & (tarih < cikis[o])
    talepli = icinde & (g["talep"].to_numpy() > 0)
    stoklu = talepli & (g["kendi_satis"].to_numpy() > 0)
    n = int(talepli.sum())
    return 100.0 * int(stoklu.sum()) / n if n else 0.0


def sezon_sonu_kalan_yuzde(sevkiyat: pd.DataFrame, siparis: pd.DataFrame, kalite: pd.DataFrame,
                           w, harita, optionlar) -> float:
    """Modül notu. `siparis`: `siparis_id, tip, option_id, gerceklesen_teslim, adet`; `kalite`:
    `siparis_id, hatali`. Teslim alınan mal yoksa 0."""
    optionlar = np.asarray(optionlar, dtype=np.int64)
    o = _option_id(w, sevkiyat["urun_id"])
    sv = sevkiyat[np.isin(o, optionlar)]
    tip = sv["tip"].astype(str).to_numpy()
    adet = sv["adet"].to_numpy(dtype=np.int64)
    kalan = int(adet[tip == "outlet_akisi"].sum())
    devir = (tip == "stok_devri") & _fiziksel(w, harita, sv["kaynak"])
    kalan += int(adet[devir].sum())

    ids = set(w.optionlar["option_id"].astype(str).to_numpy()[optionlar])
    sp = siparis[siparis["option_id"].astype(str).isin(ids).to_numpy()
                 & siparis["tip"].astype(str).isin(["ilk", "rpt"]).to_numpy()
                 & siparis["gerceklesen_teslim"].notna().to_numpy()]
    hatali = kalite[kalite["siparis_id"].astype(str).isin(set(sp["siparis_id"].astype(str)))]["hatali"]
    alinan = int(sp["adet"].to_numpy(dtype=np.int64).sum()) - int(hatali.to_numpy(dtype=np.int64).sum())
    return 100.0 * kalan / alinan if alinan > 0 else 0.0


def kal_olcutleri(kosu, w, harita, sezon: str = sabitler.KAL_SEZONU) -> dict[str, float]:
    """Koşunun (`Kosu` ya da tembel `KosuKaydi`) kalibrasyon ölçütleri, `sezon`un `LINE`
    hücrelerinde; tablolar yalnız gereken sütun ve SKU'larla okunur."""
    opt = kaynak.oyun_optionlari(w, sezon)
    sku = _skular(w, opt)
    sevk = kosu.tablo("sevkiyat", ["tarih", "varis_tarihi", "kaynak", "hedef", "urun_id", "adet", "tip"], urunler=sku)
    gercek = kosu.tablo("gercek", ["tarih", "magaza_id", "urun_id", "talep", "kendi_satis"], urunler=sku)
    siparis = kosu.tablo("siparis", ["siparis_id", "tip", "option_id", "gerceklesen_teslim", "adet"])
    kalite = kosu.tablo("kalite_kontrol", ["siparis_id", "hatali"])
    return {"bulunabilirlik": bulunabilirlik(gercek, sevk, w, harita, opt),
            "sezon_sonu_kalan_yuzde": sezon_sonu_kalan_yuzde(sevk, siparis, kalite, w, harita, opt)}


# ---------------------------------------------------------------------------
# Kalibrasyon koşucusu
# ---------------------------------------------------------------------------


def kalibrasyon_kosucusu(cev: kalibrasyon.Cevrimdisi, w, harita, *, onbellek: Path | None = motor.KOSU_DIZINI,
                         olcek: str = "tam", ilerleme: Path | None = ILERLEME):
    """`kalibrasyon.simulasyon`'un `kos_fn(ad, tanim) -> dict`'i: kolu kurar (`kalibrasyon.kol_kur`,
    temel Lumoda'nın ilk dağıtımı), yol 0'da koşar, kırpmayı denetler, ölçer."""
    ids = set(w.optionlar["option_id"].astype(str).to_numpy()[kaynak.oyun_optionlari(w, sabitler.KAL_SEZONU)])

    def kos_fn(ad: str, tanim: kalibrasyon.KalKol) -> dict:
        t0 = time.perf_counter()
        kol = kalibrasyon.kol_kur(tanim, cev, motor.lumoda("ilk_dagitim"), harita)
        if kol is None:
            k = motor.kos(ad="lumoda", parametreler={}, onbellek=onbellek, olcek=olcek, tembel=True)
        else:
            k = motor.kos(ilk_dagitim=kol, ad=ad, parametreler=tanim.parametreler(), onbellek=onbellek,
                          olcek=olcek, tembel=True)
            kirp = motor.kirpma_tablosu(k, w)
            kirp = kirp[kirp["option_id"].astype(str).isin(ids).to_numpy()]
            if len(kirp):
                raise RuntimeError(f"{ad}: motor kalibrasyon option'larında {len(kirp)} (option, mağaza) "
                                   "kırptı (kollar U'ya sığmalı; Ruling R21)")
        olcut = kal_olcutleri(k, w, harita, sabitler.KAL_SEZONU)
        sure = time.perf_counter() - t0
        ek = {"sure_sn": round(sure, 1), "motor_sn": k.meta.get("motor_sn"), "kosu_sn": k.meta.get("sure_sn"),
              "tepe_bellek_gb": k.meta.get("tepe_bellek_gb"), "onbellekten": bool(k.onbellekten),
              "anahtar": k.meta["anahtar"]}
        _ilerleme(ad, sure, k.onbellekten, ilerleme, blok="kalibrasyon", **olcut)
        return {**olcut, **ek}

    return kos_fn


def kalibrasyon_kos(yol: Path = kalibrasyon.DOSYA) -> dict:
    """Gerçek kalibrasyon (yol 0, TAM): koşusuz seçim, sonra 7 TAM koşu (+ önbellekli `lumoda`)."""
    uyanik_tut()
    t0 = time.perf_counter()
    w = motor.dunya("tam")
    harita = kaynak.harita_kur(w)
    con = kaynak.baglan()
    try:
        tablolar = kaynak.yayimlanan_tablolar(con)
    finally:
        con.close()
    cev = kalibrasyon.kosusuz(tablolar, w)
    del tablolar
    t1 = time.perf_counter()
    print(f"koşusuz: {t1 - t0:.0f} sn; en_az {cev.en_az}, tahmin {cev.tahmin_parametreleri}, "
          f"kaynak {cev.kaynak}, ölçü {cev.belirsizlik_olcusu}", flush=True)
    sim = kalibrasyon.simulasyon(kalibrasyon_kosucusu(cev, w, harita), cev)
    t2 = time.perf_counter()
    kalibrasyon.yaz(cev, sim, yol, kosusuz_sn=round(t1 - t0, 1), simulasyon_sn=round(t2 - t1, 1),
                    sure_sn=round(t2 - t0, 1))
    return kalibrasyon.oku(yol)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m allocation.oyun")
    alt = ap.add_subparsers(dest="komut", required=True)
    alt.add_parser("kalibrasyon", help="SS24 kalibrasyonu (cikti/kalibrasyon.json)")
    a = ap.parse_args(argv)
    if a.komut == "kalibrasyon":
        d = kalibrasyon_kos()
        print(json.dumps({k: d[k] for k in ("en_az", "tahmin_parametreleri", "kaynak", "belirsizlik_olcusu",
                                            "tavan", "gamma", "belirsizlik_taban", "izgara_ucunda",
                                            "belirsizlik_spearman", "gamma_bulunabilirlik_araligi_puan",
                                            "sure_sn")},
                         ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
