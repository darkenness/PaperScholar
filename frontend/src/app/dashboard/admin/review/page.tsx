'use client';

import { useEffect, useState } from 'react';
import { adminApi } from '@/lib/api';

export default function AdminReviewPage() {
  const [apps, setApps] = useState<any[]>([]);
  const [filter, setFilter] = useState('pending');
  const [loading, setLoading] = useState(true);
  const [reviewComment, setReviewComment] = useState('');
  const [reviewingId, setReviewingId] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await adminApi.getApplications(filter);
      setApps(data.items || []);
    } catch {}
    setLoading(false);
  };

  useEffect(() => { load(); }, [filter]);

  const handleReview = async (appId: number, status: 'approved' | 'rejected') => {
    try {
      await adminApi.reviewApplication(appId, { status, comment: reviewComment || undefined });
      setReviewingId(null);
      setReviewComment('');
      await load();
    } catch (e: any) { alert(e.message); }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">API 申请审核</h1>
        <p className="text-[var(--text-muted)] text-sm mt-1">审核用户的系统 API 使用申请</p>
      </div>

      <div className="flex gap-2">
        {[{ v: 'pending', l: '待审核' }, { v: 'approved', l: '已批准' }, { v: 'rejected', l: '已拒绝' }, { v: 'all', l: '全部' }].map((f) => (
          <button key={f.v} onClick={() => setFilter(f.v)} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${filter === f.v ? 'bg-primary-600 text-white' : 'bg-[var(--badge-bg)] text-[var(--text-muted)] hover:text-[var(--text-primary)]'}`}>
            {f.l}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><div className="w-6 h-6 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" /></div>
      ) : apps.length === 0 ? (
        <div className="tech-panel p-12 text-center text-[var(--text-muted)]">暂无{filter === 'pending' ? '待审核' : ''}申请</div>
      ) : (
        <div className="space-y-4">
          {apps.map((app: any) => (
            <div key={app.id} className="tech-panel p-5">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-500 to-purple-500 flex items-center justify-center text-xs font-bold text-white">
                      {app.username?.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <span className="font-medium text-[var(--text-primary)]">{app.username}</span>
                      <span className="text-xs text-[var(--text-muted)] ml-2">{app.email}</span>
                    </div>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${app.status === 'approved' ? 'bg-green-500/20 text-green-400' : app.status === 'rejected' ? 'bg-red-500/20 text-red-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
                      {app.status === 'approved' ? '已批准' : app.status === 'rejected' ? '已拒绝' : '待审核'}
                    </span>
                  </div>
                  <p className="text-sm text-[var(--text-secondary)] mb-1">{app.reason}</p>
                  <p className="text-[10px] text-[var(--text-muted)] font-mono">申请时间: {new Date(app.created_at).toLocaleString()}</p>
                  {app.review_comment && <p className="text-xs text-[var(--text-muted)] mt-1">审核备注: {app.review_comment}</p>}
                </div>
              </div>

              {app.status === 'pending' && (
                <div className="mt-4 border-t border-[var(--border-subtle)] pt-4">
                  {reviewingId === app.id ? (
                    <div className="space-y-3">
                      <textarea value={reviewComment} onChange={(e) => setReviewComment(e.target.value)} placeholder="审核备注（可选）" rows={2} className="w-full input-tech text-sm" />
                      <div className="flex gap-2">
                        <button onClick={() => handleReview(app.id, 'approved')} className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg text-xs font-bold transition-all">批准</button>
                        <button onClick={() => handleReview(app.id, 'rejected')} className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-xs font-bold transition-all">拒绝</button>
                        <button onClick={() => { setReviewingId(null); setReviewComment(''); }} className="btn-ghost text-xs py-2">取消</button>
                      </div>
                    </div>
                  ) : (
                    <button onClick={() => setReviewingId(app.id)} className="btn-primary text-xs py-2 px-4">审核此申请</button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
