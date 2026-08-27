"""Yazıların alıntıladığı bütün sayıları gerçek veriden basar.

    .venv/Scripts/python rapor.py

Yazı düzenlerken tek kaynak budur. Model spec §1: uydurma sayı yasaktır.
"""
from dataclasses import replace

import pulp

from blok_transfer import degerlendirme
from blok_transfer.cekirdek import adaylar as adaylar_mod
from blok_transfer.cekirdek import metrikler, terazi, veri
from blok_transfer.cekirdek.parametreler import Parametreler
from blok_transfer.cozuculer import mip

REFERANS = Parametreler()          # verici ≥ 6, alıcı tavanı kapalı, min_satis 1


def _lp_bosluk(df, kapasite, p) -> tuple[float, float]:
    """(LP gevşetmesinin değeri, tam sayı çözümün değeri)."""
    model, x, y = mip.kur(df, kapasite, p)
    for degisken in list(x.values()) + list(y.values()):
        degisken.cat = pulp.LpContinuous
        degisken.lowBound, degisken.upBound = 0, 1
    model.solve(pulp.PULP_CBC_CMD(msg=0))
    gevsek = pulp.value(model.objective)
    plan = mip.cozumle(df, kapasite, p)
    ozet = degerlendirme.ozetle(plan, p)
    return gevsek, ozet["net_kazanc_tl"]


def main() -> None:
    con = veri.baglan()
    karar = veri.karar_tarihi(con)
    kapasite = adaylar_mod.kapasite_boslugu(con, karar)

    magaza_sayisi = con.execute("select count(*) from magaza").fetchone()[0]
    option_sayisi = con.execute("select count(distinct option_id) from urun").fetchone()[0]
    kiriklar = metrikler.kiriklar(con, karar)

    print("=== VERİ ===")
    print(f"mağaza {magaza_sayisi} · option {option_sayisi}")
    print(f"kırık (mağaza, option) çifti: {len(kiriklar)}")
    print(f"kırık × alıcı adayı: {len(kiriklar)} × {magaza_sayisi - 1} = "
          f"{len(kiriklar) * (magaza_sayisi - 1):,}")
    print(f"kombinatorik üst sınır: {magaza_sayisi} × {magaza_sayisi - 1} × "
          f"{option_sayisi} = {magaza_sayisi * (magaza_sayisi - 1) * option_sayisi:,}")

    df = terazi.agirliklandir(adaylar_mod.uret(con, karar, REFERANS), REFERANS)
    rotalar = sorted(set(zip(df.verici, df.alici)))
    blok_kisiti = len(df.groupby(["verici", "option_id"]))
    kapasite_kisiti = df.alici.nunique()
    rota_bagi = len(df)
    koli_kisiti = len(rotalar)

    print("\n=== REFERANS SENARYO (verici ≥ 6 · alıcı tavanı kapalı) ===")
    print(f"aday: {len(df)}")
    print(f"x değişkeni {len(df)} + y değişkeni {len(rotalar)} = "
          f"{len(df) + len(rotalar)} ikili değişken")
    print(f"kısıt: blok {blok_kisiti} + kapasite {kapasite_kisiti} + "
          f"rota bağlama {rota_bagi} + koli {koli_kisiti} = "
          f"{blok_kisiti + kapasite_kisiti + rota_bagi + koli_kisiti}")

    kirik_kume = set(zip(kiriklar.magaza_id, kiriklar.option_id))
    for yontem in ("greedy", "mip"):
        plan, ozet = degerlendirme.boru_hatti(con, karar, REFERANS, yontem)
        yakalama = degerlendirme.kayip_satis_yakalama(plan, con, karar)
        h = plan.hareketler
        tek_option = (
            h.groupby(["verici", "alici"]).size().eq(1).sum() if len(h) else 0
        )
        adreslenen = len(
            {(a, o) for a, o in zip(h.alici, h.option_id) if (a, o) in kirik_kume}
        )
        print(f"\n--- {yontem} ---")
        for ad, deger in ozet.items():
            print(f"  {ad}: {deger:,}" if isinstance(deger, int) else f"  {ad}: {deger}")
        print(f"  kayip_yakalama: {yakalama:.1%}")
        print(f"  tek option taşıyan rota: {tek_option}")
        print(f"  adreslenen kırık çift: {adreslenen}")

    gevsek, tam = _lp_bosluk(df, kapasite, REFERANS)
    print(f"\nLP gevşetmesi {gevsek:,.2f} · tam sayı {tam:,.2f} · "
          f"boşluk {gevsek - tam:,.2f} TL ({(gevsek - tam) / tam:.4%})")

    print("\n=== DEMO KADRANI ===")
    for vv, aa in [(6, 0), (6, 3), (6, 6), (14, 6), (18, 14), (26, 6)]:
        p = replace(REFERANS, verici_cover_esigi=float(vv), alici_cover_tavani=float(aa))
        satir = []
        for yontem in ("greedy", "mip"):
            plan, ozet = degerlendirme.boru_hatti(con, karar, p, yontem)
            oran = degerlendirme.kayip_satis_yakalama(plan, con, karar)
            satir.append(
                f"{yontem} {ozet['option_sayisi']} hrkt / {ozet['rota_sayisi']} rota / "
                f"{ozet['net_kazanc_tl']:,.0f} TL / {oran:.1%}"
            )
        etiket = "kapalı" if aa == 0 else str(aa)
        print(f"  verici≥{vv:<3} alıcı≤{etiket:<6} | " + "  ·  ".join(satir))


if __name__ == "__main__":
    main()
