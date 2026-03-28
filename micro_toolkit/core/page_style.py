from __future__ import annotations

from PySide6.QtWidgets import QWidget

from micro_toolkit.core.theme import ThemePalette

SEMANTIC_CLASS_PROPERTY = "micro_class"


def surface_style(palette: ThemePalette, *, radius: int = 18, selector: str = "QFrame") -> str:
    return f"{selector} {{ background: {palette.card_bg}; border: none; border-radius: {radius}px; }}"


def card_style(palette: ThemePalette, *, radius: int = 18) -> str:
    return surface_style(palette, radius=radius, selector="QFrame")


def widget_card_style(palette: ThemePalette, *, radius: int = 18) -> str:
    return surface_style(palette, radius=radius, selector="QWidget")


def label_surface_style(palette: ThemePalette, *, radius: int = 18) -> str:
    return surface_style(palette, radius=radius, selector="QLabel")


def tinted_card_style(
    palette: ThemePalette,
    *,
    background: str,
    border: str | None = None,
    radius: int = 22,
) -> str:
    _ = border or palette.border
    return f"QFrame {{ background: {background}; border: none; border-radius: {radius}px; }}"


def apply_semantic_class(widget: QWidget | None, semantic_class: str | None) -> None:
    if widget is None:
        return
    widget.setProperty(SEMANTIC_CLASS_PROPERTY, semantic_class or "")
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


def page_title_style(palette: ThemePalette, *, size: int = 30, weight: int = 800) -> str:
    return f"font-size: {size}px; font-weight: {weight}; color: {palette.text_primary};"


def section_title_style(palette: ThemePalette, *, size: int = 18, weight: int = 700) -> str:
    return f"font-size: {size}px; font-weight: {weight}; color: {palette.text_primary};"


def body_text_style(palette: ThemePalette, *, size: int = 14, weight: int = 400) -> str:
    return f"font-size: {size}px; font-weight: {weight}; color: {palette.text_primary};"


def muted_text_style(palette: ThemePalette, *, size: int = 14, weight: int = 400, extra: str = "") -> str:
    suffix = f" {extra.strip()}" if extra and extra.strip() else ""
    return f"font-size: {size}px; font-weight: {weight}; color: {palette.text_muted};{suffix}"


def apply_page_chrome(
    palette: ThemePalette,
    *,
    title_label=None,
    description_label=None,
    cards: tuple | list = (),
    summary_label=None,
    title_size: int = 26,
    title_weight: int = 700,
    description_size: int = 14,
    description_weight: int = 400,
    summary_size: int = 13,
    summary_weight: int = 400,
    card_radius: int = 14,
) -> None:
    if title_label is not None:
        title_label.setStyleSheet(page_title_style(palette, size=title_size, weight=title_weight))
    if description_label is not None:
        description_label.setStyleSheet(muted_text_style(palette, size=description_size, weight=description_weight))
    for card in cards or ():
        if card is not None:
            card.setStyleSheet(card_style(palette, radius=card_radius))
    if summary_label is not None:
        summary_label.setStyleSheet(muted_text_style(palette, size=summary_size, weight=summary_weight))
