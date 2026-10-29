"""The routes, run against the fake controller: no server and no network.

TestClient hands each request straight to the app inside this process, so the
tests need neither uvicorn nor the page.
"""

import json
import re
from collections.abc import Iterator
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient

from token_viewer.api import create_app
from token_viewer.fake_controller import FakeController
from token_viewer.view_models import ViewModel

# The fields of TokenView that the page relies on.
TOKEN_FIELDS: set[str] = {"index", "id", "piece", "text", "start", "end", "special"}

# The first half of a UTF-16 pair, alone: JSON carries it as the escape \ud83d.
HALF_A_PAIR: str = "\ud83d"


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A new app with a new fake controller for every test."""
    with TestClient(create_app(FakeController())) as test_client:
        yield test_client


def current(client: TestClient) -> ViewModel:
    """Fetch the view-model and check that it fits the class."""
    response: httpx2.Response = client.get("/api/view-model")
    assert response.status_code == 200
    return ViewModel.model_validate(response.json())


def command(client: TestClient, path: str, body: dict[str, Any]) -> ViewModel:
    """Send one command and check that it answers with a view-model."""
    response: httpx2.Response = client.post(path, json=body)
    assert response.status_code == 200
    return ViewModel.model_validate(response.json())


def test_the_page_gets_the_view_model(client: TestClient) -> None:
    shown: ViewModel = current(client)
    assert shown.current_view == "chat"
    assert [token.index for token in shown.tokens] == list(range(7))
    assert shown.selected is None


def test_a_selection_stays_in_the_back_end(client: TestClient) -> None:
    answer: ViewModel = command(client, "/api/selection", {"index": 3})
    assert answer.selected is not None
    assert answer.selected.index == 3
    # A later request sees the same selection: the state lives behind the
    # controller, not in the page.
    assert current(client).selected == answer.selected


@pytest.mark.parametrize(
    ("path", "body", "reason"),
    [
        ("/api/model", {"repository": " ", "revision": "main"}, "repository"),
        ("/api/messages", {"messages": []}, "message"),
        ("/api/view", {"key": "nope"}, "nope"),
        ("/api/selection", {"index": 99}, "99"),
    ],
)
def test_a_refused_command_answers_400_and_changes_nothing(
    client: TestClient, path: str, body: dict[str, Any], reason: str
) -> None:
    # Select a token first, so that "nothing" includes the selection.
    command(client, "/api/selection", {"index": 3})
    before: ViewModel = current(client)
    response: httpx2.Response = client.post(path, json=body)
    assert response.status_code == 400
    assert reason in response.json()["detail"]
    assert current(client) == before


@pytest.mark.parametrize(
    "body",
    [{"index": "three"}, {"index": "3"}, {"index": True}, {"index": 3, "x": 1}, {}],
)
def test_json_that_does_not_fit_answers_422_before_the_controller(
    client: TestClient, body: dict[str, Any]
) -> None:
    before: ViewModel = current(client)
    response: httpx2.Response = client.post("/api/selection", json=body)
    assert response.status_code == 422
    assert current(client) == before


@pytest.mark.parametrize(
    "content_type",
    [
        "text/plain",
        "text/plain; charset=utf-8",
        "application/x-www-form-urlencoded",
        "multipart/form-data; boundary=x",
        None,
    ],
)
def test_a_body_not_declared_as_json_answers_422(
    client: TestClient, content_type: str | None
) -> None:
    # Any web page can make the browser send these to port 8000 without asking
    # the back end first. FastAPI reads a body as JSON only with a JSON
    # Content-Type.
    before: ViewModel = current(client)
    headers: dict[str, str] = (
        {} if content_type is None else {"Content-Type": content_type}
    )
    response: httpx2.Response = client.post(
        "/api/selection", content=b'{"index": 3}', headers=headers
    )
    assert response.status_code == 422
    assert current(client) == before


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/model", {"repository": HALF_A_PAIR, "revision": "main"}),
        ("/api/model", {"repository": "owner/name", "revision": HALF_A_PAIR}),
        ("/api/messages", {"messages": [{"role": HALF_A_PAIR, "content": "Hi"}]}),
        ("/api/messages", {"messages": [{"role": "user", "content": HALF_A_PAIR}]}),
        ("/api/capture", {"name": HALF_A_PAIR, "content": "{}"}),
        ("/api/capture", {"name": "capture.json", "content": HALF_A_PAIR}),
        ("/api/view", {"key": HALF_A_PAIR}),
    ],
)
def test_half_a_utf16_pair_answers_422(
    client: TestClient, path: str, body: dict[str, Any]
) -> None:
    # Once in the model, no view-model could be sent: every answer would be 500.
    before: ViewModel = current(client)
    response: httpx2.Response = client.post(
        path, content=json.dumps(body), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert current(client) == before


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity"])
def test_nan_and_infinity_answer_422(client: TestClient, number: str) -> None:
    # Python's JSON parser takes these words, but no JSON answer can carry them
    # back. The 422 answer says where and why, without the input.
    response: httpx2.Response = client.post(
        "/api/selection",
        content='{"index": ' + number + "}",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    [problem] = response.json()["detail"]
    assert set(problem) == {"loc", "msg", "type"}
    assert problem["loc"] == ["body", "index"]


def test_an_unknown_key_in_a_message_answers_422(client: TestClient) -> None:
    before: ViewModel = current(client)
    response: httpx2.Response = client.post(
        "/api/messages",
        json={"messages": [{"role": "user", "content": "Hi", "name": "x"}]},
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "messages", 0, "name"]
    assert current(client) == before


def test_every_route_carries_out_its_own_command(client: TestClient) -> None:
    shown: ViewModel = command(
        client, "/api/model", {"repository": "owner/name", "revision": "main"}
    )
    assert shown.tokenizer is not None
    assert shown.tokenizer.repository == "owner/name"
    assert shown.tokenizer.revision == "main"
    shown = command(
        client, "/api/messages", {"messages": [{"role": "system", "content": "Hi"}]}
    )
    assert [(message.role, message.content) for message in shown.messages] == [
        ("system", "Hi")
    ]
    shown = command(client, "/api/capture", {"name": "capture.json", "content": "{}"})
    assert shown.capture is not None
    assert shown.capture.name == "capture.json"
    shown = command(client, "/api/view", {"key": "text"})
    assert shown.current_view == "text"
    shown = command(client, "/api/selection", {"index": 0})
    assert shown.selected is not None
    assert shown.selected.index == 0


def test_another_view_clears_the_selection(client: TestClient) -> None:
    command(client, "/api/selection", {"index": 3})
    shown: ViewModel = command(client, "/api/view", {"key": "text"})
    assert shown.selected is None
    assert current(client).selected is None


def received(schemas: dict[str, Any], names: list[str]) -> list[str]:
    """Name these schemas and every schema they refer to, directly or not."""
    found: list[str] = []
    waiting: list[str] = list(names)
    while waiting:
        name: str = waiting.pop()
        if name not in found:
            found.append(name)
            waiting += re.findall(
                r'"#/components/schemas/([^"]+)"', json.dumps(schemas[name])
            )
    return sorted(found)


def test_the_contract_keeps_the_generated_types_simple() -> None:
    schemas: dict[str, Any] = create_app(FakeController()).openapi()["components"][
        "schemas"
    ]
    # The page reads these fields of every token.
    assert set(schemas["TokenView"]["required"]) >= TOKEN_FIELDS
    # Every field the page receives is required, so none is optional in
    # TypeScript. A request class may have optional fields.
    assert "Refusal" in schemas
    optional: list[str] = [
        name
        for name in received(schemas, ["ViewModel", "Refusal"])
        if set(schemas[name].get("properties", {}))
        != set(schemas[name].get("required", []))
    ]
    assert optional == []
    # One schema per class: no Message-Input and Message-Output.
    assert [name for name in schemas if name.endswith(("-Input", "-Output"))] == []
