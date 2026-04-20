#!/usr/bin/env python3
"""Sync selected upstream Nuvio scraper files into Doom-plug.

This script intentionally preserves Doom-plug local customizations:
- domain lookups stay pointed at Doom-plug's own domains.json
- HindMoviez keeps direct URLs instead of the upstream worker proxy
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "manifest.json"
PR_BODY_PATH = Path(
    os.environ.get("PR_BODY_PATH", str(REPO_ROOT / ".git" / "upstream-sync-pr-body.md"))
)
ANCHOR_DATE = date(2026, 4, 20)
CADENCE_DAYS = 4
UPSTREAM_RAW_BASE = "https://raw.githubusercontent.com/D3adlyRocket/All-in-One-Nuvio/main"
DOOM_DOMAINS_URL = "https://raw.githubusercontent.com/ummarm/Doom-plug/main/domains.json"
USER_AGENT = "Doom-plug upstream sync"


@dataclass(frozen=True)
class Provider:
    scraper_id: str
    relative_path: str

    @property
    def local_path(self) -> Path:
        return REPO_ROOT / self.relative_path

    @property
    def upstream_url(self) -> str:
        return f"{UPSTREAM_RAW_BASE}/{self.relative_path}"


PROVIDERS = (
    Provider("4khdhub", "providers/4khdhub.js"),
    Provider("4khdhubtv", "providers/4khdhub_tv.js"),
    Provider("hdhub4u", "providers/hdhub4u.js"),
    Provider("hindmoviez", "providers/hindmoviez.js"),
)


def write_output(name: str, value: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        return
    with open(github_output, "a", encoding="utf-8") as fh:
        fh.write(f"{name}={value}\n")


def write_summary(lines: list[str]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def patch_domain_source(text: str) -> str:
    updated, count = re.subn(
        r'var DOMAINS_URL = "[^"]+";',
        f'var DOMAINS_URL = "{DOOM_DOMAINS_URL}";',
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("Could not retarget DOMAINS_URL to Doom-plug domains.json")
    return updated


def patch_hindmoviez_source(text: str) -> str:
    text = re.sub(
        r"// ── Cloudflare Worker proxy[\s\S]*?const DEFAULT_HEADERS = \{",
        "const DEFAULT_HEADERS = {",
        text,
        count=1,
    )
    updated, count = re.subn(
        r"((?:var|const|let)\s+proxiedUrl\s*=\s*)hmProxyUrl\(url\);",
        r"\1url;",
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("Could not switch HindMoviez away from hmProxyUrl(url)")
    return updated


def transform_source(provider: Provider, text: str) -> str:
    if provider.scraper_id in {"4khdhub", "4khdhubtv", "hdhub4u"}:
        text = patch_domain_source(text)
    elif provider.scraper_id == "hindmoviez":
        text = patch_hindmoviez_source(text)
    return text.rstrip("\n") + "\n"


def bump_patch(version: str) -> str:
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"Expected semantic version x.y.z, got {version!r}")
    major, minor, patch = (int(part) for part in parts)
    return f"{major}.{minor}.{patch + 1}"


def update_manifest(changed_ids: set[str]) -> list[str]:
    with open(MANIFEST_PATH, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    version_changes: list[str] = []
    old_repo_version = manifest["version"]
    manifest["version"] = bump_patch(old_repo_version)
    version_changes.append(f"Doom-plug manifest: `{old_repo_version}` -> `{manifest['version']}`")

    for scraper in manifest.get("scrapers", []):
        if scraper.get("id") not in changed_ids:
            continue
        old_scraper_version = scraper["version"]
        scraper["version"] = bump_patch(old_scraper_version)
        version_changes.append(
            f"{scraper['name']}: `{old_scraper_version}` -> `{scraper['version']}`"
        )

    with open(MANIFEST_PATH, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")

    return version_changes


def write_pr_body(changed: list[Provider], version_changes: list[str], run_date: date) -> None:
    PR_BODY_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "## What changed",
        "",
        "This automated sync pulled the latest upstream versions of these Doom-plug scrapers:",
        "",
    ]
    for provider in changed:
        lines.append(f"- `{provider.scraper_id}` from `{provider.upstream_url}`")

    lines.extend(
        [
            "",
            "## Doom-plug local patches preserved",
            "",
            "- `4KHDHub`, `4khdhub-tv`, and `HDHub4u` still point at Doom-plug's own `domains.json`.",
            "- `HindMoviez` still uses direct resolved URLs instead of the upstream worker proxy.",
            "",
            "## Version bumps",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in version_changes)
    lines.extend(
        [
            "",
            "## Run info",
            "",
            f"- Checked on `{run_date.isoformat()}` UTC",
            f"- Upstream repo: `{UPSTREAM_RAW_BASE}`",
        ]
    )

    with open(PR_BODY_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def is_due_to_run(today_utc: date, force: bool) -> bool:
    if force:
        return True
    delta_days = (today_utc - ANCHOR_DATE).days
    return delta_days >= 0 and delta_days % CADENCE_DAYS == 0


def main() -> int:
    force = os.environ.get("FORCE_SYNC", "false").lower() == "true"
    today_utc = datetime.now(timezone.utc).date()

    if not is_due_to_run(today_utc, force):
        write_output("changed", "false")
        write_output("skipped", "true")
        write_summary(
            [
                "## Doom-plug upstream sync",
                "",
                f"Skipped on `{today_utc.isoformat()}` UTC because the 4-day cadence is anchored to `{ANCHOR_DATE.isoformat()}`.",
                "The workflow still runs daily so manual dispatch stays available, but real sync work only happens on cadence days unless `force` is enabled.",
            ]
        )
        print("Not on the 4-day sync cadence; skipping.")
        return 0

    changed_providers: list[Provider] = []

    for provider in PROVIDERS:
        upstream_text = fetch_text(provider.upstream_url)
        transformed_text = transform_source(provider, upstream_text)
        local_text = provider.local_path.read_text(encoding="utf-8")

        if transformed_text != local_text:
            provider.local_path.write_text(transformed_text, encoding="utf-8")
            changed_providers.append(provider)

    if not changed_providers:
        write_output("changed", "false")
        write_output("skipped", "false")
        write_summary(
            [
                "## Doom-plug upstream sync",
                "",
                f"No upstream changes were found for the tracked providers on `{today_utc.isoformat()}` UTC.",
            ]
        )
        print("No upstream changes detected.")
        return 0

    changed_ids = {provider.scraper_id for provider in changed_providers}
    version_changes = update_manifest(changed_ids)
    write_pr_body(changed_providers, version_changes, today_utc)

    changed_names = ",".join(provider.scraper_id for provider in changed_providers)
    write_output("changed", "true")
    write_output("skipped", "false")
    write_output("changed_scrapers", changed_names)
    write_summary(
        [
            "## Doom-plug upstream sync",
            "",
            f"Updated scrapers: `{changed_names}`",
            "",
            "Version bumps:",
            *[f"- {item}" for item in version_changes],
        ]
    )
    print(f"Updated providers: {changed_names}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
