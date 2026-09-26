// site/tests/yardimci/icerikDurumu.ts
//
// Testlerin beklediği değerleri gerçek içerikten türetir: hangi dizinin
// yayında olduğu, hangi algoritma ve aşamanın aktif olduğu, hangi sayfanın
// noindex basması gerektiği. Elle yazılmış sayılar ("4 aktif algoritma",
// "12 pasif aşama") bir sonraki dizi yayına girdiğinde testi kırıyordu; bu
// modül onların yerine geçer.
//
// Kasıtlı olarak src/lib/yayinDurumu.mjs'deki aşama kuralını kullanmaz:
// oradaki kural aşamayı `yazi/<aşama>/` klasörüne bakarak aktif sayar,
// burası dizi frontmatter'ındaki `algoritmalar` listesinden gider (sitedeki
// asamaAktifMi ile aynı yol). İki yol aynı sonucu vermezse test düşer.

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import matter from 'gray-matter'
import { algoritmaBul, HARITA } from '../../src/data/harita'

const ICERIK = fileURLToPath(new URL('../../src/content/', import.meta.url))
export const ALAN_KOKU = join(ICERIK, 'alan')
export const DIZI_KOKU = join(ICERIK, 'dizi')
export const YAZI_KOKU = join(ICERIK, 'yazi')

/** Bir klasördeki `.mdx` yazıların frontmatter'ı; alt klasörlere inmez. */
function yazilar(dizin: string): { slug: string; durum: string }[] {
  if (!existsSync(dizin)) return []
  return readdirSync(dizin)
    .filter((ad) => extname(ad) === '.mdx' && !ad.startsWith('.'))
    .map((ad) => {
      const { data } = matter(readFileSync(join(dizin, ad), 'utf-8'))
      // Şema varsayılanı yayinda (src/content.config.ts).
      return { slug: ad.slice(0, -'.mdx'.length), durum: data.durum ?? 'yayinda' }
    })
}

export type DiziDurumu = {
  alan: string
  dizi: string
  adres: string
  /** Frontmatter `baslik` — dizi etiketinin ve kartının bastığı ad. */
  baslik: string
  algoritmalar: string[]
  demo: boolean
  yayinda: boolean
}

/** Bütün dizi dosyaları ve yayında olup olmadıkları. */
export function diziler(): DiziDurumu[] {
  const sonuc: DiziDurumu[] = []
  for (const alan of readdirSync(DIZI_KOKU)) {
    const alanDizini = join(DIZI_KOKU, alan)
    if (!statSync(alanDizini).isDirectory()) continue
    for (const ad of readdirSync(alanDizini)) {
      if (extname(ad) !== '.md') continue
      const dizi = ad.slice(0, -'.md'.length)
      const { data } = matter(readFileSync(join(alanDizini, ad), 'utf-8'))
      sonuc.push({
        alan,
        dizi,
        adres: `/${alan}/${dizi}/`,
        baslik: String(data.baslik),
        algoritmalar: data.algoritmalar ?? [],
        demo: data.demo === true,
        yayinda: yazilar(join(YAZI_KOKU, alan, dizi)).some((y) => y.durum === 'yayinda'),
      })
    }
  }
  return sonuc
}

/** Bir dizinin yayındaki yazı sayısı — DiziKarti ve dizi kapağı listesinin
 *  bastığı sayıyla aynı kaynaktan (src/lib/haritaGirdisi.ts · diziBaglari
 *  aynı `durum: yayinda` filtresini kullanır). */
export function yayindakiYaziSayisi(alan: string, dizi: string): number {
  return yazilar(join(YAZI_KOKU, alan, dizi)).filter((y) => y.durum === 'yayinda').length
}

/** Yayındaki bir dizinin kapsadığı algoritmalar. */
export function aktifAlgoritmalar(): Set<string> {
  return new Set(diziler().filter((d) => d.yayinda).flatMap((d) => d.algoritmalar))
}

