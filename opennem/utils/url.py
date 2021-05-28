import urllib
from typing import Optional

# urljoin from here so that the netlocs can be loaded
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse  # noqa: F401

# Support S3 URI's in urllib
urllib.parse.uses_netloc.append("s3")
urllib.parse.uses_relative.append("s3")


def bucket_to_website(bucket_path: str, to_scheme: str = "https") -> str:
    """
    Converts a bucket path to a website path

    ex. "s3://data.test.org" -> "https://data.test.org"
    """
    bucket_path_parsed = urlparse(bucket_path)
    bucket_path_parsed = bucket_path_parsed._replace(scheme=to_scheme)
    return bucket_path_parsed.geturl()


def strip_query_string(url: str, param: Optional[str] = None) -> str:
    """strip the query string from an URL

    Args:
        url (str): URL to strip
        param (Optional[str], optional): Only strip query string parameter with name. Defaults to None.

    Returns:
        str: clean URL
    """
    _parsed = urlparse(url)

    # strip out qs
    # @TODO support popping a particular key
    _parsed = _parsed._replace(query="")

    _url_clean = urlunparse(_parsed)

    return _url_clean
