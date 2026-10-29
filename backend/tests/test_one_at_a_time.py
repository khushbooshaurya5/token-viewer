"""The lock in api.py: one command at a time, also with several requests."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from token_viewer.api import create_app
from token_viewer.fake_controller import FakeController
from token_viewer.view_models import ViewModel

# One request per route, method and path, that the fake controller carries
# out. Add a request here for every route you add, or the first test below
# fails.
REQUESTS: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/api/view-model", None),
    ("POST", "/api/model", {"repository": "owner/name", "revision": "main"}),
    ("POST", "/api/messages", {"messages": [{"role": "user", "content": "Hi"}]}),
    ("POST", "/api/capture", {"name": "capture.json", "content": "{}"}),
    ("POST", "/api/view", {"key": "text"}),
    ("POST", "/api/selection", {"index": 0}),
]


class CountingController(FakeController):
    """Counts how many commands build a view-model at the same time."""

    def __init__(self) -> None:
        """Start with no command running."""
        super().__init__()
        self.guard: threading.Lock = threading.Lock()
        self.running: int = 0
        self.most: int = 0

    def view_model(self) -> ViewModel:
        """Build the view-model slowly, so that requests would overlap.

        Every route ends in exactly one call of view_model: the query calls
        it directly, and each command calls it after its model operation.
        """
        with self.guard:
            self.running += 1
            self.most = max(self.most, self.running)
        time.sleep(0.05)
        with self.guard:
            self.running -= 1
        return super().view_model()


class WaitingController(FakeController):
    """Holds load_model, as a first download would, until the test lets go."""

    def __init__(self) -> None:
        """Start with load_model neither started nor finished."""
        super().__init__()
        self.started: threading.Event = threading.Event()
        self.go_on: threading.Event = threading.Event()
        self.finished: threading.Event = threading.Event()

    def load_model(self, repository: str, revision: str) -> ViewModel:
        """Wait for the test, at most 5 seconds, then load as the fake does."""
        self.started.set()
        self.go_on.wait(timeout=5)
        shown: ViewModel = super().load_model(repository, revision)
        self.finished.set()
        return shown


def test_the_requests_cover_every_route() -> None:
    app: FastAPI = create_app(FakeController())
    routes: set[tuple[str, str]] = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods or ()
    }
    assert {(method, path) for method, path, _ in REQUESTS} == routes


def test_commands_run_one_at_a_time() -> None:
    controller: CountingController = CountingController()
    with (
        TestClient(create_app(controller)) as client,
        ThreadPoolExecutor(max_workers=len(REQUESTS)) as pool,
    ):

        def send(request: tuple[str, str, dict[str, Any] | None]) -> int:
            method, path, body = request
            return client.request(method, path, json=body).status_code

        # Every route twice, all at once: a route without the lock overlaps.
        statuses: list[int] = list(pool.map(send, REQUESTS * 2))
    assert statuses == [200] * len(REQUESTS) * 2
    assert controller.most == 1


def test_the_api_description_does_not_wait_for_a_command() -> None:
    # npm run types reads /openapi.json, also while load_model downloads.
    controller: WaitingController = WaitingController()
    with (
        TestClient(create_app(controller)) as client,
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        loading = pool.submit(
            client.post, "/api/model", json={"repository": "a/b", "revision": "main"}
        )
        assert controller.started.wait(timeout=5)
        description: int = client.get("/openapi.json").status_code
        answered_during_the_command: bool = not controller.finished.is_set()
        controller.go_on.set()
        assert loading.result().status_code == 200
    assert description == 200
    assert answered_during_the_command
