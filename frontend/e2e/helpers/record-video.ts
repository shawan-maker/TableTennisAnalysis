/**
 * E2E 视频样本生成（FS8）
 * headless 环境无 ffmpeg/样本视频，且 Taro H5 chooseVideo 的 loadMedia 会真实
 * 解析视频元数据（<video> oncanplay）——假字节无法通过。故用 canvas +
 * MediaRecorder 在页面内现场生成最小真实 webm（约 0.5KB，VP8 编码），
 * oncanplay 实测可触发（probe-recorder 实证 2026-11-09）。
 */
import type { Page } from '@playwright/test'

export interface SampleVideo {
  name: string
  mimeType: string
  buffer: Buffer
}

/** 在页面内生成最小真实 webm（约 0.5KB；160×120，~0.5s） */
export async function recordSampleVideo(page: Page): Promise<SampleVideo> {
  const b64 = await page.evaluate(async () => {
    const canvas = document.createElement('canvas')
    canvas.width = 160
    canvas.height = 120
    const ctx = canvas.getContext('2d')!
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, 160, 120)
    const stream = canvas.captureStream(10)
    const mimes = ['video/webm;codecs=vp8', 'video/webm;codecs=vp9', 'video/webm']
    const mime = mimes.find((m) => MediaRecorder.isTypeSupported(m))
    if (!mime) throw new Error('MediaRecorder: no supported webm mime')
    const rec = new MediaRecorder(stream, { mimeType: mime })
    const chunks: Blob[] = []
    rec.ondataavailable = (e) => e.data.size > 0 && chunks.push(e.data)
    const done = new Promise<void>((res) => (rec.onstop = () => res()))
    rec.start()
    await new Promise((r) => setTimeout(r, 500))
    rec.stop()
    await done
    const blob = new Blob(chunks, { type: mime })
    const buf = await blob.arrayBuffer()
    const bytes = new Uint8Array(buf)
    let binary = ''
    const CHUNK = 0x8000
    for (let i = 0; i < bytes.length; i += CHUNK)
      binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK))
    return { mime, b64: btoa(binary) }
  })
  const bin = Buffer.from(b64.b64, 'base64')
  return { name: 'match.webm', mimeType: 'video/webm', buffer: bin }
}
