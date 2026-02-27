'use client';

import { useEffect, useState } from 'react';
import { generateApi } from '@/lib/api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export default function HistoryPage() {
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');

  const load = async (p = 1) => {
    setLoading(true);
    try {
      const data = await generateApi.getHistory(p, 12, filter || undefined);
      setItems(data.items);
      setTotal(data.total);
      setPage(p);
    } catch { }
    setLoading(false);
  };

  useEffect(() => { load(1); }, [filter]);

  const totalPages = Math.ceil(total / 12);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">历史记录</h1>
          <p className="text-[var(--text-muted)] text-sm mt-1">共 {total} 条生成记录</p>
        </div>
        <div className="flex gap-2">
          {['', 'diagram', 'plot'].map((f) => (
            <button key={f} onClick={() => setFilter(f)} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${filter === f ? 'bg-primary-600 text-white' : 'bg-[var(--badge-bg)] text-[var(--text-muted)] hover:text-[var(--text-primary)]'}`}>
              {f === '' ? '全部' : f === 'diagram' ? '示意图' : '统计图'}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-20"><div className="w-6 h-6 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" /></div>
      ) : items.length === 0 ? (
        <div className="tech-panel p-12 text-center">
          <p className="text-[var(--text-muted)]">暂无生成记录</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {items.map((item: any) => (
              <div key={item.task_id} className="tech-panel overflow-hidden group hover:border-primary-500/50 transition-all">
                <div className="aspect-square bg-[var(--bg-inset)] relative overflow-hidden">
                  {item.thumbnail_url || item.image_url ? (
                    <img src={`${API_BASE}${item.thumbnail_url || item.image_url}`} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-[var(--text-faint)]">
                      <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                      </svg>
                    </div>
                  )}
                  <div className="absolute top-2 right-2">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${item.status === 'completed' ? 'bg-green-500/80 text-white' : item.status === 'failed' ? 'bg-red-500/80 text-white' : 'bg-yellow-500/80 text-white'}`}>
                      {item.status === 'completed' ? '完成' : item.status === 'failed' ? '失败' : item.status === 'running' ? '运行中' : '等待'}
                    </span>
                  </div>
                  {item.quality_score && (
                    <div className="absolute bottom-2 left-2 px-1.5 py-0.5 rounded bg-black/60 text-[10px] text-white font-mono">
                      {item.quality_score.toFixed(1)}/10
                    </div>
                  )}
                </div>
                <div className="p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--badge-bg)] text-[var(--text-muted)]">{item.task_type}</span>
                    <span className="text-[10px] text-[var(--text-muted)]">{item.pipeline_mode}</span>
                  </div>
                  <div className="text-[10px] text-[var(--text-muted)] font-mono">{new Date(item.created_at).toLocaleString()}</div>
                </div>
              </div>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex justify-center gap-2 pt-4">
              <button onClick={() => load(page - 1)} disabled={page <= 1} className="btn-ghost text-xs py-1.5 px-3 disabled:opacity-30">上一页</button>
              <span className="text-sm text-[var(--text-muted)] flex items-center px-3">{page} / {totalPages}</span>
              <button onClick={() => load(page + 1)} disabled={page >= totalPages} className="btn-ghost text-xs py-1.5 px-3 disabled:opacity-30">下一页</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
