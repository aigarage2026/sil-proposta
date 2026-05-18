"""
Autenticacao e autorizacao — JWT, password hashing, RBAC dependencies.
Padrao agn-auth da plataforma AI Garage (v3 §6).

Tokens emitidos seguem o shape v3 §6.3:
  { sub, email, tenant_id, products[], roles{by_product},
    exp, iat, iss, aud, kid, trace_id }

Until the Portal exposes JWKS RS256, this module signs locally with HS256.
The decode side already accepts iss/aud claims in lenient mode for forward
compatibility.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.database import get_db

if TYPE_CHECKING:
    from models.user import User

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security_scheme = HTTPBearer(auto_error=False)


# ── Password ────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT ─────────────────────────────────────────────────────────────────────

def _build_roles_claim(role: str, is_platform_admin: bool) -> dict:
    """Builds the v3 `roles{by_product}` claim from the local user record.

    Until the Portal owns roles, every user gets the same role under
    PRODUCT_SLUG, plus a synthesized `platform` role for super admins.
    """
    roles: dict[str, str] = {settings.PRODUCT_SLUG: role}
    if is_platform_admin:
        roles["platform"] = "super_admin"
    else:
        roles["platform"] = "tenant_admin" if role == "owner" else "tenant_user"
    return roles


def create_access_token(
    user_id: str,
    tenant_id: str,
    email: str,
    role: str,
    is_platform_admin: bool = False,
    products: Optional[list[str]] = None,
    trace_id: Optional[str] = None,
    expires_minutes: Optional[int] = None,
) -> str:
    """Issues a v3-shaped access token (HS256 for now; RS256 when Portal lands)."""
    now = datetime.utcnow()
    exp = now + timedelta(minutes=expires_minutes or settings.JWT_EXPIRES_MIN)
    payload = {
        # v3 §6.3 claims
        "sub": user_id,
        "email": email,
        "tenant_id": tenant_id,
        "products": products or [settings.PRODUCT_SLUG],
        "roles": _build_roles_claim(role, is_platform_admin),
        "iss": settings.JWT_ISSUER,
        "aud": [settings.PRODUCT_SLUG],
        "exp": exp,
        "iat": now,
        # Legacy claims kept for backward compatibility with existing
        # decode paths and the frontend until it is updated to read
        # the new shape.
        "role": role,
        "is_platform_admin": is_platform_admin,
    }
    if trace_id:
        payload["trace_id"] = trace_id
    return jwt.encode(
        payload,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
        headers={"kid": settings.JWT_KID},
    )


def create_refresh_token(user_id: str, tenant_id: str) -> str:
    now = datetime.utcnow()
    exp = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRES_DAYS)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "type": "refresh",
        "iss": settings.JWT_ISSUER,
        "aud": [settings.PRODUCT_SLUG],
        "exp": exp,
        "iat": now,
    }
    return jwt.encode(
        payload,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
        headers={"kid": settings.JWT_KID},
    )


async def decode_token(token: str) -> dict:
    """Decodes and validates a JWT — dual mode (v3 §6.5).

    Strategy:
      1. Read the unverified header to learn `alg` and `kid`.
      2. If `alg=RS256` and a JWKS client is enabled, fetch the public
         key for `kid` from the Portal's JWKS and validate.
      3. Else (HS256, or RS256 with no Portal yet) validate locally
         with JWT_SECRET. This is the v3 §6.5 dual-mode fallback.

    iss/aud are enforced only when JWT_STRICT_VALIDATION=true.
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token invalido (header): {e}",
        )

    alg = unverified_header.get("alg")
    kid = unverified_header.get("kid")

    options = {"require": ["exp", "sub"]}
    decode_kwargs: dict = {"options": options}
    if settings.JWT_STRICT_VALIDATION:
        decode_kwargs["issuer"] = settings.JWT_ISSUER
        decode_kwargs["audience"] = settings.PRODUCT_SLUG
    else:
        options["verify_aud"] = False
        options["verify_iss"] = False

    # Try RS256 via Portal JWKS first when the token claims that algorithm.
    if alg == "RS256" and kid:
        from core.jwks_client import get_jwks_client

        jwks = get_jwks_client()
        if jwks.enabled:
            public_key = await jwks.get_signing_key(kid)
            if public_key is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Token kid '{kid}' nao encontrado no JWKS do Portal",
                )
            decode_kwargs["key"] = public_key
            decode_kwargs["algorithms"] = ["RS256"]
            try:
                return jwt.decode(token, **decode_kwargs)
            except jwt.ExpiredSignatureError:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado")
            except jwt.InvalidTokenError as e:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token invalido: {e}")

    # Local HS256 path (legacy tokens, dev tokens, or RS256 fallback when
    # Portal is unreachable but dual mode is on).
    decode_kwargs["key"] = settings.JWT_SECRET
    decode_kwargs["algorithms"] = [settings.JWT_ALGORITHM]
    try:
        return jwt.decode(token, **decode_kwargs)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token invalido: {e}")


def decode_token_sync(token: str) -> dict:
    """Synchronous fallback for callsites that can't await (rare).

    Always uses local HS256. Don't use in async paths — prefer decode_token().
    """
    options = {"require": ["exp", "sub"]}
    if not settings.JWT_STRICT_VALIDATION:
        options["verify_aud"] = False
        options["verify_iss"] = False
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options=options,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token invalido: {e}")


# ── Dependencies ────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> "User":
    """Extrai usuario do JWT. Retorna modelo User completo."""
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token nao fornecido")

    payload = await decode_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido")

    from models.user import User
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario nao encontrado")

    return user


async def get_current_tenant_id(request: Request) -> str:
    """Extrai tenant_id do JWT sem carregar o User completo."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token nao fornecido")
    payload = await decode_token(auth[7:])
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant nao identificado")
    return tenant_id


def require_role(allowed_roles: list[str]):
    """Dependency factory — verifica se o usuario tem um dos roles permitidos."""
    async def checker(user=Depends(get_current_user)):
        if user.is_platform_admin:
            return user
        if user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissao insuficiente")
        return user
    return checker


def get_platform_admin(user=Depends(get_current_user)):
    """Dependency — exige platform admin."""
    if not user.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito a administradores da plataforma")
    return user
