// site/tests/harita.test.ts
//
// Lumtify planlama haritası tek kaynaklı veri dosyasının şeklini doğrular:
// üç faz, on beş aşama, otuz dört algoritma; numaralar kesintisiz; slug ve
// kimlikler tekil ve URL güvenli (spec §0.1 madde 8 ve 10).
import { describe, expect, it } from 'vitest'
import {
  algoritmaBul,
  asamaBul,
  AYRILMIS_KOK_ADLAR,
  HARITA,
  TEMELLER,
} from '../src/data/harita'

const SLUG_SEKLI = /^[a-z0-9]+(-[a-z0-9]+)*$/

describe('HARITA', () => {
  it('üç faz, on beş aşama, otuz dört algoritma', () => {
    expect(HARITA.map((f) => f.slug)).toEqual(['sezon-oncesi', 'sezon-ici', 'diger-surecler'])
    expect(HARITA.map((f) => f.ad)).toEqual(['Sezon Öncesi', 'Sezon İçi', 'Diğer Süreçler'])
    expect(HARITA.map((f) => f.asamalar.length)).toEqual([6, 5, 4])

    const algoritmaSayisi = (faz: (typeof HARITA)[number]) =>
      faz.asamalar.reduce((toplam, a) => toplam + a.algoritmalar.length, 0)
    expect(HARITA.map(algoritmaSayisi)).toEqual([10, 9, 15])
    expect(HARITA.map(algoritmaSayisi).reduce((t, n) => t + n, 0)).toBe(34)
  })

  it("aşama numaraları üç faz boyunca 1'den 15'e kesintisiz", () => {
    const numaralar = HARITA.flatMap((f) => f.asamalar.map((a) => a.no))
    expect(numaralar).toEqual(Array.from({ length: 15 }, (_, i) => i + 1))
  })

  it('aşamalar spec §0.1 madde 8 sırasıyla fazlara dağılır', () => {
    expect(HARITA.map((f) => f.asamalar.map((a) => a.slug))).toEqual([
      ['mfp', 'range-plan', 'urun-stratejileri', 'koleksiyon', 'assortment', 'magaza-kumeleme'],
      ['allocation', 'replenishment', 'rpt', 'transfer', 'indirim'],
      ['tedarik', 'is-zekasi', 'depo-lojistik', 'crm'],
    ])
  })

  it('algoritma listesi spec §0.1 madde 10 revizyonunu taşır', () => {
    const algoritmalar = (slug: string) => asamaBul(slug)!.asama.algoritmalar
    expect(algoritmalar('rpt')).toEqual([
      { id: 'rpt-gereksinim-adet', ad: 'RPT gereksinim tahminleme ve adet hesaplama' },
    ])
    expect(algoritmalar('transfer')).toEqual([
      { id: 'blok-transfer', ad: 'Blok transfer' },
      { id: 'tekleme-transfer', ad: 'Tekleme transfer' },
      { id: 'acma-kapama-transferi', ad: 'Mağaza açma-kapama transferi' },
    ])
    expect(algoritmalar('tedarik')).toEqual([
      { id: 'tedarikci-performans-secim', ad: 'Tedarikçi performans ve seçim öneri sistemi' },
    ])
    const crm = algoritmalar('crm').map((a) => a.id)
    expect(crm).toHaveLength(6)
    expect(crm).not.toContain('dinamik-fiyatlama')
    expect(crm).not.toContain('kampanya-kitle')
    for (const eski of ['rpt-gereksinim', 'rpt-adet', 'blok-tekleme-kiriklik', 'transfer-optimizasyonu', 'acma-kapama', 'tedarikci-performans', 'tedarikci-secim']) {
      expect(algoritmaBul(eski), eski).toBeUndefined()
    }
  })

  it("aşama slug'ları ve algoritma kimlikleri tekil", () => {
    const asamaSluglari = HARITA.flatMap((f) => f.asamalar.map((a) => a.slug))
    expect(new Set(asamaSluglari).size).toBe(asamaSluglari.length)

    const algoritmaKimlikleri = HARITA.flatMap((f) =>
      f.asamalar.flatMap((a) => a.algoritmalar.map((alg) => alg.id)),
    )
    expect(new Set(algoritmaKimlikleri).size).toBe(algoritmaKimlikleri.length)
  })

  it('hiçbir aşama ayrılmış bir kök adı kullanmaz', () => {
    expect(AYRILMIS_KOK_ADLAR).toEqual([
      'sezon-oncesi',
      'sezon-ici',
      'diger-surecler',
      'temeller',
      'sozluk',
      'kadro',
      'veri-seti',
    ])
    const asamaSluglari = HARITA.flatMap((f) => f.asamalar.map((a) => a.slug))
    const kesisim = asamaSluglari.filter((s) => AYRILMIS_KOK_ADLAR.includes(s))
    expect(kesisim).toEqual([])
  })

  it('slug ve kimlikler küçük harf, ascii, tireli', () => {
    for (const faz of HARITA) {
      for (const asama of faz.asamalar) {
        expect(asama.slug).toMatch(SLUG_SEKLI)
        for (const algoritma of asama.algoritmalar) {
          expect(algoritma.id).toMatch(SLUG_SEKLI)
        }
      }
    }
  })

  it("asamaBul('rpt') RPT aşamasını sezon-ici fazında bulur", () => {
    const sonuc = asamaBul('rpt')
    expect(sonuc?.faz.slug).toBe('sezon-ici')
    expect(sonuc?.asama.ad).toBe('RPT')
    expect(sonuc?.asama.no).toBe(9)
  })

  it("asamaBul('tedarik') Tedarik aşamasını diger-surecler fazında bulur", () => {
    const sonuc = asamaBul('tedarik')
    expect(sonuc?.faz.slug).toBe('diger-surecler')
    expect(sonuc?.asama.no).toBe(12)
  })

  it("asamaBul('yok') tanımsız döner", () => {
    expect(asamaBul('yok')).toBeUndefined()
  })

  it("algoritmaBul('yasam-egrisi') range-plan aşamasında bulunur", () => {
    const sonuc = algoritmaBul('yasam-egrisi')
    expect(sonuc?.asama.slug).toBe('range-plan')
  })

  it('adlar spec §2 ile birebir', () => {
    expect(asamaBul('allocation')!.asama.ad).toBe('Allocation — ilk sevkiyat')
    expect(asamaBul('transfer')!.asama.ad).toBe('Mağazalar arası transfer')
  })

  it('TEMELLER harita dışı sabit bir alan adıdır', () => {
    expect(TEMELLER).toBe('temeller')
  })
})
