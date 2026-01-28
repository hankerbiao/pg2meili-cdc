import React, { createContext, useContext, useState, type ReactNode } from 'react';
import { createClient } from '../api';
import type { ApiConfig } from '../api';
import { message } from 'antd';

interface AppState extends ApiConfig {
  indexUid: string;
  meiliUrl?: string;
  meiliKey?: string;
}

interface AppContextType {
  config: AppState;
  setConfig: (config: AppState) => void;
  updateConfig: (updates: Partial<AppState>) => void;
  response: string;
  setResponse: (res: string) => void;
  loading: boolean;
  setLoading: (loading: boolean) => void;
  getClient: () => any | null;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [config, setConfig] = useState<AppState>({
    baseUrl: 'http://localhost:8080',
    token: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcHBfbmFtZSI6Im15YXBwIiwic2NvcGVzIjpbXSwiZXhwIjoyMDg0OTI3MzAwfQ.XeQ_PTo1WqIRBn6jY3vqxETD61PwJUUAHpsTfSHH_Ok',
    appName: '',
    indexUid: 'test_index',
    meiliUrl: 'http://10.17.154.252:7700/',
    meiliKey: 'fa6593611630cec2eb3c41b9d3a73af8',
  });

  const [response, setResponse] = useState<string>('准备就绪，等待发送请求...');
  const [loading, setLoading] = useState(false);

  const updateConfig = (updates: Partial<AppState>) => {
    setConfig(prev => ({ ...prev, ...updates }));
  };

  const getClient = () => {
    if (!config.baseUrl) {
      message.error('请配置 Base URL');
      return null;
    }
    if (!config.token) {
      message.error('请配置 JWT Token');
      return null;
    }
    return createClient(config);
  };

  return (
    <AppContext.Provider value={{
      config,
      setConfig,
      updateConfig,
      response,
      setResponse,
      loading,
      setLoading,
      getClient
    }}>
      {children}
    </AppContext.Provider>
  );
};

export const useApp = () => {
  const context = useContext(AppContext);
  if (context === undefined) {
    throw new Error('useApp must be used within an AppProvider');
  }
  return context;
};
