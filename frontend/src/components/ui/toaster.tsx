'use client';

import { Toaster as SonnerToaster } from 'sonner';

export function Toaster() {
  return (
    <SonnerToaster
      position="top-right"
      toastOptions={{
        style: {
          background: 'rgba(17, 24, 39, 0.9)',
          backdropFilter: 'blur(12px)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          color: '#f3f4f6',
          fontSize: '13px',
        },
        className: 'glass-toast',
      }}
      closeButton
      richColors
    />
  );
}
