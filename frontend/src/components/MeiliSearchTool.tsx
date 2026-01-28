import React, { useState } from 'react';
import { Form, Input, Button, Card, message, Table, Tag } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { MeiliSearch } from 'meilisearch';
import { useApp } from '../context/AppContext';

export const MeiliSearchTool: React.FC = () => {
  const { config, setResponse, setLoading, loading } = useApp();
  const [form] = Form.useForm();
  const [searchResults, setSearchResults] = useState<any[]>([]);

  const handleSearch = async (values: any) => {
    if (!config.meiliUrl || !config.meiliKey) {
      message.error('请先配置 MeiliSearch URL 和 Key（可在配置栏设置或通过“获取 Meili 地址”自动获取）');
      return;
    }

    setLoading(true);
    try {
      const client = new MeiliSearch({
        host: config.meiliUrl,
        apiKey: config.meiliKey,
      });

      const index = client.index(config.indexUid);
      const searchParams = values.filter ? { filter: values.filter } : {};
      
      const results = await index.search(values.query || '', searchParams);
      
      setResponse(JSON.stringify(results, null, 2));
      setSearchResults(results.hits);
      message.success(`找到 ${results.hits.length} 条结果`);
    } catch (err: any) {
      setResponse(JSON.stringify(err.message || err, null, 2));
      message.error('搜索失败');
    } finally {
      setLoading(false);
    }
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id' },
    { title: '标题 (Title)', dataIndex: 'title', key: 'title' },
    { 
      title: '优先级 (Priority)', 
      dataIndex: 'priority', 
      key: 'priority',
      render: (priority: string) => (
        <Tag color={priority === 'high' ? 'red' : priority === 'medium' ? 'orange' : 'green'}>
          {priority}
        </Tag>
      )
    },
    { 
        title: '匹配分数 (Score)',
        dataIndex: '_rankingScore',
        key: '_rankingScore',
        render: (score: number) => score ? score.toFixed(2) : '-'
    }
  ];

  return (
    <Card title="条件搜索 (MeiliSearch)">
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
