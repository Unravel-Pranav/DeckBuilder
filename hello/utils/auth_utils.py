import asyncio
import time
from typing import Any, cast

import jwt
from fastapi.responses import Response
from fastapi.requests import Request
from fastapi.exceptions import HTTPException
from hello.services.config import settings
from traceback import print_exc
from hello.services.miq_service import (
    get_miq_user_info,
    get_miq_user_permissions,
    search_miq,
    MIQUserPermissions,
    MIQUserInfo,
    get_miq_jwt_validation_response
)
from hello import models
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from logging import getLogger
from sqlalchemy.exc import IntegrityError

logger = getLogger(__name__)

# Default permission hierarchy for division/market filtering
PERMISSION_HIERARCHY = ["division", "market"]


def now_epoch_seconds() -> int:
    return int(time.time())


def _now() -> int:
    # Backwards-compatible internal alias
    return now_epoch_seconds()


def _normalize_epoch_seconds(exp_claim: Any) -> int:
    """
    Normalize a JWT exp claim to epoch seconds.

    MIQ/AAD tokens should use epoch seconds, but some issuers may send epoch milliseconds.
    """
    try:
        exp_int = int(exp_claim)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid JWT exp")

    # Heuristic: epoch milliseconds are ~1.7e12; epoch seconds are ~1.7e9.
    if exp_int > 10_000_000_000:
        exp_int = exp_int // 1000
    return exp_int


def mint_app_jwt(
    *,
    email: str | None,
    azure_oid: str | None,
    aad_exp: int | None = None,
    extra_claims: dict | None = None,
) -> str:
    now = _now()
    if aad_exp:
        exp = aad_exp
    else:
        exp = now + settings.APP_JWT_EXPIRES_HOURS * 3600

    sub = azure_oid or (email or "unknown")
    payload = {
        "sub": sub,
        "email": email.lower() if email else None,
        "oid": azure_oid,
        "iat": now,
        "exp": exp,
        "iss": "fastapi-app",
        "aud": "fastapi-frontend",
    }

    # Merge in any extra claims (e.g., MIQ data)
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.APP_SIGNING_SECRET, algorithm="HS256")


def set_session_cookie(resp: Response, token: str) -> None:
    """Store the app JWT in an HttpOnly cookie (plus samesite=lax)."""
    max_age = settings.APP_JWT_EXPIRES_HOURS * 3600
    resp.set_cookie(
        settings.APP_SESSION_COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
        max_age=max_age,
    )


def clear_session_cookie(resp: Response) -> None:
    """Clear the app JWT cookie."""
    resp.delete_cookie(
        settings.APP_SESSION_COOKIE_NAME,
        path="/",
    )


def read_app_jwt_from_request(request: Request) -> str | None:
    """Accept token from Authorization: Bearer <token> OR from app cookie."""
    auth = (
        request.headers.get("Authorization")
        or request.cookies.get(settings.APP_SESSION_COOKIE_NAME)
        or ""
    )
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    cookie_val = request.cookies.get(settings.APP_SESSION_COOKIE_NAME)
    if cookie_val:
        return cookie_val
    return None


def decode_app_jwt(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.APP_SIGNING_SECRET,
            algorithms="HS256",
            verify=True,
            audience="fastapi-frontend",
            issuer="fastapi-app",
            options={"require": ["exp", "iss", "sub", "email"]},
        )
    except Exception as e:
        print_exc()
        raise HTTPException(status_code=401, detail=str(e))


def extract_email_from_claims(claims: dict[str, Any] | None) -> str | None:
    """
    Extract user email from JWT claims.

    Args:
        claims: Decoded JWT claims dictionary, can be None for unauthenticated requests

    Returns:
        User email string or None if not available
    """
    if not claims:
        return None
    user_claims = claims.get("user") or {}
    return user_claims.get("email") or claims.get("email")


async def require_auth(request: Request) -> dict:
    # Check if this endpoint should skip authentication
    request_path = request.url.path
    for public_pattern in settings.PUBLIC_ENDPOINTS:
        if request_path.endswith(public_pattern) or request_path == public_pattern:
            return {}

    # Proceed with normal authentication for protected endpoints
    token = read_app_jwt_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    return decode_app_jwt(token)


