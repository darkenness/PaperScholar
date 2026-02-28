'use client';

import { useState, useEffect, useCallback } from 'react';

interface ImageLightboxProps {
  src: string;
  alt?: string;
  className?: string;
  children?: React.ReactNode;
}

/**
 * Wraps an image (or any clickable element) and shows a fullscreen lightbox on click.
 * Supports zoom in/out via scroll, drag to pan, and keyboard (Esc to close).
 */
export default function ImageLightbox({ src, alt = '', className = '', children }: ImageLightboxProps) {
  const [open, setOpen] = useState(false);
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  const resetView = useCallback(() => {
    setScale(1);
    setPosition({ x: 0, y: 0 });
  }, []);

  const handleOpen = () => {
    resetView();
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
  };

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose();
      if (e.key === '+' || e.key === '=') setScale((s) => Math.min(s * 1.2, 8));
      if (e.key === '-') setScale((s) => Math.max(s / 1.2, 0.2));
      if (e.key === '0') resetView();
    };
    window.addEventListener('keydown', handleKeyDown);
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [open, resetView]);

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setScale((s) => Math.min(Math.max(s * delta, 0.2), 8));
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    setDragging(true);
    setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!dragging) return;
    setPosition({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
  };

  const handleMouseUp = () => {
    setDragging(false);
  };

  return (
    <>
      <div onClick={handleOpen} className={`cursor-zoom-in ${className}`}>
        {children || <img src={src} alt={alt} className="w-full h-auto" />}
      </div>

      {open && (
        <div
          className="fixed inset-0 z-[100] bg-black/90 flex items-center justify-center"
          onWheel={handleWheel}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          style={{ cursor: dragging ? 'grabbing' : 'grab' }}
        >
          {/* Top bar */}
          <div className="absolute top-0 left-0 right-0 h-12 flex items-center justify-between px-4 z-10 bg-gradient-to-b from-black/60 to-transparent">
            <span className="text-white/70 text-xs font-mono">
              {Math.round(scale * 100)}% · scroll to zoom · drag to pan · 0 to reset
            </span>
            <div className="flex items-center gap-2">
              <a
                href={src}
                download
                onClick={(e) => e.stopPropagation()}
                className="p-2 text-white/70 hover:text-white transition-colors"
                title="Download"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                </svg>
              </a>
              <button
                onClick={(e) => { e.stopPropagation(); resetView(); }}
                className="p-2 text-white/70 hover:text-white transition-colors"
                title="Reset zoom"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25" />
                </svg>
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); handleClose(); }}
                className="p-2 text-white/70 hover:text-white transition-colors"
                title="Close (Esc)"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Image */}
          <img
            src={src}
            alt={alt}
            className="max-w-none select-none pointer-events-none"
            style={{
              transform: `translate(${position.x}px, ${position.y}px) scale(${scale})`,
              transition: dragging ? 'none' : 'transform 0.1s ease-out',
            }}
            draggable={false}
          />
        </div>
      )}
    </>
  );
}

/**
 * Standalone lightbox trigger — use when you want to open the lightbox
 * from a button or custom element instead of wrapping the image.
 */
export function LightboxTrigger({
  src,
  alt,
  trigger,
}: {
  src: string;
  alt?: string;
  trigger: React.ReactNode;
}) {
  return (
    <ImageLightbox src={src} alt={alt}>
      {trigger}
    </ImageLightbox>
  );
}
