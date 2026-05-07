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
from urllib.error import HTTPError
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
CADENCE_DAYS = 2
UPSTREAM_RAW_BASE = "https://raw.githubusercontent.com/D3adlyRocket/All-in-One-Nuvio/main"
UPSTREAM_TREE_API = "https://api.github.com/repos/D3adlyRocket/All-in-One-Nuvio/git/trees/main?recursive=1"
DOOM_DOMAINS_URL = "https://raw.githubusercontent.com/ummarm/Doom-plug/main/domains.json"
USER_AGENT = "Doom-plug upstream sync"
SEEKABLE_VALIDATION_MARKER = "__DOOM_SEEKABLE_VALIDATION__"
SEEKABLE_VALIDATION_SNIPPET = r"""
// __DOOM_SEEKABLE_VALIDATION__
var __doomProbeCache = Object.create(null);
var __doomProbeCacheTtlMs = 10 * 60 * 1000;
var __doomProbeTimeoutMs = 6 * 1000;

function __doomMergeHeaders(base, extra) {
  var merged = {};
  var key;
  for (key in base || {}) merged[key] = base[key];
  for (key in extra || {}) merged[key] = extra[key];
  return merged;
}

function __doomWithTimeout(promise, timeoutMs) {
  return new Promise(function(resolve, reject) {
    var settled = false;
    var timer = setTimeout(function() {
      if (settled) return;
      settled = true;
      reject(new Error("timeout"));
    }, timeoutMs);

    Promise.resolve(promise).then(function(value) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(value);
    }, function(error) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(error);
    });
  });
}

function __doomLooksLikeHls(url, contentType) {
  var normalizedUrl = String(url || "").toLowerCase();
  var normalizedType = String(contentType || "").toLowerCase();
  return normalizedUrl.indexOf(".m3u8") !== -1
    || normalizedType.indexOf("mpegurl") !== -1
    || normalizedType.indexOf("application/x-mpegurl") !== -1
    || normalizedType.indexOf("vnd.apple.mpegurl") !== -1;
}

function __doomBuildProbeCacheKey(stream) {
  var headers = stream && stream.headers ? stream.headers : {};
  return [
    stream && stream.url ? stream.url : "",
    headers.Referer || headers.referer || "",
    headers.Origin || headers.origin || ""
  ].join("|");
}

function __doomGetCachedProbeResult(cacheKey) {
  var entry = __doomProbeCache[cacheKey];
  if (!entry) return null;
  if (Date.now() - entry.timestamp > __doomProbeCacheTtlMs) {
    delete __doomProbeCache[cacheKey];
    return null;
  }
  return entry.ok;
}

function __doomSetCachedProbeResult(cacheKey, ok) {
  __doomProbeCache[cacheKey] = {
    ok: !!ok,
    timestamp: Date.now()
  };
}

function __doomResponseIsSeekable(response, url) {
  if (!response || !response.ok) return false;
  var headers = response.headers;
  var contentType = headers && headers.get ? headers.get("content-type") || "" : "";
  if (__doomLooksLikeHls(url, contentType)) return true;
  var acceptRanges = headers && headers.get ? headers.get("accept-ranges") || "" : "";
  var contentRange = headers && headers.get ? headers.get("content-range") || "" : "";
  return response.status === 206
    || /bytes/i.test(acceptRanges)
    || /^bytes\s+/i.test(contentRange);
}

function __doomProbeStream(stream) {
  if (!stream || !stream.url || typeof fetch !== "function") {
    return Promise.resolve(false);
  }

  var cacheKey = __doomBuildProbeCacheKey(stream);
  var cached = __doomGetCachedProbeResult(cacheKey);
  if (cached !== null) {
    return Promise.resolve(cached);
  }

  var url = stream.url;
  var isHls = __doomLooksLikeHls(url, "");
  var baseHeaders = __doomMergeHeaders({}, stream.headers || {});
  var rangedHeaders = __doomMergeHeaders({}, baseHeaders);
  if (!isHls && !rangedHeaders.Range && !rangedHeaders.range) {
    rangedHeaders.Range = "bytes=0-1";
  }

  var attempts = [
    { method: "GET", headers: isHls ? baseHeaders : rangedHeaders, redirect: "follow" },
    { method: "HEAD", headers: baseHeaders, redirect: "follow" }
  ];

  function tryAttempt(index) {
    if (index >= attempts.length) return Promise.resolve(false);
    return __doomWithTimeout(fetch(url, attempts[index]), __doomProbeTimeoutMs)
      .then(function(response) {
        if (__doomResponseIsSeekable(response, url)) return true;
        return tryAttempt(index + 1);
      })
      .catch(function() {
        return tryAttempt(index + 1);
      });
  }

  return tryAttempt(0).then(function(ok) {
    __doomSetCachedProbeResult(cacheKey, ok);
    return ok;
  });
}

function __doomFilterSeekableStreams(streams, providerLabel) {
  if (!Array.isArray(streams) || streams.length === 0) {
    return Promise.resolve([]);
  }

  return Promise.all(streams.map(function(stream) {
    return __doomProbeStream(stream)
      .then(function(ok) { return { stream: stream, ok: ok }; })
      .catch(function() { return { stream: stream, ok: false }; });
  })).then(function(results) {
    var filtered = results.filter(function(item) { return item.ok; }).map(function(item) { return item.stream; });
    var label = providerLabel || "[Doom-plug]";
    console.log(label + " Seekable filter kept " + filtered.length + "/" + streams.length + " streams");
    return filtered;
  });
}

(function() {
  if (typeof getStreams !== "function" || getStreams.__doomSeekableWrapped) {
    return;
  }

  var __doomOriginalGetStreams = getStreams;
  var __doomProviderLabel = typeof PLUGIN_TAG !== "undefined"
    ? PLUGIN_TAG
    : (typeof TAG !== "undefined" ? TAG : "[Doom-plug]");

  var __doomWrappedGetStreams = function() {
    return Promise.resolve(__doomOriginalGetStreams.apply(this, arguments))
      .then(function(streams) {
        return __doomFilterSeekableStreams(streams, __doomProviderLabel);
      })
      .catch(function(error) {
        var message = error && error.message ? error.message : String(error);
        console.error(__doomProviderLabel + " Seekable validation failed: " + message);
        return [];
      });
  };

  __doomWrappedGetStreams.__doomSeekableWrapped = true;
  getStreams = __doomWrappedGetStreams;

  if (typeof module !== "undefined" && module.exports) {
    module.exports.getStreams = getStreams;
  } else if (typeof global !== "undefined") {
    global.getStreams = getStreams;
  }
})();
"""


