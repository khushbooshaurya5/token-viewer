"""The model, the controller and the terminal view, without the network.

Two kinds of tests:
- With a small byte-level BPE tokenizer trained here and a short chat
  template: they always run, offline.
- With Nemotron's real files: they run once load_model has downloaded them
  into backend/downloads, and check the known 24 tokens.
"""

import json
from pathlib import Path

import pytest
from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers

from token_viewer.controller import CommandError
from token_viewer.course import (
    COURSE_CHAT_IDS,
    COURSE_REPOSITORY,
    COURSE_REVISION,
)
from token_viewer.hub import HubFetcher
from token_viewer.model import ModelError, TokenModel
from token_viewer.view_models import Message, ViewModel
from token_viewer.viewer_controller import ViewerController
from token_viewer.wiring import DOWNLOADS

CAPTURE: Path = Path(__file__).parent / "data" / "made_up_nvidia_capture.json"
TEMPLATE: str = (
    "{% for m in messages %}<|im_start|>{{ m.role }}\n{{ m.content }}<|im_end|>\n"
    "{% endfor %}{% if add_generation_prompt %}<|im_start|>assistant\n"
    "{% if enable_thinking %}<think>\n{% else %}<think></think>{% endif %}{% endif %}"
)
COMMIT: str = "0" * 40


class LocalFetcher:
    """Hands the model files from a folder, as a finished download would."""

    def __init__(self, files: dict[str, Path]) -> None:
        """Serve these files for every repository."""
        self.files: dict[str, Path] = files

    def resolve(self, repository: str, revision: str) -> str:
        """Pretend every revision is the same commit."""
        return COMMIT

    def fetch(self, repository: str, commit: str) -> dict[str, Path]:
        """Return the files."""
        return self.files


@pytest.fixture(scope="module")
def small_files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Train a tiny byte-level BPE tokenizer with Nemotron's markers."""
    tokenizer: Tokenizer = Tokenizer(models.BPE())
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tokenizer.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(
        vocab_size=400,
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
        special_tokens=["<|im_start|>", "<|im_end|>"],
    )
    tokenizer.train_from_iterator(
        ["Explain tokenization in one sentence."] * 20 + ["user assistant system"],
        trainer,
    )
    tokenizer.add_tokens(["<think>", "</think>"])  # Added, but not special.
    folder: Path = tmp_path_factory.mktemp("small")
    tokenizer.save(str(folder / "tokenizer.json"))
    (folder / "chat_template.jinja").write_text(TEMPLATE, encoding="utf-8")
    return {
        "tokenizer.json": folder / "tokenizer.json",
        "chat_template.jinja": folder / "chat_template.jinja",
    }


@pytest.fixture
def model(small_files: dict[str, Path]) -> TokenModel:
    """A model with the small tokenizer loaded."""
    loaded: TokenModel = TokenModel(LocalFetcher(small_files))
    loaded.load("owner/small", "main")
    return loaded


def test_the_chat_view_is_the_template_text_encoded(model: TokenModel) -> None:
    assert model.view == "chat"
    assert model.text() == (
        "<|im_start|>user\nExplain tokenization in one sentence.<|im_end|>\n"
        "<|im_start|>assistant\n<think></think>"
    )
    tokens = model.tokens()
    assert "".join(token.text for token in tokens) == model.text()
    special: list[str] = [t.text for t in tokens if t.special]
    assert special == ["<|im_start|>", "<|im_end|>", "<|im_start|>"]
    assert [t.text for t in tokens if t.added and not t.special] == [
        "<think>",
        "</think>",
    ]


def test_offsets_count_code_points_and_cover_the_text(model: TokenModel) -> None:
    model.set_messages([("user", "Hi 👋🏽, Äpfel")])
    model.show_view("message-1")
    text: str = model.text()
    data: bytes = text.encode("utf-8")
    tokens = model.tokens()
    assert b"".join(token.bytes for token in tokens) == data
    for token in tokens:
        assert data[token.byte_start : token.byte_end] == token.bytes
        if not token.partial:
            assert text[token.start : token.end] == token.text


def test_a_cut_emoji_is_marked_partial_and_shows_its_bytes(model: TokenModel) -> None:
    model.set_messages([("user", "👋🏽")])
    model.show_view("message-1")
    tokens = model.tokens()
    # Two code points, eight bytes; the small vocabulary has no emoji merges.
    assert len(tokens) > 2
    assert all(token.partial for token in tokens)
    assert all(token.text.startswith("⟨") for token in tokens)
    assert {(token.start, token.end) for token in tokens} <= {(0, 1), (1, 2), (0, 2)}


def test_the_thinking_switch_changes_the_text(model: TokenModel) -> None:
    model.set_template_switches({"enable_thinking": True})
    assert model.text().endswith("<think>\n")


def test_a_refused_operation_changes_nothing(model: TokenModel) -> None:
    model.select(3)
    before: tuple[object, ...] = (model.view, model.selected, model.messages)
    with pytest.raises(ModelError, match="no token 999"):
        model.select(999)
    with pytest.raises(ModelError, match="no view"):
        model.show_view("nope")
    with pytest.raises(ModelError, match="at least one message"):
        model.set_messages([])
    with pytest.raises(ModelError, match="owner/name"):
        model.load("no-slash", "main")
    assert (model.view, model.selected, model.messages) == before


