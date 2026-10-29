"""Fetch a model repository's tokenizer files from Hugging Face, once.

Files land in plain folders, one per repository and commit:
downloads/<owner>--<name>/<40-character commit>/. A commit never changes, so
a folder that holds its files.json is complete and is used offline from then
on: no request goes out, not even to check for updates.

Part of the model: it imports no view and no web framework.
"""

import json
import re
from pathlib import Path
from typing import Protocol

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.errors import (
    GatedRepoError,
    RemoteEntryNotFoundError,
    RepositoryNotFoundError,
    RevisionNotFoundError,
)

# The files a tokenizer needs. tokenizer.json is required; a repository keeps
# its chat template either in chat_template.jinja or in tokenizer_config.json,
# which also names special tokens such as bos_token for the template.
REQUIRED: tuple[str, ...] = ("tokenizer.json",)
OPTIONAL: tuple[str, ...] = ("chat_template.jinja", "tokenizer_config.json")
_MANIFEST: str = "files.json"
_COMMIT: re.Pattern[str] = re.compile(r"[0-9a-f]{40}")


class FetchError(Exception):
    """The files could not be fetched. The message says why, for the user."""


class Fetcher(Protocol):
    """Where the model gets a repository's files from."""

    def resolve(self, repository: str, revision: str) -> str:
        """Return the 40-character commit that revision names.

        Raises:
            FetchError: If the repository or revision cannot be found.
        """
        ...

    def fetch(self, repository: str, commit: str) -> dict[str, Path]:
        """Return the local path of each tokenizer file the commit has.

        Raises:
            FetchError: If a required file is missing or the download fails.
        """
        ...


class HubFetcher:
    """Fetches from huggingface.co into a downloads folder, never with a login."""

    def __init__(self, folder: Path) -> None:
        """Keep downloads in folder, e.g. backend/downloads."""
        self.folder: Path = folder

    def resolve(self, repository: str, revision: str) -> str:
        """Return revision if it is a commit, else ask the Hub which commit."""
        if _COMMIT.fullmatch(revision):
            return revision  # Pinned already: no request needed.
        try:
            commit: str | None = (
                HfApi().model_info(repository, revision=revision, token=False).sha
            )
        except Exception as problem:
            raise FetchError(_explain(problem, repository, revision)) from problem
        if commit is None:
            raise FetchError(f"Hugging Face names no commit for {revision!r}.")
        return commit

    def fetch(self, repository: str, commit: str) -> dict[str, Path]:
        """Download the tokenizer files at commit, or reuse an earlier download."""
        folder: Path = self.folder / repository.replace("/", "--") / commit
        manifest: Path = folder / _MANIFEST
        if manifest.is_file():
            names: list[str] = json.loads(manifest.read_text(encoding="utf-8"))
            if all((folder / name).is_file() for name in names):
                return {name: folder / name for name in names}

        found: dict[str, Path] = {}
        for name in (*REQUIRED, *OPTIONAL):
            try:
                found[name] = Path(
                    hf_hub_download(
                        repository,
                        name,
                        revision=commit,
                        local_dir=folder,
                        token=False,  # Public files: never send a login.
                    )
                )
            except RemoteEntryNotFoundError:  # Only the Hub saying "no such file".
                # Offline, hf_hub_download raises LocalEntryNotFoundError, also an
                # EntryNotFoundError: that is a failure, not a missing file.
                if name in REQUIRED:
                    raise FetchError(
                        f"{repository} has no {name} at {commit[:12]}: "
                        "it is not a model with a Hugging Face tokenizer."
                    ) from None
            except Exception as problem:
                raise FetchError(_explain(problem, repository, commit)) from problem
        # Written last: a folder with a manifest is complete.
        manifest.write_text(json.dumps(sorted(found)), encoding="utf-8")
        return found


def _explain(problem: Exception, repository: str, revision: str) -> str:
    """Turn a Hub failure into a sentence for the user."""
    if isinstance(problem, GatedRepoError):
        return (
            f"{repository} asks you to accept its terms with a Hugging Face "
            "login; this viewer sends none."
        )
    if isinstance(problem, RevisionNotFoundError):
        return f"{repository} has no revision {revision!r}."
    if isinstance(problem, RepositoryNotFoundError):
        return f"There is no public repository {repository!r} on Hugging Face."
    return (
        f"Could not reach Hugging Face for {repository} ({type(problem).__name__}). "
        "Check the internet connection; files downloaded once work offline."
    )
