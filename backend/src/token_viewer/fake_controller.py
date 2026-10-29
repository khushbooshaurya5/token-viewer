"""A fake controller with made-up data, so that everything runs from day one.

It lets you try the page, the proxy, the generated TypeScript types and the
debugger before your model exists. No tokenizer runs here: every token below
is made up, and the tokens never change. Keep this file when your own
controller works: the route tests use it. So it must grow with the contract:
when you add a command to Controller or a field to a view-model, add it here
too, or the route tests fail.

A controller keeps no state and no rules of its own; both live in the model.
To show that split, the fake comes with a small stand-in model, _FakeModel.
It holds the made-up data and refuses what breaks its rules. FakeController
checks each command, calls one model operation, turns a refusal into a
CommandError and builds the view-model.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias

from token_viewer.controller import CommandError, Controller
from token_viewer.view_models import (
    CaptureView,
    Message,
    TokenizerView,
    TokenView,
    ViewModel,
    ViewOption,
)

# One made-up token: ID, piece, text, start, end, special.
_MadeUpToken: TypeAlias = tuple[int, str, str, int, int, bool]


@dataclass(frozen=True)
class _MadeUpView:
    """The made-up text and tokens of one view."""

    title: str
    text: str
    tokens: list[_MadeUpToken]


# The stand-in model's data: only _FakeModel reads it.
_MADE_UP_VIEWS: dict[str, _MadeUpView] = {
    "chat": _MadeUpView(
        title="Chat, after a made-up template",
        text="<fake>Show me fake tokens.</fake>",
        tokens=[
            (1, "<fake>", "<fake>", 0, 6, True),
            (2, "Show", "Show", 6, 10, False),
            (3, "_me", " me", 10, 13, False),
            (4, "_fake", " fake", 13, 18, False),
            (5, "_tokens", " tokens", 18, 25, False),
            (6, ".", ".", 25, 26, False),
            (7, "</fake>", "</fake>", 26, 33, True),
        ],
    ),
    "text": _MadeUpView(
        title="Text alone",
        text="Show me fake tokens.",
        tokens=[
            (2, "Show", "Show", 0, 4, False),
            (3, "_me", " me", 4, 7, False),
            (4, "_fake", " fake", 7, 12, False),
            (5, "_tokens", " tokens", 12, 19, False),
            (6, ".", ".", 19, 20, False),
        ],
    ),
}

_MADE_UP_ANSWER: str = "A made-up answer: the fake controller does not read the file."


class _FakeModelError(Exception):
    """The stand-in model refused an operation and kept its state.

    The message says why, in words meant for the user. Your model raises an
    exception of its own like this one, and your controller turns it into a
    CommandError, so the model never imports controller.py.
    """


class _FakeModel:
    """A stand-in for your model: the made-up data and the rules that guard it.

    Read its attributes; change them only through its operations. Each
    operation checks its rule before it changes anything, so a refused
    operation changes nothing. A real operation computes the new state first,
    e.g. the new tokens, and assigns it last, for the same reason. Like a real
    model, it knows nothing of view-models or of the controller.
    """

    def __init__(self) -> None:
        """Start with one made-up message and the chat view."""
        self.repository: str = "fake/example"
        self.revision: str = "fake"
        self.messages: list[tuple[str, str]] = [("user", "Show me fake tokens.")]
        self.view: str = "chat"  # The key of the view shown.
        self.selected: int | None = None  # A token's index in that view.
        self.capture_name: str | None = None
        self.capture_answer: str | None = None

    def views(self) -> list[tuple[str, str]]:
        """Return the key and the title of every view."""
        return [(key, made_up.title) for key, made_up in _MADE_UP_VIEWS.items()]

    def text(self) -> str:
        """Return the text of the view shown."""
        return _MADE_UP_VIEWS[self.view].text

    def tokens(self) -> list[_MadeUpToken]:
        """Return the tokens of the view shown."""
        return _MADE_UP_VIEWS[self.view].tokens

    def choose(self, repository: str, revision: str) -> None:
        """Remember the repository and revision; the tokens stay made up."""
        self.repository = repository
        self.revision = revision

    def set_messages(self, messages: list[tuple[str, str]]) -> None:
        """Replace the messages, as pairs of role and content.

        The made-up tokens stay, and so the selection stays valid. Your
        model's tokens change with the messages: keep the selection only
        while its index still names the same token.
        """
        self.messages = messages

    def set_capture(self, name: str) -> None:
        """Remember a capture's name, with a made-up answer."""
        self.capture_name = name
        self.capture_answer = _MADE_UP_ANSWER

    def show_view(self, key: str) -> None:
        """Show another view, and clear the selection.

        The selection is an index into the old view's tokens: in another view
        it would name another token, or none.

        Raises:
            _FakeModelError: If there is no view with this key.
        """
        if key not in _MADE_UP_VIEWS:
            raise _FakeModelError(f"There is no view {key!r}.")
        self.view = key
        self.selected = None

    def select(self, index: int) -> None:
        """Select one token of the view shown.

        Raises:
            _FakeModelError: If the view has no token with this index.
        """
        count: int = len(self.tokens())
        if not 0 <= index < count:
            raise _FakeModelError(
                f"There is no token {index}: this view has {count}, numbered from 0."
            )
        self.selected = index


