import React from 'react';
import { Card } from 'antd';
import { CodeOutlined } from '@ant-design/icons';
import { useApp } from '../context/AppContext';

export const ResponseArea: React.FC = () => {
  const { response } = useApp();

  return (
    <Card 
      title={<span><CodeOutlined /> 响应结果</span>}
      style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
      bodyStyle={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
    >
      <div className="response-area" style={{ flex: 1, marginTop: 0 }}>
        {response}
      </div>
    </Card>
  );
};
