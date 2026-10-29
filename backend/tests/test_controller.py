"""The controller interface: an incomplete controller fails at startup."""

import pytest

from token_viewer.controller import Controller
from token_viewer.fake_controller import FakeController
from token_viewer.view_models import ViewModel


def test_a_controller_that_misses_a_command_cannot_be_created() -> None:
    class Incomplete(Controller):
        """Has view_model, and none of the other commands."""

        def view_model(self) -> ViewModel:
            """Show what the fake shows."""
            return FakeController().view_model()

    # build_controller() runs when uvicorn imports api.py: the back end does
    # not start, rather than answer 500 at the first click.
    with pytest.raises(TypeError, match="select_token"):
        Incomplete()  # type: ignore[abstract]
