import { yaziAdresi, yaziYolunuAyristir } from './yol'

type HamYazi = {
  id: string
  data: {
    baslik: string
    tip: string
    sira: number
    durum: string
    ozet: string
  }
}

export type YaziOzet = {
  id: string
  slug: string
  baslik: string
  tip: string
  sira: number
  durum: string
  ozet: string
  adres: string
}

function ozetle(ham: HamYazi): YaziOzet {
  const yol = yaziYolunuAyristir(ham.id)
  return {
    id: ham.id,
    slug: yol.slug,
    baslik: ham.data.baslik,
    tip: ham.data.tip,
    sira: ham.data.sira,
    durum: ham.data.durum,
    ozet: ham.data.ozet,
    adres: yaziAdresi(yol),
  }
}

function siraya(a: YaziOzet, b: YaziOzet): number {
  return a.sira - b.sira
}

/** Bir dizinin yazıları, okuma sırasına göre. */
export function diziYazilari(
  yazilar: HamYazi[],
  alan: string,
  dizi: string,
): YaziOzet[] {
  return yazilar
    .filter((ham) => ham.id.startsWith(`${alan}/${dizi}/`))
    .map(ozetle)
    .sort(siraya)
}

/** Tekil bir alanın doğrudan altındaki yazılar. */
export function alanYazilari(yazilar: HamYazi[], alan: string): YaziOzet[] {
  return yazilar
    .filter((ham) => {
      const yol = yaziYolunuAyristir(ham.id)
      return yol.alan === alan && yol.dizi === null
    })
    .map(ozetle)
    .sort(siraya)
}

/** Sıralı bir listede verilen yazının önceki ve sonraki komşusu. */
export function komsular(
  sirali: YaziOzet[],
  slug: string,
): { onceki: YaziOzet | null; sonraki: YaziOzet | null } {
  const yer = sirali.findIndex((y) => y.slug === slug)
  if (yer === -1) return { onceki: null, sonraki: null }
  return {
    onceki: sirali[yer - 1] ?? null,
    sonraki: sirali[yer + 1] ?? null,
  }
}
