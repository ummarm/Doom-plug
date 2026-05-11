#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const hdhub4uMurph = require("../providers/hdhub4u_murph.js");
const fourKhdhubMurph = require("../providers/4khdhub_murph.js");

const MURPH_BASE = "https://badboysxs-morpheus.hf.space";
const ISSUE_TITLE = "Murph wrapper monitor detected drift";
const USER_AGENT = "Doom-plug Murph monitor";
const REQUEST_HEADERS = {
  "User-Agent": USER_AGENT,
  "Accept": "application/json, text/plain, */*",
};
const REPORT_PATH = process.env.REPORT_PATH || ".git/murph-monitor-report.json";
const ISSUE_BODY_PATH = process.env.ISSUE_BODY_PATH || ".git/murph-monitor-issue.md";

const checks = [];
const failures = [];

function setOutput(name, value) {
  const githubOutput = process.env.GITHUB_OUTPUT;
  if (!githubOutput) return;
  fs.appendFileSync(githubOutput, `${name}=${value}\n`, "utf8");
}

function appendStepSummary(markdown) {
  const summaryPath = process.env.GITHUB_STEP_SUMMARY;
  if (!summaryPath) return;
  fs.appendFileSync(summaryPath, markdown, "utf8");
}

async function fetchJson(url, timeoutMs = 20000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new Error("timeout")), timeoutMs);
  try {
    const response = await fetch(url, {
      headers: REQUEST_HEADERS,
      redirect: "follow",
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status} -> ${url}`);
    }
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

function extractStreams(payload) {
  if (Array.isArray(payload)) return payload;
  if (!payload || typeof payload !== "object") return [];
  const candidates = [
    payload.streams,
    payload.data && payload.data.streams,
    payload.result && payload.result.streams,
    payload.data && payload.data.results,
    payload.results,
    payload.items,
  ];
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) return candidate;
  }
  return [];
}

function listProviderNames(statsPayload) {
  const providers = statsPayload && statsPayload.providers;
  if (Array.isArray(providers)) {
    return providers
      .map((provider) => {
        if (typeof provider === "string") return provider;
        return provider && (provider.name || provider.id || provider.provider);
      })
      .filter(Boolean);
  }

  if (providers && typeof providers === "object") {
    return Object.keys(providers);
  }

  return [];
}

function recordCheck(name, ok, details) {
  const entry = { name, ok: !!ok, details: String(details || "") };
  checks.push(entry);
  if (!entry.ok) failures.push(entry);
}

function summarizeStreams(streams) {
  if (!Array.isArray(streams)) return "0 streams";
  const preview = streams.slice(0, 3).map((stream) => stream && (stream.name || stream.title || stream.url || "[unknown]"));
  return `${streams.length} stream(s)` + (preview.length ? `; sample: ${preview.join(" | ")}` : "");
}

function buildIssueBody(report) {
  const lines = [
    `Murph wrapper monitor found drift on \`${report.checkedAt}\`.`,
    "",
    "## Failing checks",
    "",
  ];

  if (failures.length === 0) {
    lines.push("- None");
  } else {
    for (const failure of failures) {
      lines.push(`- ${failure.name}: ${failure.details}`);
    }
  }

  lines.push("", "## Passing checks", "");
  for (const check of checks.filter((entry) => entry.ok)) {
    lines.push(`- ${check.name}: ${check.details}`);
  }

  lines.push(
    "",
    "## What this means",
    "",
    "- Small upstream content changes are handled automatically because the Murph wrappers read the live endpoint on every request.",
    "- This alert only triggers when the Murph route, JSON shape, provider labels, or filtered playable results drift enough that Doom-plug may need a wrapper patch.",
    "",
    `Issue title: \`${ISSUE_TITLE}\``,
    ""
  );

  return lines.join("\n");
}

function writeArtifacts(report) {
  fs.mkdirSync(path.dirname(REPORT_PATH), { recursive: true });
  fs.mkdirSync(path.dirname(ISSUE_BODY_PATH), { recursive: true });
  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2) + "\n", "utf8");
  fs.writeFileSync(ISSUE_BODY_PATH, buildIssueBody(report) + "\n", "utf8");
}

async function runCheck(name, fn) {
  try {
    const details = await fn();
    recordCheck(name, true, details);
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    recordCheck(name, false, message);
  }
}

