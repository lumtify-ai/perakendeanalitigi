"""`sayi_denetimi.py` testleri: geçici yazı dizini ve geçici `rapor.txt`."""

from pathlib import Path

import sayi_denetimi

RAPOR = """=== LUMODA ===
  2025 kayıp 1.234.567 adet (%12,3), ortalama 0,55; −3,2 sapma
  hafta sonu 1,54 kat; 2025
"""


def _yaz(dizin: Path, ad: str, metin: str) -> Path:
    dizin.mkdir(parents=True, exist_ok=True)
    yol = dizin / ad
    yol.write_text(metin, encoding="utf-8")
    return yol


def _rapor(tmp_path: Path) -> Path:
    return _yaz(tmp_path, "rapor.txt", RAPOR)


def _argv(yazi: Path, rapor: Path) -> list[str]:
    return ["--yazi", str(yazi), "--rapor", str(rapor)]


def test_normalize():
    assert sayi_denetimi.normalize("1.234.567") == "1234567"
    assert sayi_denetimi.normalize("12,30") == "12.3"
    assert sayi_denetimi.normalize("1000") == sayi_denetimi.normalize("1.000") == "1000"


def test_denetim_eksik_sayiyi_yakalar(tmp_path, capsys):
    yazi = tmp_path / "yazi"
    _yaz(yazi, "bir.mdx", "---\nbaslik: Kayıp\nsira: 12\n---\n\n"
                          "Lumoda 2025'te 1.234.567 adet kaybetti (%12,3).\n"
                          "Bir gün 12.345 adet, hafta sonu 1,54 kat; 3 mağaza, 10 gün.\n"
                          "Sapma yüzde 3,2.\n")
    eksik = sayi_denetimi.bul(yazi, _rapor(tmp_path))
    assert [(b.dosya.name, b.satir, b.sayi, b.neden) for b in eksik] == [
        ("bir.mdx", 7, "12.345", "eksik")]
    assert sayi_denetimi.main(_argv(yazi, tmp_path / "rapor.txt")) == 1
    assert "bir.mdx:7" in capsys.readouterr().out


def test_denetim_kod_blogunu_atlar(tmp_path):
    yazi = tmp_path / "yazi"
    _yaz(yazi, "iki.mdx", "---\nsira: 99\n---\n\nKayıp 1.234.567 adet.\n\n"
                          "```python\nesik = 98.765\nn = 4321\n```\n\n"
                          "~~~\n55.555\n~~~\n\nSon: 0,55.\n")
    assert sayi_denetimi.bul(yazi, _rapor(tmp_path)) == []
    assert sayi_denetimi.main(_argv(yazi, tmp_path / "rapor.txt")) == 0


def test_yazi_yoksa_uyarir(tmp_path, capsys, monkeypatch):
    # varsayılan dizin yoksa uyarı + 0; elle verilen dizin yoksa uyarı + hata kodu
    monkeypatch.setattr(sayi_denetimi, "YAZI_DIZINI", tmp_path / "yok")
    assert sayi_denetimi.main(["--rapor", str(_rapor(tmp_path))]) == 0
    assert "yazı yok" in capsys.readouterr().err
    assert sayi_denetimi.main(_argv(tmp_path / "yok", _rapor(tmp_path))) != 0
    assert "yazı yok" in capsys.readouterr().err


def test_bicimsiz_sayi_kirpilmaz_hata(tmp_path, capsys):
    yazi = tmp_path / "yazi"
    _yaz(yazi, "uc.mdx", "Oran 1.5, sonra 12.34 ve 38.1; dizi 1.234.56.\n"
                         "Geçerli: 1.234.567 ve 0,55. Cümle sonu 12.345.\n")
    bulgular = sayi_denetimi.bul(yazi, _rapor(tmp_path))
    assert [(b.satir, b.sayi, b.neden) for b in bulgular] == [
        (1, "1.5", "biçim"), (1, "12.34", "biçim"), (1, "38.1", "biçim"),
        (1, "1.234.56", "biçim"), (2, "12.345", "eksik")]
    assert sayi_denetimi.main(_argv(yazi, tmp_path / "rapor.txt")) == 1
    assert "uc.mdx:1: 1.5 (Türkçe biçimde değil)" in capsys.readouterr().out


def test_rapor_yoksa_komutu_soyler(tmp_path, capsys):
    yazi = tmp_path / "yazi"
    _yaz(yazi, "bir.mdx", "Kayıp 1.234.567.\n")
    assert sayi_denetimi.main(_argv(yazi, tmp_path / "rapor.txt")) != 0
    assert "rapor.py" in capsys.readouterr().out
