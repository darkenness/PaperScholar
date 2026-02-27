'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/auth';
import { useSidebarStore } from '@/stores/sidebar';
import ThemeToggle from '@/components/ui/ThemeToggle';

const navItems = [
  { label: '仪表盘', href: '/dashboard', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
  { label: '图表生成', href: '/dashboard/generate', icon: 'M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z' },
  { label: '图表编辑', href: '/dashboard/edit', icon: 'M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z' },
  { label: '精修增强', href: '/dashboard/refine', icon: 'M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z' },
  { label: 'API 配置', href: '/dashboard/settings', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
  { label: '历史记录', href: '/dashboard/history', icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' },
];

const adminItems = [
  { label: '用户管理', href: '/dashboard/admin/users', icon: 'M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z' },
  { label: 'API 审核', href: '/dashboard/admin/review', icon: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z' },
  { label: '系统配置', href: '/dashboard/admin/config', icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01' },
];

export default function Sidebar({ isOpen, onToggle }: { isOpen?: boolean; onToggle?: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const { collapsed, toggleCollapsed } = useSidebarStore();
  const isAdmin = user?.role === 'admin';

  const handleLogout = () => {
    logout();
    router.push('/login');
  };

  const navTo = (href: string) => {
    router.push(href);
    if (onToggle) onToggle();
  };

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div className="fixed inset-0 bg-black/40 z-40 lg:hidden" onClick={onToggle} />
      )}
      <aside
        className={`fixed lg:static inset-y-0 left-0 z-50 tech-sidebar flex flex-col h-full flex-shrink-0 transform transition-all duration-300 lg:translate-x-0 ${
          isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        } ${collapsed ? 'lg:w-16 w-64' : 'w-64'}`}
      >
        {/* Logo */}
        <div className="h-14 flex items-center border-b border-[var(--border-main)] px-4 gap-3">
          <div className="w-8 h-8 bg-primary-600 flex items-center justify-center shrink-0">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="square" strokeLinejoin="miter" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
            </svg>
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <h1 className="font-bold text-sm text-[var(--text-primary)] leading-none truncate">PaperScholar</h1>
              <span className="text-[9px] font-mono text-[var(--text-muted)] tracking-wider uppercase">ACADEMIC AI</span>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto overflow-x-hidden">
          {!collapsed && <div className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-wider px-3 mb-1.5 mt-1">功能</div>}
          {navItems.map((item) => (
            <button
              key={item.href}
              onClick={() => navTo(item.href)}
              title={collapsed ? item.label : undefined}
              className={`w-full flex items-center gap-2.5 rounded-none border-l-2 border-transparent transition-colors text-sm ${
                collapsed ? 'justify-center px-0 py-2.5' : 'px-3 py-2'
              } ${
                pathname === item.href
                  ? 'bg-[var(--bg-panel)] border-primary-500 text-primary-500 font-medium'
                  : 'text-[var(--text-muted)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-primary)]'
              }`}
            >
              <span className={`shrink-0 flex items-center justify-center ${collapsed ? 'w-8 h-8' : 'w-7 h-7'} bg-[var(--bg-inset)] ${
                pathname === item.href ? 'bg-primary-500/15 text-primary-500' : ''
              }`}>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d={item.icon} />
                </svg>
              </span>
              {!collapsed && <span className="text-sm font-medium truncate">{item.label}</span>}
            </button>
          ))}

          {isAdmin && (
            <>
              {!collapsed && <div className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-wider px-3 mb-1.5 mt-3">管理</div>}
              {collapsed && <div className="my-2 mx-2 border-t border-[var(--border-subtle)]" />}
              {adminItems.map((item) => (
                <button
                  key={item.href}
                  onClick={() => navTo(item.href)}
                  title={collapsed ? item.label : undefined}
                  className={`w-full flex items-center gap-2.5 rounded-none border-l-2 border-transparent transition-colors text-sm ${
                    collapsed ? 'justify-center px-0 py-2.5' : 'px-3 py-2'
                  } ${
                    pathname === item.href
                      ? 'bg-[var(--bg-panel)] border-orange-500 text-orange-400 font-medium'
                      : 'text-[var(--text-muted)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-primary)]'
                  }`}
                >
                  <span className={`shrink-0 flex items-center justify-center ${collapsed ? 'w-8 h-8' : 'w-7 h-7'} bg-[var(--bg-inset)]`}>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d={item.icon} />
                    </svg>
                  </span>
                  {!collapsed && <span className="text-sm font-medium truncate">{item.label}</span>}
                </button>
              ))}
            </>
          )}
        </nav>

        {/* Bottom: User / Theme / Collapse / Logout */}
        <div className="border-t border-[var(--border-main)] p-2 space-y-1.5">
          {/* User info */}
          {!collapsed ? (
            <div className="flex items-center gap-2.5 px-2 py-1.5">
              <div className="w-7 h-7 bg-primary-600 flex items-center justify-center text-[10px] font-bold text-white shrink-0">
                {user?.username?.charAt(0).toUpperCase() || '?'}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium text-[var(--text-primary)] truncate">{user?.username}</div>
                <div className="text-[10px] text-[var(--text-muted)] truncate">{user?.email}</div>
              </div>
            </div>
          ) : (
            <div className="flex justify-center py-1">
              <div className="w-7 h-7 bg-primary-600 flex items-center justify-center text-[10px] font-bold text-white" title={user?.username}>
                {user?.username?.charAt(0).toUpperCase() || '?'}
              </div>
            </div>
          )}

          {/* Theme toggle */}
          {collapsed ? <ThemeToggle compact /> : <ThemeToggle />}

          {/* Collapse toggle (desktop only) */}
          <button
            onClick={toggleCollapsed}
            className="hidden lg:flex w-full items-center justify-center gap-2 py-1.5 text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors text-xs"
            title={collapsed ? '展开侧边栏' : '收起侧边栏'}
          >
            <svg className={`w-4 h-4 transition-transform ${collapsed ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            </svg>
            {!collapsed && <span className="font-mono text-[10px]">收起</span>}
          </button>

          {/* Logout */}
          {!collapsed ? (
            <button onClick={handleLogout} className="w-full flex items-center justify-center gap-2 py-2 rounded-none border border-red-500/20 text-red-400 hover:bg-red-500/10 hover:text-red-300 transition-colors text-xs font-bold font-mono uppercase">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
              退出登录
            </button>
          ) : (
            <button onClick={handleLogout} title="退出登录" className="w-full flex items-center justify-center py-2 text-red-400 hover:bg-red-500/10 hover:text-red-300 transition-colors">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
            </button>
          )}
        </div>
      </aside>
    </>
  );
}
