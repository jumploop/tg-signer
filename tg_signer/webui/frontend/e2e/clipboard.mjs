/**
 * 复制功能回归测试。
 *
 * 背景：navigator.clipboard 只在安全上下文（HTTPS / localhost）存在。通过局域网
 * IP 以 HTTP 访问 WebUI 时它是 undefined，直接调用 writeText 会抛 TypeError，
 * 表现为「复制失败，请手动复制」。api.js 的 copyText() 为此提供 execCommand
 * 降级路径，这里同时覆盖两条分支。
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
const CHAT_ID = '-1001234567890'

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
}

const STUB_API = {
  '/api/auth/status': { required: false, locked_until: 0 },
  '/api/state': { workdir: '/tmp/e2e', log_path: '/tmp/e2e/logs/tg-signer.log' },
  '/api/accounts': [],
  '/api/chats': [
    {
      id: CHAT_ID,
      title: '回归测试群组',
      type: 'supergroup',
      username: null,
      account: 'demo_account',
    },
  ],
}

function startServer() {
  const server = createServer(async (req, res) => {
    const path = new URL(req.url, 'http://localhost').pathname

    if (path in STUB_API) {
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify(STUB_API[path]))
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

// 记录两条复制路径各自收到的文本，用来断言走的是哪条分支。
function initScript(secureContext) {
  const clipboard =
    secureContext
      ? `{ writeText: (t) => { window.__viaClipboard.push(t); return Promise.resolve(); } }`
      : 'undefined'
  return `(() => {
    window.__viaClipboard = [];
    window.__viaExecCommand = [];

    Object.defineProperty(window, 'isSecureContext', {
      get: () => ${secureContext},
      configurable: true,
    });
    Object.defineProperty(navigator, 'clipboard', {
      get: () => (${clipboard}),
      configurable: true,
    });

    const original = document.execCommand.bind(document);
    document.execCommand = function (command) {
      if (command === 'copy') {
        const el = document.activeElement;
        window.__viaExecCommand.push(el && 'value' in el ? el.value : null);
        return true;
      }
      return original(command);
    };
  })();`
}

const SCENARIOS = [
  {
    name: '安全上下文走 navigator.clipboard',
    secureContext: true,
    expect: { viaClipboard: [CHAT_ID], viaExecCommand: [] },
  },
  {
    name: '非安全上下文降级到 execCommand',
    secureContext: false,
    expect: { viaClipboard: [], viaExecCommand: [CHAT_ID] },
  },
]

async function run() {
  const { server, port } = await startServer()
  const browser = await chromium.launch({
    channel: 'chrome',
    headless: true,
  })

  const failures = []
  try {
    for (const scenario of SCENARIOS) {
      const context = await browser.newContext()
      await context.addInitScript(initScript(scenario.secureContext))
      const page = await context.newPage()
      const pageErrors = []
      page.on('pageerror', (error) => pageErrors.push(error.message))

      await page.goto(`http://127.0.0.1:${port}/#/chats`, { waitUntil: 'networkidle' })
      const button = page.locator('button', { hasText: '复制ID' }).first()
      await button.waitFor({ state: 'visible', timeout: 15000 })
      await button.click()

      // 页面上可能同时挂着「已读取缓存」等旧提示，这里只认带「已复制」的那条。
      const toast = page.locator('.el-message', { hasText: '已复制' })
      await toast.first().waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
      const toastText = (await toast.first().textContent().catch(() => null)) ?? null
      const viaClipboard = await page.evaluate(() => window.__viaClipboard)
      const viaExecCommand = await page.evaluate(() => window.__viaExecCommand)

      const problems = []
      if (JSON.stringify(viaClipboard) !== JSON.stringify(scenario.expect.viaClipboard)) {
        problems.push(`navigator.clipboard 收到 ${JSON.stringify(viaClipboard)}`)
      }
      if (JSON.stringify(viaExecCommand) !== JSON.stringify(scenario.expect.viaExecCommand)) {
        problems.push(`execCommand 收到 ${JSON.stringify(viaExecCommand)}`)
      }
      if (!toastText) {
        problems.push('未出现「已复制」成功提示')
      } else if (!toastText.includes(CHAT_ID)) {
        problems.push(`成功提示缺少 ID: ${JSON.stringify(toastText)}`)
      }
      if (pageErrors.length) {
        problems.push(`页面报错: ${pageErrors.join('; ')}`)
      }

      if (problems.length) {
        failures.push(`${scenario.name}: ${problems.join(' | ')}`)
        console.log(`FAIL  ${scenario.name}`)
        problems.forEach((p) => console.log(`        ${p}`))
      } else {
        console.log(`PASS  ${scenario.name}`)
      }
      await context.close()
    }
  } finally {
    await browser.close()
    server.close()
  }

  if (failures.length) {
    console.error(`\n${failures.length} 个场景失败`)
    process.exit(1)
  }
  console.log(`\n全部 ${SCENARIOS.length} 个场景通过`)
}

run().catch((error) => {
  console.error('测试执行失败:', error.message)
  process.exit(1)
})
