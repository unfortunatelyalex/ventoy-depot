from __future__ import annotations

_MESSAGES = {
    "en": {
        "title": "Ventoy Depot",
        "choose_device": "Choose a detected Ventoy drive.",
        "no_devices": "No mounted Ventoy drive found.",
        "refresh": "Refresh devices",
        "scan": "Scan ISOs",
        "deprecated": "ventoy-iso-updater is deprecated; use ventoy-depot.",
    },
    "de": {
        "title": "Ventoy Depot",
        "choose_device": "Wähle ein erkanntes Ventoy-Laufwerk.",
        "no_devices": "Kein eingehängtes Ventoy-Laufwerk gefunden.",
        "refresh": "Laufwerke suchen",
        "scan": "ISOs prüfen",
        "deprecated": "ventoy-iso-updater ist veraltet; bitte ventoy-depot verwenden.",
    },
}


def translate(key: str, language: str = "en") -> str:
    return _MESSAGES.get(language, _MESSAGES["en"]).get(key, _MESSAGES["en"].get(key, key))
