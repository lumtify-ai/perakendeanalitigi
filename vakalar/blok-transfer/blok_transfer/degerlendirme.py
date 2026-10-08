import dataclasses
import hashlib
import json
import os
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from .cekirdek import adaylar as adaylar_mod
from .cekirdek import terazi, veri
from .cekirdek.parametreler import Parametreler
from .cozuculer import greedy, mip
from .cozuculer.tip import HAREKET_KOLONLARI, Plan, bos_hareketler

COZUCULER = {"greedy": greedy.cozumle, "mip": mip.cozumle}
PAKET_KOKU = Path(__file__).resolve().parent      # blok_transfer/


def ozetle(plan: Plan, p: Parametreler) -> dict:
    h = plan.hareketler
    rota_sayisi = len(h.groupby(["verici", "alici"])) if len(h) else 0
    return {
        "option_sayisi": int(len(h)),
        "tasinan_adet": int(h.adet.sum()) if len(h) else 0,
        "rota_sayisi": int(rota_sayisi),
        "bosalan_magaza": int(h.verici.nunique()) if len(h) else 0,
        "net_kazanc_tl": round(float(h.w.sum()) - rota_sayisi * p.rota_sabiti_tl, 2),
        "sure_sn": round(plan.sure_sn, 3),
        "durum": plan.durum,
    }


def _kaynak_izi(con: duckdb.DuckDBPyConnection) -> list:
    """Bağlantının veri dosyası: yol, boyut, mtime. Bellek içi bağlantıda (testler) "bellek"."""
    yol = con.execute(
        "select path from duckdb_databases() where database_name = current_database()"
    ).fetchone()[0]
    if not yol:
        return ["bellek"]
    durum = os.stat(yol)
    return [str(Path(yol).resolve()), durum.st_size, durum.st_mtime_ns]


def kod_ozeti(kok: Path = PAKET_KOKU) -> str:
    """`kok` altındaki bütün `*.py` dosyalarının (göreli yol + içerik) sha256'sı.

    Formülasyon, terazi ya da aday kodu değişince önbellek anahtarı da değişsin
    diye. Satır sonları LF'ye çevrilir: aynı kod Windows (CRLF) ve Linux
    çalışma kopyasında aynı özeti verir."""
    ozet = hashlib.sha256()
    for yol in sorted(kok.rglob("*.py"), key=lambda y: y.relative_to(kok).as_posix()):
        ozet.update(yol.relative_to(kok).as_posix().encode("utf-8") + b"\0")
        ozet.update(yol.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return ozet.hexdigest()


def onbellek_anahtari(
    con: duckdb.DuckDBPyConnection, karar: date, p: Parametreler, yontem: str, deger: str
) -> str:
    """Planı belirleyen her şeyin özeti: karar anı, bütün parametreler, yöntem,
    değer terazisi, v4 dosyasının kimliği (yol + boyut + mtime) ve
    `blok_transfer` paketinin kod özeti (`kod_ozeti`)."""
    icerik = {
        "karar": karar.isoformat(),
        "parametreler": dataclasses.asdict(p),
        "yontem": yontem,
        "deger": deger,
        "kaynak": _kaynak_izi(con),
        "kod": kod_ozeti(),
    }
    metin = json.dumps(icerik, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(metin.encode("utf-8")).hexdigest()


def _oku(onbellek: Path, anahtar: str) -> Plan | None:
    """`<anahtar>.json` yazımın son adımı: o yoksa kayıt yarımdır, okunmaz."""
    ust, hareket = onbellek / f"{anahtar}.json", onbellek / f"{anahtar}.parquet"
    if not (ust.exists() and hareket.exists()):
        return None
    bilgi = json.loads(ust.read_text(encoding="utf-8"))
    df = pd.read_parquet(hareket)
    return Plan(
        hareketler=df if len(df) else bos_hareketler(),
        durum=bilgi["durum"],
        sure_sn=bilgi["sure_sn"],
        sayaclar=bilgi["sayaclar"],
        amac=bilgi["amac"],
    )


def _yaz(onbellek: Path, anahtar: str, plan: Plan) -> None:
    """Önce hareketler, en son üst bilgi; ikisi de geçici dosyadan yer değiştirerek."""
    onbellek.mkdir(parents=True, exist_ok=True)
    hareket, ust = onbellek / f"{anahtar}.parquet", onbellek / f"{anahtar}.json"
    gecici = hareket.with_suffix(".parquet.yaziliyor")
    plan.hareketler[HAREKET_KOLONLARI].reset_index(drop=True).to_parquet(gecici, index=False)
    os.replace(gecici, hareket)
    bilgi = {
        "durum": plan.durum,
        "sure_sn": plan.sure_sn,
        "sayaclar": plan.sayaclar,
        "amac": plan.amac,
    }
    gecici = ust.with_suffix(".json.yaziliyor")
    gecici.write_text(json.dumps(bilgi, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(gecici, ust)


def boru_hatti(
    con: duckdb.DuckDBPyConnection,
    karar: date,
    p: Parametreler,
    yontem: str,
    onbellek: Path | None = None,
    deger: str = "ciro",
) -> tuple[Plan, dict]:
    """Görünümler → adaylar → terazi → çözücü → özet. Senaryoların ve testlerin tek kapısı.

    `onbellek` verilirse plan `onbellek/<anahtar>.parquet` (hareketler) ve
    `.json` (durum, süre, sayaçlar, amaç) olarak saklanır; aynı anahtarla
    ikinci çağrı çözücüyü çalıştırmaz. Durumu "hata" olan plan saklanmaz.
    Anahtar için `onbellek_anahtari`.
    """
    veri.gorunumler(con, karar)
    anahtar = onbellek_anahtari(con, karar, p, yontem, deger) if onbellek is not None else None
    plan = _oku(Path(onbellek), anahtar) if anahtar else None
    if plan is None:
        df = terazi.agirliklandir(adaylar_mod.uret(con, karar, p), p, deger=deger)
        kapasite = adaylar_mod.kapasite_boslugu(con, karar, tepe_hafta=p.tepe_hafta)
        plan = COZUCULER[yontem](df, kapasite, p)
        if anahtar and plan.durum != "hata":      # hata kalıcı sonuç değil, saklanmaz
            _yaz(Path(onbellek), anahtar, plan)
    return plan, ozetle(plan, p)
