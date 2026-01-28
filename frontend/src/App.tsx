import React, { useState } from 'react';
import { Layout, Tabs, Typography } from 'antd';
import { DatabaseOutlined, SearchOutlined } from '@ant-design/icons';
import { ConfigSider } from './components/ConfigSider';
import { ResponseArea } from './components/ResponseArea';
import { CreateTestCase } from './components/CreateTestCase';
import { UpdateTestCase } from './components/UpdateTestCase';
import { DeleteTestCase } from './components/DeleteTestCase';
import { MeiliSearchTool } from './components/MeiliSearchTool';
import { AppProvider } from './context/AppContext';

const { Header, Sider, Content } = Layout;
const { Title } = Typography;

const AppContent: React.FC = () => {
  const [activeTab, setActiveTab] = useState('api');

  const apiItems = [
    {
      key: 'create',
      label: '创建测试用例',
      children: <CreateTestCase />,
    },
    {
      key: 'update',
      label: '更新测试用例',
      children: <UpdateTestCase />,
    },
    {
      key: 'delete',
      label: '删除测试用例',
      children: <DeleteTestCase />,
    },
  ];

  const searchItems = [
    {
      key: 'search',
      label: '条件搜索',
      children: <MeiliSearchTool />,
    },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center', background: '#fff', padding: '0 20px', borderBottom: '1px solid #f0f0f0' }}>
        <Title level={4} style={{ margin: 0, marginRight: 40, color: '#1890ff' }}>
          UniData API Tester
        </Title>
        <Tabs 
          activeKey={activeTab} 
          onChange={setActiveTab}
          style={{ marginBottom: -1 }}
          items={[
            {
              key: 'api',
              label: (
                <span>
                  <DatabaseOutlined />
                  数据管理
                </span>
              ),
            },
            {
              key: 'search',
              label: (
                <span>
                  <SearchOutlined />
                  搜索测试
                </span>
              ),
            }
          ]}
        />
      </Header>
      <Layout>
        <Sider width={300} theme="light" style={{ borderRight: '1px solid #f0f0f0' }}>
          <ConfigSider />
        </Sider>
        <Content style={{ padding: '20px', background: '#f5f5f5', overflowY: 'auto' }}>
          <div style={{ display: 'flex', gap: '20px', height: '100%' }}>
            <div style={{ flex: 1, overflowY: 'auto' }}>
              {activeTab === 'api' ? (
                <Tabs defaultActiveKey="create" items={apiItems} type="card" />
              ) : (
                <Tabs defaultActiveKey="search" items={searchItems} type="card" />
              )}
            </div>
            <div style={{ width: '400px', display: 'flex', flexDirection: 'column' }}>
              <ResponseArea />
            </div>
          </div>
        </Content>
      </Layout>
    </Layout>
  );
};

const App: React.FC = () => {
  return (
    <AppProvider>
      <AppContent />
    </AppProvider>
  );
};

export default App;
