/**
 * 集中管理 data-testid 选择器。
 * 当源码中尚未添加 data-testid 时，回退到语义化选择器。
 * 后续可逐步在组件中补充 data-testid 属性。
 */
export const SEL = {
  // Layout
  siteNav: '.site-nav',
  consoleSidebar: '.console-sidebar',
  mobileMenuBtn: '[aria-label="菜单"]',

  // Login
  loginForm: '.login-panel form',
  loginError: '[role="alert"]',

  // Apps
  metricStrip: '.metric-strip',
  appTable: '.data-table',
  emptyState: '.empty-state',

  // App Detail
  appMeta: '.app-meta',
  keyTable: '.key-table',
  scopeChips: '.scope-chips',

  // Audit
  filterBar: '.filter-bar',
  pagination: '.pagination',

  // Dialogs
  secretDialog: '[role="dialog"]',
  confirmDialog: '[role="alertdialog"]',

  // Code
  codeBlock: '.code-block',
  copyBtn: '.code-block button',
} as const
