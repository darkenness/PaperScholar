'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { authApi } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';

export default function LoginPage() {
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await authApi.login(email, password);
      setAuth(data.user, data.access_token);
      router.push('/dashboard');
    } catch (err: any) {
      setError(err.message || 'AUTH_FAILED');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 flex items-center justify-center p-4">
      <div className="w-full max-w-md tech-panel p-8 tech-corner-tl relative">
        {/* Decorative corner brackets */}
        <div className="absolute top-0 right-0 w-4 h-4 border-t border-r border-[var(--border-main)]" />
        <div className="absolute bottom-0 left-0 w-4 h-4 border-b border-l border-[var(--border-main)]" />
        <div className="absolute bottom-0 right-0 w-4 h-4 border-b border-r border-[var(--border-main)]" />
        
        {/* Header */}
        <div className="mb-10">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 bg-primary-600 flex items-center justify-center text-white">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="square" strokeLinejoin="miter" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
              </svg>
            </div>
            <h1 className="text-xl font-bold text-[var(--text-primary)] tracking-tight">PaperScholar</h1>
          </div>
          <div className="flex items-center gap-2 text-[10px] font-mono text-[var(--text-muted)] uppercase">
            <span className="w-1.5 h-1.5 bg-primary-500"></span>
            需要登录系统
          </div>
        </div>

        <form onSubmit={handleLogin} className="space-y-6">
          <div className="space-y-1">
            <label className="block text-[11px] font-mono text-[var(--text-muted)] uppercase tracking-wider">
              邮箱
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your@email.com"
              required
              className="w-full input-tech"
            />
          </div>
          
          <div className="space-y-1">
            <label className="block text-[11px] font-mono text-[var(--text-muted)] uppercase tracking-wider">
              密码
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              className="w-full input-tech"
            />
          </div>

          {error && (
            <div className="text-accent-500 text-xs font-mono bg-accent-500/10 border border-accent-500/20 px-4 py-2 uppercase">
              &gt; 错误: {error}
            </div>
          )}

          <button type="submit" disabled={loading} className="w-full btn-primary group relative overflow-hidden">
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin"></span>
                登录中...
              </span>
            ) : (
              <span className="flex items-center justify-center gap-2">
                登 录
                <svg className="w-4 h-4 transform group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="square" strokeLinejoin="miter" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </span>
            )}
          </button>
        </form>

        <div className="mt-8 pt-6 border-t border-[var(--border-main)]">
          <p className="text-xs text-[var(--text-muted)] font-mono text-center">
            还没有账号？{' '}
            <a href="/register" className="text-primary-500 hover:text-primary-600 underline decoration-primary-500/30 underline-offset-4">
              注册账号
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
