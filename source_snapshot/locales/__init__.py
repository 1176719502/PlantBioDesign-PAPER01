"""Locale dictionaries for BioDesign Studio.

The dictionaries are intentionally plain mappings so every Streamlit surface
can resolve copy through :mod:`core.i18n` without introducing a second UI
translation mechanism.
"""

from .en import TRANSLATIONS as EN_TRANSLATIONS
from .zh_cn import TRANSLATIONS as ZH_CN_TRANSLATIONS

# Keep the zh-CN surface total even for repository-native keys that predate the
# frozen V1 inventory. Missing Chinese entries fall back to the approved
# English value through the central resolver rather than leaking a key name.
ZH_CN_COMPLETE_TRANSLATIONS = dict(EN_TRANSLATIONS)
ZH_CN_COMPLETE_TRANSLATIONS.update(ZH_CN_TRANSLATIONS)

LOCALES = {
    "en": EN_TRANSLATIONS,
    "zh-CN": ZH_CN_COMPLETE_TRANSLATIONS,
}
