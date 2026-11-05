// VideoMind 桌面壳：选空闲端口 → 拉起 PyInstaller 后端 sidecar → 健康探测 → 开窗口。
// 打包态从 resources/backend 拉后端；开发态直接用 backend/dist 里的产物，方便联调。

const { app, BrowserWindow, dialog } = require('electron')
const { spawn } = require('child_process')
const fs = require('fs')
const http = require('http')
const net = require('net')
const path = require('path')

const isDev = !app.isPackaged
const BACKEND_EXE = isDev
  ? path.join(__dirname, '..', 'backend', 'dist', 'VideoMindBackend', 'VideoMindBackend.exe')
  : path.join(process.resourcesPath, 'backend', 'VideoMindBackend.exe')
const DATA_DIR = path.join(app.getPath('appData'), 'VideoMind', 'data')
const LOG_DIR = path.join(DATA_DIR, 'logs')

fs.mkdirSync(LOG_DIR, { recursive: true })

function log(file, line) {
  fs.appendFileSync(path.join(LOG_DIR, file), `[${new Date().toISOString()}] ${line}\n`)
}

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer()
    srv.listen(0, '127.0.0.1', () => {
      const port = srv.address().port
      srv.close(() => resolve(port))
    })
    srv.on('error', reject)
  })
}

function waitHealth(port, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs
  return new Promise((resolve, reject) => {
    const tick = () => {
      const req = http.get(`http://127.0.0.1:${port}/api/health`, { timeout: 2000 }, (res) => {
        res.resume()
        if (res.statusCode === 200) return resolve()
        retry()
      })
      req.on('error', retry)
      req.on('timeout', () => { req.destroy(); retry() })
    }
    const retry = () => {
      if (Date.now() > deadline) return reject(new Error(`后端健康探测超时（端口 ${port}）`))
      setTimeout(tick, 400)
    }
    tick()
  })
}

let backendProc = null
let mainWindow = null

function startBackend(port) {
  if (!fs.existsSync(BACKEND_EXE)) {
    throw new Error(`后端可执行文件不存在：${BACKEND_EXE}（先跑 backend 的 PyInstaller 打包）`)
  }
  backendProc = spawn(BACKEND_EXE, [], {
    cwd: DATA_DIR,
    env: { ...process.env, VMIND_PORT: String(port), VMIND_DATA_DIR: DATA_DIR, PYTHONUNBUFFERED: '1' },
    windowsHide: true
  })
  backendProc.stdout.on('data', (d) => log('backend.log', String(d).trim()))
  backendProc.stderr.on('data', (d) => log('backend.log', String(d).trim()))
  backendProc.on('exit', (code) => log('backend.log', `backend exited code=${code}`))
}

function stopBackend() {
  if (backendProc) {
    try { backendProc.kill() } catch { /* 已退出则忽略 */ }
    backendProc = null
  }
}

async function createWindow() {
  const port = await freePort()
  try {
    startBackend(port)
    await waitHealth(port)
    log('app.log', `backend ready on port ${port}`)
  } catch (err) {
    log('app.log', `backend failed: ${err}`)
    dialog.showErrorBox('VideoMind 启动失败', String(err))
    app.quit()
    return
  }

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    show: false,
    autoHideMenuBar: true,
    title: `VideoMind 视析 v${app.getVersion()}`,
    webPreferences: { contextIsolation: true }
  })
  mainWindow.once('ready-to-show', () => mainWindow.show())
  mainWindow.on('closed', () => { mainWindow = null })
  await mainWindow.loadURL(`http://127.0.0.1:${port}/`)
}

// 单实例锁：更新器装完新版本重启时避免双开
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.focus()
    }
  })

  app.whenReady().then(async () => {
    await createWindow()

    if (app.isPackaged) {
      // 自动更新走 GitHub Releases（electron-builder 的 publish 配置）；失败只记日志，不打断使用
      try {
        const { autoUpdater } = require('electron-updater')
        autoUpdater.autoDownload = true
        autoUpdater.autoInstallOnAppQuit = true
        autoUpdater.on('checking-for-update', () => log('updater.log', 'checking-for-update'))
        autoUpdater.on('update-available', (i) => log('updater.log', `update-available version=${i && i.version}`))
        autoUpdater.on('update-not-available', (i) => log('updater.log', `update-not-available version=${i && i.version}`))
        autoUpdater.on('download-progress', (p) => {
          if (Math.floor(p.percent) % 10 === 0) log('updater.log', `download-progress ${Math.floor(p.percent)}%`)
        })
        autoUpdater.on('update-downloaded', (i) => {
          log('updater.log', `update-downloaded version=${i && i.version}，退出应用后自动安装`)
        })
        autoUpdater.on('error', (err) => log('updater.log', `error ${err}`))
        autoUpdater.checkForUpdatesAndNotify().catch((err) => log('updater.log', `check failed ${err}`))
      } catch (err) {
        log('updater.log', `updater init failed ${err}`)
      }
    }
  })

  app.on('window-all-closed', () => {
    stopBackend()
    app.quit()
  })

  app.on('before-quit', stopBackend)

  process.on('exit', stopBackend)
}
