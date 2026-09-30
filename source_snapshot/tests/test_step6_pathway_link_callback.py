from __future__ import annotations

import os
import sys
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.design_session import DesignSession
from services.pathway_wizard_context import PATHWAY_WIZARD_CONTEXT_KEY


class _Recorder:
    def __init__(self):
        self.session_state: dict[str, object] = {}
        self.button_map: dict[str, bool] = {}
        self.button_calls: list[dict[str, object]] = []
        self.multiselect_values: dict[str | None, list[object]] = {}
        self.multiselect_calls: list[dict[str, object]] = []
        self.dataframes: list[object] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.rerun_calls = 0


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeColumn:
    def __init__(self, recorder: _Recorder):
        self.recorder = recorder

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def metric(self, *args, **kwargs):
        return None

    def markdown(self, *args, **kwargs):
        return None

    def button(self, label, **kwargs):
        self.recorder.button_calls.append({"label": label, **kwargs})
        return self.recorder.button_map.get(kwargs.get("key"), False)

    def download_button(self, *args, **kwargs):
        return False


class _FakeStreamlit:
    def __init__(self, recorder: _Recorder):
        self.recorder = recorder
        self.session_state = recorder.session_state

    def cache_data(self, **_cache_kwargs):
        def decorator(func):
            return func
        return decorator

    def columns(self, spec, **kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [_FakeColumn(self.recorder) for _ in range(count)]

    def expander(self, *args, **kwargs):
        return _Context()

    def container(self, *args, **kwargs):
        return _Context()

    def button(self, label, **kwargs):
        self.recorder.button_calls.append({"label": label, **kwargs})
        return self.recorder.button_map.get(kwargs.get("key"), False)

    def divider(self):
        return None

    def caption(self, *args, **kwargs):
        return None

    def markdown(self, *args, **kwargs):
        return None

    def metric(self, *args, **kwargs):
        return None

    def multiselect(self, label, options, default=None, key=None, **kwargs):
        option_list = list(options)
        default_list = list(default or [])
        self.recorder.multiselect_calls.append(
            {"label": label, "options": option_list, "default": default_list, "key": key, **kwargs}
        )
        if key in self.recorder.multiselect_values:
            return self.recorder.multiselect_values[key]
        return [value for value in default_list if value in option_list]

    def dataframe(self, data, **kwargs):
        self.recorder.dataframes.append({"data": data, **kwargs})
        return None

    def warning(self, body, **kwargs):
        self.recorder.warnings.append(str(body))

    def error(self, body, **kwargs):
        self.recorder.errors.append(str(body))

    def rerun(self):
        self.recorder.rerun_calls += 1


class _FakeController:
    def __init__(self, ds: DesignSession):
        self._ds = ds

    def get(self) -> DesignSession:
        return self._ds


def _ds() -> DesignSession:
    return DesignSession(
        step=6,
        gene_name="demo_gene",
        original_seq="ATG" + "AAA" * 20 + "TAA",
        optimized_seq="ATG" + "GCC" * 20 + "TAA",
        host="E.coli BL21(DE3)",
        tag="No tag",
        elements={"promoter_name": "T7 promoter"},
        frame={
            "success": True,
            "final_sequence": "ATG" + "GCC" * 20 + "TAA",
            "total_length": 66,
            "gc_content": 64.0,
        },
        primers=[{"Fragment Name": "Expression frame", "Quality Grade": "Recommended"}],
        validation_results=[],
        validation_context_signature="completed",
    )


def _install_step6(monkeypatch, recorder: _Recorder, save_result=(True, "Saved Design"), link_result=None):
    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    import views.wizard_steps.step6_export as step6

    monkeypatch.setattr(step6, "st", fake_st)
    monkeypatch.setattr(step6, "_step_header", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6, "_section_label", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6, "_status_panel", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6, "_render_export_risk_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6, "_review_panel", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6, "_render_step6_report_display", lambda *args, **kwargs: None)

    export_payload = {
        "sequence": "ATG" + "GCC" * 20 + "TAA",
        "has_sequence": True,
        "payloads": {},
        "plasmid_map_features": [],
        "plasmid_map_title": "Demo map",
        "png_filename": "demo.png",
        "report": {},
        "safe_name": "demo",
    }
    fake_export_manager = types.SimpleNamespace(
        build_design_session_export_payload=lambda ds: export_payload,
        build_export_manifest=lambda **kwargs: {},
        build_export_manifest_payload=lambda manifest, safe_name: None,
    )
    monkeypatch.setitem(sys.modules, "components.export_manager", fake_export_manager)
    monkeypatch.setitem(
        sys.modules,
        "services.design_saver",
        types.SimpleNamespace(save_wizard_design=lambda ds: save_result),
    )

    link_calls = []

    def fake_link(ds, **kwargs):
        link_calls.append(kwargs)
        if link_result is not None:
            return link_result
        context = recorder.session_state.get(PATHWAY_WIZARD_CONTEXT_KEY)
        if isinstance(context, dict) and context.get("status") == "active":
            context = dict(context)
            context["status"] = "linked"
            context["linked_design_name"] = kwargs.get("saved_design_name")
            recorder.session_state[PATHWAY_WIZARD_CONTEXT_KEY] = context
            return True, "Linked.", True
        return True, "No active pathway context; no pathway link was created.", False

    def fake_get_context():
        context = recorder.session_state.get(PATHWAY_WIZARD_CONTEXT_KEY)
        return context if isinstance(context, dict) else {}

    def fake_clear_context():
        recorder.session_state.pop(PATHWAY_WIZARD_CONTEXT_KEY, None)

    monkeypatch.setitem(
        sys.modules,
        "services.pathway_wizard_context",
        types.SimpleNamespace(
            clear_pathway_wizard_context=fake_clear_context,
            get_pathway_wizard_context=fake_get_context,
            has_active_pathway_wizard_context=lambda: isinstance(
                recorder.session_state.get(PATHWAY_WIZARD_CONTEXT_KEY), dict
            ) and recorder.session_state[PATHWAY_WIZARD_CONTEXT_KEY].get("source") == "pathway_workspace"
            and recorder.session_state[PATHWAY_WIZARD_CONTEXT_KEY].get("status") == "active",
            link_saved_design_to_active_pathway_context=fake_link,
        ),
    )
    return step6, link_calls


def test_step6_independent_wizard_save_does_not_create_pathway_link(monkeypatch):
    recorder = _Recorder()
    recorder.button_map["wf_p6_save"] = True
    step6, link_calls = _install_step6(monkeypatch, recorder)

    step6.page(_FakeController(_ds()))

    assert link_calls == []
    assert PATHWAY_WIZARD_CONTEXT_KEY not in recorder.session_state
    assert recorder.session_state["wf_p6_saved_name"] == "Saved Design"
    assert recorder.rerun_calls == 1


def test_step6_active_context_links_only_after_dashboard_save_success(monkeypatch):
    recorder = _Recorder()
    recorder.button_map["wf_p6_save"] = True
    recorder.session_state[PATHWAY_WIZARD_CONTEXT_KEY] = {
        "source": "pathway_workspace",
        "status": "active",
        "project_id": 1,
        "step_id": 2,
    }
    step6, link_calls = _install_step6(monkeypatch, recorder)

    step6.page(_FakeController(_ds()))

    assert len(link_calls) == 1
    assert link_calls[0]["saved_design_name"] == "Saved Design"
    assert recorder.session_state[PATHWAY_WIZARD_CONTEXT_KEY]["status"] == "linked"
    assert recorder.session_state[PATHWAY_WIZARD_CONTEXT_KEY]["linked_design_name"] == "Saved Design"
    assert recorder.session_state["wf_p6_saved_name"] == "Saved Design"


def test_step6_linked_context_shows_return_action_and_clears_context_on_return(monkeypatch):
    recorder = _Recorder()
    recorder.button_map["wf_p6_return_pathway"] = True
    recorder.session_state["wf_p6_saved_name"] = "Saved Design"
    recorder.session_state[PATHWAY_WIZARD_CONTEXT_KEY] = {
        "source": "pathway_workspace",
        "status": "linked",
        "project_id": 1,
        "step_id": 2,
        "linked_design_name": "Saved Design",
    }
    step6, _link_calls = _install_step6(monkeypatch, recorder)

    step6.page(_FakeController(_ds()))

    labels = [call["label"] for call in recorder.button_calls]
    assert "Return to Pathway Workspace" in labels
    assert "Open dashboard" in labels
    assert recorder.session_state["selected_page"] == "Pathway Workspace"
    assert PATHWAY_WIZARD_CONTEXT_KEY not in recorder.session_state
    assert recorder.rerun_calls == 1


def test_step6_dashboard_save_failure_does_not_call_pathway_link(monkeypatch):
    recorder = _Recorder()
    recorder.button_map["wf_p6_save"] = True
    recorder.session_state[PATHWAY_WIZARD_CONTEXT_KEY] = {
        "source": "pathway_workspace",
        "status": "active",
        "project_id": 1,
        "step_id": 2,
    }
    step6, link_calls = _install_step6(monkeypatch, recorder, save_result=(False, "Save failed."))

    step6.page(_FakeController(_ds()))

    assert link_calls == []
    assert recorder.session_state[PATHWAY_WIZARD_CONTEXT_KEY]["status"] == "active"
    assert recorder.errors == ["Save failed: Save failed."]


def test_step6_link_failure_preserves_context_and_shows_warning(monkeypatch):
    recorder = _Recorder()
    recorder.button_map["wf_p6_save"] = True
    context = {
        "source": "pathway_workspace",
        "status": "active",
        "project_id": 1,
        "step_id": 2,
    }
    recorder.session_state[PATHWAY_WIZARD_CONTEXT_KEY] = context
    step6, link_calls = _install_step6(
        monkeypatch,
        recorder,
        link_result=(False, "Repository unavailable.", True),
    )

    step6.page(_FakeController(_ds()))

    assert len(link_calls) == 1
    assert recorder.session_state[PATHWAY_WIZARD_CONTEXT_KEY] == context
    assert recorder.session_state["pathway_link_warning"] == "Repository unavailable."
    assert recorder.warnings == [
        "Design was saved to the dashboard, but pathway linking failed: Repository unavailable."
    ]


def test_step6_unsaved_start_new_design_clears_active_pathway_context(monkeypatch):
    recorder = _Recorder()
    recorder.button_map["wf_p6_reset"] = True
    recorder.session_state[PATHWAY_WIZARD_CONTEXT_KEY] = {
        "source": "pathway_workspace",
        "status": "active",
        "project_id": 1,
        "step_id": 2,
    }
    step6, _link_calls = _install_step6(monkeypatch, recorder)

    step6.page(_FakeController(_ds()))

    assert PATHWAY_WIZARD_CONTEXT_KEY not in recorder.session_state


def test_step6_saved_start_new_design_clears_linked_pathway_context(monkeypatch):
    recorder = _Recorder()
    recorder.button_map["wf_p6_reset"] = True
    recorder.session_state["wf_p6_saved_name"] = "Saved Design"
    recorder.session_state[PATHWAY_WIZARD_CONTEXT_KEY] = {
        "source": "pathway_workspace",
        "status": "linked",
        "project_id": 1,
        "step_id": 2,
        "linked_design_name": "Saved Design",
    }
    step6, _link_calls = _install_step6(monkeypatch, recorder)

    step6.page(_FakeController(_ds()))

    assert PATHWAY_WIZARD_CONTEXT_KEY not in recorder.session_state
