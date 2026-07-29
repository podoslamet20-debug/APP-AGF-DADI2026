// server.js
//
// Minimal, dependency-free static file server for the production build.
//
// Nixpacks (Railway) always runs the "start" script defined in package.json
// at runtime. Previously that was "craco start", which boots the webpack
// dev server (HMR + react-refresh) instead of serving the already-built
// static assets produced by "craco build" at build time. That caused blank
// pages and dev-only behavior in production.
//
// This server uses only Node.js built-ins (no Express, no webpack, no dev
// dependencies) to serve the contents of ./build, with SPA-style fallback
// routing to index.html for any path that isn't a real file on disk.

const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = process.env.PORT || 3000;
const BUILD_DIR = path.join(__dirname, "build");
const INDEX_HTML = path.join(BUILD_DIR, "index.html");

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".webp": "image/webp",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".eot": "application/vnd.ms-fontobject",
  ".otf": "font/otf",
  ".txt": "text/plain; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".webmanifest": "application/manifest+json",
};

function getContentType(filePath) {
  return MIME_TYPES[path.extname(filePath).toLowerCase()] || "application/octet-stream";
}

function setSecurityHeaders(res) {
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.setHeader("X-Frame-Options", "SAMEORIGIN");
  res.setHeader("X-XSS-Protection", "1; mode=block");
  res.setHeader("Referrer-Policy", "strict-origin-when-cross-origin");
}

function sendFile(res, filePath, statusCode = 200) {
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Internal Server Error");
      return;
    }

    setSecurityHeaders(res);
    res.setHeader("Content-Type", getContentType(filePath));

    // index.html should never be cached, static assets (with hashed
    // filenames) can be cached aggressively.
    if (path.basename(filePath) === "index.html") {
      res.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");
    } else {
      res.setHeader("Cache-Control", "public, max-age=31536000, immutable");
    }

    res.writeHead(statusCode);
    res.end(data);
  });
}

if (!fs.existsSync(BUILD_DIR) || !fs.existsSync(INDEX_HTML)) {
  console.error(
    `[server] Build output not found at ${BUILD_DIR}. Did "craco build" run during the build step?`
  );
  process.exit(1);
}

const server = http.createServer((req, res) => {
  try {
    const requestUrl = new URL(req.url, `http://${req.headers.host || "localhost"}`);
    let requestedPath = decodeURIComponent(requestUrl.pathname);

    // Normalize and prevent path traversal outside of BUILD_DIR.
    const safeSuffix = path.normalize(requestedPath).replace(/^(\.\.[/\\])+/, "");
    let filePath = path.join(BUILD_DIR, safeSuffix);

    if (!filePath.startsWith(BUILD_DIR)) {
      filePath = INDEX_HTML;
    }

    fs.stat(filePath, (err, stats) => {
      if (!err && stats.isFile()) {
        sendFile(res, filePath);
        return;
      }

      // Not a real static file — fall back to index.html for client-side
      // (SPA) routing.
      sendFile(res, INDEX_HTML);
    });
  } catch (err) {
    console.error("[server] Error handling request:", err);
    res.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Internal Server Error");
  }
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`[server] Serving static build from ${BUILD_DIR} on port ${PORT}`);
});
