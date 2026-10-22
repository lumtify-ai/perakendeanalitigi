"""Hikâye koşumu (ölçüm yanı): gerçek veride sahneyi seçer, hakemle doğrular, `cikti/hikaye.json` yazar.

    PYTHONIOENCODING=utf-8 .venv/Scripts/python -m beden_paket.hikaye_kos [--gizlisiz]

Neden ayrı modül (Kümeleme `hikaye_kos` kalıbı): `hikaye_sec` karar modülüdür ve kilit onun `hakem`'e
ulaşmasına izin vermez (`tests/test_sizinti.py`). Gizli kaymayı `hakem`'den okuyup
`hikaye_sec.sec(..., kayma=)`'ya `Series` olarak veren bu modüldür; ölçüm modülleri arasındadır
(`IZINLI_MODULLER`). Seçim mantığı `hikaye_sec`'tedir; burada yalnız veriyi kurmak, hakemi bağlamak
ve yazmak vardır.

Girdiler yayımlanan v4'ten, karar gününden (`KARAR_GUNU`) önce: eğrinin tabloları
(`egri.egri_tablolari`: haftalık satış ve stok fotoğrafları), `paket` ve `sevkiyat`'ın ilk dağıtım
satırları; eğri `egri.magaza_egrisi` (oyunun yol 0'ındaki eğriyle aynı kural ve veri). Hakem: etkin
(kırpılmış) gizli kayma (`hakem.kayma`).

Kayıt (`hikaye.json`): sahne (`Hikaye.sozluk`), iki mağazanın künyesi (ad, şehir, bölge, tip, m²),
`kod` (paket kodunun özeti; rapor eski kaydı reddeder) ve hakemsiz seçimin aynı sahneyi verip
vermediği (`hakemsiz_ayni`).
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

from beden_paket import egri as egri_modulu
from beden_paket import hakem, hikaye_sec, kaynak, sabitler

YOL = sabitler.CIKTI / "hikaye.json"
KAYIT_SURUMU = 1
KOD_MODULLERI = ("egri", "hikaye_sec", "hikaye_kos", "kaynak", "sabitler")


def kod_ozeti() -> str:
    """Sahneyi belirleyen kodun özeti (`KOD_MODULLERI`; satır sonları LF)."""
    kok = Path(__file__).resolve().parent
    h = hashlib.sha256()
    for m in KOD_MODULLERI:
        y = kok / f"{m}.py"
        h.update(y.name.encode() + b"\0" + y.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def girdiler(karar_gunu=sabitler.KARAR_GUNU) -> dict:
    """Yayımlanan v4'ten `hikaye_sec.sec`'in girdileri (gizli gerçek yok): tablolar ve eğri."""
    karar = pd.Timestamp(karar_gunu)
    con = kaynak.baglan()
    try:
        t = egri_modulu.egri_tablolari(con, karar)
        t |= kaynak.yayimlanan_tablolar(con, ("paket",))
        t["sevkiyat"] = con.execute(
            "select tarih, varis_tarihi, kaynak::varchar as kaynak, hedef::varchar as hedef, "
            "urun_id::varchar as urun_id, adet, tip::varchar as tip, paket_id::varchar as paket_id "
            "from sevkiyat where tip = 'ilk_dagitim' and tarih < ?", [karar]).df()
    finally:
        con.close()
    kapsam = kaynak.kapsam(t, karar)
    e = egri_modulu.magaza_egrisi(t, kapsam, karar)
    return {"tablolar": t, "kapsam": kapsam, "egri": e, "karar_gunu": karar}


def calistir(g: dict, *, gizli: bool = True):
    """Üç değer döndürür: `(h, hakemsiz, kayma)`.

    h         seçilen `Hikaye` (`gizli=True` ise hakemin kaymasıyla doğrulanmış)
    hakemsiz  aynı seçimin hakemsiz hâli (`gizli=False` ise `None`)
    kayma     hakemden okunan mağaza → etkin gizli kayma (`gizli=False` ise `None`)"""
    kayma = hakem.kayma() if gizli else None
    h = hikaye_sec.sec(g["tablolar"], g["egri"], g["karar_gunu"], kayma=kayma)
    hakemsiz = hikaye_sec.sec(g["tablolar"], g["egri"], g["karar_gunu"]) if gizli else None
    return h, hakemsiz, kayma


def _kunye(g: dict, h: hikaye_sec.Hikaye) -> dict:
    k = g["kapsam"].set_index("magaza_id")
    out = {}
    for m in (h.buyuk["magaza"], h.kucuk["magaza"]):
        r = k.loc[m]
        out[m] = {"ad": str(r["ad"]), "sehir": str(r["sehir"]), "bolge": str(r["bolge"]), "tip": str(r["tip"]),
                  "metrekare": int(r["metrekare"]), "istanbul": bool(r["istanbul"])}
    return out


def _ayni(a: hikaye_sec.Hikaye, b: hikaye_sec.Hikaye) -> bool:
    return all(a_[x] == b_[x] for a_, b_ in ((a.buyuk, b.buyuk), (a.kucuk, b.kucuk)) for x in ("magaza", "option"))


def kayit(g: dict, h, hakemsiz) -> dict:
    out = {"surum": KAYIT_SURUMU, "kod": kod_ozeti(), "karar_gunu": g["karar_gunu"].date().isoformat(),
           **h.sozluk()}
    out["magazalar"] = _kunye(g, h)
    if h.alternatif is not None:
        out["alternatif"]["magazalar"] = _kunye(g, h.alternatif)
    out["hakemsiz_ayni"] = None if hakemsiz is None else _ayni(h, hakemsiz)
    return out


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="beden_paket.hikaye_kos", description=__doc__.splitlines()[0])
    p.add_argument("--gizlisiz", action="store_true", help="hakemi bağlama (doğrulama yok)")
    p.add_argument("--cikti", type=Path, default=YOL)
    a = p.parse_args(argv)
    g = girdiler()
    h, hakemsiz, _ = calistir(g, gizli=not a.gizlisiz)
    out = kayit(g, h, hakemsiz)
    a.cikti.parent.mkdir(parents=True, exist_ok=True)
    a.cikti.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"hikaye: büyük {h.buyuk['magaza']} / küçük {h.kucuk['magaza']} ({h.buyuk['option']}, "
          f"{h.kucuk['option']}), kademe {h.kademe}, gevşeyen {h.gevseyen or 'yok'}, roller {h.roller}, "
          f"elenen {h.elenen} -> {a.cikti}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
