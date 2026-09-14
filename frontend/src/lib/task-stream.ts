/** Authenticated SSE, event replay and bounded reconnects. */
import {generateApi} from './api';
export interface TaskEvent {id?:string; type:string; data:any;}
export function subscribeTask(taskId:string,onEvent:(event:TaskEvent)=>void,onConnection:(state:string)=>void) {
  const controller=new AbortController();let lastId='';let finished=false;
  const sleep=(ms:number)=>new Promise<void>(resolve=>{const timer=setTimeout(done,ms);function done(){clearTimeout(timer);controller.signal.removeEventListener('abort',done);resolve();}controller.signal.addEventListener('abort',done,{once:true});});
  void(async()=>{
    let attempts=0;
    while(!controller.signal.aborted&&!finished&&attempts<12){
      attempts++;
      try{
        onConnection(attempts>1?'连接中断，正在恢复进度…':'连接进度服务…');
        const token=localStorage.getItem('token');
        const res=await fetch(generateApi.streamUrl(taskId),{signal:controller.signal,headers:{...(token?{Authorization:`Bearer ${token}`}:{ }),...(lastId?{'Last-Event-ID':lastId}:{ })}});
        if(!res.ok||!res.body){if([401,403,404].includes(res.status)){onConnection('任务不可访问或登录已过期，请重新登录/刷新。');return;}throw new Error(`HTTP ${res.status}`);}
        onConnection('已连接');const reader=res.body.getReader();const decoder=new TextDecoder();let buffer='';
        try{
          while(!controller.signal.aborted&&!finished){
            const {value,done}=await reader.read();if(done)break;
            buffer+=decoder.decode(value,{stream:true}).replace(/\r/g,'');let end:number;
            while((end=buffer.indexOf('\n\n'))>=0){
              const block=buffer.slice(0,end);buffer=buffer.slice(end+2);
              let type='message',id='';const lines:string[]=[];
              for(const line of block.split('\n')){if(line.startsWith('event:'))type=line.slice(6).trim();else if(line.startsWith('id:'))id=line.slice(3).trim();else if(line.startsWith('data:'))lines.push(line.slice(5).trimStart());}
              if(!lines.length||(id&&lastId&&Number(id)<=Number(lastId)))continue;
              const data=JSON.parse(lines.join('\n'));if(id)lastId=id;
              onEvent({id:id||undefined,type,data});if(type==='done'){finished=true;break;}
            }
          }
        }finally{await reader.cancel().catch(()=>undefined);}
        if(!finished)throw new Error('Stream closed');
      }catch(e){
        if(controller.signal.aborted)break;
        try{const task=await generateApi.getTask(taskId);if(['completed','failed','cancelled'].includes(task.status)){onEvent({type:'done',data:{status:task.status,message:task.error_message}});finished=true;break;}}catch{/* keep task available for refresh */}
        onConnection(attempts>=12?'进度连接暂不可用；任务仍可能在运行，可刷新恢复。':'连接中断，正在恢复进度…');
        if(attempts<12)await sleep(Math.min(1000*2**(attempts-1),10000));
      }
    }
  })();
  return ()=>controller.abort();
}
