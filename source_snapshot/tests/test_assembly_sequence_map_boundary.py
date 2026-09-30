from __future__ import annotations

import os
import sys
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.session_keys import SK


class _Recorder:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.dataframes: list[str] = []

    def add(self, *values) -> None:
        for value in values:
            if value is not None:
                self.texts.append(str(value))

    def add_dataframe(self, value) -> None:
        try:
            rendered = value.to_string(index=False)
        except Exception:
            rendered = str(value)
        self.dataframes.append(rendered)
        self.texts.append(rendered)

    def joined(self) -> str:
        return "\n".join(self.texts)


class _ContextColumn:
    def __init__(self, fake_st: "_FakeStreamlit") -> None:
        self._fake_st = fake_st

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __getattr__(self, name: str):
        return getattr(self._fake_st, name)


class _FakeStreamlit:
    def __init__(self, recorder: _Recorder) -> None:
        self.recorder = recorder
        self.session_state: dict[str, object] = {}
        self.column_config = types.SimpleNamespace(
            NumberColumn=lambda *args, **kwargs: types.SimpleNamespace(args=args, kwargs=kwargs)
        )

    def markdown(self, body, **kwargs):
        self.recorder.add(body)

    def caption(self, body, **kwargs):
        self.recorder.add(body)

    def info(self, body, **kwargs):
        self.recorder.add(body)

    def error(self, body, **kwargs):
        self.recorder.add(body)

    def warning(self, body, **kwargs):
        self.recorder.add(body)

    def metric(self, label, value, *args, **kwargs):
        self.recorder.add(label, value)

    def code(self, body, **kwargs):
        self.recorder.add(body)

    def dataframe(self, value, **kwargs):
        self.recorder.add_dataframe(value)

    def divider(self):
        return None

    def columns(self, spec, **kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [_ContextColumn(self) for _ in range(count)]

    def expander(self, label, **kwargs):
        self.recorder.add(label)
        return _ContextColumn(self)

    def text_area(self, label, value="", **kwargs):
        self.recorder.add(label, kwargs.get("placeholder"))
        return value

    def text_input(self, label, value="", **kwargs):
        self.recorder.add(label)
        return value

    def radio(self, label, options, index=0, **kwargs):
        self.recorder.add(label)
        return options[index]

    def checkbox(self, label, value=False, **kwargs):
        self.recorder.add(label)
        return value

    def multiselect(self, label, options, default=None, **kwargs):
        self.recorder.add(label)
        return list(default or [])


def test_feature_readback_rows_frame_documentation_follow_up() -> None:
    from components.assembly_modules import tab_plasmid_map

    rows = tab_plasmid_map._build_feature_readback_rows(
        [
            {
                "label": "T7 promoter",
                "type": "promoter",
                "strand": 1,
                "source_record_label": "Component Library source note",
                "review_status": "Documentation review recorded",
            },
            {
                "label": "Reverse tag",
                "type": "tag",
                "strand": -1,
            },
        ]
    )

    assert rows[0]["Feature name"] == "T7 promoter"
    assert rows[0]["Feature type"] == "Promoter"
    assert rows[0]["Source/provenance status"] == "Component Library source note"
    assert rows[0]["Direction/orientation"] == "forward"
    assert rows[0]["Manual follow-up status"] == "Documentation review recorded"
    assert rows[1]["Direction/orientation"] == "reverse"
    assert rows[1]["Source/provenance status"] == "Source/provenance status not recorded"
    assert rows[1]["Manual follow-up status"] == "Manual documentation follow-up"
    assert rows[1]["Missing documentation cue"] == "Missing documentation cue: source/provenance, manual review"

    rendered = str(rows).lower()
    for unsafe in [
        "sequence verified",
        "cloning-ready",
        "validated construct",
        "recommended vector",
        "wet-lab ready",
        "optimized design",
    ]:
        assert unsafe not in rendered


def test_sequence_map_missing_features_shows_follow_up_state(monkeypatch) -> None:
    from components.assembly_modules import tab_plasmid_map

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    fake_st.session_state[SK.PROJECT_NAME] = "Demo construct"
    fake_st.session_state[SK.ACTIVE_SEQ] = "ATG" + ("GCC" * 12) + "TAA"
    fake_st.session_state[SK.FEATURES] = []

    render_calls: list[object] = []
    monkeypatch.setattr(tab_plasmid_map, "st", fake_st)
    monkeypatch.setattr(tab_plasmid_map, "_auto_detect_features", lambda seq: [])
    monkeypatch.setattr(tab_plasmid_map, "render_plasmid_map", lambda **kwargs: render_calls.append(kwargs))

    tab_plasmid_map.render()

    rendered = recorder.joined().lower()
    assert "sequence documentation preview" in rendered
    assert "no documented features were found" in rendered
    assert "manual documentation follow-up" in rendered
    assert "map rendering is paused because required feature documentation is missing" in rendered
    assert "not sequence verification" in rendered
    assert "not cloning feasibility verification" in rendered
    assert "not experimental readiness approval" in rendered
    assert render_calls == []


def test_sequence_map_with_features_keeps_renderer_available(monkeypatch) -> None:
    from components.assembly_modules import tab_plasmid_map

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    sequence = "ATG" + ("GCC" * 12) + "TAA"
    fake_st.session_state[SK.PROJECT_NAME] = "Demo construct"
    fake_st.session_state[SK.ACTIVE_SEQ] = sequence
    fake_st.session_state[SK.FEATURES] = [
        {
            "label": "Promoter note",
            "type": "promoter",
            "start": 0,
            "end": 6,
            "source_status": "Source note recorded",
            "review_status": "Documentation review recorded",
        },
        {
            "label": "CDS note",
            "type": "cds",
            "start": 6,
            "end": len(sequence),
            "strand": -1,
        },
    ]

    render_calls: list[dict] = []
    log_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(tab_plasmid_map, "st", fake_st)
    monkeypatch.setattr(tab_plasmid_map, "_auto_detect_features", lambda seq: [])
    monkeypatch.setattr(tab_plasmid_map, "render_plasmid_map", lambda **kwargs: render_calls.append(kwargs))
    monkeypatch.setattr(tab_plasmid_map, "log_build_activity", lambda title, details: log_calls.append((title, details)))

    tab_plasmid_map.render()

    rendered = recorder.joined()
    assert "Assembly documentation readback (2 feature records)" in rendered
    assert "Source/provenance status" in rendered
    assert "Source/provenance status not recorded" in rendered
    assert "Manual documentation follow-up" in rendered
    assert "documentation-only preview" in rendered
    assert len(render_calls) == 1
    assert render_calls[0]["sequence"] == sequence
    assert render_calls[0]["map_type"] == "Linear"
    assert len(render_calls[0]["features"]) == 2
    assert log_calls


def test_renderer_labels_sequence_documentation_preview() -> None:
    source = open(
        os.path.join(ROOT, "components", "plasmid_map.py"),
        encoding="utf-8",
    ).read()

    assert "Sequence documentation preview" in source
    assert "map_label = f'Plasmid Map" not in source
    assert "ax.set_title(f'Plasmid Map" not in source
