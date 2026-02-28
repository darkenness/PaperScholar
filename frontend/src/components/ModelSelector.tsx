'use client';

import { useState, useEffect } from 'react';
import { generateApi, type AvailableModelsResponse } from '@/lib/api';

export interface ModelSelection {
  chatModelName: string;
  chatKeyId: number | null;
  imageModelName: string;
  imageKeyId: number | null;
}

interface ModelSelectorProps {
  showChat?: boolean;
  showImage?: boolean;
  onChange?: (selection: ModelSelection) => void;
}

export default function ModelSelector({ showChat = true, showImage = true, onChange }: ModelSelectorProps) {
  const [models, setModels] = useState<AvailableModelsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [chatModelName, setChatModelName] = useState('');
  const [chatKeyId, setChatKeyId] = useState<number | null>(null);
  const [imageModelName, setImageModelName] = useState('');
  const [imageKeyId, setImageKeyId] = useState<number | null>(null);

  useEffect(() => {
    const fetch = async () => {
      setLoading(true);
      try {
        const data = await generateApi.getAvailableModels();
        setModels(data);
        let initChat = '', initChatKey: number | null = null;
        let initImage = '', initImageKey: number | null = null;
        if (data.chat_models.length === 1) {
          initChat = data.chat_models[0].model_name;
          if (data.chat_models[0].providers.length === 1) initChatKey = data.chat_models[0].providers[0].key_id;
        }
        if (data.image_models.length === 1) {
          initImage = data.image_models[0].model_name;
          if (data.image_models[0].providers.length === 1) initImageKey = data.image_models[0].providers[0].key_id;
        }
        setChatModelName(initChat);
        setChatKeyId(initChatKey);
        setImageModelName(initImage);
        setImageKeyId(initImageKey);
        onChange?.({ chatModelName: initChat, chatKeyId: initChatKey, imageModelName: initImage, imageKeyId: initImageKey });
      } catch {
        // User may not have keys configured yet
      } finally {
        setLoading(false);
      }
    };
    fetch();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const notify = (patch: Partial<ModelSelection>) => {
    const sel = { chatModelName, chatKeyId, imageModelName, imageKeyId, ...patch };
    onChange?.(sel);
  };

  const selectedChatGroup = models?.chat_models.find(m => m.model_name === chatModelName);
  const selectedImageGroup = models?.image_models.find(m => m.model_name === imageModelName);

  if (loading) {
    return <div className="text-[10px] text-[var(--text-faint)] py-2">正在加载可用模型...</div>;
  }

  if (!models) return null;

  const hasChatModels = showChat && models.chat_models.length > 0;
  const hasImageModels = showImage && models.image_models.length > 0;
  const noModels = (showChat && models.chat_models.length === 0) && (showImage && models.image_models.length === 0);
  const chatOnlyEmpty = showChat && models.chat_models.length === 0 && !showImage;
  const imageOnlyEmpty = showImage && models.image_models.length === 0 && !showChat;

  const formatProvider = (p: { provider: string; base_url: string | null; is_system: boolean; api_key_preview: string }) => {
    let label = p.provider;
    if (p.base_url) {
      try { label += ` · ${new URL(p.base_url).host}`; } catch { /* ignore */ }
    }
    if (p.is_system) label += ' [系统]';
    return `${label} (${p.api_key_preview})`;
  };

  return (
    <div className="space-y-3 pt-2 border-t border-[var(--border-subtle)]">
      <label className="text-[11px] font-bold text-[var(--text-muted)] block uppercase tracking-wider">模型选择</label>

      {(noModels || chatOnlyEmpty || imageOnlyEmpty) && (
        <div className="py-3 px-3 bg-yellow-500/10 border border-yellow-500/20">
          <p className="text-xs text-yellow-400">暂无可用{chatOnlyEmpty ? ' Chat ' : imageOnlyEmpty ? ' Image ' : ''}模型</p>
          <p className="text-[10px] text-[var(--text-muted)] mt-1">
            请先在 <a href="/dashboard/settings" className="text-primary-400 underline">API 配置</a> 中添加并验证 API Key，或申请使用系统 API
          </p>
        </div>
      )}

      {hasChatModels && (
        <div>
          <label className="text-[11px] text-[var(--text-muted)] mb-1 block">Chat 模型</label>
          <select
            value={chatModelName}
            onChange={(e) => {
              const name = e.target.value;
              setChatModelName(name);
              let keyId: number | null = null;
              const group = models.chat_models.find(m => m.model_name === name);
              if (group && group.providers.length === 1) keyId = group.providers[0].key_id;
              setChatKeyId(keyId);
              notify({ chatModelName: name, chatKeyId: keyId });
            }}
            className="w-full input-tech text-sm py-2"
          >
            <option value="">自动选择</option>
            {models.chat_models.map(m => (
              <option key={m.model_name} value={m.model_name}>
                {m.model_name} ({m.providers.length}个供应商)
              </option>
            ))}
          </select>
          {selectedChatGroup && selectedChatGroup.providers.length > 1 && (
            <div className="mt-1.5">
              <label className="text-[11px] text-[var(--text-faint)] mb-1 block">选择供应商</label>
              <select
                value={chatKeyId ?? ''}
                onChange={(e) => { const v = e.target.value ? Number(e.target.value) : null; setChatKeyId(v); notify({ chatKeyId: v }); }}
                className="w-full input-tech text-sm py-2"
              >
                <option value="">自动负载均衡</option>
                {selectedChatGroup.providers.map(p => (
                  <option key={p.key_id} value={p.key_id}>{formatProvider(p)}</option>
                ))}
              </select>
            </div>
          )}
        </div>
      )}

      {hasImageModels && (
        <div>
          <label className="text-[11px] text-[var(--text-muted)] mb-1 block">Image 模型</label>
          <select
            value={imageModelName}
            onChange={(e) => {
              const name = e.target.value;
              setImageModelName(name);
              let keyId: number | null = null;
              const group = models.image_models.find(m => m.model_name === name);
              if (group && group.providers.length === 1) keyId = group.providers[0].key_id;
              setImageKeyId(keyId);
              notify({ imageModelName: name, imageKeyId: keyId });
            }}
            className="w-full input-tech text-sm py-2"
          >
            <option value="">自动选择（fallback 到 Chat）</option>
            {models.image_models.map(m => (
              <option key={m.model_name} value={m.model_name}>
                {m.model_name} ({m.providers.length}个供应商)
              </option>
            ))}
          </select>
          {selectedImageGroup && selectedImageGroup.providers.length > 1 && (
            <div className="mt-1.5">
              <label className="text-[11px] text-[var(--text-faint)] mb-1 block">选择供应商</label>
              <select
                value={imageKeyId ?? ''}
                onChange={(e) => { const v = e.target.value ? Number(e.target.value) : null; setImageKeyId(v); notify({ imageKeyId: v }); }}
                className="w-full input-tech text-sm py-2"
              >
                <option value="">自动负载均衡</option>
                {selectedImageGroup.providers.map(p => (
                  <option key={p.key_id} value={p.key_id}>{formatProvider(p)}</option>
                ))}
              </select>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
