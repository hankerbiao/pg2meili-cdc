import React from 'react';
import { Form, Input, Button, Card, message } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useApp } from '../context/AppContext';
import { api } from '../api';

export const DeleteTestCase: React.FC = () => {
  const { config, getClient, setResponse, setLoading, loading } = useApp();
  const [form] = Form.useForm();

  const handleDelete = async (values: any) => {
    const client = getClient();
    if (!client) return;

    setLoading(true);
    try {
      const res = await api.deleteTestCase(client, values.id, config.indexUid);
      setResponse(JSON.stringify(res.data, null, 2));
      message.success('测试用例删除成功');
    } catch (err: any) {
      setResponse(JSON.stringify(err.response?.data || err.message, null, 2));
      message.error('删除测试用例失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card title="删除测试用例">
      <Form form={form} layout="vertical" onFinish={handleDelete}>
        <Form.Item name="id" label="测试用例 ID (ID)" rules={[{ required: true }]}>
          <Input placeholder="tc_001" />
        </Form.Item>
        <Form.Item>
          <Button danger htmlType="submit" loading={loading} block icon={<DeleteOutlined />}>
            发送删除请求
          </Button>
        </Form.Item>
      </Form>
    </Card>
  );
};
