"""The page's back end: thin HTTP routes, one controller command each.

The page sends a command as JSON. A route parses it into one of the request
classes below, calls one command and returns the view-model, which FastAPI
sends back as JSON. FastAPI also describes every route and class at
/openapi.json, from which the page's TypeScript types are generated, and shows
them at /docs.

Run from the backend folder: uv run uvicorn token_viewer.api:app --port 8000

Answers:
- 200 with the view-model.
- 422 when the JSON does not fit the request class; the controller never ran.
  The answer says where and why, without repeating the input.
- 400 when the controller refused the command (CommandError). FastAPI itself
  also answers 400, "There was an error parsing the body", to a body that is
  not UTF-8, such as an umlaut sent by Windows PowerShell 5.1 without
  "; charset=utf-8" in the Content-Type.

There is no CORS middleware, on purpose: the page reaches this API through the
Vite proxy, on its own origin. Other web pages can still make the browser send
commands here, but not with Content-Type: application/json. FastAPI reads a
body as JSON only with a JSON Content-Type while strict_content_type is on,
its default, so such commands answer 422 and change nothing: keep it on.
uvicorn listens only on 127.0.0.1, its default; keep it that way.
"""

import threading

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from token_viewer.controller import CommandError, Controller
from token_viewer.view_models import Message, Text, ViewModel
from token_viewer.wiring import build_controller


class RequestBody(BaseModel):
    """A command's arguments, as JSON.

    Strict: "3" is not an int and true is not 1, and unknown keys are refused.
    """

    # Strict, so that a body that does not fit exactly gets 422, never a guess.
    model_config = ConfigDict(
        strict=True, extra="forbid", use_attribute_docstrings=True
    )


class RepositoryChoice(RequestBody):
    """The arguments of load_model."""

    repository: Text
    """The model repository on Hugging Face, as owner/name."""
    revision: Text
    """The revision to take the files from."""


class MessageList(RequestBody):
    """The argument of set_messages."""

    messages: list[Message]
    """The chat messages, as a chat completions API receives them."""


class CaptureFile(RequestBody):
    """The arguments of load_capture: a capture file the user picked."""

    name: Text
    """The file's name."""
    content: Text
    """The file's content, as text."""


class ViewChoice(RequestBody):
    """The argument of select_view."""

    key: Text
    """The key of one of the view-model's views."""


class Selection(RequestBody):
    """The argument of select_token."""

    index: int
    """The position of a token in the current view."""


class Refusal(BaseModel):
    """The body of a 400 answer: why the controller refused the command."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    detail: str
    """The reason, in words meant for the user."""


def create_app(controller: Controller) -> FastAPI:
    """Build the web API around one controller."""
    app: FastAPI = FastAPI(
        title="Token viewer",
        # Describes the 400 answer of every route in /docs and in the types.
        responses={400: {"model": Refusal, "description": "Command refused"}},
    )
    # FastAPI runs def routes in parallel worker threads, and the model is not
    # thread-safe: the lock lets one command touch the model at a time.
    one_at_a_time: threading.Lock = threading.Lock()

    @app.exception_handler(CommandError)
    def refused(request: Request, error: CommandError) -> JSONResponse:
        return JSONResponse(
            status_code=400, content=Refusal(detail=str(error)).model_dump()
        )

    @app.exception_handler(RequestValidationError)
    def unfit(request: Request, error: RequestValidationError) -> JSONResponse:
        # FastAPI's own 422 answer repeats the input, and JSON cannot carry
        # every input back: NaN, for example, or half of a UTF-16 pair.
        detail: list[dict[str, object]] = [
            {"loc": problem["loc"], "msg": problem["msg"], "type": problem["type"]}
            for problem in error.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": detail})

    @app.get("/api/view-model")
    def view_model() -> ViewModel:
        with one_at_a_time:
            return controller.view_model()

    @app.post("/api/model")
    def load_model(body: RepositoryChoice) -> ViewModel:
        with one_at_a_time:
            return controller.load_model(body.repository, body.revision)

    @app.post("/api/messages")
    def set_messages(body: MessageList) -> ViewModel:
        with one_at_a_time:
            return controller.set_messages(body.messages)

    @app.post("/api/capture")
    def load_capture(body: CaptureFile) -> ViewModel:
        with one_at_a_time:
            return controller.load_capture(body.name, body.content)

    @app.post("/api/view")
    def select_view(body: ViewChoice) -> ViewModel:
        with one_at_a_time:
            return controller.select_view(body.key)

    @app.post("/api/selection")
    def select(body: Selection) -> ViewModel:
        with one_at_a_time:
            return controller.select_token(body.index)

    # Yours: for each command you add to Controller, a route like these, with
    # a request class derived from RequestBody, like Selection above.

    return app


# The app uvicorn serves. build_controller() in wiring.py decides which
# controller it uses.
app: FastAPI = create_app(build_controller())
