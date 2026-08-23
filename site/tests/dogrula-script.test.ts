// site/tests/dogrula-script.test.ts
//
// scripts/dogrula.ts, hepsiniDogrula'yı doğrudan diskten okunan içerik
// üzerinde koşan komut satırı script'idir; `npm run build` bu script
// başarısız olursa astro build'i hiç çalıştırmaz. Birim testleri
// hepsiniDogrula'nın saf mantığını doğruluyor; bu test ise script'in asıl
// işini yaptığını — gerçekten sıfırdan farklı bir çıkış koduyla
// başarısız olduğunu ve hatada eksik terimin adını gösterdiğini — kanıtlar.
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SITE_KOKU = fileURLToPath(new URL('..', import.meta.url))
const SCRIPT = fileURLToPath(new URL('../scripts/dogrula.ts', import.meta.url))
// npx + shell yerine tsx'in CLI giriş noktasını doğrudan node ile çalıştır:
// hem shell kaçış sorunlarından kaçınır hem de Windows'ta güvenilir çalışır.
const TSX_CLI = fileURLToPath(new URL('../node_modules/tsx/dist/cli.mjs', import.meta.url))

type CalistirmaSonucu = { kod: number; cikti: string }

function scriptiCalistir(icerikKoku: string): CalistirmaSonucu {
  try {
    const cikti = execFileSync(process.execPath, [TSX_CLI, SCRIPT, icerikKoku], {
      cwd: SITE_KOKU,
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    return { kod: 0, cikti }
  } catch (hata) {
    const e = hata as { status: number | null; stdout: string; stderr: string }
    return { kod: e.status ?? 1, cikti: `${e.stdout ?? ''}${e.stderr ?? ''}` }
  }
}

describe('scripts/dogrula.ts', () => {
  it('bozuk fixture içeriğinde sıfırdan farklı çıkış koduyla başarısız olur', () => {
    const sonuc = scriptiCalistir('tests/fixtures/bozuk-icerik')
    expect(sonuc.kod).not.toBe(0)
    expect(sonuc.cikti).toMatch(/raf-omru/)
  })

  it('gerçek içerikte sıfır çıkış koduyla başarılı olur', () => {
    const sonuc = scriptiCalistir('src/content')
    expect(sonuc.kod).toBe(0)
    expect(sonuc.cikti).toMatch(/İçerik doğrulandı/)
  })

  // Kritik gözden geçirme bulgusu: var olmayan ya da boş bir içerik kökü,
  // sessizce "0 hata" (dolayısıyla exit 0) döndürüp doğrulamanın hiç
  // koşmadığını gizleyebiliyordu. Bu iki test o davranışı kilitler.
  it('var olmayan bir kökte sıfırdan farklı çıkış koduyla başarısız olur', () => {
    const sonuc = scriptiCalistir('tests/fixtures/yok-boyle-bir-dizin')
    expect(sonuc.kod).not.toBe(0)
    expect(sonuc.cikti).toMatch(/yok-boyle-bir-dizin/)
    expect(sonuc.cikti).toMatch(/bulunamadı/i)
  })

  it('var olan ama boş bir kökte sıfırdan farklı çıkış koduyla başarısız olur', () => {
    const sonuc = scriptiCalistir('tests/fixtures/bos-icerik')
    expect(sonuc.kod).not.toBe(0)
    expect(sonuc.cikti).toMatch(/bos-icerik/)
    expect(sonuc.cikti).toMatch(/0 yazı, 0 terim/)
  })
})
