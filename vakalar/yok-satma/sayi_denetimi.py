"""Satış kaybı yazılarındaki her sayının `cikti/rapor.txt`'te geçtiğini denetler.

    .venv/Scripts/python sayi_denetimi.py      # eksik varsa çıkış kodu 1

Sayma kuralları ortak pakette (`perakende_analitik.sayi_denetimi`); burada yalnız
bu vakanın yazı dizini, rapor dosyası ve rapor komutu bulunur.
"""

import sys
from pathlib import Path

from perakende_analitik import sayi_denetimi as ortak

KOK = Path(__file__).resolve().parent
YAZI_DIZINI = KOK.parents[1] / "site" / "src" / "content" / "yazi" / "is-zekasi" / "satis-kaybi"
RAPOR = KOK / "cikti" / "rapor.txt"
RAPOR_KOMUTU = "PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py > cikti/rapor.txt"


def main(argv: list[str] | None = None) -> int:
    """Varsayılan dizin ve rapor komutuyla ortak denetimi çağırır; verilen argümanlar üstüne yazar."""
    argv = list(argv or [])
    if "--yazi" not in argv and not YAZI_DIZINI.is_dir():
        # yayın dizini henüz yoksa geçer (yazı yok); elle verilen dizin yoksa ortak denetim hata verir
        print(f"uyarı: yazı yok ({YAZI_DIZINI}); denetlenecek sayı yok", file=sys.stderr)
        return 0
    return ortak.main(["--yazi", str(YAZI_DIZINI), "--rapor", str(RAPOR),
                       "--komut", RAPOR_KOMUTU, *argv])


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
