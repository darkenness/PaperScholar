const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';
const API_V1 = `${API_BASE}/api/v1`;

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('token');
}

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(url, { ...options, headers });

  if (res.status === 401) {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
    throw new Error('认证已过期，请重新登录');
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '请求失败' }));
    let message = `HTTP ${res.status}`;
    if (typeof err.detail === 'string') {
      message = err.detail;
    } else if (Array.isArray(err.detail)) {
      message = err.detail.map((e: any) => e.msg || JSON.stringify(e)).join('; ');
    } else if (err.detail) {
      message = JSON.stringify(err.detail);
    }
    throw new Error(message);
  }

  return res.json();
}

// Auth
export const authApi = {
  sendCode: (email: string) =>
    request<{ message: string }>(`${API_V1}/auth/send-code`, {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),
  register: (data: { username: string; email: string; password: string; verification_code?: string }) =>
    request<{ user: any; access_token: string }>(`${API_V1}/auth/register`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  login: (email: string, password: string) =>
    request<{ user: any; access_token: string }>(`${API_V1}/auth/login`, {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<any>(`${API_V1}/auth/me`),
};

// API Keys
export const apiKeysApi = {
  list: () => request<{ chat_keys: any[]; image_keys: any[] }>(`${API_V1}/api-keys`),
  create: (data: any) =>
    request<any>(`${API_V1}/api-keys`, { method: 'POST', body: JSON.stringify(data) }),
  verify: (id: number) =>
    request<{ is_verified: boolean; message: string }>(`${API_V1}/api-keys/${id}/verify`, { method: 'POST' }),
  update: (id: number, data: any) =>
    request<any>(`${API_V1}/api-keys/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id: number) =>
    request<any>(`${API_V1}/api-keys/${id}`, { method: 'DELETE' }),
};

// API Applications
export const applicationsApi = {
  create: (reason: string) =>
    request<any>(`${API_V1}/api-applications`, { method: 'POST', body: JSON.stringify({ reason }) }),
  my: () => request<any[]>(`${API_V1}/api-applications/my`),
};

// Model selection types
export interface ModelProviderInfo {
  key_id: number;
  provider: string;
  base_url: string | null;
  api_key_preview: string;
  is_system: boolean;
  priority: number;
}

export interface ModelGroupInfo {
  model_name: string;
  providers: ModelProviderInfo[];
}

export interface AvailableModelsResponse {
  chat_models: ModelGroupInfo[];
  image_models: ModelGroupInfo[];
}

// Generation
export const generateApi = {
  create: (data: any) =>
    request<{ task_id: string; status: string; stream_url: string }>(`${API_V1}/generate`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getAvailableModels: () =>
    request<AvailableModelsResponse>(`${API_V1}/generate/available-models`),
  getTask: (taskId: string) => request<any>(`${API_V1}/generate/${taskId}`),
  getHistory: (page = 1, pageSize = 20, taskType?: string) => {
    let url = `${API_V1}/generate/history/list?page=${page}&page_size=${pageSize}`;
    if (taskType) url += `&task_type=${taskType}`;
    return request<any>(url);
  },
  cancel: (taskId: string) =>
    request<any>(`${API_V1}/generate/${taskId}/cancel`, { method: 'POST' }),
  deleteTask: (taskId: string) =>
    request<any>(`${API_V1}/generate/${taskId}`, { method: 'DELETE' }),
  toggleFavorite: (resultId: number, isFavorited: boolean) =>
    request<any>(`${API_V1}/generate/results/${resultId}/favorite`, {
      method: 'POST',
      body: JSON.stringify({ is_favorited: isFavorited }),
    }),
  streamUrl: (taskId: string) => `${API_V1}/generate/${taskId}/stream`,
  getEvolution: (taskId: string) => request<any>(`${API_V1}/generate/${taskId}/evolution`),
  downloadZip: (taskId: string) => `${API_V1}/generate/${taskId}/download`,
};

// Admin
export const adminApi = {
  getUsers: (page = 1, pageSize = 20) =>
    request<any>(`${API_V1}/admin/users?page=${page}&page_size=${pageSize}`),
  updateRole: (userId: number, role: string) =>
    request<any>(`${API_V1}/admin/users/${userId}/role?role=${role}`, { method: 'PUT' }),
  toggleActive: (userId: number) =>
    request<any>(`${API_V1}/admin/users/${userId}/toggle-active`, { method: 'PUT' }),
  getApplications: (status = 'pending') =>
    request<any>(`${API_V1}/admin/applications?status_filter=${status}`),
  reviewApplication: (appId: number, data: { status: string; comment?: string }) =>
    request<any>(`${API_V1}/admin/applications/${appId}`, { method: 'PUT', body: JSON.stringify(data) }),
  getStats: () => request<any>(`${API_V1}/admin/stats`),
  getConfigs: () => request<any>(`${API_V1}/admin/configs`),
  updateConfig: (key: string, value: any) =>
    request<any>(`${API_V1}/admin/configs/${key}`, { method: 'PUT', body: JSON.stringify(value) }),
  getAnnouncements: () => request<any>(`${API_V1}/admin/announcements`),
  createAnnouncement: (content: string, isImportant = false) =>
    request<any>(`${API_V1}/admin/announcements?content=${encodeURIComponent(content)}&is_important=${isImportant}`, { method: 'POST' }),
  deleteAnnouncement: (id: number) =>
    request<any>(`${API_V1}/admin/announcements/${id}`, { method: 'DELETE' }),
  // System API Keys
  getSystemKeys: () => request<any>(`${API_V1}/admin/system-keys`),
  addSystemKey: (data: { model_type: string; provider: string; api_key: string; base_url?: string; model_name?: string }) => {
    const params = new URLSearchParams();
    params.set('model_type', data.model_type);
    params.set('provider', data.provider);
    params.set('api_key', data.api_key);
    if (data.base_url) params.set('base_url', data.base_url);
    if (data.model_name) params.set('model_name', data.model_name);
    return request<any>(`${API_V1}/admin/system-keys?${params.toString()}`, { method: 'POST' });
  },
  verifySystemKey: (id: number) =>
    request<any>(`${API_V1}/admin/system-keys/${id}/verify`, { method: 'POST' }),
  updateSystemKey: (id: number, data: { base_url?: string; api_key?: string; model_name?: string }) => {
    const params = new URLSearchParams();
    if (data.base_url !== undefined) params.set('base_url', data.base_url);
    if (data.api_key !== undefined) params.set('api_key', data.api_key);
    if (data.model_name !== undefined) params.set('model_name', data.model_name);
    return request<any>(`${API_V1}/admin/system-keys/${id}?${params.toString()}`, { method: 'PUT' });
  },
  deleteSystemKey: (id: number) =>
    request<any>(`${API_V1}/admin/system-keys/${id}`, { method: 'DELETE' }),
};

// Public
export const publicApi = {
  announcements: () => request<any>(`${API_V1}/announcements/active`),
  health: () => request<any>(`${API_BASE}/api/health`),
};
