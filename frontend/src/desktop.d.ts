export interface UpdateState {
  status: 'idle' | 'checking' | 'available' | 'up-to-date' | 'downloading' | 'downloaded' | 'error' | 'unsupported'
  currentVersion: string
  latestVersion?: string
  releaseName?: string
  releaseNotes?: string
  progress?: number
  error?: string
}

export interface AppInfo {
  version: string
  packaged: boolean
  canUpdate: boolean
}

export interface DesktopBridge {
  getAppInfo(): Promise<AppInfo>
  getUpdateState(): Promise<UpdateState>
  checkForUpdates(): Promise<UpdateState>
  downloadUpdate(): Promise<UpdateState>
  installUpdate(): Promise<{ ok: boolean }>
  onUpdateState(callback: (state: UpdateState) => void): () => void
}

declare global {
  interface Window {
    videomind?: DesktopBridge
  }
}

export {}
