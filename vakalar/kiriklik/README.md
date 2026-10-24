# Kırıklık transferi (tekleme) vakası

Kırık beden setlerinin kalan bedenlerini indirimden önce toplamanın (kırıklık transferi) kırıklığı ne kadar
azalttığını, satışa ne kadar döndüğünü ve maliyetine değip değmediğini aynı mal ve aynı indirimle ölçen vaka.
Bu dosya yalnız kurulumu anlatır; kollar, tanımlar ve sonuçların okunduğu bölümler vaka bittiğinde eklenir.

## Kurulum

    cd vakalar/kiriklik
    python -m venv .venv
    .venv/Scripts/pip install numpy==2.5.4 pandas==2.3.3 duckdb==1.5.6 pyarrow==26.0.0 \
        scikit-learn==1.7.2 scipy==1.18.1 lightgbm==4.5.0 threadpoolctl==3.7.0 pulp==3.3.2
    .venv/Scripts/pip install -e ../ortak              # perakende_analitik (kaynak, sayı denetimi)
    .venv/Scripts/pip install --no-deps -e ../../veri  # perakende_veri (yalnız hakem ve simülasyon)
    .venv/Scripts/pip install --no-deps -e ../allocation   # İlk Sevkiyat motoru ve yardımcıları
    .venv/Scripts/pip install --no-deps -e ../kumeleme
    .venv/Scripts/pip install -e ".[dev]"

Kütüphane sürümleri Markdown (İndirim Takvimi) vakasının `.venv`'iyle (dolayısıyla İlk Sevkiyat'ınkiyle) aynıdır ve koşu
önbelleğinin anahtarındadır (numpy, pandas, pyarrow, duckdb, lightgbm, scikit-learn); biri değişirse bütün
koşular yeniden simüle edilir. `pulp` yalnız optimizasyon kolları içindir (Blok Transfer'in `.venv`'iyle aynı
sürüm). `allocation` ve `kumeleme` `--no-deps` kurulur; hiçbir sürüm değişmemelidir.

**Veri.** `veri/cikti/v4/perakende.duckdb` (ya da `PERAKENDE_V4_DB`). Yoksa yayımlanan `veri-v4` dosyalarını
indirin ya da `cd veri && python -m perakende_veri.v4.uret`. Bir `git worktree`'de `veri/cikti` bulunmaz:
`PERAKENDE_V4_DB`'yi ana çalışma dizinindeki dosyaya gösterin. `veri` işaretli testler dosya yoksa atlanır.

## Testler

Komutlar vakanın `.venv`'iyle, `vakalar/kiriklik` içinden; Windows konsolunda `PYTHONIOENCODING=utf-8`.

    .venv/Scripts/python -m pytest tests -q -m "not veri"     # hızlı takım: oyuncak fikstür
    .venv/Scripts/python -m pytest tests -q -m veri           # yayımlanan v4 gerekir
