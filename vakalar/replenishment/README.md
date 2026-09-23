# Replenishment — depodan mağazaya

Lumoda v2 sentetik verisi üstünde depo→mağaza ikmal vakası: kural tabanlı
temel çizgi ve LightGBM tabanlı öngörü ile karşılaştırma.

## Kurulum ve koşum

    cd vakalar/replenishment
    python -m venv .venv
    .venv/Scripts/python -m pip install -e ../../veri -e ".[dev]"
    .venv/Scripts/python -m pytest -q          # testler (hızlı + @pytest.mark.veri)

Veri yoksa önce üret: `cd veri && .venv/Scripts/python -m perakende_veri.uret`

## Kapsam

`replenishment/dunya.py` simülasyonun `cesit` sırasını koruyarak vakanın
sabit dünyasını (`Dunya`) kurar. `replenishment/kaynak.py` v2 DuckDB
tablolarını bu dünyanın hücre sırasına göre `(gün, hücre)` matrislerine
pivotlar. Hücre sırası simülasyonla hizalı kalır ki ileride bir eşdeğerlik
testi v2'yi gün gün yeniden oynatabilsin.
