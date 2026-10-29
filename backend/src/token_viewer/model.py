"""The model: a tokenizer, a chat template, messages and the tokens they make.

MVC's model, the domain and its state. It knows nothing of view-models, of the
controller or of any view, and imports no web framework.

What it does, step by step, as token_lab's tokenize_chat.py does:
1. Fetch tokenizer.json and the chat template of a repository at a pinned
   commit (hub.py).
2. Render the chat template on the messages, in a sandbox, with the template
   switches, e.g. enable_thinking=False.
3. Encode that text into tokens, adding nothing: the template wrote every
   marker already.

Each token also gets its bytes and its offsets. Offsets count Unicode code
points, the unit of a Python str: text[start:end] is the token's span. A
byte-level tokenizer can cut a character, such as an emoji, into several
tokens; each of those then spans the whole character and is marked partial,
and its text shows the bytes it carries, e.g. ⟨F0 9F⟩.
"""

import json
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import TemplateError
from jinja2.sandbox import ImmutableSandboxedEnvironment
from tokenizers import Encoding, Tokenizer

from token_viewer.capture import Capture, CaptureError, read_capture
from token_viewer.course import COURSE_MESSAGES, COURSE_TEMPLATE_SWITCHES
from token_viewer.hub import Fetcher, FetchError


class ModelError(Exception):
    """The model refused an operation and kept its state.

    The message says why, in words meant for the user. The controller turns
    it into a CommandError, so this module never imports controller.py.
    """


@dataclass(frozen=True)
class Token:
    """One token of a sequence, with everything the views may show."""

    index: int
    id: int
    piece: str
    """The vocabulary entry, e.g. Ġtoken for " token"."""
    text: str
    """The token's text; bytes of a cut character appear as ⟨F0 9F⟩."""
    start: int
    """First code point of the text the token touches."""
    end: int
    """One past the last code point the token touches."""
    byte_start: int
    """First UTF-8 byte of the token in the text."""
    byte_end: int
    """One past the token's last UTF-8 byte."""
    bytes: bytes
    special: bool
    """A special token: a marker of structure, such as <|im_start|>."""
    added: bool
    """An added token, outside the merge rules, such as <think>."""
    partial: bool
    """The token begins or ends inside a character."""


@dataclass(frozen=True)
class Sequence:
    """One view: a text and its tokens, with a note on what it is."""

    key: str
    title: str
    text: str
    tokens: list[Token]
    note: str


@dataclass(frozen=True)
class Loaded:
    """What load needs to keep: where the files come from and what they hold."""

    repository: str
    revision: str
    """The revision as the user gave it, e.g. main or a commit."""
    commit: str
    """The 40-character commit the files come from."""
    tokenizer: Tokenizer
    template: str | None
    """The chat template's source, or None if the repository has none."""
    template_variables: dict[str, str]
    """Special tokens the template may use, such as bos_token."""
    special_ids: frozenset[int]
    added_ids: dict[int, str]
    """Every added token's ID and content."""


