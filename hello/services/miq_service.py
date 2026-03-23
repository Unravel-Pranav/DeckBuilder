import os
import httpx
from httpx import AsyncClient, HTTPStatusError
from logging import getLogger
from dataclasses import dataclass
from datetime import datetime
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from hello.services.config import settings

ENV = settings.TESTING_ENV

logger = getLogger(__name__)


class MIQClientManager:
    """Singleton manager for MIQ HTTP client with proper connection pooling."""
    
    _instance = None
    _miq_client: AsyncClient | None = None
    _miq_api_client: AsyncClient | None = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def get_client(self) -> AsyncClient:
        """Get or create the shared HTTP client."""
        if self._miq_client is None:
            if os.getenv('ENV') == 'prod' or os.getenv('ENV') == 'dev' or os.getenv('ENV') == 'test':
                self._miq_client = AsyncClient(
                    base_url=settings.MIQ_BASE,
                    headers={
                        "Authorization": f"Bearer {settings.MIQ_RBAC_TOKEN}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
                )
            elif os.getenv('ENV') == 'qa':
                self._miq_client = AsyncClient(
                    base_url=settings.MIQ_BASE_QA,
                    headers={
                        "Authorization": f"Bearer {settings.MIQ_RBAC_TOKEN_QA}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
                )

        return self._miq_client

    async def get_api_client(self) -> AsyncClient:
        """Get or create the shared MIQ API client."""
        if self._miq_api_client is None:
            if os.getenv('ENV') == 'prod' or os.getenv('ENV') == 'dev' or os.getenv('ENV') == 'test':
                self._miq_api_client = AsyncClient(
                    base_url="https://api.marketiq.cbre.com",
                    headers={
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
                )
            elif os.getenv('ENV') == 'qa':
                self._miq_api_client = AsyncClient(
                    base_url="https://qa.api.marketiq.cbre.com",
                    headers={
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
                )
        return self._miq_api_client
    
    async def close(self):
        """Close the HTTP client and cleanup resources."""
        if self._miq_client is not None:
            await self._miq_client.aclose()
            self._miq_client = None
        if self._miq_api_client is not None:
            await self._miq_api_client.aclose()
            self._miq_api_client = None


# Global instance
_miq_client_manager = MIQClientManager()


@asynccontextmanager
async def get_miq_client() -> AsyncGenerator[AsyncClient, None]:
    """Context manager that provides the shared MIQ HTTP client."""
    client = await _miq_client_manager.get_client()
    try:
        yield client
    except Exception:
        raise

@asynccontextmanager
async def get_miq_api_client() -> AsyncGenerator[AsyncClient, None]:
    """Context manager that provides the shared MIQ API client."""
    client = await _miq_client_manager.get_api_client()
    try:
        yield client
    except Exception:
        raise

async def close_miq_client():
    """Close the MIQ client. Should be called on application shutdown."""
    await _miq_client_manager.close()


@dataclass
class MIQSearchResponse:
    id: int
    username: str
    firstName: str
    lastName: str
    emailAddress: str
    statusId: int
    userTypeId: int
    roleId: int
    emailNotificationFlag: int
    globalRegionVal: str
    countryVal: str
    regionVal: str
    marketVal: str
    propertyUsageTypeVal: str
    subMarketVal: str
    districtVal: str
    locationAccessStatus: int
    accessRequestStatusVal: str
    confidentialityTypeVal: str
    accessRequestReason: str
    recordLevelAccessStatus: int
    locationReqPending: bool
    recordReqPending: bool


async def search_miq(search_term: str) -> list[MIQSearchResponse]:
    miq_responses: list[MIQSearchResponse] = []
    if ENV == "CBRE":
        async with get_miq_client() as client:
            try:
                response = await client.get(
                    f"/api/users/search", params={"query": search_term}
                )
                response.raise_for_status()
            except Exception as e:
                logger.error(f"Error searching MIQ: {e}")
                return []

            payload = response.json()
            logger.info(f"MIQ search response: {payload}")

            if not payload or not isinstance(payload, list):
                logger.warning(f"Unexpected MIQ response format: {type(payload)}")
                return []

            for item in payload:
                try:
                    miq_response = MIQSearchResponse(
                        id=item.get("id"),
                        username=item.get("username"),
                        firstName=item.get("firstName"),
                        lastName=item.get("lastName"),
                        emailAddress=item.get("emailAddress"),
                        statusId=item.get("statusId"),
                        userTypeId=item.get("userTypeId"),
                        roleId=item.get("roleId"),
                        emailNotificationFlag=item.get("emailNotificationFlag"),
                        globalRegionVal=item.get("globalRegionVal"),
                        countryVal=item.get("countryVal"),
                        regionVal=item.get("regionVal"),
                        marketVal=item.get("marketVal"),
                        propertyUsageTypeVal=item.get("propertyUsageTypeVal"),
                        subMarketVal=item.get("subMarketVal"),
                        districtVal=item.get("districtVal"),
                        locationAccessStatus=item.get("locationAccessStatus"),
                        accessRequestStatusVal=item.get("accessRequestStatusVal"),
                        confidentialityTypeVal=item.get("confidentialityTypeVal"),
                        accessRequestReason=item.get("accessRequestReason"),
                        recordLevelAccessStatus=item.get("recordLevelAccessStatus"),
                        locationReqPending=item.get("locationReqPending"),
                        recordReqPending=item.get("recordReqPending"),
                    )
                    miq_responses.append(miq_response)
                except Exception as e:
                    logger.error(
                        f"Error converting item to MIQSearchResponse: {e}, item: {item}"
                    )
                    continue
    else:
        miq_responses.append(
            MIQSearchResponse(
                id=12345,
                username="admin",
                firstName="Admin",
                lastName="User",
                emailAddress="admin@cbre.com",
                statusId=1,
                userTypeId=1,
                roleId=8,
                emailNotificationFlag=0,
                globalRegionVal="Americas",
                countryVal="",
                regionVal="",
                marketVal="",
                propertyUsageTypeVal="",
                subMarketVal="",
                districtVal="",
                locationAccessStatus=1,
                accessRequestStatusVal="Approved",
                confidentialityTypeVal="Level 0",
                accessRequestReason="Reason",
                recordLevelAccessStatus=0,
                locationReqPending=False,
                recordReqPending=False,
            )
        )
    return miq_responses


@dataclass
class MIQUserGroup:
    key: int
    value: str


@dataclass
class MIQUserInfo:
    id: int
    username: str
    firstName: str
    lastName: str
    emailAddress: str
    statusId: int
    statusVal: str
    userTypeId: int
    userTypeVal: str
    roleId: int
    roleVal: str
    locationReqPending: bool
    recordReqPending: bool
    createTs: datetime
    updateTs: datetime
    groups: list[MIQUserGroup]
    userCountrySkey: int
    userCountry: str
    userLobSkey: int
    userLob: str
    timezone: int
    globalRegion: str


async def get_miq_user_info(user_id: str) -> MIQUserInfo | None:
    if ENV == "CBRE":
        async with get_miq_client() as client:
            try:
                response = await client.get(f"/api/users/{user_id}")
                response.raise_for_status()
            except Exception as e:
                logger.error(f"Error fetching MIQ user info for {user_id}: {e}")
                return None

            item = response.json()
            logger.info(f"MIQ user info response: {item}")

            try:
                groups = [
                    MIQUserGroup(key=group["key"], value=group["value"])
                    for group in item.get("groups", [])
                ]

                miq_user_info = MIQUserInfo(
                    id=item.get("id"),
                    username=item.get("username"),
                    firstName=item.get("firstName"),
                    lastName=item.get("lastName"),
                    emailAddress=item.get("emailAddress"),
                    statusId=item.get("statusId"),
                    statusVal=item.get("statusVal"),
                    userTypeId=item.get("userTypeId"),
                    userTypeVal=item.get("userTypeVal"),
                    roleId=item.get("roleId"),
                    roleVal=item.get("roleVal"),
                    locationReqPending=item.get("locationReqPending"),
                    recordReqPending=item.get("recordReqPending"),
                    createTs=datetime.fromisoformat(item.get("createTs")),
                    updateTs=datetime.fromisoformat(item.get("updateTs")),
                    groups=groups,
                    userCountrySkey=item.get("userCountrySkey"),
                    userCountry=item.get("userCountry"),
                    userLobSkey=item.get("userLobSkey"),
                    userLob=item.get("userLob"),
                    timezone=item.get("timezone"),
                    globalRegion=item.get("globalRegion"),
                )
                return miq_user_info
            except Exception as e:
                logger.error(f"Error converting item to MIQUserInfo: {e}, item: {item}")
                return None
    else:
        return MIQUserInfo(
            id=12345,
            username="admin",
            firstName="Admin",
            lastName="User",
            emailAddress="admin@cbre.com",
            statusId=1,
            statusVal="Active",
            userTypeId=1,
            userTypeVal="Admin",
            roleId=8,
            roleVal="D\u0026T",
            locationReqPending=False,
            recordReqPending=False,
            createTs=datetime.now(),
            updateTs=datetime.now(),
            groups=[
                MIQUserGroup(key=4, value="Trusted User"),
                MIQUserGroup(key=6, value="Bulk Export"),
                MIQUserGroup(key=7, value="Report Generator App Admin"),
            ],
            userCountrySkey=10000234,
            userCountry="USA",
            userLobSkey=1,
            userLob="US General",
            timezone=0,
            globalRegion="",
        )


@dataclass
class MIQUserPermissions:
    id: int
    userId: int
    globalRegionId: int
    globalRegionName: str
    globalRegionVal: str
    countryId: int
    countryName: str
    countryVal: str
    divisionId: int
    divisionName: str
    divisionVal: str
    marketId: int
    marketName: str
    marketVal: str
    propertyUsageTypeId: int
    propertyUsageTypeName: str
    propertyUsageTypeVal: str
    subMarketId: int
    subMarketName: str
    subMarketVal: str
    districtId: int
    districtName: str
    districtVal: str
    neighborhoodId: int
    neighborhoodName: str
    neighborhoodVal: str
    accessRequestStatusId: int
    accessRequestStatusVal: str
    confidentialityTypeId: int
    confidentialityTypeVal: str
    businessJustification: str


async def get_miq_user_permissions(user_id: str) -> list[MIQUserPermissions]:
    if ENV == "CBRE":
        async with get_miq_client() as client:
            try:
                response = await client.get(f"/api/users/{user_id}/perms/location")
                response.raise_for_status()
            except Exception as e:
                logger.error(f"Error fetching MIQ user permissions for {user_id}: {e}")
                return []

            items = response.json()
            logger.info(f"MIQ user permissions response: {items}")
            try:
                miq_user_permissions = [
                    MIQUserPermissions(
                        id=item.get("id"),
                        userId=item.get("userId"),
                        globalRegionId=item.get("globalRegionId"),
                        globalRegionName=item.get("globalRegionName"),
                        globalRegionVal=item.get("globalRegionVal"),
                        countryId=item.get("countryId"),
                        countryName=item.get("countryName"),
                        countryVal=item.get("countryVal"),
                        divisionId=item.get("divisionId"),
                        divisionName=item.get("divisionName"),
                        divisionVal=item.get("divisionVal"),
                        marketId=item.get("marketId"),
                        marketName=item.get("marketName"),
                        marketVal=item.get("marketVal"),
                        propertyUsageTypeId=item.get("propertyUsageTypeId"),
                        propertyUsageTypeName=item.get("propertyUsageTypeName"),
                        propertyUsageTypeVal=item.get("propertyUsageTypeVal"),
                        subMarketId=item.get("subMarketId"),
                        subMarketName=item.get("subMarketName"),
                        subMarketVal=item.get("subMarketVal"),
                        districtId=item.get("districtId"),
                        districtName=item.get("districtName"),
                        districtVal=item.get("districtVal"),
                        neighborhoodId=item.get("neighborhoodId"),
                        neighborhoodName=item.get("neighborhoodName"),
                        neighborhoodVal=item.get("neighborhoodVal"),
                        accessRequestStatusId=item.get("accessRequestStatusId"),
                        accessRequestStatusVal=item.get("accessRequestStatusVal"),
                        confidentialityTypeId=item.get("confidentialityTypeId"),
                        confidentialityTypeVal=item.get("confidentialityTypeVal"),
                        businessJustification=item.get("businessJustification"),
                    )
                    for item in items
                ]
                return miq_user_permissions
            except Exception as e:
                logger.error(
                    f"Error converting items to MIQUserPermissions: {e}, items: {items}"
                )
                return []
    else:
        return [
            MIQUserPermissions(
                id=12345,
                userId=12345,
                globalRegionId=1,
                globalRegionName="Americas",
                globalRegionVal="Americas",
                countryId=0,
                countryName="All",
                countryVal="All",
                divisionId=0,
                divisionName="All",
                divisionVal="All",
                marketId=0,
                marketName="All",
                marketVal="All",
                propertyUsageTypeId=0,
                propertyUsageTypeName="All",
                propertyUsageTypeVal="All",
                subMarketId=0,
                subMarketName="All",
                subMarketVal="All",
                districtId=0,
                districtName="All",
                districtVal="All",
                neighborhoodId=0,
                neighborhoodName="All",
                neighborhoodVal="All",
                accessRequestStatusId=1,
                accessRequestStatusVal="Approved",
                confidentialityTypeId=1,
                confidentialityTypeVal="Level 0",
                businessJustification="Reason"
            )
        ]

async def get_miq_jwt_validation_response(miq_jwt: str) -> bool:
    if ENV == "CBRE":
        async with get_miq_api_client() as client:
            try:
                response = await client.get("/authorize", headers={"Authorization": f"Bearer {miq_jwt}"})
                response.raise_for_status()
            except HTTPStatusError as e:
                logger.error(f"Error validating MIQ JWT: {e}, status code: {response.status_code}")
                return False
            return True
    else:
        return True
