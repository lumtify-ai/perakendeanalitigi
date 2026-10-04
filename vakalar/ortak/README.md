# perakende-analitik

Yok satma vakasının (stoksuzluk kayıp satışı kestiricileri) ortak paketi.
Yayımlanan v4 verisini okur; kestiriciler ve değerlendirme bu paketin üstünde
durur.

## Kurulum

```
cd vakalar/ortak
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"          # Windows; Linux/macOS: .venv/bin/pip
.venv/Scripts/python -m pytest -q              # hızlı testler
.venv/Scripts/python -m pytest -q -m veri      # gerçek v4 gerektirenler (yavaş)
```

Veri: `veri/cikti/v4/perakende.duckdb` (yayımlanan `lumoda-v4.duckdb`'yi bu adla
koyun ya da `PERAKENDE_V4_DB` ortam değişkeniyle gösterin; indirme:
<https://github.com/lumtify-ai/perakendeanalitigi/releases/tag/veri-v4>). Yoksa
`veri` işaretli testler atlanır. Hakem için ek bağımlılık:
`pip install -e ".[hakem]"` (`perakende-veri`).

## Modüller

| Modül | İş |
|---|---|
| `kaynak` | v4'e salt okunur bağlantı; `temiz_satis` (mükerrer satış ayıklanır), `cesit_hucreleri` (mağaza × SKU çeşidi; hayalet stok düşer) |

Sonraki görevlerde `stok`, `ozellikler`, `hakem`, `talep` gibi modüller eklenir.

## Sızıntı kuralı

Kestiriciler yalnız yayımlanan tabloları okur, gizli gerçeği görmez.
`perakende_veri` (gizli gerçeği üreten paket) yalnız `hakem.py`'de, `hakem`
yalnız `degerlendir.py`'de içe aktarılır. `tests/test_sizinti.py` paketteki
her dosyayı `ast` ile tarar ve bu kuralı kilitler.
