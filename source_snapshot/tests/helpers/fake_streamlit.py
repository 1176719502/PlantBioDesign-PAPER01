from __future__ import annotations

from contextlib import contextmanager
from typing import Any


class FakeStreamlitContext:
    def __init__(self, fake_st: "FakeStreamlit | None" = None):
        self.fake_st = fake_st

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def metric(self, label: Any, value: Any = None, *args: Any, **kwargs: Any) -> None:
        if self.fake_st is not None:
            self.fake_st.metric_calls.append({"label": str(label), "value": str(value)})
        return None

    def markdown(self, body: Any, *args: Any, **kwargs: Any) -> None:
        if self.fake_st is not None:
            self.fake_st.markdown_calls.append({"body": body, "args": args, **kwargs})
        return None

    def caption(self, body: Any, **kwargs: Any) -> None:
        if self.fake_st is not None:
            self.fake_st.caption_messages.append(str(body))
        return None

    def info(self, body: Any, **kwargs: Any) -> None:
        if self.fake_st is not None:
            self.fake_st.info_messages.append(str(body))
        return None

    def warning(self, body: Any, **kwargs: Any) -> None:
        if self.fake_st is not None:
            self.fake_st.warning_messages.append(str(body))
        return None

    def error(self, body: Any, **kwargs: Any) -> None:
        if self.fake_st is not None:
            self.fake_st.error_messages.append(str(body))
        return None

    def success(self, body: Any, **kwargs: Any) -> None:
        if self.fake_st is not None:
            self.fake_st.success_messages.append(str(body))
        return None

    def button(self, label: str, key: str | None = None, **kwargs: Any) -> bool:
        if self.fake_st is None:
            return False
        return self.fake_st.button(label, key=key, **kwargs)

    def download_button(
        self,
        label: str,
        data: Any = None,
        file_name: str | None = None,
        mime: str | None = None,
        **kwargs: Any,
    ) -> bool:
        if self.fake_st is None:
            return False
        return self.fake_st.download_button(label, data=data, file_name=file_name, mime=mime, **kwargs)

    def expander(self, label: Any, *args: Any, **kwargs: Any) -> "FakeStreamlitContext":
        if self.fake_st is not None:
            self.fake_st.expander_calls.append({"label": str(label), **kwargs})
        return self


class FakeStreamlitTab(FakeStreamlitContext):
    pass


