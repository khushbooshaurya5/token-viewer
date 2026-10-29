"""The view-models: what the views receive, and the contract with the page.

A view-model is plain data shaped for display. Python decides what is shown;
each view decides how it looks. FastAPI describes these classes in OpenAPI, at
/openapi.json, and openapi-typescript turns that description into the
TypeScript types in frontend/src/schema.d.ts. After a change here, restart the
back end and run npm run types in the frontend folder.

Two rules keep the generated types simple:
- No default values in ViewModel and the classes in it. Every field the page
  receives is then required in OpenAPI, and TypeScript never sees an optional
  field there. A field of a request class in api.py may have a default:
  TypeScript then marks it optional, and the page may leave it out.
- No computed fields or custom serializers on a class that is also part of a
  request, such as Message. FastAPI would split it into two schemas,
  Message-Input and Message-Output.

The docstring under each field becomes its description in OpenAPI, in /docs
and in the generated TypeScript types.
"""

from typing import Annotated, TypeAlias

from pydantic import AfterValidator, BaseModel, ConfigDict


def _whole_characters(text: str) -> str:
    """Refuse text that UTF-8 cannot encode: a lone surrogate."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(
            "not valid Unicode text: a lone surrogate, half of a UTF-16 pair"
        ) from None
    return text


Text: TypeAlias = Annotated[str, AfterValidator(_whole_characters)]
"""A str for request fields: it refuses a lone surrogate with 422.

JSON can carry half of a UTF-16 pair, such as the escape \\ud83d without the
second half, and Python keeps it in a str. But no answer can carry it: once
it is in the model, every view-model with it fails to send, with 500.
"""


class TokenView(BaseModel):
    """One token, as the views show it."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    index: int
    """The token's position in its sequence, counted from 0."""
    id: int
    """The token's ID in the vocabulary."""
    piece: str
    """The vocabulary entry for this ID."""
    text: str
    """The token's text, as the views show it."""
    # Yours: decide what start and end count, and say so in their docstrings
    # (README.md, section 6).
    start: int
    """Where the token begins in the text of its view."""
    end: int
    """Where the token ends in the text of its view."""
    special: bool
    """Whether the token is a special token."""


class TokenizerView(BaseModel):
    """Where the tokenizer and the chat template come from."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    repository: str
    """The model repository on Hugging Face, as owner/name."""
    revision: str
    """The revision the files were taken from."""


class Message(BaseModel):
    """One chat message, as a chat completions API receives it.

    Unknown keys are refused, as in the request bodies in api.py. To send
    another key, add a field for it here first.
    """

    # Refuse unknown keys: a dropped key would silently change the tokens.
    model_config = ConfigDict(use_attribute_docstrings=True, extra="forbid")

    role: Text
    """Who speaks, e.g. "user"."""
    content: Text
    """What the message says."""


class ViewOption(BaseModel):
    """One view the user can choose: a text and its tokens.

    A view in this sense is one token sequence, for example the chat after the
    chat template, or the text alone. select_view switches between them. The
    page and the terminal view are views in the other sense: the V of MVC.
    """

    model_config = ConfigDict(use_attribute_docstrings=True)

    key: str
    """What select_view receives, e.g. "chat"."""
    title: str
    """What the view selector shows."""


class CaptureView(BaseModel):
    """A captured provider response.

    A first version with the two texts only. Add the response metadata the
    task asks for.
    """

    model_config = ConfigDict(use_attribute_docstrings=True)

    name: str
    """The capture file's name."""
    answer: str | None
    """The answer text, or None if the response has none."""
    reasoning: str | None
    """The reasoning text, or None if the response has none."""
    # Yours: the response metadata that "4. Captures" on the task sheet lists.


class ViewModel(BaseModel):
    """Everything the views show at one moment. Every command returns it."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    tokenizer: TokenizerView | None
    """The tokenizer in use, or None before load_model."""
    notice: str | None
    """A note the views show above the tokens, or None."""
    messages: list[Message]
    """The chat messages, as set_messages received them."""
    views: list[ViewOption]
    """The views select_view can choose from."""
    current_view: str | None
    """The key of the view shown, or None while there is none."""
    text: str
    """The text of the current view."""
    tokens: list[TokenView]
    """The tokens of the current view."""
    selected: TokenView | None
    """The selected token of the current view, or None."""
    capture: CaptureView | None
    """The loaded capture, or None before load_capture."""
