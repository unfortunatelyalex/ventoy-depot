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
        "assign_iso": "Assign ISO",
        "assign_title": "Assign highlighted ISO",
        "assign_help": (
            "Use this only for a renamed ISO from a supported product. The assignment is "
            "bound to this file's SHA-256; changing the file invalidates it."
        ),
        "provider_product": "Product",
        "edition": "Edition (optional unless required by the product)",
        "flavor": "Flavor (optional)",
        "channel": "Channel",
        "architecture": "Architecture",
        "language": "Language (optional)",
        "installed_version": "Installed version (required)",
        "build_optional": "Build (optional)",
        "save_assignment": "Save assignment",
        "assignment_required": "Product, version, channel and architecture are required.",
        "scan_before_assign": "Check updates first, then highlight an unknown ISO.",
        "already_identified": "{name} is already identified automatically.",
        "saving_assignment": "Hashing the ISO and saving its assignment…",
        "assignment_saved": "Assignment saved; rebuilding the update plan…",
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
        "assign_iso": "ISO zuordnen",
        "assign_title": "Markierte ISO zuordnen",
        "assign_help": (
            "Nur für eine umbenannte ISO eines unterstützten Produkts verwenden. Die Zuordnung "
            "wird an den SHA-256-Hash dieser Datei gebunden und bei Änderungen ungültig."
        ),
        "provider_product": "Produkt",
        "edition": "Edition (optional, sofern das Produkt sie nicht benötigt)",
        "flavor": "Variante (optional)",
        "channel": "Kanal",
        "architecture": "Architektur",
        "language": "Sprache (optional)",
        "installed_version": "Installierte Version (erforderlich)",
        "build_optional": "Build (optional)",
        "save_assignment": "Zuordnung speichern",
        "assignment_required": "Produkt, Version, Kanal und Architektur sind erforderlich.",
        "scan_before_assign": "Zuerst Updates prüfen und dann eine unbekannte ISO markieren.",
        "already_identified": "{name} wurde bereits automatisch erkannt.",
        "saving_assignment": "ISO wird gehasht und ihre Zuordnung gespeichert…",
        "assignment_saved": "Zuordnung gespeichert; Updateplan wird neu erstellt…",
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
