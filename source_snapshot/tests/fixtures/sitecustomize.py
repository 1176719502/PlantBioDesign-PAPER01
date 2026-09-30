"""Process-local Registry UI demo hook used only with this fixture directory on PYTHONPATH."""

from pathlib import Path
import sys

repository_root = Path(__file__).resolve().parents[2]
if str(repository_root) not in sys.path:
    sys.path.insert(0, str(repository_root))
from services import plant_component_workflow_registry


plant_component_workflow_registry.REGISTRY_PATH = Path(__file__).with_name(
    "registry_v1_ui_demo.json"
)
