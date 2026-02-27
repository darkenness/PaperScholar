'use client';

import { useState } from 'react';
import { toast } from 'sonner';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export default function RefinePage() {
  const [mode, setMode] = useState<'enhance' | 'style'>('enhance');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [refFile, setRefFile] = useState<File | null>(null);
  const [refPreview, setRefPreview] = useState<string | null>(null);
  const [instruction, setInstruction] = useState('提高整体视觉质量，使其达到出版级别');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>, isRef = false) => {
    const f = e.target.files?.[0];
    if (f) {
      if (isRef) { setRefFile(f); setRefPreview(URL.createObjectURL(f)); }
      else { setFile(f); setPreview(URL.createObjectURL(f)); }
      setResult(null);
    }
  };

  const handleEnhance = async () => {
    if (!file) { toast.error('请上传图片'); return; }
    setLoading(true);
    const token = localStorage.getItem('token');
    const formData = new FormData();
    formData.append('image', file);
    formData.append('instruction', instruction);

    try {
      const res = await fetch(`${API_BASE}/api/v1/refine/enhance`, {
        method: 'POST', body: formData,
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || '请求失败'); }
      setResult(await res.json());
      toast.success('图片增强完成');
    } catch (e: any) { toast.error(e.message); }
    setLoading(false);
  };

  const handleStyleTransfer = async () => {
    if (!file || !refFile) { toast.error('请上传源图和参考图'); return; }
    setLoading(true);
    const token = localStorage.getItem('token');
    const formData = new FormData();
    formData.append('source_image', file);
    formData.append('reference_image', refFile);

    try {
      const res = await fetch(`${API_BASE}/api/v1/refine/style-transfer`, {
        method: 'POST', body: formData,
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || '请求失败'); }
      setResult(await res.json());
      toast.success('风格迁移完成');
    } catch (e: any) { toast.error(e.message); }
    setLoading(false);
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">精修增强</h1>
        <p className="text-[var(--text-muted)] text-sm mt-1">AI 图片增强、风格迁移</p>
      </div>

      <div className="flex gap-2">
        <button onClick={() => { setMode('enhance'); setResult(null); }} className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${mode === 'enhance' ? 'bg-primary-600 text-white' : 'bg-[var(--badge-bg)] text-[var(--text-muted)]'}`}>
          图片增强
        </button>
        <button onClick={() => { setMode('style'); setResult(null); }} className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${mode === 'style' ? 'bg-primary-600 text-white' : 'bg-[var(--badge-bg)] text-[var(--text-muted)]'}`}>
          风格迁移
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Input */}
        <div className="space-y-4">
          <div className="tech-panel p-5">
            <h3 className="text-sm font-bold text-[var(--text-primary)] mb-3">{mode === 'enhance' ? '上传图片' : '源图片'}</h3>
            <label className="block border-2 border-dashed border-[var(--border-main)] rounded-xl p-6 text-center cursor-pointer hover:border-primary-500/50 transition-colors">
              <input type="file" accept="image/*" onChange={(e) => handleFileChange(e)} className="hidden" />
              {preview ? (
                <img src={preview} alt="Source" className="max-h-40 mx-auto rounded-lg" />
              ) : (
                <p className="text-sm text-[var(--text-muted)]">点击上传</p>
              )}
            </label>
          </div>

          {mode === 'enhance' ? (
            <div className="tech-panel p-5">
              <h3 className="text-sm font-bold text-[var(--text-primary)] mb-3">增强指令</h3>
              <textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} rows={3} className="w-full input-tech text-sm resize-none" placeholder="描述你希望如何改进这张图片..." />
              <button onClick={handleEnhance} disabled={loading || !file} className="w-full btn-primary py-2.5 text-sm mt-3 disabled:opacity-50">
                {loading ? '增强中...' : '开始增强'}
              </button>
            </div>
          ) : (
            <div className="tech-panel p-5">
              <h3 className="text-sm font-bold text-[var(--text-primary)] mb-3">参考风格图片</h3>
              <label className="block border-2 border-dashed border-[var(--border-main)] rounded-xl p-6 text-center cursor-pointer hover:border-primary-500/50 transition-colors">
                <input type="file" accept="image/*" onChange={(e) => handleFileChange(e, true)} className="hidden" />
                {refPreview ? (
                  <img src={refPreview} alt="Reference" className="max-h-32 mx-auto rounded-lg" />
                ) : (
                  <p className="text-sm text-[var(--text-muted)]">上传参考风格图片</p>
                )}
              </label>
              <button onClick={handleStyleTransfer} disabled={loading || !file || !refFile} className="w-full btn-primary py-2.5 text-sm mt-3 disabled:opacity-50">
                {loading ? '迁移中...' : '开始风格迁移'}
              </button>
            </div>
          )}
        </div>

        {/* Right: Result */}
        <div>
          {result ? (
            <div className="tech-panel p-5 space-y-4">
              <h3 className="text-sm font-bold text-[var(--text-primary)]">结果</h3>
              {mode === 'enhance' && result.enhanced_url && (
                <div className="space-y-3">
                  <div className="bg-white rounded-lg overflow-hidden"><img src={`${API_BASE}${result.enhanced_url}`} alt="Enhanced" className="w-full" /></div>
                  <a href={`${API_BASE}${result.enhanced_url}`} download className="btn-primary text-xs py-2 px-4 inline-block">下载增强图片</a>
                </div>
              )}
              {mode === 'style' && result.result_url && (
                <div className="space-y-3">
                  <div className="bg-white rounded-lg overflow-hidden"><img src={`${API_BASE}${result.result_url}`} alt="Result" className="w-full" /></div>
                  <a href={`${API_BASE}${result.result_url}`} download className="btn-primary text-xs py-2 px-4 inline-block">下载结果</a>
                </div>
              )}
            </div>
          ) : (
            <div className="tech-panel p-12 text-center text-[var(--text-muted)]">
              <svg className="w-16 h-16 mx-auto mb-4 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={0.5}><path strokeLinecap="round" strokeLinejoin="round" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" /></svg>
              <p>{mode === 'enhance' ? '上传图片并开始增强' : '上传源图和参考图开始风格迁移'}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
