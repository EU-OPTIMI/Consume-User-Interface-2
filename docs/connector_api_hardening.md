## Connector API hardening for artifact JSON

Use this when `/connector/api/artifacts/<uuid>/data` is expected to return JSON.

### App behavior

- Return `HTTP 200` for successful artifact fetches.
- Return `Content-Type: application/json; charset=utf-8` for JSON payloads.
- Ensure upstream app does not default this route to `text/html`.

### Nginx behavior

Use a dedicated API location and avoid content mutation:

```nginx
location /connector/api/ {
  proxy_pass http://connector:8080/connector/api/;
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

  # Do not transform API payloads
  gzip off;
  brotli off;
}
```

Operational checks:
- Ensure no `default_type text/html;` applies to `/connector/api/*`.
- Ensure no HTML rewrite/minify filters apply to this location.
- Prefer passing upstream `Content-Type` unchanged.

### Cloudflare behavior

Create a rule for `/connector/api/*` with:

- Cache: Bypass
- Auto Minify: Off
- Rocket Loader: Off
- HTML transforms/optimizations: Off
- Brotli: Off only if you observe decode issues

### Verification commands

```bash
curl -skI -H "Authorization: Basic <...>" \
  "https://<host>/connector/api/artifacts/<uuid>/data" \
  | egrep -i 'HTTP/|content-type|content-encoding|server|cf-cache-status'
```

```bash
curl -sk -H "Authorization: Basic <...>" -H "Accept-Encoding: identity" \
  "https://<host>/connector/api/artifacts/<uuid>/data" \
  | head -c 200; echo
```

Expected:
- `content-type: application/json` (optionally with charset)
- Response body is valid JSON (or a meaningful API error JSON)