def extract_email_and_oid_from_idp_token(
    token: dict,
) -> tuple[str | None, str | None, int | None]:
    """
        Try to pull an email, stable object id (oid/sub), and expiry from Azure AD token response.
        We prefer userinfo, and fall back to id_token claims if needed.
        Returns: (email, oid, aad_exp)
        id_token = token.get("id_token")  # present in OIDC code flow
    claims = jwt.get_unverified_claims(id_token)  # from python-jose
    aad_exp = int(claims["exp"])  # epoch seconds

    # 2) (Optional) Bound your own max session so the app token never exceeds your policy
    now = int(time.time())
    max_app_exp = now + settings.APP_JWT_MAX_HOURS * 3600  # your internal cap, if any
    app_exp = min(aad_exp, max_app_exp)

    # 3) Mint the app JWT using the Azure AD expiry
    payload = {
        "sub": claims.get("oid") or claims.get("sub"),
        "email": claims.get("email") or claims.get("preferred_username"),
        "oid": claims.get("oid"),
        "iat": now,
        "exp": app_exp,
        "iss": "fastapi-app",
        "aud": "fastapi-frontend",
    }
    app_jwt = jwt.encode(payload, settings.APP_SIGNING_SECRET, algorithm="HS256")
    """

    userinfo = token.get("userinfo") or {}
    email = userinfo.get("email") or userinfo.get("preferred_username")
    oid = userinfo.get("oid") or userinfo.get("sub")
    aad_exp = userinfo.get("exp")

    if not (email and oid) and (id_token := token.get("id_token")):
        try:
            claims = jwt.decode(id_token, options={"verify_signature": False})
        except Exception:
            claims = {}
        email = email or claims.get("email") or claims.get("preferred_username")
        oid = oid or claims.get("oid") or claims.get("sub")
        aad_exp = aad_exp or claims.get("exp")

    return email, oid, aad_exp


async def get_user_info_from_miq(
    email: str | None = None,
    user_id: str | None = None,
) -> tuple[MIQUserInfo, list[MIQUserPermissions]]:
    """
    Get user info and permissions from MIQ.
    Args:
        email: Email of the user
        user_id: User ID of the user
        If both email and user_id are provided, email takes precedence. If neither are provided, an error is raised.
    Returns:
        Tuple of user info and permissions
    """
    if not email and not user_id:
        raise HTTPException(status_code=400, detail="Atleast one of email or user_id is required")
    user_id_str = ""
    if user_id:
        user_id_str = user_id
    elif email:
        search_results = await search_miq(search_term=email.lower())
        if not search_results:
            logger.error(f"User not found in MIQ: {email}")
            raise HTTPException(status_code=404, detail="User not found in MIQ")
        user_id_int = search_results[0].id
        user_id_str = str(user_id_int)

    user_info, user_permissions = await asyncio.gather(
        get_miq_user_info(user_id_str), get_miq_user_permissions(user_id_str)
    )
    if not user_info or not user_permissions:
        logger.error(
            f"User info or permissions not found in MIQ for user ID: {user_id_str}"
        )
        raise HTTPException(
            status_code=404, detail="User info or permissions not found in MIQ"
        )
    return user_info, user_permissions


async def get_user_by_email(session: AsyncSession, email: str) -> models.User | None:
    """Fetch user by email. Returns None if not found."""
    email = email.lower()
    res = await session.execute(select(models.User).where(models.User.email == email))
    return res.scalars().first()


async def create_user_from_miq(
    session: AsyncSession,
    user_info: MIQUserInfo,
) -> models.User:
    """
    Create a new user from MIQ data.
    If concurrent creation occurs, fetches the existing user instead of failing.
    """

    email_normalized = user_info.emailAddress.lower()
    username = (
        user_info.username
        if user_info.username
        else f"{user_info.lastName}, {user_info.firstName}".strip()
    )

    new_user = models.User(
        email=email_normalized, username=username, miq_user_id=user_info.id
    )
    session.add(new_user)

    try:
        await session.commit()
        await session.refresh(new_user)
        logger.info(f"Created new user: {email_normalized} (MIQ ID: {user_info.id})")
        return new_user
    except IntegrityError:
        # Concurrent request already created this user - fetch and return it
        await session.rollback()
        user = await get_user_by_email(session, email_normalized)
        if user:
            return user
        raise HTTPException(status_code=500, detail="Failed to create user")


async def get_or_create_user_from_miq(
    session: AsyncSession,
    *,
    email: str,
    user_info: MIQUserInfo,
) -> models.User:
    """
    Fetch user by email; if missing, create from MIQ user_info.
    Keeping `email` as an explicit param preserves caller semantics (IdP email vs MIQ email).
    """
    user = await get_user_by_email(session, email)
    if user:
        return user
    return await create_user_from_miq(session, user_info)