class TokenModel:
    """The token viewer's domain state, changed only through its operations.

    Each operation checks before it changes anything and assigns its new state
    last, so a refused operation leaves everything as it was.
    """

    def __init__(self, fetcher: Fetcher) -> None:
        """Start with the course messages and switches, and no tokenizer yet.

        Quick and offline: files are fetched by load, not here.
        """
        self._fetcher: Fetcher = fetcher
        self.loaded: Loaded | None = None
        self.messages: list[tuple[str, str]] = list(COURSE_MESSAGES)
        self.template_switches: dict[str, bool] = dict(COURSE_TEMPLATE_SWITCHES)
        self.capture: Capture | None = None
        self.sequences: list[Sequence] = []
        self.view: str | None = None
        self.selected: int | None = None

    # --- Operations ---------------------------------------------------------

    def load(self, repository: str, revision: str) -> None:
        """Use the tokenizer and chat template of repository at revision.

        Raises:
            ModelError: If the files cannot be fetched or read.
        """
        repository, revision = repository.strip(), revision.strip()
        if repository.count("/") != 1 or not all(repository.split("/")):
            raise ModelError(f"Give the repository as owner/name, not {repository!r}.")
        if not revision:
            raise ModelError("Give a revision: a commit, or a branch such as main.")
        try:
            commit: str = self._fetcher.resolve(repository, revision)
            files: dict[str, Path] = self._fetcher.fetch(repository, commit)
        except FetchError as problem:
            raise ModelError(str(problem)) from problem
        loaded: Loaded = _read_files(repository, revision, commit, files)
        self._commit(loaded=loaded)

    def set_messages(self, messages: list[tuple[str, str]]) -> None:
        """Replace the messages, as pairs of role and content.

        Raises:
            ModelError: If there are none, or the template refuses them.
        """
        if not messages:
            raise ModelError("Give at least one message.")
        self._commit(messages=list(messages))

    def set_template_switches(self, switches: dict[str, bool]) -> None:
        """Replace the chat template's switches, e.g. enable_thinking."""
        self._commit(template_switches=dict(switches))

    def load_capture(self, name: str, content: str) -> None:
        """Read a capture file's content.

        Raises:
            ModelError: If it is not a capture.
        """
        try:
            capture: Capture = read_capture(name, content)
        except CaptureError as problem:
            raise ModelError(str(problem)) from problem
        self._commit(capture=capture)

    def show_view(self, key: str) -> None:
        """Show another view, and clear the selection.

        Raises:
            ModelError: If there is no view with this key.
        """
        if self._sequence(key) is None:
            raise ModelError(f"There is no view {key!r}.")
        self.view = key
        self.selected = None

    def select(self, index: int) -> None:
        """Select one token of the view shown.

        Raises:
            ModelError: If the view has no token with this index.
        """
        count: int = len(self.tokens())
        if not 0 <= index < count:
            raise ModelError(
                f"There is no token {index}: this view has {count}, numbered from 0."
            )
        self.selected = index

    # --- Queries --------------------------------------------------------------

    def current(self) -> Sequence | None:
        """Return the view shown, or None while there is none."""
        return None if self.view is None else self._sequence(self.view)

    def text(self) -> str:
        """Return the text of the view shown."""
        current: Sequence | None = self.current()
        return "" if current is None else current.text

    def tokens(self) -> list[Token]:
        """Return the tokens of the view shown."""
        current: Sequence | None = self.current()
        return [] if current is None else current.tokens

    def local_prompt_tokens(self) -> int | None:
        """Count the capture's request tokens with the loaded tokenizer."""
        prompt: Sequence | None = self._sequence("capture-prompt")
        return None if prompt is None else len(prompt.tokens)

    # --- State changes ----------------------------------------------------------

    def _commit(
        self,
        *,
        loaded: Loaded | None = None,
        messages: list[tuple[str, str]] | None = None,
        template_switches: dict[str, bool] | None = None,
        capture: Capture | None = None,
    ) -> None:
        """Compute every view for the new state, then assign it all at once.

        Raises:
            ModelError: If the chat template fails; then nothing changed.
        """
        new_loaded: Loaded | None = loaded or self.loaded
        new_messages: list[tuple[str, str]] = (
            self.messages if messages is None else messages
        )
        new_switches: dict[str, bool] = (
            self.template_switches if template_switches is None else template_switches
        )
        new_capture: Capture | None = capture or self.capture
        sequences: list[Sequence] = (
            []
            if new_loaded is None
            else _sequences(new_loaded, new_messages, new_switches, new_capture)
        )

        # Keep the view if it still exists, else show the first one. Keep the
        # selection only while its index still names a token with the same ID.
        keys: list[str] = [s.key for s in sequences]
        view: str | None = self.view if self.view in keys else None
        if view is None and keys:
            view = keys[0]
        selected: int | None = None
        if view is not None and view == self.view and self.selected is not None:
            old: Token = self.tokens()[self.selected]
            new_tokens: list[Token] = sequences[keys.index(view)].tokens
            if (
                self.selected < len(new_tokens)
                and new_tokens[self.selected].id == old.id
            ):
                selected = self.selected

        self.loaded = new_loaded
        self.messages = new_messages
        self.template_switches = new_switches
        self.capture = new_capture
        self.sequences = sequences
        self.view = view
        self.selected = selected

    def _sequence(self, key: str) -> Sequence | None:
        """Return the view with this key, or None."""
        return next((s for s in self.sequences if s.key == key), None)


