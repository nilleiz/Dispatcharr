# Fork-Image `nillivanilli0815/dispatcharr-xmltv-original-air-date`

Dieses Fork-Repository baut ein Docker-Image aus dem **letzten stabilen
Upstream-Release** von Dispatcharr plus zwei eigenständigen Feature-Commits:

| Feature | Branch (genau ein Commit auf dem Release-Tag) |
| --- | --- |
| XMLTV original air date | `feature/epg-air-date-compatibility-v033-single-commit` |
| HDHR/Plex-Tunerkompatibilität | `feature/hdhr-plex-tuner-compat` |

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
4. Baut `linux/amd64` + `linux/arm64` und pusht nach Docker Hub als `:latest`,
   `:<release-tag>` und `:candidate-<release-tag>-<xmltv-sha12>-<hdhr-sha12>`.

Auslöser: täglich 03:47 UTC, Push einer Änderung an der Workflow-Datei auf
`main`, oder manuell (`workflow_dispatch`, optional `force_rebuild`).
Ein neuer Build entsteht nur, wenn sich Release-Tag oder einer der beiden
Feature-SHAs geändert hat (sonst existiert der Candidate-Tag schon).
Pull Requests gegen `main` bauen nur zur Validierung (amd64, ohne Push).

Lokal nachbauen:

```bash
git clone --branch <release-tag> https://github.com/Dispatcharr/Dispatcharr.git src
cd src
git fetch https://github.com/nilleiz/Dispatcharr.git \
  feature/epg-air-date-compatibility-v033-single-commit feature/hdhr-plex-tuner-compat
git cherry-pick <xmltv-sha> <hdhr-sha>
docker build -f docker/Dockerfile \
  --build-arg REPO_OWNER=dispatcharr --build-arg REPO_NAME=dispatcharr \
  --build-arg BASE_TAG=base --build-arg BRANCH=<release-tag> \
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
| HDHR Max Tuner Count | `hdhr_max_tuner_count` | leer (automatisch) | Obergrenze für die gemeldete Tunerzahl. |
| Count custom streams toward HDHR tuners | `hdhr_count_custom_streams` | an (bisheriges Verhalten) | Aus: Custom-Streams (z. B. Fallback-/Slate-Streams) erhöhen die automatische Tunerzahl nicht. |
| Count identical custom stream URLs once | `hdhr_dedupe_custom_stream_urls` | aus | An: Custom-Streams mit gleicher URL zählen nur einmal. |

Automatische Tunerzahl = Summe `max_streams` der aktiven M3U-Profile (bzw. 10,
wenn ein Profil unbegrenzt ist) + gezählte Custom-Streams, mindestens 1,
höchstens `hdhr_max_tuner_count`.

### DeviceID – Achtung, Identitätswechsel für Plex

Ohne HDHR-Device-Eintrag meldet der Emulator jetzt `DeviceID: dispatcharr`
(vorher `12345678`; Plex hielt das für die IP 0.188.97.78 und fragte jeden Tuner
per UDP 65001 einzeln ab). `device.xml` nutzt nun dieselbe ID wie
`discover.json`. Vorhandene HDHR-Device-Einträge und profilbezogene IDs
(`dispatcharr-hdhr-…`) bleiben unverändert.

Plex sieht nach dem Update ein **neues Gerät**: DVR in Plex einmal neu
hinzufügen bzw. Tuner neu zuordnen. Wer die alte Identität behalten will, legt
einen HDHR-Device-Eintrag mit Device-ID `12345678` an (dann bleibt aber auch das
IP-Fehlverhalten in Plex bestehen).
