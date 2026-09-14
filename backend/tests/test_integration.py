import asyncio,uuid,base64
from unittest.mock import AsyncMock
from types import SimpleNamespace
import pytest
from sqlalchemy import select,update
from app.models.api_key import ApiKeyConfig
from app.models.generation import GenerationTask,GenerationResult,PipelineEvent
from app.services.generation_service import run_generation_task,_build_load_balancer
from app.services.artifact_service import write_image,safe_artifact_path
from app.core.security import decrypt_api_key,mask_api_key,encrypt_api_key
from conftest import add_configs,auth,make_image
from test_pipeline import Models

async def new_task(factory,**kw):
    async with factory() as db:
        task=GenerationTask(**{'user_id':1,'task_type':'diagram','content':'Existing inputs are encoded then processed then decoded.','visual_intent':'Overview of the existing method.','pipeline_mode':'demo_full','retrieval_setting':'none','num_candidates':1,'max_critic_rounds':0,'request_params':{'quality_guard':True,'image_size':'2K'},'status':'pending',**kw})
        db.add(task);await db.commit();return task

@pytest.fixture
def no_launch(monkeypatch):monkeypatch.setattr('app.api.generate.launch_task',lambda id,coro:coro.close())

async def test_create_clone_reuses_secret(client,database):
    response=await client.post('/api/v1/api-keys',json={'model_type':'chat','provider':'openai_compat','base_url':'https://relay.test/v1/chat/completions','api_key':'short','model_name':'reader','display_name':'Test relay'})
    assert response.status_code==201,response.text
    data=response.json();assert data['base_url']=='https://relay.test/v1' and 'short' not in response.text
    response=await client.post(f"/api/v1/api-keys/{data['id']}/models",json={'model_type':'image','provider':'openai_images','model_name':'custom-image'})
    assert response.status_code==201,response.text
    async with database() as db:
        cfg=await db.get(ApiKeyConfig,response.json()['id']);assert decrypt_api_key(cfg.api_key_encrypted)=='short' and not cfg.is_verified

async def test_cannot_promote_to_shared(client,database):
    key,_=await add_configs(database)
    assert (await client.put(f'/api/v1/api-keys/{key.id}',json={'priority':-1})).status_code==422

@pytest.mark.parametrize('method,path,payload',[('PUT','',{'model_name':'oops'}),('DELETE','',None),('POST','/verify',None),('GET','/models',None)])
async def test_key_ownership(client,database,method,path,payload):
    key,_=await add_configs(database,uid=2)
    assert (await client.request(method,f'/api/v1/api-keys/{key.id}{path}',json=payload)).status_code==404

async def test_independent_capability_status(client,database,monkeypatch):
    _,key=await add_configs(database)
    fake=SimpleNamespace(generate_image=AsyncMock(return_value=make_image()),generate_image_with_images=AsyncMock(side_effect=ValueError('edit not supported')))
    monkeypatch.setattr('app.services.provider_service.LLMClientFactory.create',lambda **kw:fake)
    assert (await client.post(f'/api/v1/api-keys/{key.id}/verify?capability=image_generation')).json()['is_verified']
    result=(await client.post(f'/api/v1/api-keys/{key.id}/verify?capability=image_edit')).json()
    assert result['is_verified'] and result['status']=='failed' and result['capability_status']['image_generation']['status']=='passed'

async def test_display_name_only_preserves_validation(client,database):
    key,_=await add_configs(database)
    response=await client.put(f'/api/v1/api-keys/{key.id}',json={'display_name':'Renamed only'})
    assert response.status_code==200,response.text
    assert response.json()['is_verified']

