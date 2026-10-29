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

from typing import Annotated, Literal, TypeAlias

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
    start: int
    """Where the token begins in the text of its view, in Unicode code points.

    Code points are the unit of a Python str: text[start:end] is the token's
    span. A token that cuts a character spans that whole character.
    """
    end: int
    """Where the token ends in the text of its view, in Unicode code points."""
    byte_start: int
    """Where the token's bytes begin in the UTF-8 encoding of the text."""
    byte_end: int
    """Where the token's bytes end in the UTF-8 encoding of the text."""
    bytes: str
    """The token's UTF-8 bytes, in hex, e.g. "20 F0 9F"."""
    special: bool
    """Whether the token is a special token, a marker such as <|im_start|>."""
    added: bool
    """Whether the token is an added token, outside the merge rules."""
    partial: bool
    """Whether the token begins or ends inside a character, e.g. an emoji.

    Its text then shows the bytes of the cut character as ⟨F0 9F⟩.
    """


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


class MetadataView(BaseModel):
    """One piece of a capture's metadata, with where it comes from."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    label: str
    """What the value is, e.g. "Reported model"."""
    value: str
    """The value, as text."""
    source: Literal["request", "provider", "local"]
    """Who says so: request is what the laptop sent, provider what the
    provider's service answered, local what the laptop measured or this
    viewer reconstructed."""


class CaptureView(BaseModel):
    """A captured provider response."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    name: str
    """The capture file's name."""
    answer: str | None
    """The answer text, or None if the response has none."""
    reasoning: str | None
    """The reasoning text, or None if the response has none."""
    metadata: list[MetadataView]
    """The response metadata, each piece with its source."""


class ViewModel(BaseModel):
    """Everything the views show at one moment. Every command returns it."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    tokenizer: TokenizerView | None
    """The tokenizer in use, or None before load_model."""
    notice: str | None
    """A note the views show above the tokens, or None."""
    messages: list[Message]
    """The chat messages, as set_messages received them."""
    template_switches: dict[str, bool]
    """The chat template's switches, e.g. {"enable_thinking": false}."""
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
