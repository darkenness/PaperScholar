'use client';

import { useEffect, useState } from 'react';
import { adminApi } from '@/lib/api';

export default function AdminConfigPage() {
  const [configs, setConfigs] = useState<any[]>([]);
  const [announcements, setAnnouncements] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [systemKeys, setSystemKeys] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [annContent, setAnnContent] = useState('');
  const [annImportant, setAnnImportant] = useState(false);

  // System Key form
  const [showKeyForm, setShowKeyForm] = useState(false);
  const [keyModelType, setKeyModelType] = useState<'chat' | 'image'>('chat');
  const [keyProvider, setKeyProvider] = useState('openai_compat');
  const [keyBaseUrl, setKeyBaseUrl] = useState('');
  const [keyApiKey, setKeyApiKey] = useState('');
  const [keyModelName, setKeyModelName] = useState('');
  const [keySaving, setKeySaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [cfgData, annData, statsData, keysData] = await Promise.all([
        adminApi.getConfigs(),
        adminApi.getAnnouncements(),
        adminApi.getStats(),
        adminApi.getSystemKeys(),
      ]);
      setConfigs(cfgData.items || []);
      setAnnouncements(annData.items || []);
      setStats(statsData);
      setSystemKeys(keysData.items || []);
    } catch {}
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const handleAddAnnouncement = async () => {
    if (!annContent.trim()) return;
    try {
      await adminApi.createAnnouncement(annContent, annImportant);
      setAnnContent('');
      setAnnImportant(false);
      await load();
    } catch (e: any) { alert(e.message); }
  };

  const handleDeleteAnnouncement = async (id: number) => {
    if (!confirm('确定删除此公告？')) return;
    try { await adminApi.deleteAnnouncement(id); await load(); } catch {}
  };

  const handleAddSystemKey = async () => {
    if (!keyApiKey || keyApiKey.length < 10) { alert('API Key 长度不足'); return; }
    setKeySaving(true);
    try {
      await adminApi.addSystemKey({
        model_type: keyModelType, provider: keyProvider,
        api_key: keyApiKey,
        base_url: keyBaseUrl || undefined,
        model_name: keyModelName || undefined,
      });
      setShowKeyForm(false); setKeyApiKey(''); setKeyBaseUrl(''); setKeyModelName('');
      await load();
    } catch (e: any) { alert(e.message); }
    setKeySaving(false);
  };

  const handleVerifySystemKey = async (id: number) => {
    try {
      const res = await adminApi.verifySystemKey(id);
      alert(res.message);
      await load();
    } catch (e: any) { alert(e.message); }
  };

  const handleDeleteSystemKey = async (id: number) => {
    if (!confirm('确定删除此系统API Key？')) return;
    try { await adminApi.deleteSystemKey(id); await load(); } catch {}
  };

  if (loading) return <div className="flex justify-center py-20"><div className="w-6 h-6 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" /></div>;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-[var(--text-primary)]">系统配置</h1>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: '总用户数', value: stats.total_users, color: 'from-indigo-500 to-purple-600' },
            { label: '今日任务', value: stats.today_tasks, color: 'from-emerald-500 to-teal-600' },
            { label: '总任务数', value: stats.total_tasks, color: 'from-amber-500 to-orange-600' },
            { label: '待审核申请', value: stats.pending_applications, color: 'from-rose-500 to-pink-600' },
          ].map((s) => (
            <div key={s.label} className="tech-panel p-4">
              <div className="text-xs text-[var(--text-muted)] mb-1">{s.label}</div>
              <div className={`text-2xl font-bold bg-gradient-to-r ${s.color} bg-clip-text text-transparent`}>{s.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* System API Keys */}
      <div className="tech-panel p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-[var(--text-primary)]">系统共享 API Key</h2>
          <button onClick={() => setShowKeyForm(true)} className="btn-primary text-xs py-1.5 px-4">+ 添加</button>
        </div>
        <p className="text-xs text-[var(--text-muted)] mb-4">管理员配置的系统级 API Key，审核通过的用户在没有自己的 Key 时会自动使用这些</p>

        {systemKeys.length === 0 ? (
          <p className="text-[var(--text-muted)] text-sm py-4 text-center">暂未配置系统 API Key</p>
        ) : (
          <div className="divide-y divide-[var(--border-subtle)]">
            {systemKeys.map((k: any) => (
              <div key={k.id} className="py-3 flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono px-1.5 py-0.5 bg-[var(--badge-bg)] text-[var(--text-secondary)]">{k.model_type}</span>
                    <span className="text-sm font-medium text-[var(--text-primary)]">{k.provider}</span>
                    {k.model_name && <span className="text-xs text-[var(--text-muted)]">· {k.model_name}</span>}
                    <span className={`px-1.5 py-0.5 text-[10px] font-bold ${k.is_verified ? 'bg-green-500/20 text-green-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
                      {k.is_verified ? '已验证' : '未验证'}
                    </span>
                  </div>
                  <div className="text-xs text-[var(--text-muted)] mt-0.5 font-mono">{k.api_key_preview}</div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button onClick={() => handleVerifySystemKey(k.id)} className="btn-ghost text-xs py-1 px-2">验证</button>
                  <button onClick={() => handleDeleteSystemKey(k.id)} className="text-xs text-red-400 hover:text-red-300 px-2 py-1">删除</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add System Key Modal */}
      {showKeyForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowKeyForm(false)}>
          <div className="tech-panel p-6 w-full max-w-md space-y-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-[var(--text-primary)]">添加系统 API Key</h3>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-[var(--text-muted)] mb-1 block">模型类型</label>
                <select value={keyModelType} onChange={(e) => setKeyModelType(e.target.value as any)} className="w-full input-tech text-sm py-2">
                  <option value="chat">Chat 模型</option>
                  <option value="image">Image 模型</option>
                </select>
              </div>
              <div>
                <label className="text-xs text-[var(--text-muted)] mb-1 block">Provider</label>
                <select value={keyProvider} onChange={(e) => setKeyProvider(e.target.value)} className="w-full input-tech text-sm py-2">
                  <option value="openai_compat">OpenAI 兼容</option>
                  <option value="gemini">Google Gemini</option>
                  <option value="anthropic">Anthropic</option>
                </select>
              </div>
            </div>
            <div>
              <label className="text-xs text-[var(--text-muted)] mb-1 block">Base URL (可选)</label>
              <input value={keyBaseUrl} onChange={(e) => setKeyBaseUrl(e.target.value)} placeholder="https://openrouter.ai/api/v1" className="w-full input-tech text-sm" />
            </div>
            <div>
              <label className="text-xs text-[var(--text-muted)] mb-1 block">API Key *</label>
              <input value={keyApiKey} onChange={(e) => setKeyApiKey(e.target.value)} placeholder="sk-..." type="password" className="w-full input-tech text-sm" />
            </div>
            <div>
              <label className="text-xs text-[var(--text-muted)] mb-1 block">模型名称 (可选)</label>
              <input value={keyModelName} onChange={(e) => setKeyModelName(e.target.value)} placeholder="gemini-2.5-pro" className="w-full input-tech text-sm" />
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setShowKeyForm(false)} className="btn-ghost flex-1 py-2 text-sm">取消</button>
              <button onClick={handleAddSystemKey} disabled={keySaving} className="btn-primary flex-1 py-2 text-sm disabled:opacity-50">{keySaving ? '保存中...' : '保存'}</button>
            </div>
          </div>
        </div>
      )}

      {/* System Configs */}
      <div className="tech-panel p-5">
        <h2 className="text-lg font-bold text-[var(--text-primary)] mb-4">系统参数</h2>
        {configs.length === 0 ? (
          <p className="text-[var(--text-muted)] text-sm">暂无配置项（首次启动后会自动创建默认配置）</p>
        ) : (
          <div className="space-y-3">
            {configs.map((c: any) => (
              <div key={c.key} className="flex items-center justify-between py-2 border-b border-[var(--border-subtle)] last:border-0">
                <div>
                  <div className="text-sm font-medium text-[var(--text-primary)]">{c.key}</div>
                  {c.description && <div className="text-xs text-[var(--text-muted)]">{c.description}</div>}
                </div>
                <div className="text-sm text-[var(--text-secondary)] font-mono bg-[var(--badge-bg)] px-3 py-1 rounded">{JSON.stringify(c.value)}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Announcements */}
      <div className="tech-panel p-5">
        <h2 className="text-lg font-bold text-[var(--text-primary)] mb-4">系统公告</h2>

        <div className="flex gap-3 mb-4">
          <textarea value={annContent} onChange={(e) => setAnnContent(e.target.value)} placeholder="输入公告内容..." rows={2} className="flex-1 input-tech text-sm" />
          <div className="flex flex-col gap-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={annImportant} onChange={(e) => setAnnImportant(e.target.checked)} className="rounded" />
              <span className="text-xs text-[var(--text-muted)]">重要</span>
            </label>
            <button onClick={handleAddAnnouncement} disabled={!annContent.trim()} className="btn-primary text-xs py-2 px-4 disabled:opacity-50">发布</button>
          </div>
        </div>

        <div className="space-y-2">
          {announcements.length === 0 ? (
            <p className="text-[var(--text-muted)] text-sm">暂无公告</p>
          ) : (
            announcements.map((a: any) => (
              <div key={a.id} className="flex items-start justify-between py-2 border-b border-[var(--border-subtle)] last:border-0">
                <div className="flex-1">
                  <p className={`text-sm ${a.is_important ? 'text-orange-400 font-medium' : 'text-[var(--text-secondary)]'}`}>
                    {a.is_important && <span className="mr-1">🔥</span>}
                    {a.content}
                  </p>
                  <span className="text-[10px] text-[var(--text-muted)] font-mono">{new Date(a.created_at).toLocaleString()}</span>
                </div>
                <button onClick={() => handleDeleteAnnouncement(a.id)} className="text-[var(--text-faint)] hover:text-red-400 transition-colors ml-3 text-xs">删除</button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
