import pytest


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Keep one asyncio runner for live HTTP clients and their deferred cleanup."""
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
async def live_asyncio_session(anyio_backend: str):
    """Hold an anyio runner lease until every live test has finished."""
    yield
