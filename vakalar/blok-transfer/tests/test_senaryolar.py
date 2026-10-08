import json
from dataclasses import replace
from datetime import date
from itertools import product
from pathlib import Path

import pandas as pd
import pytest

import senaryolar
from blok_transfer import degerlendirme, hazirla
from blok_transfer.cekirdek import veri
from blok_transfer.cozuculer.tip import Plan, bos_hareketler

KARAR = date(2025, 12, 29)
OLCUTLER = ["option_sayisi", "tasinan_adet", "rota_sayisi", "bosalan_magaza",
            "net_kazanc_tl", "kayip_yakalama_yuzde", "sure_sn"]


def sahte_kayip() -> pd.DataFrame:
    """Ölçüm penceresi [2025-12-29, 2026-02-23). Fikstürde plan MA→MC OPT2'yi taşır
    (OPT2-1: 2, -2: 1, -3: 2, -4: 1, -5: 2 adet = 8).

    pencere içi, evren içi kayıp  MC OPT2-1: 1 · MC OPT2-3: 5 · MB OPT1-3: 14 · MD OPT2-1: 2
    → payda 22; kurtarılan min(2,1) + min(2,5) = 3 → yakalama 3/22 = %13,6.
    Düşenler: pencere öncesi satır, ONL (evren dışı), pencere sonrası satır."""
    return pd.DataFrame(
        [
            ("2026-01-05", "MC", "OPT2-1", 1),
            ("2026-01-12", "MC", "OPT2-3", 5),
            ("2026-01-12", "MB", "OPT1-3", 14),
            ("2026-02-02", "MD", "OPT2-1", 2),
            ("2025-12-01", "MC", "OPT2-2", 9),     # pencere öncesi
            ("2026-01-05", "ONL", "OPT2-4", 9),    # evren dışı
            ("2026-02-23", "MC", "OPT2-5", 9),     # pencere sonrası (ikinci uç dahil değil)
        ],
        columns=["tarih", "magaza_id", "urun_id", "kayip"],
    )


def test_sema_ve_anahtar_tamligi(con, tmp_path):
    icerik = senaryolar.uret(con, KARAR, sahte_kayip())
    assert [p["ad"] for p in icerik["parametreler"]] == [
        "verici_cover_esigi", "alici_cover_tavani", "yontem",
    ]
    assert icerik["surum"]
    assert len(icerik["sonuclar"]) == 4 * 4 * 2
    kombinasyonlar = {f"{v}|{t}|{y}" for v, t, y in product(
        *[p["degerler"] for p in icerik["parametreler"]])}
    assert set(icerik["sonuclar"]) == kombinasyonlar
    assert "6|0|greedy" in icerik["sonuclar"]   # yazıların referans senaryosu
    ornek = icerik["sonuclar"]["6|0|mip"]
    assert set(ornek["ozet"]) == set(OLCUTLER)
    assert ornek["satirlar"] == []
    # durum ve boşluk sonuç düzeyinde: Demo yalnız `ozet`i çizer
    assert ornek["durum"] == "optimal" and "bosluk_yuzde" in ornek
    assert icerik["sonuclar"]["6|0|greedy"]["durum"] == "sezgisel"
    assert "bosluk_yuzde" not in icerik["sonuclar"]["6|0|greedy"]   # açgözlüde sınır yok
    assert "durum" not in ornek["ozet"] and "bosluk_yuzde" not in ornek["ozet"]

    hedef = tmp_path / "blok-transfer.json"
    senaryolar.yaz(icerik, hedef)
    assert hedef.stat().st_size < 500 * 1024
    json.loads(hedef.read_text(encoding="utf-8"))


def test_olcut_sirasi_manset_ustte(con):
    """Demo.astro ölçütleri sözlüğün ekleme sırasıyla basar: manşet (net kazanç, yakalama)
    üstte, çözüm süresi en altta."""
    icerik = senaryolar.uret(con, KARAR, sahte_kayip())
    for anahtar, sonuc in icerik["sonuclar"].items():
        assert list(sonuc["ozet"]) == OLCUTLER, anahtar


def test_kayip_yakalama_ileriye_bakan_olcumden_gelir(con):
    """Yakalama hakemsiz Basit kaybından, ölçüm penceresinde: 3/22 → yüzde olarak tek ondalık."""
    icerik = senaryolar.uret(con, KARAR, sahte_kayip())
    for anahtar, sonuc in icerik["sonuclar"].items():
        oran = sonuc["ozet"]["kayip_yakalama_yuzde"]
        assert oran == pytest.approx(13.6), anahtar
        assert len(str(oran).partition(".")[2]) <= 1, anahtar


def test_referans_senaryo_ilk_tiktir(con):
    """Okuyucu yazıdaki sayıyı demoda çevirmeden bulabilmeli."""
    icerik = senaryolar.uret(con, KARAR, sahte_kayip())
    ilk = "|".join(str(p["degerler"][0]) for p in icerik["parametreler"])
    assert ilk == "6|0|greedy"
    assert list(icerik["sonuclar"])[0] == ilk


def test_kapali_tavanin_ekran_etiketi_var(con):
    icerik = senaryolar.uret(con, KARAR, sahte_kayip())
    tavan = icerik["parametreler"][1]
    assert tavan["deger_etiketleri"]["0"] == "kapalı"


