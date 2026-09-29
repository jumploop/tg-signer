/**
 * 日志页默认选中文件的回归测试。
 *
 * 历史问题：后端 list_log_files() 按文件名升序返回，前端取 files[files.length-1]
 * 作为默认选中项，恰好落到 warn.log 这类空文件上，页面一进来就显示「暂无日志
 * 内容」，看起来像日志功能整体失效。现改为优先选主日志 tg-signer.log。
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
const MAIN_LOG = ['line 1', 'line 2', 'line 3']

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
}

// 升序排列，warn.log 落在最后 —— 正是旧实现会误选中的那个空文件。
const LOG_FILES = ['error.log', 'run-2026-09-29.log', 'tg-signer.log', 'warn.log']

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
      res.end(JSON.stringify({ files: LOG_FILES.map((f) => `${LOG_DIR}/${f}`) }))
      return
    }

    if (path === '/api/logs') {
      const requested = url.searchParams.get('path') || `${LOG_DIR}/tg-signer.log`
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(
        JSON.stringify({
          path: requested,
          lines: requested.endsWith('tg-signer.log') ? MAIN_LOG : [],
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

  if (selected !== 'tg-signer.log') {
    throw new Error(`默认选中的应是主日志 tg-signer.log，实际为: ${selected}`)
  }
  if (value !== MAIN_LOG.join('\n')) {
    throw new Error(`日志内容未正确加载，实际为: ${JSON.stringify(value)}`)
  }

  // 下拉框应展示文件名而不是完整绝对路径。
  await page.locator('.log-file-select').click()
  const options = await page.locator('.el-select-dropdown__item').allInnerTexts()
  if (options.some((o) => o.includes('/'))) {
    throw new Error(`下拉框选项不应展示完整路径: ${JSON.stringify(options)}`)
  }

  console.log(`OK 默认选中 ${selected}，内容 ${value.split('\n').length} 行，下拉框仅显示文件名`)
} finally {
  await browser.close()
  server.close()
}