/** En az bir algoritması aktif olan harita aşamaları. */
export function aktifAsamalar(): Set<string> {
  return new Set(
    [...aktifAlgoritmalar()]
      .map((id) => algoritmaBul(id)?.asama.slug)
      .filter((slug): slug is string => slug !== undefined),
  )
}

/** src/content/alan altındaki alan kimlikleri. */
export function alanDosyalari(): Set<string> {
  return new Set(
    readdirSync(ALAN_KOKU)
      .filter((ad) => extname(ad) === '.md')
      .map((ad) => ad.slice(0, -'.md'.length)),
  )
}

/** Harita aşamaları; her biri için alan dosyası var mı, aktif mi. */
export function asamalar(): { slug: string; faz: string; alanVar: boolean; aktif: boolean }[] {
  const alanlar = alanDosyalari()
  const aktifler = aktifAsamalar()
  return HARITA.flatMap((faz) =>
    faz.asamalar.map((asama) => ({
      slug: asama.slug,
      faz: faz.slug,
      alanVar: alanlar.has(asama.slug),
      aktif: aktifler.has(asama.slug),
    })),
  )
}

/** Sayfası üretilen ama aktif olmayan aşamaların adresleri. */
export function pasifAsamaAdresleriBeklenen(): string[] {
  return asamalar()
    .filter((a) => a.alanVar && !a.aktif)
    .map((a) => `/${a.slug}/`)
}

/** `durum: hazirlaniyor` yazıların adresleri (dizili ve tekil). */
export function hazirlaniyorYaziAdresleri(): string[] {
  const sonuc: string[] = []
  for (const alan of readdirSync(YAZI_KOKU)) {
    const alanDizini = join(YAZI_KOKU, alan)
    if (!statSync(alanDizini).isDirectory()) continue
    for (const y of yazilar(alanDizini)) {
      if (y.durum === 'hazirlaniyor') sonuc.push(`/${alan}/${y.slug}/`)
    }
    for (const dizi of readdirSync(alanDizini)) {
      const diziDizini = join(alanDizini, dizi)
      if (!statSync(diziDizini).isDirectory()) continue
      for (const y of yazilar(diziDizini)) {
        if (y.durum === 'hazirlaniyor') sonuc.push(`/${alan}/${dizi}/${y.slug}/`)
      }
    }
  }
  return sonuc
}

/** Yayında yazısı olmayan dizilerin kapak ve (varsa) demo adresleri. */
export function taslakDiziAdresleriBeklenen(): string[] {
  return diziler()
    .filter((d) => !d.yayinda)
    .flatMap((d) => (d.demo ? [d.adres, `${d.adres}demo/`] : [d.adres]))
}

/** noindex basması gereken bütün adresler. */
export function noindexBeklenen(): string[] {
  return [
    ...hazirlaniyorYaziAdresleri(),
    ...pasifAsamaAdresleriBeklenen(),
    ...taslakDiziAdresleriBeklenen(),
  ].sort()
}

/** Bir dizinin bütün yazılarının slug'ları, okuma sırasına (`sira`) göre —
 *  hazırlanıyor olanlar dahil. Yazı sayfasının sol menüsü ve mobil dizi
 *  kutusu dizinin tamamını listeler (src/lib/agac.ts · diziYazilari). */
export function diziSiralamasi(alan: string, dizi: string): string[] {
  const dizin = join(YAZI_KOKU, alan, dizi)
  if (!existsSync(dizin)) return []
  return readdirSync(dizin)
    .filter((ad) => extname(ad) === '.mdx' && !ad.startsWith('.'))
    .map((ad) => {
      const { data } = matter(readFileSync(join(dizin, ad), 'utf-8'))
      return { slug: ad.slice(0, -'.mdx'.length), sira: Number(data.sira) }
    })
    .sort((a, b) => a.sira - b.sira)
    .map((y) => y.slug)
}
