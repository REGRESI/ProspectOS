# ProspectOS auf einem eigenen Server (EU)

Diese Anleitung bringt ProspectOS auf einen gemieteten Server, damit Heute, Posteingang und der Autopilot laufen, auch wenn dein Mac zugeklappt ist. **Nichts davon ist bisher gemietet oder gestartet.** Du entscheidest, ob und wann.

## Was du bekommst

- ProspectOS unter deiner eigenen Adresse mit HTTPS (Caddy holt das Zertifikat automatisch).
- Eine eigene Datenbank auf dem Server, nur intern erreichbar.
- Jede Nacht ein verschlüsseltes Backup auf einem zweiten Speicher außer Haus. Den Schlüssel zum Entschlüsseln hast nur du, nicht der Server.
- Ein Befehl zum Einrichten und Aktualisieren: `infra/deploy/setup-server.sh`.

## Kosten (ungefähr, vor der Bestellung beim Anbieter prüfen)

| Posten | Beispiel | ca. pro Monat |
| --- | --- | --- |
| Server, 2 CPU, 4 GB RAM, Standort Deutschland/Finnland | Hetzner Cloud CX22 o. ä. | 5 bis 8 € |
| Backup-Speicher außer Haus | Hetzner Storage Box (1 TB) o. ä. | 4 € |
| Domain bzw. Subdomain | bei deinem Domain-Anbieter | 0 bis 2 € |
| Login (Supabase, EU-Region) | Free-Tarif reicht für ein kleines Team | 0 € |
| **Summe** | | **ca. 10 bis 15 €** |

Die Beträge sind Erfahrungswerte, keine geprüften Angebote. Externe Dienste (OpenAI, Brave) kosten wie bisher nach Verbrauch und erscheinen im Kostenkonto.

## Einmalig vorbereiten

1. **Server mieten** (Ubuntu 24.04, Standort EU). SSH-Schlüssel hinterlegen.
2. **Domain:** einen DNS-Eintrag `A` (und ggf. `AAAA`) von z. B. `app.cleanstar-dienstleistungen.de` auf die IP des Servers setzen.
3. **Supabase-Projekt** in der Region Frankfurt anlegen. Du brauchst URL, „anon key“ und den Issuer (`https://<projekt>.supabase.co/auth/v1`). Der lokale Demo-Login ist auf dem Server bewusst abgeschaltet.
4. **Backup-Schlüssel auf deinem Mac erzeugen** (nicht auf dem Server):
   ```bash
   age-keygen -o ~/prospectos-backup-key.txt
   ```
   Die Zeile `# public key: age1…` brauchst du gleich. Die Datei selbst sicher aufbewahren (z. B. Passwortmanager). Ohne sie lässt sich kein Backup öffnen.
5. **Backup-Speicher:** Storage Box bestellen und auf dem Server später mit `rclone config` als Remote `storagebox` (SFTP) eintragen.

## Einrichten (ein Befehl, zweimal)

Auf dem Server als root:

```bash
git clone --branch claude/v3-multichannel https://github.com/REGRESI/ProspectOS.git /opt/prospectos/app
```

Das Repository ist privat: Für den Klon einen Deploy-Key mit Lesezugriff in GitHub anlegen oder ein Token nur für dieses Repository verwenden.

```bash
sudo bash /opt/prospectos/app/infra/deploy/setup-server.sh
```

Der erste Lauf installiert Docker, Firewall (nur 22, 80, 443), `age` und `rclone` und legt `/opt/prospectos/server.env` mit neuen Datenbank-Passwörtern und neuem Verschlüsselungsschlüssel an. Trag dort ein: `DOMAIN`, `ACME_EMAIL`, `APP_BASE_URL`, die drei `SUPABASE_*`-Werte, `BACKUP_AGE_RECIPIENT` (der öffentliche Schlüssel aus Schritt 4) und `BACKUP_REMOTE`. Dann denselben Befehl noch einmal: Er baut alles, startet hinter HTTPS, führt die Migrationen aus und aktiviert das tägliche Backup um 03:15 UTC.

