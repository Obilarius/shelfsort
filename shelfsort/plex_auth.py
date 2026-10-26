"""Signing in with Plex (official PIN flow) and finding the user's servers.

The user signs in on plex.tv in their own browser; ShelfSort only receives the resulting token.
"""
from __future__ import annotations

import platform
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from urllib.parse import urlencode

import requests

from . import __version__

PLEX_TV = "https://plex.tv/api/v2"
PRODUCT = "ShelfSort"


def _headers(client_id: str, token: str | None = None) -> dict:
    h = {"Accept": "application/json", "X-Plex-Product": PRODUCT, "X-Plex-Version": __version__,
         "X-Plex-Client-Identifier": client_id, "X-Plex-Platform": platform.system(),
         "X-Plex-Device-Name": f"{PRODUCT} ({platform.node()})"}
    if token:
        h["X-Plex-Token"] = token
    return h


@dataclass
class Pin:
    id: int
    code: str


def start_pin(client_id: str) -> Pin:
    r = requests.post(f"{PLEX_TV}/pins", params={"strong": "true"}, headers=_headers(client_id), timeout=15)
    r.raise_for_status()
    data = r.json()
    return Pin(data["id"], data["code"])


def auth_url(client_id: str, pin: Pin) -> str:
    """Page the user opens in the browser to approve ShelfSort."""
    return "https://app.plex.tv/auth#?" + urlencode(
        {"clientID": client_id, "code": pin.code, "context[device][product]": PRODUCT})


def check_pin(client_id: str, pin: Pin) -> str | None:
    """The token once the user has signed in, else None."""
    r = requests.get(f"{PLEX_TV}/pins/{pin.id}", headers=_headers(client_id), timeout=15)
    r.raise_for_status()
    return r.json().get("authToken") or None


@dataclass
class Connection:
    uri: str
    local: bool
    relay: bool


@dataclass
class Server:
    name: str
    client_identifier: str
    access_token: str
    owned: bool
    connections: list[Connection] = field(default_factory=list)


def account_name(client_id: str, token: str) -> str:
    """Name of the signed-in Plex account (to spot a wrong account / Plex Home user)."""
    r = requests.get(f"{PLEX_TV}/user", headers=_headers(client_id, token), timeout=15)
    r.raise_for_status()
    u = r.json()
    return u.get("title") or u.get("username") or u.get("email") or "?"


def resources(client_id: str, token: str) -> list[dict]:
    """All devices of the account as plex.tv reports them."""
    r = requests.get(f"{PLEX_TV}/resources", params={"includeHttps": 1, "includeRelay": 1},
                     headers=_headers(client_id, token), timeout=20)
    r.raise_for_status()
    return r.json()


def servers(client_id: str, token: str, devices: list[dict] | None = None) -> list[Server]:
    """Plex Media Servers the account can use (own ones first)."""
    out = []
    for res in devices if devices is not None else resources(client_id, token):
        if "server" not in (res.get("provides") or ""):
            continue
        conns = []
        for c in res.get("connections", []):
            conns.append(Connection(c["uri"], bool(c.get("local")), bool(c.get("relay"))))
            # the plain http address often works locally even when the https one doesn't resolve
            if c.get("local") and c.get("address") and c.get("port"):
                conns.append(Connection(f"http://{c['address']}:{c['port']}", True, False))
        out.append(Server(res.get("name", "?"), res["clientIdentifier"], res.get("accessToken") or token,
                          bool(res.get("owned")), conns))
    return sorted(out, key=lambda s: (not s.owned, s.name.lower()))


def manual_server(url: str, token: str) -> Server | None:
    """A server entered by hand (e.g. http://192.168.1.5:32400), if it answers with this token."""
    url = url.strip().rstrip("/")
    if not url.startswith("http"):
        url = "http://" + url
    if ":" not in url.split("//", 1)[1]:
        url += ":32400"
    try:
        r = requests.get(f"{url}/identity", headers={"X-Plex-Token": token, "Accept": "application/json"},
                         timeout=5)
        r.raise_for_status()
        info = r.json().get("MediaContainer", {})
        r = requests.get(url, headers={"X-Plex-Token": token, "Accept": "application/json"}, timeout=5)
        r.raise_for_status()  # the root needs a valid token, /identity doesn't
        name = r.json().get("MediaContainer", {}).get("friendlyName") or url
    except (requests.RequestException, ValueError):
        return None
    return Server(name, info.get("machineIdentifier", ""), token, True, [Connection(url, True, False)])


def _reachable(uri: str, token: str) -> bool:
    try:
        r = requests.get(f"{uri}/identity", headers={"X-Plex-Token": token, "Accept": "application/json"},
                         timeout=3)
        return r.ok
    except requests.RequestException:
        return False


def best_connection(server: Server) -> str | None:
    """A reachable address: the first local one that answers, else remote, relay last.

    All addresses are tried in parallel; we don't wait for dead ones to time out once a
    local address has answered.
    """
    rank = {c.uri: (c.relay, not c.local) for c in server.connections}
    pool = ThreadPoolExecutor(8)
    futures = {pool.submit(_reachable, c.uri, server.access_token): c for c in server.connections}
    good: list[Connection] = []
    try:
        for f in as_completed(futures):
            c = futures[f]
            if f.result():
                if c.local and not c.relay:
                    return c.uri
                good.append(c)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return min(good, key=lambda c: rank[c.uri]).uri if good else None
