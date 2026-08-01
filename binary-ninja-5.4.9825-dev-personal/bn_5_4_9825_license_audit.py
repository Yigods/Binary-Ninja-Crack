#!/usr/bin/env python3
"""Binary Ninja 5.4.9825-dev Personal license verifier/auditor.

This tool does not contain a private signing key and cannot create a new vendor
license. It verifies existing licenses using the public key extracted from this
specific build, and can demonstrate the unsigned expiresEpoch field on a valid
fixture without touching the installed application.
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PUBLIC_KEY = HERE / "bn_5.4.9825_license_public.pem"
SIGNED_FIELDS = ("product", "email", "serial", "created", "type", "count", "data")


def decode_signature(value: str) -> bytes:
    """Match the binary's permissive standard/URL-safe Base64 decoding."""
    raw = value.encode("ascii")
    raw += b"=" * (-len(raw) % 4)
    return base64.b64decode(raw, altchars=b"-_", validate=False)


def canonical_payload(license_obj: dict) -> bytes:
    """Build the exact signed byte stream: seven fields separated by NUL bytes."""
    missing = [key for key in SIGNED_FIELDS if key not in license_obj]
    if missing:
        raise ValueError("missing signed field(s): " + ", ".join(missing))
    if not isinstance(license_obj["count"], int):
        raise ValueError("count must be an integer")

    values: list[bytes] = []
    for key in SIGNED_FIELDS:
        value = str(license_obj[key]) if key == "count" else license_obj[key]
        if not isinstance(value, str):
            raise ValueError(f"{key} must be a string")
        values.append(value.encode("utf-8"))
    return b"\0".join(values)


def verify(license_obj: dict, public_key: Path = PUBLIC_KEY) -> tuple[bool, str]:
    if not isinstance(license_obj.get("signature"), str):
        return False, "missing or non-string signature"
    try:
        payload = canonical_payload(license_obj)
        signature = decode_signature(license_obj["signature"])
    except (ValueError, UnicodeEncodeError) as exc:
        return False, str(exc)

    with tempfile.TemporaryDirectory(prefix="bn-license-audit-") as tempdir:
        root = Path(tempdir)
        payload_path = root / "payload.bin"
        signature_path = root / "signature.bin"
        payload_path.write_bytes(payload)
        signature_path.write_bytes(signature)
        proc = subprocess.run(
            ["openssl", "dgst", "-sha256", "-verify", str(public_key),
             "-signature", str(signature_path), str(payload_path)],
            text=True, capture_output=True,
        )
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def read_license(path: Path) -> tuple[list[dict], bool]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        return [value], True
    if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        return value, False
    raise ValueError("top-level JSON value must be an object or a non-empty array of objects")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("license", type=Path, help="JSON license fixture to inspect")
    parser.add_argument("--public-key", type=Path,
                        help="PEM public key (default: public key extracted from the original build)")
    parser.add_argument("--show-payload", action="store_true", help="print canonical signed bytes as hex")
    parser.add_argument("--set-expiry", type=int, metavar="UNIX_EPOCH",
                        help="write a copy with only expiresEpoch changed")
    parser.add_argument("--out", type=Path, help="destination required with --set-expiry")
    args = parser.parse_args()

    if (args.set_expiry is None) != (args.out is None):
        parser.error("--set-expiry and --out must be supplied together")
    try:
        public_key = args.public_key or PUBLIC_KEY
        if not public_key.is_file():
            raise ValueError(f"public key does not exist: {public_key}")
        licenses, was_object = read_license(args.license)
        results = [verify(item, public_key) for item in licenses]
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    ok = all(result[0] for result in results)
    print(f"license_entries={len(licenses)}")
    for index, (item, (valid, detail)) in enumerate(zip(licenses, results)):
        print(f"entry[{index}].signature_valid={str(valid).lower()}")
        print(f"entry[{index}].signature_result={detail}")
        print(f"entry[{index}].expiresEpoch={item.get('expiresEpoch')!r} (not included in signed payload)")
    if args.show_payload:
        for index, item in enumerate(licenses):
            print(f"entry[{index}].payload_hex=" + canonical_payload(item).hex())

    if args.set_expiry is not None:
        if not ok:
            print("refusing to write: source signature is not valid for this build", file=sys.stderr)
            return 1
        for item in licenses:
            item["expiresEpoch"] = args.set_expiry
        written: object = licenses[0] if was_object else licenses
        args.out.write_text(json.dumps(written, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        patched, _ = read_license(args.out)
        patched_results = [verify(item, public_key) for item in patched]
        patched_ok = all(result[0] for result in patched_results)
        print(f"patched_signature_valid={str(patched_ok).lower()}")
        return 0 if patched_ok else 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
