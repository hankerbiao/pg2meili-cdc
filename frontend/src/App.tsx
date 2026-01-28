import React from 'react';
import { Layout, Menu, Breadcrumb, Row, Col, Tabs } from 'antd';
import { 
  RocketOutlined, 
  PlusOutlined, 
  EditOutlined, 
  DeleteOutlined, 
  SearchOutlined,
  ZoomInOutlined
} from '@ant-design/icons';
import './App.css';
import { AppProvider } from './context/AppContext';
import { ConfigSider } from './components/ConfigSider';
import { ResponseArea } from './components/ResponseArea';
import { CreateTestCase } from './components/CreateTestCase';
import { UpdateTestCase } from './components/UpdateTestCase';
import { DeleteTestCase } from './components/DeleteTestCase';
import { MeiliEndpoint } from './components/MeiliEndpoint';
import { MeiliSearchTool } from './components/MeiliSearchTool';

const { Header, Content, Footer, Sider } = Layout;

const MainContent: React.FC = () => {
  const menuItems = [
    { key: '1', icon: <RocketOutlined />, label: 'API 测试工具' }
  ];

  const breadcrumbItems = [
    { title: '首页' },
    { title: 'API 测试工具' }
  ];

  const tabItems = [
    {
      key: 'create',
      label: <span><PlusOutlined />创建用例</span>,
      children: <CreateTestCase />
    },
    {
      key: 'update',
      label: <span><EditOutlined />更新用例</span>,
      children: <UpdateTestCase />
    },
    {
      key: 'delete',
      label: <span><DeleteOutlined />删除用例</span>,
      children: <DeleteTestCase />
    },
    {
      key: 'meili-endpoint',
      label: <span><SearchOutlined />获取端点</span>,
      children: <MeiliEndpoint />
    },
    {
      key: 'meili-search',
      label: <span><ZoomInOutlined />搜索工具</span>,
      children: <MeiliSearchTool />
    }
  ];

  return (
    <Layout>
      <Header style={{ display: 'flex', alignItems: 'center' }}>
        <div className="logo">UniData 测试工具</div>
        <Menu theme="dark" mode="horizontal" defaultSelectedKeys={['1']} items={menuItems} style={{ flex: 1 }} />
      </Header>
      <Layout>
        <Sider width={300} style={{ background: '#fff', borderRight: '1px solid #f0f0f0' }}>
          <ConfigSider />
        </Sider>
        <Layout style={{ padding: '0 24px 24px' }}>
          <Breadcrumb style={{ margin: '16px 0' }} items={breadcrumbItems} />
          <Content className="site-layout-content">
            <Row gutter={24}>
              <Col span={14}>
                <Tabs defaultActiveKey="create" items={tabItems} />
              </Col>
              <Col span={10}>
                <ResponseArea />
              </Col>
            </Row>
          </Content>
          <Footer style={{ textAlign: 'center' }}>UniData API 测试工具 ©2026</Footer>
        </Layout>
      </Layout>
    </Layout>
  );
};

function App() {
  return (
    <AppProvider>
      <MainContent />
    </AppProvider>
  );
}

export default App;
