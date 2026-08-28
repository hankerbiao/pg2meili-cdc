import { ArrowRight, Bot, BookOpen, CheckCircle2, ClipboardCheck, Code2, ExternalLink, Rocket, Search } from 'lucide-react'
import { Link } from 'react-router-dom'
import { DocsLayout } from '../components/DocsLayout'

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
    icon: ClipboardCheck,
    title: '申请 App API',
    body: '在控制台创建应用，按实际用途申请权限范围，并为开发、测试、生产环境分别管理 API Key。密钥只在创建时展示一次，请妥善保存。',
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
    action: { label: '查看 Python SDK', to: '/docs/python-sdk' },
  },
  {
    number: '06',
    icon: Rocket,
    title: '部署时填写 API Key',
    body: '部署应用时，通过平台的 Secret 或环境变量注入 API Key，例如 MELIDATA_API_KEY。部署后先验证鉴权，再验证写入、同步和搜索链路。',
    action: { label: '查看认证规则', to: '/docs/authentication' },
  },
]

export function HowToUsePage() {
  return (
    <DocsLayout toc={steps.map((step) => ({ href: `#step-${step.number}`, label: `${step.number} ${step.title}` }))}>
      <article className="doc-article how-to-use-article">
        <div className="eyebrow">HOW TO USE</div>
        <h1>从需求评估到上线部署</h1>
        <p className="lead">按照下面六个步骤接入 MeliData。先确认搜索需求，再申请应用权限，最后把 API Key 作为部署配置注入你的服务。</p>

        <div className="how-to-use-note">
          <CheckCircle2 size={19} />
          <span>推荐顺序：了解服务 → 评估需求 → 申请 API → 让 AI 学习 → 开发代码 → 部署配置。</span>
        </div>

        <section id="steps" className="how-to-use-steps" aria-label="接入步骤">
          {steps.map(({ number, icon: Icon, title, body, action }) => (
            <article className="how-to-use-step" id={`step-${number}`} key={number}>
              <div className="how-to-use-step-icon"><Icon size={20} /></div>
              <div className="how-to-use-step-content">
                <span className="how-to-use-step-number">{number}</span>
                <h2>{title}</h2>
                <p>{body}</p>
                <Link className="how-to-use-action" to={action.to}>{action.label}<ArrowRight size={15} /></Link>
              </div>
            </article>
          ))}
        </section>

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
