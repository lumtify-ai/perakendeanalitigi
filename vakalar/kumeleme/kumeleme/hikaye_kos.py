"""Hikâye koşumu (ölçüm yanı): gerçek veride sahneyi seçer, hakemle doğrular, `cikti/hikaye.json` yazar.

`python -m kumeleme.hikaye_kos [--gizlisiz] [--zorla M1,M2,M3,M4]`

Neden ayrı modül: `hikaye_sec` karar modülüdür ve kilit onun `hakem`'e ulaşmasına izin vermez
(`tests/test_sizinti.py`). Gizli segmenti `hakem`'den okuyup `hikaye_sec.sec(..., gizli=)`'ye
`Series` olarak veren bu modüldür; bu yüzden ölçüm modülleri arasındadır (`IZINLI_MODULLER`).
Seçim mantığı `hikaye_sec`'tedir; burada yalnız veriyi kurmak, hakemi bağlamak ve yazmak vardır.

Kayıt (`hikaye.json`): sahne (`Hikaye.sozluk`), dört mağazanın künyesi (ad, şehir, bölge, ciro
sınıfı, ML kümesi, net ciro, gizli segment), önerilen ML kümesinin kimliği ve hakemsiz seçimin
aynı sahneyi verip vermediği (`hakemsiz_ayni`: hakem seçimi değiştirdiyse `False`).
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from kumeleme import hakem, hikaye_sec, kaynak, kural, ogren, ozellikler, sabitler

YOL = sabitler.CIKTI / "hikaye.json"


def girdiler(karar_gunu=sabitler.KARAR_GUNU) -> dict:
    """Yayımlanan v4'ten `hikaye_sec.sec`'in girdileri (gizli gerçek yok): kapsam, S1 ham özellikleri,
    K1-K4 etiketleri, önerilen ML kümesi."""
    con = kaynak.baglan()
    try:
        t = kaynak.yayimlanan_tablolar(con, ("magaza", "magaza_olay", "urun"))
        gunluk = con.execute(
            "select distinct tarih::date::timestamp as tarih, magaza_id::varchar as magaza_id, "
            "1 as adet from satis where adet > 0 and tarih < ?", [karar_gunu]).df()
        k = kaynak.kapsam(t["magaza"], t["magaza_olay"], gunluk, karar_gunu)
        ham = con.execute("select * from satis where tarih >= ? and tarih < ?",
                          [karar_gunu - pd.DateOffset(years=1), karar_gunu]).df()
        ham["magaza_id"] = ham["magaza_id"].astype(str)
        ids = k.loc[k["kumelenir"], "magaza_id"]
        X = {a: ozellikler.ozellik_tablosu(con, ids, t["urun"], karar_gunu, a) for a in ogren.ONERI_AILELERI}
    finally:
        con.close()
    k2 = kural.ciro_sinifi(ham, k, karar_gunu)
    o = ogren.oneri(None, k, None, karar_gunu, ozellik=X)
    return {"kapsam": k, "ozellik": X[hikaye_sec.AILE], "k1": kural.bolge(k), "k2": k2,
            "k3": kural.bolge_ciro(k, k2), "k4": kural.konum(k), "ciro": kural.net_ciro(ham, k, karar_gunu),
            "oneri": o}


def calistir(g: dict, *, gizli: bool = True, zorla=None):
    """Üç değer döndürür: `(h, hakemsiz, gizli_s)`.

    h         seçilen `Hikaye` (`gizli=True` ise hakemin segmentleriyle doğrulanmış)
    hakemsiz  aynı seçimin hakemsiz hâli (`gizli=False` ise `None`); `h` ile aynı sahne mi diye
              karşılaştırmak içindir (`kayit` → `hakemsiz_ayni`)
    gizli_s   hakemden okunan mağaza → gizli segment `Series` (`gizli=False` ise `None`)"""
    etiketler = {"k2": g["k2"], "k3": g["k3"]}
    ml = g["oneri"].etiket
    gizli_s = hakem.gizli_segment() if gizli else None
    h = hikaye_sec.sec(g["ozellik"], g["kapsam"], etiketler, ml, gizli=gizli_s, zorla=zorla)
    hakemsiz = hikaye_sec.sec(g["ozellik"], g["kapsam"], etiketler, ml, zorla=zorla) if gizli else None
    return h, hakemsiz, gizli_s


def _kunye(g: dict, h: hikaye_sec.Hikaye, gizli_s) -> dict:
    k = g["kapsam"].set_index("magaza_id")
    sonuc = {}
    for m in (*h.cift1, *h.cift2):
        r = k.loc[m]
        sonuc[m] = {"ad": r["ad"], "sehir": r["sehir"], "bolge": r["bolge"], "tip": r["tip"],
                    "metrekare": int(r["metrekare"]), "istanbul": bool(r["istanbul"]),
                    "k2": str(g["k2"][m]), "k3": str(g["k3"][m]), "k4": str(g["k4"][m]),
                    "ml_kume": int(g["oneri"].etiket[m]), "net_ciro": float(g["ciro"][m])}
        if gizli_s is not None:
            sonuc[m]["gizli_segment"] = str(gizli_s[m])
    return sonuc


def kayit(g: dict, h, hakemsiz, gizli_s) -> dict:
    o = g["oneri"]
    out = h.sozluk()
    out["magazalar"] = _kunye(g, h, gizli_s)
    if h.alternatif is not None:
        out["alternatif"]["magazalar"] = _kunye(g, h.alternatif, gizli_s)
    out["ml"] = {"aile": o.aile, "yontem": o.yontem, "k": o.k, "kimlik": o.kimlik}
    out["hakemsiz_ayni"] = None if hakemsiz is None else (hakemsiz.cift1, hakemsiz.cift2) == (h.cift1, h.cift2)
    return out


def argumanlar(argv=None) -> argparse.Namespace:
    """Komut satırı: `--gizlisiz`, `--zorla M1,M2,M3,M4` (`zorla` çözülmüş: ((M1, M2), (M3, M4)) ya da None),
    `--cikti`."""
    p = argparse.ArgumentParser(prog="kumeleme.hikaye_kos", description=__doc__.splitlines()[0])
    p.add_argument("--gizlisiz", action="store_true", help="hakemi bağlama (doğrulama yok)")
    p.add_argument("--zorla", help="M1,M2,M3,M4: 1. çift M1-M2, 2. çift M3-M4")
    p.add_argument("--cikti", type=Path, default=YOL)
    a = p.parse_args(argv)
    if a.zorla:
        m = [x.strip() for x in a.zorla.split(",")]
        if len(m) != 4 or not all(m):
            p.error("--zorla dört mağaza ister: M1,M2,M3,M4")
        a.zorla = ((m[0], m[1]), (m[2], m[3]))
    else:
        a.zorla = None
    return a


def main(argv=None) -> int:
    a = argumanlar(argv)
    g = girdiler()
    h, hakemsiz, gizli_s = calistir(g, gizli=not a.gizlisiz, zorla=a.zorla)
    out = kayit(g, h, hakemsiz, gizli_s)
    a.cikti.parent.mkdir(parents=True, exist_ok=True)
    a.cikti.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"hikaye: 1. çift {h.cift1}, 2. çift {h.cift2}, gevşeyen {h.gevseyen or 'yok'}, "
          f"elenen {h.elenen} -> {a.cikti}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
