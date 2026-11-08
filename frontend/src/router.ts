import { createRouter, createWebHistory } from 'vue-router'
import { adminApi } from './lib/api'

export const router = createRouter({
  history: createWebHistory(),
  routes: [],
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
