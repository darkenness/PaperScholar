import base64,json,io
from unittest.mock import AsyncMock
import httpx,pytest
from PIL import Image
from app.llm.openai_client import OpenAICompatClient
from app.llm.gemini_client import GeminiNativeClient
from app.llm.endpoint_config import normalize_base_url
from app.llm.image_validation import validate_image_bytes,InvalidModelOutputError
from app.llm.provider_capabilities import image_model_capabilities,resolve_openai_image_size
from conftest import make_image

@pytest.fixture
def transport(monkeypatch):
    original=httpx.AsyncClient;requests=[];result={'data':[{'b64_json':base64.b64encode(make_image()).decode()}]}
    def handler(request):requests.append(request);return httpx.Response(200,json=result)
    monkeypatch.setattr(httpx,'AsyncClient',lambda *a,**kw:original(*a,**{**kw,'transport':httpx.MockTransport(handler)}))
    return requests,result

@pytest.mark.parametrize('root,provider,expected',[
    ('https://relay.test/v1/','openai_compat','https://relay.test/v1'),
    ('https://relay.test/api/v1/chat/completions','openai_compat','https://relay.test/api/v1'),
    ('https://relay.test/v1/images/edits','openai_images','https://relay.test/v1'),
    ('http://localhost:1234/v1','openai_compat','http://localhost:1234/v1'),
    ('https://relay.test/v1beta','gemini','https://relay.test/v1beta'),
    ('https://relay.test/v1','anthropic','https://relay.test'),
])
def test_roots(root,provider,expected):assert normalize_base_url(root,provider)==expected

@pytest.mark.parametrize('url',['file:///etc/passwd','https://u:secret@relay.test/v1','https://relay.test/v1?key=secret','ftp://relay.test'])
def test_bad_root(url):
    with pytest.raises(ValueError):normalize_base_url(url,'openai_compat')

@pytest.mark.parametrize('fmt',['PNG','JPEG','WEBP'])
async def test_multipart_edit_keeps_bytes_and_true_mime(transport,fmt):
    requests,_=transport;raw=make_image(fmt=fmt)
    client=OpenAICompatClient('test-key','https://relay.test/v1/','gpt-image-1',image_api_mode='images')
    assert await client.generate_image_with_images('Move labels',[{'b64':base64.b64encode(raw).decode(),'media_type':'image/png'}],system_instruction='Keep source science')
    req=requests[-1]
    assert req.url.path=='/v1/images/edits' and req.headers['content-type'].startswith('multipart/form-data;')
    assert raw in req.content and Image.MIME[fmt].encode() in req.content and b'Keep source science' in req.content

async def test_multiple_images(transport):
    reqs,_=transport;client=OpenAICompatClient('k',model='custom-model',image_api_mode='images')
    await client.generate_image_with_images('Transfer style',[{'b64':base64.b64encode(make_image(c)).decode()} for c in ['red','blue']])
    assert reqs[-1].content.count(b'name="image[]"')==2

async def test_fallback_obeys_protocol(transport):
    reqs,_=transport;client=OpenAICompatClient('k',model='gpt-image-1',image_api_mode='images')
    await client.generate_image_from_chat(['draw',{'type':'image_base64','data':base64.b64encode(make_image()).decode()}])
    assert reqs[-1].url.path.endswith('/images/edits')
    await client.generate_image_from_chat(['draw']);assert reqs[-1].url.path.endswith('/images/generations')

async def test_strict_relay_options_preserve_model(transport):
    reqs,data=transport;data.clear();data.update({'choices':[{'message':{'content':'OK'}}]})
    client=OpenAICompatClient('k','https://relay.test/v1','namespace/custom-model',api_options={'send_temperature':False,'token_parameter':'max_completion_tokens','send_modalities':False,'send_image_config':False})
    assert await client.chat([{'role':'system','content':'rules'}],max_tokens=27)=='OK'
    body=json.loads(reqs[-1].content)
    assert body['model']=='namespace/custom-model' and body['max_completion_tokens']==27 and 'temperature' not in body and 'max_tokens' not in body
    body=client._build_image_chat_payload('m',[],{'image_size':'4K'})
    assert 'image_config' not in body and 'modalities' not in body

@pytest.mark.parametrize('shape',['images','content','markdown'])
@pytest.mark.parametrize('remote',[False,True])
async def test_relay_image_response_formats(transport,monkeypatch,shape,remote):
    _,data=transport;raw=make_image();url='https://cdn.example/figure.png' if remote else 'data:image/png;base64,'+base64.b64encode(raw).decode()
    msg={'images':[{'image_url':{'url':url}}]} if shape=='images' else {'content':[{'type':'image_url','image_url':{'url':url}}]} if shape=='content' else {'content':f'![figure]({url})'}
    data.clear();data.update({'choices':[{'message':msg}]})
    mock=AsyncMock(return_value=raw);monkeypatch.setattr('app.llm.openai_client.download_image',mock)
    assert await OpenAICompatClient('k',image_api_mode='chat').generate_image('draw')==raw
    assert mock.call_count==int(remote)

@pytest.mark.parametrize('bad',[None,b'',b'<html>login</html>',b'not a figure'])
def test_non_images_rejected(bad):
    with pytest.raises(InvalidModelOutputError):validate_image_bytes(bad)

@pytest.mark.parametrize('model',['gpt-image-2','gpt-image-2-all','relay/custom-image'])
@pytest.mark.parametrize('size',['auto','1536x864','2048x1152'])
def test_custom_sizes_not_clamped(model,size):
    assert image_model_capabilities('openai_images',model)['size_mode']=='custom'
    assert resolve_openai_image_size(model,'16:9',size)==size

def test_real_sdk_image_config():
    from google.genai import types
    assert types.GenerateContentConfig(image_config=types.ImageConfig(image_size='2K')).image_config.image_size=='2K'

async def test_gemini_system_and_non_thought_parts(monkeypatch):
    from google.genai import types
    client=GeminiNativeClient('test',base_url='https://relay.test')
    response=types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(parts=[types.Part(text='hidden',thought=True),types.Part(text='hello'),types.Part(text=' world')]))])
    mock=AsyncMock(return_value=response);monkeypatch.setattr(client._genai_client.aio.models,'generate_content',mock)
    assert await client.chat([{'role':'system','content':'rules'},{'role':'user','content':'hello'}])=='hello world'
    assert mock.call_args.kwargs['config'].system_instruction=='rules'
    assert 'relay.test' in str(client._genai_client._api_client._http_options.base_url)
    await client._genai_client.aio.aclose()

async def test_gemini_empty_candidate(monkeypatch):
    from google.genai import types
    client=GeminiNativeClient('test');monkeypatch.setattr(client._genai_client.aio.models,'generate_content',AsyncMock(return_value=types.GenerateContentResponse(candidates=[types.Candidate(content=None)])))
    assert await client.chat([{'role':'user','content':'hi'}])==''
    await client._genai_client.aio.aclose()
