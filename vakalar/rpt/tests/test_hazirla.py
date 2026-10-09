import json

import pytest

from rpt import hazirla


def test_gunluk_yolu_yoksa_komut_soyler(tmp_path):
    with pytest.raises(RuntimeError, match="rpt.hazirla"):
        hazirla.gunluk_yolu(tmp_path)


def test_gunluk_yolu_bayat_pencere(tmp_path):
    (tmp_path / hazirla.GUNLUK).write_bytes(b"")
    (tmp_path / hazirla.KAYNAK).write_text(json.dumps({"pencere": ["2024-01-01", "2024-12-31"]}),
                                           encoding="utf-8")
    with pytest.raises(RuntimeError, match="pencere"):
        hazirla.gunluk_yolu(tmp_path)
    (tmp_path / hazirla.KAYNAK).write_text(json.dumps({"pencere": hazirla._iz_pencere()}),
                                           encoding="utf-8")
    assert hazirla.gunluk_yolu(tmp_path) == tmp_path / hazirla.GUNLUK
