'use client';

import { useState, useRef, useEffect } from 'react';
import { generateApi } from '@/lib/api';
import ModelSelector, { type ModelSelection } from '@/components/ModelSelector';
import ImageLightbox from '@/components/ImageLightbox';
import EvolutionTimeline from '@/components/EvolutionTimeline';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

// Diagram pipeline modes — aligned with PaperBanana demo
const DIAGRAM_PIPELINE_MODES = [
  { value: 'demo_full', label: '完整Pipeline（推荐）', desc: 'Retriever → Planner → Stylist → Visualizer → Critic → Visualizer（Stylist 可让图更美观，但可能过度简化，建议两种模式都试试）' },
  { value: 'demo_planner_critic', label: 'Planner + Critic', desc: 'Planner → Visualizer → Critic → Visualizer' },
  { value: 'dev_planner_stylist', label: 'Planner + Stylist（无Critic）', desc: 'Retriever → Planner → Stylist → Visualizer' },
  { value: 'dev_planner', label: '仅Planner（无Critic）', desc: 'Retriever → Planner → Visualizer' },
  { value: 'vanilla', label: '直接生成', desc: '无规划，直接生成' },
];

// Plot pipeline modes — same agent chain structure, but Visualizer uses code generation
const PLOT_PIPELINE_MODES = [
  { value: 'demo_full', label: '完整Pipeline（推荐）', desc: 'Retriever → Planner → Stylist → Visualizer(matplotlib) → Critic → Visualizer' },
  { value: 'demo_planner_critic', label: 'Planner + Critic', desc: 'Planner → Visualizer(matplotlib) → Critic → Visualizer' },
  { value: 'dev_planner', label: '仅Planner', desc: 'Retriever → Planner → Visualizer(matplotlib)' },
  { value: 'vanilla', label: '直接生成', desc: '无规划，直接生成代码' },
];

const RETRIEVAL_SETTINGS = [
  { value: 'auto', label: '自动检索' },
  { value: 'random', label: '随机参考' },
  { value: 'none', label: '无参考' },
];

const DIAGRAM_ASPECT_RATIOS = ['1:1', '16:9', '4:3', '3:2', '21:9'];

interface SSEEvent {
  type: string;
  data: any;
  time: string;
}

