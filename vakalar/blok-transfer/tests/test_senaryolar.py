import json
from datetime import date
from pathlib import Path

import pytest

import senaryolar

KARAR = date(2025, 12, 29)


def test_sema_ve_anahtar_tamligi(con_kayipli, tmp_path):
    icerik = senaryolar.uret(con_kayipli, KARAR)
    assert [p["ad"] for p in icerik["parametreler"]] == ["verici_cover_esigi", "min_satis", "yontem"]
    assert icerik["surum"]
    assert len(icerik["sonuclar"]) == 4 * 4 * 2
    assert "6|1|greedy" in icerik["sonuclar"]   # yazilarin referans senaryosu
    ornek = icerik["sonuclar"]["6|1|mip"]
    assert set(ornek["ozet"]) == {
        "option_sayisi", "tasinan_adet", "rota_sayisi", "bosalan_magaza",
        "net_kazanc_tl", "sure_sn", "kayip_yakalama_yuzde",
    }
    assert ornek["satirlar"] == []

    hedef = tmp_path / "blok-transfer.json"
    senaryolar.yaz(icerik, hedef)
    assert hedef.stat().st_size < 500 * 1024
    json.loads(hedef.read_text(encoding="utf-8"))


def test_boyut_bekcisi(tmp_path):
    sisik = {"surum": "x", "parametreler": [], "sonuclar": {"k": {"ozet": {"a": "b" * 600_000}, "satirlar": []}}}
    with pytest.raises(ValueError, match="500"):
        senaryolar.yaz(sisik, tmp_path / "sisik.json")


def test_kayip_yakalama_yuzde_olarak_yazilir(con_kayipli, tmp_path):
    """Demonun okuduğu JSON'da metrik yüzde olarak ve tek ondalıkla durur.

    Kırılabilecek iki şey var: oranın (0–1) yüzde sanılarak saklanması ve
    yuvarlamanın atlanması. İkisi de sayıyı ekranda sessizce yanlış gösterir.
    """
    icerik = senaryolar.uret(con_kayipli, KARAR)
    hedef = tmp_path / "senaryo.json"
    senaryolar.yaz(icerik, hedef)
    okunan = json.loads(hedef.read_text(encoding="utf-8"))

    degerler = []
    for anahtar, sonuc in okunan["sonuclar"].items():
        oran = sonuc["ozet"]["kayip_yakalama_yuzde"]
        assert 0.0 <= oran <= 100.0, f"{anahtar}: {oran}"
        ondalik = str(oran).partition(".")[2]
        assert len(ondalik) <= 1, f"{anahtar}: {oran} bir ondalıktan uzun"
        degerler.append(oran)

    # Fikstürde plan MB-OPT1 (12 adet) ve MC-OPT2 (6 adet) kaybını adresliyor,
    # MD-OPT2 (2 adet) adreslenmiyor: 18/20. Oran olarak (0,9) saklansaydı ya da
    # yuvarlama kaçsaydı bu satır düşerdi.
    assert max(degerler) == pytest.approx(90.0)