async function main() {
  await runCheck("Murph manifest shape", async () => {
    const manifest = await fetchJson(`${MURPH_BASE}/manifest.json`);
    if (!manifest || typeof manifest !== "object") {
      throw new Error("manifest payload was not an object");
    }
    if (!manifest.id || !Array.isArray(manifest.resources) || !Array.isArray(manifest.types)) {
      throw new Error("manifest is missing expected id/resources/types fields");
    }
    return `id=${manifest.id}, version=${manifest.version || "unknown"}`;
  });

  await runCheck("Murph stats expose HDHub4u and 4KHDHub", async () => {
    const stats = await fetchJson(`${MURPH_BASE}/api/stats`);
    const names = listProviderNames(stats).map((name) => String(name));
    if (!names.some((name) => /hdhub4u/i.test(name))) {
      throw new Error(`HDHub4u missing from stats providers: ${names.join(", ") || "[none]"}`);
    }
    if (!names.some((name) => /4khdhub/i.test(name))) {
      throw new Error(`4KHDHub missing from stats providers: ${names.join(", ") || "[none]"}`);
    }
    return names.join(", ");
  });

  await runCheck("Murph movie endpoint still exposes 4KHDHub", async () => {
    const payload = await fetchJson(`${MURPH_BASE}/stream/movie/tt4154796.json`);
    const streams = extractStreams(payload);
    if (!streams.length) {
      throw new Error("movie endpoint did not return any streams");
    }
    const names = streams.map((stream) => String(stream && stream.name || ""));
    if (!names.some((name) => /4khdhub/i.test(name))) {
      throw new Error(`4KHDHub missing from movie endpoint names: ${names.slice(0, 10).join(", ")}`);
    }
    return `${streams.length} upstream stream(s)`;
  });

  await runCheck("Murph series endpoint still exposes HDHub4u and 4KHDHub", async () => {
    const payload = await fetchJson(`${MURPH_BASE}/stream/series/tt0944947:1:1.json`);
    const streams = extractStreams(payload);
    if (!streams.length) {
      throw new Error("series endpoint did not return any streams");
    }
    const names = streams.map((stream) => String(stream && stream.name || ""));
    if (!names.some((name) => /hdhub4u/i.test(name))) {
      throw new Error(`HDHub4u missing from series endpoint names: ${names.slice(0, 10).join(", ")}`);
    }
    if (!names.some((name) => /4khdhub/i.test(name))) {
      throw new Error(`4KHDHub missing from series endpoint names: ${names.slice(0, 10).join(", ")}`);
    }
    return `${streams.length} upstream stream(s)`;
  });

  await runCheck("HDHub4u Murph wrapper returns playable series links", async () => {
    const streams = await hdhub4uMurph.getStreams("tt0944947", "series", 1, 1);
    if (!Array.isArray(streams) || streams.length < 1) {
      throw new Error(`wrapper returned ${summarizeStreams(streams)}`);
    }
    return summarizeStreams(streams);
  });

  await runCheck("4KHDHub Murph wrapper returns playable movie links", async () => {
    const streams = await fourKhdhubMurph.getStreams("tt4154796", "movie");
    if (!Array.isArray(streams) || streams.length < 1) {
      throw new Error(`wrapper returned ${summarizeStreams(streams)}`);
    }
    return summarizeStreams(streams);
  });

  await runCheck("4KHDHub Murph wrapper returns playable series links", async () => {
    const streams = await fourKhdhubMurph.getStreams("tt0944947", "series", 1, 1);
    if (!Array.isArray(streams) || streams.length < 1) {
      throw new Error(`wrapper returned ${summarizeStreams(streams)}`);
    }
    return summarizeStreams(streams);
  });

  const report = {
    checkedAt: new Date().toISOString(),
    murphBase: MURPH_BASE,
    drift: failures.length > 0,
    checkCount: checks.length,
    failures,
    checks,
  };

  writeArtifacts(report);
  setOutput("drift", report.drift ? "true" : "false");
  setOutput("healthy", report.drift ? "false" : "true");
  setOutput("issue_title", ISSUE_TITLE);

  const summaryLines = [
    "## Murph wrapper monitor",
    "",
    report.drift
      ? `Detected drift in ${failures.length}/${checks.length} checks.`
      : `All ${checks.length} checks passed.`,
    "",
  ];
  for (const check of checks) {
    summaryLines.push(`- ${check.ok ? "PASS" : "FAIL"} ${check.name}: ${check.details}`);
  }
  appendStepSummary(summaryLines.join("\n") + "\n");

  if (report.drift) {
    console.log(`Murph wrapper drift detected in ${failures.length} checks.`);
  } else {
    console.log("Murph wrapper monitor passed.");
  }
}

main().catch((error) => {
  const message = error && error.stack ? error.stack : String(error);
  const report = {
    checkedAt: new Date().toISOString(),
    murphBase: MURPH_BASE,
    drift: true,
    checkCount: checks.length,
    failures: failures.concat([{ name: "Murph monitor script crash", ok: false, details: message }]),
    checks,
  };
  writeArtifacts(report);
  setOutput("drift", "true");
  setOutput("healthy", "false");
  setOutput("issue_title", ISSUE_TITLE);
  appendStepSummary(`## Murph wrapper monitor\n\n- FAIL Murph monitor script crash: ${message}\n`);
  console.error(message);
  process.exitCode = 0;
});
