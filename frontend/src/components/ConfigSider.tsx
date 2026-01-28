import React from 'react';
import { Form, Input, Divider, Typography } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import { useApp } from '../context/AppContext';

const { TextArea } = Input;
const { Text } = Typography;

export const ConfigSider: React.FC = () => {
  const { config, updateConfig } = useApp();

  return (
    <div style={{ padding: '20px', height: '100%', overflowY: 'auto' }}>
      <div className="section-title"><SettingOutlined /> 全局配置</div>
      <Form
        layout="vertical"
        initialValues={config}
        onValuesChange={(_, allValues) => updateConfig(allValues)}
      >
        <Form.Item label="服务地址 (Base URL)" name="baseUrl" rules={[{ required: true }]}>
          <Input placeholder="https://api.example.com" />
        </Form.Item>
        <Form.Item label="认证令牌 (JWT Token)" name="token" rules={[{ required: true }]}>
          <TextArea rows={4} placeholder="Bearer Token..." />
        </Form.Item>
        <Form.Item label="应用名称 (App Name)" name="appName">
          <Input placeholder="my_app" />
        </Form.Item>
        <Form.Item label="索引标识 (Index UID)" name="indexUid">
          <Input placeholder="test_index" />
        </Form.Item>
        
        <Divider>MeiliSearch 配置</Divider>
        <Form.Item label="服务地址 (MeiliSearch URL)" name="meiliUrl">
          <Input placeholder="http://localhost:7700" />
        </Form.Item>
        <Form.Item label="访问密钥 (MeiliSearch Key)" name="meiliKey">
          <Input.Password placeholder="Master Key or API Key" />
        </Form.Item>
      </Form>
      <Divider />
      <Text type="secondary" style={{ fontSize: '12px' }}>
        请确保您的 Token 拥有正确的权限范围和签名。
        <br />
        MeiliSearch 配置可以通过“获取 Meili 地址”功能自动填充。
      </Text>
    </div>
  );
};
