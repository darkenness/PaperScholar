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
    throw new Error(err.detail || `HTTP ${res.status}`);
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
  register: (data: { username: string; email: string; password: string; verification_code: string }) =>
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

// Generation
export const generateApi = {
  create: (data: any) =>
    request<{ task_id: string; status: string; stream_url: string }>(`${API_V1}/generate`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getTask: (taskId: string) => request<any>(`${API_V1}/generate/${taskId}`),
  getHistory: (page = 1, pageSize = 20, taskType?: string) => {
    let url = `${API_V1}/generate/history/list?page=${page}&page_size=${pageSize}`;
    if (taskType) url += `&task_type=${taskType}`;
    return request<any>(url);
  },
  cancel: (taskId: string) =>
    request<any>(`${API_V1}/generate/${taskId}/cancel`, { method: 'POST' }),
  toggleFavorite: (resultId: number, isFavorited: boolean) =>
    request<any>(`${API_V1}/generate/results/${resultId}/favorite`, {
      method: 'POST',
      body: JSON.stringify({ is_favorited: isFavorited }),
    }),
  streamUrl: (taskId: string) => `${API_V1}/generate/${taskId}/stream`,
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
};

// Public
export const publicApi = {
  announcements: () => request<any>(`${API_V1}/announcements/active`),
  health: () => request<any>(`${API_BASE}/api/health`),
};
