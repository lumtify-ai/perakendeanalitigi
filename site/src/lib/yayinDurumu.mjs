// site/src/lib/yayinDurumu.mjs
//
// `durum: hazirlaniyor` yazılar sayfa olarak üretilmeye devam eder — dizi
// kapağı onlara bağlanıyor — ama ne indekslenir ne de site haritasına girer.
// Sitenin bütün stratejisi yapay zekâ araçlarının alıntılaması üzerine
// kurulu; ilk taramada tek cümlelik altı yer tutucu sayfa görmek geri
// alması en zor birinci izlenimdir.
//
// Neden .mjs: bu modülü astro.config.mjs içe aktarıyor. Astro yapılandırması
// yüklenirken TypeScript kaynaklarını çözebilir, ama yapılandırma yükleme
// yolu Astro sürümleri arasında değişen bir ayrıntıdır ve bu dosyanın
// çalışmaması durumunda hata "site haritası biraz fazla kalabalık" gibi
// sessiz bir sonuç doğurur. Düz ESM her koşulda yüklenir. Yine de saf
// fonksiyon ve birim testlidir (tests/yayinDurumu.test.ts).

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { extname, join, relative, sep } from 'node:path'
import matter from 'gray-matter'

/**
 * Bir yazı id'sini (`transfer/blok-transfer/sonuclar`) mutlak adrese çevirir.
 * src/lib/yol.ts'deki `yaziAdresi` ile aynı kural; burada ESM tarafında
 * tekrarlanıyor çünkü bu modül TypeScript içe aktaramaz.
 *
 * @param {string} id
 * @returns {string}
 */
export function yaziAdresinden(id) {
  return `/${id}/`
}

/**
 * `src/content/yazi` altındaki `durum: hazirlaniyor` yazıların adresleri.
 *
 * @param {string} yaziKoku `src/content/yazi` dizininin mutlak yolu
 * @returns {string[]}
 */
export function hazirlaniyorAdresleri(yaziKoku) {
  if (!existsSync(yaziKoku)) return []

  const adresler = []

  /** @param {string} dizin */
  function gez(dizin) {
    for (const ad of readdirSync(dizin)) {
      if (ad.startsWith('.')) continue
      const tamYol = join(dizin, ad)
      if (statSync(tamYol).isDirectory()) {
        gez(tamYol)
        continue
      }
      if (extname(ad) !== '.mdx') continue
      const { data } = matter(readFileSync(tamYol, 'utf-8'))
      // Şema varsayılanı "yayinda"; yalnızca açıkça hazırlanıyor olan süzülür.
      if (data.durum !== 'hazirlaniyor') continue
      const id = relative(yaziKoku, tamYol).slice(0, -'.mdx'.length).split(sep).join('/')
      adresler.push(yaziAdresinden(id))
    }
  }

  gez(yaziKoku)
  return adresler
}

/**
 * Harita dışı raf; hiçbir zaman dışarıda bırakılmaz. src/data/harita.ts'deki
 * `TEMELLER` ile aynı değer — bu modül TypeScript içe aktaramadığı için
 * burada tekrarlanıyor.
 */
export const TEMELLER = 'temeller'

/**
 * Bir dizindeki `.mdx` yazıların en az birinin yayında olup olmadığı.
 *
 * @param {string} dizin
 * @returns {boolean}
 */
function yayindaYaziVarMi(dizin) {
  if (!existsSync(dizin)) return false
  for (const ad of readdirSync(dizin)) {
    if (ad.startsWith('.')) continue
    const tamYol = join(dizin, ad)
    if (statSync(tamYol).isDirectory()) {
      if (yayindaYaziVarMi(tamYol)) return true
      continue
    }
    if (extname(ad) !== '.mdx') continue
    const { data } = matter(readFileSync(tamYol, 'utf-8'))
    if (data.durum !== 'hazirlaniyor') return true
  }
  return false
}

