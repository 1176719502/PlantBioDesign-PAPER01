from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.helpers.fake_streamlit import FakeStreamlit
import views.Homepage as homepage


def test_homepage_renders_rice_albumin_example_preview_without_persistence(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(homepage, "st", fake_st)

    homepage._render_rice_albumin_example_preview()

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[call["body"] for call in fake_st.code_calls],
        ]
    )
    markdown_blocks = [str(call["body"]) for call in fake_st.markdown_calls]

    assert any(call["label"] == "View rice albumin example preview" for call in fake_st.expander_calls)
    for expected in [
        "Rice albumin example preview",
        "Example only",
        "Documentation-only",
        "Not a construct recommendation",
        "Not " + "experiment" + "-ready",
        "Plant recombinant protein / molecular farming",
        "Rice context, review-only",
        "source/provenance required",
        "manual follow-up required",
        "Home -> Expression Wizard -> Component Library -> Plant Design Review Package -> QR/MD5 identity",
        "Target product / protein",
        "Plant species / host context",
        "Target tissue / organ / expression compartment",
        "Expression mode",
        "Gene / CDS source provenance",
        "Plant promoter context",
        "Signal peptide / transit peptide / subcellular targeting if applicable",
        "Terminator",
        "Selectable marker / reporter",
        "Vector / backbone context",
        "Transformation context",
        "Evidence / provenance gaps",
        "Detailed example readback",
        "Example package identity",
        "Snapshot ID:",
        "Show QR payload",
        "QR status:",
        "payload-only",
        "MD5 checksum",
        "BioDesignStudioPlant",
        "PlantDesignReviewPackage",
        "example=rice-albumin",
        "BDS-PLANT-R313-RICE-ALBUMIN-EXAMPLE",
        "QR/MD5 verifies only example package identity",
    ]:
        assert expected in rendered

    boundary_index = next(
        index for index, block in enumerate(markdown_blocks) if homepage._rice_albumin_example_preview()["boundary_note"] in block
    )
    readback_index = next(
        index for index, block in enumerate(markdown_blocks) if "Target product / protein" in block
    )
    assert boundary_index < readback_index

    identity = homepage._rice_albumin_example_preview()["identity"]
    assert identity["snapshot_id"] in rendered
    assert re.fullmatch(r"[0-9a-f]{32}", identity["md5_checksum"])
    assert identity["md5_checksum"] in rendered
    assert identity["qr_payload"] in rendered

    assert "Report identity / QR-MD5" not in rendered
    assert "st.metric" not in (Path(ROOT) / "views" / "Homepage.py").read_text(encoding="utf-8")
    assert fake_st.metric_calls == []
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.text_input_calls == []
    assert fake_st.text_area_calls == []
    assert fake_st.checkbox_calls == []
    assert fake_st.selectbox_calls == []
    assert fake_st.form_submit_button_calls == []


def test_homepage_collapses_legacy_module_launcher_after_example(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(homepage, "st", fake_st)

    navigated: list[str] = []

    homepage.render(navigated.append)

    expander_labels = [call["label"] for call in fake_st.expander_calls]
    rendered = "\n".join(str(call["body"]) for call in fake_st.markdown_calls)

    assert "View rice albumin example preview" in expander_labels
    assert "Advanced existing workflow map" in expander_labels
    assert "Existing documentation workflow modules" in expander_labels
    assert fake_st.expander_calls[-1] == {
        "label": "Existing documentation workflow modules",
        "expanded": False,
    }
    assert rendered.index("Rice albumin example preview") < rendered.index("Main Workflow")
    assert rendered.index("Main Workflow") < rendered.index("All Modules")
    assert any(call["label"].startswith("Open Expression Wizard") for call in fake_st.button_calls)
    assert navigated == []