@dataclass(frozen=True)
class Provider:
    scraper_id: str
    upstream_paths: tuple[str, ...]
    local_path_str: str
    discovery_terms: tuple[str, ...] = ()

    @property
    def local_path(self) -> Path:
        return REPO_ROOT / self.local_path_str


@dataclass(frozen=True)
class ResolvedProvider:
    provider: Provider
    upstream_path: str

    @property
    def scraper_id(self) -> str:
        return self.provider.scraper_id

    @property
    def local_path(self) -> Path:
        return self.provider.local_path

    @property
    def upstream_url(self) -> str:
        return f"{UPSTREAM_RAW_BASE}/{self.upstream_path}"


PROVIDERS = (
    Provider("4khdhub", ("providers/4khdhub.js", "providers/4khdhubtest.js"), "providers/4khdhub.js", ("4khdhub", "hubcloud")),
    Provider(
        "4khdhubtv",
        ("providers/4khdhub_tv.js", "providers/4khdhubtest.js", "providers/4khdhub.js"),
        "providers/4khdhub_tv.js",
        ("4khdhub", "tv", "test"),
    ),
    Provider("hdhub4u", ("providers/hdhub4u.js", "src/hdhub4u/index.js"), "providers/hdhub4u.js", ("hdhub4u",)),
    Provider("hindmoviez", ("providers/hindmoviez.js",), "providers/hindmoviez.js", ("hindmoviez",)),
    Provider("movieblast", ("providers/movieblast.js",), "providers/movieblast.js", ("movieblast",)),
    Provider("moviebox", ("providers/moviebox.js",), "providers/moviebox.js", ("moviebox",)),
    Provider("moviesdrive", ("src/providers/moviesdrive.js", "providers/moviesdrive.js"), "providers/moviesdrive.js", ("moviesdrive",)),
    Provider("streamflix", ("providers/streamflix.js",), "providers/streamflix.js", ("streamflix",)),
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


def fetch_json(url: str) -> object:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_upstream_tree_paths() -> list[str]:
    payload = fetch_json(UPSTREAM_TREE_API)
    tree = payload["tree"]
    return [item["path"] for item in tree if item.get("type") == "blob"]


def normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def score_discovered_path(provider: Provider, path: str) -> int:
    normalized_path = normalize_token(path)
    normalized_name = normalize_token(Path(path).stem)
    normalized_id = normalize_token(provider.scraper_id)
    score = 0

    if normalized_name == normalized_id:
        score += 100
    elif normalized_id and normalized_id in normalized_name:
        score += 50

    for term in provider.discovery_terms:
        normalized_term = normalize_token(term)
        if not normalized_term:
            continue
        if normalized_term in normalized_name:
            score += 30
        elif normalized_term in normalized_path:
            score += 12

    if path.startswith("providers/"):
        score += 5
    elif path.startswith("src/providers/"):
        score += 3

    return score


def candidate_upstream_paths(provider: Provider, upstream_tree_paths: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    tree_set = set(upstream_tree_paths)

    for path in provider.upstream_paths:
        if path in tree_set and path not in seen:
            ordered.append(path)
            seen.add(path)

    scored_paths = [
        (score_discovered_path(provider, path), path)
        for path in upstream_tree_paths
        if path.endswith(".js")
    ]
    scored_paths.sort(key=lambda item: (-item[0], item[1]))

    for score, path in scored_paths:
        if score < 40 or path in seen:
            continue
        ordered.append(path)
        seen.add(path)

    for path in provider.upstream_paths:
        if path not in seen:
            ordered.append(path)
            seen.add(path)

    return ordered


def patch_domain_source(text: str) -> str:
    updated, count = re.subn(
        r"""(?:var|const|let)\s+DOMAINS_URL\s*=\s*["'][^"']+["'];""",
        f'var DOMAINS_URL = "{DOOM_DOMAINS_URL}";',
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("Could not retarget DOMAINS_URL to Doom-plug domains.json")
    return updated


def patch_moviesdrive_domain_source(text: str) -> str:
    if "DOMAIN_JSON_URL" in text:
        updated, count = re.subn(
            r"""(?:var|const|let)\s+DOMAIN_JSON_URL\s*=\s*["'][^"']+["'];""",
            f'const DOMAIN_JSON_URL = "{DOOM_DOMAINS_URL}";',
            text,
            count=1,
        )
        if count != 1:
            raise RuntimeError("Could not retarget DOMAIN_JSON_URL to Doom-plug domains.json")
        old_block = """if (data && data[PROVIDER_KEY] && data[PROVIDER_KEY].url) {
          moviesDriveDomain = data[PROVIDER_KEY].url.replace(/\\/$/, "");
          domainCacheTimestamp = now;
          console.log(`[MoviesDrive] Domain set to: ${moviesDriveDomain}`);
        }
"""
        new_block = """if (data) {
          const resolvedDomain = data.Moviesdrive || (typeof data[PROVIDER_KEY] === "string" ? data[PROVIDER_KEY] : data[PROVIDER_KEY] && data[PROVIDER_KEY].url);
          if (resolvedDomain) {
            moviesDriveDomain = resolvedDomain.replace(/\\/$/, "");
            domainCacheTimestamp = now;
            console.log(`[MoviesDrive] Domain set to: ${moviesDriveDomain}`);
          }
        }
"""
        if old_block not in updated:
            raise RuntimeError("Could not adapt MoviesDrive domain reader to Doom-plug domains.json")
        return updated.replace(old_block, new_block, 1)

    return patch_domain_source(text)


def patch_hindmoviez_source(text: str) -> str:
    text = re.sub(
        r"// ── Cloudflare Worker proxy[\s\S]*?const DEFAULT_HEADERS = \{",
        "const DEFAULT_HEADERS = {",
        text,
        count=1,
    )
    text, call_count = re.subn(r"(:\s*)hmProxyUrl\(([^)]+)\)", r"\1\2", text)
    text, assign_count = re.subn(
        r"((?:var|const|let)\s+proxiedUrl\s*=\s*)hmProxyUrl\(([^)]+)\);",
        r"\1\2;",
        text,
    )
    if call_count + assign_count < 1:
        raise RuntimeError("Could not remove hmProxyUrl wrapper from HindMoviez provider")
    return text


def patch_4khdhub_fsl_preferred(text: str) -> str:
    if "const preferredLinks = fslLinks.length ? fslLinks : extractedLinks;" in text:
        return text
    if "const preferredStreams = streams.filter((stream) => !/(BuzzServer|Pixeldrain)/i.test(" in text:
        return text

    updated, count = re.subn(
        r"(\s*const extractedLinks = yield extractHubCloud\(sourceResult\.url, sourceResult\.meta\);\n)\s*return extractedLinks\.map\(",
        r'\1          const fslLinks = extractedLinks.filter((link) => link.source === "FSL");\n          const preferredLinks = fslLinks.length ? fslLinks : extractedLinks;\n          return preferredLinks.map(',
        text,
        count=1,
    )
    if count == 1:
        return updated

    function_start = text.find("function resolveHubcloud(")
    if function_start == -1:
        raise RuntimeError("Could not find resolveHubcloud in 4KHDHub provider")

    return_anchor = text.find("return streams;", function_start)
    if return_anchor == -1:
        raise RuntimeError("Could not find stream return point in 4KHDHub provider")

    replacement = (
        'const preferredStreams = streams.filter((stream) => !/(BuzzServer|Pixeldrain)/i.test(`${stream.name || ""} ${stream.title || ""}`));\n'
        "    return preferredStreams.length ? preferredStreams : streams;"
    )
    return text[:return_anchor] + replacement + text[return_anchor + len("return streams;") :]


def patch_hdhub4u_fsl_preferred(text: str) -> str:
    if 'const fslLinks = filteredLinks.filter((link) => /fsl/i.test(link.source || ""));' in text:
        return text

    updated, count = re.subn(
        r"(\s*if \(mediaType === \"tv\" && episode !== null\) \{\n\s*filteredLinks = finalLinks\.filter\(\(link\) => link\.episode === episode\);\n\s*})",
        r'\1\n      const fslLinks = filteredLinks.filter((link) => /fsl/i.test(link.source || ""));\n      if (fslLinks.length) {\n        filteredLinks = fslLinks;\n      }',
        text,
        count=1,
    )
    if count == 1:
        return updated

    block_start = text.find("let filteredLinks = finalLinks;")
    map_anchor = text.find("const streams = filteredLinks.map(", block_start)
    if block_start == -1 or map_anchor == -1:
        raise RuntimeError("Could not add FSL-first fallback logic to HDHub4u provider")

    insertion = (
        '      const fslLinks = filteredLinks.filter((link) => /fsl/i.test(link.source || ""));\n'
        "      if (fslLinks.length) {\n"
        "        filteredLinks = fslLinks;\n"
        "      }\n"
    )
    return text[:map_anchor] + insertion + text[map_anchor:]


def patch_seekable_validation(text: str) -> str:
    if SEEKABLE_VALIDATION_MARKER in text:
        return text
    return text.rstrip("\n") + "\n\n" + SEEKABLE_VALIDATION_SNIPPET.strip("\n") + "\n"


def transform_source(provider: Provider, text: str) -> str:
    if provider.scraper_id in {"4khdhub", "4khdhubtv", "hdhub4u"}:
        text = patch_domain_source(text)
    elif provider.scraper_id == "moviesdrive":
        text = patch_moviesdrive_domain_source(text)
    if provider.scraper_id in {"4khdhub", "4khdhubtv"}:
        text = patch_4khdhub_fsl_preferred(text)
    elif provider.scraper_id == "hdhub4u":
        text = patch_hdhub4u_fsl_preferred(text)
    elif provider.scraper_id == "hindmoviez":
        text = patch_hindmoviez_source(text)
    text = patch_seekable_validation(text)
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


def write_pr_body(
    changed: list[ResolvedProvider],
    version_changes: list[str],
    warnings: list[str],
    run_date: date,
) -> None:
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
            "- `4KHDHub`, `4khdhub-tv`, `HDHub4u`, and `MoviesDrive` still point at Doom-plug's own `domains.json`.",
            "- `HindMoviez` still uses direct resolved URLs instead of the upstream worker proxy.",
            "- `4KHDHub` and `4khdhub-tv` keep Doom-plug's preferred-host fallback behavior, while `HDHub4u` keeps FSL-first fallback behavior.",
            "- All tracked providers keep Doom-plug's working-and-seekable stream validation wrapper before results are returned.",
            "",
            "## Version bumps",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in version_changes)
    if warnings:
        lines.extend(["", "## Skipped providers", ""])
        lines.extend(f"- {item}" for item in warnings)
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
                f"Skipped on `{today_utc.isoformat()}` UTC because the 2-day cadence is anchored to `{ANCHOR_DATE.isoformat()}`.",
                "The workflow still runs daily so manual dispatch stays available, but real sync work only happens on cadence days unless `force` is enabled.",
            ]
        )
        print("Not on the 2-day sync cadence; skipping.")
        return 0

    changed_providers: list[ResolvedProvider] = []
    sync_warnings: list[str] = []
    try:
        upstream_tree_paths = fetch_upstream_tree_paths()
    except Exception as exc:
        upstream_tree_paths = []
        warning = f"Upstream tree discovery failed, so Doom-plug fell back to static paths: {exc}"
        sync_warnings.append(warning)
        print(f"Warning: {warning}")

    for provider in PROVIDERS:
        resolved_provider = None
        upstream_text = None

        for upstream_path in candidate_upstream_paths(provider, upstream_tree_paths):
            try:
                upstream_text = fetch_text(f"{UPSTREAM_RAW_BASE}/{upstream_path}")
                resolved_provider = ResolvedProvider(provider, upstream_path)
                if upstream_path != provider.upstream_paths[0]:
                    print(
                        f"Info: `{provider.scraper_id}` auto-followed upstream path "
                        f"`{upstream_path}`."
                    )
                break
            except HTTPError as exc:
                if exc.code == 404:
                    continue
                raise

        if resolved_provider is None or upstream_text is None:
            warning = (
                f"`{provider.scraper_id}` was skipped because no compatible upstream provider "
                "file could be found automatically."
            )
            sync_warnings.append(warning)
            print(f"Warning: {warning}")
            continue

        try:
            transformed_text = transform_source(provider, upstream_text)
        except RuntimeError as exc:
            warning = f"`{provider.scraper_id}` was skipped because local patching failed: {exc}"
            sync_warnings.append(warning)
            print(f"Warning: {warning}")
            continue

        local_text = (
            provider.local_path.read_text(encoding="utf-8")
            if provider.local_path.exists()
            else ""
        )

        if transformed_text != local_text:
            provider.local_path.parent.mkdir(parents=True, exist_ok=True)
            provider.local_path.write_text(transformed_text, encoding="utf-8")
            changed_providers.append(resolved_provider)

    if not changed_providers:
        summary_lines = [
            "## Doom-plug upstream sync",
            "",
            f"No upstream changes were applied on `{today_utc.isoformat()}` UTC.",
        ]
        if sync_warnings:
            summary_lines.extend(["", "Skipped providers:"])
            summary_lines.extend(f"- {item}" for item in sync_warnings)
        write_output("changed", "false")
        write_output("skipped", "false")
        write_summary(summary_lines)
        if sync_warnings:
            print("No upstream changes applied; some providers were skipped.")
        else:
            print("No upstream changes detected.")
        return 0

    changed_ids = {provider.scraper_id for provider in changed_providers}
    version_changes = update_manifest(changed_ids)
    write_pr_body(changed_providers, version_changes, sync_warnings, today_utc)

    changed_names = ",".join(provider.scraper_id for provider in changed_providers)
    write_output("changed", "true")
    write_output("skipped", "false")
    write_output("changed_scrapers", changed_names)
    summary_lines = [
        "## Doom-plug upstream sync",
        "",
        f"Updated scrapers: `{changed_names}`",
        "",
        "Version bumps:",
        *[f"- {item}" for item in version_changes],
    ]
    if sync_warnings:
        summary_lines.extend(["", "Skipped providers:"])
        summary_lines.extend(f"- {item}" for item in sync_warnings)
    write_summary(summary_lines)
    print(f"Updated providers: {changed_names}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
