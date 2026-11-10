import { ArrowRight, Bot, BookOpen, CheckCircle2, Code2, Download, ExternalLink, KeyRound, Rocket, Search } from 'lucide-react'
import { Link } from 'react-router-dom'
import { DocsLayout } from '../components/DocsLayout'

const flow = [
  { number: '01', title: '开通应用与 API Key', role: '开通人', detail: '创建应用、选择所需 scope，并安全交付 API Key。' },
  { number: '02', title: '服务端写入数据', role: '业务开发者', detail: '调用 POST /api/v1/data/{collection}，使用 data:write。' },
  { number: '03', title: 'CDC 自动同步', role: '平台自动', detail: 'PostgreSQL → Outbox → Debezium → Kafka → 区域 Agent → Meilisearch。' },
  { number: '04', title: '通过区域 Agent 搜索', role: '业务开发者', detail: '调用搜索端点，使用 search:read；写入后需等待异步同步。' },
]

const steps = [
  {
    number: '01',
    icon: BookOpen,
    title: '了解什么是 MeliData 服务',
    body: 'MeliData 是面向应用的统一数据与搜索服务：业务数据通过数据 API 写入，再由区域 Agent 同步到 Meilisearch，提供就近、低延迟的搜索能力。',
    action: { label: '阅读快速开始', to: '/docs/quickstart' },
  },
  {
    number: '02',
    icon: Search,
    title: '评估与 App 的搜索需求契合度',
    body: '梳理需要搜索的集合、文档字段、过滤与排序条件，以及数据更新频率。确认你的场景适合全文检索和异步同步后，再进入接入流程。',
    action: { label: '查看 API 能力', to: '/docs/api-reference' },
  },
  {
    number: '03',
    icon: KeyRound,
    title: '开通应用并创建 API Key',
    body: '由开通人在控制台创建应用，按实际用途申请最小权限范围，并为开发、测试、生产环境分别创建 API Key。密钥只在创建时展示一次，请立即保存到密钥管理系统再交付，不要通过截图或聊天记录传递。',
    action: { label: '打开控制台', to: '/console/apps' },
  },
  {
    number: '04',
    icon: Bot,
    title: '交给 AI 页面网址学习',
    body: '将当前页面网址或 AI Agent 集成指南的网址交给你的 AI 编程助手，让它学习服务边界、鉴权要求和代码示例，再开始生成接入方案。',
    action: { label: '打开 AI Agent 指南', to: '/docs/agent-guide' },
  },
  {
    number: '05',
    icon: Code2,
    title: '开发代码',
    body: '让 AI 先生成代码，再由你确认请求路径、集合名称、字段映射和错误重试策略。使用服务端环境变量保存配置，不要把密钥写入前端源码。',
    action: { label: '查看 API Reference', to: '/docs/api-reference' },
  },
  {
    number: '06',
    icon: Rocket,
    title: '部署时填写 API Key',
    body: '部署应用时，通过平台的 Secret 或环境变量注入 API Key，例如 MELIDATA_API_KEY。上线前按快速开始验证完整链路：写入一条文档，等待区域同步完成，搜索能命中该文档，再接入全量数据。',
    action: { label: '查看认证规则', to: '/docs/authentication' },
  },
]

export function HowToUsePage() {
  return (
    <DocsLayout toc={[
      { href: '#flow', label: '接入流程一览' },
      ...steps.map((step) => ({ href: `#step-${step.number}`, label: `${step.number} ${step.title}` })),
    ]}>
      <article className="doc-article how-to-use-article">
        <div className="eyebrow">ONBOARDING OVERVIEW</div>
        <h1>从申请 Key 到搜索成功</h1>
        <p className="lead">从创建应用到区域搜索只有四步。先看流程，再按下方步骤完成接入；完整请求路径、参数和响应示例见 API Reference。</p>
        <a className="button button-secondary how-to-use-download" href={`${import.meta.env.BASE_URL}assets/melidata-usage-guide.md`} download="MeliData-使用说明.md">
          <Download size={16} />下载 Markdown 使用说明
        </a>

        <section id="flow">
          <h2>接入流程一览</h2>
          <ol className="onboarding-flow" aria-label="MeliData 接入流程">
            {flow.map((item) => (
              <li className={item.role === '平台自动' ? 'onboarding-flow-step automatic' : 'onboarding-flow-step'} key={item.number}>
                <span className="onboarding-flow-number">{item.number}</span>
                <span className="onboarding-flow-role">{item.role}</span>
                <h3>{item.title}</h3>
                <p>{item.detail}</p>
              </li>
            ))}
          </ol>
        </section>

        <div className="how-to-use-note">
          <CheckCircle2 size={19} />
          <span>推荐顺序：开通与交付 Key → 服务端写入 → 等待 CDC 同步 → 通过区域 Agent 搜索。</span>
        </div>

        <ol id="steps" className="how-to-use-steps" aria-label="按顺序完成接入步骤">
          {steps.map(({ number, icon: Icon, title, body, action }) => (
            <li className="how-to-use-step" id={`step-${number}`} key={number}>
              <div className="how-to-use-step-icon"><Icon size={20} /></div>
              <div className="how-to-use-step-content">
                <span className="how-to-use-step-number">{number}</span>
                <h2>{title}</h2>
                <p>{body}</p>
                <Link className="how-to-use-action" to={action.to}>{action.label}<ArrowRight size={15} /></Link>
              </div>
            </li>
          ))}
        </ol>

        <section className="next-section how-to-use-next">
          <h2>准备开始了吗？</h2>
          <p>把这页网址交给 AI，或直接从快速开始页面复制第一段请求示例。</p>
          <div className="next-links">
            <Link to="/docs/quickstart"><BookOpen size={18} /><span>快速开始</span><ArrowRight size={18} /></Link>
            <Link to="/docs/agent-guide"><Bot size={18} /><span>AI Agent 指南</span><ArrowRight size={18} /></Link>
          </div>
          <p className="how-to-use-url-hint"><ExternalLink size={14} />当前页面可直接分享给 AI 编程助手作为参考资料。</p>
        </section>
      </article>
    </DocsLayout>
  )
}
