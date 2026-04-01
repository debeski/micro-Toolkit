from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.parse import urljoin, urlparse

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dngine.core.app_utils import generate_output_filename
from dngine.core.command_runtime import HeadlessTaskContext
from dngine.core.page_style import apply_page_chrome, apply_semantic_class
from dngine.core.plugin_api import QtPlugin, bind_tr, safe_tr
from dngine.core.table_utils import configure_resizable_table
from dngine.core.widgets import ScrollSafeComboBox


QComboBox = ScrollSafeComboBox

DEFAULT_MAX_PAGES = 1
MAX_PAGES_LIMIT = 50
DEFAULT_TIMEOUT_SECONDS = 15.0
OUTPUT_FIELDS = ("source_url", "page_url", "title", "link", "text")


def _pt(translate, key: str, default: str | None = None, **kwargs) -> str:
    return safe_tr(translate, key, default, **kwargs)


def _normalize_whitespace(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _preview_text(value: str, *, limit: int = 120) -> str:
    compact = _normalize_whitespace(value)
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _coerce_start_url(url: str, *, translate=None) -> str:
    raw = str(url or "").strip()
    if not raw:
        raise ValueError(_pt(translate, "error.invalid_url", "Enter a valid http:// or https:// URL."))
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(_pt(translate, "error.invalid_url", "Enter a valid http:// or https:// URL."))
    return raw


def _validate_selector(selector: str, *, translate=None, label_key: str = "error.invalid_selector") -> str:
    text = str(selector or "").strip()
    return text


def _clamp_max_pages(value: int | str, *, translate=None) -> int:
    try:
        parsed = int(value)
    except Exception as exc:
        raise ValueError(_pt(translate, "error.invalid_pages", "Max pages must be a whole number between 1 and {limit}.", limit=str(MAX_PAGES_LIMIT))) from exc
    if parsed < 1 or parsed > MAX_PAGES_LIMIT:
        raise ValueError(_pt(translate, "error.invalid_pages", "Max pages must be a whole number between 1 and {limit}.", limit=str(MAX_PAGES_LIMIT)))
    return parsed


def _coerce_timeout(value: float | str, *, translate=None) -> float:
    try:
        parsed = float(value)
    except Exception as exc:
        raise ValueError(_pt(translate, "error.invalid_timeout", "Timeout must be a positive number of seconds.")) from exc
    if parsed <= 0:
        raise ValueError(_pt(translate, "error.invalid_timeout", "Timeout must be a positive number of seconds."))
    return parsed


def _safe_select(root, selector: str, *, translate=None):
    try:
        return root.select(selector)
    except Exception as exc:
        raise ValueError(_pt(translate, "error.invalid_selector", "One of the CSS selectors is invalid: {error}", error=str(exc))) from exc


def _safe_select_one(root, selector: str, *, translate=None):
    try:
        return root.select_one(selector)
    except Exception as exc:
        raise ValueError(_pt(translate, "error.invalid_selector", "One of the CSS selectors is invalid: {error}", error=str(exc))) from exc


def _resolved_href(element, current_url: str) -> str:
    if element is None:
        return ""
    href = ""
    for key in ("href", "data-href"):
        candidate = str(element.get(key, "")).strip()
        if candidate:
            href = candidate
            break
    if not href:
        return ""
    return urljoin(current_url, href)


def _extract_link(item, current_url: str, selector: str, *, translate=None) -> str:
    target = None
    if selector:
        target = _safe_select_one(item, selector, translate=translate)
    elif getattr(item, "name", "") == "a":
        target = item
    else:
        target = item.select_one("a[href]")
    return _resolved_href(target, current_url)


def _extract_title(item, selector: str, *, translate=None) -> str:
    target = _safe_select_one(item, selector, translate=translate) if selector else None
    if target is not None:
        return _normalize_whitespace(target.get_text(" ", strip=True))
    return ""


def _extract_text(item, selector: str, *, translate=None) -> str:
    target = _safe_select_one(item, selector, translate=translate) if selector else item
    if target is None:
        return ""
    return _normalize_whitespace(target.get_text(" ", strip=True))


def _sanitize_export_rows(rows: list[dict[str, object]]) -> list[dict[str, str]]:
    sanitized: list[dict[str, str]] = []
    for row in rows:
        sanitized.append({field: str(row.get(field, "") or "") for field in OUTPUT_FIELDS})
    return sanitized


def export_scrape_results(
    rows: list[dict[str, object]],
    *,
    output_dir: Path,
    output_format: str,
    source_url: str,
) -> Path:
    normalized_format = str(output_format or "json").strip().lower()
    if normalized_format not in {"json", "csv"}:
        raise ValueError(f"Unsupported export format: {output_format}")
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    host = urlparse(source_url).netloc or "web"
    extension = ".json" if normalized_format == "json" else ".csv"
    output_path = output_dir / generate_output_filename("WebScrape", host, extension)
    safe_rows = _sanitize_export_rows(rows)
    if normalized_format == "json":
        output_path.write_text(json.dumps(safe_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        return output_path

    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(OUTPUT_FIELDS))
        writer.writeheader()
        writer.writerows(safe_rows)
    return output_path


def scrape_web_pages(
    context,
    *,
    url: str,
    item_selector: str,
    title_selector: str = "",
    link_selector: str = "",
    text_selector: str = "",
    next_selector: str = "",
    max_pages: int = DEFAULT_MAX_PAGES,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    translate=None,
):
    try:
        import requests
        from bs4 import BeautifulSoup
    except Exception as exc:
        raise RuntimeError(
            _pt(
                translate,
                "error.dependencies",
                "Web Scraper dependencies are missing. Reinstall the updated requirements for requests and beautifulsoup4.",
            )
        ) from exc

    source_url = _coerce_start_url(url, translate=translate)
    item_selector = _validate_selector(item_selector, translate=translate)
    title_selector = _validate_selector(title_selector, translate=translate)
    link_selector = _validate_selector(link_selector, translate=translate)
    text_selector = _validate_selector(text_selector, translate=translate)
    next_selector = _validate_selector(next_selector, translate=translate)
    if not item_selector:
        raise ValueError(_pt(translate, "error.missing_item_selector", "Enter a CSS selector for the items you want to extract."))
    pages_limit = _clamp_max_pages(max_pages, translate=translate)
    timeout_value = _coerce_timeout(timeout_seconds, translate=translate)

    session = requests.Session()
    session.headers.update({"User-Agent": "DNgine Web Scraper/0.8.8"})

    rows: list[dict[str, object]] = []
    visited_urls: list[str] = []
    visited_set: set[str] = set()
    current_url = source_url
    stop_reason = "max_pages"

    for page_number in range(1, pages_limit + 1):
        if current_url in visited_set:
            stop_reason = "repeated_url"
            context.log(_pt(translate, "log.pagination_repeat", "Stopping because pagination repeated a page URL: {url}", url=current_url), "WARNING")
            break

        visited_set.add(current_url)
        visited_urls.append(current_url)
        context.log(
            _pt(
                translate,
                "log.fetch",
                "Fetching page {index} of up to {limit}: {url}",
                index=str(page_number),
                limit=str(pages_limit),
                url=current_url,
            )
        )

        try:
            response = session.get(current_url, timeout=timeout_value)
            response.raise_for_status()
        except requests.exceptions.Timeout as exc:
            if page_number == 1:
                raise ValueError(_pt(translate, "error.timeout", "The request timed out after {seconds} seconds.", seconds=str(timeout_value))) from exc
            stop_reason = "fetch_timeout"
            context.log(_pt(translate, "log.fetch_timeout", "Stopping after a later page timed out: {url}", url=current_url), "WARNING")
            break
        except requests.exceptions.HTTPError as exc:
            if page_number == 1:
                status_code = getattr(getattr(exc, "response", None), "status_code", "unknown")
                raise ValueError(_pt(translate, "error.http", "The server returned HTTP {status} for {url}.", status=str(status_code), url=current_url)) from exc
            stop_reason = "fetch_http_error"
            context.log(_pt(translate, "log.fetch_http", "Stopping after a later page returned an HTTP error: {url}", url=current_url), "WARNING")
            break
        except requests.exceptions.RequestException as exc:
            if page_number == 1:
                raise ValueError(_pt(translate, "error.request", "The page could not be fetched: {error}", error=str(exc))) from exc
            stop_reason = "fetch_error"
            context.log(_pt(translate, "log.fetch_error", "Stopping after a later page failed to load: {url}", url=current_url), "WARNING")
            break

        soup = BeautifulSoup(response.text, "html.parser")
        items = _safe_select(soup, item_selector, translate=translate)
        extracted_count = 0
        for item in items:
            title = _extract_title(item, title_selector, translate=translate)
            link = _extract_link(item, current_url, link_selector, translate=translate)
            text = _extract_text(item, text_selector, translate=translate)
            if not title and text:
                title = _preview_text(text, limit=90)
            if not text and title:
                text = title
            if not any((title, link, text)):
                continue
            rows.append(
                {
                    "source_url": source_url,
                    "page_url": current_url,
                    "title": title,
                    "link": link,
                    "text": text,
                    "page_number": page_number,
                }
            )
            extracted_count += 1

        context.log(
            _pt(
                translate,
                "log.page_result",
                "Page {index} produced {count} matching item(s).",
                index=str(page_number),
                count=str(extracted_count),
            )
        )
        context.progress(page_number / float(pages_limit))

        if not next_selector:
            stop_reason = "no_pagination"
            break

        next_element = _safe_select_one(soup, next_selector, translate=translate)
        next_url = _resolved_href(next_element, current_url)
        if not next_url:
            stop_reason = "no_next_link"
            context.log(_pt(translate, "log.pagination_end", "Stopping because no next-page link matched the selector."), "INFO")
            break
        if next_url in visited_set:
            stop_reason = "repeated_url"
            context.log(_pt(translate, "log.pagination_repeat", "Stopping because pagination repeated a page URL: {url}", url=next_url), "WARNING")
            break
        current_url = next_url
    else:
        stop_reason = "max_pages"

    context.log(
        _pt(
            translate,
            "log.done",
            "Scrape complete. Visited {pages} page(s) and extracted {count} item(s).",
            pages=str(len(visited_urls)),
            count=str(len(rows)),
        )
    )
    return {
        "source_url": source_url,
        "rows": _sanitize_export_rows(rows),
        "count": len(rows),
        "pages_visited": len(visited_urls),
        "stop_reason": stop_reason,
    }


def run_web_scraper_task(
    context,
    services,
    plugin_id: str,
    *,
    url: str,
    item_selector: str,
    title_selector: str = "",
    link_selector: str = "",
    text_selector: str = "",
    next_selector: str = "",
    max_pages: int = DEFAULT_MAX_PAGES,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
):
    translate = lambda key, default=None, **kwargs: services.plugin_text(plugin_id, key, default, **kwargs)
    return scrape_web_pages(
        context,
        url=url,
        item_selector=item_selector,
        title_selector=title_selector,
        link_selector=link_selector,
        text_selector=text_selector,
        next_selector=next_selector,
        max_pages=max_pages,
        timeout_seconds=timeout_seconds,
        translate=translate,
    )


def run_web_scraper_headless(
    services,
    plugin_id: str,
    *,
    url: str,
    item_selector: str,
    title_selector: str = "",
    link_selector: str = "",
    text_selector: str = "",
    next_selector: str = "",
    max_pages: int = DEFAULT_MAX_PAGES,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    output_format: str = "json",
    output_dir: str = "",
):
    context = HeadlessTaskContext(services, command_id="tool.web_scraper.run")
    try:
        payload = run_web_scraper_task(
            context,
            services,
            plugin_id,
            url=url,
            item_selector=item_selector,
            title_selector=title_selector,
            link_selector=link_selector,
            text_selector=text_selector,
            next_selector=next_selector,
            max_pages=max_pages,
            timeout_seconds=timeout_seconds,
        )
        target_dir = Path(output_dir).expanduser().resolve() if str(output_dir).strip() else services.default_output_path() / "web_scraper"
        export_path = export_scrape_results(
            payload["rows"],
            output_dir=target_dir,
            output_format=output_format,
            source_url=str(payload["source_url"]),
        )
    except Exception as exc:
        services.record_run(plugin_id, "ERROR", str(exc)[:500])
        raise

    status = "SUCCESS" if int(payload.get("count", 0)) > 0 else "WARNING"
    services.record_run(plugin_id, status, str(export_path)[:500])
    return {
        "source_url": payload["source_url"],
        "count": payload["count"],
        "pages_visited": payload["pages_visited"],
        "stop_reason": payload["stop_reason"],
        "output_format": str(output_format).strip().lower() or "json",
        "output_path": str(export_path),
    }


class WebScraperPlugin(QtPlugin):
    plugin_id = "web_scraper"
    name = "Web Scraper"
    description = "Extract rows from public static HTML pages with CSS selectors, in-app previews, and optional export."
    category = "Data Utilities"
    preferred_icon = "search"

    def register_commands(self, registry, services) -> None:
        registry.register(
            "tool.web_scraper.run",
            "Run Web Scraper",
            "Scrape public static HTML pages with CSS selectors and export the results.",
            lambda url, item_selector, title_selector="", link_selector="", text_selector="", next_selector="", max_pages=1, timeout_seconds=15.0, output_format="json", output_dir="": run_web_scraper_headless(
                services,
                self.plugin_id,
                url=url,
                item_selector=item_selector,
                title_selector=title_selector,
                link_selector=link_selector,
                text_selector=text_selector,
                next_selector=next_selector,
                max_pages=max_pages,
                timeout_seconds=timeout_seconds,
                output_format=output_format,
                output_dir=output_dir,
            ),
        )

    def create_widget(self, services) -> QWidget:
        return WebScraperPage(services, self.plugin_id)


class WebScraperPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.tr = bind_tr(services, plugin_id)
        self._rows: list[dict[str, str]] = []
        self._latest_result: dict[str, object] | None = None
        self._has_run = False
        self._build_ui()
        self.services.i18n.language_changed.connect(self._apply_texts)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)
        self._apply_texts()

    def _pt(self, key: str, default: str | None = None, **kwargs) -> str:
        return self.tr(key, default, **kwargs)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        self.title_label = QLabel()
        outer.addWidget(self.title_label)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        outer.addWidget(self.description_label)

        self.config_card = QFrame()
        config_layout = QFormLayout(self.config_card)
        config_layout.setContentsMargins(16, 14, 16, 14)
        config_layout.setSpacing(10)

        self.url_input = QLineEdit()
        self.item_selector_input = QLineEdit()
        self.title_selector_input = QLineEdit()
        self.link_selector_input = QLineEdit()
        self.text_selector_input = QLineEdit()
        self.next_selector_input = QLineEdit()
        for widget in (
            self.url_input,
            self.item_selector_input,
            self.title_selector_input,
            self.link_selector_input,
            self.text_selector_input,
            self.next_selector_input,
        ):
            widget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            widget.setClearButtonEnabled(True)

        self.url_label = QLabel()
        self.item_selector_label = QLabel()
        self.title_selector_label = QLabel()
        self.link_selector_label = QLabel()
        self.text_selector_label = QLabel()
        self.next_selector_label = QLabel()
        config_layout.addRow(self.url_label, self.url_input)
        config_layout.addRow(self.item_selector_label, self.item_selector_input)
        config_layout.addRow(self.title_selector_label, self.title_selector_input)
        config_layout.addRow(self.link_selector_label, self.link_selector_input)
        config_layout.addRow(self.text_selector_label, self.text_selector_input)
        config_layout.addRow(self.next_selector_label, self.next_selector_input)

        self.max_pages_label = QLabel()
        self.max_pages_input = QSpinBox()
        self.max_pages_input.setRange(1, MAX_PAGES_LIMIT)
        self.max_pages_input.setValue(DEFAULT_MAX_PAGES)
        config_layout.addRow(self.max_pages_label, self.max_pages_input)

        self.timeout_label = QLabel()
        self.timeout_input = QDoubleSpinBox()
        self.timeout_input.setRange(0.5, 120.0)
        self.timeout_input.setDecimals(1)
        self.timeout_input.setSingleStep(0.5)
        self.timeout_input.setValue(DEFAULT_TIMEOUT_SECONDS)
        config_layout.addRow(self.timeout_label, self.timeout_input)

        self.output_format_label = QLabel()
        self.output_format_combo = QComboBox()
        config_layout.addRow(self.output_format_label, self.output_format_combo)
        outer.addWidget(self.config_card)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)
        self.run_button = QPushButton()
        apply_semantic_class(self.run_button, "button_class")
        self.run_button.clicked.connect(self._run)
        actions_row.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_row.addStretch(1)
        outer.addLayout(actions_row)

        self.summary_card = QFrame()
        summary_layout = QVBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        outer.addWidget(self.summary_card)

        filters_row = QHBoxLayout()
        filters_row.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.textChanged.connect(self._refresh_results_view)
        filters_row.addWidget(self.search_input, 1)
        outer.addLayout(filters_row)

        self.results_splitter = QSplitter(Qt.Orientation.Vertical)

        self.table = QTableWidget(0, 4)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemSelectionChanged.connect(self._render_selected_details)
        configure_resizable_table(
            self.table,
            stretch_columns={0, 3},
            resize_to_contents_columns=set(),
            default_widths={0: 220, 1: 200, 2: 220, 3: 420},
        )
        self.results_splitter.addWidget(self.table)

        self.details_output = QPlainTextEdit()
        self.details_output.setReadOnly(True)
        apply_semantic_class(self.details_output, "output_class")
        self.results_splitter.addWidget(self.details_output)
        self.results_splitter.setStretchFactor(0, 3)
        self.results_splitter.setStretchFactor(1, 2)
        outer.addWidget(self.results_splitter, 1)

    def _apply_texts(self) -> None:
        direction = self.services.i18n.layout_direction()
        self.setLayoutDirection(direction)
        self.search_input.setLayoutDirection(direction)
        self.table.setLayoutDirection(direction)
        self.details_output.setLayoutDirection(direction)

        current_format = self.output_format_combo.currentData() or "json"
        self.output_format_combo.blockSignals(True)
        self.output_format_combo.clear()
        self.output_format_combo.addItem(self._pt("output_format.json", "JSON"), "json")
        self.output_format_combo.addItem(self._pt("output_format.csv", "CSV"), "csv")
        index = self.output_format_combo.findData(current_format)
        self.output_format_combo.setCurrentIndex(index if index >= 0 else 0)
        self.output_format_combo.blockSignals(False)

        align = Qt.AlignmentFlag.AlignRight if self.services.i18n.is_rtl() else Qt.AlignmentFlag.AlignLeft
        self.title_label.setAlignment(align)
        self.description_label.setAlignment(align)
        self.summary_label.setAlignment(align)

        self.title_label.setText(self._pt("title", "Web Scraper"))
        self.description_label.setText(
            self._pt(
                "description",
                "Extract rows from public static HTML pages with CSS selectors, review them in-app, then optionally export the filtered results.",
            )
        )
        self.url_label.setText(self._pt("url.label", "Start URL"))
        self.item_selector_label.setText(self._pt("item_selector.label", "Item Selector"))
        self.title_selector_label.setText(self._pt("title_selector.label", "Title Selector"))
        self.link_selector_label.setText(self._pt("link_selector.label", "Link Selector"))
        self.text_selector_label.setText(self._pt("text_selector.label", "Text Selector"))
        self.next_selector_label.setText(self._pt("next_selector.label", "Next-Page Selector"))
        self.max_pages_label.setText(self._pt("max_pages.label", "Max Pages"))
        self.timeout_label.setText(self._pt("timeout.label", "Timeout (s)"))
        self.output_format_label.setText(self._pt("output_format.label", "Export Format"))
        self.url_input.setPlaceholderText(self._pt("url.placeholder", "https://example.com/articles"))
        self.item_selector_input.setPlaceholderText(self._pt("item_selector.placeholder", "article"))
        self.title_selector_input.setPlaceholderText(self._pt("title_selector.placeholder", "h2, .title"))
        self.link_selector_input.setPlaceholderText(self._pt("link_selector.placeholder", "a[href]"))
        self.text_selector_input.setPlaceholderText(self._pt("text_selector.placeholder", "p, .summary"))
        self.next_selector_input.setPlaceholderText(self._pt("next_selector.placeholder", "a.next"))
        self.run_button.setText(self._pt("run.button", "Run Scrape"))
        self.search_input.setPlaceholderText(self._pt("filter.placeholder", "Filter current results..."))
        self.table.setHorizontalHeaderLabels(
            [
                self._pt("table.title", "Title"),
                self._pt("table.page", "Page"),
                self._pt("table.link", "Link"),
                self._pt("table.text", "Text"),
            ]
        )
        if self._latest_result is None and not self._has_run:
            self.summary_label.setText(self._pt("summary.ready", "Enter a page URL, add at least one item selector, and run the scraper."))
        else:
            self._render_summary()
        self._render_selected_details()
        self._apply_theme_styles()

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.description_label,
            cards=(self.config_card, self.summary_card),
            summary_label=self.summary_label,
        )

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()

    def _current_output_format(self) -> str:
        return str(self.output_format_combo.currentData() or "json")

    def _filter_query(self) -> str:
        return self.search_input.text().strip().lower()

    def _visible_rows(self) -> list[dict[str, str]]:
        query = self._filter_query()
        if not query:
            return list(self._rows)
        visible: list[dict[str, str]] = []
        for row in self._rows:
            haystack = " ".join(str(row.get(key, "")) for key in ("title", "link", "text", "page_url", "source_url")).lower()
            if query in haystack:
                visible.append(row)
        return visible

    def _set_busy(self, busy: bool) -> None:
        for widget in (
            self.url_input,
            self.item_selector_input,
            self.title_selector_input,
            self.link_selector_input,
            self.text_selector_input,
            self.next_selector_input,
            self.max_pages_input,
            self.timeout_input,
            self.output_format_combo,
            self.search_input,
        ):
            widget.setEnabled(not busy)
        self.run_button.setEnabled(not busy)

    def _run(self) -> None:
        url = self.url_input.text().strip()
        item_selector = self.item_selector_input.text().strip()
        if not url:
            QMessageBox.warning(self, self._pt("dialog.missing.title", "Missing Input"), self._pt("dialog.missing.url", "Enter a page URL to scrape."))
            return
        if not item_selector:
            QMessageBox.warning(
                self,
                self._pt("dialog.missing.title", "Missing Input"),
                self._pt("dialog.missing.item_selector", "Enter a CSS selector for the items you want to extract."),
            )
            return

        self._has_run = True
        self._latest_result = None
        self._rows = []
        self.table.setRowCount(0)
        self.details_output.setPlainText("")
        self.summary_label.setText(self._pt("summary.running", "Scraping pages..."))
        self._set_busy(True)

        self.services.run_task(
            lambda context: run_web_scraper_task(
                context,
                self.services,
                self.plugin_id,
                url=url,
                item_selector=item_selector,
                title_selector=self.title_selector_input.text().strip(),
                link_selector=self.link_selector_input.text().strip(),
                text_selector=self.text_selector_input.text().strip(),
                next_selector=self.next_selector_input.text().strip(),
                max_pages=self.max_pages_input.value(),
                timeout_seconds=self.timeout_input.value(),
            ),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
            status_text=self._pt("summary.running", "Scraping pages..."),
        )

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self._latest_result = result
        self._rows = [dict(row) for row in result.get("rows", [])]
        self._refresh_results_view()
        count = int(result.get("count", 0))
        status = "SUCCESS" if count > 0 else "WARNING"
        self.services.record_run(
            self.plugin_id,
            status,
            self._pt(
                "log.task.success",
                "Scraped {count} item(s) from {pages} page(s).",
                count=str(count),
                pages=str(result.get("pages_visited", 0)),
            ),
        )

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", self._pt("error.unknown", "Unknown web scraping error.")) if isinstance(payload, dict) else str(payload)
        self.summary_label.setText(message)
        self.details_output.setPlainText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self._pt("log.error", "Web scraping failed."), "ERROR")

    def _finish_run(self) -> None:
        self._set_busy(False)

    def _refresh_results_view(self) -> None:
        visible_rows = self._visible_rows()
        self.table.setRowCount(0)
        for row_index, row in enumerate(visible_rows):
            self.table.insertRow(row_index)
            title_item = QTableWidgetItem(_preview_text(str(row.get("title", "")), limit=80))
            title_item.setData(Qt.ItemDataRole.UserRole, row_index)
            title_item.setToolTip(str(row.get("title", "")))
            page_item = QTableWidgetItem(_preview_text(str(row.get("page_url", "")), limit=80))
            page_item.setToolTip(str(row.get("page_url", "")))
            link_item = QTableWidgetItem(_preview_text(str(row.get("link", "")), limit=80))
            link_item.setToolTip(str(row.get("link", "")))
            text_item = QTableWidgetItem(_preview_text(str(row.get("text", "")), limit=140))
            text_item.setToolTip(str(row.get("text", "")))
            self.table.setItem(row_index, 0, title_item)
            self.table.setItem(row_index, 1, page_item)
            self.table.setItem(row_index, 2, link_item)
            self.table.setItem(row_index, 3, text_item)
        self._render_summary()
        if self.table.rowCount():
            self.table.setCurrentCell(0, 0)
        else:
            self.details_output.setPlainText(
                self._pt("details.empty", "Select a result row to inspect its source, page URL, link, and extracted text.")
                if self._rows
                else self._pt("summary.empty", "No matching items were extracted from the current scrape.")
            )

    def _selected_row(self) -> dict[str, str] | None:
        current_row = self.table.currentRow()
        visible_rows = self._visible_rows()
        if current_row < 0 or current_row >= len(visible_rows):
            return None
        return visible_rows[current_row]

    def _render_summary(self) -> None:
        if self._latest_result is None and not self._has_run:
            self.summary_label.setText(self._pt("summary.ready", "Enter a page URL, add at least one item selector, and run the scraper."))
            return
        if self._latest_result is None:
            self.summary_label.setText(self._pt("summary.running", "Scraping pages..."))
            return
        total_count = int(self._latest_result.get("count", 0))
        visible_count = len(self._visible_rows())
        self.summary_label.setText(
            self._pt(
                "summary.success",
                "Visited {pages} page(s) and extracted {count} item(s). The current filter shows {visible} row(s). Right-click the table to copy fields, open URLs, or export the visible results.",
                pages=str(self._latest_result.get("pages_visited", 0)),
                count=str(total_count),
                visible=str(visible_count),
            )
        )

    def _render_selected_details(self) -> None:
        row = self._selected_row()
        if row is None:
            if self.table.rowCount():
                self.details_output.setPlainText(self._pt("details.empty", "Select a result row to inspect its source, page URL, link, and extracted text."))
            return
        details = [
            f"{self._pt('details.source_url', 'Source URL')}: {row.get('source_url', '')}",
            f"{self._pt('details.page_url', 'Page URL')}: {row.get('page_url', '')}",
            f"{self._pt('details.link', 'Link')}: {row.get('link', '')}",
            "",
            f"{self._pt('details.title', 'Title')}:",
            str(row.get("title", "")) or self._pt("details.none", "(empty)"),
            "",
            f"{self._pt('details.text', 'Text')}:",
            str(row.get("text", "")) or self._pt("details.none", "(empty)"),
        ]
        self.details_output.setPlainText("\n".join(details))

    def _export_visible_results(self) -> None:
        visible_rows = self._visible_rows()
        if not visible_rows or self._latest_result is None:
            return
        try:
            export_path = export_scrape_results(
                visible_rows,
                output_dir=self.services.default_output_path() / "web_scraper",
                output_format=self._current_output_format(),
                source_url=str(self._latest_result.get("source_url", "")),
            )
        except Exception as exc:
            QMessageBox.warning(self, self._pt("dialog.export.title", "Export Failed"), self._pt("error.export", "The results could not be exported: {error}", error=str(exc)))
            return

        self.summary_label.setText(
            self._pt(
                "summary.exported",
                "Exported {count} visible row(s) to {path}.",
                count=str(len(visible_rows)),
                path=str(export_path),
            )
        )
        self.services.record_run(self.plugin_id, "SUCCESS", str(export_path)[:500])
        self.services.log(self._pt("log.export", "Web scraper results exported to {path}.", path=str(export_path)))

    def _show_context_menu(self, position) -> None:
        visible_rows = self._visible_rows()
        if not visible_rows:
            return
        item = self.table.itemAt(position)
        if item is not None:
            self.table.setCurrentItem(item)
        row = self._selected_row()
        menu = QMenu(self)
        open_source = menu.addAction(self._pt("context.open_source", "Open Source URL"))
        open_page = menu.addAction(self._pt("context.open_page", "Open Page URL"))
        open_link = menu.addAction(self._pt("context.open_link", "Open Extracted Link"))
        menu.addSeparator()
        copy_title = menu.addAction(self._pt("context.copy_title", "Copy Title"))
        copy_text = menu.addAction(self._pt("context.copy_text", "Copy Text"))
        copy_link = menu.addAction(self._pt("context.copy_link", "Copy Link"))
        menu.addSeparator()
        export_action = menu.addAction(self._pt("context.export", "Export Visible Results"))

        if row is None:
            open_source.setEnabled(False)
            open_page.setEnabled(False)
            open_link.setEnabled(False)
            copy_title.setEnabled(False)
            copy_text.setEnabled(False)
            copy_link.setEnabled(False)
        else:
            if not str(row.get("link", "")).strip():
                open_link.setEnabled(False)
                copy_link.setEnabled(False)

        chosen = menu.exec(self.table.viewport().mapToGlobal(position))
        if row is None:
            if chosen == export_action:
                self._export_visible_results()
            return
        if chosen == open_source:
            QDesktopServices.openUrl(QUrl(str(row.get("source_url", ""))))
        elif chosen == open_page:
            QDesktopServices.openUrl(QUrl(str(row.get("page_url", ""))))
        elif chosen == open_link:
            QDesktopServices.openUrl(QUrl(str(row.get("link", ""))))
        elif chosen == copy_title:
            QGuiApplication.clipboard().setText(str(row.get("title", "")))
        elif chosen == copy_text:
            QGuiApplication.clipboard().setText(str(row.get("text", "")))
        elif chosen == copy_link:
            QGuiApplication.clipboard().setText(str(row.get("link", "")))
        elif chosen == export_action:
            self._export_visible_results()