async def test_admin_api_reuses_validation(client,database):
    response=await client.post('/api/v1/admin/system-keys',headers=auth(3),json={'model_type':'image','provider':'openai_images','api_key':'test-admin-key','model_name':'gpt-image-1'})
    assert response.status_code==201,response.text
    id=response.json()['id']
    async with database() as db:
        key=await db.get(ApiKeyConfig,id);key.is_verified=True;key.capability_status={'image_generation':{'status':'passed'}};await db.commit()
    response=await client.put(f'/api/v1/admin/system-keys/{id}',headers=auth(3),json={'base_url':'https://new.test/v1'})
    assert response.status_code==200,response.text
    assert not response.json()['is_verified'] and response.json()['capability_status']=={}
    assert (await client.delete(f'/api/v1/api-keys/{id}',headers=auth(3))).status_code==404

async def test_parameters_and_zero_rounds_persist(client,database,no_launch):
    await add_configs(database)
    response=await client.post('/api/v1/generate',json={'task_type':'diagram','content':'Original methodology content','visual_intent':'Draw its overview','max_critic_rounds':0,'image_size':'4K','candidate_strategy':'layouts','num_candidates':4})
    assert response.status_code==201,response.text
    async with database() as db:
        task=await db.get(GenerationTask,uuid.UUID(response.json()['task_id']));assert task.max_critic_rounds==0 and task.request_params['image_size']=='4K' and task.request_params['candidate_strategy']=='layouts'

async def test_preflight_missing_models(client,database,no_launch):
    response=await client.post('/api/v1/generate',json={'content':'Original methodology content','visual_intent':'Draw its overview','task_type':'diagram'})
    assert response.status_code==400,response.text
    async with database() as db:assert not (await db.execute(select(GenerationTask))).scalars().all()

async def test_real_pipeline_checkpoints_before_done(client,database,monkeypatch):
    await add_configs(database);model=Models();monkeypatch.setattr('app.llm.client_factory.LLMClientFactory.create',lambda **kw:model)
    task=await new_task(database);await run_generation_task(task.id)
    async with database() as db:
        done=await db.get(GenerationTask,task.id);assert done.status=='completed',done.error_message
        events=(await db.execute(select(PipelineEvent).where(PipelineEvent.task_id==task.id).order_by(PipelineEvent.id))).scalars().all()
        images=[e for e in events if e.event_data.get('image_url')];assert images and images[0].id<events[-1].id
        assert safe_artifact_path(images[0].event_data['image_path']).read_bytes()==make_image() and 'image_base64' not in images[0].event_data
        assert images[0].event_data['description'] and images[0].event_data['candidate_index']==0
    assert model.images==1
    response=await client.get(f'/api/v1/generate/{task.id}/stream',headers={**auth(1),'Last-Event-ID':str(images[0].id)})
    assert response.status_code==200 and f'id: {images[0].id}\r\n' not in response.text and 'event: done' in response.text
    assert (await client.get(f'/api/v1/generate/{task.id}/download')).status_code==200
    assert (await client.get(f'/api/v1/generate/{task.id}/download',headers=auth(2))).status_code==404

async def test_atomic_claim_once(database,monkeypatch):
    await add_configs(database);model=Models();monkeypatch.setattr('app.llm.client_factory.LLMClientFactory.create',lambda **kw:model)
    task=await new_task(database);await asyncio.gather(run_generation_task(task.id),run_generation_task(task.id));assert model.images==1
    async with database() as db:assert len((await db.execute(select(GenerationResult).where(GenerationResult.task_id==task.id))).scalars().all())==1

async def test_cancel_pending_no_execution(client,database,monkeypatch):
    await add_configs(database);model=Models();monkeypatch.setattr('app.llm.client_factory.LLMClientFactory.create',lambda **kw:model)
    task=await new_task(database)
    assert (await client.post(f'/api/v1/generate/{task.id}/cancel')).status_code==200
    await run_generation_task(task.id);assert not model.calls
    async with database() as db:assert (await db.get(GenerationTask,task.id)).status=='cancelled'

async def test_cancel_running_not_overwritten(client,database,monkeypatch):
    await add_configs(database);model=Models();entered=asyncio.Event();release=asyncio.Event()
    async def generate(**kw):entered.set();await release.wait();return make_image()
    model.generate_image=generate;monkeypatch.setattr('app.llm.client_factory.LLMClientFactory.create',lambda **kw:model)
    task=await new_task(database);running=asyncio.create_task(run_generation_task(task.id));await asyncio.wait_for(entered.wait(),5)
    assert (await client.post(f'/api/v1/generate/{task.id}/cancel')).status_code==200
    release.set();await asyncio.wait_for(running,5)
    async with database() as db:assert (await db.get(GenerationTask,task.id)).status=='cancelled'

