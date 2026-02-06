import { defineConfig } from 'vitepress'

export default defineConfig({
  title: "UniData",
  description: "Unified Data Management & Search API",
  lang: 'zh-CN',
  lastUpdated: true,
  
  themeConfig: {
    // 启用本地搜索
    search: {
      provider: 'local'
    },

    // 导航栏
    nav: [
      { text: '首页', link: '/' },
      { text: '使用指南', link: '/guide/' },
      { text: '搜索接口', link: '/search/index' },
      { text: '数据管理', link: '/management/index' },
      { text: '开发环境部署', link: '/deployment/' }
    ],

    // 侧边栏
    sidebar: {
      '/deployment/': [
        {
          text: '环境部署',
          items: [
            { text: '部署概览', link: '/deployment/' },
            { text: '系统需求', link: '/deployment/requirements' },
            { text: '安装步骤', link: '/deployment/installation' },
            { text: '配置介绍', link: '/deployment/configuration' },
            { text: '运行和维护', link: '/deployment/operations' }
          ]
        }
      ],
      '/guide/': [
        {
          text: '开发指南',
          items: [
            { text: '指南概览', link: '/guide/' },
            { text: '用户引导手册', link: '/guide/user-manual' }
          ]
        }
      ],
      '/search/': [
        {
          text: '搜索服务',
          items: [
            { text: '接口概览', link: '/search/index' }
          ]
        }
      ],
      '/management/': [
        {
          text: '数据管理',
          items: [
            { text: '数据管理概览', link: '/management/index' }
          ]
        }
      ]
    },

    // 页脚
    footer: {
      message: 'Released under the MIT License.',
      copyright: 'Copyright © 2024-present UniData Team'
    },

    // 右侧大纲配置
    outline: {
      level: [2, 3],
      label: '页面导航'
    },

    // 文档页脚（上一页/下一页）
    docFooter: {
      prev: '上一页',
      next: '下一页'
    },

    // 最后更新时间文本
    lastUpdatedText: '最后更新于',

    // 社交链接
    socialLinks: [
      { icon: 'github', link: 'https://github.com/hankerbiao/pg2meili-cdc/tree/main' }
    ]
  }
})
