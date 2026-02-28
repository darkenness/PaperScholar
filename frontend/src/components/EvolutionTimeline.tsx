'use client';

import { useState, useEffect } from 'react';
import { generateApi } from '@/lib/api';
import ImageLightbox from './ImageLightbox';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

interface EvolutionStage {
  name: string;
  status: string;
  round: number | null;
  description: string | null;
  image_available: boolean;
  suggestions: string | null;
  timestamp: string | null;
}

interface EvolutionTimelineProps {
  taskId: string;
  /** If provided, skips the API call and uses these stages directly */
  stages?: EvolutionStage[];
  /** Compact mode hides descriptions by default */
  compact?: boolean;
}

const STAGE_ICONS: Record<string, string> = {
  retriever: '🔍',
  planner: '📋',
  stylist: '✨',
  visualizer: '🎨',
  critic: '🔎',
  polish: '💎',
};

const STAGE_LABELS: Record<string, string> = {
  retriever: '检索器',
  planner: '规划器',
  stylist: '风格师',
  visualizer: '可视化器',
  critic: '评审器',
  polish: '精修器',
};

function getStageName(stage: EvolutionStage): string {
  const base = STAGE_LABELS[stage.name] || stage.name;
  if (stage.round != null) return `${base} 第 ${stage.round} 轮`;
  return base;
}

function getStageIcon(stage: EvolutionStage): string {
  return STAGE_ICONS[stage.name] || '⚙️';
}

export default function EvolutionTimeline({ taskId, stages: propStages, compact = false }: EvolutionTimelineProps) {
  const [stages, setStages] = useState<EvolutionStage[]>(propStages || []);
  const [loading, setLoading] = useState(!propStages);
  const [error, setError] = useState('');
  const [expandedStage, setExpandedStage] = useState<number | null>(null);
  const [collapsed, setCollapsed] = useState(compact);

  useEffect(() => {
    if (propStages) {
      setStages(propStages);
      return;
    }
    if (!taskId) return;
    (async () => {
      try {
        const data = await generateApi.getEvolution(taskId);
        setStages(data.stages || []);
      } catch (e: any) {
        setError(e.message || '加载演进信息失败');
      }
      setLoading(false);
    })();
  }, [taskId, propStages]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-xs text-[var(--text-faint)] py-2">
        <div className="w-3 h-3 border border-primary-500 border-t-transparent rounded-full animate-spin" />
        加载 Pipeline 演进...
      </div>
    );
  }

  if (error) {
    return <div className="text-xs text-red-400 py-1">{error}</div>;
  }

  if (stages.length === 0) {
    return <div className="text-xs text-[var(--text-faint)] py-1">暂无演进数据</div>;
  }

  return (
    <div className="space-y-2">
      {/* Header */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-2 text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider hover:text-[var(--text-primary)] transition-colors w-full text-left"
      >
        <svg
          className={`w-3 h-3 transition-transform ${collapsed ? '' : 'rotate-90'}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
        Pipeline 演进时间线 ({stages.length} 个阶段)
      </button>

      {!collapsed && (
        <div className="relative pl-4 border-l-2 border-[var(--border-main)] space-y-3">
          {stages.map((stage, idx) => {
            const isExpanded = expandedStage === idx;
            const isLast = idx === stages.length - 1;

            return (
              <div key={idx} className="relative">
                {/* Timeline dot */}
                <div className={`absolute -left-[21px] top-1 w-3 h-3 rounded-full border-2 ${
                  isLast
                    ? 'bg-primary-500 border-primary-500'
                    : 'bg-[var(--bg-main)] border-[var(--text-faint)]'
                }`} />

                {/* Stage card */}
                <div className={`tech-panel p-3 transition-all ${isLast ? 'border-primary-500/30' : ''}`}>
                  <div
                    className="flex items-center justify-between cursor-pointer"
                    onClick={() => setExpandedStage(isExpanded ? null : idx)}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-base">{getStageIcon(stage)}</span>
                      <span className="text-sm font-medium text-[var(--text-primary)]">
                        {getStageName(stage)}
                      </span>
                      {isLast && (
                        <span className="px-1.5 py-0.5 bg-primary-500/20 text-primary-400 text-[10px] font-bold rounded">
                          最终
                        </span>
                      )}
                      {stage.image_available && (
                        <span className="px-1.5 py-0.5 bg-emerald-500/20 text-emerald-400 text-[10px] font-bold rounded">
                          有图片
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {stage.timestamp && (
                        <span className="text-[10px] text-[var(--text-faint)] font-mono">
                          {new Date(stage.timestamp).toLocaleTimeString()}
                        </span>
                      )}
                      <svg
                        className={`w-4 h-4 text-[var(--text-faint)] transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                        fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                      </svg>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="mt-3 space-y-3">
                      {/* Description */}
                      {stage.description && (
                        <div>
                          <h5 className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-wider mb-1">描述</h5>
                          <div className="text-xs text-[var(--text-secondary)] bg-[var(--bg-inset)] p-2 rounded max-h-40 overflow-y-auto whitespace-pre-wrap">
                            {stage.description.length > 500
                              ? stage.description.substring(0, 500) + '...'
                              : stage.description}
                          </div>
                        </div>
                      )}

                      {/* Critic suggestions */}
                      {stage.suggestions && (
                        <div>
                          <h5 className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-wider mb-1">评审建议</h5>
                          <div className={`text-xs p-2 rounded max-h-40 overflow-y-auto whitespace-pre-wrap ${
                            stage.suggestions.trim() === 'No changes needed.'
                              ? 'bg-green-500/10 text-green-400'
                              : 'bg-yellow-500/10 text-yellow-300'
                          }`}>
                            {stage.suggestions.trim() === 'No changes needed.'
                              ? '✅ 无需修改 — 迭代已停止'
                              : stage.suggestions}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
