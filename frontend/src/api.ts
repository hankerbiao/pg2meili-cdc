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
    return client.post(`/testcases?index_uid=${indexUid}`, data);
  },
  updateTestCase: async (client: any, id: string, indexUid: string, data: any) => {
    return client.put(`/testcases/${id}?index_uid=${indexUid}`, data);
  },
  deleteTestCase: async (client: any, id: string, indexUid: string) => {
    return client.delete(`/testcases/${id}?index_uid=${indexUid}`);
  },
  getMeiliSearchEndpoint: async (client: any, appName: string) => {
    return client.get(`/testcases/meilisearch/endpoint?app_name=${appName}`);
  },
};
