"""`hikaye_kos`: komut satırı, `calistir` ve `kayit` (oyuncak dünya; gerçek veri `test_hikaye_sec.py`'de).

`girdiler` (gerçek v4) ve `hakem.gizli_segment` (v4 dünyası) monkeypatch'lenir; yalnız bağlantı kodu sınanır.
"""

import json
from types import SimpleNamespace

import pandas as pd
import pytest

from kumeleme import hikaye_kos as kos
from test_hikaye_sec import DUNYA, etiketler_kur, gizli_kur, kapsam_kur, ozellik_kur


def oyuncak_girdiler() -> dict:
    k = kapsam_kur()
    k["ad"] = "Mağaza " + k["magaza_id"]
    k["tip"] = "AVM"
    k["metrekare"] = 400
    kural, ml = etiketler_kur()
    kd = k.loc[k["kumelenir"], "magaza_id"]
    oneri = SimpleNamespace(aile="S1", yontem="kmeans", k=2, kimlik="abc", etiket=ml.loc[kd])
    return {"kapsam": k, "ozellik": ozellik_kur().loc[kd], "k1": None, "k2": kural["k2"],
            "k3": kural["k3"], "k4": pd.Series("metropol", index=kapsam_kur()["magaza_id"]),
            "ciro": pd.Series(1e6, index=kapsam_kur()["magaza_id"]), "oneri": oneri}


def test_argumanlar_varsayilan():
    a = kos.argumanlar([])
    assert a.gizlisiz is False and a.zorla is None and a.cikti == kos.YOL


def test_argumanlar_gizlisiz_ve_zorla():
    a = kos.argumanlar(["--gizlisiz", "--zorla", "I1, I2,I2,A1", "--cikti", "x.json"])
    assert a.gizlisiz is True and a.zorla == (("I1", "I2"), ("I2", "A1")) and str(a.cikti) == "x.json"


@pytest.mark.parametrize("zorla", ["I1,I2,I3", "I1,I2,I3,A1,A2", "I1,I2,,A1"])
def test_argumanlar_zorla_dort_magaza_ister(zorla, capsys):
    with pytest.raises(SystemExit) as e:
        kos.argumanlar(["--zorla", zorla])
    assert e.value.code == 2 and "dört mağaza" in capsys.readouterr().err


def test_calistir_ve_kayit(monkeypatch):
    g = oyuncak_girdiler()
    monkeypatch.setattr(kos.hakem, "gizli_segment", lambda *a, **k: gizli_kur())
    h, hakemsiz, gizli_s = kos.calistir(g)
    assert (hakemsiz.cift1, hakemsiz.cift2) == (h.cift1, h.cift2) and h.dogrulama is not None
    assert gizli_s.equals(gizli_kur())
    out = kos.kayit(g, h, hakemsiz, gizli_s)
    assert out["hakemsiz_ayni"] is True
    assert out["ml"] == {"aile": "S1", "yontem": "kmeans", "k": 2, "kimlik": "abc"}
    assert set(out["magazalar"]) == {*h.cift1, *h.cift2}
    m = out["magazalar"][h.cift1[0]]
    assert m["gizli_segment"] == gizli_kur()[h.cift1[0]] and m["ml_kume"] in (0, 1) and m["k2"] in "ABC"
    assert set(out["alternatif"]["magazalar"]) == {*h.alternatif.cift1, *h.alternatif.cift2}
    assert out["kalemler"][0]["olcu"].endswith("payı")
    json.dumps(out, ensure_ascii=False)


def test_calistir_gizlisiz(monkeypatch):
    g = oyuncak_girdiler()

    def yasak(*a, **k):
        raise AssertionError("hakem çağrılmamalı")
    monkeypatch.setattr(kos.hakem, "gizli_segment", yasak)
    h, hakemsiz, gizli_s = kos.calistir(g, gizli=False)
    assert hakemsiz is None and gizli_s is None and h.dogrulama is None
    out = kos.kayit(g, h, hakemsiz, gizli_s)
    assert out["hakemsiz_ayni"] is None
    assert all("gizli_segment" not in m for m in out["magazalar"].values())


def test_main_yazar(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(kos, "girdiler", oyuncak_girdiler)
    monkeypatch.setattr(kos.hakem, "gizli_segment", lambda *a, **k: gizli_kur())
    yol = tmp_path / "alt" / "hikaye.json"
    assert kos.main(["--cikti", str(yol), "--zorla", "I1,I2,I2,A1"]) == 0
    out = json.loads(yol.read_text(encoding="utf-8"))
    assert out["cift1"] == ["I2", "I1"] and out["cift2"] == ["I2", "A1"]      # ortak mağaza (I2) ilk
    assert out["gevseyen"][0] == "zorlandı" and out["alternatif"] is None
    assert "hikaye:" in capsys.readouterr().out
    yol2 = tmp_path / "gizlisiz.json"
    assert kos.main(["--cikti", str(yol2), "--gizlisiz"]) == 0
    out2 = json.loads(yol2.read_text(encoding="utf-8"))
    assert out2["dogrulama"] is None and out2["hakemsiz_ayni"] is None
