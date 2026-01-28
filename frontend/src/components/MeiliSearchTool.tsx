import React, { useState } from 'react';
import { Form, Input, Button, Card, message, Table, Tag, Space, Divider, Typography } from 'antd';
import { SearchOutlined, CloudUploadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useApp } from '../context/AppContext';

const { Text } = Typography;



export const MeiliSearchTool: React.FC = () => {
  const { config, setResponse, setLoading, loading, getClient } = useApp();
  const [form] = Form.useForm();
  const [searchResults, setSearchResults] = useState<any[]>([]);

  const handleInitData = async () => {
    setResponse('初始化测试数据目前仅支持直接写入 Meilisearch，如需保留可另建工具');
    message.info('当前版本不再通过前端直接写入 Meilisearch');
  };

  const handleSearch = async (values: any) => {
    const client = getClient();
    if (!client) return;

    setLoading(true);
    try {
      const payload: any = {
        q: values.query || '',
      };
      if (config.indexUid) {
        payload.index_uid = config.indexUid;
      }
      if (values.filter) {
        payload.filter = values.filter;
      }

      const res = await client.post('/search', payload);
      const results = res.data;

      setResponse(JSON.stringify(results, null, 2));
      setSearchResults(results.hits || []);
      message.success(`找到 ${results.hits ? results.hits.length : 0} 条结果`);
    } catch (err: any) {
      const msg = err.response?.data || err.message || err;
      setResponse(JSON.stringify(msg, null, 2));
      message.error('搜索失败');
    } finally {
      setLoading(false);
    }
  };

  const applyPreset = (query: string, filter: string) => {
    form.setFieldsValue({ query, filter });
    handleSearch({ query, filter });
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 100, ellipsis: true },
    { title: '名称 (Name)', dataIndex: 'name', key: 'name', ellipsis: true },
    { title: '实验室 (Lab)', dataIndex: 'lab', key: 'lab', width: 80 },
    { 
      title: '标签 (Tags)', 
      dataIndex: 'tags', 
      key: 'tags',
      render: (tags: string[]) => (
        <>
          {tags?.map(tag => (
            <Tag key={tag} color="blue" style={{ fontSize: '10px', marginBottom: '2px' }}>{tag}</Tag>
          ))}
        </>
      )
    },
    { 
      title: '状态', 
      dataIndex: 'status', 
      key: 'status',
      width: 80,
      render: (status: string) => (
        <Tag color={status === '启用' ? 'success' : 'default'}>{status}</Tag>
      )
    },
    { 
        title: '通过率',
        dataIndex: 'pass_rate',
        key: 'pass_rate',
        width: 80,
        render: (rate: number) => rate ? `${(rate * 100).toFixed(0)}%` : '-'
    }
  ];

  return (
    <Card 
      title="条件搜索 (MeiliSearch)" 
      extra={
        <Button type="primary" ghost size="small" icon={<CloudUploadOutlined />} onClick={handleInitData} loading={loading}>
          初始化测试数据
        </Button>
      }
    >
      <div style={{ marginBottom: 16 }}>
        <Text strong style={{ marginRight: 8 }}>预设场景：</Text>
        <Space wrap>
          <Button size="small" icon={<ThunderboltOutlined />} onClick={() => applyPreset('电源', '')}>
            搜索"电源"
          </Button>
          <Button size="small" icon={<ThunderboltOutlined />} onClick={() => applyPreset('', 'lab = BIOS')}>
            筛选 BIOS 实验室
          </Button>
          <Button size="small" icon={<ThunderboltOutlined />} onClick={() => applyPreset('', 'pass_rate > 0.9')}>
            高通过率 ({'>'}90%)
          </Button>
          <Button size="small" icon={<ThunderboltOutlined />} onClick={() => applyPreset('监测', 'lab = BMC AND status = "启用"')}>
            BMC 监测启用项
          </Button>
        </Space>
      </div>
      
      <Divider style={{ margin: '12px 0' }} />

      <Form form={form} layout="vertical" onFinish={handleSearch}>
        <Form.Item name="query" label="搜索关键词 (Query)">
          <Input placeholder="输入搜索词..."/>
        </Form.Item>
        <Form.Item name="filter" label="过滤条件 (Filter - 可选)">
          <Input placeholder="priority = high AND id != tc_001" />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block icon={<SearchOutlined />}>
            搜索索引
          </Button>
        </Form.Item>
      </Form>

      {searchResults.length > 0 && (
        <Table 
          dataSource={searchResults} 
          columns={columns} 
          rowKey="id" 
          size="small" 
          pagination={{ pageSize: 5 }}
          style={{ marginTop: '20px' }}
        />
      )}
    </Card>
  );
};
