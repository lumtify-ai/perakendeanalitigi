"""Yazılardaki her sayının `cikti/rapor.txt`'te geçtiğini denetler.

    .venv/Scripts/python sayi_denetimi.py      # eksik varsa çıkış kodu 1

`site/src/content/yazi/is-zekasi/satis-kaybi/*.mdx` taranır. Sayılmayanlar:
frontmatter'ın `sira` satırı, çitli kod blokları (``` ya da ~~~ ile açılan),
10'dan büyük olmayan tam sayılar ve bir kelimenin içindeki rakamlar (`MDL0388`,
`SS24`). Sayı Türkçe yazılır: binlik `.` (yalnız üçlü gruplarla, `1.234.567`),
ondalık `,` (`12,3`). İşaret ve `%` sayının parçası değildir (`−%3,2` → 3,2).

Normalize: binlik noktalar düşer, ondalık virgül noktaya döner, sondaki
sıfırlar atılır (`12,30` → 12.3; `1.000` ve `1000` → 1000). Aynı kural
`rapor.txt`'e uygulanır; yazıdaki sayının normal biçimi raporun sayıları
arasında yoksa eksik sayılır (alt dize değil, tam sayı eşleşmesi: rapordaki
`123` yazıdaki `12`yi karşılamaz).
"""

import argparse
import re
import sys
from decimal import Decimal
from pathlib import Path

KOK = Path(__file__).resolve().parent
YAZI_DIZINI = KOK.parents[1] / "site" / "src" / "content" / "yazi" / "is-zekasi" / "satis-kaybi"
RAPOR = KOK / "cikti" / "rapor.txt"
RAPOR_KOMUTU = "PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py > cikti/rapor.txt"
ESIK = 10                          # bundan büyük olmayan tam sayılar denetlenmez

SAYI = re.compile(r"(?<![\w.,])(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)(?!\w)")
_CIT = re.compile(r"^\s*(```|~~~)")


def normalize(metin: str) -> str:
    """Türkçe sayı metni -> karşılaştırma biçimi (`1.234,50` -> `1234.5`)."""
    d = Decimal(metin.replace(".", "").replace(",", ".")).normalize()
    return format(d, "f")


def _denetlenir(metin: str) -> bool:
    d = Decimal(normalize(metin))
    return not (d == d.to_integral_value() and d <= ESIK)


def satirlar(metin: str):
    """(satır no, satır) — frontmatter `sira` satırı ve çitli kod blokları hariç."""
    cit = None
    frontmatter = False
    for no, satir in enumerate(metin.splitlines(), start=1):
        if no == 1 and satir.strip() == "---":
            frontmatter = True
            continue
        if frontmatter:
            if satir.strip() == "---":
                frontmatter = False
            elif not re.match(r"^\s*sira\s*:", satir):
                yield no, satir
            continue
        m = _CIT.match(satir)
        if m:
            if cit is None:
                cit = m.group(1)
            elif m.group(1) == cit:
                cit = None
            continue
        if cit is None:
            yield no, satir


def rapor_sayilari(metin: str) -> set[str]:
    return {normalize(m.group(1)) for m in SAYI.finditer(metin)}


def bul(yazi_dizini: Path, rapor: Path) -> list[tuple[Path, int, str]]:
    """Rapor'da geçmeyen sayılar: (dosya, satır no, yazıdaki biçim), dosya ve satır sırasıyla."""
    bilinen = rapor_sayilari(Path(rapor).read_text(encoding="utf-8"))
    eksik = []
    for dosya in sorted(Path(yazi_dizini).glob("*.mdx")):
        for no, satir in satirlar(dosya.read_text(encoding="utf-8")):
            for m in SAYI.finditer(satir):
                sayi = m.group(1)
                if _denetlenir(sayi) and normalize(sayi) not in bilinen:
                    eksik.append((dosya, no, sayi))
    return eksik


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python sayi_denetimi.py", description=__doc__.split("\n")[0])
    p.add_argument("--yazi", type=Path, default=YAZI_DIZINI, help=f"yazı dizini ({YAZI_DIZINI})")
    p.add_argument("--rapor", type=Path, default=RAPOR, help=f"rapor dosyası ({RAPOR})")
    a = p.parse_args(argv)
    if not a.yazi.is_dir() or not any(a.yazi.glob("*.mdx")):
        print(f"yazı yok ({a.yazi})")
        return 0
    if not a.rapor.exists():
        print(f"{a.rapor} yok. Önce raporu üretin: {RAPOR_KOMUTU}")
        return 2
    eksik = bul(a.yazi, a.rapor)
    for dosya, no, sayi in eksik:
        print(f"{dosya.name}:{no}: {sayi}")
    if eksik:
        print(f"{len(eksik)} sayı rapor.txt'te yok")
        return 1
    print("bütün sayılar rapor.txt'te var")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
