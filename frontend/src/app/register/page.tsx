'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { authApi } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';

export default function RegisterPage() {
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [codeSent, setCodeSent] = useState(false);
  const [codeLoading, setCodeLoading] = useState(false);
  const [countdown, setCountdown] = useState(0);

  const handleSendCode = async () => {
    if (!email) { setError('请输入邮箱'); return; }
    setCodeLoading(true);
    setError('');
    try {
      await authApi.sendCode(email);
      setCodeSent(true);
      setCountdown(60);
      const timer = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) { clearInterval(timer); return 0; }
          return prev - 1;
        });
      }, 1000);
    } catch (err: any) {
      setError(err.message || '发送验证码失败');
    } finally {
      setCodeLoading(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await authApi.register({ username, email, password, verification_code: code || undefined });
      setAuth(data.user, data.access_token);
      router.push('/dashboard');
    } catch (err: any) {
      setError(err.message || '注册失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-28px)] flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-[var(--bg-panel)] border border-[var(--border-main)] p-8 tech-corner-tl relative">
        {/* Decorative corner brackets */}
        <div className="absolute top-0 right-0 w-4 h-4 border-t border-r border-[var(--border-main)]" />
        <div className="absolute bottom-0 left-0 w-4 h-4 border-b border-l border-[var(--border-main)]" />
        <div className="absolute bottom-0 right-0 w-4 h-4 border-b border-r border-[var(--border-main)]" />

        {/* Header */}
        <div className="mb-10">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 bg-primary-600 flex items-center justify-center text-white">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="square" strokeLinejoin="miter" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
              </svg>
            </div>
            <h1 className="text-xl font-bold text-[var(--text-primary)] tracking-tight">PaperScholar</h1>
          </div>
          <div className="flex items-center gap-2 text-[10px] font-mono text-[var(--text-muted)] uppercase">
            <span className="w-1.5 h-1.5 bg-primary-500"></span>
            新用户注册
          </div>
        </div>

        <form onSubmit={handleRegister} className="space-y-6">
          <div className="space-y-1">
            <label className="block text-[11px] font-mono text-[var(--text-muted)] uppercase tracking-wider">用户名</label>
            <input type="text" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="2-50个字符" required className="w-full input-tech" />
          </div>
          <div className="space-y-1">
            <label className="block text-[11px] font-mono text-[var(--text-muted)] uppercase tracking-wider">邮箱</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="your@email.com" required className="w-full input-tech" />
          </div>
          <div className="space-y-1">
            <label className="block text-[11px] font-mono text-[var(--text-muted)] uppercase tracking-wider">密码</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="至少6位字符" required minLength={6} className="w-full input-tech" />
          </div>
          <div className="space-y-1">
            <label className="block text-[11px] font-mono text-[var(--text-muted)] uppercase tracking-wider">验证码 <span className="text-[var(--text-faint)]">(可选)</span></label>
            <div className="flex gap-3">
              <input type="text" value={code} onChange={(e) => setCode(e.target.value)} placeholder="6位数字，开发模式可留空" maxLength={6} className="flex-1 input-tech" />
              <button
                type="button"
                onClick={handleSendCode}
                disabled={codeLoading || countdown > 0}
                className="btn-ghost text-sm whitespace-nowrap disabled:opacity-50 font-mono"
              >
                {codeLoading ? '发送中...' : countdown > 0 ? `${countdown}s` : codeSent ? '重新发送' : '获取验证码'}
              </button>
            </div>
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
                注册中...
              </span>
            ) : (
              <span className="flex items-center justify-center gap-2">
                注 册
                <svg className="w-4 h-4 transform group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="square" strokeLinejoin="miter" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </span>
            )}
          </button>
        </form>

        <div className="mt-8 pt-6 border-t border-[var(--border-main)]">
          <p className="text-xs text-[var(--text-muted)] font-mono text-center">
            已有账号？{' '}
            <a href="/login" className="text-primary-400 hover:text-primary-300 underline decoration-primary-400/30 underline-offset-4">
              登录
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
