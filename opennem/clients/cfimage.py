import logging
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel
from requests.exceptions import RequestException

from opennem import settings
from opennem.utils.http import API_CLIENT_HEADERS, http

logger = logging.getLogger("opennem.clients.cfimage")

CF_URL = "https://api.cloudflare.com/client/v4/accounts/{account_id}/images/v1"


class CloudflareImageException(Exception):
    pass


class CloudflareImageResponse(BaseModel):
    filename: str
    uploaded: datetime
    variants: list[str]


def save_image_to_cloudflare(image: bytes) -> CloudflareImageResponse:
    if not settings.cloudflare_api_key or not settings.cloudflare_account_id:
        raise CloudflareImageException("API not configured with account id and key")

    headers = API_CLIENT_HEADERS

    headers["Authorization"] = f"Bearer {settings.cloudflare_api_key}"

    cfimage_url = CF_URL.format(account_id=settings.cloudflare_account_id)

    file_upload = {"file": BytesIO(image)}

    json_response: Optional[Dict[str, Any]] = None

    try:
        response = http.post(cfimage_url, headers=headers, files=file_upload)

        if not response.ok:
            logger.debug(response.text)
            raise CloudflareImageException(f"Response error: {response.status_code}")

        try:
            json_response = response.json()
        except ValueError:
            raise CloudflareImageException("Bad response json")

    except RequestException as e:
        raise CloudflareImageException(f"Request error: {e}")

    if not json_response:
        raise CloudflareImageException("No json response")

    if "errors" in json_response and json_response["errors"]:
        err_msg = "\n".join(json_response["errors"])
        raise CloudflareImageException(f"Response errors: {err_msg}")

    if "success" not in json_response:
        raise CloudflareImageException("Bad response no success")

    if not json_response["success"]:
        raise CloudflareImageException("Bad response no success")

    model = CloudflareImageResponse(**json_response["result"])

    return model


if __name__ == "__main__":
    path = Path("data/screenshot_croppedVNOWWDGH.png")

    with path.open("br") as fh:
        image_content = fh.read()

    r = save_image_to_cloudflare(image_content)
    logger.info(r.variants)