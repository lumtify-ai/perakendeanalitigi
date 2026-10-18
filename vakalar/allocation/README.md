# Allocation — ilk sevkiyat

Lumoda v4 sentetik verisi ve v4 motoru üstünde ilk sevkiyat (initial allocation) vakası:
yeni bir sezonun dalgası mağazalara ilk kez dağıtılırken, depoda ne kadarının tutulacağı ve
kalanın hangi mağazaya, hangi pakete gideceği. Tasarım:
`docs/superpowers/specs/2026-10-19-ilk-sevkiyat-design.md` (`docs/` ayrı depodur). Bu dosya
iskelettir; koşum sırası, süreler ve çıktılar vakanın son görevinde tamamlanır.

## Kurulum

    cd vakalar/allocation
    python -m venv .venv
    .venv/Scripts/pip install -e ../ortak              # perakende_analitik (kaynak, stok, sayı denetimi)
    .venv/Scripts/pip install --no-deps -e ../../veri  # perakende_veri (v4 motoru)
    .venv/Scripts/pip install -e ".[dev]"

Veri `veri/cikti/v4/perakende.duckdb` (ya da `PERAKENDE_V4_DB`); yoksa yayımlanan `veri-v4`
dosyasını indirin ya da `cd veri && python -m perakende_veri.v4.uret`.

`lightgbm` < 4.6 ve `scikit-learn` < 1.8 sabit (Windows çökmesi ve `force_all_finite`;
`pyproject.toml`'daki not).

## Koşum

Bütün komutlar `vakalar/allocation` içinden, vakanın `.venv`'iyle; Windows konsolunda
`PYTHONIOENCODING=utf-8`.

- **Sıralı koş:** v4 koşu önbelleği eşzamanlı yazmaya güvenli değil. Vakanın iki komutunu
  (testler dahil) aynı anda koşmayın; RPT ve DM vakalarının koşularıyla da aynı anda koşmayın
  (TAM bir koşu tepe ~8 GB bellek).
- Hızlı testler: `.venv/Scripts/python -m pytest -q -m "not veri"`. `veri` işaretli testler
  gerçek v4 dosyasını ve TAM dünyayı kurar (yavaş).
