'use client';

import { useEffect, useState } from 'react';
import { adminApi } from '@/lib/api';

export default function AdminConfigPage() {
  const [configs, setConfigs] = useState<any[]>([]);
  const [announcements, setAnnouncements] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [annContent, setAnnContent] = useState('');
  const [annImportant, setAnnImportant] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [cfgData, annData, statsData] = await Promise.all([
        adminApi.getConfigs(),
        adminApi.getAnnouncements(),
        adminApi.getStats(),
      ]);
      setConfigs(cfgData.items || []);
      setAnnouncements(annData.items || []);
      setStats(statsData);
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

  if (loading) return <div className="flex justify-center py-20"><div className="w-6 h-6 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" /></div>;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-white">系统配置</h1>

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
              <div className="text-xs text-gray-400 mb-1">{s.label}</div>
              <div className={`text-2xl font-bold bg-gradient-to-r ${s.color} bg-clip-text text-transparent`}>{s.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* System Configs */}
      <div className="tech-panel p-5">
        <h2 className="text-lg font-bold text-white mb-4">系统参数</h2>
        {configs.length === 0 ? (
          <p className="text-gray-500 text-sm">暂无配置项（首次启动后会自动创建默认配置）</p>
        ) : (
          <div className="space-y-3">
            {configs.map((c: any) => (
              <div key={c.key} className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
                <div>
                  <div className="text-sm font-medium text-white">{c.key}</div>
                  {c.description && <div className="text-xs text-gray-500">{c.description}</div>}
                </div>
                <div className="text-sm text-gray-300 font-mono bg-white/5 px-3 py-1 rounded">{JSON.stringify(c.value)}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Announcements */}
      <div className="tech-panel p-5">
        <h2 className="text-lg font-bold text-white mb-4">系统公告</h2>

        <div className="flex gap-3 mb-4">
          <textarea value={annContent} onChange={(e) => setAnnContent(e.target.value)} placeholder="输入公告内容..." rows={2} className="flex-1 input-tech text-sm" />
          <div className="flex flex-col gap-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={annImportant} onChange={(e) => setAnnImportant(e.target.checked)} className="rounded" />
              <span className="text-xs text-gray-400">重要</span>
            </label>
            <button onClick={handleAddAnnouncement} disabled={!annContent.trim()} className="btn-primary text-xs py-2 px-4 disabled:opacity-50">发布</button>
          </div>
        </div>

        <div className="space-y-2">
          {announcements.length === 0 ? (
            <p className="text-gray-500 text-sm">暂无公告</p>
          ) : (
            announcements.map((a: any) => (
              <div key={a.id} className="flex items-start justify-between py-2 border-b border-white/5 last:border-0">
                <div className="flex-1">
                  <p className={`text-sm ${a.is_important ? 'text-orange-300 font-medium' : 'text-gray-300'}`}>
                    {a.is_important && <span className="mr-1">🔥</span>}
                    {a.content}
                  </p>
                  <span className="text-[10px] text-gray-500 font-mono">{new Date(a.created_at).toLocaleString()}</span>
                </div>
                <button onClick={() => handleDeleteAnnouncement(a.id)} className="text-gray-600 hover:text-red-400 transition-colors ml-3 text-xs">删除</button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
