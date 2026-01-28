import React from 'react';
import { Button, Card, message, Typography } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useApp } from '../context/AppContext';
import { api } from '../api';

const { Paragraph } = Typography;

export const MeiliEndpoint: React.FC = () => {
  const { config, updateConfig, getClient, setResponse, setLoading, loading } = useApp();

  const handleGetMeili = async () => {
    const client = getClient();
    if (!client) return;

    if (!config.appName) {
      message.error('App Name is required for this request');
      return;
    }

    setLoading(true);
    try {
      const res = await api.getMeiliSearchEndpoint(client, config.appName);
      setResponse(JSON.stringify(res.data, null, 2));
      
      // Automatically update MeiliSearch config if successful
      if (res.data.meilisearch_url && res.data.api_key) {
        updateConfig({
          meiliUrl: res.data.meilisearch_url,
          meiliKey: res.data.api_key
        });
        message.success('MeiliSearch 配置已自动更新');
      } else {
        message.warning('未找到 MeiliSearch 连接信息');
      }
    } catch (err: any) {
      setResponse(JSON.stringify(err.response?.data || err.message, null, 2));
      message.error('获取 MeiliSearch 地址失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card title="获取 MeiliSearch 服务地址">
      <Button type="primary" icon={<SearchOutlined />} onClick={handleGetMeili} loading={loading} block>
        获取地址并更新配置
      </Button>
    </Card>
  );
};
