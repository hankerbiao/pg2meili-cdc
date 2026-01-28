import axios from 'axios';

export interface ApiConfig {
  baseUrl: string;
  token: string;
  appName?: string;
}

export const createClient = (config: ApiConfig) => {
  const client = axios.create({
    baseURL: config.baseUrl,
    headers: {
      'Authorization': `Bearer ${config.token}`,
      'Content-Type': 'application/json',
      ...(config.appName ? { 'X-App-Name': config.appName } : {}),
    },
  });

  return client;
};

// API Functions
export const api = {
  createTestCase: async (client: any, indexUid: string, data: any) => {
    return client.post(`/api/v1/testcases?index_uid=${indexUid}`, data);
  },
  updateTestCase: async (client: any, id: string, indexUid: string, data: any) => {
    return client.put(`/api/v1/testcases/${id}?index_uid=${indexUid}`, data);
  },
  deleteTestCase: async (client: any, id: string, indexUid: string) => {
    return client.delete(`/api/v1/testcases/${id}?index_uid=${indexUid}`);
  },
};
