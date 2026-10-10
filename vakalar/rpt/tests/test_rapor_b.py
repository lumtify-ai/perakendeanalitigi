"""rapor_b.py'nin saf yardımcıları: koşu tablolarından FIFO akıbeti (oyuncakla), adlar.
Uçtan uca B bölümleri gerçek oyun önbelleği ister (`rapor.py`, el ile)."""

import pandas as pd
from test_hikaye import rpt_tablolari

import rapor
import rapor_b
from rpt import hikaye


class SahteKosu:
    """`motor.KosuKaydi` arayüzü: tablo(ad, sutunlar, urunler); kategorik sütunlarla
    (koşu Parquet'i kategorik döner)."""

    def __init__(self, t: dict):
        self.t = t

    def tablo(self, ad, sutunlar=None, urunler=None):
        df = self.t[ad].copy()
        if urunler is not None:
            df = df[df["urun_id"].astype(str).isin(set(map(str, urunler)))]
        if sutunlar is not None:
            df = df[list(sutunlar)]
        for c in ("urun_id", "magaza_id", "kaynak", "hedef", "tip"):
            if c in df.columns:
                df[c] = df[c].astype("category")
        return df.reset_index(drop=True)


def test_kosu_akibeti_yayimlanan_yukleyiciyle_ayni():
    """Koşunun günlük `depo_stok`'u pazartesiye süzülür (yayımlanan yükleyici gibi), satış
    yalnız online, kategorik kimlikler metne döner: sonuç `hikaye.rpt_akibeti` ile birebir."""
    t, opt = rpt_tablolari()
    beklenen_t = dict(t)
    d = t["depo_stok"]
    beklenen_t["depo_stok"] = d[pd.to_datetime(d["tarih"]).dt.dayofweek == 0].reset_index(drop=True)
    beklenen = hikaye.rpt_akibeti(beklenen_t, opt, "SS25").set_index("option_id").sort_index()
    sonuc = rapor_b.kosu_akibeti(SahteKosu(t), opt, "SS25").set_index("option_id").sort_index()
    sutun = ["rpt_giren", "depo_cikista", "rpt_depoda_cikista", "rpt_cikisa_kadar", "rpt_magazaya_alt",
             "rpt_magazaya_ust", "rpt_outlete", "rpt_depoda_kalan", "depo_son"]
    pd.testing.assert_frame_equal(sonuc[sutun], beklenen[sutun])
    assert all(ok for _, ok in rapor.fifo_denetimleri(sonuc.reset_index(), "oyuncak"))


def test_okunur_kol_adi():
    assert rapor_b._ad("mevcut|b") == "Banu / b"
    assert rapor_b._ad("oneri|b") == "öneri (LightGBM) / b"
    assert rapor_b._ad("kahin|a") == "kâhin / a"
