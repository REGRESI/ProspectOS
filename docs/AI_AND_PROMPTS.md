# Vorschläge und KI

Ohne echte Provideranbindung sind Textvorschläge deterministische **Offline-Demo-Vorschläge**, keine KI-Generierung. Sie dürfen nur vorhandene Kontakt-/Unternehmensdaten verwenden und unbekannte Fakten nicht ergänzen. Entwurfserzeugung löst keinen Versand aus.

Noch nicht implementiert: externer LLM-Gateway, Modell-/Promptregistry, strukturierte Provider-Outputs, Token-/Kostenledger, workspacebezogene Budgets und echte Bildgenerierung. Es werden keine API-Schlüssel benötigt, um den lokalen Kern zu testen.

Vor einer späteren Anbindung: versionierte Prompts, strikt validierte Schemas, Timeout/Retry-Limits, Kostenobergrenzen, PII-Minimierung, Redaction, Anbieter-/Regionenfreigabe, Datenschutzvertrag und Auswertungen gegen Halluzinationen. Provider-Ausgaben und Webseiten bleiben nicht vertrauenswürdige Daten, nie ausführbare Anweisungen.
