import type { Metadata } from 'next';
import { Toaster } from '@/components/ui/toaster';
import './globals.css';

export const metadata: Metadata = {
  title: 'PaperScholar | AI Academic Illustration',
  description: 'AI-powered academic illustration generation and editing platform for researchers',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="dark">
      <body className="min-h-screen bg-dark-900 text-gray-300 antialiased font-sans">
        {/* Subtle noise texture overlay */}
        <div 
          className="fixed inset-0 pointer-events-none z-50 opacity-[0.015]"
          style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg viewBox=\'0 0 200 200\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cfilter id=\'noiseFilter\'%3E%3CfeTurbulence type=\'fractalNoise\' baseFrequency=\'0.65\' numOctaves=\'3\' stitchTiles=\'stitch\'/%3E%3C/filter%3E%3Crect width=\'100%25\' height=\'100%25\' filter=\'url(%23noiseFilter)\'/%3E%3C/svg%3E")' }}
        />
        
        {/* Industrial layout wrapper */}
        <div className="relative z-10 min-h-screen flex flex-col">
          {/* Top subtle structural line */}
          <div className="h-1 w-full bg-dark-800 border-b border-dark-600/50" />
          
          <main className="flex-1 flex flex-col">
            {children}
          </main>
          
          {/* Bottom subtle structural line */}
          <div className="h-6 w-full bg-dark-900 border-t border-dark-600 flex items-center justify-between px-4 text-[10px] font-mono text-gray-600">
            <span>SYS.STATUS: ONLINE</span>
            <span>v1.0.0-beta</span>
          </div>
        </div>
        <Toaster />
      </body>
    </html>
  );
}
