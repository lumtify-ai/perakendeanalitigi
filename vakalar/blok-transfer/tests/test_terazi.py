import pandas as pd
import pytest

from blok_transfer.cekirdek.parametreler import Parametreler
from blok_transfer.cekirdek import terazi


def test_spec_4_formulleri():
    # spec §4: kazanc=min(stok, v_alici*H)*fiyat; kayip=min(stok, v_verici*H)*fiyat
    df = pd.DataFrame([
        # MA→MB OPT1 örneği: adet 12, v_a 4, v_v 0.5, fiyat 100
        dict(verici="MA", alici="MB", option_id="OPT1", adet=12,
             hiz_verici=0.5, hiz_alici=4.0, fiyat=100.0),
        # talep stoktan az: adet 20, v_a 1 → kazanc 8*50
        dict(verici="X", alici="Y", option_id="OPT9", adet=20,
             hiz_verici=0.0, hiz_alici=1.0, fiyat=50.0),
    ])
    p = Parametreler()  # H=8, adet_maliyeti 25
    sonuc = terazi.agirliklandir(df, p)
    assert sonuc.iloc[0].kazanc == pytest.approx(1200.0)   # min(12,32)*100
    assert sonuc.iloc[0].kayip == pytest.approx(400.0)     # min(12,4)*100
    assert sonuc.iloc[0].tasima == pytest.approx(300.0)    # 25*12
    assert sonuc.iloc[0].w == pytest.approx(500.0)
    assert sonuc.iloc[1].kazanc == pytest.approx(400.0)    # min(20,8)*50
    assert sonuc.iloc[1].kayip == pytest.approx(0.0)
    assert sonuc.iloc[1].w == pytest.approx(400.0 - 0.0 - 500.0)  # tasima 25*20


def test_terazi_kar_degeri():
    # deger="kar": birim değer fiyat − alis; taşıma maliyeti aynı
    df = pd.DataFrame([
        dict(verici="MA", alici="MB", option_id="OPT1", adet=12,
             hiz_verici=0.5, hiz_alici=4.0, fiyat=100.0, alis=40.0),
        dict(verici="X", alici="Y", option_id="OPT9", adet=20,
             hiz_verici=0.0, hiz_alici=1.0, fiyat=50.0, alis=20.0),
    ])
    p = Parametreler()
    sonuc = terazi.agirliklandir(df, p, deger="kar")
    assert sonuc.iloc[0].kazanc == pytest.approx(720.0)    # min(12,32)*(100-40)
    assert sonuc.iloc[0].kayip == pytest.approx(240.0)     # min(12,4)*60
    assert sonuc.iloc[0].tasima == pytest.approx(300.0)    # 25*12, ciroyla aynı
    assert sonuc.iloc[0].w == pytest.approx(180.0)         # 720-240-300
    assert sonuc.iloc[1].kazanc == pytest.approx(240.0)    # min(20,8)*30
    assert sonuc.iloc[1].kayip == pytest.approx(0.0)
    assert sonuc.iloc[1].w == pytest.approx(240.0 - 0.0 - 500.0)
    # varsayılan "ciro": alis kolonu olsa da fiyatı kullanır
    assert terazi.agirliklandir(df, p).iloc[0].w == pytest.approx(500.0)


def test_terazi_bilinmeyen_deger_hata():
    df = pd.DataFrame([dict(adet=1, hiz_verici=0.0, hiz_alici=1.0, fiyat=1.0, alis=0.5)])
    with pytest.raises(ValueError):
        terazi.agirliklandir(df, Parametreler(), deger="marj")
