from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "data" / "plant_host_registry_v1" / "hosts.json"
sys.path.insert(0, str(ROOT))

from services import plant_host_registry as registry


def _payload() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _write_payload(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "hosts.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_loads_exactly_six_plant_hosts_with_stable_order() -> None:
    records = registry.list_hosts()
    assert len(records) == 6
    assert [record["display_order"] for record in records] == [1, 2, 3, 4, 5, 6]
    assert [record["scientific_name"] for record in records] == [
        "Oryza sativa", "Nicotiana benthamiana", "Zea mays",
        "Arabidopsis thaliana", "Solanum lycopersicum", "Glycine max",
    ]
    assert {record["host_id"] for record in records} == {"rice", "tobacco", "maize", "arabidopsis", "tomato", "soybean"}


def test_excludes_nonplant_legacy_names() -> None:
    text = REGISTRY_PATH.read_text(encoding="utf-8").casefold()
    for name in ("agrobacterium", "e. coli", "yeast", "human"):
        assert name not in text


def test_workflow_permissions_and_contains_vector_contract() -> None:
    complete_vector_hosts = registry.hosts_for_workflow(registry.SINGLE_GENE_COMPLETE_VECTOR)
    assert [record["host_id"] for record in complete_vector_hosts] == ["rice", "tomato"]
    for record in registry.list_hosts():
        is_complete_vector_host = record["host_id"] in {"rice", "tomato"}
        assert record["workflow_levels"] == ([registry.SINGLE_GENE_COMPLETE_VECTOR, registry.GENERIC_MULTI_TU_ASSEMBLY] if is_complete_vector_host else [registry.GENERIC_MULTI_TU_ASSEMBLY])
        assert record["workflow_contracts"][registry.GENERIC_MULTI_TU_ASSEMBLY]["contains_vector"] is False
        if not is_complete_vector_host:
            assert registry.SINGLE_GENE_COMPLETE_VECTOR not in record["workflow_levels"]


@pytest.mark.parametrize("mutate", [
    lambda payload: payload["records"].append(copy.deepcopy(payload["records"][0])),
    lambda payload: payload["records"][0].update(workflow_levels=["INVALID"]),
    lambda payload: payload["records"][0].update(plant_scope="bacterium"),
    lambda payload: payload["records"][0]["workflow_contracts"].update({registry.GENERIC_MULTI_TU_ASSEMBLY: {"contains_vector": True}}),
])
def test_invalid_records_fail_strict_validation(tmp_path: Path, mutate) -> None:
    payload = _payload()
    mutate(payload)
    with pytest.raises(registry.PlantHostRegistryError):
        registry.load_registry(_write_payload(tmp_path, payload))


def test_loader_does_not_access_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("SQLite access is forbidden")
    monkeypatch.setattr("sqlite3.connect", fail)
    assert len(registry.list_hosts()) == 6


def test_results_are_defensive_copies() -> None:
    records = registry.list_hosts()
    records[0]["common_name"] = "changed"
    assert registry.list_hosts()[0]["common_name"] == "Rice"
