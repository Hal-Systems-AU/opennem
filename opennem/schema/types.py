"""
OpenNEM Custom Schema Types


"""

from typing import Any, Callable, Dict, Generator, Union

from pydantic.networks import AnyUrl
from pydantic.utils import update_not_none
from pydantic.validators import str_validator

from opennem.core.normalizers import validate_twitter_handle
from opennem.core.validators.strings import urlsafe_str_validator

AnyCallable = Callable[..., Any]

CallableGenerator = Generator[AnyCallable, None, None]

__all__ = ["PostgresSqlAlchemyDsn", "TwitterHandle", "UrlsafeString"]


class PostgresSqlAlchemyDsn(AnyUrl):
    """DSN for Postgres for latest sqlalchemy which doesn't allow `postgres` as the scheme"""

    allowed_schemes = {"postgresql"}
    user_required = True


class TwitterHandle(str):
    """Twitter Handle type for Pydantic schemas"""

    @classmethod
    def __modify_schema__(cls, field_schema: Dict[str, Any]) -> None:
        field_schema.update(type="string", format="twitter_handle")

    @classmethod
    def __get_validators__(cls) -> "CallableGenerator":
        yield str_validator
        yield cls.validate

    @classmethod
    def validate(cls, value: Union[str]) -> str:
        if validate_twitter_handle(value):
            return value

        raise ValueError("Invalid twitter handle")


class UrlsafeString(str):
    """API key type for Pydantic schemas

    It's a URL safe string of minimum length and max length
    """

    strip_whitespace = True
    min_length = 16
    max_length = 128

    @classmethod
    def __modify_schema__(cls, field_schema: Dict[str, Any]) -> None:
        update_not_none(
            field_schema, minLength=cls.min_length, maxLength=cls.max_length, format="api_key"
        )

    @classmethod
    def __get_validators__(cls) -> "CallableGenerator":
        yield str_validator
        yield cls.validate
        yield urlsafe_str_validator

    @classmethod
    def validate(cls, value: Union[str]) -> str:
        if cls.min_length <= len(value) <= cls.max_length:
            return value

        raise ValueError(
            "Invalid length. Must be between {} and {}".format(cls.min_length, cls.max_length)
        )
