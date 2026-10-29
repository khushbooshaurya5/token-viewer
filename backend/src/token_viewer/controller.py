"""The controller interface: the commands the views send.

A view turns user input into one of these commands and shows the view-model
the command returns. The controller carries the command out on the model; it
renders nothing. The FastAPI routes in api.py call these commands for the
page, and a terminal view can call them directly.

Yours: write your controller as a subclass of Controller, in a module of your
own in this package, as FakeController does.

Python refuses to create a controller while a command is missing, and names
the command; mypy reports it too.
"""

from abc import ABC, abstractmethod

from token_viewer.view_models import Message, ViewModel


class CommandError(Exception):
    """The controller refused a command, and nothing changed.

    The message says why, in words meant for the user. Any other exception
    from a command is a bug.
    """


class Controller(ABC):
    """The commands of the token viewer. Each returns the new view-model."""

    @abstractmethod
    def view_model(self) -> ViewModel:
        """Return what the views show now, without changing anything."""
        ...

    @abstractmethod
    def load_model(self, repository: str, revision: str) -> ViewModel:
        """Use the tokenizer and chat template of a model repository.

        Args:
            repository: The model repository on Hugging Face, as owner/name.
            revision: The revision to take the files from.
        """
        ...

    @abstractmethod
    def set_messages(self, messages: list[Message]) -> ViewModel:
        """Replace the chat messages whose tokens the views show."""
        ...

    @abstractmethod
    def load_capture(self, name: str, content: str) -> ViewModel:
        """Read a captured provider response.

        Args:
            name: The capture file's name, for display.
            content: The file's content: JSON text, as capture-nvidia-response
                writes it.
        """
        ...

    @abstractmethod
    def select_view(self, key: str) -> ViewModel:
        """Show the tokens of one view, e.g. "chat"."""
        ...

    @abstractmethod
    def select_token(self, index: int) -> ViewModel:
        """Select one token of the current view."""
        ...
