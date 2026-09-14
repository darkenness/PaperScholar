"""Explicit API roots: preserve custom paths/model IDs; never guess a version."""
from urllib.parse import urlsplit, urlunsplit

DEFAULT_ROOTS = {
    "openai_compat": "https://openrouter.ai/api/v1",
    "openai_images": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com",
    "anthropic": "https://api.anthropic.com",
}

def normalize_base_url(value, provider):
    root = (value or DEFAULT_ROOTS[provider]).strip().rstrip("/")
    parts = urlsplit(root)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("服务地址必须为完整 HTTP(S) URL")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("服务地址不能包含账号、密码、查询参数或片段")
    path = parts.path
    for suffix in ("/chat/completions", "/images/generations", "/images/edits"):
        if path.endswith(suffix):
            path = path[:-len(suffix)]
            break
    if provider == "anthropic" and path.endswith("/v1"):
        path = path[:-3]
    return urlunsplit((parts.scheme, parts.netloc, path.rstrip("/"), "", ""))

def effective_model(provider, model_type, model):
    if model and model.strip():
        return model.strip()
    defaults = {"openai_images": "gpt-image-1", "gemini": "gemini-2.5-flash-image" if model_type == "image" else "gemini-2.5-pro", "anthropic": "claude-sonnet-4-20250514"}
    return defaults.get(provider, "")

def endpoint_preview(provider, value):
    root = normalize_base_url(value, provider)
    if provider == "openai_images":
        return {"generate":root+"/images/generations", "edit":root+"/images/edits"}
    if provider == "openai_compat":
        return {"request":root+"/chat/completions"}
    if provider == "anthropic":
        return {"request":root+"/v1/messages"}
    version = root.rsplit("/",1)[-1]
    return {"request":root + ("" if version in {"v1", "v1beta", "v1alpha"} else "/v1beta") + "/models/{model}:generateContent"}
