import React from 'react';
import { Form, Input, Button, Card, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useApp } from '../context/AppContext';
import { api } from '../api';

const { TextArea } = Input;

export const CreateTestCase: React.FC = () => {
  const { config, getClient, setResponse, setLoading, loading } = useApp();
  const [form] = Form.useForm();

  const handleCreate = async (values: any) => {
    const client = getClient();
    if (!client) return;

    setLoading(true);
    try {
      let payload = { ...values };
      if (values.jsonContent) {
        try {
          const parsed = JSON.parse(values.jsonContent);
          payload = { ...payload, ...parsed };
          delete payload.jsonContent;
        } catch (e) {
          message.error('无效的 JSON 格式');
          setLoading(false);
          return;
        }
      }
      
      const res = await api.createTestCase(client, config.indexUid, payload);
      setResponse(JSON.stringify(res.data, null, 2));
      message.success('测试用例创建成功');
    } catch (err: any) {
      setResponse(JSON.stringify(err.response?.data || err.message, null, 2));
      message.error('创建测试用例失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card title="创建测试用例">
      <Form form={form} layout="vertical" onFinish={handleCreate}>
        <Form.Item name="id" label="测试用例 ID (ID)" rules={[{ required: true }]}>
          <Input placeholder="tc_001" />
        </Form.Item>
        <Form.Item name="title" label="标题 (Title)" rules={[{ required: true }]}>
          <Input placeholder="登录功能测试" />
        </Form.Item>
        <Form.Item name="description" label="描述 (Description)">
          <Input placeholder="测试用户登录流程" />
        </Form.Item>
         <Form.Item name="priority" label="优先级 (Priority)">
          <Input placeholder="high" />
        </Form.Item>
        <Form.Item name="jsonContent" label="额外 JSON 数据">
          <TextArea rows={4} placeholder='{"extra_field": "value"}' />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block icon={<PlusOutlined />}>
            发送请求
          </Button>
        </Form.Item>
      </Form>
    </Card>
  );
};
