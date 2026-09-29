/**
 * 日志页默认选中文件的回归测试。
 *
 * 两次真实故障：
 * 1) 后端 list_log_files() 用 glob 而非 rglob，runner.py 写在
 *    logs/<kind>-<account>/tg-signer.log 的任务日志一个都列不出来；
 * 2) 顶层 tg-signer.log 靠 stdout 重定向写入，纯 CLI 签到时是 0 字节，
 *    按文件名排序会正好把它选成默认项，页面显示「暂无日志内容」。
 *
 * 现在后端按「非空优先 + mtime 倒序」返回，前端取第一个作为默认选中项，
 * 下拉框展示相对 logs/ 的路径（否则子目录日志和主日志同名，分不清）。
 *
 * 不依赖 Python：用内置静态服务托管已构建的 static/，并对 /api/* 返回桩数据。
 * 运行：npm run test:e2e
 */
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { extname, join, normalize } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const STATIC_DIR = fileURLToPath(new URL('../../static', import.meta.url))
const LOG_DIR = '/srv/workdir/logs'
const TASK_LOG = `${LOG_DIR}/signer-demo/tg-signer.log`
const TASK_LINES = ['task line 1', 'task line 2', 'task line 3']

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
}

// 后端已排好序：非空的任务日志排第一，0 字节的主日志排最后。
const LOG_FILES = [TASK_LOG, `${LOG_DIR}/error.log`, `${LOG_DIR}/tg-signer.log`]

const STUB_API = {
  '/api/auth/status': { required: false, locked_until: 0 },
  '/api/state': { workdir: '/srv/workdir', log_path: `${LOG_DIR}/tg-signer.log` },
}

function startServer() {
  const server = createServer(async (req, res) => {
    const url = new URL(req.url, 'http://localhost')
    const path = url.pathname

    if (path in STUB_API) {
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify(STUB_API[path]))
      return
    }

    if (path === '/api/logs/files') {
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ files: LOG_FILES }))
      return
    }

    if (path === '/api/logs') {
      const requested = url.searchParams.get('path') || `${LOG_DIR}/tg-signer.log`
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(
        JSON.stringify({
          path: requested,
          lines: requested === TASK_LOG ? TASK_LINES : [],
        }),
      )
      return
    }

    const rel = normalize(path === '/' ? '/index.html' : path).replace(/^([/\\])+/, '')
    try {
      const body = await readFile(join(STATIC_DIR, rel))
      res.writeHead(200, { 'Content-Type': MIME[extname(rel)] || 'application/octet-stream' })
      res.end(body)
    } catch {
      res.writeHead(404).end('not found')
    }
  })

  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve({ server, port: server.address().port }))
  })
}

const { server, port } = await startServer()
const browser = await chromium.launch({ channel: 'chrome' })

try {
  const page = await browser.newPage()
  await page.goto(`http://127.0.0.1:${port}/#/logs`, { waitUntil: 'networkidle' })
  await page.waitForSelector('textarea')
  await page.waitForFunction(() => document.querySelector('textarea').value.length > 0, null, {
    timeout: 10000,
  })

  const selected = (await page.locator('.log-file-select').innerText()).trim()
  const value = await page.locator('textarea').inputValue()

  // 默认选中应是有内容的任务子目录日志，而不是 0 字节的主日志。
  if (selected !== 'signer-demo/tg-signer.log') {
    throw new Error(`默认选中的应是非空任务日志 signer-demo/tg-signer.log，实际为: ${selected}`)
  }
  if (value !== TASK_LINES.join('\n')) {
    throw new Error(`日志内容未正确加载，实际为: ${JSON.stringify(value)}`)
  }

  // 下拉框展示相对 logs/ 的路径：主日志与子目录日志同名，只显示文件名会分不清。
  await page.locator('.log-file-select').click()
  const options = (await page.locator('.el-select-dropdown__item').allInnerTexts()).map((t) => t.trim())
  const expected = ['signer-demo/tg-signer.log', 'error.log', 'tg-signer.log']
  if (JSON.stringify(options) !== JSON.stringify(expected)) {
    throw new Error(`下拉框选项不符，期望 ${JSON.stringify(expected)}，实际 ${JSON.stringify(options)}`)
  }
  if (options.some((o) => o.includes('/srv/workdir'))) {
    throw new Error(`下拉框选项不应展示绝对路径: ${JSON.stringify(options)}`)
  }

  console.log(`OK 默认选中 ${selected}，内容 ${value.split('\n').length} 行，子目录日志可见`)
} finally {
  await browser.close()
  server.close()
}
