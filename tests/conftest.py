import os
import random
from typing import Optional

import pytest
import requests
from docker.models.containers import Container
from requests.adapters import HTTPAdapter
from urllib3 import Retry

try:
    # Should be installed as pyvespa-dependency
    import docker

    client = docker.from_env()
    docker_available = client.ping()
except Exception as e:
    docker_available = False


@pytest.fixture
def random_port() -> int:
    return random.randint(1025, 65535)


@pytest.fixture
def wiremock_server(random_port: int) -> Optional[Container]:
    if not docker_available:
        return None

    wiremock_dir = os.path.join(os.path.dirname(__file__), "wiremock")
    container = client.containers.run(
        image="wiremock/wiremock:3.13.0-1",
        auto_remove=True,
        detach=True,
        ports={"8080/tcp": random_port},
        remove=True,
        volumes=[wiremock_dir + ":/home/wiremock/"],
        command="--verbose --local-response-templating",
    )

    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    http = requests.Session()
    http.mount("https://", adapter)
    http.mount("http://", adapter)
    http.get("http://localhost:" + str(random_port) + "/health", timeout=10)

    return container


@pytest.fixture
def wiremock_url(wiremock_server: Optional[Container]) -> Optional[str]:
    if wiremock_server is None:
        return None

    port = wiremock_server.attrs["HostConfig"]["PortBindings"]["8080/tcp"][0][
        "HostPort"
    ]
    return f"http://localhost:{port}"
