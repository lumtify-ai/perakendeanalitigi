import numpy as np
import pytest
from lightgbm.basic import LightGBMError

import replenishment.tahmin as tahmin_mod
from replenishment.tahmin import (
    OZELLIKLER,
    Tahminci,
    egitim_seti,
    hiperparametre_sec,
    ozellik_tablosu,
)

P = {"num_leaves": 15, "n_estimators": 50, "learning_rate": 0.05, "min_child_samples": 5}


def test_egitim_hedefi_karar_gununu_asmaz(mini_dunya):
    H = len(mini_dunya.hucre_urun)
    s = np.ones((365, H), np.int32)
    k = mini_dunya.gun("2025-09-01")
    s[k + 1 :] = 999  # gelecek bozuk
    X, y = egitim_seti(s, mini_dunya, k, mini_dunya.gun("2025-06-02"))
    assert y.max() < 999


def test_sifir_hedefte_negatif_ya_da_nan_yok(mini_dunya):
    H = len(mini_dunya.hucre_urun)
    s = np.zeros((365, H), np.int32)
    t = Tahminci(P, mini_dunya.gun("2025-06-02")).tahmin_et(s, mini_dunya, mini_dunya.gun("2025-09-01"))
    assert (t >= 0).all() and not np.isnan(t).any()


def test_deterministik(mini_dunya):
    rng = np.random.default_rng(1)
    s = rng.poisson(0.5, (365, len(mini_dunya.hucre_urun))).astype(np.int32)
    tc = Tahminci(P, mini_dunya.gun("2025-06-02"))
    k = mini_dunya.gun("2025-09-01")
    assert (tc.tahmin_et(s, mini_dunya, k) == tc.tahmin_et(s, mini_dunya, k)).all()


def test_ozellik_tablosu_oc_basina_bir_satir(mini_dunya):
    s = np.zeros((365, len(mini_dunya.hucre_urun)), np.int32)
    X = ozellik_tablosu(s, mini_dunya, mini_dunya.gun("2025-09-01"))
    assert len(X) == len(mini_dunya.oc_hucre) and list(X.columns) == OZELLIKLER


def test_bozuk_egitim_verisi_sessizce_sifir_donmez(mini_dunya, monkeypatch):
    """`except Exception` genişliğinin daraltıldığını kanıtlar: yalnız
    belgelenen iki dal (eğitim örneği yok / hedefin tamamı sıfır) sabit 0
    döner. Burada `egitim_seti`, LightGBM'in reddedeceği bozuk (X, y
    uzunlukları uyuşmayan, hedefi sıfır OLMAYAN) bir çift döndürecek
    şekilde maymun-yamalanır; `tahmin_et` bunu yutup 0 döndürmek yerine
    gerçek LightGBM hatasını yükseltmeli."""
    H = len(mini_dunya.hucre_urun)
    s = np.zeros((365, H), np.int32)
    k = mini_dunya.gun("2025-09-01")

    normal_X = ozellik_tablosu(s, mini_dunya, k)
    X_bozuk = normal_X.iloc[:2].copy()          # 2 satır
    y_bozuk = np.array([1.0, 2.0, 3.0, 4.0])    # 4 eleman — uzunluk uyuşmuyor, toplam > 0

    monkeypatch.setattr(tahmin_mod, "egitim_seti", lambda *a, **kw: (X_bozuk, y_bozuk))

    tc = Tahminci(P, mini_dunya.gun("2025-06-02"))
    with pytest.raises(LightGBMError):
        tc.tahmin_et(s, mini_dunya, k)


def test_hiperparametre_sec_izgara_noktasi_doner(mini_dunya):
    rng = np.random.default_rng(2)
    s = rng.poisson(0.5, (365, len(mini_dunya.hucre_urun))).astype(np.int32)
    bit = mini_dunya.gun("2025-09-01")
    p = hiperparametre_sec(s, mini_dunya, bit)
    assert (p["num_leaves"], p["n_estimators"]) in {(15, 200), (15, 400), (31, 200), (31, 400)}
    assert p["learning_rate"] == 0.05 and p["min_child_samples"] == 50


def test_hiperparametre_sec_bit_gunune_sizmaz(mini_dunya, monkeypatch):
    """`hiperparametre_sec`'in kullandığı hiçbir eğitim/doğrulama hedef
    penceresi `bit_gunu`'ye veya sonrasına dokunmamalı (spec: kalibrasyon
    yalnız `bit_gunu`'den KESİNLİKLE önceki veriyi kullanmalı). `ihtiyac.
    haftalik`'in 3. pozisyonel argümanı (`karar_gunu`), o pencerenin son
    dahil edilen günüdür (`haftalik`'in kendi belgesi: "karar_gunu dahil
    geriye doğru"); `tahmin.py`'nin her `haftalik` çağrısını (özellik
    penceresi VE hedef penceresi) casus (spy) ile yakalayıp hiçbirinin
    `bit_gunu`'ye ulaşmadığını doğrudan kanıtlıyoruz — istatistiksel bir
    karşılaştırma değil, birebir sınır kanıtı."""
    rng = np.random.default_rng(3)
    s = rng.poisson(0.5, (365, len(mini_dunya.hucre_urun))).astype(np.int32)
    bit = mini_dunya.gun("2025-09-01")

    cagrilan_gunler = []
    gercek_haftalik = tahmin_mod.haftalik

    def casus(satis, dunya, karar_gunu, hafta):
        cagrilan_gunler.append(karar_gunu)
        return gercek_haftalik(satis, dunya, karar_gunu, hafta)

    monkeypatch.setattr(tahmin_mod, "haftalik", casus)

    hiperparametre_sec(s, mini_dunya, bit)

    assert cagrilan_gunler, "hiç haftalik cagrisi yakalanmadi"
    assert max(cagrilan_gunler) < bit, (
        f"bit_gunu={bit} icin en buyuk cagrilan gun {max(cagrilan_gunler)} - "
        "oyun doneminin ilk gunune (veya sonrasina) sizinti var"
    )
