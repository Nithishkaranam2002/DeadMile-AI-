"""Small download helpers with explicit size limits (stdlib only)."""

import shutil
import urllib.request
from collections.abc import Iterator
from pathlib import Path

USER_AGENT = "dmlab/0.1 (DeadMile AI experiment lab)"
ONE_GB = 1_000_000_000


def _open(url: str, timeout: float = 60):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, timeout=timeout)


def remote_size(url: str) -> int | None:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        size = resp.headers.get("Content-Length")
    return int(size) if size else None


def fetch_bytes(url: str, max_bytes: int) -> bytes:
    with _open(url) as resp:
        data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise RuntimeError(f"{url} is larger than the {max_bytes} byte limit")
    return data


def download_file(url: str, dest: Path, max_bytes: int = ONE_GB) -> Path:
    """Download to dest unless it exists. Refuses anything above max_bytes."""
    if dest.exists():
        return dest
    size = remote_size(url)
    if size is None or size > max_bytes:
        raise RuntimeError(f"{url}: size {size} is unknown or above {max_bytes} bytes")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with _open(url, timeout=120) as resp, tmp.open("wb") as f:
        shutil.copyfileobj(resp, f, length=1 << 20)
    tmp.rename(dest)
    return dest


def stream_chunks(url: str, chunk_size: int = 1 << 20) -> Iterator[bytes]:
    """Stream a remote file without storing it."""
    with _open(url, timeout=300) as resp:
        while chunk := resp.read(chunk_size):
            yield chunk
