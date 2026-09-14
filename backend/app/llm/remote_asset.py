"""Bounded provider image downloads. Credentials never go to an asset host.

Unrelated asset hosts must resolve to public addresses. Explicitly configured
provider roots may be private. Enforce network egress policy in production too:
DNS checks alone cannot provide a complete DNS-rebinding defense.
"""
import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit, urljoin
import httpx
from app.llm.image_validation import validate_image_bytes, InvalidModelOutputError


def origin(url):
    p=urlsplit(url)
    return p.scheme,p.hostname,p.port or (443 if p.scheme=='https' else 80)


async def validate_asset_url(url, trusted_origin=None):
    p=urlsplit(url)
    if p.scheme not in {'http','https'} or not p.hostname or p.username or p.password:
        raise InvalidModelOutputError('Unsupported image asset URL')
    if trusted_origin and origin(url)==origin(trusted_origin):
        return
    try:
        records=await asyncio.get_running_loop().getaddrinfo(p.hostname,p.port or (443 if p.scheme=='https' else 80),type=socket.SOCK_STREAM)
    except OSError as exc:
        raise InvalidModelOutputError('Cannot resolve image asset host') from exc
    if not records or not all(ipaddress.ip_address(x[4][0]).is_global for x in records):
        raise InvalidModelOutputError('Image URL resolves to a non-public host')


async def download_image(url, *, trusted_origin=None, timeout=180):
    async with httpx.AsyncClient(timeout=timeout,follow_redirects=False) as client:
        for _ in range(5):
            await validate_asset_url(url,trusted_origin)
            async with client.stream('GET',url) as response:
                if response.is_redirect:
                    if not response.headers.get('location'):
                        raise InvalidModelOutputError('Missing redirect location')
                    url=urljoin(url,response.headers['location'])
                    continue
                response.raise_for_status()
                chunks=[];total=0
                async for chunk in response.aiter_bytes():
                    total+=len(chunk)
                    if total>64*1024*1024:
                        raise InvalidModelOutputError('Image asset exceeds 64 MiB')
                    chunks.append(chunk)
                return await asyncio.to_thread(validate_image_bytes,b''.join(chunks))
    raise InvalidModelOutputError('Too many image redirects')
