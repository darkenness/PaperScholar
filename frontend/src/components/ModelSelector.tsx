'use client';
import {useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {generateApi,type AvailableModelsResponse,type ModelGroupInfo} from '@/lib/api';
export interface ModelSelection {chatModelName:string;chatKeyId:number|null;imageModelName:string;imageKeyId:number|null;imageSizeMode?:'quality'|'fixed'|'custom';imageSizeOptions?:string[];}
export const EMPTY_SELECTION:ModelSelection={chatModelName:'',chatKeyId:null,imageModelName:'',imageKeyId:null};
interface Props{showChat?:boolean;showImage?:boolean;value?:ModelSelection;onChange?:(selection:ModelSelection)=>void;disabled?:boolean;}
function safeHost(url:string){try{return new URL(url).host;}catch{return url;}}
export default function ModelSelector({showChat=true,showImage=true,value,onChange,disabled=false}:Props){
  const [models,setModels]=useState<AvailableModelsResponse|null>(null);const [internal,setInternal]=useState(EMPTY_SELECTION);
  const [loading,setLoading]=useState(true);const [error,setError]=useState('');const [refresh,setRefresh]=useState(0);
  const sel=value||internal;const valueRef=useRef(value);valueRef.current=value;const changeRef=useRef(onChange);changeRef.current=onChange;
  const capabilities=(next:ModelSelection,data:AvailableModelsResponse)=>{
    const group=next.imageModelName?data.image_models.find(g=>g.model_name===next.imageModelName):data.image_models[0];
    const provider=group?.providers.find(p=>p.key_id===next.imageKeyId);
    return {...next,imageSizeMode:provider?.size_mode||group?.size_mode||'quality' as const,imageSizeOptions:provider?.size_options||group?.size_options||[]};
  };
  useEffect(()=>{let live=true;setLoading(true);setError('');generateApi.getAvailableModels().then(data=>{
    if(!live)return;setModels(data);let next=valueRef.current||{...EMPTY_SELECTION};
    if(!valueRef.current)for(const kind of ['chat','image'] as const){const groups=data[`${kind}_models`];if(groups.length===1){next[`${kind}ModelName`]=groups[0].model_name;if(groups[0].providers.length===1)next[`${kind}KeyId`]=groups[0].providers[0].key_id;}}
    next=capabilities(next,data);setInternal(next);if(!valueRef.current||JSON.stringify(valueRef.current)!==JSON.stringify(next))changeRef.current?.(next);
  }).catch(e=>{if(live)setError(e.message||'模型加载失败');}).finally(()=>{if(live)setLoading(false);});return()=>{live=false;};},[refresh]);
  const update=(patch:Partial<ModelSelection>)=>{const next=models?capabilities({...sel,...patch},models):{...sel,...patch};setInternal(next);onChange?.(next);};
  const render=(kind:'chat'|'image',groups:ModelGroupInfo[])=>{const name=sel[`${kind}ModelName`],group=groups.find(g=>g.model_name===name);return <div className="space-y-2" key={kind}><label className="field-label" htmlFor={`${kind}-model`}>{kind==='chat'?'理解与评审模型':'图像生成模型'}</label>{!groups.length?<p className="text-sm text-amber-600">暂无可用模型。<Link href="/dashboard/settings" className="underline">配置并测试</Link></p>:<><select id={`${kind}-model`} disabled={disabled} className="input-tech w-full" value={name} onChange={e=>{const group=groups.find(g=>g.model_name===e.target.value);update({[`${kind}ModelName`]:e.target.value,[`${kind}KeyId`]:group?.providers.length===1?group.providers[0].key_id:null});}}><option value="">自动选择已配置模型</option>{name&&!group&&<option value={name}>{name}（不可用，请重选）</option>}{groups.map(g=><option key={g.model_name} value={g.model_name}>{g.model_name}</option>)}</select>{group&&<select aria-label={`${kind==='chat'?'理解':'生图'}供应商`} disabled={disabled} className="input-tech w-full text-sm" value={sel[`${kind}KeyId`]??''} onChange={e=>update({[`${kind}KeyId`]:e.target.value?Number(e.target.value):null})}><option value="">同模型备用连接自动切换</option>{group.providers.map(p=><option key={p.key_id} value={p.key_id}>{(p as any).display_name||p.provider} · {p.base_url?safeHost(p.base_url):'默认地址'}{p.is_system?' · 共享':''}</option>)}</select>}</>}</div>;};
  return <section className="space-y-4"><div className="flex items-center justify-between"><h3 className="text-sm font-semibold">模型组合</h3><button type="button" disabled={loading} className="text-xs text-primary-600" onClick={()=>setRefresh(r=>r+1)}>刷新模型</button></div>{loading&&<p role="status" className="text-sm text-[var(--text-muted)]">加载模型…</p>}{error&&<p role="alert" className="text-sm text-red-600">{error}</p>}{models&&<>{showChat&&render('chat',models.chat_models)}{showImage&&render('image',models.image_models)}</>}</section>;
}