export default function GeneratePage() {
  const [content, setContent] = useState('');
  const [caption, setCaption] = useState('');
  const [taskType, setTaskType] = useState('diagram');
  const [pipelineMode, setPipelineMode] = useState('demo_full');
  const [retrievalSetting, setRetrievalSetting] = useState('auto');
  const [numCandidates, setNumCandidates] = useState(1);
  const [aspectRatio, setAspectRatio] = useState('16:9');
  const [maxCriticRounds, setMaxCriticRounds] = useState(3);
  const [retrieverContentLimit, setRetrieverContentLimit] = useState<number | null>(null);
  const [retrieverTopK, setRetrieverTopK] = useState(10);
  const [retrieverPoolSize, setRetrieverPoolSize] = useState<number | null>(null);

  const [modelSel, setModelSel] = useState<ModelSelection>({ chatModelName: '', chatKeyId: null, imageModelName: '', imageKeyId: null });

  const [extracting, setExtracting] = useState(false);
  const [loading, setLoading] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [currentStage, setCurrentStage] = useState('');
  const [progress, setProgress] = useState(0);
  const [previewImages, setPreviewImages] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [isDone, setIsDone] = useState(false);
  const [taskStatus, setTaskStatus] = useState<'idle' | 'running' | 'completed' | 'failed' | 'cancelled'>('idle');
  const evtSourceRef = useRef<EventSource | null>(null);
  const [finalResults, setFinalResults] = useState<any>(null);
  const [activeCandidateIdx, setActiveCandidateIdx] = useState(0);
  const [loadingResults, setLoadingResults] = useState(false);

  // Fetch final results when generation completes
  useEffect(() => {
    if (taskStatus !== 'completed' || !taskId) return;
    (async () => {
      setLoadingResults(true);
      try {
        const data = await generateApi.getTask(taskId);
        setFinalResults(data);
        setActiveCandidateIdx(0);
      } catch (e: any) {
        console.error('Failed to load final results:', e);
      }
      setLoadingResults(false);
    })();
  }, [taskStatus, taskId]);

  const handleExtractFromPaper = async (file: File) => {
    setExtracting(true);
    setError('');
    const token = localStorage.getItem('token');
    const formData = new FormData();
    formData.append('file', file);
    if (modelSel.chatModelName) formData.append('chat_model_name', modelSel.chatModelName);
    if (modelSel.chatKeyId) formData.append('chat_key_id', String(modelSel.chatKeyId));

    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';
      const res = await fetch(`${API_BASE}/api/v1/edit/extract-methodology`, {
        method: 'POST', body: formData,
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: '提取失败' }));
        throw new Error(err.detail || '提取失败');
      }
      const data = await res.json();
      setContent(data.methodology);
    } catch (e: any) {
      setError(e.message || '论文方法论提取失败');
    }
    setExtracting(false);
  };

  const handleGenerate = async () => {
    if (!content.trim() || !caption.trim()) {
      setError(taskType === 'diagram' ? '请输入方法描述和图表说明' : '请输入原始数据和可视化意图');
      return;
    }
    setError('');
    setLoading(true);
    setEvents([]);
    setPreviewImages([]);
    setIsDone(false);
    setFinalResults(null);
    setActiveCandidateIdx(0);
    setProgress(0);
    setCurrentStage('');

    try {
      const res = await generateApi.create({
        task_type: taskType,
        content,
        visual_intent: caption,
        pipeline_mode: pipelineMode,
        retrieval_setting: retrievalSetting,
        num_candidates: numCandidates,
        aspect_ratio: taskType === 'diagram' ? aspectRatio : undefined,
        max_critic_rounds: maxCriticRounds,
        retriever_content_limit: retrieverContentLimit,
        retriever_top_k: retrieverTopK,
        retriever_pool_size: retrieverPoolSize,
        chat_model_name: modelSel.chatModelName || undefined,
        chat_key_id: modelSel.chatKeyId || undefined,
        image_model_name: modelSel.imageModelName || undefined,
        image_key_id: modelSel.imageKeyId || undefined,
      });

      setTaskId(res.task_id);
      setTaskStatus('running');

      // Connect to SSE stream with token as query param (EventSource can't send headers)
      const token = localStorage.getItem('token');
      const evtSource = new EventSource(
        `${generateApi.streamUrl(res.task_id)}?token=${encodeURIComponent(token || '')}`,
      );
      evtSourceRef.current = evtSource;

      evtSource.addEventListener('stage', (e) => {
        const data = JSON.parse(e.data);
        const now = new Date().toLocaleTimeString();
        setEvents((prev) => [...prev, { type: 'stage', data, time: now }]);
        setCurrentStage(data.name || '');
        if (data.progress) setProgress((prev) => Math.max(prev, data.progress));
      });

      evtSource.addEventListener('intermediate', (e) => {
        const data = JSON.parse(e.data);
        const now = new Date().toLocaleTimeString();
        setEvents((prev) => [...prev, { type: 'intermediate', data, time: now }]);
        if (data.type === 'image' && data.image_url) {
          setPreviewImages((prev) => [...prev, data.image_url]);
        }
      });

      evtSource.addEventListener('done', (e) => {
        const data = JSON.parse(e.data);
        setIsDone(true);
        setProgress(1);
        setCurrentStage('');
        setLoading(false);
        evtSourceRef.current = null;
        if (data.status === 'failed') {
          setTaskStatus('failed');
          setError(data.message || '生成失败，请检查 API 配置或稍后重试');
        } else if (data.status === 'cancelled') {
          setTaskStatus('cancelled');
        } else {
          setTaskStatus('completed');
        }
        evtSource.close();
      });

      evtSource.addEventListener('error', (e) => {
        try {
          const data = JSON.parse((e as MessageEvent).data);
          const now = new Date().toLocaleTimeString();
          setEvents((prev) => [...prev, { type: 'error', data, time: now }]);
          setError(data.message || '生成过程中发生错误');
          setTaskStatus('failed');
        } catch {}
      });

      evtSource.onerror = () => {
        setLoading(false);
        evtSourceRef.current = null;
        evtSource.close();
      };
    } catch (err: any) {
      setError(err.message || '创建任务失败');
      setLoading(false);
      setTaskStatus('idle');
    }
  };

  const handleCancel = async () => {
    if (!taskId) return;
    try {
      await generateApi.cancel(taskId);
      if (evtSourceRef.current) {
        evtSourceRef.current.close();
        evtSourceRef.current = null;
      }
      setLoading(false);
      setTaskStatus('cancelled');
      setCurrentStage('');
      setError('');
      const now = new Date().toLocaleTimeString();
      setEvents((prev) => [...prev, { type: 'stage', data: { name: 'cancelled', status: '已取消' }, time: now }]);
    } catch (err: any) {
      setError(err.message || '取消失败');
    }
  };

  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="space-y-4">
      {/* Top bar: title + config toggle */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-[var(--text-primary)]">图表生成</h1>
          <p className="text-[var(--text-muted)] text-xs mt-0.5">
            {taskType === 'diagram' ? '示意图模式 · 图像生成' : '统计图模式 · matplotlib'}
            {' · '}{(taskType === 'diagram' ? DIAGRAM_PIPELINE_MODES : PLOT_PIPELINE_MODES).find(m => m.value === pipelineMode)?.label}
            {modelSel.chatModelName && <span className="text-primary-400"> · Chat: {modelSel.chatModelName}</span>}
            {modelSel.imageModelName && <span className="text-primary-400"> · Image: {modelSel.imageModelName}</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Quick task type toggle */}
          <div className="hidden sm:flex items-center border border-[var(--border-main)] text-xs">
            {['diagram', 'plot'].map((t) => (
              <button
                key={t}
                onClick={() => { setTaskType(t); setPipelineMode('demo_full'); if (t === 'plot') setAspectRatio('1:1'); }}
                className={`px-3 py-1.5 font-medium transition-colors ${
                  taskType === t ? 'bg-primary-600 text-white' : 'text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]'
                }`}
              >
                {t === 'diagram' ? '示意图' : '统计图'}
              </button>
            ))}
          </div>
          <button
            onClick={() => setDrawerOpen(true)}
            className="flex items-center gap-2 px-4 py-2 border border-[var(--border-main)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors text-xs font-medium"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
            </svg>
            配置与输入
          </button>
          {loading && (
            <button
              onClick={handleCancel}
              className="px-4 py-2 border border-red-500/50 text-red-400 hover:bg-red-500/10 transition-colors text-xs font-medium"
            >
              取消生成
            </button>
          )}
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="btn-primary py-2 px-5 text-xs disabled:opacity-50"
          >
            {loading ? '生成中...' : '开始生成'}
          </button>
        </div>
      </div>

      {error && (
        <div className="text-red-400 text-sm bg-red-500/10 border border-red-500/20 px-4 py-2">{error}</div>
      )}

      {/* Main content: full-width preview area */}
      <div className="space-y-4">
        {/* Progress Bar */}
        {(loading || isDone) && (
          <div className="tech-panel p-4">
            <div className="flex items-center justify-between mb-2">
              <span className={`text-sm font-medium ${
                taskStatus === 'failed' ? 'text-red-400' :
                taskStatus === 'cancelled' ? 'text-yellow-400' :
                isDone ? 'text-green-400' : 'text-[var(--text-primary)]'
              }`}>
                {taskStatus === 'failed' ? '生成失败' :
                 taskStatus === 'cancelled' ? '已取消' :
                 isDone ? '生成完成' :
                 currentStage ? `正在执行: ${currentStage}` : '准备中...'}
              </span>
              <span className="text-xs text-[var(--text-muted)]">{Math.round(progress * 100)}%</span>
            </div>
            {taskStatus === 'failed' && error && (
              <div className="mt-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 px-3 py-2 rounded">
                {error}
              </div>
            )}
            <div className="w-full h-1.5 bg-[var(--bg-inset)] overflow-hidden">
              <div
                className="h-full bg-primary-500 transition-all duration-500"
                style={{ width: `${Math.round(progress * 100)}%` }}
              />
            </div>
          </div>
        )}

        {/* Preview Images — responsive grid (during generation) */}
        {previewImages.length > 0 && !finalResults && (
          <div className="tech-panel p-4">
            <h3 className="text-sm font-bold text-[var(--text-primary)] mb-3">中间预览 ({previewImages.length})</h3>
            <div className={`grid gap-4 ${
              previewImages.length === 1 ? 'grid-cols-1 max-w-2xl mx-auto' :
              previewImages.length === 2 ? 'grid-cols-1 md:grid-cols-2' :
              previewImages.length <= 4 ? 'grid-cols-2 md:grid-cols-2 lg:grid-cols-4' :
              'grid-cols-2 md:grid-cols-3 lg:grid-cols-5'
            }`}>
              {previewImages.map((url, i) => (
                <ImageLightbox key={i} src={url} alt={`Preview ${i + 1}`}>
                  <div className="overflow-hidden border border-[var(--border-main)] bg-white group">
                    <img src={url} alt={`Preview ${i + 1}`} className="w-full h-auto group-hover:scale-105 transition-transform duration-300" />
                  </div>
                </ImageLightbox>
              ))}
            </div>
          </div>
        )}

        {/* Events Log */}
        {events.length > 0 && (
          <div className="tech-panel p-4">
            <details className={finalResults ? '' : 'open'}>
              <summary className="text-sm font-bold text-[var(--text-primary)] mb-3 cursor-pointer select-none">
                Pipeline 日志 ({events.length})
              </summary>
              <div className="max-h-60 overflow-y-auto space-y-1.5">
                {events.map((evt, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs">
                    <span className="text-[var(--text-muted)] font-mono shrink-0">{evt.time}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold shrink-0 ${
                      evt.type === 'stage' ? 'bg-primary-500/20 text-primary-400' :
                      evt.type === 'intermediate' ? 'bg-emerald-500/20 text-emerald-400' :
                      'bg-gray-500/20 text-gray-400'
                    }`}>
                      {evt.type}
                    </span>
                    <span className="text-[var(--text-secondary)] break-all">
                      {evt.type === 'stage' ? `${evt.data.name} - ${evt.data.status}` :
                       evt.data.type === 'text' ? evt.data.content?.substring(0, 150) + '...' :
                       evt.data.type === 'image' ? `[图片] ${evt.data.stage || ''}` :
                       JSON.stringify(evt.data).substring(0, 100)}
                    </span>
                  </div>
                ))}
              </div>
            </details>
          </div>
        )}

        {/* ===== Final Results Section ===== */}
        {taskStatus === 'completed' && (loadingResults || finalResults) && (
          <div className="space-y-4">
            {loadingResults ? (
              <div className="tech-panel p-8 flex items-center justify-center gap-3">
                <div className="w-5 h-5 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
                <span className="text-sm text-[var(--text-muted)]">加载最终结果...</span>
              </div>
            ) : finalResults?.results?.length > 0 && (
              <>
                {/* Results header */}
                <div className="tech-panel p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <h3 className="text-sm font-bold text-[var(--text-primary)]">
                        生成结果 ({finalResults.results.length} 张候选图)
                      </h3>
                      {finalResults.completed_at && (
                        <span className="text-[10px] text-[var(--text-faint)] font-mono">
                          {new Date(finalResults.completed_at).toLocaleString()}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {taskId && (
                        <a
                          href={`${API_BASE}${generateApi.downloadZip(taskId)}`}
                          className="btn-ghost text-xs py-1.5 px-3 flex items-center gap-1.5"
                          onClick={(e) => {
                            e.preventDefault();
                            const token = localStorage.getItem('token');
                            window.open(`${API_BASE}${generateApi.downloadZip(taskId)}?token=${encodeURIComponent(token || '')}`, '_blank');
                          }}
                        >
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                          </svg>
                          下载全部 (ZIP)
                        </a>
                      )}
                    </div>
                  </div>
                </div>

                {/* Candidates overview grid */}
                <div className={`grid gap-3 ${
                  finalResults.results.length === 1 ? 'grid-cols-1 max-w-2xl mx-auto' :
                  finalResults.results.length === 2 ? 'grid-cols-2' :
                  finalResults.results.length <= 4 ? 'grid-cols-2 lg:grid-cols-4' :
                  'grid-cols-2 md:grid-cols-3 lg:grid-cols-5'
                }`}>
                  {finalResults.results.map((r: any, i: number) => (
                    <div
                      key={r.id}
                      className={`tech-panel overflow-hidden cursor-pointer transition-all ${
                        activeCandidateIdx === i
                          ? 'ring-2 ring-primary-500 border-primary-500/50'
                          : 'hover:border-primary-500/30'
                      }`}
                      onClick={() => setActiveCandidateIdx(i)}
                    >
                      {r.image_url ? (
                        <div className="aspect-square bg-white overflow-hidden">
                          <img
                            src={`${API_BASE}${r.image_url}`}
                            alt={`Candidate ${i}`}
                            className="w-full h-full object-cover"
                          />
                        </div>
                      ) : (
                        <div className="aspect-square bg-[var(--bg-inset)] flex items-center justify-center">
                          <span className="text-[var(--text-faint)] text-xs">无图片</span>
                        </div>
                      )}
                      <div className="p-2 flex items-center justify-between">
                        <span className="text-xs font-medium text-[var(--text-secondary)]">
                          候选 {i}
                        </span>
                        {r.quality_score != null && (
                          <span className="text-[10px] font-bold text-primary-400">
                            {r.quality_score.toFixed(1)}/10
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Active candidate detail view */}
                {finalResults.results[activeCandidateIdx] && (() => {
                  const activeResult = finalResults.results[activeCandidateIdx];
                  const activeImageUrl = activeResult.image_url ? `${API_BASE}${activeResult.image_url}` : null;

                  return (
                    <div className="tech-panel p-5">
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                          {/* Candidate selector tabs */}
                          <div className="flex items-center gap-1 bg-[var(--bg-inset)] rounded-lg p-0.5">
                            {finalResults.results.map((_: any, i: number) => (
                              <button
                                key={i}
                                onClick={() => setActiveCandidateIdx(i)}
                                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                                  activeCandidateIdx === i
                                    ? 'bg-primary-600 text-white shadow-sm'
                                    : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                                }`}
                              >
                                候选 {i}
                                {finalResults.results[i].quality_score != null && (
                                  <span className="ml-1 opacity-70">
                                    ({finalResults.results[i].quality_score.toFixed(1)})
                                  </span>
                                )}
                              </button>
                            ))}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {activeResult.svg_url && (
                            <a href={`${API_BASE}${activeResult.svg_url}`} download className="btn-ghost text-xs py-1.5 px-3">
                              下载 SVG
                            </a>
                          )}
                          {activeImageUrl && (
                            <a href={activeImageUrl} download className="btn-primary text-xs py-1.5 px-3">
                              下载图片
                            </a>
                          )}
                        </div>
                      </div>

                      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                        {/* Main image — large with lightbox */}
                        <div className="lg:col-span-2">
                          {activeImageUrl ? (
                            <ImageLightbox src={activeImageUrl} alt={`Candidate ${activeCandidateIdx}`}>
                              <div className="bg-white rounded-lg overflow-hidden border border-[var(--border-main)] group relative">
                                <img
                                  src={activeImageUrl}
                                  alt={`Candidate ${activeCandidateIdx}`}
                                  className="w-full h-auto group-hover:scale-[1.02] transition-transform duration-300"
                                />
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
                            <div className="bg-[var(--bg-inset)] rounded-lg flex items-center justify-center aspect-video">
                              <span className="text-[var(--text-faint)]">无图片</span>
                            </div>
                          )}
                        </div>

                        {/* Right panel: score + evolution timeline */}
                        <div className="space-y-4">
                          {/* Quality Score */}
                          {activeResult.quality_score != null && (
                            <div className="tech-panel p-4">
                              <h4 className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-wider mb-2">质量评分</h4>
                              <div className="flex items-end gap-1">
                                <span className="text-3xl font-bold text-primary-400">
                                  {activeResult.quality_score.toFixed(1)}
                                </span>
                                <span className="text-sm text-[var(--text-faint)] mb-1">/ 10</span>
                              </div>
                            </div>
                          )}

                          {/* Evolution Timeline */}
                          {taskId && (
                            <div className="tech-panel p-4">
                              <EvolutionTimeline taskId={taskId} compact={true} />
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })()}
              </>
            )}
          </div>
        )}

        {/* Empty State */}
        {!loading && !isDone && events.length === 0 && (
          <div className="tech-panel p-16 text-center">
            <svg className="w-20 h-20 mx-auto mb-4 text-[var(--text-faint)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={0.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <h3 className="text-lg font-medium text-[var(--text-secondary)] mb-2">等待生成</h3>
            <p className="text-sm text-[var(--text-muted)] mb-6">点击右上角「配置与输入」填写内容，然后点击「开始生成」</p>
            <button onClick={() => setDrawerOpen(true)} className="btn-primary text-xs py-2 px-6">
              打开配置面板
            </button>
          </div>
        )}
      </div>

      {/* ===== Floating Config Drawer ===== */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 flex justify-end" onClick={() => setDrawerOpen(false)}>
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/30" />
          {/* Drawer */}
          <div
            className="relative w-full max-w-md h-full bg-[var(--bg-main)] border-l border-[var(--border-main)] flex flex-col shadow-2xl drawer-slide-in"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Drawer header */}
            <div className="h-14 flex items-center justify-between px-5 border-b border-[var(--border-main)] shrink-0">
              <h2 className="text-sm font-bold text-[var(--text-primary)]">生成配置</h2>
              <button onClick={() => setDrawerOpen(false)} className="w-8 h-8 flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Drawer body — scrollable */}
            <div className="flex-1 overflow-y-auto p-5 space-y-5">
              {/* Task Type */}
              <div>
                <label className="text-[11px] font-bold text-[var(--text-muted)] mb-2 block uppercase tracking-wider">图表类型</label>
                <div className="flex gap-2">
                  {['diagram', 'plot'].map((t) => (
                    <button
                      key={t}
                      onClick={() => { setTaskType(t); setPipelineMode('demo_full'); if (t === 'plot') setAspectRatio('1:1'); }}
                      className={`flex-1 py-2 text-sm font-medium transition-all ${
                        taskType === t ? 'bg-primary-600 text-white' : 'bg-[var(--badge-bg)] text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                      }`}
                    >
                      {t === 'diagram' ? '示意图' : '统计图'}
                    </button>
                  ))}
                </div>
                <p className="text-[10px] text-[var(--text-faint)] mt-1">
                  {taskType === 'diagram'
                    ? '基于方法描述生成论文示意图（使用图像生成模型）'
                    : '基于原始数据生成统计图表（使用 matplotlib 代码生成）'}
                </p>
              </div>

              {/* Content */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-[11px] font-bold text-[var(--text-muted)] uppercase tracking-wider">
                    {taskType === 'diagram' ? '方法描述' : '原始数据'}
                  </label>
                  {taskType === 'diagram' && (
                    <label className={`flex items-center gap-1.5 px-2.5 py-1 text-[10px] font-medium cursor-pointer transition-all ${
                      extracting ? 'opacity-50 pointer-events-none' : 'hover:bg-primary-500/10 text-primary-400 hover:text-primary-300'
                    }`}>
                      <input
                        type="file"
                        accept=".pdf,.md,.txt,.tex"
                        className="hidden"
                        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleExtractFromPaper(f); e.target.value = ''; }}
                      />
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                      </svg>
                      {extracting ? '提取中...' : '从论文提取'}
                    </label>
                  )}
                </div>
                <textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder={taskType === 'diagram'
                    ? '粘贴你的论文方法部分内容 (推荐 Markdown 格式)\n\n或点击右上方「从论文提取」上传 PDF 自动提取方法论...'
                    : '粘贴原始数据，支持 JSON、表格或 CSV 格式...'}
                  rows={6}
                  className="w-full input-tech resize-none text-sm"
                />
              </div>

              {/* Caption */}
              <div>
                <label className="text-[11px] font-bold text-[var(--text-muted)] mb-1.5 block uppercase tracking-wider">
                  {taskType === 'diagram' ? '图表说明' : '可视化意图'}
                </label>
                <textarea
                  value={caption}
                  onChange={(e) => setCaption(e.target.value)}
                  placeholder={taskType === 'diagram'
                    ? 'Figure 1: Overview of our framework...'
                    : '柱状图对比各方法在不同数据集上的准确率...'}
                  rows={3}
                  className="w-full input-tech resize-none text-sm"
                />
              </div>

              {/* Model selection */}
              <ModelSelector showChat={true} showImage={true} onChange={setModelSel} />

              {/* Pipeline settings */}
              <div className="space-y-3 pt-2 border-t border-[var(--border-subtle)]">
                <label className="text-[11px] font-bold text-[var(--text-muted)] block uppercase tracking-wider">Pipeline 设置</label>
                <div>
                  <label className="text-[11px] text-[var(--text-muted)] mb-1 block">模式</label>
                  <select value={pipelineMode} onChange={(e) => setPipelineMode(e.target.value)} className="w-full input-tech text-sm py-2">
                    {(taskType === 'diagram' ? DIAGRAM_PIPELINE_MODES : PLOT_PIPELINE_MODES).map((m) => (
                      <option key={m.value} value={m.value}>{m.label}</option>
                    ))}
                  </select>
                  <p className="text-[10px] text-[var(--text-faint)] mt-1">
                    {(taskType === 'diagram' ? DIAGRAM_PIPELINE_MODES : PLOT_PIPELINE_MODES).find(m => m.value === pipelineMode)?.desc}
                  </p>
                </div>

                <div className={`grid gap-3 ${taskType === 'diagram' ? 'grid-cols-2' : 'grid-cols-1'}`}>
                  <div>
                    <label className="text-[11px] text-[var(--text-muted)] mb-1 block">参考图检索</label>
                    <select value={retrievalSetting} onChange={(e) => setRetrievalSetting(e.target.value)} className="w-full input-tech text-sm py-2">
                      {RETRIEVAL_SETTINGS.map((s) => (
                        <option key={s.value} value={s.value}>{s.label}</option>
                      ))}
                    </select>
                  </div>
                  {taskType === 'diagram' && (
                    <div>
                      <label className="text-[11px] text-[var(--text-muted)] mb-1 block">宽高比</label>
                      <select value={aspectRatio} onChange={(e) => setAspectRatio(e.target.value)} className="w-full input-tech text-sm py-2">
                        {DIAGRAM_ASPECT_RATIOS.map((r) => (
                          <option key={r} value={r}>{r}</option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[11px] text-[var(--text-muted)] mb-1 block">候选数量: {numCandidates}</label>
                    <input type="range" min={1} max={10} value={numCandidates} onChange={(e) => setNumCandidates(Number(e.target.value))} className="w-full" />
                  </div>
                  <div>
                    <label className="text-[11px] text-[var(--text-muted)] mb-1 block">Critic轮数: {maxCriticRounds}</label>
                    <input type="range" min={1} max={5} value={maxCriticRounds} onChange={(e) => setMaxCriticRounds(Number(e.target.value))} className="w-full" />
                  </div>
                </div>

                {/* Retriever context strategy */}
                <div className="space-y-3 pt-2 border-t border-[var(--border-subtle)]">
                  <label className="text-[11px] font-bold text-[var(--text-muted)] block uppercase tracking-wider">Retriever 上下文策略</label>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-[11px] text-[var(--text-muted)] mb-1 block">内容截断</label>
                      <select
                        value={retrieverContentLimit === null ? 'none' : String(retrieverContentLimit)}
                        onChange={(e) => setRetrieverContentLimit(e.target.value === 'none' ? null : Number(e.target.value))}
                        className="w-full input-tech text-sm py-2"
                      >
                        <option value="none">不截断（完整内容）</option>
                        <option value="500">500 字</option>
                        <option value="1000">1000 字</option>
                        <option value="2000">2000 字</option>
                        <option value="5000">5000 字</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-[11px] text-[var(--text-muted)] mb-1 block">TopK 示例数: {retrieverTopK}</label>
                      <input type="range" min={1} max={20} value={retrieverTopK} onChange={(e) => setRetrieverTopK(Number(e.target.value))} className="w-full" />
                    </div>
                  </div>
                  <div>
                    <label className="text-[11px] text-[var(--text-muted)] mb-1 block">候选池大小</label>
                    <select
                      value={retrieverPoolSize === null ? 'default' : String(retrieverPoolSize)}
                      onChange={(e) => setRetrieverPoolSize(e.target.value === 'default' ? null : Number(e.target.value))}
                      className="w-full input-tech text-sm py-2"
                    >
                      <option value="default">默认（示意图200 / 统计图全部）</option>
                      <option value="50">50 条</option>
                      <option value="100">100 条</option>
                      <option value="200">200 条</option>
                      <option value="500">500 条</option>
                      <option value="0">全部（不限制）</option>
                    </select>
                    <p className="text-[10px] text-[var(--text-faint)] mt-1">
                      不截断 + 全部候选池 = 最接近 PaperBanana 原版（需要模型支持超长上下文）
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Drawer footer */}
            <div className="shrink-0 p-4 border-t border-[var(--border-main)]">
              {error && (
                <div className="text-red-400 text-xs bg-red-500/10 border border-red-500/20 px-3 py-1.5 mb-3">{error}</div>
              )}
              <button
                onClick={() => { setDrawerOpen(false); handleGenerate(); }}
                disabled={loading}
                className="w-full btn-primary py-3 disabled:opacity-50"
              >
                {loading ? '生成中...' : '确认并生成'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
