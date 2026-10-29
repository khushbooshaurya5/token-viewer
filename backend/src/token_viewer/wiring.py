"""Which controller the views use: the one place to plug in your own.

The web back end and a terminal view each run in a process of their own. Each
calls build_controller() once, so both use the same classes, each with its own
state.
"""

from pathlib import Path

from token_viewer.controller import Controller
from token_viewer.hub import HubFetcher
from token_viewer.model import TokenModel
from token_viewer.viewer_controller import ViewerController

# backend/downloads: model files, kept out of Git by backend/.gitignore.
DOWNLOADS: Path = Path(__file__).resolve().parents[2] / "downloads"


def build_controller() -> Controller:
    """Return a new controller, with its model."""
    # Importing api.py calls this, and the route tests import api.py: keep it
    # quick and offline. Files are fetched when the load_model command runs.
    return ViewerController(TokenModel(HubFetcher(DOWNLOADS)))
