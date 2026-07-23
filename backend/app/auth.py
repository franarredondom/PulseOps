from dataclasses import dataclass
import asyncio
from time import monotonic
from typing import Annotated, Any

import httpx
from fastapi import Header, HTTPException, status

from .config import get_settings


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    name: str


_token_cache: dict[str, tuple[float, AuthUser]] = {}
_cache_lock = asyncio.Lock()
CACHE_SECONDS = 60


def _user_from_payload(payload: dict[str, Any]) -> AuthUser:
    metadata = payload.get("user_metadata") or {}
    email = str(payload.get("email") or "")
    name = str(metadata.get("full_name") or metadata.get("name") or email.split("@", 1)[0] or "Usuario")
    return AuthUser(id=str(payload["id"]), email=email, name=name[:120])


async def get_current_user(authorization: Annotated[str | None, Header()] = None) -> AuthUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inicia sesión para continuar")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="La sesión no es válida")

    settings = get_settings()
    if not settings.supabase_publishable_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="La autenticación no está configurada")

    now = monotonic()
    async with _cache_lock:
        cached = _token_cache.get(token)
        if cached and cached[0] > now:
            return cached[1]

        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.get(
                    f"{settings.supabase_url}/auth/v1/user",
                    headers={
                        "apikey": settings.supabase_publishable_key,
                        "Authorization": f"Bearer {token}",
                    },
                )
        except httpx.HTTPError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No fue posible validar la sesión") from error

        if response.status_code != 200:
            _token_cache.pop(token, None)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="La sesión expiró o no es válida")

        user = _user_from_payload(response.json())
        if len(_token_cache) >= 500:
            expired = [key for key, value in _token_cache.items() if value[0] <= now]
            for key in expired or list(_token_cache)[:100]:
                _token_cache.pop(key, None)
        _token_cache[token] = (now + CACHE_SECONDS, user)
        return user