class FakeStreamlit:
    def __init__(self):
        self.session_state: dict[str, Any] = {}
        self.button_values: dict[str | None, bool] = {}
        self.file_uploader_value: Any = None
        self.file_uploader_calls: list[dict[str, Any]] = []
        self.button_calls: list[dict[str, Any]] = []
        self.download_button_calls: list[dict[str, Any]] = []
        self.markdown_calls: list[dict[str, Any]] = []
        self.info_messages: list[str] = []
        self.caption_messages: list[str] = []
        self.subheaders: list[str] = []
        self.titles: list[str] = []
        self.warning_messages: list[str] = []
        self.error_messages: list[str] = []
        self.success_messages: list[str] = []
        self.write_messages: list[str] = []
        self.code_calls: list[dict[str, Any]] = []
        self.metric_calls: list[dict[str, str]] = []
        self.tab_labels: list[str] = []
        self.tab_groups: list[list[str]] = []
        self.expander_calls: list[dict[str, Any]] = []
        self.dataframes: list[Any] = []
        self.tables: list[Any] = []
        self.text_input_calls: list[dict[str, Any]] = []
        self.text_area_calls: list[dict[str, Any]] = []
        self.text_input_values: dict[str | None, str] = {}
        self.text_area_values: dict[str | None, str] = {}
        self.checkbox_values: dict[str | None, bool] = {}
        self.checkbox_calls: list[dict[str, Any]] = []
        self.selectbox_values: dict[str | None, Any] = {}
        self.selectbox_calls: list[dict[str, Any]] = []
        self.multiselect_values: dict[str | None, list[Any]] = {}
        self.multiselect_calls: list[dict[str, Any]] = []
        self.radio_values: dict[str | None, Any] = {}
        self.radio_calls: list[dict[str, Any]] = []
        self.form_submit_values: dict[str | None, bool] = {}
        self.form_submit_button_calls: list[dict[str, Any]] = []
        self.rerun_calls = 0
        self.page_config_calls: list[dict[str, Any]] = []
        self.number_input_values: dict[str | None, Any] = {}
        self.number_input_calls: list[dict[str, Any]] = []

    def set_page_config(self, **kwargs: Any) -> None:
        self.page_config_calls.append(dict(kwargs))

    def title(self, body: Any, **kwargs: Any) -> None:
        self.titles.append(str(body))

    def subheader(self, body: Any, **kwargs: Any) -> None:
        self.subheaders.append(str(body))

    def caption(self, body: Any, **kwargs: Any) -> None:
        self.caption_messages.append(str(body))

    def info(self, body: Any, **kwargs: Any) -> None:
        self.info_messages.append(str(body))

    def warning(self, body: Any, **kwargs: Any) -> None:
        self.warning_messages.append(str(body))

    def error(self, body: Any, **kwargs: Any) -> None:
        self.error_messages.append(str(body))

    def success(self, body: Any, **kwargs: Any) -> None:
        self.success_messages.append(str(body))

    def markdown(self, body: Any, *args: Any, **kwargs: Any) -> None:
        self.markdown_calls.append({"body": body, "args": args, **kwargs})
        return None

    def write(self, body: Any, **kwargs: Any) -> None:
        self.write_messages.append(str(body))

    def code(self, body: Any, language: str | None = None, **kwargs: Any) -> None:
        self.code_calls.append({"body": str(body), "language": language, **kwargs})

    def divider(self) -> None:
        return None

    def metric(self, label: Any, value: Any = None, *args: Any, **kwargs: Any) -> None:
        self.metric_calls.append({"label": str(label), "value": str(value)})

    def dataframe(self, data: Any, **kwargs: Any) -> None:
        self.dataframes.append(data)

    def table(self, data: Any, **kwargs: Any) -> None:
        self.tables.append(data)

    def button(self, label: str, key: str | None = None, **kwargs: Any) -> bool:
        self.button_calls.append({"label": label, "key": key, **kwargs})
        lookup_key = key if key is not None else label
        return self.button_values.get(lookup_key, self.button_values.get(key, False))

    def download_button(
        self,
        label: str,
        data: Any = None,
        file_name: str | None = None,
        mime: str | None = None,
        **kwargs: Any,
    ) -> bool:
        self.download_button_calls.append(
            {"label": label, "data": data, "file_name": file_name, "mime": mime, **kwargs}
        )
        return False

    def columns(self, spec: int | list[Any] | tuple[Any, ...], **kwargs: Any) -> list[FakeStreamlitContext]:
        count = spec if isinstance(spec, int) else len(spec)
        return [FakeStreamlitContext(self) for _ in range(count)]

    def tabs(self, labels: list[Any] | tuple[Any, ...]) -> list[FakeStreamlitTab]:
        tab_labels = [str(label) for label in labels]
        self.tab_labels.extend(tab_labels)
        self.tab_groups.append(tab_labels)
        return [FakeStreamlitTab(self) for _ in tab_labels]

    def expander(self, label: Any, *args: Any, **kwargs: Any) -> FakeStreamlitContext:
        self.expander_calls.append({"label": str(label), **kwargs})
        return FakeStreamlitContext(self)

    @contextmanager
    def container(self, **kwargs: Any):
        yield FakeStreamlitContext(self)

    @contextmanager
    def form(self, *args: Any, **kwargs: Any):
        yield FakeStreamlitContext(self)

    def number_input(self, label: str, value: Any = 1, **kwargs: Any) -> Any:
        key = kwargs.get("key")
        self.number_input_calls.append({"label": label, "value": value, **kwargs})
        if key in self.number_input_values:
            resolved = self.number_input_values[key]
            if key is not None:
                self.session_state[key] = resolved
            return resolved
        if key is not None and key in self.session_state:
            return self.session_state[key]
        if key is not None:
            self.session_state[key] = value
        return value

    def text_input(self, label: str, value: str = "", **kwargs: Any) -> str:
        key = kwargs.get("key")
        self.text_input_calls.append({"label": label, "value": value, **kwargs})
        if key in self.text_input_values:
            return self.text_input_values[key]
        if key is not None and key in self.session_state:
            return str(self.session_state[key])
        return value

    def text_area(self, label: str, value: str = "", **kwargs: Any) -> str:
        key = kwargs.get("key")
        self.text_area_calls.append({"label": label, "value": value, **kwargs})
        if key in self.text_area_values:
            return self.text_area_values[key]
        if key is not None and key in self.session_state:
            return str(self.session_state[key])
        return value

    def checkbox(self, label: str, value: bool = False, key: str | None = None, **kwargs: Any) -> bool:
        self.checkbox_calls.append({"label": label, "key": key, "value": value, **kwargs})
        return self.checkbox_values.get(key, value)

    def selectbox(self, label: str, options: Any, index: int = 0, key: str | None = None, **kwargs: Any) -> Any:
        option_list = list(options)
        self.selectbox_calls.append({"label": label, "options": option_list, "index": index, "key": key, **kwargs})
        if key in self.selectbox_values:
            return self.selectbox_values[key]
        if not option_list:
            return None
        normalized_index = min(max(index, 0), len(option_list) - 1)
        return option_list[normalized_index]

    def multiselect(self, label: str, options: Any, default: Any = None, key: str | None = None, **kwargs: Any) -> list[Any]:
        option_list = list(options)
        default_list = list(default or [])
        self.multiselect_calls.append({"label": label, "options": option_list, "default": default_list, "key": key, **kwargs})
        if key in self.multiselect_values:
            return self.multiselect_values[key]
        return [value for value in default_list if value in option_list]

    def radio(self, label: str, options: Any, index: int = 0, key: str | None = None, **kwargs: Any) -> Any:
        option_list = list(options)
        self.radio_calls.append({"label": label, "options": option_list, "index": index, "key": key, **kwargs})
        if key in self.radio_values:
            return self.radio_values[key]
        if key is not None and key in self.session_state and self.session_state[key] in option_list:
            return self.session_state[key]
        if not option_list:
            return None
        normalized_index = min(max(index, 0), len(option_list) - 1)
        value = option_list[normalized_index]
        if key is not None:
            self.session_state[key] = value
        return value

    def form_submit_button(self, label: str, **kwargs: Any) -> bool:
        key = kwargs.get("key")
        self.form_submit_button_calls.append({"label": label, "key": key, **kwargs})
        return self.form_submit_values.get(key, False)

    def file_uploader(self, label: str, **kwargs: Any) -> Any:
        self.file_uploader_calls.append({"label": label, **kwargs})
        return self.file_uploader_value

    def rerun(self) -> None:
        self.rerun_calls += 1
