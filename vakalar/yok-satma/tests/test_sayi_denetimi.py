"""`sayi_denetimi.py` sarmalayıcı testi: sayma kuralları ortak pakette (`vakalar/ortak/tests`)."""

import sayi_denetimi


def test_sarmalayici_varsayilan_dizinleri_gecirir(monkeypatch):
    cagrilar = []
    monkeypatch.setattr(sayi_denetimi.ortak, "main",
                        lambda argv=None: cagrilar.append(argv) or 0)
    assert sayi_denetimi.main([]) == 0
    assert cagrilar == [["--yazi", str(sayi_denetimi.YAZI_DIZINI),
                         "--rapor", str(sayi_denetimi.RAPOR),
                         "--komut", sayi_denetimi.RAPOR_KOMUTU]]
