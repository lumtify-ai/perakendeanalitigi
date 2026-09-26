// site/src/lib/alanBasligi.ts
import { asamaBul } from '../data/harita'

/** Aşama alanının başlığı haritadan, Temeller'inki frontmatter'dan gelir. */
export function alanBasligi(alanId: string, data: { baslik?: string }): string {
  const bulunan = asamaBul(alanId)
  if (bulunan) return bulunan.asama.ad
  if (data.baslik) return data.baslik
  throw new Error(
    `"${alanId}" alanı haritada bir aşama değil ve frontmatter'da baslik yok ` +
      `(src/content/alan/${alanId}.md). Aşamaysa src/data/harita.ts'deki slug'la ` +
      `aynı adı taşımalı; harita dışı bir rafsa baslik yazılmalı.`,
  )
}
