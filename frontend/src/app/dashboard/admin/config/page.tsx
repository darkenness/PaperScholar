'use client';

import { useEffect, useState } from 'react';
import { adminApi } from '@/lib/api';
import ProviderManager from '@/components/ProviderManager';

const providerOptionsFor = (type: 'chat' | 'image') => (
  type === 'image'
    ? [
        { value: 'openai_images', label: 'OpenAI Images (/images/generations)' },
        { value: 'openai_compat', label: 'OpenAI 兼容' },
        { value: 'gemini', label: 'Google Gemini' },
      ]
    : [
        { value: 'openai_compat', label: 'OpenAI 兼容' },
        { value: 'gemini', label: 'Google Gemini' },
        { value: 'anthropic', label: 'Anthropic' },
      ]
);

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

  // System Key edit form
  const [editingSysKey, setEditingSysKey] = useState<any>(null);
  const [editSysBaseUrl, setEditSysBaseUrl] = useState('');
  const [editSysApiKey, setEditSysApiKey] = useState('');
  const [editSysModelName, setEditSysModelName] = useState('');
  const [editSysSaving, setEditSysSaving] = useState(false);
  const [verifyingSysId, setVerifyingSysId] = useState<number | null>(null);

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
    setVerifyingSysId(id);
    try {
      const res = await adminApi.verifySystemKey(id);
      alert(res.message);
      await load();
    } catch (e: any) { alert(e.message); }
    setVerifyingSysId(null);
  };

  const openEditSysKey = (k: any) => {
    setEditingSysKey(k);
    setEditSysBaseUrl(k.base_url || '');
    setEditSysApiKey('');
    setEditSysModelName(k.model_name || '');
  };

  const handleEditSysKey = async () => {
    if (!editingSysKey) return;
    if (editSysApiKey && editSysApiKey.length < 10) { alert('API Key 长度不足（至少10位）'); return; }
    setEditSysSaving(true);
    try {
      const payload: any = {};
      if (editSysBaseUrl !== (editingSysKey.base_url || '')) payload.base_url = editSysBaseUrl;
      if (editSysApiKey) payload.api_key = editSysApiKey;
      if (editSysModelName !== (editingSysKey.model_name || '')) payload.model_name = editSysModelName;
      await adminApi.updateSystemKey(editingSysKey.id, payload);
      setEditingSysKey(null);
      await load();
    } catch (e: any) { alert(e.message); }
    setEditSysSaving(false);
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

      <ProviderManager system />

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
