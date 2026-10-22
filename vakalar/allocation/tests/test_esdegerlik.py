"""Kilit: vakanın kapısından geçen Lumoda koşusu yayımlanan v4'ün ta kendisidir.

`veri` işaretli: bir TAM koşu (~4 dk, tepe ~8 GB). Koşu `lumoda` adıyla `cikti/kosular/`'a
yazılır (sonraki çağrılar oradan okur). Kıyas yayımlanan Parquet dışa aktarımına karşıdır
(`veri/cikti/v4/parquet/`; başka yerdeyse `PERAKENDE_V4_PARQUET`, ör. veri kopyası yalnız
DuckDB olan bir worktree'de ana checkout'unki); satır sayıları ve Σ adet DuckDB'den.

Koşu Lumoda'nın ilk dağıtım, RPT ve markdown kararlarını kaydeder (Ruling R2): sabit takvim
(`motor.takvim`) ve kırpma tablosu (`motor.kirpma_tablosu`) buradan kurulur.
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from allocation import kaynak, motor, sabitler


def _parquet_turu(df):
    """Parquet gidiş-dönüşü bellekte (yayımlama `to_parquet(index=False)`; koşu tabloları
    da Parquet'ten döner: kategori adı gibi üst veri düşer)."""
    import io

    tampon = io.BytesIO()
    df.to_parquet(tampon, index=False)
    tampon.seek(0)
    return pd.read_parquet(tampon)


def _parquet_dizini() -> Path:
    return Path(os.environ.get("PERAKENDE_V4_PARQUET") or kaynak.VERITABANI.parent / "parquet")


def _yayimlanan_ile_ayni(tablolar_temiz: dict) -> None:
    parquet = _parquet_dizini()
    tablolar = motor.yayimlanan_bicim(tablolar_temiz, "tam")
    yayimlanan = sorted(p.stem for p in parquet.glob("*.parquet"))
    assert len(yayimlanan) == 18
    assert sorted(tablolar) == yayimlanan
    for ad in yayimlanan:
        pd.testing.assert_frame_equal(
            _parquet_turu(tablolar[ad]), pd.read_parquet(parquet / f"{ad}.parquet"), obj=ad)
    con = kaynak.baglan()
    try:
        for ad in yayimlanan:
            n = con.execute(f"select count(*) from {ad}").fetchone()[0]
            assert len(tablolar[ad]) == int(n), ad
        adet = con.execute("select sum(adet) from satis").fetchone()[0]
    finally:
        con.close()
    assert int(tablolar["satis"]["adet"].sum()) == int(adet)


def _veri_yoksa_atla():
    if not kaynak.VERITABANI.exists() or not _parquet_dizini().exists():
        pytest.skip("yayımlanan v4 yok (DuckDB ya da Parquet dışa aktarımı)")


def _lumoda():
    return motor.kos(ad="lumoda", parametreler={}, onbellek=motor.KOSU_DIZINI, tembel=True)


@pytest.mark.veri
def test_lumoda_yayimlanan_v4_ile_ayni():
    """Lumoda + kaydediciler (ilk dağıtım, RPT, markdown) + varsayılan tohumlar (yol 0)
    `motor.kos`'tan geçince yayımlanan v4'tür: koşunun temiz tabloları `yayimlanan_bicim`le
    18 yayımlanan tablonun her biriyle değer, tür ve sıra olarak aynı (Parquet dışa
    aktarımına karşı; DuckDB satır sayıları, Σ adet). Kayıtlar dolu; motor Lumoda'nın
    paketlerini yalnız kırpar (giden ≤ istenen); oyun sezonunun Collection'ında kırpılan
    option, paket ve adet basılır."""
    _veri_yoksa_atla()
    k = _lumoda()
    print(f"\nkoşu: {'önbellekten' if k.onbellekten else 'yeni'}; "
          f"motor {k.meta.get('motor_sn')} sn, toplam {k.meta.get('sure_sn')} sn; "
          f"tepe bellek {k.meta.get('tepe_bellek_gb')} GB; "
          f"kayıt satırları { {a: len(d) for a, d in k.kayitlar.items()} }")
    assert k.meta["talep_tohumu"] is None and k.meta["operasyon_tohumu"] == motor.TOHUM
    assert k.meta["turler"] == {} and k.meta["olcek"] == "tam"
    _yayimlanan_ile_ayni(k.tablolar)

    assert sorted(k.kayitlar) == ["ilk_dagitim", "markdown", "rpt"]
    for ad, d in k.kayitlar.items():
        assert len(d) > 0, ad

    w = motor.dunya()
    t = motor.kirpma_tablosu(k)
    assert (t["giden_paket"] < t["istenen_paket"]).all()
    opt = w.optionlar.set_index("option_id")
    oyun = opt[(opt["sezon_kodu"] == sabitler.OYUN_SEZONU) & (opt["line"] == sabitler.LINE)]
    t = t[t["option_id"].isin(oyun.index)]
    paket = k.tablolar["paket"].groupby("beden_seti")["adet"].sum()
    icerik = oyun.loc[t["option_id"], "beden_seti"].map(paket).to_numpy()
    kirpilan = (t["istenen_paket"] - t["giden_paket"]).to_numpy()
    print(f"kırpma ({sabitler.OYUN_SEZONU} {sabitler.LINE}): {t['option_id'].nunique()}/{len(oyun)} "
          f"option, {len(t)} (option, mağaza), {int(kirpilan.sum()):,} paket, "
          f"{int((kirpilan * icerik).sum()):,} adet")
    assert t["option_id"].nunique() > 0

    tk = motor.takvim(k)
    assert len(tk.rpt) > 0 and len(tk.markdown) > 0
    print(f"takvim: {len(tk.rpt)} RPT günü, {len(tk.markdown)} markdown günü, kimlik {tk.kimlik[:12]}")


@pytest.mark.veri
def test_takvim_yeniden_oynatma_esdeger():
    """`lumoda` koşusunun takvimini oyun sezonunun Collection option'larında `rpt=` ve
    `markdown=` ile yeniden oynatan koşu (`TakvimRPT` / `TakvimMarkdown`; öteki option'lar
    Lumoda'nın tepkili kararı, sabit takvim kollarının üretim biçimi) aynı 18 tabloyu ve aynı
    gizli gerçeği üretir."""
    from allocation.politika import TakvimMarkdown, TakvimRPT

    _veri_yoksa_atla()
    tk = motor.takvim(_lumoda()).sabitle()
    oyun = kaynak.oyun_optionlari(motor.dunya(), sabitler.OYUN_SEZONU)
    assert len(oyun) == 210
    assert any(o in d for d in tk.rpt.values() for o in oyun)
    k = motor.kos(rpt=TakvimRPT(motor.lumoda("rpt"), tk, oyun),
                  markdown=TakvimMarkdown(motor.lumoda("markdown"), tk, oyun), ad="lumoda_takvimli",
                  parametreler={}, onbellek=motor.KOSU_DIZINI, tembel=True)
    print(f"\nkoşu: {'önbellekten' if k.onbellekten else 'yeni'}; motor {k.meta.get('motor_sn')} sn, "
          f"toplam {k.meta.get('sure_sn')} sn; tepe bellek {k.meta.get('tepe_bellek_gb')} GB")
    assert k.meta["turler"] == {"rpt": "allocation.politika.TakvimRPT",
                                "markdown": "allocation.politika.TakvimMarkdown"}
    _yayimlanan_ile_ayni(k.tablolar)
    gercek = _lumoda().tablo("gercek", sutunlar=list(motor.GERCEK_SUTUNLARI))
    yeni = k.tablo("gercek", sutunlar=list(motor.GERCEK_SUTUNLARI))
    for s in motor.GERCEK_SUTUNLARI:
        np.testing.assert_array_equal(yeni[s].to_numpy(), gercek[s].to_numpy(), err_msg=s)
