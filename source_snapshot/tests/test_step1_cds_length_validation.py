from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

from core.design_session import DesignSession
from services.sequence_inspector import inspect_sequence
from views.wizard_steps import step1_gene_input as step1
from views.wizard_steps._shared import _validate_cds_sequence


class _FakeContainer:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeColumn(_FakeContainer):
    def metric(self, *args, **kwargs):
        return None


class _FakeController:
    def __init__(self, ds: DesignSession):
        self._ds = ds
        self.saved = None
        self.advanced = False

    def get(self) -> DesignSession:
        return self._ds

    def save(self, ds: DesignSession) -> None:
        self.saved = ds
        self._ds = ds

    def advance(self) -> None:
        self.advanced = True


@pytest.fixture(autouse=True)
def _patch_streamlit_session(monkeypatch):
    import streamlit as st

    monkeypatch.setattr(st, 'session_state', {})
    monkeypatch.setattr(st, 'rerun', lambda: None)


@pytest.fixture
def _prime_step1_page(monkeypatch):
    import streamlit as st

    captured_errors: list[str] = []
    captured_warnings: list[str] = []
    captured_infos: list[str] = []
    captured_success: list[str] = []
    captured_status_panels: list[tuple[str, str, str | None]] = []

    monkeypatch.setattr(step1, '_step_header', lambda *args, **kwargs: None)
    monkeypatch.setattr(step1, '_section_label', lambda *args, **kwargs: None)

    def _capture_status_panel(title, body, tone=None, *args, **kwargs):
        captured_status_panels.append((str(title), str(body), tone))

    monkeypatch.setattr(step1, '_status_panel', _capture_status_panel)

    monkeypatch.setattr(step1.st, 'radio', lambda *args, **kwargs: 'Paste sequence')
    monkeypatch.setattr(step1.st, 'text_input', lambda label, value='', **kwargs: value)
    monkeypatch.setattr(step1.st, 'text_area', lambda label, value='', **kwargs: value)
    monkeypatch.setattr(step1.st, 'columns', lambda spec, **kwargs: tuple(_FakeColumn() for _ in range(spec if isinstance(spec, int) else len(spec))))
    monkeypatch.setattr(step1.st, 'caption', lambda *args, **kwargs: None)
    monkeypatch.setattr(step1.st, 'metric', lambda *args, **kwargs: None)
    monkeypatch.setattr(step1.st, 'markdown', lambda *args, **kwargs: None)
    monkeypatch.setattr(step1.st, 'code', lambda *args, **kwargs: None)
    monkeypatch.setattr(step1.st, 'file_uploader', lambda *args, **kwargs: None)
    monkeypatch.setattr(step1.st, 'selectbox', lambda label, options, **kwargs: options[0] if options else None)
    monkeypatch.setattr(step1.st, 'spinner', lambda *args, **kwargs: _FakeContainer())
    monkeypatch.setattr(step1.st, 'button', lambda label, **kwargs: kwargs.get('key') == 'wf_p1_next')
    monkeypatch.setattr(step1.st, 'error', lambda message, **kwargs: captured_errors.append(str(message)))
    monkeypatch.setattr(step1.st, 'warning', lambda message, **kwargs: captured_warnings.append(str(message)))
    monkeypatch.setattr(step1.st, 'info', lambda message, **kwargs: captured_infos.append(str(message)))
    monkeypatch.setattr(step1.st, 'success', lambda message, **kwargs: captured_success.append(str(message)))

    monkeypatch.setattr(st, 'session_state', {
        'wf_p1_name': 'GeneX',
        'wf_p1_seq': '',
    })

    return {
        'errors': captured_errors,
        'warnings': captured_warnings,
        'infos': captured_infos,
        'success': captured_success,
        'status_panels': captured_status_panels,
    }


def _status_panel_titles(captured: dict[str, object]) -> list[str]:
    return [title for title, _body, _tone in captured['status_panels']]


def _status_panel_bodies(captured: dict[str, object]) -> list[str]:
    return [body for _title, body, _tone in captured['status_panels']]


def test_step1_preflight_keeps_raw_invalid_sequence_as_overall_status():
    raw_result, raw_status, ready = step1._resolve_step1_readiness("ATGGCXTAA")
    parsed_result, parsed_status, parsed_ready = step1._resolve_step1_readiness("ATGGCTAA")

    assert raw_result is not None
    assert parsed_result is not None
    assert raw_status == "Invalid Sequence"
    assert parsed_status == "Needs Review"
    assert ready is False
    assert parsed_ready is False


