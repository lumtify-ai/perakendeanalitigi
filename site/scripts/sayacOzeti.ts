// site/scripts/sayacOzeti.ts
//
// Sayaç verisini okunur özete çeviren saf kısım; ağ işi sayac-oku.ts'de.
// Eleme burada, okuma anında yapılıyor: Worker ham kaydı saklar, kural
// değiştiğinde geçmiş veri de yeni kurala göre yeniden okunabilir.

export interface Satir {
  /** 1970 başından bu yana İstanbul günü. */
  gun: number
  sayfa: string
  ulke: string
  ag: string
  tarayici: string
  istekTuru: string
  goruntuleme: number
  tekil: number
  yeni: number
}

const BOT =
  /bot\b|bot\/|crawl|spider|slurp|headless|lighthouse|pagespeed|inspectiontool|iubenda|semrush|ahrefs|bytespider|gptbot|claude|perplexity|facebookexternalhit|curl|wget|python|httpclient|okhttp|java\/|go-http|node-fetch|axios|scrapy/i

// Chrome kendini otomatik günceller; 100'ün altı (2022 öncesi) bir tanıtım
// sahte olma olasılığı yüksek bir işarettir. 2026-11'de panelde görülen
// "Chrome/89 HUAWEI" trafiğinin çoğu aynı Çin bloklarından geliyordu.
const ESKI_CHROME_ESIGI = 100

// Akamai, Cloudflare ve Fastly bilerek yok: iCloud Özel Geçiş (Safari) çıkışları
// bu ağlardan görünür, oradaki okur gerçek bir insandır.
const VERI_MERKEZI =
  /amazon|google|microsoft|digitalocean|alibaba|tencent|huawei cloud|ovh|hetzner|linode|vultr|choopa|oracle|contabo|leaseweb|m247|scaleway|datacamp|hostinger/i

export type Neden = 'sayfasız' | 'görsel değil' | 'bot' | 'eski Chrome' | 'veri merkezi'

/** Satır insan trafiği sayılmıyorsa nedeni, sayılıyorsa null. */
export function elemeNedeni(s: Satir): Neden | null {
  if (!s.sayfa) return 'sayfasız'
  // Sec-Fetch başlığını göndermeyen eski tarayıcılar elenmez.
  if (s.istekTuru && s.istekTuru !== 'image') return 'görsel değil'
  if (!s.tarayici || BOT.test(s.tarayici)) return 'bot'
  const chrome = s.tarayici.match(/Chrome\/(\d+)/)
  if (chrome && Number(chrome[1]) < ESKI_CHROME_ESIGI) return 'eski Chrome'
  if (VERI_MERKEZI.test(s.ag)) return 'veri merkezi'
  return null
}

function sirala(harita: Map<string, number>): [string, number][] {
  return [...harita].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
}

function ekle(harita: Map<string, number>, anahtar: string, adet: number): void {
  harita.set(anahtar, (harita.get(anahtar) ?? 0) + adet)
}

export function ozetle(satirlar: Satir[]) {
  const gunler = new Map<number, { goruntuleme: number; tekil: number; yeni: number }>()
  const sayfalar = new Map<string, number>()
  const ulkeler = new Map<string, number>()
  const elenen: Partial<Record<Neden, number>> = {}
  const toplam = { goruntuleme: 0, tekil: 0, yeni: 0 }

  for (const s of satirlar) {
    const neden = elemeNedeni(s)
    if (neden) {
      elenen[neden] = (elenen[neden] ?? 0) + s.goruntuleme
      continue
    }
    const gun = gunler.get(s.gun) ?? { goruntuleme: 0, tekil: 0, yeni: 0 }
    for (const hedef of [gun, toplam]) {
      hedef.goruntuleme += s.goruntuleme
      hedef.tekil += s.tekil
      hedef.yeni += s.yeni
    }
    gunler.set(s.gun, gun)
    ekle(sayfalar, s.sayfa, s.goruntuleme)
    ekle(ulkeler, s.ulke, s.goruntuleme)
  }

  return {
    gunler: [...gunler]
      .sort((a, b) => a[0] - b[0])
      .map(([gun, g]) => ({
        gun: new Date(gun * 86_400_000).toISOString().slice(0, 10),
        ...g,
      })),
    toplam,
    sayfalar: sirala(sayfalar),
    ulkeler: sirala(ulkeler),
    elenen,
  }
}

/** Son `gun` günün ham satırları. Saklama süresi üç ay olduğu için 92'de sınırlı. */
export function sorgu(gun: number): string {
  if (!Number.isInteger(gun) || gun < 1 || gun > 92) {
    throw new Error(`Gün sayısı 1 ile 92 arasında bir tam sayı olmalı: ${gun}`)
  }
  return `
    SELECT
      intDiv(toUInt32(timestamp) + 10800, 86400) AS gun,
      blob1 AS sayfa,
      blob2 AS ulke,
      blob3 AS ag,
      blob4 AS tarayici,
      blob5 AS istekTuru,
      SUM(_sample_interval) AS goruntuleme,
      SUM(_sample_interval * double1) AS tekil,
      SUM(_sample_interval * double2) AS yeni
    FROM perakende_sayac
    WHERE timestamp > NOW() - INTERVAL '${gun}' DAY
    GROUP BY gun, sayfa, ulke, ag, tarayici, istekTuru
    LIMIT 100000
    FORMAT JSON`
}
