from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption("--pubtator", action="store_true", help="Run tests that use PubTator3 API")


def pytest_collection_modifyitems(config, items):
    skip_tests_need_cnx = pytest.mark.skipif("not config.getoption('--pubtator')")

    for item in items:
        if item.name.startswith("test_api_"):
            item.add_marker(skip_tests_need_cnx)


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return Path(__file__).parent / "test_data"
