// VideoMind 桌面壳：选空闲端口 → 拉起 PyInstaller 后端 sidecar → 健康探测 → 开窗口。
// 打包态从 resources/backend 拉后端；开发态直接用 backend/dist 里的产物，方便联调。

const { app, BrowserWindow, dialog, ipcMain } = require('electron')
const { spawn } = require('child_process')
const fs = require('fs')
const http = require('http')
const net = require('net')
const path = require('path')

const isDev = !app.isPackaged
const UPDATE_URL = process.env.VMIND_UPDATE_URL || ''
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

// ── 更新器：设置页“检查更新”走这里；发现新版本后由用户决定下载/重启安装 ──
let autoUpdater = null
let updateState = { status: 'idle', currentVersion: app.getVersion() }

function emitUpdate(patch) {
  updateState = { ...updateState, ...patch, currentVersion: app.getVersion() }
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('update:state', updateState)
  }
  return updateState
}

function updateErrorText(err) {
  const text = err && err.message ? err.message : String(err)
  return text.replace(/\s+/g, ' ').slice(0, 500)
}

function updateNotes(notes) {
  if (!notes) return ''
  const text = Array.isArray(notes)
    ? notes.map((n) => (typeof n === 'string' ? n : n && n.note ? n.note : '')).join('\n')
    : typeof notes === 'string' ? notes : JSON.stringify(notes)
  return text.slice(0, 4000)
}

function initUpdater() {
  if (!app.isPackaged && !UPDATE_URL) return null
  try {
    const { autoUpdater: au } = require('electron-updater')
    autoUpdater = au
    autoUpdater.autoDownload = false
    autoUpdater.autoInstallOnAppQuit = true
    autoUpdater.allowPrerelease = false
    autoUpdater.allowDowngrade = false
    autoUpdater.logger = {
      info: (m) => log('updater.log', `info ${m}`),
      warn: (m) => log('updater.log', `warn ${m}`),
      error: (m) => log('updater.log', `error ${m}`),
      debug: () => {}
    }

    if (!app.isPackaged) {
      // 开发态联调：VMIND_UPDATE_URL 指向一个 generic 更新源（目录里放 latest.yml）
      autoUpdater.forceDevUpdateConfig = true
      const cfg = path.join(app.getPath('userData'), 'dev-app-update.yml')
      fs.writeFileSync(cfg, `provider: generic\nurl: ${UPDATE_URL}\n`, 'utf-8')
      autoUpdater.updateConfigPath = cfg
      log('updater.log', `dev update url=${UPDATE_URL}`)
    }

    autoUpdater.on('checking-for-update', () => emitUpdate({ status: 'checking', error: '' }))
    autoUpdater.on('update-available', (info) => emitUpdate({
      status: 'available',
      latestVersion: info && info.version,
      releaseName: info && info.releaseName,
      releaseNotes: updateNotes(info && info.releaseNotes)
    }))
    autoUpdater.on('update-not-available', (info) => emitUpdate({
      status: 'up-to-date', latestVersion: info && info.version, error: ''
    }))
    autoUpdater.on('download-progress', (p) => emitUpdate({
      status: 'downloading', progress: Math.round(p && p.percent ? p.percent : 0)
    }))
    autoUpdater.on('update-downloaded', (info) => emitUpdate({
      status: 'downloaded', latestVersion: info && info.version, progress: 100
    }))
    autoUpdater.on('error', (err) => emitUpdate({ status: 'error', error: updateErrorText(err) }))
    return autoUpdater
  } catch (err) {
    log('updater.log', `updater init failed ${err}`)
    return null
  }
}

async function checkForUpdates() {
  if (!autoUpdater) {
    return emitUpdate({
      status: 'unsupported',
      error: '当前构建未启用自动更新（浏览器模式或未配置更新源的开发模式）'
    })
  }
  emitUpdate({ status: 'checking', error: '' })
  try {
    const result = await autoUpdater.checkForUpdates()
    const latest = result && result.updateInfo ? result.updateInfo.version : ''
    if (updateState.status === 'checking') {
      // 正常情况下 electron-updater 已发出 available/not-available；这里只兜底
      const newer = latest && latest !== app.getVersion()
      emitUpdate({ status: newer ? 'available' : 'up-to-date', latestVersion: latest })
    }
  } catch (err) {
    emitUpdate({ status: 'error', error: updateErrorText(err) })
  }
  return updateState
}

ipcMain.handle('app:info', () => ({
  version: app.getVersion(),
  packaged: app.isPackaged,
  canUpdate: !!autoUpdater
}))
ipcMain.handle('update:state', () => updateState)
ipcMain.handle('update:check', () => checkForUpdates())
ipcMain.handle('update:download', async () => {
  if (!autoUpdater) return emitUpdate({ status: 'unsupported', error: '当前构建未启用自动更新' })
  if (updateState.status !== 'available') return updateState
  try {
    emitUpdate({ status: 'downloading', progress: 0, error: '' })
    await autoUpdater.downloadUpdate()
  } catch (err) {
    emitUpdate({ status: 'error', error: updateErrorText(err) })
  }
  return updateState
})
ipcMain.handle('update:install', () => {
  if (!autoUpdater || updateState.status !== 'downloaded') return { ok: false }
  // 退出应用并运行已下载的安装程序，安装完成后自动拉起新版本；before-quit 会停 sidecar
  autoUpdater.quitAndInstall(false, true)
  return { ok: true }
})

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
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, 'preload.js')
    }
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
    initUpdater()
    await createWindow()

    if (autoUpdater) {
      // 启动后静默查一次，让设置页直接显示是否有新版本；下载仍由用户点击触发
      setTimeout(() => { checkForUpdates().catch((err) => log('updater.log', `startup check ${err}`)) }, 1500)
    }
  })

  app.on('window-all-closed', () => {
    stopBackend()
    app.quit()
  })

  app.on('before-quit', stopBackend)

  process.on('exit', stopBackend)
}
