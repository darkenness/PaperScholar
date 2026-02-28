'use client';

import { useEffect, useState, useCallback } from 'react';
import { generateApi } from '@/lib/api';
import { toast } from 'sonner';
import ImageLightbox from '@/components/ImageLightbox';
import EvolutionTimeline from '@/components/EvolutionTimeline';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    completed: { label: '完成', cls: 'bg-green-500/80 text-white' },
    failed: { label: '失败', cls: 'bg-red-500/80 text-white' },
    running: { label: '运行中', cls: 'bg-yellow-500/80 text-white' },
    pending: { label: '等待', cls: 'bg-gray-500/80 text-white' },
    cancelled: { label: '已取消', cls: 'bg-gray-500/80 text-white' },
  };
  const s = map[status] || map.pending;
  return <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${s.cls}`}>{s.label}</span>;
}

function TypeBadge({ type }: { type: string }) {
  const map: Record<string, string> = {
    diagram: '示意图', plot: '统计图',
    refine_enhance: '增强', refine_style: '风格迁移', edit: '编辑',
  };
  const label = map[type] || type;
  const color = type.startsWith('refine') ? 'bg-purple-500/20 text-purple-400'
    : type === 'edit' ? 'bg-blue-500/20 text-blue-400'
    : 'bg-[var(--badge-bg)] text-[var(--text-muted)]';
  return <span className={`text-[10px] px-1.5 py-0.5 rounded ${color}`}>{label}</span>;
}

/* ──────── Detail Modal ──────── */
function DetailModal({ item, onClose, onDelete, onToggleFavorite }: {
  item: any;
  onClose: () => void;
  onDelete: (id: string) => void;
  onToggleFavorite: (resultId: number, current: boolean) => void;
}) {
  const [taskDetail, setTaskDetail] = useState<any>(null);
  const [loadingDetail, setLoadingDetail] = useState(true);
  const [activeCandidateIdx, setActiveCandidateIdx] = useState(0);

  useEffect(() => {
    (async () => {
      try {
        const data = await generateApi.getTask(item.task_id);
        setTaskDetail(data);
      } catch { }
      setLoadingDetail(false);
    })();
  }, [item.task_id]);

  // Active result based on candidate selector
  const activeResult = taskDetail?.results?.[activeCandidateIdx];
  const activeImageUrl = activeResult?.image_url ? `${API_BASE}${activeResult.image_url}` : (item.image_url ? `${API_BASE}${item.image_url}` : null);
  const allResults = taskDetail?.results || [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50" />
      <div className="relative bg-[var(--bg-main)] border border-[var(--border-main)] rounded-xl shadow-2xl w-full max-w-5xl max-h-[92vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3 border-b border-[var(--border-main)] shrink-0">
          <div className="flex items-center gap-3">
            <TypeBadge type={item.task_type} />
            <StatusBadge status={item.status} />
            {item.pipeline_mode && <span className="text-xs text-[var(--text-muted)]">{item.pipeline_mode}</span>}
            <span className="text-xs text-[var(--text-faint)] font-mono">{new Date(item.created_at).toLocaleString()}</span>
          </div>
          <div className="flex items-center gap-2">
            {item.result_id && (
              <button
                onClick={() => onToggleFavorite(item.result_id, item.is_favorited)}
                className={`p-1.5 rounded transition-colors ${item.is_favorited ? 'text-yellow-400 hover:text-yellow-300' : 'text-[var(--text-faint)] hover:text-yellow-400'}`}
                title={item.is_favorited ? '取消收藏' : '收藏'}
              >
                <svg className="w-5 h-5" fill={item.is_favorited ? 'currentColor' : 'none'} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z" />
                </svg>
              </button>
            )}
            {item.status !== 'running' && (
              <button
                onClick={() => { if (confirm('确定删除此记录？')) onDelete(item.task_id); }}
                className="p-1.5 rounded text-[var(--text-faint)] hover:text-red-400 transition-colors"
                title="删除"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                </svg>
              </button>
            )}
            <button onClick={onClose} className="p-1.5 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {loadingDetail ? (
            <div className="flex items-center justify-center py-12 gap-3">
              <div className="w-5 h-5 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
              <span className="text-sm text-[var(--text-muted)]">加载详情...</span>
            </div>
          ) : (
            <>
              {/* Candidate selector tabs (only if multiple candidates) */}
              {allResults.length > 1 && (
                <div>
                  <h4 className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-wider mb-2">
                    候选图 ({allResults.length})
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {allResults.map((r: any, i: number) => (
                      <button
                        key={r.id}
                        onClick={() => setActiveCandidateIdx(i)}
                        className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-medium transition-all ${
                          activeCandidateIdx === i
                            ? 'bg-primary-600 text-white border-primary-500 shadow-sm'
                            : 'bg-[var(--bg-inset)] text-[var(--text-muted)] border-[var(--border-main)] hover:border-primary-500/50 hover:text-[var(--text-primary)]'
                        }`}
                      >
                        {r.image_url && (
                          <img
                            src={`${API_BASE}${r.thumbnail_url || r.image_url}`}
                            alt=""
                            className="w-8 h-8 rounded object-cover"
                          />
                        )}
                        <span>候选 {i}</span>
                        {r.quality_score != null && (
                          <span className={`${activeCandidateIdx === i ? 'opacity-80' : 'text-primary-400'}`}>
                            {r.quality_score.toFixed(1)}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Main content: image + details */}
              <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
                {/* Left: Image (3 cols) */}
                <div className="lg:col-span-3">
                  {activeImageUrl ? (
                    <ImageLightbox src={activeImageUrl} alt={`Candidate ${activeCandidateIdx}`}>
                      <div className="bg-white rounded-lg overflow-hidden border border-[var(--border-main)] group relative">
                        <img src={activeImageUrl} alt="Result" className="w-full h-auto group-hover:scale-[1.02] transition-transform duration-300" />
                        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/10">
                          <span className="px-3 py-1.5 bg-black/60 text-white text-xs rounded-full flex items-center gap-1.5">
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607zM10.5 7.5v6m3-3h-6" />
                            </svg>
                            点击放大
                          </span>
                        </div>
                      </div>
                    </ImageLightbox>
                  ) : (
                    <div className="bg-[var(--bg-inset)] rounded-lg flex items-center justify-center aspect-square">
                      <div className="text-center text-[var(--text-faint)]">
                        <svg className="w-16 h-16 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={0.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                        </svg>
                        <p className="text-sm">{item.status === 'failed' ? '生成失败' : '无图片'}</p>
                      </div>
                    </div>
                  )}
                  {activeImageUrl && (
                    <div className="flex gap-2 mt-3">
                      <a href={activeImageUrl} download className="btn-primary text-xs py-1.5 px-3">下载图片</a>
                      {activeResult?.svg_url && (
                        <a href={`${API_BASE}${activeResult.svg_url}`} download className="btn-ghost text-xs py-1.5 px-3">下载 SVG</a>
                      )}
                    </div>
                  )}
                </div>

                {/* Right: Details (2 cols) */}
                <div className="lg:col-span-2 space-y-4">
                  {/* Quality Score */}
                  {activeResult?.quality_score != null && (
                    <div className="tech-panel p-3">
                      <h4 className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-wider mb-1">质量评分</h4>
                      <div className="flex items-end gap-1">
                        <span className="text-2xl font-bold text-primary-400">{activeResult.quality_score.toFixed(1)}</span>
                        <span className="text-xs text-[var(--text-faint)] mb-0.5">/ 10</span>
                      </div>
                    </div>
                  )}

                  {/* Models */}
                  <div className="space-y-1">
                    <h4 className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider">模型信息</h4>
                    <div className="text-xs text-[var(--text-secondary)] space-y-0.5">
                      {item.chat_model && <p>Chat: <span className="text-primary-400">{item.chat_model}</span></p>}
                      {item.image_model && <p>Image: <span className="text-primary-400">{item.image_model}</span></p>}
                    </div>
                  </div>

                  {item.error_message && (
                    <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 px-3 py-2 rounded">
                      {item.error_message}
                    </div>
                  )}

                  {/* Content */}
                  {item.content && (
                    <div>
                      <h4 className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider mb-1">
                        {item.task_type === 'diagram' ? '方法描述' : '原始数据'}
                      </h4>
                      <p className="text-xs text-[var(--text-secondary)] bg-[var(--bg-inset)] p-2 rounded max-h-24 overflow-y-auto">{item.content}</p>
                    </div>
                  )}

                  {item.visual_intent && (
                    <div>
                      <h4 className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider mb-1">
                        {item.task_type === 'diagram' ? '图表说明' : '可视化意图'}
                      </h4>
                      <p className="text-xs text-[var(--text-secondary)] bg-[var(--bg-inset)] p-2 rounded">{item.visual_intent}</p>
                    </div>
                  )}

                  {/* Evolution Timeline */}
                  {item.status === 'completed' && (
                    <EvolutionTimeline taskId={item.task_id} compact={true} />
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ──────── Main History Page ──────── */
export default function HistoryPage() {
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const [selectedItem, setSelectedItem] = useState<any>(null);

  const load = useCallback(async (p = 1) => {
    setLoading(true);
    try {
      const data = await generateApi.getHistory(p, 12, filter || undefined);
      setItems(data.items);
      setTotal(data.total);
      setPage(p);
    } catch { }
    setLoading(false);
  }, [filter]);

  useEffect(() => { load(1); }, [load]);

  const totalPages = Math.ceil(total / 12);

  const handleDelete = async (taskId: string) => {
    try {
      await generateApi.deleteTask(taskId);
      toast.success('已删除');
      setSelectedItem(null);
      load(page);
    } catch (e: any) { toast.error(e.message); }
  };

  const handleToggleFavorite = async (resultId: number, current: boolean) => {
    try {
      await generateApi.toggleFavorite(resultId, !current);
      // Update local state
      setItems(prev => prev.map(it => it.result_id === resultId ? { ...it, is_favorited: !current } : it));
      if (selectedItem?.result_id === resultId) {
        setSelectedItem({ ...selectedItem, is_favorited: !current });
      }
      toast.success(current ? '已取消收藏' : '已收藏');
    } catch (e: any) { toast.error(e.message); }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">历史记录</h1>
          <p className="text-[var(--text-muted)] text-sm mt-1">共 {total} 条生成记录</p>
        </div>
        <div className="flex gap-1.5 flex-wrap">
          {[
            { value: '', label: '全部' },
            { value: 'diagram', label: '示意图' },
            { value: 'plot', label: '统计图' },
            { value: 'refine_enhance', label: '增强' },
            { value: 'refine_style', label: '风格迁移' },
            { value: 'edit', label: '编辑' },
          ].map((f) => (
            <button key={f.value} onClick={() => setFilter(f.value)} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${filter === f.value ? 'bg-primary-600 text-white' : 'bg-[var(--badge-bg)] text-[var(--text-muted)] hover:text-[var(--text-primary)]'}`}>
              {f.label}
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
              <div
                key={item.task_id}
                className="tech-panel overflow-hidden group hover:border-primary-500/50 transition-all cursor-pointer"
                onClick={() => setSelectedItem(item)}
              >
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
                    <StatusBadge status={item.status} />
                  </div>
                  {item.is_favorited && (
                    <div className="absolute top-2 left-2 text-yellow-400">
                      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z" /></svg>
                    </div>
                  )}
                  {item.quality_score != null && (
                    <div className="absolute bottom-2 left-2 px-1.5 py-0.5 rounded bg-black/60 text-[10px] text-white font-mono">
                      {item.quality_score.toFixed(1)}/10
                    </div>
                  )}
                </div>
                <div className="p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <TypeBadge type={item.task_type} />
                    <span className="text-[10px] text-[var(--text-muted)]">{item.pipeline_mode}</span>
                  </div>
                  {item.visual_intent && (
                    <p className="text-[10px] text-[var(--text-secondary)] truncate mb-1">{item.visual_intent}</p>
                  )}
                  <div className="text-[10px] text-[var(--text-faint)] font-mono">{new Date(item.created_at).toLocaleString()}</div>
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

      {/* Detail Modal */}
      {selectedItem && (
        <DetailModal
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
          onDelete={handleDelete}
          onToggleFavorite={handleToggleFavorite}
        />
      )}
    </div>
  );
}
