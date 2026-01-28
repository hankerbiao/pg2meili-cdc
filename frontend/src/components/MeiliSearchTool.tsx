import React, { useState } from 'react';
import { Form, Input, Button, Card, message, Table, Tag, Space, Divider, Typography } from 'antd';
import { SearchOutlined, CloudUploadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { MeiliSearch } from 'meilisearch';
import { useApp } from '../context/AppContext';

const { Text } = Typography;

const SAMPLE_DATA = [
  {
    "id": "66c46c589ec5d1471b49c8d2",
    "author": "乔海丽",
    "creation_ts": "2024-08-20 18:13",
    "lab": "BMC",
    "ext_id": "BMC-88428",
    "name": "电源线缆故障监控测试",
    "summary": "当电源线缆被拔出，但电源模块仍在位发生 AC Lost 时，该电源的输入电压、输出电压、输入功耗、输出功耗及电压风扇转速均跳过监控，对应传感器放在禁用中",
    "status": "启用",
    "paths": ["PSU failure warning"],
    "updater": "陈梦洁",
    "update_ts": "2025-08-21 09:27",
    "tags": ["BHS_G60", "EVT", "DVT", "HighPassRate"],
    "phases": ["EVT", "DVT"],
    "automation": ["手动执行"],
    "full_exec_range": [15],
    "manual_exec_range": [15],
    "os_list": ["Linux"],
    "variation_settings": [],
    "videos": [],
    "scores": "不适用",
    "requirement_count": 3,
    "bug_count": 0,
    "pass_rate": 1,
    "fail_rate": 0,
    "block_rate": 0,
    "utility": 1.2,
    "executed": 5,
    "variations": 1,
    "enabled_tcv": 1,
    "disabled_tcv": 0,
    "reviewed_tcv": 1,
    "not_reviewed_tcv": 0
  },
  {
    "id": "66c46c589ec5d1471b49c8d3",
    "author": "张伟",
    "creation_ts": "2024-08-21 10:30",
    "lab": "BIOS",
    "ext_id": "BIOS-88429",
    "name": "CPU温度过高保护测试",
    "summary": "测试当CPU温度超过阈值时，系统是否能够正确触发保护机制，包括降频和关机操作",
    "status": "启用",
    "paths": ["Temperature protection"],
    "updater": "李娜",
    "update_ts": "2025-08-22 14:15",
    "tags": ["Thermal", "EVT", "HighPriority"],
    "phases": ["EVT", "DVT", "PVT"],
    "automation": ["自动执行"],
    "full_exec_range": [10, 20, 30],
    "manual_exec_range": [10, 20],
    "os_list": ["Linux", "Windows"],
    "variation_settings": [],
    "videos": [],
    "scores": "95",
    "requirement_count": 5,
    "bug_count": 1,
    "pass_rate": 0.95,
    "fail_rate": 0.05,
    "block_rate": 0,
    "utility": 2.5,
    "executed": 20,
    "variations": 3,
    "enabled_tcv": 3,
    "disabled_tcv": 1,
    "reviewed_tcv": 2,
    "not_reviewed_tcv": 1
  },
  {
    "id": "66c46c589ec5d1471b49c8d4",
    "author": "王芳",
    "creation_ts": "2024-08-22 09:00",
    "lab": "BMC",
    "ext_id": "BMC-88430",
    "name": "内存ECC错误检测测试",
    "summary": "验证BMC能够正确检测和报告内存ECC错误，包括单比特错误和双比特错误",
    "status": "启用",
    "paths": ["Memory error detection"],
    "updater": "王芳",
    "update_ts": "2025-08-23 11:45",
    "tags": ["Memory", "DVT", "ECC"],
    "phases": ["DVT"],
    "automation": ["手动执行"],
    "full_exec_range": [5],
    "manual_exec_range": [5],
    "os_list": ["Linux"],
    "variation_settings": [],
    "videos": [],
    "scores": "88",
    "requirement_count": 8,
    "bug_count": 2,
    "pass_rate": 0.8,
    "fail_rate": 0.15,
    "block_rate": 0.05,
    "utility": 1.8,
    "executed": 40,
    "variations": 1,
    "enabled_tcv": 1,
    "disabled_tcv": 0,
    "reviewed_tcv": 0,
    "not_reviewed_tcv": 1
  }
];

export const MeiliSearchTool: React.FC = () => {
  const { config, setResponse, setLoading, loading } = useApp();
  const [form] = Form.useForm();
  const [searchResults, setSearchResults] = useState<any[]>([]);

  const getClient = () => {
    if (!config.meiliUrl || !config.meiliKey) {
      message.error('请先配置 MeiliSearch URL 和 Key（可在配置栏设置或通过“获取 Meili 地址”自动获取）');
      return null;
    }
    return new MeiliSearch({
      host: config.meiliUrl,
      apiKey: config.meiliKey,
    });
  };

  const handleInitData = async () => {
    const client = getClient();
    if (!client) return;

    setLoading(true);
    try {
      const index = client.index(config.indexUid);
      const task = await index.addDocuments(SAMPLE_DATA);
      setResponse(JSON.stringify(task, null, 2));
      message.success('测试数据初始化任务已提交，请稍候搜索');
    } catch (err: any) {
      setResponse(JSON.stringify(err.message || err, null, 2));
      message.error('初始化数据失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (values: any) => {
    const client = getClient();
    if (!client) return;

    setLoading(true);
    try {
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
