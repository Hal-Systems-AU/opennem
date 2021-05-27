"""
OpenNEM API authentication schemas

"""

from datetime import datetime
from typing import Optional

from opennem.schema.core import BaseConfig
from opennem.schema.opennem import OpennemBaseDataSchema
from opennem.schema.types import UrlsafeString


class AuthApiKeyRecord(BaseConfig):
    """Schema for an API Key database entry or definition"""

    keyid: UrlsafeString
    description: Optional[str]
    revoked: bool = True
    created_at: datetime


class AuthApiKeyInfoResponse(OpennemBaseDataSchema):
    """Info response from API showing key details"""

    record: AuthApiKeyRecord
