// site/tests/harita.test.ts
//
// Lumtify planlama haritası tek kaynaklı veri dosyasının şeklini doğrular:
// iki faz, on beş aşama, otuz sekiz algoritma; numaralar kesintisiz; slug ve
// kimlikler tekil ve URL güvenli; kalıcı slug'lar Lumtify sırasıyla eşleşir.
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
  it('iki faz, on beş aşama, otuz sekiz algoritma', () => {
    expect(HARITA.map((f) => f.slug)).toEqual(['sezon-oncesi', 'sezon-ici'])
    expect(HARITA.map((f) => f.ad)).toEqual(['Sezon Öncesi', 'Sezon İçi'])
    expect(HARITA.map((f) => f.asamalar.length)).toEqual([7, 8])

    const algoritmaSayisi = (faz: (typeof HARITA)[number]) =>
      faz.asamalar.reduce((toplam, a) => toplam + a.algoritmalar.length, 0)
    expect(HARITA.map(algoritmaSayisi)).toEqual([12, 26])
  })

  it("aşama numaraları 1'den 15'e kesintisiz", () => {
    const numaralar = HARITA.flatMap((f) => f.asamalar.map((a) => a.no))
    expect(numaralar).toEqual(Array.from({ length: 15 }, (_, i) => i + 1))
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
    expect(sonuc?.asama.no).toBe(10)
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