Einmal sofort testen:

```bash
sudo systemctl start prospectos-backup.service
```

```bash
sudo journalctl -u prospectos-backup.service -n 20
```

## Daten vom Mac übernehmen

Auf dem Mac (im Ordner ProspectOS, Container laufen):

```bash
docker compose exec -T db pg_dump -U prospectos -d prospectos -Fc --no-owner > prospectos-mac.dump
```

```bash
age -r "$(grep -o 'age1[0-9a-z]*' ~/prospectos-backup-key.txt)" -o prospectos-mac.dump.age prospectos-mac.dump && rm prospectos-mac.dump
```

Die verschlüsselte Datei per `scp` in einen Ordner auf dem Server kopieren (z. B. `/root/umzug/db-mac.dump.age`), dazu den privaten Schlüssel nur für diesen Moment, dann:

```bash
sudo /opt/prospectos/app/infra/deploy/restore.sh /root/umzug /root/umzug/key.txt --switch
```

Danach den Schlüssel vom Server löschen. Die Datenbank-Anmeldung auf dem Server läuft über Supabase: Lege dort Nutzer mit denselben E-Mail-Adressen an wie auf dem Mac.

## Wiederherstellen (Notfall)

```bash
sudo /opt/prospectos/app/infra/deploy/restore.sh 2026-11-08T0315Z /pfad/zu/key.txt
```

Das stellt in eine zweite Datenbank `prospectos_restore` her und zeigt Firmen, Kontakte und Migrationsstand. Erst mit `--switch` wird sie live; die alte bleibt als `prospectos_before_restore_<Zeit>` erhalten. Die Assets (Bilder) liegen im Backup als `assets-*.tar.gz.age`.

**Geprüft in der Entwicklung:** `infra/scripts/test-backup-restore.sh` legt eine Datenbank an, migriert und füllt sie, sichert sie verschlüsselt mit `age`, stellt sie in eine zweite Datenbank wieder her und vergleicht alle Tabellen (Ergebnis 08.11.2026: 76 Tabellen identisch, Migration 0026, RLS und Code-Funktion vorhanden). Auf einem echten Server wurde das noch nicht ausgeführt.

## Was sich mit dem Server ändert

- **LinkedIn-App:** In den „Authorized redirect URLs“ zusätzlich `https://<DOMAIN>/v1/integrations/linkedin/callback` eintragen und `LINKEDIN_REDIRECT_URI` in `server.env` genau so setzen. Die bisherige `http://localhost:3000/...` kann für den Mac bleiben.
- **QR-Codes in Briefen:** Sobald `APP_BASE_URL` mit `https://` gesetzt ist, zeigen neue Briefe auf `https://<DOMAIN>/r/<code>`. ProspectOS zählt den Scan selbst und leitet auf die Website weiter. Bereits gedruckte Briefe zeigen weiter direkt auf die Website mit `?ref=<code>`.
- **Login:** über Supabase statt Demo-Login.
- **Autopilot und Erinnerungen** laufen im Worker-Container, unabhängig vom Mac.

## Aktualisieren

```bash
sudo bash /opt/prospectos/app/infra/deploy/setup-server.sh
```

Holt den Branch, baut neu, führt neue Migrationen aus und startet neu. Vorher läuft nichts automatisch zurück: bei Problemen das letzte Backup mit `restore.sh` prüfen.

## Healthchecks

Datenbank (`pg_isready`), API (`/health/ready`) und Web werden von Docker überwacht und bei Ausfall neu gestartet (`restart: unless-stopped`). `docker compose ps` zeigt den Zustand; `/opt/prospectos/last-backup-ok` enthält den Zeitpunkt des letzten erfolgreichen Backups.