def test_boyut_bekcisi(tmp_path):
    sisik = {"surum": "x", "parametreler": [], "sonuclar": {"k": {"ozet": {"a": "b" * 600_000}, "satirlar": []}}}
    with pytest.raises(ValueError, match="500"):
        senaryolar.yaz(sisik, tmp_path / "sisik.json")


def test_hata_durumunda_uretim_durur(con, monkeypatch):
    def hatali(*args, **kwargs):
        return Plan(bos_hareketler(), "hata", 0.0)

    monkeypatch.setitem(degerlendirme.COZUCULER, "mip", hatali)
    with pytest.raises(RuntimeError, match=r"6\|0\|mip"):
        senaryolar.uret(con, KARAR, sahte_kayip())


def test_korunum_mip_acgozluden_kotuyse_durur(con, monkeypatch):
    """MIP ≥ açgözlü yapısal garanti değil, üretimde denetlenir: 'optimal' bir MIP planı
    açgözlüden 0,5 TL'den fazla kötüyse hücre adıyla hata."""
    def bos(*args, **kwargs):
        return Plan(bos_hareketler(), "optimal", 0.0, amac=0.0)

    monkeypatch.setitem(degerlendirme.COZUCULER, "mip", bos)
    with pytest.raises(RuntimeError, match=r"6\|0.*açgözlü"):
        senaryolar.uret(con, KARAR, sahte_kayip())


def sonuc_sozlugu(f) -> tuple[dict, list[dict]]:
    """`f(verici, tavan) -> (option_sayisi, net_kazanc_tl)` ile elle kurulmuş MIP sonuçları."""
    parametreler = senaryolar.PARAMETRELER
    sonuclar = {}
    for v, t in product(parametreler[0]["degerler"], parametreler[1]["degerler"]):
        opt, net = f(v, t)
        for yontem in ("greedy", "mip"):
            sonuclar[f"{v}|{t}|{yontem}"] = {
                "ozet": {"option_sayisi": opt if yontem == "mip" else -1,
                         "net_kazanc_tl": net if yontem == "mip" else -1.0},
                "satirlar": [],
            }
    return sonuclar, parametreler


def test_olu_adim_bulunur():
    # verici 14 → 18 hiçbir tavanda planı değiştirmiyor; diğer adımlar değiştiriyor.
    def f(v, t):
        kademe = {6: 0, 14: 1, 18: 1, 26: 2}[v]
        return 10 * kademe + t, 1000.0 * kademe + 10 * t
    sonuclar, parametreler = sonuc_sozlugu(f)
    olu = senaryolar.olu_adimlar(sonuclar, parametreler)
    assert len(olu) == 1
    assert "verici_cover_esigi" in olu[0] and "14" in olu[0] and "18" in olu[0]


def test_olu_adim_tek_birlesimde_degisiyorsa_olu_degil():
    # tavan 3 → 6 yalnız verici 26'da fark yaratıyor: diğer birleşimlerde aynı olması yetmez
    def f(v, t):
        return (7, 500.0) if not (v == 26 and t >= 6) else (8, 650.0)
    sonuclar, parametreler = sonuc_sozlugu(f)
    olu = senaryolar.olu_adimlar(sonuclar, parametreler)
    assert not any("alici_cover_tavani" in s and "3" in s and "6" in s for s in olu)


def test_olu_adim_yok():
    sonuclar, parametreler = sonuc_sozlugu(lambda v, t: (v + t, 100.0 * v + t))
    assert senaryolar.olu_adimlar(sonuclar, parametreler) == []


def test_tarama_mip_satirlari(con):
    df = senaryolar.tarama(con, KARAR, sahte_kayip(), [6, 14], [0, 3, 6])
    assert list(df.columns) == ["verici", "alici_tavani", "option_sayisi", "net_kazanc_tl",
                                "kayip_yakalama_yuzde", "durum", "bosluk_yuzde"]
    assert len(df) == 2 * 3
    assert set(zip(df.verici, df.alici_tavani)) == set(product([6, 14], [0, 3, 6]))
    assert (df.durum == "optimal").all()
    assert (df.option_sayisi == 1).all() and (df.net_kazanc_tl == 100.0).all()
    assert df.kayip_yakalama_yuzde.iloc[0] == pytest.approx(13.6)


@pytest.mark.veri
def test_json_koddan_birebir_uretilir():
    """Diskteki iki JSON, koddan (önbellekli planlarla) yeniden üretilen içerikle aynı."""
    import getiri

    con = veri.baglan()
    karar = veri.karar_ani(con)
    kayip = hazirla.oku_kayip(senaryolar.CIKTI, con, karar, 8)
    uretilen = {
        senaryolar.HEDEF: senaryolar.uret(con, karar, kayip, onbellek=senaryolar.ONBELLEK),
        getiri.HEDEF: getiri.uret(con, karar, senaryolar.referans_olcum(con, karar, kayip)),
    }
    for hedef, icerik in uretilen.items():
        disk = json.loads(Path(hedef).read_text(encoding="utf-8"))
        kod = json.loads(json.dumps(icerik, ensure_ascii=False))
        disk.pop("surum"), kod.pop("surum")
        assert kod == disk, hedef
