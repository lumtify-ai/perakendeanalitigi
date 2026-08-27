"""Gerçek veri setiyle tutarlılık: veri/README.md 528 kırık çift ilan ediyor."""
from dataclasses import replace
from pathlib import Path

import pytest

from blok_transfer import degerlendirme
from blok_transfer.cekirdek import adaylar as adaylar_mod
from blok_transfer.cekirdek import metrikler, veri
from blok_transfer.cekirdek.parametreler import Parametreler

# tests/ → blok-transfer/ → vakalar/ → depo kökü
YAZI = (
    Path(__file__).resolve().parents[3]
    / "site"
    / "src"
    / "content"
    / "yazi"
    / "transfer"
    / "blok-transfer"
    / "sql-ve-greedy.mdx"
)


def test_kirik_cift_sayisi_readme_ile_tutarli():
    con = veri.baglan()
    assert len(metrikler.kiriklar(con, veri.karar_tarihi(con))) == 528


def _yayimlanan_sql() -> str:
    """Dördüncü yazıdaki ```sql çitinin içini döndürür.

    Regex yok: çit satırları tam eşleşmeyle taranır, blok bulunamazsa
    ya da birden çok blok varsa test sessizce geçmek yerine ne olduğunu
    söyleyerek düşer.
    """
    if not YAZI.exists():
        raise AssertionError(f"Yazı dosyası yok: {YAZI}")
    satirlar = YAZI.read_text(encoding="utf-8").splitlines()
    bloklar: list[str] = []
    icerde: list[str] | None = None
    for satir in satirlar:
        if icerde is None:
            if satir.strip() == "```sql":
                icerde = []
        elif satir.strip() == "```":
            bloklar.append("\n".join(icerde))
            icerde = None
        else:
            icerde.append(satir)
    if icerde is not None:
        raise AssertionError(f"{YAZI.name}: ```sql çiti kapanmamış")
    if len(bloklar) != 1:
        raise AssertionError(
            f"{YAZI.name}: tam bir ```sql bloğu bekleniyordu, {len(bloklar)} bulundu"
        )
    return bloklar[0]


def test_yazidaki_sql_python_boru_hattiyla_ayni_adayi_uretiyor():
    """Dördüncü yazının taşıyıcı iddiası: yayımlanan sorgu Python tarafıyla
    birebir aynı aday listesini üretir. Geçmişte tam burada hata çıktı —
    `soguma` CTE'si tanımlanıp verici filtresinde kullanılmayınca sorgu
    375 yerine 1.460 aday döndürmüştü."""
    con = veri.baglan()
    karar = veri.karar_tarihi(con)
    sql_adaylari = con.execute(_yayimlanan_sql()).df()
    python_adaylari = adaylar_mod.uret(con, karar, Parametreler())

    assert len(sql_adaylari) == len(python_adaylari)
    assert set(zip(sql_adaylari.verici, sql_adaylari.alici, sql_adaylari.option_id)) == set(
        zip(python_adaylari.verici, python_adaylari.alici, python_adaylari.option_id)
    )


def test_gercek_veride_mip_greedyden_kotu_olamaz():
    con = veri.baglan()
    karar = veri.karar_tarihi(con)
    p = Parametreler()  # cover 6, min_satis 1 — orta senaryo
    g_plan, g_ozet = degerlendirme.boru_hatti(con, karar, p, "greedy")
    m_plan, m_ozet = degerlendirme.boru_hatti(con, karar, p, "mip")
    assert len(g_plan.hareketler) > 0, "orta senaryoda hic hareket cikmamasi supheli"
    if m_plan.durum == "optimal":
        assert m_ozet["net_kazanc_tl"] >= g_ozet["net_kazanc_tl"] - 1e-6
