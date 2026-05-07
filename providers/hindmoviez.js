/**
 * ╔══════════════════════════════════════════════════════════════════════════════╗
 * ║            HindMoviez — Nuvio Stream Plugin Optimized for Android TV                       ║
 * ╠══════════════════════════════════════════════════════════════════════════════╣
 * ║  Source     › https://hindmovie.ltd                                                        ║
 * ║  Author     › Sanchit  |  TG: @S4NCHITT                                                    ║
 * ║  Project    › Murph's Streams                                                              ║
 * ║  Manifest   › https://badboysxs-morpheus.hf.space/manifest.json                            ║
 * ╠══════════════════════════════════════════════════════════════════════════════╣
 * ║  Supports   › Movies & Series  (480p / 720p / 1080p / 4K)                                  ║
 * ║  Chain      › mvlink.site → hshare.ink → hcloud → Servers                                ║
 * ║  Info       › Quality + Language parsed from page headings                                 ║
 * ║  Parallel   › All links resolved concurrently                                              ║
 * ╚══════════════════════════════════════════════════════════════════════════════╝
 */

'use strict';

var BASE_URL     = 'https://hindmovie.ltd';
var TMDB_API_KEY = '439c478a771f35c05022f9feabcca01c';
var PLUGIN_TAG   = '[HindMoviez]';
var HM_WORKER    = 'https://hindmoviez.s4nch1tt.workers.dev';

var DEFAULT_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
};

function hmProxyUrl(rawUrl) {
  if (!rawUrl) return rawUrl;
  return HM_WORKER + '/hm/proxy?url=' + encodeURIComponent(rawUrl);
}

// ─────────────────────────────────────────────────────────────────────────────
// The Secret Sauce: A fail-safe Fetch that works on TV & Mobile
// ─────────────────────────────────────────────────────────────────────────────
function safeFetch(url) {
  return fetch(url, { headers: DEFAULT_HEADERS, redirect: 'follow' })
    .then(function(res) { 
      if (!res.ok) return null;
      return res.text(); 
    })
    .catch(function() { return null; });
}

function getStreams(tmdbId, type, season, episode) {
  var isSeries = (type === 'series' || type === 'tv');
  var tmdbUrl = 'https://api.themoviedb.org/3/' + (isSeries ? 'tv' : 'movie') + '/' + tmdbId + '?api_key=' + TMDB_API_KEY;

  return fetch(tmdbUrl)
    .then(function(res) { return res.json(); })
    .then(function(details) {
      if (!details) return [];
      var query = isSeries ? details.name : details.title;
      return safeFetch(BASE_URL + '/?s=' + encodeURIComponent(query));
    })
    .then(function(html) {
      if (!html) return [];
      // Look for article links
      var linkMatch = html.match(/<h2[^>]*class="entry-title"[^>]*>\s*<a\s[^>]*href="([^"]+)"/i) || html.match(/<a\s[^>]*href="([^"]+)"[^>]*rel="bookmark"/i);
      if (!linkMatch) return [];
      return safeFetch(linkMatch[1]);
    })
    .then(function(pageHtml) {
      if (!pageHtml) return [];

      var streams = [];
      var resolvePromises = [];
      // Split page into chunks by H3 so we don't mix up quality info
      var sections = pageHtml.split(/<h3/i);

      for (var i = 1; i < sections.length; i++) {
        var chunk = sections[i];
        var mvMatch = chunk.match(/href="(https:\/\/mvlink\.site\/[^"]+)"/i);
        
        if (mvMatch) {
          // Extract info from the H3 text (before the </h3>)
          var headingText = chunk.split('</h3>')[0];
          var qMatch = headingText.match(/\b(2160p|1080p|720p|480p|4K)\b/i);
          var quality = qMatch ? qMatch[1].toLowerCase().replace('4k', '2160p') : '720p';
          var sizeMatch = headingText.match(/\[([0-9.]+\s*(?:MB|GB))\]/i);
          var size = sizeMatch ? sizeMatch[1] : '';

          (function(mvUrl, q, sz) {
            var p = safeFetch(mvUrl)
              .then(function(mvHtml) {
                if (!mvHtml) return null;
                var hs = mvHtml.match(/href="(https:\/\/hshare\.ink\/[^"]+)"/i);
                return hs ? safeFetch(hs[1]) : null;
              })
              .then(function(hsHtml) {
                if (!hsHtml) return null;
                var hp = hsHtml.match(/href="([^"]+)"[^>]*>HPage<\/a>/i);
                return hp ? safeFetch(hp[1]) : null;
              })
              .then(function(hcHtml) {
                if (!hcHtml) return;
                // Regex for server links: matches Server 1, Server 2, etc.
                var srvRe = /<a[^>]*href="([^"]+)"[^>]*>(Server\s+\d+)<\/a>/gi;
                var sMatch;
                while ((sMatch = srvRe.exec(hcHtml)) !== null) {
                  streams.push({
                    name: '🎬 HindMoviez | ' + sMatch[2] + ' | ' + q.toUpperCase(),
                    title: '📺 ' + q.toUpperCase() + ' • 💾 ' + sz + '\nSanchit Plugin (TV Mode)',
                    url: sMatch[1],
                    quality: q,
                    behaviorHints: { notWebReady: false }
                  });
                }
              });
            resolvePromises.push(p);
          })(mvMatch[1], quality, size);
        }
      }

      return Promise.all(resolvePromises).then(function() {
        return streams;
      });
    })
    .catch(function(err) {
      return [];
    });
}

if (typeof module !== 'undefined') { module.exports = { getStreams: getStreams }; } 
else { global.getStreams = getStreams; }

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
