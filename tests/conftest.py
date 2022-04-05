import io
from typing import BinaryIO, Callable, Optional

import pytest
from betamax import Betamax

from .utils import PATH_TESTS_FIXTURES

with Betamax.configure() as config:
    config.cassette_library_dir = "tests/fixtures/cassettes"


def _read_fixture_file(filename: str, directory: str = "files") -> BinaryIO:
    """Read a fixture file and return a file object"""
    excel_file_path = PATH_TESTS_FIXTURES / directory / filename

    if not excel_file_path.is_file():
        raise Exception("Could not find excel fixture at {}".format(excel_file_path))

    _fh = io.open(excel_file_path, mode="rb")

    return _fh


@pytest.fixture
def load_file() -> Callable:
    """Load a static file pytest fixture"""
    return _read_fixture_file


@pytest.fixture
def xls_old_file(load_file: Callable) -> BinaryIO:
    return load_file("old.xls")


@pytest.fixture
def xls_file(load_file: Callable) -> BinaryIO:
    return load_file("excel_template_compat.xls")


@pytest.fixture
def xlsx_file(load_file: Callable) -> BinaryIO:
    return load_file("excel_template.xlsx")


@pytest.fixture
def aemo_nemweb_dispatch_scada(load_file: Callable) -> BinaryIO:
    return load_file("PUBLIC_DISPATCHSCADA_202109021255_0000000348376188.zip")


@pytest.fixture
def aemo_nemweb_dirlisting(scrapy_mock_response: Callable) -> BinaryIO:
    return scrapy_mock_response(
        filename="nemweb_dispatch_scada_dirlisting.html",
        url="https://www.nemweb.com.au/Reports/CURRENT/Dispatch_SCADA/",
    )


@pytest.fixture
def aemo_nemweb_dirlisting_live(scrapy_mock_response: Callable) -> BinaryIO:
    return scrapy_mock_response(
        url="https://www.nemweb.com.au/Reports/CURRENT/Dispatch_SCADA/",
    )
