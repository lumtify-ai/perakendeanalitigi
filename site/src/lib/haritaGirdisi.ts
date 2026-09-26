// site/src/lib/haritaGirdisi.ts
//
// Harita sayfaları koleksiyonları doğrudan okumaz; önce bu dosya dizileri
// DiziBagi'ye çevirir. Böylece "yayında mı" kararı tek yerde verilir ve
// haritaDurumu.ts astro:content'ten habersiz, birim testle sınanabilir kalır.

import { asamaBul, HARITA, type Faz, type FazSlug } from '../data/harita'
import { diziYazilari } from './agac'
import type { DiziBagi } from './haritaDurumu'

type HamDizi = {
  id: string
  data: { baslik: string; algoritmalar: string[] }
}

/** Dizi koleksiyonundan haritanın okuduğu bağ listesini kurar. */
export function diziBaglari(
  diziler: HamDizi[],
  yazilar: Parameters<typeof diziYazilari>[0],
): DiziBagi[] {
  return diziler.map((dizi) => {
    const [alan, diziSlug] = dizi.id.split('/')
    const uyeler = diziYazilari(yazilar, alan, diziSlug)
    return {
      id: dizi.id,
      baslik: dizi.data.baslik,
      adres: `/${alan}/${diziSlug}/`,
      algoritmalar: dizi.data.algoritmalar,
      yayinda: uyeler.some((yazi) => yazi.durum === 'yayinda'),
    }
  })
}

/** Kırıntı yolunun başı: aşamanın fazı; Temeller için boş. */
export function fazBasamagi(alanId: string): { ad: string; adres: string }[] {
  const bulunan = asamaBul(alanId)
  if (!bulunan) return []
  return [{ ad: bulunan.faz.ad, adres: `/${bulunan.faz.slug}/` }]
}

/** Slug'a göre fazı döndürür; HARITA'da yoksa açıklamayla durur. */
export function fazAl(slug: FazSlug): Faz {
  const faz = HARITA.find((f) => f.slug === slug)
  if (!faz) throw new Error(`"${slug}" fazı src/data/harita.ts'de yok.`)
  return faz
}
