from replenishment.depo import depo_kur, depo_toplami, tedarik_et


def test_tek_alim_kolisi_ve_acigi_line_payina_gore(mini_dunya):
    # A: 3 mağaza × 5 beden × 0.1 × 10 gün × 0.8 = 12 adet → koli floor(12×0.8/8)=1, açık 12×0.2=2.4
    depo = depo_kur(mini_dunya, 0.8, "2025-09-01", "2025-09-10")
    a = list(mini_dunya.optionlar).index("A")
    assert depo.koli[a] == 1
    assert depo.acik[a].sum() in (2, 3)


def test_nos_tedarigi_hedefe_tamamlar_fazlaya_dokunmaz(mini_dunya):
    depo = depo_kur(mini_dunya, 0.8, "2025-09-01", "2025-12-31")
    b = list(mini_dunya.optionlar).index("B")
    hedef = (depo.koli[b], depo.acik[b].copy())
    depo.koli[b] = 0
    depo.acik[b] = 0
    tedarik_et(depo, mini_dunya, 250)
    assert depo.koli[b] == hedef[0] and (depo.acik[b] == hedef[1]).all()
    a = list(mini_dunya.optionlar).index("A")
    depo.koli[a] = 0
    tedarik_et(depo, mini_dunya, 250)
    assert depo.koli[a] == 0          # tek alım line'ına tedarik gelmez