def build_miq_claims(
    *,
    user: models.User,
    user_info: MIQUserInfo,
    user_permissions: list[MIQUserPermissions],
) -> dict[str, Any]:
    """
    Build MIQ-enriched claims stored inside our app JWT.
    This is shared by both MIQ SSO login and Azure callback flows.
    """
    username = user.username or f"{user_info.lastName}, {user_info.firstName}".strip()
    return {
        "user": {
            "miq_user_id": user_info.id,
            "username": username,
            "email": user.email,
            "user_id": user.id,
        },
        "status": user_info.statusVal,
        "groups": [group.value for group in user_info.groups],
        "permissions": [
            {"division": perm.divisionVal, "market": perm.marketVal}
            for perm in user_permissions
        ],
    }


async def get_user_from_claims(
    session: AsyncSession, claims: dict | None
) -> models.User | None:
    """
    Resolve the current user from JWT claims. Users must already exist in the DB;
    this helper only fetches them and will not create new rows.
    """
    if not claims:
        return None

    user_claims = claims.get("user") or {}
    claimed_user_id = user_claims.get("user_id")
    claimed_email = user_claims.get("email") or claims.get("email")
    if claimed_user_id:
        user = await session.get(models.User, claimed_user_id)
        if user:
            return user
        raise HTTPException(
            status_code=401, detail="User not found for provided claims"
        )

    if claimed_email:
        email_normalized = claimed_email.lower()
        user = await get_user_by_email(session, email_normalized)
        if user:
            return user
        raise HTTPException(
            status_code=401, detail="User not found for provided claims"
        )

    raise HTTPException(status_code=401, detail="Invalid user claims")


# =============================================================================
# Permission Utilities
# =============================================================================


