---
layout: home

hero:
  name: "UniData"
  text: "分布式数据管理与搜索中心"
  tagline: "统一的数据接入、即时搜索与全生命周期管理"
  actions:
    - theme: brand
      text: "开始搜索"
      link: "/search/index"
    - theme: alt
      text: "数据接入"
      link: "/management/index"
  
features:
  - title: "高性能搜索"
    details: "基于 Meilisearch 的毫秒级搜索体验，支持全文检索、分词高亮与多维过滤。"
    icon: 🔍
  - title: "统一数据管理"
    details: "标准化的 REST API，支持通用文档的 CRUD 操作，自动同步至搜索索引。"
    icon: 📦
  - title: "企业级鉴权"
    details: "基于 JWT 的应用级访问控制，安全可靠。"
    icon: 🛡️
  - title: "自动化同步"
    details: "内置 CDC (Change Data Capture) 机制，数据库变更实时流转至搜索引擎。"
    icon: 🔄
---

## 线上环境地址

- 搜索服务（Search Service）：
  - 天津环境：[http://10.17.154.252:8091](http://10.17.154.252:8091)
  - 北京环境：[http://10.32.129.188:8091](http://10.32.129.188:8091)
- Meilisearch 服务：
  - 天津环境：[http://10.17.154.252:7700/](http://10.17.154.252:7700/)
  - 北京环境：[http://10.32.129.188:7700](http://10.32.129.188:7700)
- 文档写入服务（Producer / UniData API）：
  - 北京环境：[http://10.32.129.188:8080/api/v1/data/](http://10.32.129.188:8080/api/v1/data/)
