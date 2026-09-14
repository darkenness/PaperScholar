'use client';
import {useEffect,useMemo,useState} from 'react';
import {Check,ChevronRight,Circle,Plus,RefreshCw,Settings2,Trash2,Plug,Search} from 'lucide-react';
import {toast} from 'sonner';
import {providerApi,type ProviderConfig,type Capability} from '@/lib/api';
import Dialog from './ui/Dialog';
const PROTOCOLS=[
  {id:'openai_compat',name:'OpenAI 兼容 · Chat Completions',help:'用于文字、看图，以及通过聊天接口返回图片的服务。'},
  {id:'openai_images',name:'OpenAI 兼容 · Images API',help:'生图走 /images/generations；带图修改走 /images/edits。'},
  {id:'gemini',name:'Google Gemini 原生',help:'使用 Google 原生协议。OpenAI 兼容的 Gemini 中转请选 Chat Completions。'},
  {id:'anthropic',name:'Anthropic 原生',help:'用于 Claude 理解与看图，不用于生图。'},
];
const ROOTS:Record<string,string>={openai_compat:'https://openrouter.ai/api/v1',openai_images:'https://api.openai.com/v1',gemini:'https://generativelanguage.googleapis.com',anthropic:'https://api.anthropic.com'};
const LABELS:Record<Capability,string>={chat:'文字',vision:'看图',image_generation:'生图',image_edit:'编辑'};
const OPTIONS={send_modalities:true,send_image_config:true,send_temperature:true,token_parameter:'max_tokens',image_quality:'',max_concurrency:1,timeout_seconds:180};
const empty=()=>({name:'',provider:'openai_compat',root:'',key:'',model:'',type:'chat' as 'chat'|'image',options:{...OPTIONS}});
export default function ProviderManager({system=false}:{system?:boolean}){
  const api=useMemo(()=>providerApi(system),[system]);const [records,setRecords]=useState<ProviderConfig[]>([]);
  const [loading,setLoading]=useState(true),[error,setError]=useState(''),[query,setQuery]=useState(''),[selected,setSelected]=useState('');
  const [modal,setModal]=useState<'create'|'edit'|'clone'|null>(null),[editing,setEditing]=useState<ProviderConfig|null>(null);
  const [form,setForm]=useState(empty),[formError,setFormError]=useState(''),[saving,setSaving]=useState(false);
  const [busy,setBusy]=useState<Record<string,boolean>>({}),[models,setModels]=useState<string[]>([]);
  const [confirmation,setConfirmation]=useState<{title:string;text:string;action:()=>Promise<void>}|null>(null);
  const load=async()=>{try{setRecords(await api.list());setError('');}catch(e:any){setError(e.message||'连接读取失败');}finally{setLoading(false);}};
  useEffect(()=>{void load();},[api]); // eslint-disable-line react-hooks/exhaustive-deps
  const groups=useMemo(()=>{
    const map=new Map<string,{id:string;name:string;host:string;records:ProviderConfig[]}>();
    records.forEach(row=>{const root=row.base_url||ROOTS[row.provider]||'';let host=root;try{host=new URL(root).host;}catch{/* legacy address */}
      const name=row.display_name||host||row.provider,id=`${name}|${root}`;if(!map.has(id))map.set(id,{id,name,host,records:[]});map.get(id)!.records.push(row);});
    return [...map.values()];
  },[records]);
  const filtered=groups.filter(g=>`${g.name} ${g.host} ${g.records.map(r=>r.model_name).join(' ')}`.toLowerCase().includes(query.toLowerCase()));
  const active=filtered.find(g=>g.id===selected)||filtered[0];
  const open=(kind:'create'|'edit'|'clone',row?:ProviderConfig)=>{setEditing(row||null);setModels([]);setFormError('');setForm(row?{name:row.display_name||'',provider:row.provider,root:row.base_url||'',key:'',model:kind==='clone'?'':row.model_name||'',type:row.model_type,options:{...OPTIONS,...(row.api_options||{})} as typeof OPTIONS}:empty());setModal(kind);};
  const patch=(values:Partial<ReturnType<typeof empty>>)=>setForm(old=>({...old,...values}));
  const save=async(event:React.FormEvent)=>{event.preventDefault();setFormError('');if(!form.model.trim()){setFormError('请输入供应商实际模型 ID');return;}if(modal==='create'&&!form.key.trim()){setFormError('请输入 API Key');return;}setSaving(true);
    try{if(modal==='clone'&&editing)await api.addModel(editing.id,{model_type:form.type,provider:form.provider,model_name:form.model.trim()});
      else await api.save({display_name:form.name.trim(),provider:form.provider,...(modal==='create'?{model_type:form.type}:{}),base_url:form.root.trim(),model_name:form.model.trim(),...(form.key.trim()?{api_key:form.key.trim()}:{}),api_options:form.options},modal==='edit'?editing?.id:undefined);
      setModal(null);setForm(empty());toast.success('已保存，请测试所需模型能力');await load();
    }catch(e:any){setFormError(e.message||'保存失败');}finally{setSaving(false);}};
  const test=async(row:ProviderConfig,capability:Capability)=>{const key=`${row.id}:${capability}`;setBusy(b=>({...b,[key]:true}));try{const result=await api.test(row.id,capability);if(result.status==='passed')toast.success(`${LABELS[capability]}测试通过 · ${result.latency_ms} ms`);else toast.error('测试失败，请展开错误详情');await load();}catch(e:any){toast.error(e.message||'测试失败');}finally{setBusy(b=>({...b,[key]:false}));}};
  const requestTest=(row:ProviderConfig,capability:Capability)=>{if(capability.startsWith('image_'))setConfirmation({title:`测试${LABELS[capability]}能力`,text:'将发送一次真实图片请求，可能产生费用。测试只验证接口与返回图片，不代表画质评分。',action:()=>test(row,capability)});else void test(row,capability);};
  const discover=async()=>{setBusy(b=>({...b,models:true}));try{const data=editing?await api.models(editing.id):await api.discoverDraft({provider:form.provider,base_url:form.root.trim(),api_key:form.key.trim()});setModels(data.models);toast.info(data.models.length?`已发现 ${data.models.length} 个模型`:data.message);}catch(e:any){setFormError(e.message||'读取失败，可手动填写模型 ID');}finally{setBusy(b=>({...b,models:false}));}};
  const root=(form.root||ROOTS[form.provider]).trim().replace(/\/+$/,'').replace(/\/(chat\/completions|images\/(generations|edits))$/,'');
  const preview=form.provider==='openai_images'?`${root}/images/generations`:form.provider==='openai_compat'?`${root}/chat/completions`:form.provider==='anthropic'?`${root.replace(/\/v1$/,'')}/v1/messages`:`${root.replace(/\/v1(beta|alpha)?$/,'')}/v1beta/models/{model}:generateContent`;
  return <section className="space-y-4">
    <header className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-semibold">{system?'共享模型连接':'模型与供应商'}</h2><p className="text-sm text-[var(--text-muted)] mt-1">先配置连接，再添加模型。文字、看图、生图、编辑分别验证。</p></div><button className="btn-primary flex items-center gap-2" onClick={()=>open('create')}><Plus size={16}/>添加连接</button></header>
    {error&&<div role="alert" className="error-box">{error}<button className="underline ml-3" onClick={load}>重试</button></div>}
    <div className="surface grid lg:grid-cols-[240px_minmax(0,1fr)] overflow-hidden min-h-[420px]">
      <aside className="p-4 bg-[var(--bg-main)] border-b lg:border-b-0 lg:border-r border-[var(--border-subtle)]"><div className="relative mb-4"><Search size={15} className="absolute left-3 top-3 text-[var(--text-muted)]"/><input aria-label="搜索供应商和模型" className="input-tech w-full pl-9" value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索连接或模型"/></div>
        {loading?<p role="status" className="p-3 text-sm">加载连接…</p>:filtered.map(group=><button key={group.id} onClick={()=>setSelected(group.id)} className={`w-full flex gap-3 items-center text-left p-3 mb-1 rounded-lg border ${active?.id===group.id?'border-primary-200 bg-primary-50 dark:bg-primary-500/10':'border-transparent hover:bg-[var(--bg-hover)]'}`}><Plug size={18}/><div className="min-w-0 flex-1"><div className="text-sm font-medium truncate">{group.name}</div><div className="text-xs text-[var(--text-muted)] mt-1">{group.records.length} 个模型 · {group.records.filter(r=>r.is_enabled&&r.is_verified).length} 个就绪</div></div><ChevronRight size={14}/></button>)}
        {!loading&&!filtered.length&&<p className="p-3 text-sm text-[var(--text-muted)]">{query?'没有匹配的连接':'尚未配置供应商'}</p>}
      </aside>
      <div className="p-5 md:p-6 min-w-0">{!active?<div className="flex flex-col items-center justify-center py-16 text-center"><Plug size={32} className="text-primary-500 mb-4"/><h3 className="font-medium">连接你使用的模型服务</h3><p className="text-sm text-[var(--text-muted)] max-w-sm mt-2">支持自定义地址与模型 ID。OpenAI 兼容的文字和图片接口可以独立配置。</p><button className="btn-ghost mt-5" onClick={()=>open('create')}>配置第一个连接</button></div>:<>
        <div className="flex flex-wrap justify-between items-center gap-3 mb-4"><div><h3 className="font-semibold">{active.name}</h3><p className="text-sm text-[var(--text-muted)] break-all mt-1">{active.host}</p></div><button className="btn-ghost flex items-center gap-2" onClick={()=>open('clone',active.records[0])}><Plus size={14}/>添加模型</button></div>
        <p className="text-xs text-[var(--text-muted)] mb-4">测试状态属于该模型配置。更改地址、密钥或参数后需重新测试；复制的模型配置可独立修改。</p>
        <div className="space-y-4">{active.records.map(row=><article key={row.id} className="border border-[var(--border-main)] rounded-xl p-4">
          <div className="flex flex-wrap justify-between items-start gap-3"><div className="min-w-0"><h4 className="font-semibold text-sm break-all">{row.model_name||'未设置模型'}</h4><p className="text-xs text-[var(--text-muted)] mt-1">{row.model_type==='chat'?'理解与评审':'图像生成'} · {PROTOCOLS.find(x=>x.id===row.provider)?.name||row.provider}</p><p className="font-mono text-xs text-[var(--text-muted)] mt-1">{row.api_key_preview}</p></div><div className="flex items-center gap-1"><label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={row.is_enabled} onChange={async e=>{try{await api.save({is_enabled:e.target.checked},row.id);await load();}catch(err:any){toast.error(err.message);}}}/>启用</label><button aria-label={`编辑 ${row.model_name}`} className="icon-button" onClick={()=>open('edit',row)}><Settings2 size={16}/></button><button aria-label={`删除 ${row.model_name}`} className="icon-button text-red-500" onClick={()=>setConfirmation({title:'删除模型配置',text:`确认删除 ${row.model_name}？历史图片不会删除。`,action:async()=>{await api.remove(row.id);await load();toast.success('已删除配置');}})}><Trash2 size={16}/></button></div></div>
          <div className="flex flex-wrap gap-2 mt-4">{(row.model_type==='chat'?['chat','vision']:['image_generation','image_edit']).map(raw=>{const cap=raw as Capability,state=row.capability_status?.[cap],pending=busy[`${row.id}:${cap}`];return <button key={cap} disabled={pending} className={`capability-button ${state?.status==='passed'?'capability-passed':state?.status==='failed'?'capability-failed':''}`} onClick={()=>requestTest(row,cap)}>{pending?<RefreshCw size={13} className="animate-spin"/>:state?.status==='passed'?<Check size={13}/>:<Circle size={11}/>} {pending?'测试中…':`测试${LABELS[cap]}`}<span className="opacity-70 text-xs">{state?.status==='passed'?'已通过':state?.status==='failed'?'失败':'未测试'}</span></button>;})}</div>
          {(Object.values(row.capability_status||{}).some(c=>c.status==='failed')||row.last_error)&&<details className="mt-3 text-sm"><summary className="cursor-pointer text-red-600 dark:text-red-400">查看错误详情与测试记录</summary><div className="mt-2 rounded-lg p-3 bg-[var(--bg-main)] space-y-2 break-words">{Object.entries(row.capability_status||{}).map(([key,state])=><div key={key}><strong>{LABELS[key as Capability]||key}</strong> · {state.status} {state.latency_ms!=null?`· ${state.latency_ms} ms`:''}<p className="text-xs whitespace-pre-wrap mt-1">{state.message}</p></div>)}{row.last_error&&<p className="text-xs whitespace-pre-wrap">{row.last_error}</p>}</div></details>}
          {row.endpoints&&<details className="mt-3 text-xs text-[var(--text-muted)]"><summary className="cursor-pointer">实际请求地址</summary>{Object.entries(row.endpoints).map(([key,url])=><p className="font-mono break-all mt-2" key={key}>{key}: {url}</p>)}</details>}
        </article>)}</div>
      </>}</div>
    </div>
    {modal&&<Dialog title={modal==='create'?'建立连接并添加模型':modal==='clone'?'为此连接添加模型':'编辑模型配置'} onClose={()=>{if(!saving){setModal(null);setForm(empty());}}}>
      <form onSubmit={save} className="space-y-4">
        {modal!=='clone'&&<label className="block"><span className="field-label">连接名称</span><input className="input-tech w-full" value={form.name} onChange={e=>patch({name:e.target.value})} placeholder="例如：实验室服务 / 我的 OpenRouter"/></label>}
        <div className="grid grid-cols-2 gap-3"><label><span className="field-label">用途</span><select disabled={modal==='edit'} className="input-tech w-full" value={form.type} onChange={e=>patch({type:e.target.value as 'chat'|'image',provider:'openai_compat'})}><option value="chat">理解与评审</option><option value="image">图像生成</option></select></label><label><span className="field-label">接口协议</span><select className="input-tech w-full" value={form.provider} onChange={e=>patch({provider:e.target.value})}>{PROTOCOLS.filter(x=>form.type==='chat'?x.id!=='openai_images':x.id!=='anthropic').map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label></div>
        <p className="text-xs text-[var(--text-muted)]">{PROTOCOLS.find(x=>x.id===form.provider)?.help}</p>
        {modal!=='clone'?<><label className="block"><span className="field-label">服务地址</span><input className="input-tech w-full" value={form.root} onChange={e=>patch({root:e.target.value})} placeholder={ROOTS[form.provider]}/></label><div className="bg-[var(--bg-main)] p-3 rounded-lg text-xs break-all"><span className="text-[var(--text-muted)]">请求预览</span><p className="font-mono mt-1">{preview}</p></div><label className="block"><span className="field-label">API Key {modal==='edit'?'（留空保留）':''}</span><input type="password" autoComplete="new-password" className="input-tech w-full" value={form.key} onChange={e=>patch({key:e.target.value})} placeholder={modal==='edit'?editing?.api_key_preview:'仅在服务端加密保存'}/></label></>:<p className="text-sm rounded-lg bg-primary-50 dark:bg-primary-500/10 p-3">复用服务地址和密钥，不会把完整 Key 返回浏览器。</p>}
        <label className="block"><span className="field-label">模型 ID</span><input required list="provider-model-ids" className="input-tech w-full" value={form.model} onChange={e=>patch({model:e.target.value})} placeholder="供应商提供的完整模型 ID"/><datalist id="provider-model-ids">{models.map(id=><option value={id} key={id}/>)}</datalist></label>
        <button type="button" className="text-sm text-primary-600 disabled:opacity-50" disabled={busy.models||(!editing&&(!form.root.trim()||!form.key.trim()))} onClick={discover}>{busy.models?'探测中…':editing?'刷新可用模型':'探测可用模型'}</button>
        {modal!=='clone'&&<details className="text-sm"><summary className="cursor-pointer text-[var(--text-muted)]">高级兼容选项</summary><div className="space-y-3 pt-3">{(['send_modalities','send_image_config','send_temperature'] as const).map(key=><label className="flex gap-2 items-center" key={key}><input type="checkbox" checked={form.options[key]} onChange={e=>patch({options:{...form.options,[key]:e.target.checked}})}/>{key==='send_modalities'?'发送 modalities（聊天生图）':key==='send_image_config'?'发送 image_config（尺寸与比例）':'发送 temperature（文字请求）'}</label>)}
          <label className="block">Token 参数<select className="input-tech w-full mt-1" value={form.options.token_parameter} onChange={e=>patch({options:{...form.options,token_parameter:e.target.value}})}><option>max_tokens</option><option>max_completion_tokens</option></select></label>
          <label className="block">原生 Images 质量（可选）<input className="input-tech w-full mt-1" value={form.options.image_quality||''} placeholder="留空使用上游默认，例如 high" onChange={e=>patch({options:{...form.options,image_quality:e.target.value}})}/></label>
          <div className="grid grid-cols-2 gap-3"><label>每 Key 并发<input className="input-tech w-full" type="number" min={1} max={8} value={form.options.max_concurrency} onChange={e=>patch({options:{...form.options,max_concurrency:Number(e.target.value)}})}/></label><label>请求超时（秒）<input className="input-tech w-full" type="number" min={15} max={600} value={form.options.timeout_seconds} onChange={e=>patch({options:{...form.options,timeout_seconds:Number(e.target.value)}})}/></label></div><p className="text-xs text-[var(--text-muted)]">仅当供应商明确不支持时关闭参数；关闭尺寸配置后，上游可能自行决定比例。</p>
        </div></details>}
        {formError&&<p role="alert" className="error-box">{formError}</p>}
        <div className="flex justify-end gap-3 pt-3"><button type="button" className="btn-ghost" disabled={saving} onClick={()=>{setModal(null);setForm(empty());}}>取消</button><button className="btn-primary" disabled={saving}>{saving?'保存中…':'保存配置'}</button></div>
      </form>
    </Dialog>}
    {confirmation&&<Dialog title={confirmation.title} onClose={()=>setConfirmation(null)}><p className="text-sm text-[var(--text-secondary)] leading-relaxed">{confirmation.text}</p><div className="flex justify-end gap-3 mt-6"><button className="btn-ghost" onClick={()=>setConfirmation(null)}>取消</button><button className="btn-primary" onClick={async()=>{const action=confirmation.action;setConfirmation(null);try{await action();}catch(e:any){toast.error(e.message);}}}>确认继续</button></div></Dialog>}
  </section>;
}
