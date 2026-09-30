from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd


CARD_STYLE = """
<style>
.bds-review-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.65rem;
  margin: 0.35rem 0 0.85rem;
}
.bds-review-card {
  border: 1px solid rgba(49, 51, 63, 0.18);
  border-radius: 8px;
  padding: 0.7rem 0.78rem;
  background: rgba(255, 255, 255, 0.55);
  overflow-wrap: anywhere;
  word-break: break-word;
}
.bds-review-label {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  color: rgba(49, 51, 63, 0.68);
  margin-bottom: 0.24rem;
}
.bds-review-value {
  font-size: 1rem;
  font-weight: 650;
  line-height: 1.32;
  color: rgb(49, 51, 63);
}
.bds-review-note {
  margin-top: 0.34rem;
  font-size: 0.82rem;
  line-height: 1.35;
  color: rgba(49, 51, 63, 0.72);
}
.bds-review-fields {
  margin-top: 0.46rem;
  display: grid;
  gap: 0.3rem;
}
.bds-review-field {
  font-size: 0.84rem;
  line-height: 1.35;
  color: rgba(49, 51, 63, 0.8);
}
.bds-review-field strong {
  color: rgba(49, 51, 63, 0.74);
}
</style>
"""


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _escape(value: Any) -> str:
    return html.escape(_text(value) or "not recorded")


def _rows(rows: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    return [dict(row) for row in rows or [] if isinstance(row, Mapping)]


def _ordered_keys(row: Mapping[str, Any], preferred: Sequence[str] | None) -> list[str]:
    keys = [key for key in preferred or [] if key in row]
    keys.extend(key for key in row.keys() if key not in keys)
    return keys


def render_wrapped_summary_cards(
    st_api: Any,
    cards: Sequence[Mapping[str, Any]],
    *,
    class_suffix: str = "",
) -> None:
    visible_cards = _rows(cards)
    if not visible_cards:
        return

    suffix = f" {html.escape(class_suffix)}" if class_suffix else ""
    parts = [CARD_STYLE, f'<div class="bds-review-grid{suffix}">']
    for card in visible_cards:
        label = _escape(card.get("label"))
        value = _escape(card.get("value"))
        note = _text(card.get("note"))
        parts.append('<div class="bds-review-card">')
        parts.append(f'<div class="bds-review-label">{label}</div>')
        parts.append(f'<div class="bds-review-value">{value}</div>')
        if note:
            parts.append(f'<div class="bds-review-note">{_escape(note)}</div>')
        parts.append("</div>")
    parts.append("</div>")
    st_api.markdown("".join(parts), unsafe_allow_html=True)


def render_compact_review_rows(
    st_api: Any,
    rows: Sequence[Mapping[str, Any]],
    *,
    title_field: str | None = None,
    subtitle_field: str | None = None,
    visible_fields: Sequence[str] | None = None,
    max_cards: int | None = None,
) -> None:
    row_list = _rows(rows)
    if not row_list:
        return

    visible_rows = row_list[:max_cards] if max_cards else row_list
    parts = [CARD_STYLE, '<div class="bds-review-grid">']
    for index, row in enumerate(visible_rows, start=1):
        keys = _ordered_keys(row, [key for key in (title_field, subtitle_field) if key] + list(visible_fields or []))
        title_key = title_field if title_field in row else (keys[0] if keys else None)
        subtitle_key = subtitle_field if subtitle_field in row else (keys[1] if len(keys) > 1 else None)
        detail_keys = [
            key
            for key in keys
            if key != title_key and key != subtitle_key and (not visible_fields or key in visible_fields)
        ]
        if not detail_keys:
            detail_keys = [key for key in keys if key != title_key and key != subtitle_key][:4]

        parts.append('<div class="bds-review-card">')
        parts.append(
            f'<div class="bds-review-label">{_escape(title_key or f"Review row {index}")}</div>'
        )
        parts.append(f'<div class="bds-review-value">{_escape(row.get(title_key) if title_key else index)}</div>')
        if subtitle_key:
            parts.append(
                f'<div class="bds-review-note"><strong>{_escape(subtitle_key)}:</strong> '
                f'{_escape(row.get(subtitle_key))}</div>'
            )
        if detail_keys:
            parts.append('<div class="bds-review-fields">')
            for key in detail_keys[:5]:
                parts.append(
                    f'<div class="bds-review-field"><strong>{_escape(key)}:</strong> '
                    f'{_escape(row.get(key))}</div>'
                )
            parts.append("</div>")
        parts.append("</div>")
    parts.append("</div>")
    st_api.markdown("".join(parts), unsafe_allow_html=True)

    if max_cards and len(row_list) > max_cards:
        st_api.caption(
            f"{len(row_list) - max_cards} additional review rows are available in the full detail table below."
        )


def render_responsive_detail_table(
    st_api: Any,
    rows: Sequence[Mapping[str, Any]],
    *,
    title: str,
    empty_message: str,
    title_field: str | None = None,
    subtitle_field: str | None = None,
    visible_fields: Sequence[str] | None = None,
    expanded: bool = False,
    table_expander: bool = True,
    dataframe: bool = True,
) -> None:
    row_list = _rows(rows)
    st_api.markdown(f"**{title}**")
    if not row_list:
        st_api.info(empty_message)
        return

    render_compact_review_rows(
        st_api,
        row_list,
        title_field=title_field,
        subtitle_field=subtitle_field,
        visible_fields=visible_fields,
    )
    table_data = pd.DataFrame(row_list) if dataframe else row_list
    if table_expander:
        with st_api.expander(f"Full {title} table", expanded=expanded):
            st_api.caption(
                "Complete read-only detail table; long source, gap, and traceability values remain available here."
            )
            st_api.dataframe(table_data, width="stretch", hide_index=True)
    else:
        st_api.caption("Complete read-only detail table; long source, gap, and traceability values remain available here.")
        st_api.dataframe(table_data, width="stretch", hide_index=True)
