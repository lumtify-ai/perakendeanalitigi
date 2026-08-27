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


def _kesirli(degiskenler) -> int:
    """Kaç tanesi ne 0 ne 1; yani gevşetme gerçekten gevşemiş mi."""
    return sum(
        1
        for d in degiskenler
        if d.value() is not None and 1e-6 < d.value() < 1 - 1e-6
    )


def _lp_bosluk(df, kapasite, p) -> tuple[float, float, int, int]:
    """(LP gevşetmesi, tam sayı çözüm, kesirli x sayısı, kesirli y sayısı)."""
    model, x, y = mip.kur(df, kapasite, p)
    for degisken in list(x.values()) + list(y.values()):
        degisken.cat = pulp.LpContinuous
        degisken.lowBound, degisken.upBound = 0, 1
    model.solve(pulp.PULP_CBC_CMD(msg=0))
    gevsek = pulp.value(model.objective)
    kesirli_x, kesirli_y = _kesirli(x.values()), _kesirli(y.values())
    plan = mip.cozumle(df, kapasite, p)
    ozet = degerlendirme.ozetle(plan, p)
    return gevsek, ozet["net_kazanc_tl"], kesirli_x, kesirli_y


def _acgozlu_sayaclar(df, kapasite, p) -> dict[str, int]:
    """Açgözlü döngünün adım adım sayaçları.

    Döngü `cozuculer/greedy.py`'den bilerek kopyalanmıştır: çözücü sayaç
    tutmuyor ve yalnız rapor uğruna Plan'a sayaç alanı eklemek çözücüyü
    kirletirdi. Kopyanın kaymadığını `main` çapraz kontrol ediyor: buradaki
    "seçilen" ile gerçek greedy planının hareket sayısı arasındaki fark
    minimum koli filtresinin kestiği sayıdır ve negatif çıkamaz.
    """
    kalan = dict(kapasite)
    verilen: set[tuple[str, str]] = set()
    sayac = {"pozitif": 0, "blok": 0, "kapasite": 0, "secilen": 0}
    sirali = df.sort_values(
        by=["w", "verici", "alici", "option_id"],
        ascending=[False, True, True, True],
    )
    for satir in sirali.itertuples(index=False):
        if satir.w <= 0:
            break
        sayac["pozitif"] += 1
        if (satir.verici, satir.option_id) in verilen:
            sayac["blok"] += 1
            continue
        if kalan.get(satir.alici, 0) < satir.adet:
            sayac["kapasite"] += 1
            continue
        verilen.add((satir.verici, satir.option_id))
        kalan[satir.alici] -= satir.adet
        sayac["secilen"] += 1
    return sayac


def _rota_dagilimi(plan) -> dict[int, int]:
    """Rota başına taşınan option sayısının dağılımı: {1: 147, 2: 42, ...}."""
    h = plan.hareketler
    if not len(h):
        return {}
    sayim = h.groupby(["verici", "alici"]).size().value_counts()
    return {int(k): int(sayim[k]) for k in sorted(sayim.index)}


def _farkli_alici(a_plan, b_plan) -> tuple[int, int]:
    """(iki planın ortak (verici, option) bloğu, bunların kaçında alıcı farklı)."""

    def harita(plan):
        h = plan.hareketler
        return {(v, o): al for v, al, o in zip(h.verici, h.alici, h.option_id)}

    a, b = harita(a_plan), harita(b_plan)
    ortak = set(a) & set(b)
    return len(ortak), sum(1 for k in ortak if a[k] != b[k])


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
    planlar = {}
    for yontem in ("greedy", "mip"):
        plan, ozet = degerlendirme.boru_hatti(con, karar, REFERANS, yontem)
        planlar[yontem] = plan
        yakalama = degerlendirme.kayip_satis_yakalama(plan, con, karar)
        h = plan.hareketler
        dagilim = _rota_dagilimi(plan)
        adreslenen = len(
            {(a, o) for a, o in zip(h.alici, h.option_id) if (a, o) in kirik_kume}
        )
        print(f"\n--- {yontem} ---")
        for ad, deger in ozet.items():
            print(f"  {ad}: {deger:,}" if isinstance(deger, int) else f"  {ad}: {deger}")
        print(f"  kayip_yakalama: {yakalama:.1%}")
        print("  rota başına option dağılımı: "
              + " · ".join(f"{k}→{dagilim.get(k, 0)}" for k in (1, 2, 3, 4)))
        print(f"  adreslenen kırık çift: {adreslenen}")

    sayac = _acgozlu_sayaclar(df, kapasite, REFERANS)
    kesilen = sayac["secilen"] - len(planlar["greedy"].hareketler)
    print("\n=== AÇGÖZLÜ ADIM TABLOSU ===")
    print(f"  SQL'in bulduğu aday: {len(df)}")
    print(f"  puanı pozitif olan: {sayac['pozitif']}")
    print(f"  'bu blok zaten verildi' diye atlanan: {sayac['blok']}")
    print(f"  kapasite yüzünden atlanan: {sayac['kapasite']}")
    print(f"  seçilen hareket: {sayac['secilen']}")
    print(f"  minimum koli filtresinin kestiği: {kesilen}")

    ortak, farkli = _farkli_alici(planlar["greedy"], planlar["mip"])
    print(f"\nİki planın ortak (verici, option) bloğu: {ortak} · "
          f"alıcısı farklı olan: {farkli}")

    gevsek, tam, kesirli_x, kesirli_y = _lp_bosluk(df, kapasite, REFERANS)
    print(f"\nLP gevşetmesi {gevsek:,.2f} · tam sayı {tam:,.2f} · "
          f"boşluk {gevsek - tam:,.2f} TL ({(gevsek - tam) / tam:.4%})")
    print(f"gevşetilmiş çözümde kesirli çıkan: {kesirli_x}/{len(df)} x · "
          f"{kesirli_y}/{len(rotalar)} y")

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
