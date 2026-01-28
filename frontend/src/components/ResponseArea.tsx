import React from 'react';
import { CodeOutlined } from '@ant-design/icons';
import { useApp } from '../context/AppContext';

export const ResponseArea: React.FC = () => {
  const { response } = useApp();

  return (
    <>
      <div className="section-title"><CodeOutlined /> 响应结果</div>
      <div className="response-area">
        {response}
      </div>
    </>
  );
};
