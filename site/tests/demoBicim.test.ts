// site/tests/demoBicim.test.ts
//
// Demo kartlarındaki sayının biçimi. Bileşen değeri `toLocaleString('tr-TR')`
// ile basıyordu; bu, Mağaza Gruplama demosunda ARI 1.0'ı "1", kararlılık
// 0.97'yi "0,97" gösteriyordu, oysa rapor ve yazılar bu ölçütleri üç
// ondalıkla basar ("1,000", "0,970"). Ondalık sayısı ölçüt başına bir
// sözlükten gelir; sözlükte olmayan ölçütler eskisi gibi basılır, öteki
// dizilerin demoları değişmez.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { demoDegeri } from '../src/lib/demoBicim'

describe('demoDegeri', () => {
  it('kümeleme ölçütlerini üç ondalıkla basar', () => {
    expect(demoDegeri('hakem_ari', 1)).toBe('1,000')
    expect(demoDegeri('hakem_ari', 0.022)).toBe('0,022')
    expect(demoDegeri('siluet', 0.308)).toBe('0,308')
    expect(demoDegeri('siluet', 0.27)).toBe('0,270')
    expect(demoDegeri('kararlilik', 0.97)).toBe('0,970')
  })

  it('beden ve koli ölçütlerini raporun basamağıyla basar', () => {
    // Rapor ilk 4 hafta yüzdelerini bir ondalıkla (%97,0 gibi sıfırlı da),
    // brüt kârı tam TL olarak basar; sıfır ondalık "97" olarak düşmemeli.
    expect(demoDegeri('bulunabilirlik_ilk4', 96.5)).toBe('96,5')
    expect(demoDegeri('bulunabilirlik_ilk4', 97)).toBe('97,0')
    expect(demoDegeri('beden_kayip_payi_ilk4', 58.4)).toBe('58,4')
    expect(demoDegeri('kirik_cift_pay_yuzde_ilk4', 2)).toBe('2,0')
    expect(demoDegeri('brut_kar_tl', 535940376)).toBe('535.940.376')
  })

  it('indirim takvimi ölçütlerini bir ondalıkla basar, eksi sıfırı düşürür', () => {
    // Rapor milyon TL, bin adet ve yüzdeleri bir ondalıkla basar; 82.0 "82"
    // olarak düşmemeli, yuvarlanınca sıfır olan fark "-0,0" görünmemeli.
    expect(demoDegeri('olu_stok_bin', 4.3)).toBe('4,3')
    expect(demoDegeri('markdown_mtl', 14)).toBe('14,0')
    expect(demoDegeri('son_str', 82)).toBe('82,0')
    expect(demoDegeri('katki_farki_mtl', 0.5)).toBe('0,5')
    expect(demoDegeri('katki_farki_mtl', -0.2)).toBe('-0,2')
    expect(demoDegeri('katki_farki_mtl', 0)).toBe('0,0')
    expect(demoDegeri('katki_farki_mtl', -0)).toBe('0,0')
  })

  it('sözlükte olmayan ölçütü eskisi gibi basar', () => {
    for (const [olcut, deger] of [
      ['en_kucuk_kume', 7],
      ['bulunabilirlik', 69.51],
      ['net_kar_tl', 1234567],
      ['tam_fiyat_str', 52.7],
      ['sure_sn', 0.5],
    ] as const) {
      expect(demoDegeri(olcut, deger), olcut).toBe(deger.toLocaleString('tr-TR'))
    }
  })

  it('Demo.astro değeri bu biçimleyiciyle basar', () => {
    const kaynak = readFileSync(
      fileURLToPath(new URL('../src/components/Demo.astro', import.meta.url)),
      'utf8',
    )
    expect(kaynak).toContain('demoDegeri(olcut, sonuclar[anahtar].ozet[olcut])')
    expect(kaynak).not.toContain(".toLocaleString('tr-TR')")
  })
})
