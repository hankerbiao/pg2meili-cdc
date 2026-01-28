import React from 'react';
import { Form, Input, Button, Card, message } from 'antd';
import { EditOutlined } from '@ant-design/icons';
import { useApp } from '../context/AppContext';
import { api } from '../api';

const { TextArea } = Input;

export const UpdateTestCase: React.FC = () => {
  const { config, getClient, setResponse, setLoading, loading } = useApp();
  const [form] = Form.useForm();

  const handleUpdate = async (values: any) => {
    const client = getClient();
    if (!client) return;

    setLoading(true);
    try {
      const { id, ...data } = values;
      let payload = { ...data };
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

      const res = await api.updateTestCase(client, id, config.indexUid, payload);
      setResponse(JSON.stringify(res.data, null, 2));
      message.success('测试用例更新成功');
    } catch (err: any) {
      setResponse(JSON.stringify(err.response?.data || err.message, null, 2));
      message.error('更新测试用例失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card title="更新测试用例">
      <Form form={form} layout="vertical" onFinish={handleUpdate}>
        <Form.Item name="id" label="测试用例 ID (ID)" rules={[{ required: true }]}>
          <Input placeholder="tc_001" />
        </Form.Item>
        <Form.Item name="title" label="标题 (Title)">
          <Input placeholder="登录功能测试（更新）" />
        </Form.Item>
        <Form.Item name="priority" label="优先级 (Priority)">
          <Input placeholder="medium" />
        </Form.Item>
        <Form.Item name="jsonContent" label="额外 JSON 数据">
          <TextArea rows={4} placeholder='{"extra_field": "value"}' />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block icon={<EditOutlined />}>
            发送请求
          </Button>
        </Form.Item>
      </Form>
    </Card>
  );
};
