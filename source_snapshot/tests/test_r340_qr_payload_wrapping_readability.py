# -*- coding: utf-8 -*-
from __future__ import annotations

from tests.helpers.fake_streamlit import FakeStreamlit
import views.pathway_workspace_sections.project_review_report_section as review_report_section


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    return fake_st


def test_r340_qr_payload_is_rendered_in_wrapped_readback_container(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    project = {"id": "r340-wrap", "name": "R340 wrap"}
    payload = "BioDesignStudioPlant|PlantDesignReviewPackage|snapshot=R340|" + "x" * 160

    review_report_section._render_qr_payload_readback(payload)

    assert fake_st.caption_messages == [
        "QR payload text readback: wraps long identity text for review only; payload content is unchanged."
    ]
    assert len(fake_st.markdown_calls) == 1
    rendered = str(fake_st.markdown_calls[0]["body"])
    assert "white-space: pre-wrap" in rendered
    assert "overflow-wrap: anywhere" in rendered
    assert "word-break: break-word" in rendered
    assert "BioDesignStudioPlant|PlantDesignReviewPackage|snapshot=R340" in rendered


def test_r340_package_identity_retains_checksum_and_payload_semantics(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    package = {
        "boundary_notes": ["This Plant Design Review Package is documentation-only."],
        "identity": {
            "package_type": "Plant Design Review Package",
            "project_direction": "Plant recombinant protein / molecular farming",
            "report_scope": "Documentation-only pre-experiment design review",
            "snapshot_id": "BDS-PLANT-R340-20260701-000000",
            "md5_checksum": "0123456789abcdef0123456789abcdef",
            "qr_payload": "BioDesignStudioPlant|PlantDesignReviewPackage|snapshot=R340|md5=0123456789abcdef0123456789abcdef",
            "qr_dependency_note": "Payload-only QR payload preview.",
            "boundary_notes": ["QR/MD5 verifies only the report/package snapshot identity."],
        },
        "summary": {
            "section_count": 3,
            "not_available_count": 1,
            "manual_follow_up_count": 3,
        },
    }

    review_report_section._render_plant_design_review_package_context(
        package,
        package["identity"],
        package["summary"],
    )

    rendered = "\n".join(fake_st.caption_messages)
    assert "MD5 checksum: 0123456789abcdef0123456789abcdef" in rendered
    assert "QR/MD5 verifies only the report/package snapshot identity." in rendered
    assert "QR payload text readback: wraps long identity text for review only" in rendered
