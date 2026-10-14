import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { extname, join, normalize } from 'node:path'
import { fileURLToPath } from 'node:url'

const STATIC_DIR = fileURLToPath(new URL('../../static', import.meta.url))
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
}

export async function startServer({ stubs = {}, routes = {} } = {}) {
  const server = createServer(async (req, res) => {
    const url = new URL(req.url, 'http://localhost')
    const path = url.pathname

    if (path in stubs) {
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify(stubs[path]))
      return
    }

    if (path in routes) {
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify(await routes[path](url)))
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