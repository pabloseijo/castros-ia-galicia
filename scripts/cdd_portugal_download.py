#!/usr/bin/env python3
"""Descarga reanudable del LiDAR/MDT portugués desde el CDD de la DGT.

No evalúa contra el precinto. Solo consulta STAC, autentica contra Keycloak,
genera URLs S3 firmadas y descarga los ficheros al directorio de entrada que
`scripts/ingerir_portugal.sh` ya sabe recoger.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse

import requests


DEFAULT_COLLECTIONS = ("MDT-50cm",)


class AuthRequired(RuntimeError):
    """The CDD redirected an asset request to the login flow."""


class FirstFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_form = False
        self.action: str | None = None
        self.method = "get"
        self.inputs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = {k: v or "" for k, v in attrs}
        if tag == "form" and self.action is None:
            self.in_form = True
            self.action = attrs_d.get("action")
            self.method = attrs_d.get("method", "get").lower()
        elif tag == "input" and self.in_form:
            name = attrs_d.get("name")
            if name:
                self.inputs[name] = attrs_d.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self.in_form:
            self.in_form = False


@dataclass(frozen=True)
class PlanRow:
    orden: str
    lon_min: float
    lat_min: float
    lon_max: float
    lat_max: float


@dataclass
class Asset:
    orden: str
    collection: str
    item_id: str
    href: str
    asset_type: str
    size: int | None
    signed_url: str | None = None


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip("'\""))


def parse_orders(spec: str) -> set[str]:
    out: set[str] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(str(n) for n in range(int(a), int(b) + 1))
        else:
            out.add(str(int(part)))
    return out


def read_plan(path: Path, orders: set[str] | None) -> list[PlanRow]:
    rows: list[PlanRow] = []
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            orden = str(int(row["orden"]))
            if orders and orden not in orders:
                continue
            rows.append(
                PlanRow(
                    orden=orden,
                    lon_min=float(row["lon_min"]),
                    lat_min=float(row["lat_min"]),
                    lon_max=float(row["lon_max"]),
                    lat_max=float(row["lat_max"]),
                )
            )
    return rows


def make_session() -> requests.Session:
    sess = requests.Session()
    sess.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (CastrosIA; local research downloader)",
            "Accept-Language": "es,en;q=0.8,pt;q=0.7",
        }
    )
    return sess


def collection_asset(feature: dict) -> tuple[str, str, str, int | None]:
    assets = feature.get("assets") or {}
    if not assets:
        raise ValueError(f"feature {feature.get('id')} has no assets")
    key = "data" if "data" in assets else "Data" if "Data" in assets else next(iter(assets))
    asset = assets[key]
    href = asset["href"]
    asset_type = asset.get("type", "")
    size = feature.get("properties", {}).get("file:size")
    try:
        size_i = int(size) if size is not None else None
    except (TypeError, ValueError):
        size_i = None
    return href, key, asset_type, size_i


def query_assets(sess: requests.Session, base_url: str, row: PlanRow, collection: str) -> list[Asset]:
    payload = {
        "bbox": [row.lon_min, row.lat_min, row.lon_max, row.lat_max],
        "limit": 1000,
        "collections": [collection],
    }
    resp = sess.post(f"{base_url}/dgt-be/v1/search", json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    assets: list[Asset] = []
    for feature in data.get("features", []):
        href, _asset_key, asset_type, size = collection_asset(feature)
        assets.append(
            Asset(
                orden=row.orden,
                collection=collection,
                item_id=feature.get("id", ""),
                href=href,
                asset_type=asset_type,
                size=size,
            )
        )
    return assets


def login(sess: requests.Session, sample_download_href: str, username: str, password: str) -> None:
    resp = sess.get(sample_download_href, timeout=60, allow_redirects=True)
    parser = FirstFormParser()
    parser.feed(resp.text)
    if not parser.action:
        if "dgt-fe/downloads" in resp.url:
            return
        raise RuntimeError(f"no login form found; final URL was {resp.url}")

    form = dict(parser.inputs)
    form["username"] = username
    form["password"] = password
    posted = sess.post(
        parser.action,
        data=form,
        timeout=60,
        allow_redirects=True,
        headers={"Referer": resp.url},
    )
    final = posted.url
    body = posted.text[:2000].lower()
    if "verify_email" in final.lower() or "verificação do endereço" in body:
        raise RuntimeError("account login requires email verification")
    if "invalid" in body and "password" in body:
        raise RuntimeError("login failed: invalid credentials")
    if "dgt-fe" not in final and "download" not in body:
        raise RuntimeError(f"login did not reach CDD app; final URL was {final}")


def sign_asset(sess: requests.Session, href: str) -> str:
    resp = sess.head(href, timeout=60, allow_redirects=False)
    if resp.status_code != 302 or not resp.headers.get("location"):
        raise RuntimeError(f"could not sign asset: HTTP {resp.status_code} {resp.text[:120]}")
    location = resp.headers["location"]
    if looks_like_login_url(location):
        raise AuthRequired("asset signing redirected to login")
    return location


def looks_like_login_url(url: str) -> bool:
    parsed = urlparse(url)
    text = f"{parsed.netloc}{parsed.path}".lower()
    return any(
        marker in text
        for marker in (
            "auth.cdd",
            "keycloak",
            "/realms/",
            "/login",
            "login-actions",
            "openid-connect/auth",
        )
    ) or Path(unquote(parsed.path)).name.lower() == "login"


def filename_from_signed_url(url: str, fallback: str) -> str:
    name = Path(unquote(urlparse(url).path)).name
    return name or fallback


def destination_for_asset(asset: Asset, signed_url: str, out_dir: Path) -> tuple[str, Path]:
    filename = filename_from_signed_url(signed_url, asset.item_id)
    if filename.lower() == "login":
        raise AuthRequired("signed URL resolved to login instead of an asset")
    return filename, out_dir / asset.orden / asset.collection / filename


def download_signed(url: str, dest: Path, expected_size: int | None, chunk_mb: int) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    headers = {}
    mode = "wb"
    existing = tmp.stat().st_size if tmp.exists() else 0
    if existing:
        headers["Range"] = f"bytes={existing}-"
        mode = "ab"

    with requests.get(url, stream=True, timeout=120, headers=headers) as resp:
        if existing and resp.status_code == 200:
            existing = 0
            mode = "wb"
        if resp.status_code not in (200, 206):
            raise RuntimeError(f"download failed: HTTP {resp.status_code} {resp.text[:120]}")
        ctype = (resp.headers.get("content-type") or "").lower()
        if looks_like_login_url(resp.url) or "text/html" in ctype:
            raise AuthRequired(f"download redirected to login/html for {dest.name}")
        with tmp.open(mode + "") as fh:
            for chunk in resp.iter_content(chunk_size=chunk_mb * 1024 * 1024):
                if chunk:
                    fh.write(chunk)

    size = tmp.stat().st_size
    if expected_size and size != expected_size:
        raise RuntimeError(f"size mismatch for {dest.name}: got {size}, expected {expected_size}")
    tmp.replace(dest)
    return "downloaded"


def print_download_result(result: tuple[str, Asset, str, int, float]) -> None:
    status, asset, filename, size, elapsed = result
    if status == "skip":
        print(f"skip {asset.orden}/{asset.collection}/{filename}", flush=True)
        return
    elapsed = max(elapsed, 0.001)
    print(
        f"{status} {asset.orden}/{asset.collection}/{filename} "
        f"{size / 1e6:.1f} MB in {elapsed:.1f}s ({size / elapsed / 1e6:.1f} MB/s)",
        flush=True,
    )


def write_manifest(path: Path, assets: Iterable[Asset], append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and append
    mode = "a" if append else "w"
    with path.open(mode, newline="", encoding="utf-8") as fh:
        fieldnames = [
            "orden",
            "collection",
            "item_id",
            "asset_type",
            "size",
            "href",
            "signed",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        if not exists:
            writer.writeheader()
        for asset in assets:
            writer.writerow(
                {
                    "orden": asset.orden,
                    "collection": asset.collection,
                    "item_id": asset.item_id,
                    "asset_type": asset.asset_type,
                    "size": asset.size or "",
                    "href": asset.href,
                    "signed": "1" if asset.signed_url else "0",
                }
            )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", type=Path, default=Path("data/plan-descarga-portugal.tsv"))
    ap.add_argument("--env", type=Path, default=Path(".env"))
    ap.add_argument("--orders", default="1", help="Ej.: 1, 1-18, 1,3,8")
    ap.add_argument("--collections", nargs="+", default=list(DEFAULT_COLLECTIONS))
    ap.add_argument("--out-dir", type=Path, default=Path("data/entrada-portugal"))
    ap.add_argument("--manifest", type=Path, default=Path("data/cdd-portugal-assets.tsv"))
    ap.add_argument("--append-manifest", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-files", type=int, default=0)
    ap.add_argument("--chunk-mb", type=int, default=8)
    ap.add_argument("--workers", type=int, default=1, help="Descargas concurrentes; 1 conserva el modo serie")
    ap.add_argument("--retries", type=int, default=4,
                    help="reintentos por asset cuando la sesion expira o hay cortes de red")
    args = ap.parse_args()

    load_dotenv(args.env)
    base_url = os.environ.get("CDD_BASE_URL", "https://cdd.dgterritorio.gov.pt").rstrip("/")
    username = os.environ.get("CDD_USERNAME") or os.environ.get("DGT_CDD_USERNAME")
    password = os.environ.get("CDD_PASSWORD") or os.environ.get("DGT_CDD_PASSWORD")

    orders = parse_orders(args.orders)
    rows = read_plan(args.plan, orders)
    if not rows:
        raise SystemExit("no matching plan rows")

    sess = make_session()
    all_assets: list[Asset] = []
    for row in rows:
        for collection in args.collections:
            assets = query_assets(sess, base_url, row, collection)
            total = sum(a.size or 0 for a in assets)
            print(f"orden {row.orden} {collection}: {len(assets)} assets, {total / 1e9:.2f} GB", flush=True)
            all_assets.extend(assets)
    if not all_assets:
        raise SystemExit("no assets found")

    if args.dry_run:
        write_manifest(args.manifest, all_assets, append=args.append_manifest)
        print(f"manifest: {args.manifest}", flush=True)
        return 0

    if not username or not password:
        raise SystemExit("missing CDD_USERNAME/CDD_PASSWORD in .env")
    login(sess, all_assets[0].href, username, password)
    print("login: ok", flush=True)

    selected_assets = all_assets[: args.max_files] if args.max_files else all_assets
    cookie_snapshot = requests.cookies.RequestsCookieJar()
    cookie_snapshot.update(sess.cookies)

    def fetch_asset(asset: Asset) -> tuple[str, Asset, str, int, float]:
        last_error: Exception | None = None
        for attempt in range(1, max(1, args.retries) + 1):
            worker_sess = make_session()
            worker_sess.cookies.update(cookie_snapshot)
            if attempt > 1:
                login(worker_sess, asset.href, username, password)
            try:
                signed = sign_asset(worker_sess, asset.href)
                asset.signed_url = signed
                filename, dest = destination_for_asset(asset, signed, args.out_dir)
                if dest.exists() and (not asset.size or dest.stat().st_size == asset.size):
                    return "skip", asset, filename, dest.stat().st_size, 0.0
                t0 = time.time()
                status = download_signed(signed, dest, asset.size, args.chunk_mb)
                elapsed = max(time.time() - t0, 0.001)
                size = dest.stat().st_size
                return status, asset, filename, size, elapsed
            except AuthRequired as exc:
                last_error = exc
                stale = args.out_dir / asset.orden / asset.collection / "login.part"
                if stale.exists():
                    stale.unlink()
                time.sleep(min(10, attempt * 2))
                continue
        raise RuntimeError(f"failed after {args.retries} retries for {asset.item_id}: {last_error}")

    if args.workers <= 1:
        for asset in selected_assets:
            print_download_result(fetch_asset(asset))
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(fetch_asset, asset) for asset in selected_assets]
            for fut in as_completed(futures):
                print_download_result(fut.result())

    write_manifest(args.manifest, all_assets, append=args.append_manifest)
    print(f"manifest: {args.manifest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
