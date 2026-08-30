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
 * @astrojs/sitemap için süzgeç üretir. Adresler mutlak URL olarak gelir.
 *
 * @param {string[]} disaridaBirakilan Site köküne göre yollar (`/…/`)
 * @returns {(sayfa: string) => boolean}
 */
export function sitemapSuzgeci(disaridaBirakilan) {
  const kume = new Set(disaridaBirakilan)
  return (sayfa) => !kume.has(new URL(sayfa).pathname)
}
