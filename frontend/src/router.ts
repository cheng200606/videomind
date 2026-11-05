import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'library', component: () => import('./views/LibraryView.vue'), meta: { title: '视频库' } },
  { path: '/upload', name: 'upload', component: () => import('./views/UploadView.vue'), meta: { title: '批量上传' } },
  { path: '/batches/:id', name: 'progress', component: () => import('./views/BatchProgressView.vue'), meta: { title: '批次进度' } },
  { path: '/videos/:id', name: 'workbench', component: () => import('./views/WorkbenchView.vue'), meta: { title: '知识工作台' } },
  { path: '/notes/:id', name: 'notes', component: () => import('./views/NotesView.vue'), meta: { title: '笔记' } },
  { path: '/batches/:id/export', name: 'export', component: () => import('./views/ExportView.vue'), meta: { title: '导出' } }
]

export default createRouter({ history: createWebHistory(), routes })