async def test_empty_result_not_completed(database,monkeypatch):
    await add_configs(database);model=Models();model.generate_image=AsyncMock(side_effect=TypeError('bad response'));model.generate_image_from_chat=AsyncMock(return_value=None)
    monkeypatch.setattr('app.llm.client_factory.LLMClientFactory.create',lambda **kw:model)
    monkeypatch.setattr('app.llm.load_balancer.LoadBalancer._cooldown_seconds',lambda *a:(0,False))
    task=await new_task(database);await run_generation_task(task.id)
    async with database() as db:
        task=await db.get(GenerationTask,task.id);assert task.status=='failed' and task.error_message
        assert not (await db.execute(select(GenerationResult).where(GenerationResult.task_id==task.id))).scalars().all()

async def test_baseline_saved_after_budget_stop(database,monkeypatch):
    from app.services.cost_service import BudgetExceededError
    await add_configs(database);model=Models();model.chat_with_images=AsyncMock(side_effect=BudgetExceededError('budget'))
    monkeypatch.setattr('app.llm.client_factory.LLMClientFactory.create',lambda **kw:model)
    task=await new_task(database,max_critic_rounds=1);await run_generation_task(task.id)
    async with database() as db:
        assert (await db.get(GenerationTask,task.id)).status=='failed'
        images=(await db.execute(select(GenerationResult).where(GenerationResult.task_id==task.id))).scalars().all()
        assert len(images)==1 and images[0].metadata_['checkpoint'] and safe_artifact_path(images[0].image_path).read_bytes()==make_image()

async def test_historical_candidate_ownership(client,database,no_launch):
    task=await new_task(database,status='completed',num_candidates=2);path=write_image(task.id,0,make_image())
    async with database() as db:
        result=GenerationResult(task_id=task.id,user_id=1,candidate_index=0,image_path=path);event=PipelineEvent(task_id=task.id,event_type='intermediate',event_data={'candidate_index':1,'image_path':path});db.add_all([result,event]);await db.commit();rid,eid=result.id,event.id
    response=await client.post(f'/api/v1/generate/{task.id}/continue',json={'result_id':rid,'source_event_id':eid,'feedback':'Move labels'})
    assert response.status_code==400

async def test_reference_validation_and_owner(client,database):
    bad=await client.post('/api/v1/references/upload',files={'file':('bad.png',b'not an image','image/png')});assert bad.status_code==400
    good=await client.post('/api/v1/references/upload',files={'file':('img.jpg',make_image(fmt='JPEG'),'image/png')});assert good.status_code==201,good.text
    from app.services.generation_service import _load_references
    async with database() as db:
        with pytest.raises(ValueError):await _load_references(db,2,[good.json()['id']])

async def test_auto_route_same_model_only(database):
    first,_=await add_configs(database,image=False)
    async with database() as db:
        db.add(ApiKeyConfig(user_id=1,model_type='chat',provider='openai_compat',base_url='https://relay.test/v1',api_key_encrypted=encrypt_api_key('x'),model_name='other-model',is_enabled=True,is_verified=True,priority=0));await db.commit()
        lb=await _build_load_balancer(db,1,'chat');assert {s.config.model for s in lb._states}=={'reader-model'}
        with pytest.raises(ValueError):await _build_load_balancer(db,1,'chat',key_id=first.id,model_name='not-the-same')

@pytest.mark.parametrize('key',['a','short','12345678'])
def test_short_secrets_masked(key):assert mask_api_key(key)=='***'

@pytest.mark.parametrize('path',['../secret','/etc/passwd','results/../../secret'])
def test_artifact_traversal(path):
    with pytest.raises(ValueError):safe_artifact_path(path)
