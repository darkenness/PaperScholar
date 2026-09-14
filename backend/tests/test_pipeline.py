import base64,json,hashlib
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from app.agents.pipeline import PipelineEngine,CriticAgent,VisualizerAgent
from app.agents.polish_agent import PolishAgent
from app.agents.quality import choose_revision
from app.services.cost_service import BudgetExceededError
from conftest import make_image
class Models:
    def __init__(self,revise=False,accept=False):self.calls=[];self.revise=revise;self.accept=accept;self.images=0
    async def chat(self,messages,**kwargs):self.calls.append(('chat',messages));return 'Draw input -> core method -> output. Preserve source relationships.'
    async def chat_with_images(self,contents,system_prompt='',**kwargs):
        self.calls.append(('vision',contents))
        if 'Compare the two' in system_prompt:return json.dumps({'choice':'candidate' if self.accept else 'previous','reason':'comparison'})
        return json.dumps({'critic_suggestions':'Fix label' if self.revise else 'No changes needed.','revised_description':'Draw corrected labels preserving method.' if self.revise else 'No changes needed.'})
    async def generate_image(self,prompt,**kwargs):self.calls.append(('image',prompt));self.images+=1;return make_image('red' if self.images==1 else 'blue')
    async def generate_image_with_images(self,prompt,images,**kwargs):self.calls.append(('edit',images));self.images+=1;return make_image('blue')
    async def generate_image_from_chat(self,contents,**kwargs):return await self.generate_image(str(contents))
def source(**kw):return {'content':'Input is encoded, processed by the core method, then decoded to output.','visual_intent':'An overview of the existing input/core/output method.','task_type':'diagram','retrieval_setting':'none',**kw}

@pytest.mark.parametrize('mode',['vanilla','dev_planner','dev_planner_stylist','dev_planner_critic','demo_planner_critic','demo_full','dev_full'])
@pytest.mark.parametrize('num',[1,3])
async def test_modes_with_zero_rounds(mode,num):
    models=Models();events=[]
    async def emit(t,d):events.append((t,d))
    out=await PipelineEngine(models,models).run(source(),mode=mode,num_candidates=num,max_critic_rounds=0,on_event=emit)
    candidates=out.get('candidates') or [out]
    assert len(candidates)==num and all(c['image_base64'] for c in candidates)
    assert not any(t=='stage' and d.get('name')=='critic' for t,d in events)
    assert all('candidate_index' in d for t,d in events if d.get('image_base64'))
    if mode=='vanilla':assert not any(kind=='chat' for kind,_ in models.calls)

async def test_original_bytes_preserved():
    model=Models();out=await PipelineEngine(model,model).run(source(),mode='demo_full',max_critic_rounds=0)
    assert base64.b64decode(out['image_base64'])==make_image()

async def test_candidate_zero_baseline_and_variants():
    model=Models();out=await PipelineEngine(model,model).run(source(candidate_strategy='layouts'),num_candidates=3,max_critic_rounds=0,mode='demo_full')
    assert out['candidates'][0]['stylist_description']==out['candidates'][0]['planner_description']
    assert len([x for kind,x in model.calls if kind=='chat' and 'alternative scientific' in x[0]['content']])==2

async def test_rejected_revision_retains_baseline_and_history():
    model=Models(revise=True);events=[]
    async def emit(t,d):events.append((t,d))
    out=await PipelineEngine(model,model).run(source(),mode='demo_full',max_critic_rounds=2,on_event=emit)
    assert base64.b64decode(out['image_base64'])==make_image()
    images=[d for _,d in events if d.get('image_base64')]
    assert len(images)>=2 and all(d.get('description') for d in images)

async def test_short_important_critique_not_ignored():
    model=Models(revise=True,accept=True)
    await PipelineEngine(model,model).run(source(),mode='demo_full',max_critic_rounds=2)
    assert model.images==3

async def test_failed_comparison_keeps_old():
    model=Models();model.chat_with_images=AsyncMock(side_effect=RuntimeError('no vision'))
    old=base64.b64encode(make_image()).decode()
    accepted,_=await choose_revision(model,old,old,source());assert not accepted

async def test_vision_failure_not_blind_review():
    model=Models();model.chat_with_images=AsyncMock(side_effect=RuntimeError('no vision'))
    data=source(image_base64=base64.b64encode(make_image()).decode(),critic_round=0,planner_description='plan')
    await CriticAgent(chat_lb=model).process(data)
    assert data['critic_parse_failed_0'] and not model.calls

async def test_edit_failure_not_text_only():
    model=Models();model.chat_with_images=AsyncMock(return_value='Improve label layout');model.generate_image_with_images=AsyncMock(side_effect=RuntimeError('not supported'))
    data=source(image_base64=base64.b64encode(make_image()).decode())
    out=await PolishAgent(chat_lb=model,image_lb=model).process(data)
    assert 'polished_image_base64' not in out and model.images==0

async def test_budget_stop_not_swallowed():
    model=Models();model.generate_image=AsyncMock(side_effect=BudgetExceededError('budget'))
    with pytest.raises(BudgetExceededError):await PipelineEngine(model,model).run(source(),max_critic_rounds=0)

async def test_empty_image_is_failure():
    model=Models();model.generate_image=AsyncMock(return_value=None);model.generate_image_from_chat=AsyncMock(return_value=None)
    with pytest.raises(RuntimeError):await PipelineEngine(model,model).run(source(),max_critic_rounds=0,num_candidates=2)

async def test_provider_image_error_does_not_switch_protocol():
    model=Models()
    model.generate_image=AsyncMock(side_effect=RuntimeError("401 invalid key"))
    model.generate_image_from_chat=AsyncMock(return_value=make_image("blue"))
    with pytest.raises(RuntimeError,match="401 invalid key"):
        await PipelineEngine(model,model).run(source(),max_critic_rounds=0)
    model.generate_image_from_chat.assert_not_awaited()

async def test_unsupported_native_image_protocol_can_fallback():
    model=Models()
    model.generate_image=AsyncMock(side_effect=NotImplementedError("native protocol unavailable"))
    model.generate_image_from_chat=AsyncMock(return_value=make_image("blue"))
    result=await PipelineEngine(model,model).run(source(),max_critic_rounds=0)
    assert result["image_base64"]==base64.b64encode(make_image("blue")).decode()
    model.generate_image_from_chat.assert_awaited_once()

async def test_continuation_passes_original_image():
    model=Models(revise=True,accept=True);raw=make_image()
    out=await PipelineEngine(model,model).run(source(image_base64=base64.b64encode(raw).decode(),planner_description='baseline',user_feedback='Move labels',preserve_layout=True),mode='continue_feedback',max_critic_rounds=1)
    calls=[x for kind,x in model.calls if kind=='edit']
    assert len(calls)==1 and base64.b64decode(calls[0][0]['b64'])==raw
    assert base64.b64decode(out['image_base64'])==make_image('blue')

def test_original_prompts_and_styles_unchanged():
    import app.agents.pipeline as pipeline
    fixture=json.loads((Path(__file__).parent/'fixtures/prompt_baseline.json').read_text())
    for name,digest in fixture['prompts'].items():assert hashlib.sha256(getattr(pipeline,name).encode()).hexdigest()==digest,name
    for name,digest in fixture['styles'].items():assert hashlib.sha256((Path(pipeline.__file__).parent/'style_guides'/name).read_bytes()).hexdigest()==digest,name
