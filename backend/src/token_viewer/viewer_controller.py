"""The token viewer's controller: commands carried out on TokenModel.

Each command checks its arguments, runs one model operation, turns the
model's refusal into a CommandError and returns the new view-model. The
controller keeps no state of its own: all of it lives in the model. It renders
nothing either; the page and the terminal view decide how things look.
"""

from collections.abc import Callable

from token_viewer.capture import Capture
from token_viewer.controller import CommandError, Controller
from token_viewer.course import COURSE_REPOSITORY, COURSE_REVISION
from token_viewer.model import ModelError, Sequence, Token, TokenModel
from token_viewer.view_models import (
    CaptureView,
    Message,
    MetadataView,
    TokenizerView,
    TokenView,
    ViewModel,
    ViewOption,
)


class ViewerController(Controller):
    """Carries out every command as one operation on a TokenModel."""

    def __init__(self, model: TokenModel) -> None:
        """Work on model, which holds all the state."""
        self._model: TokenModel = model

    def view_model(self) -> ViewModel:
        """Build the view-model from the model's state."""
        model: TokenModel = self._model
        tokens: list[TokenView] = [_token_view(token) for token in model.tokens()]
        tokenizer: TokenizerView | None = None
        if model.loaded is not None:
            tokenizer = TokenizerView(
                repository=model.loaded.repository, revision=model.loaded.commit
            )
        return ViewModel(
            tokenizer=tokenizer,
            notice=self._notice(),
            messages=[
                Message(role=role, content=content) for role, content in model.messages
            ],
            template_switches=dict(model.template_switches),
            views=[
                ViewOption(key=sequence.key, title=sequence.title)
                for sequence in model.sequences
            ],
            current_view=model.view,
            text=model.text(),
            tokens=tokens,
            # The model keeps this index valid: select checks it, and every
            # change of the tokens clears or rechecks it.
            selected=None if model.selected is None else tokens[model.selected],
            capture=self._capture_view(),
        )

    def load_model(self, repository: str, revision: str) -> ViewModel:
        """Fetch the repository's tokenizer files, once, and use them."""
        return self._carry_out(lambda: self._model.load(repository, revision))

    def set_messages(self, messages: list[Message]) -> ViewModel:
        """Replace the messages whose tokens the views show."""
        pairs: list[tuple[str, str]] = [(m.role, m.content) for m in messages]
        return self._carry_out(lambda: self._model.set_messages(pairs))

    def set_template_switches(self, switches: dict[str, bool]) -> ViewModel:
        """Replace the chat template's switches."""
        return self._carry_out(lambda: self._model.set_template_switches(switches))

    def load_capture(self, name: str, content: str) -> ViewModel:
        """Read a capture; its texts appear as views, re-tokenized."""
        return self._carry_out(lambda: self._model.load_capture(name, content))

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
        except ModelError as refusal:
            raise CommandError(str(refusal)) from refusal
        return self.view_model()

    def _notice(self) -> str:
        """Say what the tokens are, or how to get some."""
        current: Sequence | None = self._model.current()
        if current is not None:
            return f"{current.note} {len(current.tokens)} tokens."
        if self._model.loaded is not None:
            return "This repository has no chat template; choose a text view."
        return (
            "No model loaded yet. For the course request, load "
            f"{COURSE_REPOSITORY} at revision {COURSE_REVISION}."
        )

    def _capture_view(self) -> CaptureView | None:
        """Show the capture's texts and metadata, local and reported side by side."""
        capture: Capture | None = self._model.capture
        if capture is None:
            return None
        metadata: list[MetadataView] = [
            MetadataView(label=fact.label, value=fact.value, source=fact.source)
            for fact in capture.facts()
        ]
        local: int | None = self._model.local_prompt_tokens()
        reported: int | None = capture.reported_prompt_tokens
        if local is not None and self._model.loaded is not None:
            counted_with: str = self._model.loaded.repository
            metadata.append(
                MetadataView(
                    label=f"Prompt tokens, counted locally ({counted_with})",
                    value=str(local),
                    source="local",
                )
            )
        if reported is not None:
            metadata.append(
                MetadataView(
                    label="Prompt tokens, reported",
                    value=str(reported),
                    source="provider",
                )
            )
        if local is not None and reported is not None:
            difference: int = reported - local
            metadata.append(
                MetadataView(
                    label="Prompt tokens, reported minus local",
                    value=f"{difference:+d}" if difference else "0 (they agree)",
                    source="local",
                )
            )
        return CaptureView(
            name=capture.name,
            answer=capture.answer,
            reasoning=capture.reasoning,
            metadata=metadata,
        )


def _token_view(token: Token) -> TokenView:
    """Shape one token for the views."""
    return TokenView(
        index=token.index,
        id=token.id,
        piece=token.piece,
        text=token.text,
        start=token.start,
        end=token.end,
        byte_start=token.byte_start,
        byte_end=token.byte_end,
        bytes=token.bytes.hex(" ").upper(),
        special=token.special,
        added=token.added,
        partial=token.partial,
    )
