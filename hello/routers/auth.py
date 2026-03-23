"""Authentication + MIQ RBAC helpers shared by the main FastAPI app."""

from __future__ import annotations

from typing import Annotated, Optional, TypedDict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from authlib.integrations.starlette_client import OAuth
from hello.services.config import settings
from hello.utils.auth_utils import (
    extract_email_and_oid_from_idp_token,
    mint_app_jwt, set_session_cookie, require_auth, 
    clear_session_cookie,
    get_user_info_from_miq,
    validate_and_get_miq_user_id_and_exp,
    get_or_create_user_from_miq,
    build_miq_claims,
)
from hello.services.database import get_session

from sqlalchemy.ext.asyncio import AsyncSession
from logging import getLogger


router = APIRouter(tags=["auth"])
oauth = OAuth()
logger = getLogger(__name__)

WELLKNOWN_OIDC_ENDPOINT = f"{settings.OIDC_ISSUER.rstrip('/') if settings.OIDC_ISSUER else '' }/.well-known/openid-configuration"
ENV = settings.TESTING_ENV

oauth.register(
    name="idp",
    server_metadata_url=WELLKNOWN_OIDC_ENDPOINT,
    client_id=settings.OIDC_CLIENT_ID,
    client_secret=settings.OIDC_CLIENT_SECRET,
    client_kwargs={"scope": settings.OIDC_SCOPES},
)

@router.get("/login")
async def auth_login(request: Request):
    """
    Start Azure AD login.
    If the caller wants the JWT as JSON at callback time, they call:
      GET /login?mode=json 
    We store that preference in the server session (no change to redirect_uri).
    """
    logger.info("Login redirect initiated api_base_url=%s", settings.api_base_url)
    if ENV == "CBRE":
        return await oauth.idp.authorize_redirect(request, redirect_uri=f"{settings.api_base_url}/auth/callback") # type: ignore
    else:
        return RedirectResponse(url=f"{settings.api_base_url}/auth/callback")

@router.get("/login-miq")
async def auth_login_miq(request: Request, session: Annotated[AsyncSession, Depends(get_session)]):
    """
    Start MIQ login.
    """
    miq_jwt = request.query_params.get("jwt")
    if not miq_jwt:
        raise HTTPException(status_code=400, detail="No JWT provided")
    
    user_id, miq_exp = await validate_and_get_miq_user_id_and_exp(miq_jwt)
    
    user_info, user_permissions = await get_user_info_from_miq(user_id=user_id)

    if user_info.statusVal.lower() != "active":
        logger.error(f"User {user_info.emailAddress} is not active (status: {user_info.statusVal})")
        raise HTTPException(status_code=403, detail="User is not active")
    
    # Get or create user in database
    user = await get_or_create_user_from_miq(
        session, email=user_info.emailAddress, user_info=user_info
    )
    
    # Build enriched claims with MIQ data
    miq_claims = build_miq_claims(
        user=user, user_info=user_info, user_permissions=user_permissions
    )
    
    
    app_jwt = mint_app_jwt(
        email=user_info.emailAddress,
        azure_oid=None,
        aad_exp=miq_exp,
        extra_claims=miq_claims,
    )
    resp = JSONResponse(content={"status": "success"})
    set_session_cookie(resp, app_jwt)
    return resp

@router.get("/callback")
async def auth_callback(request: Request, session: Annotated[AsyncSession, Depends(get_session)]):
    # Extract email and Azure credentials based on environment
    if ENV == "CBRE":
        token = await oauth.idp.authorize_access_token(request) # type: ignore
        email, oid, aad_exp = extract_email_and_oid_from_idp_token(token)
        if not email:
            raise HTTPException(status_code=403, detail="No email claim from IdP")
        email = email.lower()
    else:
        email = "admin@cbre.com"
        oid = None
        aad_exp = None
    
    # Fetch user info from MIQ (handles ENV check internally)
    user_info, user_permissions = await get_user_info_from_miq(email=email)
    
    # Check user status from MIQ
    if user_info.statusVal.lower() != "active":
        logger.error(f"User {email} is not active (status: {user_info.statusVal})")
        raise HTTPException(status_code=403, detail="User is not active")
    
    # Get or create user in database
    user = await get_or_create_user_from_miq(session, email=email, user_info=user_info)
    
    # Build enriched claims with MIQ data
    miq_claims = build_miq_claims(
        user=user, user_info=user_info, user_permissions=user_permissions
    )
    
    app_jwt = mint_app_jwt(email=email, azure_oid=oid, extra_claims=miq_claims)

    resp = RedirectResponse(url=f"{settings.FRONTEND_ORIGIN}")
    set_session_cookie(resp, app_jwt)
    return resp


@router.get("/logout")
async def auth_logout(request: Request):
    """
    Logout endpoint.
    Clears the session cookie and redirects to the frontend.
    """
    if ENV == "CBRE":
        resp = RedirectResponse(url=f"{settings.OIDC_LOGOUT_URL}?post_logout_redirect_uri={settings.FRONTEND_ORIGIN}/signin")
    else:
        resp = RedirectResponse(url=f"{settings.FRONTEND_ORIGIN}/signin")
    clear_session_cookie(resp)
    return resp

@router.get("/logout-miq")
async def auth_logout_miq(request: Request):
    """
    Logout endpoint for MIQ.
    """
    response = JSONResponse(content={"status": "success"})
    clear_session_cookie(response)
    return response

class UserInfo(TypedDict):
    email: str
    user_id: int
    miq_user_id: int | None
    name: str | None

class UserRoleResponse(TypedDict):
    user: UserInfo
    all_access: bool
    role: str


class UsernameLoginResponse(UserRoleResponse):
    token: str
    expires_hours: int


@router.get("/user_role", response_model=UserRoleResponse)
async def user_role(claims: Annotated[dict, Depends(require_auth)], session: Annotated[AsyncSession, Depends(get_session)]):
    logger.info("User role request received")
    
    # Extract email and MIQ data from JWT claims
    user: Optional[dict[str, Any]] = claims.get("user")
    permissions: Optional[list[dict[str, Any]]] = claims.get("permissions")
    status: Optional[str] = claims.get("status")
    groups: Optional[list[str]] = claims.get("groups")

    if not (user and permissions and status and groups):
        raise HTTPException(status_code=400, detail="Invalid JWT claims")
    
    # Extract MIQ data from claims
    miq_uid = user.get("miq_user_id")
    username = user.get("username")
    email = user.get("email")
    user_id = user.get("user_id")
    
    # Determine single role based on priority logic (case insensitive)
    groups = list(map(str.lower, groups))
    if "report generator app admin" in groups:
        user_role_value = "Report Generator App Admin"
    elif "report generator app editor" in groups:
        user_role_value = "Report Generator App Editor"
    elif "report generator app viewer" in groups:
        user_role_value = "Report Generator App Viewer"
    else:
        # Fallback if no roles found
        logger.warning(f"No recognized role found for user {email}, groups: {groups}")
        user_role_value = "Report Generator App Admin"
    
    # Determine admin access from MIQ user type
    all_access = user_role_value.lower() == "report generator app admin"

    return {
        "user": {
            "email": email,
            "user_id": user_id,
            "name": username,
            "miq_user_id": miq_uid,
        },
        "all_access": all_access,
        "role": user_role_value,
    }
# Optional helper to introspect tokens during development
@router.get("/me")
async def me(claims: Annotated[dict, Depends(require_auth)]):
    return {"claims": claims}
