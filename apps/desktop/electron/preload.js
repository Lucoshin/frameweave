export function createDesktopApi(ipcRenderer) {
  return {
    chooseVideoFiles: () => ipcRenderer.invoke('video:choose-files'),
    chooseOutputDirectory: () => ipcRenderer.invoke('video:choose-output-directory'),
    startVideoJob: (request) => ipcRenderer.invoke('video:start-job', request),
    cancelVideoJob: (jobId) => ipcRenderer.invoke('video:cancel-job', jobId),
    onVideoJobEvent: (callback) => {
      if (typeof callback !== 'function') throw new TypeError('视频任务事件回调必须是函数')
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('video:job-event', listener)
      return () => ipcRenderer.removeListener('video:job-event', listener)
    },

    chooseWordWorkflow: () => ipcRenderer.invoke('workflow:choose-word'),
    generateWordBatch: (payload) => ipcRenderer.invoke('workflow:generate-word', payload),
  }
}

export function exposeDesktopApi({ contextBridge, ipcRenderer }) {
  contextBridge.exposeInMainWorld('matrixDesktop', createDesktopApi(ipcRenderer))
}

if (process.versions.electron) {
  const electron = await import('electron')
  const { contextBridge, ipcRenderer } = electron.default ?? electron
  exposeDesktopApi({ contextBridge, ipcRenderer })
}
