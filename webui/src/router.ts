import { createRouter, createWebHashHistory } from 'vue-router'
import { ApiError, restoreSession } from './api/client'
import { applySession, authState, confirmDiscardDrafts, intendedRoute, rememberRoute } from './state'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/overview' },
    { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { public: true } },
    { path: '/overview', name: 'overview', component: () => import('./views/OverviewView.vue') },
    { path: '/groups', name: 'groups', component: () => import('./views/GroupsView.vue') },
    { path: '/groups/:groupId/:plugin?', name: 'group-detail', component: () => import('./views/GroupDetailView.vue') },
    { path: '/settings/:section?', name: 'settings', component: () => import('./views/GlobalSettingsView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/overview' }
  ]
})

router.beforeEach(async (to, from) => {
  if (from.name && to.fullPath !== from.fullPath && !confirmDiscardDrafts()) return false
  if (!authState.checked) {
    try {
      applySession(await restoreSession())
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) console.warn('Session check failed')
      applySession(null)
    }
  }
  if (!to.meta.public && !authState.authenticated) {
    rememberRoute(to)
    return { name: 'login' }
  }
  if (to.name === 'login' && authState.authenticated) return intendedRoute.value ?? '/overview'
  return true
})

export default router
