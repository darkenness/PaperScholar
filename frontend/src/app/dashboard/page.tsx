'use client';

import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/auth';

const featureCards = [
  {
    title: '图表生成',
    subtitle: '文本转图表',
    desc: '输入论文方法描述，AI 自动生成高质量学术图表。',
    href: '/dashboard/generate',
    icon: 'M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10',
    color: 'text-primary-500',
    bg: 'bg-primary-500/10'
  },
  {
    title: 'API 配置',
    subtitle: '模型接口管理',
    desc: '管理 LLM 模型的 Provider、API Key 和负载均衡设置。',
    href: '/dashboard/settings',
    icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z',
    color: 'text-[var(--text-muted)]',
    bg: 'bg-[var(--bg-main)]'
  },
  {
    title: '历史记录',
    subtitle: '生成历史',
    desc: '查看历史生成结果、元数据日志和已保存的配置。',
    href: '/dashboard/history',
    icon: 'M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4',
    color: 'text-[var(--text-muted)]',
    bg: 'bg-[var(--bg-main)]'
  },
];

export default function DashboardPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);

  return (
    <div className="max-w-6xl mx-auto p-8 space-y-12">
      {/* Header Area */}
      <div className="border-b border-[var(--border-main)] pb-6 flex items-end justify-between">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <span className="w-2 h-2 bg-primary-500 rounded-none animate-pulse"></span>
            <h1 className="text-2xl font-bold text-[var(--text-primary)] tracking-tight uppercase">
              控制台
            </h1>
          </div>
          <p className="text-[var(--text-muted)] font-mono text-xs uppercase tracking-wider">
            用户: {user?.username || '访客'} | 权限: {user?.role === 'admin' ? '管理员' : '标准用户'}
          </p>
        </div>
        <div className="text-right hidden md:block">
          <div className="text-[10px] font-mono text-[var(--text-muted)] mb-1 opacity-70">系统时间</div>
          <div className="font-mono text-sm text-[var(--text-muted)]">
            {new Date().toISOString().split('T')[0]} {new Date().toISOString().split('T')[1].substring(0, 8)} UTC
          </div>
        </div>
      </div>

      {/* Control Modules */}
      <div>
        <h2 className="text-xs font-mono text-[var(--text-muted)] uppercase tracking-widest mb-4 flex items-center gap-2">
          <span className="w-1 h-1 bg-[var(--border-main)]"></span>
          功能模块
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {featureCards.map((card) => (
            <button
              key={card.href}
              onClick={() => router.push(card.href)}
              className="tech-panel p-6 text-left group hover:border-primary-500 transition-colors relative bg-[var(--bg-panel)]"
            >
              {/* Corner accent */}
              <div className="absolute top-0 right-0 w-3 h-3 border-t border-r border-transparent group-hover:border-primary-500 transition-colors" />
              
              <div className="flex items-start justify-between mb-8">
                <div className={`w-10 h-10 ${card.bg} ${card.color} flex items-center justify-center border border-[var(--border-main)] group-hover:border-primary-500/50 group-hover:text-primary-500 transition-colors`}>
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="square" strokeLinejoin="miter" d={card.icon} />
                  </svg>
                </div>
                <div className="text-[10px] font-mono text-[var(--text-muted)] group-hover:text-primary-500/70 transition-colors">
                  {card.href.split('/').pop()?.toUpperCase()}
                </div>
              </div>
              
              <div>
                <div className="text-[10px] font-mono text-primary-500 mb-1">{card.subtitle}</div>
                <h3 className="text-lg font-bold text-[var(--text-primary)] mb-3 tracking-wide">{card.title}</h3>
                <p className="text-sm text-[var(--text-muted)] leading-relaxed min-h-[40px]">{card.desc}</p>
              </div>

              <div className="mt-6 flex items-center gap-2 text-xs font-mono text-[var(--text-muted)] group-hover:text-primary-500 transition-colors">
                <span>进入</span>
                <span className="group-hover:translate-x-1 transition-transform">→</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Telemetry/Stats Area */}
      <div>
        <h2 className="text-xs font-mono text-[var(--text-muted)] uppercase tracking-widest mb-4 flex items-center gap-2">
          <span className="w-1 h-1 bg-[var(--border-main)]"></span>
          最近生成记录
        </h2>
        <div className="tech-panel p-12 relative overflow-hidden bg-[var(--bg-panel)]">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-[var(--border-main)] to-transparent opacity-50"></div>
          
          <div className="text-center font-mono text-[var(--text-muted)] flex flex-col items-center">
            <svg className="w-8 h-8 mb-4 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
              <path strokeLinecap="square" strokeLinejoin="miter" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
            </svg>
            <p className="mb-2">暂无记录</p>
            <p className="text-[10px] opacity-70 mb-6">还没有生成过图表，开始你的第一次生成吧</p>
            
            <button onClick={() => router.push('/dashboard/generate')} className="btn-primary text-xs">
              开始生成
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
