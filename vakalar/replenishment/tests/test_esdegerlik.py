"""Kilit: vakanın kapısından geçen Lumoda koşusu yayımlanan v4'ün ta kendisidir.

`veri` işaretli: bir TAM koşu (~4–7 dk, tepe ~10 GB). Koşu `lumoda_kisitsiz`
adıyla `cikti/kosular/`'a yazılır (sonraki çağrılar oradan okur). Bu koşu
Lumoda'nın replenishment isteklerini de kaydeder (Ruling R4): hikâye seçimi
orantılı kesimi buradan okur; ilk dağıtım ve outlet akışı kaydedicileri
(`kaydedici=True`, varsayılan) gölge defterin brüt akışlarıdır.
"""

import numpy as np
import pandas as pd
import pytest

from replenishment import kaynak, motor


def _parquet_turu(df):
    """Parquet gidiş-dönüşü bellekte (yayımlama `to_parquet(index=False)`;
    koşu tabloları da Parquet'ten döner: kategori adı gibi üst veri düşer)."""
    import io

    tampon = io.BytesIO()
    df.to_parquet(tampon, index=False)
    tampon.seek(0)
    return pd.read_parquet(tampon)


@pytest.mark.veri
def test_lumoda_kisitsiz_yayimlanan_v4_ile_ayni():
    """Lumoda + kaydediciler (ilk dağıtım, outlet akışı ve replenishment) +
    varsayılan tohumlar + alım oranı 1,0 `motor.kos`'tan geçince yayımlanan
    v4'tür: koşunun temiz tabloları `yayimlanan_bicim`le 18 yayımlanan
    tablonun her biriyle değer, tür ve sıra olarak aynı (Parquet dışa
    aktarımına karşı; DuckDB satır sayıları, Σ adet). Kayıtlar dolu ve
    tutarlı: gönderilen replenishment hücre-gün başına istenenden fazla
    değil. Gizli gerçeğin `karsilanmayan > 0` alt kümesi hakemin önbelleğiyle
    aynı (önbellek varsa)."""
    from perakende_analitik import hakem

    parquet = kaynak.VERITABANI.parent / "parquet"
    if not kaynak.VERITABANI.exists() or not parquet.exists():
        pytest.skip("yayımlanan v4 yok")
    k = motor.kos(motor.Kaydedici(motor.lumoda("replenishment")), ad="lumoda_kisitsiz",
                  parametreler={}, onbellek=motor.KOSU_DIZINI)
    print(f"\nkoşu: {'önbellekten' if k.onbellekten else 'yeni'}; "
          f"motor {k.meta.get('motor_sn')} sn, toplam {k.meta.get('sure_sn')} sn; "
          f"tepe bellek {k.meta.get('tepe_bellek_gb')} GB; "
          f"kayıt satırları { {a: len(d) for a, d in k.kayitlar.items()} }")
    assert k.meta["ilk_alim_orani"] == 1.0 and k.meta["kaydedici"] is True
    assert k.meta["talep_tohumu"] is None and k.meta["operasyon_tohumu"] == motor.TOHUM

    tablolar = motor.yayimlanan_bicim(k.tablolar, "tam")
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
    del tablolar

    # Kayıtlar: üç kaydedici dolu; replenishment gönderimi isteği aşmaz
    assert sorted(k.kayitlar) == ["ilk_dagitim", "outlet_akisi", "replenishment"]
    for ad, d in k.kayitlar.items():
        assert len(d) > 0, ad
    istek = k.kayitlar["replenishment"]
    assert list(istek.columns) == ["gun", "indis", "deger"] and (istek["deger"] > 0).all()
    w = motor.dunya()
    anahtar = kaynak.hucre_anahtari(w)
    s = k.tablolar["sevkiyat"]
    s = s[s["tip"].astype(str) == "replenishment"]
    gun = ((pd.to_datetime(s["tarih"]) - pd.Timestamp(motor.v4_sabitler.ISINMA_BASLANGIC)).dt.days
           .to_numpy(dtype=np.int64))
    hucre = anahtar.get_indexer(s["hedef"].astype(str) + "|" + s["urun_id"].astype(str))
    assert (hucre >= 0).all()
    gonderilen = pd.Series(s["adet"].to_numpy(dtype=np.int64)).groupby([gun, hucre]).sum()
    istenen = istek.set_index(["gun", "indis"])["deger"]
    ortak = istenen.reindex(gonderilen.index)
    assert ortak.notna().all(), "istenmemiş hücre-güne replenishment gitmiş"
    assert (gonderilen.to_numpy() <= ortak.to_numpy()).all()
    print(f"replenishment: istenen {int(istenen.sum()):,}, gönderilen (pencerede) {int(gonderilen.sum()):,}")

    g = k.gercek
    assert ((g["kendi_satis"] + g["karsilanmayan"]) == g["talep"]).all()
    assert ((g["ikameye_giden"] + g["kalici_kayip"]) == g["karsilanmayan"]).all()
    try:
        h = hakem.oku()
    except FileNotFoundError:
        return
    hk = h["karsilanmayan"]
    alt = g[g["karsilanmayan"] > 0].reset_index(drop=True)
    assert len(alt) == len(hk)
    np.testing.assert_array_equal(alt["tarih"].to_numpy(), hk["tarih"].to_numpy())
    for s_ in ("magaza_id", "urun_id"):
        np.testing.assert_array_equal(alt[s_].astype(str).to_numpy(), hk[s_].astype(str).to_numpy())
    for s_ in motor.GERCEK_SUTUNLARI:
        np.testing.assert_array_equal(alt[s_].to_numpy(), hk[s_].to_numpy(), err_msg=s_)
