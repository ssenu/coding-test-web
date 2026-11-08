import { createRouter, createWebHistory } from 'vue-router'
import { adminApi } from './lib/api'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/admin/login', component: () => import('./views/admin/LoginView.vue') },
    { path: '/admin', component: () => import('./views/admin/TemplatesView.vue'), meta: { admin: true } },
    {
      path: '/admin/templates/:id',
      component: () => import('./views/admin/EditorView.vue'),
      meta: { admin: true },
    },
    { path: '/admin/runs/:id', component: () => import('./views/admin/RunView.vue'), meta: { admin: true } },
    {
      path: '/admin/runs/:id/result',
      component: () => import('./views/admin/ResultView.vue'),
      meta: { admin: true },
    },
  ],
})

router.beforeEach(async (to) => {
  if (!to.meta.admin) return true
  try {
    await adminApi.me()
    return true
  } catch {
    return { path: '/admin/login', query: { next: to.fullPath } }
  }
})
