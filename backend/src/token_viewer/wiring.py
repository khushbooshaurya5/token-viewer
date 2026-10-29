"""Which controller the views use: the one place to plug in your own.

The web back end and a terminal view each run in a process of their own. Each
calls build_controller() once, so both use the same classes, each with its own
state.
"""

from token_viewer.controller import Controller
from token_viewer.fake_controller import FakeController


def build_controller() -> Controller:
    """Return a new controller, with its model."""
    # Importing api.py calls this, and the route tests import api.py: keep it
    # quick and offline. Download files when the load_model command runs, not
    # here.
    # Yours: replace FakeController() with your own controller, built on your
    # model, both in modules of your own in this package.
    return FakeController()
