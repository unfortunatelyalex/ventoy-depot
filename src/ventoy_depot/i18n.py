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
        "replace_old": "Replace old ISO",
        "replace_unavailable": "The highlighted ISO cannot be replaced automatically.",
        "assign_iso": "Assign ISO",
        "add_iso": "Add new ISO",
        "add_title": "Add a new official ISO",
        "add_help": (
            "Choose the exact product variant. Ventoy Depot resolves and verifies the latest "
            "matching official release before it writes anything."
        ),
        "prepare_add": "Prepare download plan",
        "add_required": "Channel and architecture are required.",
        "no_add_providers": "No downloadable providers are available.",
        "resolving_new_iso": "Resolving the selected official ISO…",
        "verify_iso": "Verify ISO",
        "verifying_iso": "Hashing the highlighted ISO…",
        "verify_missing": "The highlighted row has no existing local ISO.",
        "verify_match": "VERIFIED: checksum matches the current official release.",
        "verify_mismatch": "FAILED: checksum does not match the current official release.",
        "verify_hash_only": (
            "HASHED: no matching historical official checksum is available automatically."
        ),
        "assign_title": "Assign highlighted ISO",
        "assign_help": (
            "Use this only for a renamed ISO from a supported product. The assignment is "
            "bound to this file's SHA-256; changing the file invalidates it."
        ),
        "volume_id_hint": "Read-only ISO volume identifier: {volume_id}",
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
        "replace_warning": (
            "Items marked REPLACE move the old ISO to .ventoy-depot/trash only after the new "
            "copy has been verified."
        ),
        "start_updates": "Download and install",
        "cancel": "Cancel",
        "cancel_run": "Cancel update",
        "retry_failed": "Retry failed",
        "empty_trash": "Empty trash",
        "empty_trash_title": "Permanently empty Ventoy Depot trash",
        "empty_trash_warning": (
            "This permanently deletes {count} previously replaced ISO file(s) ({size}). "
            "This cannot be undone."
        ),
        "empty_trash_confirm": "Permanently delete",
        "empty_trash_empty": "The Ventoy Depot trash is empty.",
        "emptying_trash": "Permanently deleting confirmed trash files…",
        "trash_emptied": "Permanently deleted {count} file(s) from the Ventoy Depot trash.",
        "settings": "Settings",
        "settings_title": "Ventoy Depot settings",
        "language_setting": "Interface language",
        "registry_updates": "Check the signed registry for updates",
        "download_cache": "Keep verified downloads for resume and retry",
        "proxy_setting": "HTTPS proxy (optional; credentials are not stored)",
        "parallelism_setting": "Parallel metadata requests (1-16)",
        "default_action_setting": "Default plan selection",
        "default_add": "Select safe additions",
        "default_skip": "Select nothing",
        "local_manifests_setting": "Enabled local manifests (one absolute path per line)",
        "save_settings": "Save settings",
        "settings_saved": "Settings saved. Labels use the selected language after restart.",
        "cancelling": "Cancelling safely after the current data block…",
        "cancelled": "Cancelled by the user.",
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
        "replace_old": "Alte ISO ersetzen",
        "replace_unavailable": "Die markierte ISO kann nicht automatisch ersetzt werden.",
        "assign_iso": "ISO zuordnen",
        "add_iso": "Neue ISO hinzufügen",
        "add_title": "Neue offizielle ISO hinzufügen",
        "add_help": (
            "Wähle die genaue Produktvariante. Ventoy Depot ermittelt und prüft das neueste "
            "passende offizielle Release, bevor etwas geschrieben wird."
        ),
        "prepare_add": "Downloadplan erstellen",
        "add_required": "Kanal und Architektur sind erforderlich.",
        "no_add_providers": "Es sind keine herunterladbaren Provider verfügbar.",
        "resolving_new_iso": "Die ausgewählte offizielle ISO wird ermittelt…",
        "verify_iso": "ISO verifizieren",
        "verifying_iso": "Die markierte ISO wird gehasht…",
        "verify_missing": "Für die markierte Zeile existiert noch keine lokale ISO.",
        "verify_match": "VERIFIZIERT: Prüfsumme entspricht dem aktuellen offiziellen Release.",
        "verify_mismatch": (
            "FEHLGESCHLAGEN: Prüfsumme entspricht nicht dem aktuellen offiziellen Release."
        ),
        "verify_hash_only": (
            "GEHASHT: Eine passende historische offizielle Prüfsumme ist nicht automatisch "
            "verfügbar."
        ),
        "assign_title": "Markierte ISO zuordnen",
        "assign_help": (
            "Nur für eine umbenannte ISO eines unterstützten Produkts verwenden. Die Zuordnung "
            "wird an den SHA-256-Hash dieser Datei gebunden und bei Änderungen ungültig."
        ),
        "volume_id_hint": "Read-only erkannte ISO-Datenträgerkennung: {volume_id}",
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
        "replace_warning": (
            "Bei REPLACE wird die alte ISO erst nach erfolgreicher Prüfung der neuen Kopie nach "
            ".ventoy-depot/trash verschoben."
        ),
        "start_updates": "Herunterladen und installieren",
        "cancel": "Abbrechen",
        "cancel_run": "Update abbrechen",
        "retry_failed": "Fehler erneut versuchen",
        "empty_trash": "Papierkorb leeren",
        "empty_trash_title": "Ventoy-Depot-Papierkorb endgültig leeren",
        "empty_trash_warning": (
            "Dadurch werden {count} zuvor ersetzte ISO-Datei(en) ({size}) endgültig gelöscht. "
            "Dies kann nicht rückgängig gemacht werden."
        ),
        "empty_trash_confirm": "Endgültig löschen",
        "empty_trash_empty": "Der Ventoy-Depot-Papierkorb ist leer.",
        "emptying_trash": "Bestätigte Papierkorbdateien werden endgültig gelöscht…",
        "trash_emptied": (
            "{count} Datei(en) wurden endgültig aus dem Ventoy-Depot-Papierkorb gelöscht."
        ),
        "settings": "Einstellungen",
        "settings_title": "Ventoy-Depot-Einstellungen",
        "language_setting": "Sprache der Oberfläche",
        "registry_updates": "Signierte Registry auf Updates prüfen",
        "download_cache": "Verifizierte Downloads für Fortsetzung und Wiederholung behalten",
        "proxy_setting": "HTTPS-Proxy (optional; Zugangsdaten werden nicht gespeichert)",
        "parallelism_setting": "Parallele Metadatenabfragen (1–16)",
        "default_action_setting": "Standardauswahl im Updateplan",
        "default_add": "Sichere Ergänzungen auswählen",
        "default_skip": "Nichts auswählen",
        "local_manifests_setting": "Aktive lokale Manifeste (ein absoluter Pfad pro Zeile)",
        "save_settings": "Einstellungen speichern",
        "settings_saved": "Einstellungen gespeichert. Beschriftungen wechseln nach Neustart.",
        "cancelling": "Sicherer Abbruch nach dem aktuellen Datenblock…",
        "cancelled": "Vom Benutzer abgebrochen.",
        "updating": "Ausgewählte ISOs werden heruntergeladen und geprüft…",
        "run_finished": "Update-Lauf abgeschlossen.",
        "deprecated": "ventoy-iso-updater ist veraltet; bitte ventoy-depot verwenden.",
    },
}


def translate(key: str, language: str = "en") -> str:
    return _MESSAGES.get(language, _MESSAGES["en"]).get(key, _MESSAGES["en"].get(key, key))
