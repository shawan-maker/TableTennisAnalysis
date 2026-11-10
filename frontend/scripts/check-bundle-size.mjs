/**
 * FS8-8/FS8-9 bundle 体积门控（总览 §3.9 / 实施计划 §6.3 第 6 步）
 *
 * weapp 编译产物总大小 ≤ 8MB（微信整包上限）；主包 ≤ 2MB 由微信开发者
 * 工具上传时校验（FS8-9 实测记录）。CI 在 build:weapp 后执行本脚本。
 *
 * 用法：node scripts/check-bundle-size.mjs [dist 目录=dist]
 */
import { readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const LIMIT_MB = 8
const target = process.argv[2] ?? 'dist'

function dirSize(dir) {
  let total = 0
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name)
    if (entry.isDirectory()) total += dirSize(p)
    else total += statSync(p).size
  }
  return total
}

let bytes
try {
  bytes = dirSize(target)
} catch (err) {
  console.error(`[bundle-size] 读取目录失败: ${target}（先执行 npm run build:weapp）`)
  console.error(String(err))
  process.exit(2)
}

const mb = bytes / 1024 / 1024
console.log(`[bundle-size] ${target}: ${mb.toFixed(2)} MB（门控 ${LIMIT_MB} MB）`)

if (mb > LIMIT_MB) {
  console.error('[bundle-size] 超标——按总览 §3.9 拆分包或按需引入后重试')
  process.exit(1)
}
