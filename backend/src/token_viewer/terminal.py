"""The terminal view: the same controller and model as the page, in a terminal.

Run from the backend folder:
    uv run token-viewer-terminal
    uv run token-viewer-terminal --messages ../course_messages.json --select 9
    uv run token-viewer-terminal --text "Hi 👋🏽" --view message-1
    uv run token-viewer-terminal --capture nvidia_capture.json --view capture-answer

Like the page, it is a view: it turns its arguments into controller commands
and prints the view-model each command returns. It imports no tokenizer
library and decides nothing about tokens; it only decides how they look.
"""

import argparse
import io
import json
import sys
from pathlib import Path

from token_viewer.controller import CommandError, Controller
from token_viewer.course import COURSE_REPOSITORY, COURSE_REVISION
from token_viewer.view_models import Message, TokenView, ViewModel
from token_viewer.wiring import build_controller

# How invisible characters look in the table.
_VISIBLE: dict[int, str] = {ord("\n"): "\\n", ord("\r"): "\\r", ord("\t"): "\\t"}


def main() -> None:
    """Send the commands the arguments ask for, then print the view-model."""
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows: print Ġ and emoji.
    arguments: argparse.Namespace = _parser().parse_args()
    controller: Controller = build_controller()
    try:
        shown: ViewModel = _run(controller, arguments)
    except CommandError as refusal:
        raise SystemExit(f"Refused: {refusal}") from None
    except (OSError, ValueError) as problem:
        raise SystemExit(f"Could not read a file: {problem}") from None
    _print(shown)


def _parser() -> argparse.ArgumentParser:
    """Describe the arguments."""
    parser = argparse.ArgumentParser(
        prog="token-viewer-terminal",
        description="Show the tokens a model reads for chat messages.",
    )
    parser.add_argument("--repository", default=COURSE_REPOSITORY)
    parser.add_argument("--revision", default=COURSE_REVISION)
    messages = parser.add_mutually_exclusive_group()
    messages.add_argument(
        "--messages",
        type=Path,
        help="a JSON file with chat messages, e.g. samples/course_messages.json",
    )
    messages.add_argument("--text", help="one user message, given here")
    parser.add_argument(
        "--thinking",
        choices=("on", "off"),
        help="the chat template switch enable_thinking (default: off, as the "
        "course request)",
    )
    parser.add_argument("--capture", type=Path, help="a capture-nvidia-response file")
    parser.add_argument("--view", help="the view to show, e.g. message-1")
    parser.add_argument("--select", type=int, help="the index of a token to detail")
    return parser


def _run(controller: Controller, arguments: argparse.Namespace) -> ViewModel:
    """Send one command per argument given, in a fixed order."""
    shown: ViewModel = controller.load_model(arguments.repository, arguments.revision)
    if arguments.messages is not None:
        data: object = json.loads(arguments.messages.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"{arguments.messages} holds no list of messages")
        shown = controller.set_messages([Message.model_validate(m) for m in data])
    elif arguments.text is not None:
        shown = controller.set_messages([Message(role="user", content=arguments.text)])
    if arguments.thinking is not None:
        shown = controller.set_template_switches(
            {"enable_thinking": arguments.thinking == "on"}
        )
    if arguments.capture is not None:
        shown = controller.load_capture(
            arguments.capture.name, arguments.capture.read_text(encoding="utf-8")
        )
    if arguments.view is not None:
        shown = controller.select_view(arguments.view)
    if arguments.select is not None:
        shown = controller.select_token(arguments.select)
    return shown


def _print(shown: ViewModel) -> None:
    """Print the view-model: source, views, tokens, selection and capture."""
    if shown.tokenizer is not None:
        print(
            f"Model: {shown.tokenizer.repository}, revision {shown.tokenizer.revision}"
        )
    if shown.notice:
        print(shown.notice)
    switches: str = ", ".join(f"{k}={v}" for k, v in shown.template_switches.items())
    print(f"Template switches: {switches or 'none'}")
    print("Views:")
    for option in shown.views:
        mark: str = "*" if option.key == shown.current_view else " "
        print(f"  {mark} {option.key:<18} {option.title}")
    print(f"\nText of this view:\n  {shown.text!r}\n")

    header: str = f"{'#':>3}  {'ID':>6}  {'vocabulary entry':<18} {'text':<14}"
    print(f"  {header} {'chars':>7}  notes")
    for token in shown.tokens:
        print(
            f"  {token.index:>3}  {token.id:>6}  {token.piece:<18} "
            f"{_visible(token.text):<14} {f'{token.start}-{token.end}':>7}  "
            f"{_notes(token)}"
        )
    special: int = sum(token.special for token in shown.tokens)
    partial: int = sum(token.partial for token in shown.tokens)
    print(f"\n{len(shown.tokens)} tokens: {special} special, {partial} partial.")

    if shown.selected is not None:
        print("\nSelected token:")
        for name, value in shown.selected.model_dump().items():
            print(f"  {name:<10} {value!r}")

    if shown.capture is not None:
        print(f"\nCapture {shown.capture.name}:")
        for source in ("request", "provider", "local"):
            facts = [m for m in shown.capture.metadata if m.source == source]
            if facts:
                print(f"  {source}:")
                for fact in facts:
                    print(f"    {fact.label}: {fact.value}")


def _visible(text: str) -> str:
    """Show newlines and tabs as escapes, and the rest as it is."""
    return text.translate(_VISIBLE)


def _notes(token: TokenView) -> str:
    """Mark special, added and partial tokens."""
    notes: list[str] = []
    if token.special:
        notes.append("special")
    elif token.added:
        notes.append("added")
    if token.partial:
        notes.append(f"partial, bytes {token.bytes}")
    return ", ".join(notes)


if __name__ == "__main__":
    main()
