import { createRouter, createWebHashHistory } from 'vue-router'
import { ApiError, restoreSession } from './api/client'
import { applySession, authState, confirmDiscardDrafts, intendedRoute, rememberRoute } from './state'

const router = createRouter({
  history: createWebHashHistory(),
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.path === from.path) return false
    return { top: 0 }
  },
  routes: [
    { path: '/', redirect: '/groups' },
    { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { public: true } },
    { path: '/groups', name: 'groups', component: () => import('./views/GroupsView.vue') },
    { path: '/groups/:groupId', name: 'group-plugins', component: () => import('./views/GroupDetailView.vue') },
    { path: '/groups/:groupId/plugins/:plugin', name: 'group-plugin-settings', component: () => import('./views/GroupDetailView.vue') },
    { path: '/plugins', name: 'plugins', component: () => import('./views/GlobalSettingsView.vue') },
    { path: '/system', name: 'system', component: () => import('./views/OverviewView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/groups' }
  ]
})

router.beforeEach(async (to, from) => {
  const authenticationRedirect = to.name === 'login' && authState.checked && !authState.authenticated
  if (!authenticationRedirect && from.name && to.fullPath !== from.fullPath && !confirmDiscardDrafts()) return false
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
  if (to.name === 'login' && authState.authenticated) return intendedRoute.value ?? '/groups'
  return true
})

export default router
