import type { Page, Route } from '@playwright/test'

export const mockSession = {
  username: 'admin',
  csrf_token: 'csrf-test',
  expires_at: 4102444800,
}

type AuthenticatedHandler = (route: Route) => Promise<void> | void

/**
 * Model the complete browser session transition so route-guard tests start
 * unauthenticated and only gain a session after the login request succeeds.
 */
export async function mockLoginFlow(
  page: Page,
  handleAuthenticated?: AuthenticatedHandler,
) {
  let authenticated = false

  await page.route('**/api/v1/open-platform/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname

    if (path.endsWith('/session')) {
      if (request.method() === 'POST') {
        authenticated = true
        return route.fulfill({ json: { data: mockSession } })
      }
      if (request.method() === 'DELETE') {
        authenticated = false
        return route.fulfill({ json: { data: { logged_out: true } } })
      }
      if (authenticated) return route.fulfill({ json: { data: mockSession } })
      return route.fulfill({ status: 401, json: { message: '未登录', data: null } })
    }

    if (!authenticated) {
      return route.fulfill({ status: 401, json: { message: '未登录', data: null } })
    }
    if (handleAuthenticated) return handleAuthenticated(route)
    return route.fulfill({ status: 404, json: { message: 'not found', data: null } })
  })

  return {
    expire() {
      authenticated = false
    },
  }
}
