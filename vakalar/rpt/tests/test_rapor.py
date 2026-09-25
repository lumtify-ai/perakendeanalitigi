import contextlib
import io

import pytest

import rapor


def test_turkce_sayi_bicimi():
    assert rapor.s(12345) == "12.345"
    assert rapor.s(0.555, 2) == "0,56"
    assert rapor.s(-3.2, 1) == "−3,2"
    assert rapor.y(0.1234) == "%12,3"
    assert rapor.s(float("nan")) == "—"


@pytest.mark.veri
def test_rapor_duman(veri):
    v = rapor.hazirla(veri["t"], veri["dunya"])
    tampon = io.StringIO()
    with contextlib.redirect_stdout(tampon):
        rapor.hikaye_bolumu(v)
        rapor.karar_bolumu(v)
        rapor.sansur_bolumu(v)
    cikti = tampon.getvalue()
    for bolum in ("HİKÂYE (1. yazı)", "KARAR (2. yazı)", "SANSÜR (3. yazı)",
                  "Veli'nin hatırası", "Bir sezonda kaç soru", "FRR karşılığı"):
        assert bolum in cikti
    adaylar, yerli, uzak = rapor._secim(v)
    assert yerli["mense"] == "Yerli" and uzak["mense"] == "Uzak Doğu"
    assert yerli["oran"] >= 1.5 and uzak["oran"] >= 1.5
    # Katman d, SS25'te h=2'de buyer planından belirgin iyi (FRR'nin tezinin karşılığı)
    tab = v.hata["SS25"].set_index(["kesit", "katman", "h"])
    assert tab.loc[("tümü", "d", 2), "wape"] < tab.loc[("tümü", "plan", 2), "wape"] / 2