/**
 * Sayfası üretilen ama aktif olmayan aşamaların adresleri (`/<aşama>/`).
 *
 * Aşama sayfası her alan dosyası için üretilir, çünkü taslak dizinin kırıntı
 * yolu ona bağlanır. Aşama aktif değilse sayfası taslak yazı gibi davranır:
 * noindex basar (src/pages/[alan]/index.astro) ve site haritasına girmez.
 * Kural src/lib/haritaDurumu.ts'deki `asamaAktifMi`'nin dosya düzeyindeki
 * karşılığıdır: `yazi/<alan>/` altında `hazirlaniyor` olmayan en az bir yazı
 * varsa aşama aktiftir. İkisi denktir, çünkü build öncesi doğrulama üç
 * şeyi zorunlu kılar: her dizi en az bir algoritmayı kendi aşamasında
 * kapsar (src/lib/dogrula.ts), her yazı tanımlı bir dizinin içindedir, ve
 * harita aşamasının doğrudan altında tekil yazı durmaz (src/lib/agacSekli.ts
 * · alanHaritaDogrula; tekil yazı yalnızca Temeller'de). Üçüncüsü olmasaydı
 * aşamanın altındaki tekil bir yazı sayfayı site haritasına sokardı ama
 * sayfa noindex basmaya devam ederdi. Denklik tests/yayinDurumu.test.ts'te
 * gerçek içerik üzerinde de sınanır.
 *
 * @param {string} alanKoku `src/content/alan` dizininin mutlak yolu
 * @param {string} yaziKoku `src/content/yazi` dizininin mutlak yolu
 * @returns {string[]}
 */
export function pasifAsamaAdresleri(alanKoku, yaziKoku) {
  if (!existsSync(alanKoku)) return []
  return readdirSync(alanKoku)
    .filter((ad) => extname(ad) === '.md' && !ad.startsWith('.'))
    .map((ad) => ad.slice(0, -'.md'.length))
    .filter((alan) => alan !== TEMELLER && !yayindaYaziVarMi(join(yaziKoku, alan)))
    .map((alan) => `/${alan}/`)
}

/**
 * Yayında yazısı olmayan dizilerin kapak adresleri (`/<aşama>/<dizi>/`) ve
 * `demo: true` ise demo adresleri (`/<aşama>/<dizi>/demo/`).
 *
 * Bütün yazıları `hazirlaniyor` olan (ya da henüz hiç yazısı olmayan) dizi,
 * yazıları gibi davranır: kapağı ve demosu üretilir ama noindex basar
 * (src/pages/[alan]/[dizi]/index.astro ve demo.astro) ve site haritasına
 * girmez. Kural src/lib/haritaGirdisi.ts'deki `diziBaglari`'nın `yayinda`
 * alanının dosya düzeyindeki karşılığıdır.
 *
 * @param {string} diziKoku `src/content/dizi` dizininin mutlak yolu
 * @param {string} yaziKoku `src/content/yazi` dizininin mutlak yolu
 * @returns {string[]}
 */
export function taslakDiziAdresleri(diziKoku, yaziKoku) {
  if (!existsSync(diziKoku)) return []
  const adresler = []
  for (const alan of readdirSync(diziKoku)) {
    if (alan.startsWith('.')) continue
    const alanDizini = join(diziKoku, alan)
    if (!statSync(alanDizini).isDirectory()) continue
    for (const ad of readdirSync(alanDizini)) {
      if (ad.startsWith('.') || extname(ad) !== '.md') continue
      const dizi = ad.slice(0, -'.md'.length)
      if (yayindaYaziVarMi(join(yaziKoku, alan, dizi))) continue
      const kapak = `/${alan}/${dizi}/`
      const { data } = matter(readFileSync(join(alanDizini, ad), 'utf-8'))
      adresler.push(kapak)
      if (data.demo === true) adresler.push(`${kapak}demo/`)
    }
  }
  return adresler
}

/**
 * @astrojs/sitemap için süzgeç üretir. Adresler mutlak URL olarak gelir.
 *
 * @param {string[]} disaridaBirakilan Site köküne göre yollar (`/…/`)
 * @returns {(sayfa: string) => boolean}
 */
export function sitemapSuzgeci(disaridaBirakilan) {
  const kume = new Set(disaridaBirakilan)
  return (sayfa) => !kume.has(new URL(sayfa).pathname)
}