# --- Reading the files ----------------------------------------------------------


def _read_files(
    repository: str, revision: str, commit: str, files: dict[str, Path]
) -> Loaded:
    """Read the tokenizer, the chat template and the special tokens.

    Raises:
        ModelError: If a file cannot be read.
    """
    try:
        tokenizer: Tokenizer = Tokenizer.from_file(str(files["tokenizer.json"]))
        config: dict[str, Any] = {}
        if "tokenizer_config.json" in files:
            config = json.loads(
                files["tokenizer_config.json"].read_text(encoding="utf-8")
            )
        template: str | None = None
        if "chat_template.jinja" in files:
            template = files["chat_template.jinja"].read_text(encoding="utf-8")
        else:
            template = _template_from_config(config.get("chat_template"))
    except Exception as problem:
        raise ModelError(
            f"Could not read the tokenizer files of {repository}: {problem}"
        ) from problem

    decoder: dict[int, Any] = tokenizer.get_added_tokens_decoder()
    return Loaded(
        repository=repository,
        revision=revision,
        commit=commit,
        tokenizer=tokenizer,
        template=template,
        template_variables=_special_token_names(config),
        special_ids=frozenset(i for i, added in decoder.items() if added.special),
        added_ids={i: added.content for i, added in decoder.items()},
    )


def _template_from_config(value: object) -> str | None:
    """Return the chat template kept in tokenizer_config.json, if any.

    It is a string, or a list of named templates of which "default" is used.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and item.get("name") == "default":
                template: Any = item.get("template")
                return template if isinstance(template, str) else None
    return None


def _special_token_names(config: dict[str, Any]) -> dict[str, str]:
    """Return bos_token, eos_token and the like, as Transformers passes them."""
    names: dict[str, str] = {}
    for key, value in config.items():
        if not key.endswith("_token"):
            continue
        content: Any = value.get("content") if isinstance(value, dict) else value
        if isinstance(content, str):
            names[key] = content
    return names


# --- Building the views ---------------------------------------------------------


def _sequences(
    loaded: Loaded,
    messages: list[tuple[str, str]],
    switches: dict[str, bool],
    capture: Capture | None,
) -> list[Sequence]:
    """Return every view the current state offers, in the selector's order."""
    source: str = f"{loaded.repository} at {loaded.commit[:12]}"
    shown: list[Sequence] = []
    if loaded.template is not None:
        shown.append(
            _encode(
                loaded,
                "chat",
                "Chat, after the chat template",
                _render(loaded, messages, switches),
                f"What the model reads: the chat template of {source}, rendered "
                f"locally with {_switches_text(switches)}, then encoded.",
            )
        )
    for number, (role, content) in enumerate(messages, start=1):
        shown.append(
            _encode(
                loaded,
                f"message-{number}",
                f"Message {number} ({role}), text alone",
                content,
                f"Message {number}'s content alone, without the chat template.",
            )
        )
    if capture is not None:
        shown.extend(_capture_sequences(loaded, capture))
    return shown


def _capture_sequences(loaded: Loaded, capture: Capture) -> list[Sequence]:
    """Return the capture's views: its prompt, answer and reasoning, re-tokenized."""
    shown: list[Sequence] = []
    retokenized: str = (
        "Re-tokenized locally: the provider returned text, not token IDs. These "
        f"are the tokens {loaded.repository} makes of that text; the tokens the "
        "model generated can differ, e.g. where one text has several encodings."
    )
    if loaded.template is not None and capture.request_messages:
        shown.append(
            _encode(
                loaded,
                "capture-prompt",
                "Captured request, after the chat template",
                _render(loaded, capture.request_messages, capture.template_switches),
                "Local reconstruction of the prompt the provider's server built: "
                "the capture's messages and template switches, rendered with "
                f"the chat template of {loaded.repository}.",
            )
        )
    if capture.answer is not None:
        shown.append(
            _encode(
                loaded,
                "capture-answer",
                "Answer, re-tokenized",
                capture.answer,
                retokenized,
            )
        )
    if capture.reasoning is not None:
        shown.append(
            _encode(
                loaded,
                "capture-reasoning",
                "Reasoning, re-tokenized",
                capture.reasoning,
                retokenized,
            )
        )
    return shown