def test_the_selection_stays_only_while_it_names_the_same_token(
    model: TokenModel,
) -> None:
    model.select(0)  # <|im_start|>, the same in every chat.
    model.set_messages([("user", "Something else")])
    assert model.selected == 0
    model.show_view("message-1")
    model.select(0)
    model.set_messages([("user", "Different start")])
    assert model.selected is None


def test_a_capture_adds_its_views_and_counts_prompt_tokens(model: TokenModel) -> None:
    model.load_capture(CAPTURE.name, CAPTURE.read_text(encoding="utf-8"))
    keys: list[str] = [sequence.key for sequence in model.sequences]
    assert keys == ["chat", "message-1", "capture-prompt", "capture-answer"]
    assert model.local_prompt_tokens() == len(model.tokens())  # Same request.
    assert model.capture is not None
    sources: dict[str, str] = {f.label: f.source for f in model.capture.facts()}
    assert sources["Reported model"] == "provider"
    assert sources["Requested model"] == "request"
    assert sources["Provider (derived from the URL)"] == "local"


def test_a_file_that_is_not_a_capture_is_refused(model: TokenModel) -> None:
    with pytest.raises(ModelError, match="not JSON"):
        model.load_capture("x.json", "{")
    with pytest.raises(ModelError, match="not a capture"):
        model.load_capture("package.json", '{"name": "page"}')
    assert model.capture is None


def test_the_controller_turns_refusals_into_command_errors(
    small_files: dict[str, Path],
) -> None:
    controller: ViewerController = ViewerController(
        TokenModel(LocalFetcher(small_files))
    )
    assert controller.view_model().tokenizer is None
    shown: ViewModel = controller.load_model("owner/small", "main")
    assert shown.tokenizer is not None
    assert shown.tokenizer.revision == COMMIT
    shown = controller.set_messages([Message(role="user", content="Hi")])
    assert shown.messages[0].content == "Hi"
    with pytest.raises(CommandError):
        controller.select_token(-1)
    shown = controller.load_capture(CAPTURE.name, CAPTURE.read_text(encoding="utf-8"))
    assert shown.capture is not None
    labels: list[str] = [m.label for m in shown.capture.metadata]
    assert "Prompt tokens, reported minus local" in labels


def test_the_fetcher_reuses_a_finished_download_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder: Path = tmp_path / "owner--name" / COMMIT
    folder.mkdir(parents=True)
    (folder / "tokenizer.json").write_text("{}", encoding="utf-8")
    (folder / "files.json").write_text('["tokenizer.json"]', encoding="utf-8")

    def no_network(*args: object, **kwargs: object) -> str:
        raise AssertionError("no request may go out")

    monkeypatch.setattr("token_viewer.hub.hf_hub_download", no_network)
    fetcher: HubFetcher = HubFetcher(tmp_path)
    assert fetcher.resolve("owner/name", COMMIT) == COMMIT
    assert fetcher.fetch("owner/name", COMMIT) == {
        "tokenizer.json": folder / "tokenizer.json"
    }


# --- With Nemotron's real files -----------------------------------------------

NEMOTRON: Path = DOWNLOADS / COURSE_REPOSITORY.replace("/", "--") / COURSE_REVISION
needs_nemotron = pytest.mark.skipif(
    not (NEMOTRON / "files.json").is_file(),
    reason="Nemotron files not downloaded yet: run uv run token-viewer-terminal",
)


@pytest.fixture
def nemotron() -> TokenModel:
    """The course model, from the earlier download."""
    loaded: TokenModel = TokenModel(HubFetcher(DOWNLOADS))
    loaded.load(COURSE_REPOSITORY, COURSE_REVISION)
    return loaded


@needs_nemotron
def test_the_course_request_gives_the_known_24_tokens(nemotron: TokenModel) -> None:
    assert [token.id for token in nemotron.tokens()] == COURSE_CHAT_IDS
    special: list[int] = [t.index for t in nemotron.tokens() if t.special]
    assert special == [0, 3, 5, 16, 18]  # The markers; role names are not.


@needs_nemotron
def test_nemotron_cuts_the_waving_hand_into_bytes(nemotron: TokenModel) -> None:
    nemotron.set_messages([("user", "Hi 👋🏽 there")])
    nemotron.show_view("message-1")
    partial = [token for token in nemotron.tokens() if token.partial]
    assert len(partial) == 7
    assert b"".join(t.bytes for t in nemotron.tokens()) == "Hi 👋🏽 there".encode()


@needs_nemotron
def test_the_captured_prompt_counts_like_the_report(nemotron: TokenModel) -> None:
    capture: dict[str, object] = json.loads(CAPTURE.read_text(encoding="utf-8"))
    assert isinstance(capture["response"], dict)
    nemotron.load_capture(CAPTURE.name, json.dumps(capture))
    assert nemotron.local_prompt_tokens() == 24
