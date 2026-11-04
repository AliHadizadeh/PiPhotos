#!/usr/bin/env python3
"""Minimal Immich API client (standard library only) with streaming multipart uploads and retries."""
import hashlib, http.client, io, json, os, socket, ssl, time, urllib.parse, uuid

CHUNK = 1024 * 1024


class ApiError(Exception):
    def __init__(self, status, body, url):
        super().__init__(f"HTTP {status} for {url}: {body[:300]}")
        self.status, self.body = status, body


class MultipartBody:
    """File-like multipart/form-data body that streams file parts from disk (no full read into memory)."""

    def __init__(self, fields, files):
        self.boundary = "----immichpihandbook" + uuid.uuid4().hex
        b = self.boundary.encode()
        self.segments = []  # bytes or (path, size)
        for name, value in fields.items():
            if value is None:
                continue
            self.segments.append(b"--" + b + f'\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        for name, (filename, source, ctype) in files.items():
            head = b"--" + b + f'\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
            self.segments.append(head)
            if isinstance(source, bytes):
                self.segments.append(source)
            else:
                self.segments.append((source, os.path.getsize(source)))
            self.segments.append(b"\r\n")
        self.segments.append(b"--" + b + b"--\r\n")
        self.length = sum(len(s) if isinstance(s, bytes) else s[1] for s in self.segments)
        self._idx, self._fh, self._pos = 0, None, 0

    def content_type(self):
        return f"multipart/form-data; boundary={self.boundary}"

    def __len__(self):
        return self.length

    def read(self, n=-1):
        out = bytearray()
        want = self.length if n is None or n < 0 else n
        while len(out) < want and self._idx < len(self.segments):
            seg = self.segments[self._idx]
            if isinstance(seg, bytes):
                take = seg[self._pos:self._pos + (want - len(out))]
                out += take
                self._pos += len(take)
                if self._pos >= len(seg):
                    self._idx, self._pos = self._idx + 1, 0
            else:
                if self._fh is None:
                    self._fh = open(seg[0], "rb")
                data = self._fh.read(want - len(out))
                if not data:
                    self._fh.close()
                    self._fh, self._idx, self._pos = None, self._idx + 1, 0
                else:
                    out += data
        return bytes(out)


def sha1_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


class ImmichClient:
    def __init__(self, base_url, api_key, timeout=900, retries=5, verbose=False):
        u = urllib.parse.urlparse(base_url.rstrip("/"))
        self.scheme, self.host, self.port = u.scheme, u.hostname, u.port or (443 if u.scheme == "https" else 80)
        self.prefix = u.path.rstrip("/") + "/api"
        self.api_key, self.timeout, self.retries, self.verbose = api_key, timeout, retries, verbose

    def _conn(self):
        if self.scheme == "https":
            return http.client.HTTPSConnection(self.host, self.port, timeout=self.timeout, context=ssl.create_default_context())
        return http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)

    def request(self, method, path, body=None, headers=None, json_body=None, body_factory=None):
        hdr = {"Accept": "application/json", "x-api-key": self.api_key}
        if json_body is not None:
            body, hdr["Content-Type"] = json.dumps(json_body).encode(), "application/json"
        if headers:
            hdr.update(headers)
        url = self.prefix + path
        last = None
        for attempt in range(self.retries):
            b = body_factory() if body_factory else body
            if isinstance(b, MultipartBody):
                hdr["Content-Type"], hdr["Content-Length"] = b.content_type(), str(len(b))
            try:
                conn = self._conn()
                conn.request(method, url, body=b, headers=hdr)
                resp = conn.getresponse()
                data = resp.read()
                conn.close()
                if resp.status in (429, 500, 502, 503, 504):
                    raise ApiError(resp.status, data.decode(errors="replace"), url)
                if resp.status >= 400:
                    raise ApiError(resp.status, data.decode(errors="replace"), url)
                return json.loads(data) if data and resp.getheader("Content-Type", "").startswith("application/json") else data
            except ApiError as e:
                last = e
                if e.status not in (429, 500, 502, 503, 504):
                    raise
            except (OSError, socket.timeout, http.client.HTTPException) as e:
                last = e
            wait = min(60, 2 ** attempt)
            if self.verbose:
                print(f"  retry {attempt + 1}/{self.retries} after error: {last} (sleep {wait}s)")
            time.sleep(wait)
        raise last

    # ---- server / user -------------------------------------------------
    def ping(self):
        return self.request("GET", "/server/ping")

    def version(self):
        return self.request("GET", "/server/version")

    def me(self):
        return self.request("GET", "/users/me")

    # ---- assets ----------------------------------------------------------
    def bulk_upload_check(self, items):
        """items: [{'id': any_str, 'checksum': sha1_hex}] -> {id: result}"""
        out = {}
        for i in range(0, len(items), 500):
            res = self.request("POST", "/assets/bulk-upload-check", json_body={"assets": items[i:i + 500]})
            for r in res.get("results", []):
                out[r["id"]] = r
        return out

    def upload(self, path, filename, device_asset_id, device_id, created_at, modified_at, is_favorite=None,
               visibility=None, live_photo_video_id=None, duration_ms=None, sidecar=None, checksum_hex=None, content_type="application/octet-stream"):
        fields = {"deviceAssetId": device_asset_id, "deviceId": device_id, "fileCreatedAt": created_at, "fileModifiedAt": modified_at,
                  "isFavorite": "true" if is_favorite else None, "visibility": visibility, "livePhotoVideoId": live_photo_video_id,
                  "duration": str(int(duration_ms)) if duration_ms else None}
        files = {"assetData": (filename, path, content_type)}
        if sidecar:
            files["sidecarData"] = (filename + ".xmp", sidecar.encode() if isinstance(sidecar, str) else sidecar, "application/xml")
        headers = {"x-immich-checksum": checksum_hex} if checksum_hex else None
        return self.request("POST", "/assets", headers=headers, body_factory=lambda: MultipartBody(fields, files))

    def get_asset(self, asset_id):
        return self.request("GET", f"/assets/{asset_id}")

    def update_asset(self, asset_id, **fields):
        return self.request("PUT", f"/assets/{asset_id}", json_body=fields)

    # ---- albums / stacks ---------------------------------------------------
    def albums(self):
        return self.request("GET", "/albums")

    def create_album(self, name, asset_ids=None, description=None):
        body = {"albumName": name}
        if asset_ids:
            body["assetIds"] = asset_ids
        if description:
            body["description"] = description
        return self.request("POST", "/albums", json_body=body)

    def add_to_album(self, album_id, asset_ids):
        out = []
        for i in range(0, len(asset_ids), 500):
            out += self.request("PUT", f"/albums/{album_id}/assets", json_body={"ids": asset_ids[i:i + 500]})
        return out

    def create_stack(self, asset_ids):
        return self.request("POST", "/stacks", json_body={"assetIds": asset_ids})


if __name__ == "__main__":
    import sys
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:2283"
    c = ImmichClient(base, api_key="")
    print("ping:", c.ping(), " version:", c.version())
    body = MultipartBody({"a": "1"}, {"f": ("x.txt", b"hello", "text/plain")})
    assert len(body.read()) == len(body)
    print("multipart body ok")