def test_step1_preflight_cleaned_needs_review_does_not_override_raw_invalid():
    _result, status, ready = step1._resolve_step1_readiness("ATGGCXTAA")

    assert status == "Invalid Sequence"
    assert ready is False


def test_step1_preflight_short_valid_cds_is_needs_review():
    _result, status, ready = step1._resolve_step1_readiness("ATGGCTGCTTAA")

    assert status == "Needs Review"
    assert ready is False


def test_step1_preflight_detail_message_distinguishes_invalid_review_short_and_ready_states():
    invalid_result = inspect_sequence("ATGGCXTAA")
    short_result = inspect_sequence("ATGGCTGCTTAA")
    review_result = inspect_sequence("ATG" + "GCGCGC" * 6 + "TAA")
    ready_result = inspect_sequence(
        "ATGGTGAGCAAGGGCGAGGAGCTGTTCACCGGGGTGGTGCCC"
        "ATCCTGGTCGAGCTGGACGGCGACGTAAACGGCCACAAGTAA"
    )

    assert step1._build_step1_preflight_detail_message(invalid_result).startswith("Invalid Sequence:")
    assert step1._build_step1_preflight_detail_message(short_result).startswith("Too Short:")
    assert step1._build_step1_preflight_detail_message(review_result).startswith("Needs Review:")
    assert step1._build_step1_preflight_detail_message(ready_result).startswith("Ready for Wizard:")


def test_step1_readiness_helper_allows_only_ready_for_wizard_status():
    assert step1._resolve_step1_readiness(
        "ATGGTGAGCAAGGGCGAGGAGCTGTTCACCGGGGTGGTGCCC"
        "ATCCTGGTCGAGCTGGACGGCGACGTAAACGGCCACAAGTAA"
    )[2] is True
    assert step1._resolve_step1_readiness("ATGGCTGCTTAA")[2] is False
    assert step1._resolve_step1_readiness("ATGGCXTAA")[2] is False
    assert step1._resolve_step1_readiness(None)[2] is False


@pytest.mark.parametrize(
    ("sequence", "expected_status", "expected_disabled", "expected_advanced"),
    [
        ("ATGGCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGTAA", "Needs Review", True, False),
        ("ATG" + ("GCT" * 12) + "TA", "Needs Review", True, False),
        (
            "ATGGTGAGCAAGGGCGAGGAGCTGTTCACCGGGGTGGTGCCC"
            "ATCCTGGTCGAGCTGGACGGCGACGTAAACGGCCACAAGTAA",
            "Ready for Wizard",
            False,
            True,
        ),
        ("ATGGCXTAA", "Invalid Sequence", True, False),
        ("ATGGCTNNNTAA", "Needs Review", True, False),
        ("ATGGCTTAAGCTTAA", "Needs Review", True, False),
        ("ATGGCTGCTTAA", "Needs Review", True, False),
    ],
)
def test_step1_confirm_gate_matches_sequence_inspector_status(
    _prime_step1_page,
    monkeypatch,
    sequence,
    expected_status,
    expected_disabled,
    expected_advanced,
):
    ds = DesignSession(step=1, gene_name='GeneX', original_seq=sequence)
    ctrl = _FakeController(ds)
    button_calls: list[dict[str, object]] = []

    monkeypatch.setattr(step1.st, 'text_input', lambda label, value='', **kwargs: 'GeneX')
    monkeypatch.setattr(step1.st, 'text_area', lambda label, value='', **kwargs: sequence)

    def _button(label, **kwargs):
        button_calls.append({'label': label, **kwargs})
        return False if kwargs.get('disabled') else kwargs.get('key') == 'wf_p1_next'

    monkeypatch.setattr(step1.st, 'button', _button)
    step1.page(ctrl)

    result = inspect_sequence(sequence)
    confirm_call = next(call for call in button_calls if call.get('key') == 'wf_p1_next')
    status_bodies = _status_panel_bodies(_prime_step1_page)
    status_titles = _status_panel_titles(_prime_step1_page)

    assert result.status == expected_status
    assert any(f"Sequence Inspector status: {expected_status}." in body for body in status_bodies)
    if expected_status == "Needs Review":
        assert any(
            "Step 1 can only be confirmed when the sequence status is Ready for Wizard" in body
            or "Too Short:" in body
            for body in status_bodies
        )
    assert confirm_call.get('disabled') is expected_disabled
    assert ctrl.advanced is expected_advanced
    assert (ctrl.saved is not None) is expected_advanced
    if expected_status == "Ready for Wizard":
        assert "Ready for the next step" in status_titles
    else:
        assert "Ready for the next step" not in status_titles
        assert "A valid sequence is still required" in status_titles


