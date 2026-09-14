'use client';
import {useEffect,useRef} from 'react';
import {X} from 'lucide-react';
export default function Dialog({title,children,onClose}:{title:string;children:React.ReactNode;onClose:()=>void}) {
  const ref=useRef<HTMLDivElement>(null);const close=useRef(onClose);close.current=onClose;
  useEffect(()=>{
    const previous=document.activeElement as HTMLElement;
    ref.current?.querySelector<HTMLElement>('input,select,textarea,button')?.focus();
    const key=(e:KeyboardEvent)=>{if(e.key==='Escape')close.current();if(e.key==='Tab'){
      const nodes=Array.from(ref.current?.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),a[href]')||[]);
      const first=nodes[0],last=nodes[nodes.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}
    }};
    document.addEventListener('keydown',key);return()=>{document.removeEventListener('keydown',key);previous?.focus();};
  },[]);
  return <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4" onMouseDown={e=>{if(e.target===e.currentTarget)onClose();}}><div ref={ref} role="dialog" aria-modal="true" aria-label={title} className="surface max-w-xl w-full p-6 max-h-[90vh] overflow-y-auto shadow-2xl"><div className="flex items-center justify-between mb-5"><h2 className="text-lg font-semibold">{title}</h2><button type="button" aria-label="关闭对话框" className="icon-button" onClick={onClose}><X size={18}/></button></div>{children}</div></div>;
}
