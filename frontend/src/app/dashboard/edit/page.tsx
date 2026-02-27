'use client';

import { useState } from 'react';
import { toast } from 'sonner';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export default function EditPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [samBackend, setSamBackend] = useState('fal');
  const [samApiKey, setSamApiKey] = useState('');
  const [samPrompts, setSamPrompts] = useState('icon,diagram,arrow');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [svgMode, setSvgMode] = useState(false);
  const [svgDesc, setSvgDesc] = useState('');
  const [svgContent, setSvgContent] = useState('');
  const [svgResult, setSvgResult] = useState<any>(null);
  const [svgLoading, setSvgLoading] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) {
      setFile(f);
      setPreview(URL.createObjectURL(f));
      setResult(null);
    }
  };

  const handleVectorize = async () => {
    if (!file) { toast.error('请上传图片'); return; }
    setLoading(true);
    const token = localStorage.getItem('token');
    const formData = new FormData();
    formData.append('image', file);
    formData.append('sam_backend', samBackend);
    if (samApiKey) formData.append('sam_api_key', samApiKey);
    formData.append('sam_prompts', samPrompts);

    try {
      const res = await fetch(`${API_BASE}/api/v1/edit`, {
        method: 'POST', body: formData,
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || '请求失败'); }
      const data = await res.json();
      setResult(data);
      toast.success(`矢量化完成，检测到 ${data.icon_count} 个图标区域`);
    } catch (e: any) {
      toast.error(e.message);
    }
    setLoading(false);
  };

  const handleSvgGenerate = async () => {
    if (!svgDesc.trim()) { toast.error('请输入图表描述'); return; }
    setSvgLoading(true);
    const token = localStorage.getItem('token');
    const formData = new FormData();
    formData.append('description', svgDesc);
    formData.append('content', svgContent);

    try {
      const res = await fetch(`${API_BASE}/api/v1/edit/svg-generate`, {
        method: 'POST', body: formData,
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || '请求失败'); }
      const data = await res.json();
      setSvgResult(data);
      toast.success(`SVG 生成完成，评分 ${data.final_score?.toFixed(1)}/10`);
    } catch (e: any) {
      toast.error(e.message);
    }
    setSvgLoading(false);
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">图表编辑</h1>
        <p className="text-gray-400 text-sm mt-1">上传图片进行矢量化编辑，或直接生成 SVG 矢量图</p>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-2">
        <button onClick={() => setSvgMode(false)} className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${!svgMode ? 'bg-primary-600 text-white' : 'bg-white/5 text-gray-400'}`}>
          图片矢量化
        </button>
        <button onClick={() => setSvgMode(true)} className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${svgMode ? 'bg-primary-600 text-white' : 'bg-white/5 text-gray-400'}`}>
          SVG 直接生成
        </button>
      </div>

      {!svgMode ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left: Upload + Config */}
          <div className="space-y-4">
            <div className="tech-panel p-5">
              <h3 className="text-sm font-bold text-white mb-3">上传图表</h3>
              <label className="block border-2 border-dashed border-white/10 rounded-xl p-8 text-center cursor-pointer hover:border-primary-500/50 transition-colors">
                <input type="file" accept="image/*" onChange={handleFileChange} className="hidden" />
                {preview ? (
                  <img src={preview} alt="Preview" className="max-h-48 mx-auto rounded-lg" />
                ) : (
                  <div className="text-gray-500">
                    <svg className="w-10 h-10 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}><path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                    <p className="text-sm">点击或拖拽上传图片</p>
                  </div>
                )}
              </label>
            </div>

            <div className="tech-panel p-5 space-y-3">
              <h3 className="text-sm font-bold text-white">SAM3 分割设置</h3>
              <div>
                <label className="text-[11px] text-gray-500 mb-1 block">SAM3 后端</label>
                <select value={samBackend} onChange={(e) => setSamBackend(e.target.value)} className="w-full input-tech text-sm py-2">
                  <option value="fal">fal.ai API</option>
                  <option value="roboflow">Roboflow API</option>
                </select>
              </div>
              <div>
                <label className="text-[11px] text-gray-500 mb-1 block">SAM3 API Key</label>
                <input value={samApiKey} onChange={(e) => setSamApiKey(e.target.value)} type="password" placeholder="fal-xxx 或 roboflow-xxx" className="w-full input-tech text-sm" />
              </div>
              <div>
                <label className="text-[11px] text-gray-500 mb-1 block">检测提示词 (逗号分隔)</label>
                <input value={samPrompts} onChange={(e) => setSamPrompts(e.target.value)} className="w-full input-tech text-sm" />
              </div>
              <button onClick={handleVectorize} disabled={loading || !file} className="w-full btn-primary py-2.5 text-sm disabled:opacity-50">
                {loading ? '处理中...' : '开始矢量化'}
              </button>
            </div>
          </div>

          {/* Right: Results */}
          <div className="space-y-4">
            {result ? (
              <>
                <div className="tech-panel p-5">
                  <h3 className="text-sm font-bold text-white mb-3">检测结果</h3>
                  <p className="text-sm text-gray-400 mb-2">检测到 <span className="text-primary-400 font-bold">{result.icon_count}</span> 个图标区域</p>
                  {result.icons?.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {result.icons.map((ic: any) => (
                        <span key={ic.label} className="px-2 py-1 bg-white/5 rounded text-xs text-gray-300 font-mono">{ic.label} ({ic.width}x{ic.height})</span>
                      ))}
                    </div>
                  )}
                </div>
                {result.svg_template && (
                  <div className="tech-panel p-5">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-bold text-white">SVG 模板</h3>
                      <a href={result.svg_url} download className="btn-ghost text-xs py-1 px-3">下载 SVG</a>
                    </div>
                    <div className="bg-white rounded-lg p-2 max-h-64 overflow-auto" dangerouslySetInnerHTML={{ __html: result.svg_template }} />
                  </div>
                )}
              </>
            ) : (
              <div className="tech-panel p-12 text-center text-gray-500">
                <svg className="w-16 h-16 mx-auto mb-4 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={0.5}><path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                <p>上传图片并开始矢量化</p>
              </div>
            )}
          </div>
        </div>
      ) : (
        /* SVG Direct Generation Mode */
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="space-y-4">
            <div className="tech-panel p-5">
              <h3 className="text-sm font-bold text-white mb-3">图表描述</h3>
              <textarea value={svgDesc} onChange={(e) => setSvgDesc(e.target.value)} placeholder="描述你想要生成的SVG学术图表..." rows={6} className="w-full input-tech text-sm resize-none" />
            </div>
            <div className="tech-panel p-5">
              <h3 className="text-sm font-bold text-white mb-3">方法内容 (可选)</h3>
              <textarea value={svgContent} onChange={(e) => setSvgContent(e.target.value)} placeholder="粘贴论文方法部分..." rows={4} className="w-full input-tech text-sm resize-none" />
            </div>
            <button onClick={handleSvgGenerate} disabled={svgLoading} className="w-full btn-primary py-2.5 text-sm disabled:opacity-50">
              {svgLoading ? '生成中 (迭代优化)...' : '生成 SVG'}
            </button>
          </div>
          <div>
            {svgResult?.svg_code ? (
              <div className="tech-panel p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold text-white">生成结果</h3>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-gray-400">评分: <span className="text-primary-400 font-bold">{svgResult.final_score?.toFixed(1)}/10</span></span>
                    <span className="text-xs text-gray-400">迭代: {svgResult.iterations}次</span>
                    {svgResult.svg_url && <a href={svgResult.svg_url} download className="btn-ghost text-xs py-1 px-3">下载</a>}
                  </div>
                </div>
                <div className="bg-white rounded-lg p-2 overflow-auto max-h-96" dangerouslySetInnerHTML={{ __html: svgResult.svg_code }} />
              </div>
            ) : (
              <div className="tech-panel p-12 text-center text-gray-500">
                <svg className="w-16 h-16 mx-auto mb-4 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={0.5}><path strokeLinecap="round" strokeLinejoin="round" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                <p>输入描述并生成 SVG 矢量图</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
