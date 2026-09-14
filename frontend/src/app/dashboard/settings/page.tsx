'use client';
import {useEffect,useState} from 'react';
import {toast} from 'sonner';
import ProviderManager from '@/components/ProviderManager';
import {applicationsApi} from '@/lib/api';
import {useAuthStore} from '@/stores/auth';
export default function SettingsPage(){
  const user=useAuthStore(s=>s.user);const [reason,setReason]=useState(''),[apps,setApps]=useState<any[]>([]),[saving,setSaving]=useState(false);
  useEffect(()=>{applicationsApi.my().then(setApps).catch(()=>undefined);},[]);
  return <div className="max-w-6xl mx-auto space-y-8"><ProviderManager/>{!user?.system_api_approved&&<details className="surface p-5"><summary className="font-medium cursor-pointer">没有自己的 Key？申请使用共享模型</summary><div className="space-y-3 mt-4"><textarea aria-label="共享模型申请理由" className="input-tech w-full" rows={3} value={reason} onChange={e=>setReason(e.target.value)} placeholder="使用场景与预计用量（至少 10 字）"/><button className="btn-primary" disabled={saving||reason.trim().length<10} onClick={async()=>{setSaving(true);try{await applicationsApi.create(reason);setReason('');setApps(await applicationsApi.my());toast.success('已提交申请');}catch(e:any){toast.error(e.message);}finally{setSaving(false);}}}>{saving?'提交中…':'提交申请'}</button>{apps.map(a=><p key={a.id} className="text-sm text-[var(--text-muted)]">{a.status==='approved'?'已批准':a.status==='rejected'?'未通过':'待审核'} · {a.reason}</p>)}</div></details>}</div>;
}
