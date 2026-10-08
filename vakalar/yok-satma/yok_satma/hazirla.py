"""Vakanın bütün ara çıktılarını üretir: `python -m yok_satma.hazirla`.

Adımlar (her biri kendi dosyasına yazılır):

    gunluk      gunluk.parquet     `stok.gunluk_magaza` + `stok.gunluk_online`,
                                   2023-01-01 .. 2025-12-31, bütün uygun satırlar
                                   (stoklu dahil). Yıl yıl kurulur ve parquet'e
                                   satır grubu olarak eklenir: bütün pencere
                                   bellekte hiç birlikte durmaz.
    carpanlar   carpanlar.pkl      `carpanlar.ogren`, yalnız 2023–2024'ün stoklu
                                   günleriyle (+ gereken `ozellikler` sütunları)
    naif        kayip_naif.parquet  her kestirici için: `egit` bütün pencerenin
    basit       kayip_basit.parquet stoklu günleriyle, `tahmin` bütün pencerenin
    ml          kayip_ml.parquet    `bos` ve `tukenen` günleri; `kayip.kayip_yaz`
                                   yalnız bu satırlara (R5), sonra
                                   `agac.kaynak_ata`

Önbellek kuralları (bağımlılıklar: carpanlar, naif, ml <- gunluk;
basit <- gunluk + carpanlar):

    - Dosyası olan adım atlanır; `--yeniden` hepsini yeniden koşar, `--adim AD`
      (tekrarlanabilir) yalnız seçilenleri koşar ve onları zorla yeniden kurar.
    - Bu çağrıda koşan bir adımın bağımlıları da koşar (seçiliyse ya da seçim
      yoksa); `--adim` seçiminin dışında kalan bağımlıların dosyası SİLİNİR
      (geçersiz), bir sonraki çağrı onları yeniden kurar. Böylece eski
      girdiden kalan bir çıktı hiçbir zaman yeni bir girdinin yanında durmaz.
    - `kaynak.json` çıktının hangi v4 dosyasından kurulduğunu tutar (mutlak yol,
      boyut, mtime). `--db` farklıysa ya da `kaynak.json` yoksa dizindeki bütün
      çıktılar silinir.

Kayıp parquet'lerinin sütunları: günlük tablonun sütunları + `tahmini_talep`,
`satis`, `kayip`, `kayip_saf`, `kaynak`, `firsat`.

Bellek: her adım parquet'ten yalnız ihtiyaç duyduğu sütun ve satırları okur;
`ozellikler.ekle` yalnız kestiricinin okuduğu sütunları hesaplar; kestiriciler
arasında her şey bırakılır (`gc.collect`). Gizli gerçeğe (`hakem`) dokunulmaz.

`sure.json`: adım başına saniye ve tepe bellek. `tepe_gb` adımın süresince
0,1 sn'de bir örneklenen süreç RSS'inin (Windows'ta çalışma kümesi) en büyüğü;
`surec_tepe_gb` adım sonunda sürecin o ana kadarki tepe çalışma kümesi
(psutil `peak_wset`; Windows dışında örneklenen tepe). Atlanan adımın önceki
kaydı korunur.
"""

import argparse
import gc
import json
import threading
import time
from datetime import date
from pathlib import Path

import pandas as pd
import psutil

from perakende_analitik import kaynak
from perakende_analitik.hazirlik import carpanlar_yaz, gunluk_yaz, kayip_yaz

PENCERE = (date(2023, 1, 1), date(2025, 12, 31))
OGRENME_BITIS = pd.Timestamp("2024-12-31")       # çarpanlar 2023–2024'ten öğrenir

VARSAYILAN_CIKTI = Path(__file__).resolve().parents[1] / "cikti"

ADIMLAR = ("gunluk", "carpanlar", "naif", "basit", "ml")      # bağımlılık sırasıyla
BAGIMLILIKLAR = {"gunluk": (), "carpanlar": ("gunluk",), "naif": ("gunluk",),
                 "basit": ("gunluk", "carpanlar"), "ml": ("gunluk",)}
DOSYALAR = {"gunluk": "gunluk.parquet", "carpanlar": "carpanlar.pkl",
            "naif": "kayip_naif.parquet", "basit": "kayip_basit.parquet",
            "ml": "kayip_ml.parquet"}


# ------------------------------------------------------------------ ölçüm

class _Olcer:
    """Bir adımın süresi ve süreç belleğinin tepesi (örnekleyen iş parçacığı)."""

    ARALIK = 0.1   # sn

    def __init__(self):
        self.surec = psutil.Process()
        self.tepe = 0
        self._dur = threading.Event()

    def _rss(self) -> int:
        return self.surec.memory_info().rss

    def _ornekle(self) -> None:
        while not self._dur.wait(self.ARALIK):
            self.tepe = max(self.tepe, self._rss())

    def __enter__(self):
        self.tepe = self._rss()
        self.bas = time.perf_counter()
        self._is = threading.Thread(target=self._ornekle, daemon=True)
        self._is.start()
        return self

    def __exit__(self, *_):
        self._dur.set()
        self._is.join()
        self.tepe = max(self.tepe, self._rss())
        self.saniye = time.perf_counter() - self.bas
        bilgi = self.surec.memory_info()
        self.surec_tepe = max(getattr(bilgi, "peak_wset", 0), self.tepe)


_GB = 1024 ** 3


# ----------------------------------------------------------------- akış