def test_step1_ui_raw_invalid_character_blocks_confirmation(_prime_step1_page, monkeypatch):
    raw_seq = 'ATGGCXTAA'
    ds = DesignSession(step=1, gene_name='GeneX', original_seq=raw_seq)
    ctrl = _FakeController(ds)
    button_calls: list[dict[str, object]] = []

    monkeypatch.setattr(step1.st, 'text_input', lambda label, value='', **kwargs: 'GeneX')
    monkeypatch.setattr(step1.st, 'text_area', lambda label, value='', **kwargs: raw_seq)

    def _button(label, **kwargs):
        button_calls.append({'label': label, **kwargs})
        return False if kwargs.get('disabled') else kwargs.get('key') == 'wf_p1_next'

    monkeypatch.setattr(step1.st, 'button', _button)
    step1.page(ctrl)

    confirm_call = next(call for call in button_calls if call.get('key') == 'wf_p1_next')
    assert confirm_call.get('disabled') is True
    assert ctrl.advanced is False
    assert ctrl.saved is None
    assert any('invalid character' in message.lower() for message in _prime_step1_page['errors'])


def test_validate_cds_sequence_rejects_length_37_with_multiple_of_3_error():
    seq = 'ATG' + ('GCC' * 10) + 'GTAA'

    errors = _validate_cds_sequence(seq)

    assert len(seq) == 37
    assert 'CDS length must be a multiple of 3.' in errors


def test_validate_cds_sequence_accepts_length_39_without_multiple_of_3_error():
    seq = 'ATG' + ('GCC' * 11) + 'TAA'

    errors = _validate_cds_sequence(seq)

    assert len(seq) == 39
    assert 'CDS length must be a multiple of 3.' not in errors
    assert errors == []


def test_step1_ui_shows_multiple_of_3_status_for_length_37(_prime_step1_page, monkeypatch):
    invalid_seq = 'ATG' + ('GCC' * 10) + 'GTAA'
    ds = DesignSession(step=1, gene_name='Gene37', original_seq=invalid_seq)
    ctrl = _FakeController(ds)
    button_calls: list[dict[str, object]] = []

    monkeypatch.setattr(step1.st, 'text_input', lambda label, value='', **kwargs: 'Gene37')
    monkeypatch.setattr(step1.st, 'text_area', lambda label, value='', **kwargs: invalid_seq)

    def _button(label, **kwargs):
        button_calls.append({'label': label, **kwargs})
        return False

    monkeypatch.setattr(step1.st, 'button', _button)
    step1.page(ctrl)

    confirm_call = next(call for call in button_calls if call.get('key') == 'wf_p1_next')
    assert confirm_call.get('disabled') is True
    assert any('not divisible by 3' in message for message in _prime_step1_page['warnings'])
    assert ctrl.advanced is False
    assert ctrl.saved is None


def test_step1_ui_accepts_length_39_without_multiple_of_3_error(_prime_step1_page, monkeypatch):
    valid_seq = 'ATGGCTGATTTACCGAAAGTCCATGATGCTCCATTATAA'
    ds = DesignSession(step=1, gene_name='Gene39', original_seq=valid_seq)
    ctrl = _FakeController(ds)

    monkeypatch.setattr(step1.st, 'text_input', lambda label, value='', **kwargs: 'Gene39')
    monkeypatch.setattr(step1.st, 'text_area', lambda label, value='', **kwargs: valid_seq)
    step1.page(ctrl)

    assert len(valid_seq) == 39
    assert inspect_sequence(valid_seq).status == 'Ready for Wizard'
    assert 'CDS length must be a multiple of 3.' not in _prime_step1_page['errors']
    assert ctrl.advanced is True
    assert ctrl.saved is not None
    assert ctrl.saved.original_seq == valid_seq


def test_cleaning_does_not_bypass_multiple_of_3_validation():
    raw = '>Gene37\nATG GCC GCC GCC GCC GCC GCC GCC GCC GCC GCC GTAA\n'
    cleaned, warnings = step1._clean_pasted_gene_input(raw, use_service_cleaner=False)

    errors = _validate_cds_sequence(cleaned)

    assert warnings == []
    assert len(cleaned) == 37
    assert 'CDS length must be a multiple of 3.' in errors


def test_length_39_with_fasta_header_and_whitespace_still_passes_validation():
    raw = '>Gene39\nATG GCC GCC GCC GCC GCC GCC GCC GCC GCC GCC GCC TAA\n'
    cleaned, warnings = step1._clean_pasted_gene_input(raw, use_service_cleaner=False)

    errors = _validate_cds_sequence(cleaned)

    assert warnings == []
    assert len(cleaned) == 39
    assert errors == []
