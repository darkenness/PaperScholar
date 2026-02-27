import type { Metadata } from 'next';
import { Toaster } from '@/components/ui/toaster';
import ThemeToggle from '@/components/ui/ThemeToggle';
import './globals.css';

export const metadata: Metadata = {
  title: 'PaperScholar | AI Academic Illustration',
  description: 'AI-powered academic illustration generation and editing platform for researchers',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                let theme = localStorage.getItem('theme-storage');
                if (theme) {
                  theme = JSON.parse(theme).state.theme;
                  if (theme === 'dark') {
                    document.documentElement.classList.add('dark');
                  } else {
                    document.documentElement.classList.remove('dark');
                  }
                }
              } catch (_) {}
            `,
          }}
        />
      </head>
      <body>
        {/* Subtle noise texture overlay */}
        <div 
          className="fixed inset-0 pointer-events-none z-50 opacity-[0.015] dark:opacity-[0.03]"
          style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg viewBox=\'0 0 200 200\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cfilter id=\'noiseFilter\'%3E%3CfeTurbulence type=\'fractalNoise\' baseFrequency=\'0.65\' numOctaves=\'3\' stitchTiles=\'stitch\'/%3E%3C/filter%3E%3Crect width=\'100%25\' height=\'100%25\' filter=\'url(%23noiseFilter)\'/%3E%3C/svg%3E")' }}
        />
        
        {/* Industrial layout wrapper */}
        <div className="relative z-10 min-h-screen flex flex-col">
          {/* Top subtle structural line */}
          <div className="h-1 w-full bg-[var(--bg-panel)] border-b border-[var(--border-main)] opacity-50" />
          
          <main className="flex-1 flex flex-col">
            {children}
          </main>
          
          {/* Bottom status bar with theme toggle */}
          <div className="h-8 w-full bg-[var(--bg-panel)] border-t border-[var(--border-main)] flex items-center justify-between px-4 text-[10px] font-mono text-[var(--text-muted)]">
            <div className="flex items-center gap-4">
              <span>系统状态: 在线</span>
              <span className="hidden sm:inline">v1.0.0-beta</span>
            </div>
            <div className="flex items-center gap-2">
              <ThemeToggle compact />
            </div>
          </div>
        </div>
        <Toaster />
      </body>
    </html>
  );
}
