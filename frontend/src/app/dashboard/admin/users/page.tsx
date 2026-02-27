'use client';

import { useEffect, useState } from 'react';
import { adminApi } from '@/lib/api';

export default function AdminUsersPage() {
  const [users, setUsers] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const load = async (p = 1) => {
    setLoading(true);
    try {
      const data = await adminApi.getUsers(p, 20);
      setUsers(data.items);
      setTotal(data.total);
      setPage(p);
    } catch {}
    setLoading(false);
  };

  useEffect(() => { load(1); }, []);

  const handleToggleRole = async (userId: number, currentRole: string) => {
    const newRole = currentRole === 'admin' ? 'user' : 'admin';
    if (!confirm(`确定将此用户角色更改为 ${newRole}？`)) return;
    try { await adminApi.updateRole(userId, newRole); await load(page); } catch (e: any) { alert(e.message); }
  };

  const handleToggleActive = async (userId: number) => {
    try { await adminApi.toggleActive(userId); await load(page); } catch (e: any) { alert(e.message); }
  };

  const totalPages = Math.ceil(total / 20);

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">用户管理</h1>
          <p className="text-[var(--text-muted)] text-sm mt-1">共 {total} 位用户</p>
        </div>
        <button onClick={() => load(page)} className="btn-ghost text-xs">
          <svg className="w-3.5 h-3.5 inline mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
          刷新
        </button>
      </div>

      <div className="tech-panel overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-12"><div className="w-6 h-6 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" /></div>
        ) : (
          <table className="w-full text-left">
            <thead className="bg-[var(--badge-bg)] text-[var(--text-muted)] uppercase text-xs font-semibold">
              <tr>
                <th className="px-5 py-3">ID</th>
                <th className="px-5 py-3">用户</th>
                <th className="px-5 py-3">角色</th>
                <th className="px-5 py-3">系统API</th>
                <th className="px-5 py-3">状态</th>
                <th className="px-5 py-3">注册时间</th>
                <th className="px-5 py-3 text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border-subtle)] text-sm">
              {users.map((u: any) => (
                <tr key={u.id} className="hover:bg-[var(--bg-hover)] transition-colors">
                  <td className="px-5 py-3 font-mono text-[var(--text-muted)] text-xs">{u.id}</td>
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-500 to-purple-500 flex items-center justify-center text-xs font-bold text-white">
                        {u.username?.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <div className="font-medium text-[var(--text-primary)]">{u.username}</div>
                        <div className="text-xs text-[var(--text-muted)]">{u.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-5 py-3">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${u.role === 'admin' ? 'bg-orange-500/20 text-orange-400' : 'bg-gray-500/20 text-gray-400'}`}>
                      {u.role}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${u.system_api_approved ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-500'}`}>
                      {u.system_api_approved ? '已批准' : '未批准'}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${u.is_active ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                      {u.is_active ? '活跃' : '禁用'}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-xs text-[var(--text-muted)] font-mono">{new Date(u.created_at).toLocaleDateString()}</td>
                  <td className="px-5 py-3 text-right space-x-2">
                    <button onClick={() => handleToggleRole(u.id, u.role)} className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] border border-[var(--border-main)] hover:border-[var(--text-muted)] px-2 py-1 rounded transition-all">
                      {u.role === 'admin' ? '降为用户' : '升为管理'}
                    </button>
                    <button onClick={() => handleToggleActive(u.id)} className={`text-xs px-2 py-1 rounded transition-all border ${u.is_active ? 'text-red-400 border-red-500/30 hover:bg-red-500/10' : 'text-green-400 border-green-500/30 hover:bg-green-500/10'}`}>
                      {u.is_active ? '禁用' : '启用'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex justify-center gap-2">
          <button onClick={() => load(page - 1)} disabled={page <= 1} className="btn-ghost text-xs py-1.5 px-3 disabled:opacity-30">上一页</button>
          <span className="text-sm text-[var(--text-muted)] flex items-center px-3">{page} / {totalPages}</span>
          <button onClick={() => load(page + 1)} disabled={page >= totalPages} className="btn-ghost text-xs py-1.5 px-3 disabled:opacity-30">下一页</button>
        </div>
      )}
    </div>
  );
}
