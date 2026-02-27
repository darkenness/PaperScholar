'use client';

import { useState } from 'react';
import { generateApi } from '@/lib/api';

const PIPELINE_MODES = [
  { value: 'dev_full', label: '完整Pipeline', desc: 'Retriever → Planner → Stylist → Visualizer → Critic' },
  { value: 'dev_planner_critic', label: 'Planner + Critic', desc: 'Planner → Visualizer → Critic循环' },
  { value: 'dev_planner_stylist', label: 'Planner + Stylist', desc: 'Planner → Stylist → Visualizer' },
  { value: 'dev_planner', label: '仅Planner', desc: 'Planner → Visualizer' },
  { value: 'vanilla', label: '直接生成', desc: '无规划，直接生成' },
];

const RETRIEVAL_SETTINGS = [
  { value: 'auto', label: '自动检索' },
  { value: 'random', label: '随机参考' },
  { value: 'none', label: '无参考' },
];

const ASPECT_RATIOS = ['1:1', '16:9', '4:3', '3:2'];

interface SSEEvent {
  type: string;
  data: any;
  time: string;
}

export default function GeneratePage() {
  const [content, setContent] = useState('');
  const [caption, setCaption] = useState('');
  const [taskType, setTaskType] = useState('diagram');
  const [pipelineMode, setPipelineMode] = useState('dev_full');
  const [retrievalSetting, setRetrievalSetting] = useState('auto');
  const [numCandidates, setNumCandidates] = useState(1);
  const [aspectRatio, setAspectRatio] = useState('1:1');
  const [maxCriticRounds, setMaxCriticRounds] = useState(3);

  const [loading, setLoading] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [currentStage, setCurrentStage] = useState('');
  const [progress, setProgress] = useState(0);
  const [previewImages, setPreviewImages] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [isDone, setIsDone] = useState(false);

  const handleGenerate = async () => {
    if (!content.trim() || !caption.trim()) {
      setError('请输入方法描述和图表说明');
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
        aspect_ratio: aspectRatio,
        max_critic_rounds: maxCriticRounds,
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

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">图表生成</h1>
        <p className="text-gray-400 text-sm mt-1">输入论文方法描述，AI 自动生成高质量学术图表</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Input Panel */}
        <div className="lg:col-span-1 space-y-4">
          {/* Task Type */}
          <div className="tech-panel p-4">
            <label className="text-xs font-bold text-gray-400 mb-2 block">图表类型</label>
            <div className="flex gap-2">
              {['diagram', 'plot'].map((t) => (
                <button
                  key={t}
                  onClick={() => setTaskType(t)}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all ${
                    taskType === t ? 'bg-primary-600 text-white' : 'bg-white/5 text-gray-400 hover:text-white'
                  }`}
                >
                  {t === 'diagram' ? '示意图' : '统计图'}
                </button>
              ))}
            </div>
          </div>

          {/* Content Input */}
          <div className="tech-panel p-4">
            <label className="text-xs font-bold text-gray-400 mb-2 block">方法描述 (Method Section)</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="粘贴你的论文方法部分内容 (推荐 Markdown 格式)..."
              rows={8}
              className="w-full input-tech resize-none text-sm"
            />
          </div>

          {/* Caption */}
          <div className="tech-panel p-4">
            <label className="text-xs font-bold text-gray-400 mb-2 block">图表说明 (Figure Caption)</label>
            <textarea
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              placeholder="描述你期望生成的图表内容..."
              rows={3}
              className="w-full input-tech resize-none text-sm"
            />
          </div>

          {/* Settings */}
          <div className="tech-panel p-4 space-y-3">
            <label className="text-xs font-bold text-gray-400 block">生成设置</label>

            <div>
              <label className="text-[11px] text-gray-500 mb-1 block">Pipeline 模式</label>
              <select value={pipelineMode} onChange={(e) => setPipelineMode(e.target.value)} className="w-full input-tech text-sm py-2">
                {PIPELINE_MODES.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] text-gray-500 mb-1 block">参考图检索</label>
                <select value={retrievalSetting} onChange={(e) => setRetrievalSetting(e.target.value)} className="w-full input-tech text-sm py-2">
                  {RETRIEVAL_SETTINGS.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-[11px] text-gray-500 mb-1 block">宽高比</label>
                <select value={aspectRatio} onChange={(e) => setAspectRatio(e.target.value)} className="w-full input-tech text-sm py-2">
                  {ASPECT_RATIOS.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] text-gray-500 mb-1 block">候选数量: {numCandidates}</label>
                <input type="range" min={1} max={10} value={numCandidates} onChange={(e) => setNumCandidates(Number(e.target.value))} className="w-full" />
              </div>
              <div>
                <label className="text-[11px] text-gray-500 mb-1 block">Critic轮数: {maxCriticRounds}</label>
                <input type="range" min={1} max={5} value={maxCriticRounds} onChange={(e) => setMaxCriticRounds(Number(e.target.value))} className="w-full" />
              </div>
            </div>
          </div>

          {error && (
            <div className="text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-2">{error}</div>
          )}

          <button onClick={handleGenerate} disabled={loading} className="w-full btn-primary py-3 disabled:opacity-50">
            {loading ? '生成中...' : '开始生成'}
          </button>
        </div>

        {/* Right: Preview & Events */}
        <div className="lg:col-span-2 space-y-4">
          {/* Progress Bar */}
          {(loading || isDone) && (
            <div className="tech-panel p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-white">
                  {isDone ? '生成完成' : currentStage ? `正在执行: ${currentStage}` : '准备中...'}
                </span>
                <span className="text-xs text-gray-400">{Math.round(progress * 100)}%</span>
              </div>
              <div className="w-full h-2 bg-dark-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-primary-600 to-purple-500 rounded-full transition-all duration-500"
                  style={{ width: `${Math.round(progress * 100)}%` }}
                />
              </div>
            </div>
          )}

          {/* Preview Images */}
          {previewImages.length > 0 && (
            <div className="tech-panel p-4">
              <h3 className="text-sm font-bold text-white mb-3">预览图</h3>
              <div className="grid grid-cols-2 gap-3">
                {previewImages.map((url, i) => (
                  <div key={i} className="rounded-lg overflow-hidden border border-white/10 bg-white">
                    <img src={url} alt={`Preview ${i + 1}`} className="w-full h-auto" />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Events Log */}
          {events.length > 0 && (
            <div className="tech-panel p-4">
              <h3 className="text-sm font-bold text-white mb-3">Pipeline 日志</h3>
              <div className="max-h-80 overflow-y-auto space-y-1.5">
                {events.map((evt, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs">
                    <span className="text-gray-500 font-mono shrink-0">{evt.time}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold shrink-0 ${
                      evt.type === 'stage' ? 'bg-primary-500/20 text-primary-400' :
                      evt.type === 'intermediate' ? 'bg-emerald-500/20 text-emerald-400' :
                      'bg-gray-500/20 text-gray-400'
                    }`}>
                      {evt.type}
                    </span>
                    <span className="text-gray-300 break-all">
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
            <div className="tech-panel p-12 text-center">
              <svg className="w-16 h-16 mx-auto mb-4 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={0.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              <h3 className="text-lg font-medium text-gray-400 mb-2">等待生成</h3>
              <p className="text-sm text-gray-500">填写左侧表单并点击「开始生成」</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