def _ayristir(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m yok_satma.hazirla", description=__doc__.split("\n")[0])
    p.add_argument("--cikti", type=Path, default=VARSAYILAN_CIKTI,
                   help=f"çıktı dizini (varsayılan {VARSAYILAN_CIKTI})")
    p.add_argument("--db", type=Path, default=kaynak.VARSAYILAN_YOL,
                   help=f"v4 DuckDB dosyası (varsayılan {kaynak.VARSAYILAN_YOL})")
    p.add_argument("--yeniden", action="store_true",
                   help="var olan çıktıları da yeniden hesapla")
    p.add_argument("--adim", action="append", choices=ADIMLAR,
                   help="yalnız bu adımı (yeniden) koş; tekrarlanabilir. Seçim dışındaki "
                        "bağımlı adımların dosyaları silinir")
    return p.parse_args(argv)


def _parmak_izi(db: Path) -> dict:
    """v4 dosyasının kimliği: mutlak yol, boyut, mtime (ns)."""
    bilgi = db.stat()
    return {"yol": str(db.resolve()), "boyut": bilgi.st_size, "mtime_ns": bilgi.st_mtime_ns}


def _sil(yol: dict[str, Path], sure: dict, adimlar) -> None:
    for adim in adimlar:
        if yol[adim].exists():
            print(f"{adim}: gecersiz, siliniyor ({yol[adim]})", flush=True)
            yol[adim].unlink()
        sure["adimlar"].pop(adim, None)


def _bagimlilari(adimlar: set[str]) -> set[str]:
    """`adimlar`a (geçişli) bağımlı adımlar, kendileri hariç."""
    sonuc: set[str] = set()
    for adim in ADIMLAR:                       # sıra bağımlılık sırası: tek geçiş yeter
        if any(b in adimlar or b in sonuc for b in BAGIMLILIKLAR[adim]):
            sonuc.add(adim)
    return sonuc - adimlar


def main(argv: list[str] | None = None) -> dict:
    a = _ayristir(argv)
    cikti: Path = a.cikti
    cikti.mkdir(parents=True, exist_ok=True)
    yol = {ad: cikti / dosya for ad, dosya in DOSYALAR.items()}
    sure_yolu = cikti / "sure.json"
    sure = json.loads(sure_yolu.read_text(encoding="utf-8")) if sure_yolu.exists() else {}
    sure.setdefault("adimlar", {})
    sure["olcum"] = ("saniye: perf_counter; tepe_gb: adim boyunca 0,1 sn'de bir orneklenen "
                     "surec RSS'i (Windows calisma kumesi) en buyugu; surec_tepe_gb: adim "
                     "sonunda surecin o ana dek tepe calisma kumesi (psutil peak_wset)")

    def sure_yaz():
        sure_yolu.write_text(json.dumps(sure, ensure_ascii=False, indent=2), encoding="utf-8")

    con = kaynak.baglan(a.db)       # dosya yoksa burada açık hata
    try:
        # başka bir v4 dosyasından kurulmuş çıktılar geçersiz
        kaynak_yolu = cikti / "kaynak.json"
        iz = _parmak_izi(Path(a.db))
        eski = json.loads(kaynak_yolu.read_text(encoding="utf-8")) if kaynak_yolu.exists() else None
        if eski != iz:
            _sil(yol, sure, ADIMLAR)
            kaynak_yolu.write_text(json.dumps(iz, ensure_ascii=False, indent=2), encoding="utf-8")

        secili = list(a.adim) if a.adim else list(ADIMLAR)
        zorla = set(ADIMLAR) if a.yeniden else set(a.adim or ())
        kosan: set[str] = set()
        for adim in ADIMLAR:
            if adim not in secili:
                continue
            ustte_kosan = any(b in kosan for b in BAGIMLILIKLAR[adim])
            if yol[adim].exists() and adim not in zorla and not ustte_kosan:
                print(f"{adim}: var, atlandi ({yol[adim]})", flush=True)
                continue
            for b in BAGIMLILIKLAR[adim]:
                if not yol[b].exists():
                    raise FileNotFoundError(f"{yol[b]} yok: once `--adim {b}`")
            print(f"{adim}: basliyor", flush=True)
            with _Olcer() as o:
                if adim == "gunluk":
                    bilgi = {"satir": gunluk_yaz(con, yol["gunluk"], PENCERE)}
                elif adim == "carpanlar":
                    bilgi = {"satir": carpanlar_yaz(con, yol["gunluk"], yol["carpanlar"],
                                                    OGRENME_BITIS.date())}
                else:
                    bilgi = kayip_yaz(con, adim, yol["gunluk"], yol["carpanlar"], yol[adim])
            gc.collect()
            kosan.add(adim)
            # seçim dışındaki bağımlılar artık eski girdiye dayanıyor
            _sil(yol, sure, sorted(_bagimlilari({adim}) - set(secili), key=ADIMLAR.index))
            sure["adimlar"][adim] = {"saniye": round(o.saniye, 1),
                                     "tepe_gb": round(o.tepe / _GB, 2),
                                     "surec_tepe_gb": round(o.surec_tepe / _GB, 2), **bilgi}
            sure_yaz()
            print(f"{adim}: {o.saniye:.1f} sn, tepe {o.tepe / _GB:.2f} GB, {bilgi}", flush=True)
    finally:
        con.close()
    sure_yaz()
    return sure


if __name__ == "__main__":
    main()
