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
  register: (data: { username: string; email: string; password: string; invite_code: string }) =>
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
  size_mode?: 'quality' | 'fixed' | 'custom';
  size_options?: string[];
}

export interface ModelGroupInfo {
  model_name: string;
  providers: ModelProviderInfo[];
  size_mode?: 'quality' | 'fixed' | 'custom';
  size_options?: string[];
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
  continueTask: (taskId: string, data: any) =>
    request<{ task_id: string; status: string; stream_url: string }>(`${API_V1}/generate/${taskId}/continue`, {
      method: 'POST',
      body: JSON.stringify(data),
      }),
  retryTask: (taskId: string) =>
    request<{ task_id: string; status: string; stream_url: string }>(`${API_V1}/generate/${taskId}/retry`, {
      method: 'POST',
    }),
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
  addSystemKey: (data: { model_type: string; provider: string; api_key: string; base_url?: string; model_name?: string }) =>
    request<any>(`${API_V1}/admin/system-keys`, { method: 'POST', body: JSON.stringify(data) }),
  verifySystemKey: (id: number) =>
    request<any>(`${API_V1}/admin/system-keys/${id}/verify`, { method: 'POST' }),
  updateSystemKey: (id: number, data: { base_url?: string; api_key?: string; model_name?: string }) =>
    request<any>(`${API_V1}/admin/system-keys/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteSystemKey: (id: number) =>
    request<any>(`${API_V1}/admin/system-keys/${id}`, { method: 'DELETE' }),
};

// Public
export const publicApi = {
  announcements: () => request<any>(`${API_V1}/announcements/active`),
  health: () => request<any>(`${API_BASE}/api/health`),
};

// ===================== Edit / Vectorization =====================
export const editApi = {
  // Main vectorization
  vectorize: async (formData: FormData) => {
    const token = getToken();
    const res = await fetch(`${API_V1}/edit`, {
      method: 'POST',
      body: formData,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '请求失败' }));
      throw new Error(err.detail || '矢量化失败');
    }
    return res.json();
  },

  // Generate SVG from description (AutoFigure style)
  generateSvg: async (formData: FormData) => {
    const token = getToken();
    const res = await fetch(`${API_V1}/edit/svg-generate`, {
      method: 'POST',
      body: formData,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '请求失败' }));
      throw new Error(err.detail || 'SVG 生成失败');
    }
    return res.json();
  },

  // Extract methodology from paper (PDF/MD/TXT)
  extractMethodology: async (formData: FormData) => {
    const token = getToken();
    const res = await fetch(`${API_V1}/edit/extract-methodology`, {
      method: 'POST',
      body: formData,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '请求失败' }));
      throw new Error(err.detail || '方法论提取失败');
    }
    return res.json();
  },

  // Assemble final SVG from vectorized result
  assemble: async (formData: FormData) => {
    const token = getToken();
    const res = await fetch(`${API_V1}/edit/assemble`, {
      method: 'POST',
      body: formData,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '请求失败' }));
      throw new Error(err.detail || 'SVG 组装失败');
    }
    return res.json();
  },
};

// ===================== Refine / Enhancement =====================
export const refineApi = {
  enhance: async (formData: FormData) => {
    const token = getToken();
    const res = await fetch(`${API_V1}/refine/enhance`, {
      method: 'POST',
      body: formData,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '请求失败' }));
      throw new Error(err.detail || '图像增强失败');
    }
    return res.json();
  },

  styleTransfer: async (formData: FormData) => {
    const token = getToken();
    const res = await fetch(`${API_V1}/refine/style-transfer`, {
      method: 'POST',
      body: formData,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '请求失败' }));
      throw new Error(err.detail || '风格迁移失败');
    }
    return res.json();
  },
};

export type Capability = 'chat' | 'vision' | 'image_generation' | 'image_edit';
export interface CapabilityCheck {status: 'passed' | 'failed' | 'unknown'; checked_at?: string; latency_ms?: number; message?: string; error_code?: number;}
export interface ProviderConfig {
  id: number; model_type: 'chat' | 'image'; provider: string; base_url: string | null;
  model_name: string | null; display_name?: string; api_key_preview: string;
  api_options?: Record<string, unknown>; capability_status?: Record<string, CapabilityCheck>;
  is_verified: boolean; is_enabled: boolean; last_error?: string; endpoints?: Record<string,string>;
}
export function providerApi(system=false) {
  const root=`${API_V1}/${system?'admin/system-keys':'api-keys'}`;
  return {
    list: async ():Promise<ProviderConfig[]> => {const data=await request<any>(root);return system?data.items:[...data.chat_keys,...data.image_keys];},
    save: (data:unknown,id?:number) => request<any>(id?`${root}/${id}`:root,{method:id?'PUT':'POST',body:JSON.stringify(data)}),
    remove: (id:number) => request<any>(`${root}/${id}`,{method:'DELETE'}),
    test: (id:number,capability:Capability) => request<any>(`${root}/${id}/verify?capability=${capability}`,{method:'POST'}),
    models: (id:number) => request<{models:string[];message:string}>(`${root}/${id}/models`),
    discoverDraft: (data:unknown) => request<{models:string[];message:string}>(`${root}/discover`,{method:'POST',body:JSON.stringify(data)}),
    addModel: (id:number,data:unknown) => request<any>(`${root}/${id}/models`,{method:'POST',body:JSON.stringify(data)}),
  };
}
export const referencesApi={upload:async(file:File)=>{
  const body=new FormData();body.append('file',file);
  const token=getToken(); const res=await fetch(`${API_V1}/references/upload`,{method:'POST',body,headers:token?{Authorization:`Bearer ${token}`}:{}});
  const data=await res.json();if(!res.ok)throw new Error(data.detail||'参考图上传失败');
  return data as {id:number;url:string;file_name:string};
}};
export const assetUrl=(url:string)=>url.startsWith('/')?`${API_BASE}${url}`:url;
export async function downloadTaskZip(taskId:string) {
  const token=getToken();const res=await fetch(generateApi.downloadZip(taskId),{headers:token?{Authorization:`Bearer ${token}`}:{}});
  if(!res.ok){const data=await res.json().catch(()=>({}));throw new Error(data.detail||'下载失败');}
  const url=URL.createObjectURL(await res.blob());const a=document.createElement('a');a.href=url;a.download=`paperscholar-${taskId.slice(0,8)}.zip`;a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
