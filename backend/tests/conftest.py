"""Real FastAPI/ORM/SDK fixtures. Only external model I/O is replaced."""
import os,sys,io
from pathlib import Path
os.environ.setdefault('SECRET_KEY','regression-encryption-secret-not-production')
os.environ.setdefault('JWT_SECRET_KEY','regression-jwt-secret-not-production')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest,pytest_asyncio,httpx
from PIL import Image
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.config import settings
from app.core.database import Base
import app.models
from app.models.user import User
from app.models.api_key import ApiKeyConfig
from app.core.security import encrypt_api_key,create_access_token

@compiles(JSONB,'sqlite')
def compile_jsonb(type_,compiler,**kwargs):return 'JSON'

def make_image(color='red',fmt='PNG'):
    out=io.BytesIO();Image.new('RGB',(96,64),color).save(out,format=fmt);return out.getvalue()

def auth(uid):return {'Authorization':'Bearer '+create_access_token({'sub':str(uid)})}

@pytest.fixture(autouse=True)
def clean_state():
    import asyncio
    from app.llm import load_balancer as mod
    mod._GLOBAL_KEY_COOLDOWNS.clear();mod._GLOBAL_KEY_IN_FLIGHT.clear();mod._GLOBAL_POOL_LOCK=asyncio.Lock()
    from app.core.rate_limit import _request_log
    _request_log.clear()

@pytest_asyncio.fixture
async def database(tmp_path,monkeypatch):
    url=os.environ.get('TEST_DATABASE_URL') or f'sqlite+aiosqlite:///{tmp_path}/db.sqlite'
    engine=create_async_engine(url)
    if url.startswith('sqlite'):
        @event.listens_for(engine.sync_engine,'connect')
        def pragma(connection,_):connection.execute('PRAGMA foreign_keys=ON');connection.execute('PRAGMA busy_timeout=10000')
    async with engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    import app.core.database as mod
    monkeypatch.setattr(mod,'AsyncSessionLocal',factory)
    import app.services.generation_service as service
    monkeypatch.setattr(service,'AsyncSessionLocal',factory)
    monkeypatch.setattr(settings,'UPLOAD_DIR',str(tmp_path/'uploads'));Path(settings.UPLOAD_DIR).mkdir()
    async with factory() as db:
        db.add_all([User(id=i,username=name,email=f'{name}@example.test',password_hash='test',role='admin' if i==3 else 'user') for i,name in [(1,'reader'),(2,'other'),(3,'admin')]])
        await db.commit()
    yield factory
    from app.services.task_control import shutdown_tasks
    await shutdown_tasks()
    async with engine.begin() as conn:await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def client(database):
    from app.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test',headers=auth(1)) as client:yield client

async def add_configs(factory,uid=1,image=True):
    async with factory() as db:
        chat=ApiKeyConfig(user_id=uid,model_type='chat',provider='openai_compat',base_url='https://relay.example/v1',api_key_encrypted=encrypt_api_key('test-secret'),model_name='reader-model',is_enabled=True,is_verified=True,priority=0);db.add(chat)
        img=None
        if image:
            img=ApiKeyConfig(user_id=uid,model_type='image',provider='openai_images',base_url='https://relay.example/v1',api_key_encrypted=encrypt_api_key('image-secret'),model_name='gpt-image-1',is_enabled=True,is_verified=True,priority=0);db.add(img)
        await db.commit();return chat,img
