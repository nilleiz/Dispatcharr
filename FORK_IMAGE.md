# Fork-Image `nillivanilli0815/dispatcharr-xmltv-original-air-date`

Dieses Fork-Repository baut ein Docker-Image aus dem **letzten stabilen
Upstream-Release** von Dispatcharr plus zwei eigenständigen Feature-Commits:

| Feature | Branch (genau ein Commit auf dem Release-Tag) |
| --- | --- |
| XMLTV original air date | `feature/epg-air-date-compatibility-v033-single-commit` |
| HDHR/Plex-Tunerkompatibilität | `feature/hdhr-plex-tuner-compat-v3` |

Basis-Image: fest auf `ghcr.io/dispatcharr/dispatcharr:${BASE_TAG}` (aktuell
`base-20261023144948`, die Basis des offiziellen 0.33.0). Der gleitende Tag
`base` ist seit 2026-11-03 Ubuntu 26.04 ohne `en_US.utf8`; bestehende
AIO-Datenbanken starten darauf nicht. Bei einem neuen Upstream-Release
`BASE_TAG` im Workflow bewusst anheben (der Workflow prüft die Locale vor dem Build).

## Wie das Image gebaut wird

Workflow: `.github/workflows/stable-xmltv-original-air-date.yml`

1. Ermittelt das letzte stabile Release von `Dispatcharr/Dispatcharr` und die
   aktuellen SHAs beider Feature-Branches.
2. Checkt den Release-Tag aus und cherry-pickt nacheinander den XMLTV- und den
   HDHR-Commit (übersprungen, falls Upstream den Patch schon enthält).
   Passt ein Commit nicht mehr sauber, schlägt der Lauf fehl: den betroffenen
   Feature-Branch auf den neuen Release-Tag rebasen (weiterhin genau ein Commit).
3. Führt fokussierte Backend-Tests (inkl. `apps.m3u.tests.test_tuner_count`,
   `apps.hdhr.tests`) sowie Frontend-Lint/Prettier/Tests aus.
4. Prüft, dass das Basis-Image `en_US.utf8` enthält.
5. Baut `linux/amd64` + `linux/arm64` und pusht nach Docker Hub als `:latest`,
   `:<release-tag>` und `:candidate-<release-tag>-<xmltv-sha12>-<hdhr-sha12>-<base-tag>`.

Auslöser: täglich 03:47 UTC, Push einer Änderung an der Workflow-Datei auf
`main`, oder manuell (`workflow_dispatch`, optional `force_rebuild`).
Ein neuer Build entsteht nur, wenn sich Release-Tag, Basis-Tag oder einer der
beiden Feature-SHAs geändert hat (sonst existiert der Candidate-Tag schon).
Pull Requests gegen `main` bauen nur zur Validierung (amd64, ohne Push).

Lokal nachbauen:

```bash
git clone --branch <release-tag> https://github.com/Dispatcharr/Dispatcharr.git src
cd src
git fetch https://github.com/nilleiz/Dispatcharr.git \
  feature/epg-air-date-compatibility-v033-single-commit feature/hdhr-plex-tuner-compat-v3
git cherry-pick <xmltv-sha> <hdhr-sha>
docker build -f docker/Dockerfile \
  --build-arg REPO_OWNER=dispatcharr --build-arg REPO_NAME=dispatcharr \
  --build-arg BASE_TAG=base-20261023144948 --build-arg BRANCH=<release-tag> \
  --build-arg REPO_URL=https://github.com/Dispatcharr/Dispatcharr \
  -t dispatcharr-xmltv-original-air-date:local .
```

Deployment erfolgt separat (Portainer).

## HDHR-/Plex-Einstellungen

Unter **Settings → Stream Settings** (gespeichert in der Settings-Gruppe
`stream_settings`). Sie gelten **nur für den HDHR-Emulator**
(`TunerCount` in `discover.json`), nicht für die Xtream-Codes-API.

| Einstellung | Schlüssel | Default | Wirkung |
| --- | --- | --- | --- |
| HDHR Max Tuner Count | `hdhr_max_tuner_count` | leer (automatisch) | Obergrenze für die gemeldete Tunerzahl – gilt für jede HDHR-URL, auch mit eigenem Tuner Count. |
| Count custom streams toward HDHR tuners | `hdhr_count_custom_streams` | an (bisheriges Verhalten) | Aus: Custom-Streams (z. B. Fallback-/Slate-Streams) erhöhen die automatische Tunerzahl nicht. |
| Count identical custom stream URLs once | `hdhr_dedupe_custom_stream_urls` | aus | An: Custom-Streams mit gleicher URL zählen nur einmal. |

Automatische Tunerzahl = Summe `max_streams` der aktiven M3U-Profile (bzw. 10,
wenn ein Profil unbegrenzt ist) + gezählte Custom-Streams, mindestens 1,
höchstens `hdhr_max_tuner_count`.

### Tunerzahl pro URL

Im HDHR-Popover (Channels → Links → HDHR) gibt es **Tuner Count**. Ein Wert hängt
`/tuners/<n>` an die generierte URL, z. B.
`http://<host>:<port>/hdhr/output_profile/3/tuners/8`. Clients mit dieser URL
bekommen genau diese Tunerzahl gemeldet, aber nie mehr als „HDHR Max Tuner
Count“ (ohne globales Max: nie mehr als die automatische Zahl). So bekommen
verschiedene Clients verschiedene Tunerzahlen. Die DeviceID ändert sich dadurch
nicht.

### DeviceID – Achtung, Identitätswechsel für Plex

Jede Instanz erzeugt einmalig eine zufällige 8-stellige Kennung (Settings-Key
`hdhr_identity`) und meldet daraus:

| URL | DeviceID |
| --- | --- |
| `/hdhr/` und `/hdhr/device.xml` | `dispatcharr-<id>` |
| `/hdhr/<kanalprofil>/` | `dispatcharr-<id>-<kanalprofil>` |
| `/hdhr/output_profile/<n>/` | `dispatcharr-<id>-<n>` |
| `/hdhr/<kanalprofil>/output_profile/<n>/` | `dispatcharr-<id>-<kanalprofil>-<n>` |

Vorher: `12345678` (Plex hielt das für die IP 0.188.97.78 und fragte jeden Tuner
per UDP 65001 einzeln ab) bzw. `dispatcharr-hdhr-…` – auf jeder Instanz gleich,
sodass zwei Dispatcharr-Server in einem Plex kollidierten. Die Kennung bleibt
über Neustarts/Updates gleich. Unter **Settings → Stream Settings → HDHR Device
ID** ist sie sichtbar und per **Regenerate** neu erzeugbar (nach dem Klonen einer
Instanz nötig, sonst erben beide dieselbe ID). Ein vorhandener HDHR-Device-Eintrag
setzt weiterhin eine feste ID für alle URLs.

Plex sieht nach dem Update **neue Geräte**: DVR in Plex einmal neu hinzufügen bzw.
Tuner neu zuordnen.
