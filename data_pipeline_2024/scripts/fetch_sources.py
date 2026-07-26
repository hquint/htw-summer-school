"""Download official source files for the HTW 2024 teaching dataset.

The script uses the Python standard library plus the system ``curl`` command,
so it can run before the project's analytical dependencies are installed.
"""

from __future__ import annotations

import base64
import json
import subprocess
import time
import urllib.parse
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PIPELINE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = PIPELINE_DIR / "raw"
BERLIN_TZ = ZoneInfo("Europe/Berlin")
USER_AGENT = "HTW-Summer-School-Data-Pipeline/1.0"

SLP_SOURCES = {
    "HB": (
        "https://www.stromnetz.berlin/files/globalassets/dokumente/"
        "netz-nutzen/lastprofile/standardlastprofil-haushalte-2024.xlsx"
    ),
    "GB": (
        "https://www.stromnetz.berlin/files/globalassets/dokumente/"
        "netz-nutzen/lastprofile/"
        "standardlastprofil-gewerbe-allgemein-2024.xlsx"
    ),
    "LB": (
        "https://www.stromnetz.berlin/files/globalassets/dokumente/"
        "netz-nutzen/lastprofile/"
        "standardlastprofil-landwirtschaftsbetriebe-2024.xlsx"
    ),
}

SMARD_FILTER = 4169
SMARD_REGION = "DE"
SMARD_YEARS = (2019, 2020, 2021, 2022, 2024)


def fetch_bytes(url: str, attempts: int = 4) -> bytes:
    for attempt in range(1, attempts + 1):
        try:
            return subprocess.run(
                [
                    "curl",
                    "-L",
                    "--fail",
                    "--silent",
                    "--show-error",
                    "--max-time",
                    "90",
                    "--user-agent",
                    USER_AGENT,
                    url,
                ],
                check=True,
                capture_output=True,
            ).stdout
        except subprocess.CalledProcessError:
            if attempt == attempts:
                raise
            time.sleep(attempt)
    raise RuntimeError("unreachable")


def download_file(url: str, destination: Path) -> None:
    if destination.exists() and destination.stat().st_size > 0:
        print(f"exists: {destination.relative_to(PIPELINE_DIR)}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(fetch_bytes(url))
    print(f"downloaded: {destination.relative_to(PIPELINE_DIR)}")


def fetch_slp_workbooks() -> None:
    target_dir = RAW_DIR / "stromnetz_berlin"
    for code, url in SLP_SOURCES.items():
        download_file(url, target_dir / f"slp_{code}_2024.xlsx")


def smard_chunk_overlaps_year(timestamp_ms: int, year: int) -> bool:
    chunk_start = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
    local_start = datetime(year, 1, 1, tzinfo=BERLIN_TZ)
    local_end = datetime(year + 1, 1, 1, tzinfo=BERLIN_TZ)
    return (
        chunk_start < local_end.astimezone(UTC) + timedelta(days=7)
        and chunk_start >= local_start.astimezone(UTC) - timedelta(days=7)
    )


def fetch_smard_year(year: int, index_timestamps: list[int]) -> None:
    output = RAW_DIR / "smard" / f"day_ahead_{year}.json"
    if output.exists() and output.stat().st_size > 0:
        print(f"exists: {output.relative_to(PIPELINE_DIR)}")
        return

    selected = [
        timestamp_ms
        for timestamp_ms in index_timestamps
        if smard_chunk_overlaps_year(timestamp_ms, year)
    ]
    observations: dict[int, float | None] = {}
    for number, timestamp_ms in enumerate(selected, start=1):
        url = (
            f"https://www.smard.de/app/chart_data/{SMARD_FILTER}/"
            f"{SMARD_REGION}/{SMARD_FILTER}_{SMARD_REGION}_hour_"
            f"{timestamp_ms}.json"
        )
        payload = json.loads(fetch_bytes(url))
        for timestamp, value in payload["series"]:
            local_year = datetime.fromtimestamp(
                timestamp / 1000, tz=UTC
            ).astimezone(BERLIN_TZ).year
            if local_year == year:
                observations[int(timestamp)] = value
        print(f"SMARD {year}: {number}/{len(selected)} chunks", end="\r")

    rows = [[timestamp, observations[timestamp]] for timestamp in sorted(observations)]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "source": "Bundesnetzagentur | SMARD.de",
                "source_url": (
                    f"https://www.smard.de/app/chart_data/{SMARD_FILTER}/"
                    f"{SMARD_REGION}/index_hour.json"
                ),
                "filter": SMARD_FILTER,
                "region": SMARD_REGION,
                "resolution": "hour",
                "local_delivery_year": year,
                "series": rows,
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    print(f"downloaded: {output.relative_to(PIPELINE_DIR)} ({len(rows)} rows)")


def fetch_smard() -> None:
    index_url = (
        f"https://www.smard.de/app/chart_data/{SMARD_FILTER}/"
        f"{SMARD_REGION}/index_hour.json"
    )
    index_payload = json.loads(fetch_bytes(index_url))
    for year in SMARD_YEARS:
        fetch_smard_year(year, index_payload["timestamps"])


def rebap_download_url() -> str:
    settings = {
        "DataType": 20,
        "ProduktId": 10,
        "CultureName": "de-DE",
        "Title": "reBAP unterdeckt",
        "DiagramType": "line",
        "TimeInterval": 15,
        "DataUnit": "EUR/MWh",
        "CsvColumns": ["50Hertz", "Amprion", "TenneT TSO", "TransnetBW"],
        "TsoIds": [0],
        "NrvDirection": 0,
        "WebApiRoute": "NrvSaldo/rebap/qualitaetsgesichert",
        "WebApiBaseUri": (
            "https://lotes-UNB-svc-netzt.corp.transmission-it.de/StatistikApi/"
        ),
    }
    request_payload = {
        "LocalFrom": "2024-01-01",
        "LocalTo": "2025-01-01",
        "ResultTimeZone": "utc",
        "Settings": settings,
    }
    encoded = base64.b64encode(
        json.dumps(request_payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return (
        "https://www.netztransparenz.de/DesktopModules/LotesCharts/"
        "CsvDownloadHandler.ashx?request="
        + urllib.parse.quote(encoded)
    )


def fetch_rebap() -> None:
    download_file(
        rebap_download_url(),
        RAW_DIR / "netztransparenz" / "rebap_2024_utc.csv",
    )


def write_source_manifest() -> None:
    manifest = {
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "sources": [
            {
                "dataset": "Berlin SLP HB, GB, LB",
                "publisher": "Stromnetz Berlin GmbH",
                "status": "observed",
                "urls": list(SLP_SOURCES.values()),
            },
            {
                "dataset": "DE/LU Day-Ahead prices",
                "publisher": "Bundesnetzagentur | SMARD.de",
                "status": "observed",
                "url": (
                    f"https://www.smard.de/app/chart_data/{SMARD_FILTER}/"
                    f"{SMARD_REGION}/index_hour.json"
                ),
            },
            {
                "dataset": "Quality-assured reBAP",
                "publisher": "Netztransparenz / German TSOs",
                "status": "observed",
                "url": (
                    "https://www.netztransparenz.de/Regelenergie/"
                    "Ausgleichsenergiepreis/reBAP"
                ),
            },
        ],
    }
    output = RAW_DIR / "source_manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote: {output.relative_to(PIPELINE_DIR)}")


def main() -> None:
    fetch_slp_workbooks()
    fetch_smard()
    fetch_rebap()
    write_source_manifest()
    print("Source download complete.")


if __name__ == "__main__":
    main()
