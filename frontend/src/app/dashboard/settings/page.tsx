'use client';

import { useEffect, useState } from 'react';
import { apiKeysApi, applicationsApi } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';

export default function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const [chatKeys, setChatKeys] = useState<any[]>([]);
  const [imageKeys, setImageKeys] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Add form
  const [showForm, setShowForm] = useState(false);
  const [formType, setFormType] = useState<'chat' | 'image'>('chat');
  const [provider, setProvider] = useState('openai_compat');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [modelName, setModelName] = useState('');
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);

  // Application
  const [appReason, setAppReason] = useState('');
  const [appLoading, setAppLoading] = useState(false);
  const [myApps, setMyApps] = useState<any[]>([]);

  const loadKeys = async () => {
    try {
      const data = await apiKeysApi.list();
      setChatKeys(data.chat_keys);
      setImageKeys(data.image_keys);
    } catch { }
    setLoading(false);
  };

  const loadApps = async () => {
    try {
      const data = await applicationsApi.my();
      setMyApps(data);
    } catch { }
  };

  useEffect(() => { loadKeys(); loadApps(); }, []);

  const handleAdd = async () => {
    if (!apiKey || apiKey.length < 10) { setFormError('API Key 长度不足'); return; }
    setSaving(true); setFormError('');
    try {
      await apiKeysApi.create({
        model_type: formType, provider,
        base_url: baseUrl || undefined,
        api_key: apiKey,
        model_name: modelName || undefined,
      });
      setShowForm(false); setApiKey(''); setBaseUrl(''); setModelName('');
      await loadKeys();
    } catch (e: any) { setFormError(e.message); }
    setSaving(false);
  };

  const handleVerify = async (id: number) => {
    try {
      const res = await apiKeysApi.verify(id);
      alert(res.message);
      await loadKeys();
    } catch (e: any) { alert(e.message); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除此 API Key？')) return;
    try { await apiKeysApi.delete(id); await loadKeys(); } catch { }
  };

  const handleApply = async () => {
    if (!appReason || appReason.length < 10) return;
    setAppLoading(true);
    try { await applicationsApi.create(appReason); setAppReason(''); await loadApps(); } catch (e: any) { alert(e.message); }
    setAppLoading(false);
  };

  const renderKeyTable = (keys: any[], type: string) => (
    <div className="tech-panel overflow-hidden">
      <div className="px-5 py-4 border-b border-[var(--border-main)] flex justify-between items-center bg-[var(--badge-bg)]">
        <h3 className="font-bold text-[var(--text-primary)] text-sm">{type === 'chat' ? 'Chat 模型' : 'Image 模型'} API Keys</h3>
        <button onClick={() => { setShowForm(true); setFormType(type as any); }} className="text-xs bg-primary-600 hover:bg-primary-500 text-white px-3 py-1.5">+ 添加</button>
      </div>
      {keys.length === 0 ? (
        <div className="py-8 text-center text-[var(--text-muted)] text-sm">暂无配置</div>
      ) : (
        <div className="divide-y divide-[var(--border-subtle)]">
          {keys.map((k: any) => (
            <div key={k.id} className="px-5 py-3 flex items-center justify-between hover:bg-[var(--bg-hover)] transition-colors">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-[var(--text-primary)]">{k.provider}</span>
                  {k.model_name && <span className="text-xs text-[var(--text-muted)]">· {k.model_name}</span>}
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${k.is_verified ? 'bg-green-500/20 text-green-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
                    {k.is_verified ? '已验证' : '未验证'}
                  </span>
                </div>
                <div className="text-xs text-[var(--text-muted)] mt-0.5 font-mono">{k.api_key_preview}</div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button onClick={() => handleVerify(k.id)} className="btn-ghost text-xs py-1 px-2">验证</button>
                <button onClick={() => handleDelete(k.id)} className="text-xs text-red-400 hover:text-red-300 px-2 py-1">删除</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  if (loading) return <div className="flex justify-center py-20"><div className="w-6 h-6 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" /></div>;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">API 配置</h1>
        <p className="text-[var(--text-muted)] text-sm mt-1">管理 Chat / Image 模型的 API Key，支持多 Provider 和负载均衡</p>
      </div>

      {/* API Key Tables */}
      <div className="grid grid-cols-1 gap-6">
        {renderKeyTable(chatKeys, 'chat')}
        {renderKeyTable(imageKeys, 'image')}
      </div>

      {/* Add Form Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowForm(false)}>
          <div className="tech-panel p-6 w-full max-w-md space-y-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-[var(--text-primary)]">添加 API Key ({formType === 'chat' ? 'Chat模型' : 'Image模型'})</h3>
            <div>
              <label className="text-xs text-[var(--text-muted)] mb-1 block">Provider</label>
              <select value={provider} onChange={(e) => setProvider(e.target.value)} className="w-full input-tech text-sm py-2">
                <option value="openai_compat">OpenAI 兼容 (OpenRouter/自定义)</option>
                <option value="gemini">Google Gemini</option>
                <option value="anthropic">Anthropic Claude</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-[var(--text-muted)] mb-1 block">Base URL (可选)</label>
              <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://openrouter.ai/api/v1" className="w-full input-tech text-sm" />
            </div>
            <div>
              <label className="text-xs text-[var(--text-muted)] mb-1 block">API Key *</label>
              <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-..." type="password" className="w-full input-tech text-sm" />
            </div>
            <div>
              <label className="text-xs text-[var(--text-muted)] mb-1 block">模型名称 (可选)</label>
              <input value={modelName} onChange={(e) => setModelName(e.target.value)} placeholder="gemini-2.5-pro" className="w-full input-tech text-sm" />
            </div>
            {formError && <div className="text-red-400 text-xs">{formError}</div>}
            <div className="flex gap-3 pt-2">
              <button onClick={() => setShowForm(false)} className="btn-ghost flex-1 py-2 text-sm">取消</button>
              <button onClick={handleAdd} disabled={saving} className="btn-primary flex-1 py-2 text-sm disabled:opacity-50">{saving ? '保存中...' : '保存'}</button>
            </div>
          </div>
        </div>
      )}

      {/* System API Application */}
      {!user?.system_api_approved && (
        <div className="tech-panel p-6">
          <h3 className="text-lg font-bold text-[var(--text-primary)] mb-3">申请系统 API</h3>
          <p className="text-sm text-[var(--text-muted)] mb-4">如果您没有自己的 API Key，可以申请使用系统提供的 API（需管理员审核）</p>
          <textarea value={appReason} onChange={(e) => setAppReason(e.target.value)} placeholder="请说明您的使用场景和预计用量（至少10字）..." rows={3} className="w-full input-tech text-sm mb-3" />
          <button onClick={handleApply} disabled={appLoading || appReason.length < 10} className="btn-primary py-2 px-4 text-sm disabled:opacity-50">
            {appLoading ? '提交中...' : '提交申请'}
          </button>
          {myApps.length > 0 && (
            <div className="mt-4 space-y-2">
              <h4 className="text-xs font-bold text-[var(--text-muted)]">我的申请记录</h4>
              {myApps.map((a: any) => (
                <div key={a.id} className="flex items-center gap-3 text-xs">
                  <span className={`px-2 py-0.5 rounded font-bold ${a.status === 'approved' ? 'bg-green-500/20 text-green-400' : a.status === 'rejected' ? 'bg-red-500/20 text-red-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
                    {a.status === 'approved' ? '已批准' : a.status === 'rejected' ? '已拒绝' : '审核中'}
                  </span>
                  <span className="text-[var(--text-muted)]">{a.reason?.substring(0, 50)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