class FakeController(Controller):
    """Carries out every command as one operation on the stand-in model."""

    def __init__(self) -> None:
        """Start with a new stand-in model."""
        self._model: _FakeModel = _FakeModel()

    def view_model(self) -> ViewModel:
        """Build the view-model from the stand-in model's state."""
        # Yours: when you add a field to a view-model, give it a made-up value
        # here too, or the route tests fail.
        model: _FakeModel = self._model
        tokens: list[TokenView] = [
            TokenView(
                index=index,
                id=token_id,
                piece=piece,
                text=text,
                start=start,
                end=end,
                special=special,
            )
            for index, (token_id, piece, text, start, end, special) in enumerate(
                model.tokens()
            )
        ]
        capture: CaptureView | None = None
        if model.capture_name is not None:
            capture = CaptureView(
                name=model.capture_name, answer=model.capture_answer, reasoning=None
            )
        return ViewModel(
            tokenizer=TokenizerView(
                repository=model.repository, revision=model.revision
            ),
            notice="Made-up data from the fake controller: no tokenizer has run.",
            messages=[
                Message(role=role, content=content) for role, content in model.messages
            ],
            views=[ViewOption(key=key, title=title) for key, title in model.views()],
            current_view=model.view,
            text=model.text(),
            tokens=tokens,
            # The model keeps this index valid: select checks it, and
            # show_view clears it.
            selected=None if model.selected is None else tokens[model.selected],
            capture=capture,
        )

    def load_model(self, repository: str, revision: str) -> ViewModel:
        """Show the repository and revision; the tokens stay made up."""
        if not repository.strip() or not revision.strip():
            raise CommandError("Give both a repository and a revision.")
        return self._carry_out(lambda: self._model.choose(repository, revision))

    def set_messages(self, messages: list[Message]) -> ViewModel:
        """Show the messages; the tokens stay made up."""
        if not messages:
            raise CommandError("Give at least one message.")
        pairs: list[tuple[str, str]] = [(m.role, m.content) for m in messages]
        return self._carry_out(lambda: self._model.set_messages(pairs))

    def load_capture(self, name: str, content: str) -> ViewModel:
        """Show the file's name with a made-up answer; the content is not read."""
        return self._carry_out(lambda: self._model.set_capture(name))

    def select_view(self, key: str) -> ViewModel:
        """Show another view; the model clears the selection."""
        return self._carry_out(lambda: self._model.show_view(key))

    def select_token(self, index: int) -> ViewModel:
        """Select one token of the current view."""
        return self._carry_out(lambda: self._model.select(index))

    def _carry_out(self, operation: Callable[[], None]) -> ViewModel:
        """Run one model operation and return the new view-model.

        Raises:
            CommandError: If the model refused; then nothing changed.
        """
        try:
            operation()
        except _FakeModelError as refusal:
            raise CommandError(str(refusal)) from refusal
        return self.view_model()
