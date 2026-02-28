'use client';

import { useState, useEffect } from 'react';
import { generateApi, type AvailableModelsResponse } from '@/lib/api';

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

  // Model selection state
  const [availableModels, setAvailableModels] = useState<AvailableModelsResponse | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [chatModelName, setChatModelName] = useState<string>('');
  const [chatKeyId, setChatKeyId] = useState<number | null>(null);
  const [imageModelName, setImageModelName] = useState<string>('');
  const [imageKeyId, setImageKeyId] = useState<number | null>(null);

  const [loading, setLoading] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [currentStage, setCurrentStage] = useState('');
  const [progress, setProgress] = useState(0);
  const [previewImages, setPreviewImages] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [isDone, setIsDone] = useState(false);

  useEffect(() => {
    const fetchModels = async () => {
      setModelsLoading(true);
      try {
        const data = await generateApi.getAvailableModels();
        setAvailableModels(data);
        if (data.chat_models.length === 1) {
          setChatModelName(data.chat_models[0].model_name);
          if (data.chat_models[0].providers.length === 1) {
            setChatKeyId(data.chat_models[0].providers[0].key_id);
          }
        }
        if (data.image_models.length === 1) {
          setImageModelName(data.image_models[0].model_name);
          if (data.image_models[0].providers.length === 1) {
            setImageKeyId(data.image_models[0].providers[0].key_id);
          }
        }
      } catch {
        // Models not available yet; user might not have keys configured
      } finally {
        setModelsLoading(false);
      }
    };
    fetchModels();
  }, []);

  const selectedChatGroup = availableModels?.chat_models.find(m => m.model_name === chatModelName);
  const selectedImageGroup = availableModels?.image_models.find(m => m.model_name === imageModelName);

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
        chat_model_name: chatModelName || undefined,
        chat_key_id: chatKeyId || undefined,
        image_model_name: imageModelName || undefined,
        image_key_id: imageKeyId || undefined,
      });

      setTaskId(res.task_id);

      // Connect to SSE stream with token as query param (EventSource can't send headers)
      const token = localStorage.getItem('token');
      const evtSource = new EventSource(
        `${generateApi.streamUrl(res.task_id)}?token=${encodeURIComponent(token || '')}`,
      );

      evtSource.addEventListener('stage', (e) => {
        const data = JSON.parse(e.data);
        const now = new Date().toLocaleTimeString();
        setEvents((prev) => [...prev, { type: 'stage', data, time: now }]);
        setCurrentStage(data.name || '');
        if (data.progress) setProgress(data.progress);
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
        evtSource.close();
      });

      evtSource.onerror = () => {
        setLoading(false);
        evtSource.close();
      };
    } catch (err: any) {
      setError(err.message || '创建任务失败');
      setLoading(false);
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
            {chatModelName && <span className="text-primary-400"> · Chat: {chatModelName}</span>}
            {imageModelName && <span className="text-primary-400"> · Image: {imageModelName}</span>}
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
              <span className="text-sm font-medium text-[var(--text-primary)]">
                {isDone ? '生成完成' : currentStage ? `正在执行: ${currentStage}` : '准备中...'}
              </span>
              <span className="text-xs text-[var(--text-muted)]">{Math.round(progress * 100)}%</span>
            </div>
            <div className="w-full h-1.5 bg-[var(--bg-inset)] overflow-hidden">
              <div
                className="h-full bg-primary-500 transition-all duration-500"
                style={{ width: `${Math.round(progress * 100)}%` }}
              />
            </div>
          </div>
        )}

        {/* Preview Images — responsive grid */}
        {previewImages.length > 0 && (
          <div className="tech-panel p-4">
            <h3 className="text-sm font-bold text-[var(--text-primary)] mb-3">预览图 ({previewImages.length})</h3>
            <div className={`grid gap-4 ${
              previewImages.length === 1 ? 'grid-cols-1 max-w-2xl mx-auto' :
              previewImages.length === 2 ? 'grid-cols-1 md:grid-cols-2' :
              previewImages.length <= 4 ? 'grid-cols-2 md:grid-cols-2 lg:grid-cols-4' :
              'grid-cols-2 md:grid-cols-3 lg:grid-cols-5'
            }`}>
              {previewImages.map((url, i) => (
                <div key={i} className="overflow-hidden border border-[var(--border-main)] bg-white group">
                  <img src={url} alt={`Preview ${i + 1}`} className="w-full h-auto group-hover:scale-105 transition-transform duration-300" />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Events Log */}
        {events.length > 0 && (
          <div className="tech-panel p-4">
            <h3 className="text-sm font-bold text-[var(--text-primary)] mb-3">Pipeline 日志</h3>
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
                <label className="text-[11px] font-bold text-[var(--text-muted)] mb-1.5 block uppercase tracking-wider">
                  {taskType === 'diagram' ? '方法描述' : '原始数据'}
                </label>
                <textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder={taskType === 'diagram'
                    ? '粘贴你的论文方法部分内容 (推荐 Markdown 格式)...'
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
              {availableModels && (availableModels.chat_models.length > 0 || availableModels.image_models.length > 0) && (
                <div className="space-y-3 pt-2 border-t border-[var(--border-subtle)]">
                  <label className="text-[11px] font-bold text-[var(--text-muted)] block uppercase tracking-wider">模型选择</label>

                  {/* Chat Model */}
                  {availableModels.chat_models.length > 0 && (
                    <div>
                      <label className="text-[11px] text-[var(--text-muted)] mb-1 block">Chat 模型</label>
                      <select
                        value={chatModelName}
                        onChange={(e) => {
                          const name = e.target.value;
                          setChatModelName(name);
                          setChatKeyId(null);
                          const group = availableModels.chat_models.find(m => m.model_name === name);
                          if (group && group.providers.length === 1) {
                            setChatKeyId(group.providers[0].key_id);
                          }
                        }}
                        className="w-full input-tech text-sm py-2"
                      >
                        <option value="">自动选择</option>
                        {availableModels.chat_models.map(m => (
                          <option key={m.model_name} value={m.model_name}>
                            {m.model_name} ({m.providers.length}个供应商)
                          </option>
                        ))}
                      </select>
                      {/* Provider sub-selection */}
                      {selectedChatGroup && selectedChatGroup.providers.length > 1 && (
                        <div className="mt-1.5">
                          <label className="text-[11px] text-[var(--text-faint)] mb-1 block">选择供应商</label>
                          <select
                            value={chatKeyId ?? ''}
                            onChange={(e) => setChatKeyId(e.target.value ? Number(e.target.value) : null)}
                            className="w-full input-tech text-sm py-2"
                          >
                            <option value="">自动负载均衡</option>
                            {selectedChatGroup.providers.map(p => (
                              <option key={p.key_id} value={p.key_id}>
                                {p.provider}{p.base_url ? ` · ${new URL(p.base_url).host}` : ''}{p.is_system ? ' [系统]' : ''} ({p.api_key_preview})
                              </option>
                            ))}
                          </select>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Image Model */}
                  {availableModels.image_models.length > 0 && (
                    <div>
                      <label className="text-[11px] text-[var(--text-muted)] mb-1 block">Image 模型</label>
                      <select
                        value={imageModelName}
                        onChange={(e) => {
                          const name = e.target.value;
                          setImageModelName(name);
                          setImageKeyId(null);
                          const group = availableModels.image_models.find(m => m.model_name === name);
                          if (group && group.providers.length === 1) {
                            setImageKeyId(group.providers[0].key_id);
                          }
                        }}
                        className="w-full input-tech text-sm py-2"
                      >
                        <option value="">自动选择（fallback 到 Chat）</option>
                        {availableModels.image_models.map(m => (
                          <option key={m.model_name} value={m.model_name}>
                            {m.model_name} ({m.providers.length}个供应商)
                          </option>
                        ))}
                      </select>
                      {/* Provider sub-selection */}
                      {selectedImageGroup && selectedImageGroup.providers.length > 1 && (
                        <div className="mt-1.5">
                          <label className="text-[11px] text-[var(--text-faint)] mb-1 block">选择供应商</label>
                          <select
                            value={imageKeyId ?? ''}
                            onChange={(e) => setImageKeyId(e.target.value ? Number(e.target.value) : null)}
                            className="w-full input-tech text-sm py-2"
                          >
                            <option value="">自动负载均衡</option>
                            {selectedImageGroup.providers.map(p => (
                              <option key={p.key_id} value={p.key_id}>
                                {p.provider}{p.base_url ? ` · ${new URL(p.base_url).host}` : ''}{p.is_system ? ' [系统]' : ''} ({p.api_key_preview})
                              </option>
                            ))}
                          </select>
                        </div>
                      )}
                    </div>
                  )}

                  {availableModels.chat_models.length === 0 && availableModels.image_models.length === 0 && (
                    <p className="text-[10px] text-yellow-400">暂无可用模型，请先在设置中配置 API Key</p>
                  )}
                </div>
              )}

              {modelsLoading && (
                <div className="text-[10px] text-[var(--text-faint)] py-2">正在加载可用模型...</div>
              )}

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