def _switches_text(switches: dict[str, bool]) -> str:
    """Describe the switches, e.g. "enable_thinking=False"."""
    if not switches:
        return "no template switches"
    return ", ".join(f"{name}={value}" for name, value in switches.items())


def _render(
    loaded: Loaded, messages: list[tuple[str, str]], switches: dict[str, bool]
) -> str:
    """Write the messages into one text with the chat template.

    The template is code downloaded from the internet, so it runs in Jinja's
    immutable sandbox, with the settings and helpers Transformers gives it:
    the text is then the one an inference server such as vLLM builds.

    Raises:
        ModelError: If the template fails, e.g. with raise_exception.
    """
    environment: ImmutableSandboxedEnvironment = ImmutableSandboxedEnvironment(
        trim_blocks=True,
        lstrip_blocks=True,
        extensions=["jinja2.ext.loopcontrols"],
    )
    environment.filters["tojson"] = _tojson
    environment.globals["raise_exception"] = _raise_exception
    environment.globals["strftime_now"] = _strftime_now
    try:
        return environment.from_string(loaded.template or "").render(
            messages=[{"role": role, "content": content} for role, content in messages],
            # End with the start of the assistant's turn, as servers do.
            add_generation_prompt=True,
            **loaded.template_variables,
            **switches,
        )
    except TemplateError as problem:
        raise ModelError(f"The chat template refused the messages: {problem}") from None


def _tojson(
    value: object,
    ensure_ascii: bool = False,
    indent: int | None = None,
    separators: tuple[str, str] | None = None,
    sort_keys: bool = False,
) -> str:
    """Write JSON as Transformers' tojson filter does: no HTML escaping."""
    return json.dumps(
        value,
        ensure_ascii=ensure_ascii,
        indent=indent,
        separators=separators,
        sort_keys=sort_keys,
    )


def _raise_exception(message: str) -> None:
    """Let a template refuse its input, as Transformers allows."""
    raise TemplateError(message)


def _strftime_now(format: str) -> str:
    """Give a template today's date, as Transformers allows."""
    return datetime.now().strftime(format)


def _encode(loaded: Loaded, key: str, title: str, text: str, note: str) -> Sequence:
    """Encode text, adding no special tokens, and describe every token."""
    encoding: Encoding = loaded.tokenizer.encode(text, add_special_tokens=False)
    return Sequence(key, title, text, _describe(loaded, text, encoding), note)


def _describe(loaded: Loaded, text: str, encoding: Encoding) -> list[Token]:
    """Give every token its bytes, offsets and display text.

    A byte-level tokenizer writes each byte as one character of its alphabet,
    e.g. Ġ for a space: mapping the pieces back gives each token's bytes, and
    together they must give exactly the UTF-8 bytes of the text. If they do
    not, the tokenizer is of another kind, and the offsets it reports are used.
    """
    pieces: list[bytes] | None = _piece_bytes(loaded, encoding)
    data: bytes = text.encode("utf-8")
    if pieces is None or b"".join(pieces) != data:
        return _describe_by_offsets(loaded, text, encoding)

    # boundaries[i] is the byte where character i begins; the last entry is
    # the end of the text.
    boundaries: list[int] = [0]
    for character in text:
        boundaries.append(boundaries[-1] + len(character.encode("utf-8")))

    tokens: list[Token] = []
    position: int = 0
    for index, (token_id, piece, chunk) in enumerate(
        zip(encoding.ids, encoding.tokens, pieces, strict=True)
    ):
        byte_start, byte_end = position, position + len(chunk)
        position = byte_end
        # The characters the token's first and last byte belong to.
        start: int = bisect_right(boundaries, byte_start) - 1
        end: int = bisect_left(boundaries, byte_end)
        partial: bool = not (
            boundaries[start] == byte_start and boundaries[end] == byte_end
        )
        tokens.append(
            Token(
                index=index,
                id=token_id,
                piece=piece,
                text=_shown_text(data, boundaries, byte_start, byte_end),
                start=start,
                end=end,
                byte_start=byte_start,
                byte_end=byte_end,
                bytes=chunk,
                special=token_id in loaded.special_ids,
                added=token_id in loaded.added_ids,
                partial=partial,
            )
        )
    return tokens


