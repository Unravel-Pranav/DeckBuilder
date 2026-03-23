from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from hello.schemas import OptionListResponse
from hello.services import sidebar_options_service as service
from hello.utils.auth_utils import (
    require_auth,
    get_user_permissions_from_claims,
    build_permission_tree,
    filter_divisions_by_permissions,
    filter_markets_by_permissions,
)


router = APIRouter(dependencies=[Depends(require_auth)])


def _wrap_items(items: list[str]) -> OptionListResponse:
    return OptionListResponse(items=items)


@router.get("/divisions", response_model=OptionListResponse)
async def get_divisions(
    claims: dict = Depends(require_auth),
) -> OptionListResponse:
    """Fetch distinct divisions from Snowflake, filtered by user permissions."""
    try:
        all_divisions = service.fetch_divisions()
        permissions = get_user_permissions_from_claims(claims)
        permission_tree = build_permission_tree(permissions)
        filtered = filter_divisions_by_permissions(all_divisions, permission_tree)
        return _wrap_items(filtered)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=500, detail="Failed to fetch divisions"
        ) from exc


@router.get("/publishing-groups", response_model=OptionListResponse)
async def get_publishing_groups(
    division: str = Query(..., min_length=1, description="Division name"),
) -> OptionListResponse:
    """Fetch publishing groups for a division."""
    try:
        return _wrap_items(service.fetch_publishing_groups(division))
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=500, detail="Failed to fetch publishing groups"
        ) from exc


@router.get("/property-types", response_model=OptionListResponse)
async def get_property_types(
    division: str = Query(..., min_length=1, description="Division name"),
    publishing_group: str = Query(..., min_length=1, description="Publishing group"),
) -> OptionListResponse:
    """Fetch property types filtered by division and publishing group."""
    try:
        items = service.fetch_property_types(
            division=division, publishing_group=publishing_group
        )
        filtered = [
            item
            for item in items
            if str(item).strip().lower() in {"industrial", "office"}
        ]
        # # If nothing matched (e.g., DB returned unexpected values), fall back to both
        # if not filtered:
        #     filtered = ["Industrial", "Office"]
        return _wrap_items(filtered)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=500, detail="Failed to fetch property types"
        ) from exc


@router.get("/markets", response_model=OptionListResponse)
async def get_markets(
    division: str = Query(..., min_length=1, description="Division name"),
    publishing_group: str = Query(..., min_length=1, description="Publishing group"),
    property_type: str = Query(..., min_length=1, description="Property type"),
    claims: dict = Depends(require_auth),
) -> OptionListResponse:
    """Fetch markets filtered by division, publishing group, property type, and user permissions."""
    try:
        all_markets = service.fetch_markets(
            division=division,
            publishing_group=publishing_group,
            property_type=property_type,
        )
        permissions = get_user_permissions_from_claims(claims)
        permission_tree = build_permission_tree(permissions)
        filtered = filter_markets_by_permissions(
            all_markets, permission_tree, division=division
        )
        return _wrap_items(filtered)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="Failed to fetch markets") from exc


@router.get("/quarters", response_model=OptionListResponse)
async def get_quarters(
    defined_market_name: str = Query(..., min_length=1, description="Defined market"),
    publishing_group: str = Query(..., min_length=1, description="Publishing group"),
    limit: int = Query(3, ge=1, le=12, description="Max quarters to return"),
) -> OptionListResponse:
    """Fetch latest quarters for a market + publishing group."""
    try:
        return _wrap_items(
            service.fetch_quarters(
                defined_market_name=defined_market_name,
                publishing_group=publishing_group,
                limit=limit,
            )
        )
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="Failed to fetch quarters") from exc


@router.get("/vacancy-index", response_model=OptionListResponse)
async def get_vacancy_index(
    defined_market_name: str = Query(..., min_length=1, description="Defined market"),
) -> OptionListResponse:
    """Fetch vacancy index options for a market."""
    try:
        return _wrap_items(service.fetch_vacancy_indices(defined_market_name))
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=500, detail="Failed to fetch vacancy index options"
        ) from exc


@router.get("/submarkets", response_model=OptionListResponse)
async def get_submarkets(
    defined_market_name: str = Query(..., min_length=1, description="Defined market"),
) -> OptionListResponse:
    """Fetch distinct submarkets for a market."""
    try:
        return _wrap_items(service.fetch_submarkets_new(defined_market_name))
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=500, detail="Failed to fetch submarkets"
        ) from exc


@router.get("/districts", response_model=OptionListResponse)
async def get_districts(
    defined_market_name: str = Query(..., min_length=1, description="Defined market"),
) -> OptionListResponse:
    """Fetch distinct districts for a market."""
    try:
        return _wrap_items(service.fetch_districts_new(defined_market_name))
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=500, detail="Failed to fetch districts"
        ) from exc
