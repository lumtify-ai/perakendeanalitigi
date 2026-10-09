"""Gerçek veri setiyle tutarlılık (hepsi `veri` işaretli: gerçek v4 ve önbellek ister).

Kırık çift sayısı sabit değil, rapordan okunur: `cikti/rapor.txt` yazıların tek sayı
kaynağıdır (spec §6) ve bu test onun koddan sapmadığını denetler.
"""
from pathlib import Path

import pytest

from blok_transfer import degerlendirme
from blok_transfer.cekirdek import adaylar as adaylar_mod
from blok_transfer.cekirdek import metrikler, veri
from blok_transfer.cekirdek.parametreler import Parametreler

KOK = Path(__file__).resolve().parents[1]
RAPOR = KOK / "cikti" / "rapor.txt"
ONBELLEK = KOK / "cikti" / "planlar"
KIRIK_SATIRI = "kırık (mağaza, option) çifti: "

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


def _rapordaki_kirik() -> int:
    if not RAPOR.exists():
        pytest.skip(f"{RAPOR} yok; önce: cd vakalar/blok-transfer && "
                    "PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py > cikti/rapor.txt")
    for satir in RAPOR.read_text(encoding="utf-8").splitlines():
        if satir.startswith(KIRIK_SATIRI):
            return int(satir[len(KIRIK_SATIRI):].split()[0].replace(".", ""))
    raise AssertionError(f"{RAPOR.name}: '{KIRIK_SATIRI}' satırı yok")


@pytest.mark.veri
def test_kirik_cift_sayisi_raporla_tutarli():
    con = veri.baglan()
    karar = veri.karar_ani(con)
    veri.gorunumler(con, karar)
    assert len(metrikler.kiriklar(con, karar)) == _rapordaki_kirik()


@pytest.mark.veri
def test_rapor_korunumdan_gecmis():
    """rapor.py korunum tutmazsa stdout'a hiçbir şey yazmaz; dosyadaki rapor tam ve denetlenmiş."""
    _rapordaki_kirik()                                     # rapor.txt yoksa komutu söyleyip atlar
    metin = RAPOR.read_text(encoding="utf-8")
    satirlar = metin.splitlines()
    assert "=== KORUNUM ===" in satirlar
    son = satirlar[satirlar.index("=== KORUNUM ===") + 1]
    assert son.strip().split()[1:3] == ["denetim", "tuttu"], son


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


@pytest.mark.veri
def test_yazidaki_sql_python_boru_hattiyla_ayni_adayi_uretiyor():
    """Dördüncü yazının taşıyıcı iddiası: yayımlanan sorgu Python tarafıyla
    birebir aynı aday listesini üretir. Geçmişte tam burada hata çıktı —
    `soguma` CTE'si tanımlanıp verici filtresinde kullanılmayınca sorgu
    375 yerine 1.460 aday döndürmüştü.

    Sorgunun tek girdisi `$karar` (yazıda tarih yok); karar anını burada
    `veri.karar_ani` verir."""
    con = veri.baglan()
    karar = veri.karar_ani(con)
    veri.gorunumler(con, karar)
    sql_adaylari = con.execute(_yayimlanan_sql(), {"karar": karar}).df()
    python_adaylari = adaylar_mod.uret(con, karar, Parametreler())

    assert len(sql_adaylari) == len(python_adaylari)
    assert set(zip(sql_adaylari.verici, sql_adaylari.alici, sql_adaylari.option_id)) == set(
        zip(python_adaylari.verici, python_adaylari.alici, python_adaylari.option_id)
    )


@pytest.mark.veri
def test_gercek_veride_mip_greedyden_kotu_olamaz():
    """Referans senaryo (önbellekten): MIP 'optimal' ise amacı açgözlünün net kazancından
    düşük olamaz. 'limit' durumunda garanti yok; rapor ayrıca denetler."""
    con = veri.baglan()
    karar = veri.karar_ani(con)
    p = Parametreler()
    g_plan, g_ozet = degerlendirme.boru_hatti(con, karar, p, "greedy", onbellek=ONBELLEK)
    m_plan, m_ozet = degerlendirme.boru_hatti(con, karar, p, "mip", onbellek=ONBELLEK)
    assert len(g_plan.hareketler) > 0, "referans senaryoda hiç hareket çıkmaması şüpheli"
    if m_plan.durum == "optimal":
        assert m_ozet["net_kazanc_tl"] >= g_ozet["net_kazanc_tl"] - 1e-6
