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
    <div className="min-h-[calc(100vh-28px)] flex items-center justify-center p-4 bg-grid-pattern">
      <div className="w-full max-w-md bg-dark-900 border border-dark-600 p-8 tech-corner-tl relative">
        {/* Decorative corner brackets */}
        <div className="absolute top-0 right-0 w-4 h-4 border-t border-r border-dark-600" />
        <div className="absolute bottom-0 left-0 w-4 h-4 border-b border-l border-dark-600" />
        <div className="absolute bottom-0 right-0 w-4 h-4 border-b border-r border-dark-600" />
        
        {/* Header */}
        <div className="mb-10">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 bg-primary-600 flex items-center justify-center text-white">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="square" strokeLinejoin="miter" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
              </svg>
            </div>
            <h1 className="text-xl font-bold text-gray-100 tracking-tight">PaperScholar</h1>
          </div>
          <div className="flex items-center gap-2 text-[10px] font-mono text-gray-500 uppercase">
            <span className="w-1.5 h-1.5 bg-primary-500"></span>
            System Access Required
          </div>
        </div>

        <form onSubmit={handleLogin} className="space-y-6">
          <div className="space-y-1">
            <label className="block text-[11px] font-mono text-gray-400 uppercase tracking-wider">
              Identifier [Email]
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="user@institution.edu"
              required
              className="w-full input-tech"
            />
          </div>
          
          <div className="space-y-1">
            <label className="block text-[11px] font-mono text-gray-400 uppercase tracking-wider">
              Security Key [Password]
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
              &gt; ERR: {error}
            </div>
          )}

          <button type="submit" disabled={loading} className="w-full btn-primary group relative overflow-hidden">
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin"></span>
                AUTHENTICATING...
              </span>
            ) : (
              <span className="flex items-center justify-center gap-2">
                INITIALIZE SESSION
                <svg className="w-4 h-4 transform group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="square" strokeLinejoin="miter" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </span>
            )}
          </button>
        </form>

        <div className="mt-8 pt-6 border-t border-dark-600">
          <p className="text-xs text-gray-500 font-mono text-center">
            UNREGISTERED USER? {' '}
            <a href="/register" className="text-primary-400 hover:text-primary-300 underline decoration-primary-400/30 underline-offset-4">
              REQUEST ACCESS
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