def _piece_bytes(loaded: Loaded, encoding: Encoding) -> list[bytes] | None:
    """Return each token's bytes, or None if a piece is outside the alphabet."""
    alphabet: dict[str, int] = _byte_alphabet()
    chunks: list[bytes] = []
    for token_id, piece in zip(encoding.ids, encoding.tokens, strict=True):
        if token_id in loaded.added_ids:
            chunks.append(loaded.added_ids[token_id].encode("utf-8"))
        elif all(character in alphabet for character in piece):
            chunks.append(bytes(alphabet[character] for character in piece))
        else:
            return None
    return chunks


def _shown_text(data: bytes, boundaries: list[int], first: int, last: int) -> str:
    """Show bytes first..last: whole characters as text, cut ones as ⟨hex⟩."""
    inner_start: int = boundaries[bisect_left(boundaries, first)]
    inner_end: int = boundaries[bisect_right(boundaries, last) - 1]
    if inner_start >= inner_end:  # No whole character: bytes only.
        return _hex(data[first:last])
    return (
        (_hex(data[first:inner_start]) if first < inner_start else "")
        + data[inner_start:inner_end].decode("utf-8")
        + (_hex(data[inner_end:last]) if inner_end < last else "")
    )


def _hex(chunk: bytes) -> str:
    """Write bytes as ⟨F0 9F⟩."""
    return "⟨" + chunk.hex(" ").upper() + "⟩"


def _describe_by_offsets(loaded: Loaded, text: str, encoding: Encoding) -> list[Token]:
    """Describe tokens with the offsets the tokenizer reports, for other kinds."""
    tokens: list[Token] = []
    for index, (token_id, piece, (start, end)) in enumerate(
        zip(encoding.ids, encoding.tokens, encoding.offsets, strict=True)
    ):
        chunk: bytes = text[start:end].encode("utf-8")
        byte_start: int = len(text[:start].encode("utf-8"))
        tokens.append(
            Token(
                index=index,
                id=token_id,
                piece=piece,
                text=loaded.tokenizer.decode([token_id], skip_special_tokens=False),
                start=start,
                end=end,
                byte_start=byte_start,
                byte_end=byte_start + len(chunk),
                bytes=chunk,
                special=token_id in loaded.special_ids,
                added=token_id in loaded.added_ids,
                partial=False,
            )
        )
    return tokens


_ALPHABET: dict[str, int] = {}


def _byte_alphabet() -> dict[str, int]:
    """Return the byte-level alphabet: each character and the byte it stands for.

    GPT-2 introduced it, and byte-level BPE tokenizers keep it: printable bytes
    stand for themselves, the others are shifted to characters from 256 on,
    e.g. the space, byte 32, to Ġ and the newline, byte 10, to Ċ.
    """
    if not _ALPHABET:
        printable: list[int] = [
            *range(ord("!"), ord("~") + 1),
            *range(0xA1, 0xAC + 1),
            *range(0xAE, 0xFF + 1),
        ]
        shifted: int = 0
        for byte in range(256):
            if byte in printable:
                _ALPHABET[chr(byte)] = byte
            else:
                _ALPHABET[chr(256 + shifted)] = byte
                shifted += 1
    return _ALPHABET
