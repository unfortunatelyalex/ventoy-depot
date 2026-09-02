from __future__ import annotations

_MESSAGES = {
    "en": {
        "title": "Ventoy Depot",
        "choose_device": "Choose a detected Ventoy drive.",
        "no_devices": "No mounted Ventoy drive found.",
        "refresh": "Refresh devices",
        "scan": "Scan ISOs",
        "check_updates": "Check updates",
        "update_selected": "Update selected",
        "checking_metadata": "Checking official release metadata…",
        "updates_found": (
            "Update plan ready: {count} update(s) selected. Press Space to toggle a row."
        ),
        "confirm_title": "Confirm complete update plan",
        "keep_old": (
            "Existing ISOs remain on the drive. New files become visible only after verification."
        ),
        "start_updates": "Download and install",
        "cancel": "Cancel",
        "updating": "Downloading and verifying selected ISOs…",
        "run_finished": "Update run finished.",
        "deprecated": "ventoy-iso-updater is deprecated; use ventoy-depot.",
    },
    "de": {
        "title": "Ventoy Depot",
        "choose_device": "Wähle ein erkanntes Ventoy-Laufwerk.",
        "no_devices": "Kein eingehängtes Ventoy-Laufwerk gefunden.",
        "refresh": "Laufwerke suchen",
        "scan": "ISOs prüfen",
        "check_updates": "Updates prüfen",
        "update_selected": "Auswahl aktualisieren",
        "checking_metadata": "Offizielle Release-Metadaten werden geprüft…",
        "updates_found": (
            "Updateplan bereit: {count} Update(s) ausgewählt. Leertaste ändert die Auswahl."
        ),
        "confirm_title": "Vollständigen Updateplan bestätigen",
        "keep_old": (
            "Bestehende ISOs bleiben erhalten. Neue Dateien werden erst nach der Prüfung sichtbar."
        ),
        "start_updates": "Herunterladen und installieren",
        "cancel": "Abbrechen",
        "updating": "Ausgewählte ISOs werden heruntergeladen und geprüft…",
        "run_finished": "Update-Lauf abgeschlossen.",
        "deprecated": "ventoy-iso-updater ist veraltet; bitte ventoy-depot verwenden.",
    },
}


def translate(key: str, language: str = "en") -> str:
    return _MESSAGES.get(language, _MESSAGES["en"]).get(key, _MESSAGES["en"].get(key, key))