def get_user_permissions_from_claims(claims: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract user permissions from JWT claims.

    Args:
        claims: Decoded JWT claims dictionary

    Returns:
        List of permission dicts with keys like 'division', 'market', etc.

    Raises:
        HTTPException: If no permissions found in claims
    """
    permissions: list[dict[str, Any]] | None = claims.get("permissions")
    if not permissions:
        raise HTTPException(
            status_code=401, detail="Unauthorized - no permissions in claims"
        )
    return permissions


def build_permission_tree(
    permissions: list[dict[str, Any]], hierarchy: list[str] | None = None
) -> dict[str, Any]:
    """
    Build a nested permission tree from flat permission list.

    Args:
        permissions: List of permission dicts with keys like 'division', 'market', etc.
        hierarchy: Ordered list of permission levels. Defaults to ['division', 'market']

    Returns:
        Nested dict where keys are permission values and special keys track "all" access:
        - '_all_<level>': True indicates "all" access at that level
        - '_values_<level>': Set of specific values when parent has "all" access
        - '_has_all_children': True indicates all children allowed for this node

    Example:
        Input: [{'division': 'Office', 'market': 'Denver'}, {'division': 'Industrial', 'market': 'All'}]
        Output: {
            'office': {'denver': {}},
            'industrial': {'_has_all_children': True}
        }
    """
    if hierarchy is None:
        hierarchy = PERMISSION_HIERARCHY

    tree: dict[str, Any] = {}

    for perm in permissions:
        # Track "all" access at each level and specific values at each level
        all_flags: dict[str, bool] = {}
        values_at_level: dict[str, str] = {}

        for level in hierarchy:
            value = perm.get(level, "").strip().lower()

            if not value:
                break

            # Check if this level has "all" access
            if value == "all":
                all_flags[f"_all_{level}"] = True
            else:
                values_at_level[level] = value

        # Handle "all" at first level
        if all_flags.get(f"_all_{hierarchy[0]}"):
            tree[f"_all_{hierarchy[0]}"] = True

            # Check subsequent levels
            for i in range(1, len(hierarchy)):
                level = hierarchy[i]
                if all_flags.get(f"_all_{level}"):
                    tree[f"_all_{level}"] = True
                elif level in values_at_level:
                    # Store child values when parent is "all"
                    # Use special key to track specific values for this level
                    level_values_key = f"_values_{level}"
                    if level_values_key not in tree:
                        tree[level_values_key] = set()
                    tree[level_values_key].add(values_at_level[level])
        else:
            # Build nested structure for specific values
            current_node = tree

            for level in hierarchy:
                value = perm.get(level, "").strip().lower()

                if not value or value == "all":
                    if value == "all":
                        # Mark this node as having all children
                        current_node["_has_all_children"] = True
                    break

                # Create node if doesn't exist
                if value not in current_node:
                    current_node[value] = {}

                # Move to child node
                current_node = current_node[value]

    return tree


def _market_matches_permission(
    report_market: str, allowed_markets: set[str] | dict[str, Any]
) -> bool:
    """
    Check if a report market matches any of the allowed permission markets.

    Uses case-insensitive substring matching: the permission market should be
    a substring of the report market. For example, permission "tampa" matches
    report market "tampa industrial".

    Args:
        report_market: The market name from the report (already lowercased)
        allowed_markets: Set of allowed market names or dict with market keys (already lowercased)

    Returns:
        True if the report market matches any allowed permission market
    """
    # Get the market keys to check against
    if isinstance(allowed_markets, dict):
        market_keys = [k for k in allowed_markets.keys() if not k.startswith("_")]
    else:
        market_keys = list(allowed_markets)

    # Check if any permission market is a substring of the report market
    for perm_market in market_keys:
        if perm_market in report_market:
            return True
    return False


def filter_divisions_by_permissions(
    divisions: list[str],
    permission_tree: dict[str, Any],
) -> list[str]:
    """
    Filter a list of divisions based on user permission tree.

    Args:
        divisions: List of division names from Snowflake
        permission_tree: Nested permission tree from build_permission_tree

    Returns:
        Filtered list of divisions the user has access to
    """
    # If user has access to all divisions, return the full list
    if permission_tree.get("_all_division"):
        return divisions

    # Empty permission tree means no access
    if not permission_tree:
        return []

    # Get allowed division keys (exclude special _ prefixed keys)
    allowed_divisions = {
        key.lower() for key in permission_tree.keys() if not key.startswith("_")
    }

    # Filter divisions using case-insensitive substring matching
    # Permission "office" should match division "Office" or "Office Markets"
    filtered = []
    for division in divisions:
        div_lower = division.strip().lower()
        for allowed in allowed_divisions:
            if allowed in div_lower or div_lower in allowed:
                filtered.append(division)
                break

    return filtered


def filter_markets_by_permissions(
    markets: list[str],
    permission_tree: dict[str, Any],
    division: str | None = None,
) -> list[str]:
    """
    Filter a list of markets based on user permission tree.

    Args:
        markets: List of market names from Snowflake
        permission_tree: Nested permission tree from build_permission_tree
        division: Optional division to scope market filtering

    Returns:
        Filtered list of markets the user has access to
    """
    # Empty permission tree means no access
    if not permission_tree:
        return []

    # Case 1: User has access to all divisions AND all markets
    if permission_tree.get("_all_division") and permission_tree.get("_all_market"):
        return markets

    # Case 2: User has all divisions but specific markets (_values_market)
    if permission_tree.get("_all_division"):
        allowed_markets = permission_tree.get("_values_market")
        if allowed_markets is None:
            # _all_division without _all_market or _values_market - no market restrictions
            # This shouldn't happen in practice, but return all to be safe
            return markets
        return _filter_markets_by_allowed(markets, allowed_markets)

    # Case 3: Specific divisions with their market permissions
    # Collect all allowed markets from all divisions (or specific division if provided)
    all_allowed_markets: set[str] = set()
    has_any_all_children = False

    div_lower = division.strip().lower() if division else None

    for div_key, div_node in permission_tree.items():
        if div_key.startswith("_"):
            continue

        # If division is specified, only consider that division's permissions
        if (
            div_lower
            and div_key != div_lower
            and div_lower not in div_key
            and div_key not in div_lower
        ):
            continue

        if isinstance(div_node, dict):
            # Check if division has ALL markets access
            if div_node.get("_has_all_children"):
                has_any_all_children = True
                if div_lower:
                    # If filtering for specific division with all children, return all
                    break
            else:
                # Collect specific market keys for this division
                for mkt_key in div_node.keys():
                    if not mkt_key.startswith("_"):
                        all_allowed_markets.add(mkt_key)

    # If any matched division has all children access, return all markets
    if has_any_all_children:
        return markets

    return _filter_markets_by_allowed(markets, all_allowed_markets)


def _filter_markets_by_allowed(
    markets: list[str], allowed_markets: set[str]
) -> list[str]:
    """
    Helper to filter markets list by a set of allowed market patterns.
    Uses case-insensitive substring matching.
    """
    if not allowed_markets:
        return []

    filtered = []
    for market in markets:
        mkt_lower = market.strip().lower()
        for allowed in allowed_markets:
            # Substring matching in either direction
            if allowed in mkt_lower or mkt_lower in allowed:
                filtered.append(market)
                break

    return filtered


def user_can_access_report(
    report_divisions: list[str] | None,
    report_markets: list[str] | None,
    permission_tree: dict[str, Any],
) -> bool:
    """
    Check if a user can access a report based on their permission tree.

    A user can access a report only if they have permission for ALL divisions
    AND ALL markets in the report.

    Uses case-insensitive substring matching for markets: a permission like
    "tampa" will match a report market like "tampa industrial".

    Args:
        report_divisions: List of divisions the report belongs to
        report_markets: List of markets the report belongs to
        permission_tree: Permission tree built from user's claims

    Returns:
        True if user has access to all divisions and markets in the report

    Permission tree structure examples:
        - {"_all_division": True, "_all_market": True} - Full access
        - {"_all_division": True, "_values_market": {"denver", "tampa"}} - All divisions, specific markets
        - {"office": {"_has_all_children": True}} - Office division with all its markets
        - {"office": {"denver": {}}} - Office division, only Denver market
    """
    # Normalize inputs
    divisions = [d.strip().lower() for d in (report_divisions or []) if d and d.strip()]
    markets = [m.strip().lower() for m in (report_markets or []) if m and m.strip()]

    # Empty permission tree means no access
    if not permission_tree:
        return False

    # Case 1: Full access (ALL divisions AND ALL markets)
    if permission_tree.get("_all_division") and permission_tree.get("_all_market"):
        return True

    # Case 2: ALL divisions, but specific markets
    if permission_tree.get("_all_division"):
        # Check if we have specific market restrictions
        allowed_markets = permission_tree.get("_values_market")
        if allowed_markets is None:
            # _all_division without _all_market or _values_market means no market access
            return len(markets) == 0
        # User must have access to ALL report markets (using substring matching)
        return all(_market_matches_permission(m, allowed_markets) for m in markets)

    # Case 3: Specific divisions (may have ALL markets or specific markets per division)
    # If report has no divisions, check if user has any division access
    if not divisions:
        # Report has no divisions - allow if user has any permissions
        # Check markets against all divisions the user has access to
        if not markets:
            return True

        # Collect all allowed markets from all user's divisions
        all_allowed_markets: set[str] = set()
        has_any_all_children = False

        for div_key, div_node in permission_tree.items():
            if div_key.startswith("_"):
                continue
            if isinstance(div_node, dict):
                if div_node.get("_has_all_children"):
                    has_any_all_children = True
                    break
                for mkt_key in div_node.keys():
                    if not mkt_key.startswith("_"):
                        all_allowed_markets.add(mkt_key)

        if has_any_all_children:
            return True
        return all(_market_matches_permission(m, all_allowed_markets) for m in markets)

    # Check each division and its markets
    for div in divisions:
        if div not in permission_tree:
            return False  # User doesn't have access to this division

        div_node = permission_tree[div]

        if not isinstance(div_node, dict):
            # Unexpected structure, deny access
            return False

        # Check if division has ALL markets access
        if div_node.get("_has_all_children"):
            continue  # All markets allowed for this division

        # Check each market is allowed under this division (using substring matching)
        for mkt in markets:
            if not _market_matches_permission(mkt, div_node):
                return False

    return True

async def decode_miq_jwt(miq_jwt: str) -> dict[str, Any]:
    try:
        decoded = jwt.decode(miq_jwt, options={"verify_signature": False})
        if not isinstance(decoded, dict):
            raise HTTPException(status_code=401, detail="Invalid JWT")
        return cast(dict[str, Any], decoded)
    except Exception as e:
        logger.error(f"Error decoding MIQ JWT: {e}")
        raise HTTPException(status_code=401, detail="Invalid JWT")

async def validate_and_get_miq_user_id(miq_jwt: str) -> str:
    user_id, _exp = await validate_and_get_miq_user_id_and_exp(miq_jwt)
    return user_id


async def validate_and_get_miq_user_id_and_exp(miq_jwt: str) -> tuple[str, int]:
    """
    Validate the MIQ JWT with MIQ, then extract `userID` and `exp`.

    We require `exp` for MIQ SSO so the app session can match MIQ token lifetime.
    """
    validation_response = await get_miq_jwt_validation_response(miq_jwt)
    if not validation_response:
        raise HTTPException(status_code=401, detail="Invalid JWT")

    claims = await decode_miq_jwt(miq_jwt)

    user_id = claims.get("userID")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid JWT")

    if "exp" not in claims:
        raise HTTPException(status_code=401, detail="MIQ JWT missing exp")
    exp = _normalize_epoch_seconds(claims.get("exp"))

    now = now_epoch_seconds()
    if exp <= now:
        raise HTTPException(status_code=401, detail="MIQ JWT expired")

    return str(user_id), exp
