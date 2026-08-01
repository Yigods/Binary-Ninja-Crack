#!/usr/bin/env python3
"""Create a test RSA keypair, issue a matching BN 5.4.9825 license, and rekey arm64 core copies.

Never operates in-place: --input and --out must differ. The patch is for the
arm64 slice of libbinaryninjacore.1.dylib from 5.4.9825-dev_personal only.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ARM64_SLICE_OFFSET = 0x97F8000
MOVZ_START_VA = 0x733184
WORD_COUNT = 73                 # Bytes 0x000..0x123; final two bytes are fixed DER exponent tail.
XOR_KEY = 0xF9336918            # The decoder uses w28 + 0x100.
ORIGINAL_PUBLIC_DER_SHA256 = "8ce4389e25ed2b3e084dfdfc88321faff82e072d5b92db602ed236825942de7f"
SIGNED_FIELDS = ("product", "email", "serial", "created", "type", "count", "data")
# The final 24 bytes of the 0x118-byte data field are RC4-protected with a
# key derived from the preceding 0x100 random bytes. This is a format check in
# the current core, independent of the RSA signature.
DATA_MARKER = bytes.fromhex("9C2AAA09A4E2252B0BA125DB1E1CD272207D97CCA8446899")


def run(args: list[str], *, input: bytes | None = None) -> bytes:
    p = subprocess.run(args, input=input, capture_output=True)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout).decode(errors="replace").strip())
    return p.stdout


def public_der(private_key: Path) -> bytes:
    return run(["openssl", "pkey", "-in", str(private_key), "-pubout", "-outform", "DER"])


def canonical(obj: dict) -> bytes:
    values: list[bytes] = []
    for field in SIGNED_FIELDS:
        value = str(obj[field]) if field == "count" else obj[field]
        if not isinstance(value, str):
            raise ValueError(f"{field} has to be a string")
        values.append(value.encode("utf-8"))
    return b"\0".join(values)


def rc4(key: bytes, data: bytes) -> bytes:
    """Small dependency-free RC4 implementation for the license data wrapper."""
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + key[i % len(key)]) & 0xff
        state[i], state[j] = state[j], state[i]
    out = bytearray()
    i = j = 0
    for byte in data:
        i = (i + 1) & 0xff
        j = (j + state[i]) & 0xff
        state[i], state[j] = state[j], state[i]
        out.append(byte ^ state[(state[i] + state[j]) & 0xff])
    return bytes(out)


def make_license_data() -> str:
    prefix = __import__("secrets").token_bytes(0x100)
    protected = rc4(hashlib.md5(prefix).digest(), DATA_MARKER)
    return base64.b64encode(prefix + protected).decode("ascii")


def validate_license_data(value: str) -> None:
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise ValueError("data must be standard Base64") from exc
    if len(raw) != 0x118:
        raise ValueError("data must decode to exactly 0x118 bytes")
    marker = rc4(hashlib.md5(raw[:0x100]).digest(), raw[0x100:])
    if marker != DATA_MARKER:
        raise ValueError("data does not contain the expected RC4-wrapped marker")


def extract_pinned_public_der(image: bytes) -> bytes:
    """Recover the arm64 DER blob exactly as the target's MOVZ/MOVK decoder does."""
    cipher = bytearray()
    for index in range(WORD_COUNT):
        offset = ARM64_SLICE_OFFSET + MOVZ_START_VA + index * 12
        movz, movk = struct.unpack_from("<II", image, offset)
        # MOVZ W8,#imm16 ; MOVK W8,#imm16,LSL#16 ; STR W8,[...] 
        if (movz & 0xffe0001f) != 0x52800008 or (movk & 0xffe0001f) != 0x72a00008:
            raise RuntimeError("input does not contain the expected arm64 public-key decoder")
        word = ((movz >> 5) & 0xffff) | (((movk >> 5) & 0xffff) << 16)
        cipher.extend(struct.pack("<I", word))
    decoded = bytes(byte ^ ((XOR_KEY >> (8 * (i % 4))) & 0xff) for i, byte in enumerate(cipher))
    return decoded + bytes.fromhex("0001")


def cmd_init(args: argparse.Namespace) -> None:
    if args.key.exists() and not args.force:
        raise RuntimeError(f"refusing to overwrite {args.key}; pass --force")
    args.key.parent.mkdir(parents=True, exist_ok=True)
    run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(args.key)])
    args.key.chmod(0o600)
    args.public.parent.mkdir(parents=True, exist_ok=True)
    args.public.write_bytes(public_der(args.key))
    print(f"private_key={args.key}")
    print(f"public_key_der={args.public}")


def cmd_issue(args: argparse.Namespace) -> None:
    created = args.created or dt.datetime.now(tz=dt.timezone.utc).isoformat(timespec="milliseconds")
    obj = {
        "product": args.product,
        "email": args.email,
        "serial": args.serial,
        "created": created,
        "type": args.type,
        "count": args.count,
        "data": args.data if args.data is not None else make_license_data(),
    }
    if args.expires is not None:
        obj["expiresEpoch"] = args.expires
    validate_license_data(obj["data"])
    with tempfile.TemporaryDirectory(prefix="bn-issue-") as tempdir:
        msg = Path(tempdir) / "message.bin"
        sig = Path(tempdir) / "signature.bin"
        msg.write_bytes(canonical(obj))
        run(["openssl", "dgst", "-sha256", "-sign", str(args.key), "-out", str(sig), str(msg)])
        obj["signature"] = base64.b64encode(sig.read_bytes()).decode("ascii")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload: object = obj if args.bare_object else [obj]
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"license={args.out}")


def cmd_patch_core(args: argparse.Namespace) -> None:
    source = args.input.resolve()
    destination = args.out.resolve()
    if source == destination:
        raise RuntimeError("--input and --out must differ")
    patch_core_file(source, destination, args.key, adhoc_sign=args.adhoc_sign)
    print(f"patched_core={destination}")


def patch_core_file(source: Path, destination: Path, key: Path, *, adhoc_sign: bool) -> None:
    data = bytearray(source.read_bytes())
    if len(data) < ARM64_SLICE_OFFSET + MOVZ_START_VA + WORD_COUNT * 12:
        raise RuntimeError("input is not the expected universal 5.4.9825 core image")
    original_der = extract_pinned_public_der(data)
    if hashlib.sha256(original_der).hexdigest() != ORIGINAL_PUBLIC_DER_SHA256:
        raise RuntimeError("input is not the unmodified 5.4.9825-dev_personal arm64 core")
    der = public_der(key)
    if len(der) != 294 or not der.startswith(bytes.fromhex("30820122300d06092a864886f70d01010105000382010f00")) or not der.endswith(bytes.fromhex("0203010001")):
        raise RuntimeError("expected a 2048-bit RSA public key with exponent 65537")

    # The final two decoded bytes come from w28, and all e=65537 SPKI DER keys
    # end in 00 01, so rekeying only needs the 73 explicit 32-bit constants.
    cipher = bytes(b ^ ((XOR_KEY >> (8 * (i % 4))) & 0xff) for i, b in enumerate(der))
    for i in range(WORD_COUNT):
        word = struct.unpack_from("<I", cipher, i * 4)[0]
        off = ARM64_SLICE_OFFSET + MOVZ_START_VA + i * 12
        movz = 0x52800008 | ((word & 0xffff) << 5)
        movk = 0x72A00008 | (((word >> 16) & 0xffff) << 5)
        struct.pack_into("<I", data, off, movz)
        struct.pack_into("<I", data, off + 4, movk)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    if adhoc_sign:
        run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(destination)])


def cmd_install(args: argparse.Namespace) -> None:
    app = args.app.resolve()
    core = app / "Contents/MacOS/libbinaryninjacore.1.dylib"
    if not core.is_file():
        raise RuntimeError(f"not a Binary Ninja app bundle: {app}")
    if not args.license.is_file():
        raise RuntimeError(f"license does not exist: {args.license}")
    backup = args.backup.resolve() if args.backup else core.with_suffix(core.suffix + ".original.backup")
    if backup.exists() and not args.force:
        raise RuntimeError(f"backup already exists: {backup}; pass --force to replace it")
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(core, backup)
    temporary = core.with_name(core.name + ".rekey-tmp")
    replaced = False
    try:
        patch_core_file(core, temporary, args.key, adhoc_sign=False)
        temporary.replace(core)
        replaced = True
        run(["codesign", "--force", "--deep", "--sign", "-", "--timestamp=none", str(app)])
        run(["codesign", "--verify", "--deep", "--strict", str(app)])
        args.license_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.license, args.license_dest)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        if replaced:
            # Do not leave a half-installed unsigned core when post-patch
            # signing or license deployment fails.
            shutil.copy2(backup, core)
        raise
    print(f"backup_core={backup}")
    print(f"patched_app={app}")
    print(f"installed_license={args.license_dest}")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(required=True)
    init = sub.add_parser("init", help="generate a 2048-bit test keypair")
    init.add_argument("--key", type=Path, required=True)
    init.add_argument("--public", type=Path, required=True)
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    issue = sub.add_parser("issue", help="issue a license signed by the supplied test key")
    issue.add_argument("--key", type=Path, required=True)
    issue.add_argument("--out", type=Path, required=True)
    issue.add_argument("--email", required=True)
    issue.add_argument("--serial", required=True)
    issue.add_argument("--expires", type=int, help="optional unsigned Unix expiry field")
    issue.add_argument("--product", default="Binary Ninja Personal")
    issue.add_argument("--type", default="User")
    issue.add_argument("--count", type=int, default=32)
    issue.add_argument("--data", help="Base64 text decoding to exactly 0x118 bytes (default: valid RC4-wrapped data)")
    issue.add_argument("--created")
    issue.add_argument("--bare-object", action="store_true", help="emit an object instead of the normal one-element array")
    issue.set_defaults(func=cmd_issue)

    patch = sub.add_parser("patch-core", help="write a rekeyed arm64 core copy")
    patch.add_argument("--key", type=Path, required=True)
    patch.add_argument("--input", type=Path, required=True)
    patch.add_argument("--out", type=Path, required=True)
    patch.add_argument("--adhoc-sign", action="store_true")
    patch.set_defaults(func=cmd_patch_core)

    install = sub.add_parser("install", help="backup, patch, ad-hoc sign an installed app, and deploy a license")
    install.add_argument("--key", type=Path, required=True)
    install.add_argument("--license", type=Path, required=True)
    install.add_argument("--app", type=Path, default=Path("/Applications/Binary Ninja.app"))
    install.add_argument("--backup", type=Path, help="backup destination for the original core")
    install.add_argument("--license-dest", type=Path,
                         default=Path.home() / "Library/Application Support/Binary Ninja/license.dat")
    install.add_argument("--force", action="store_true", help="replace an existing backup")
    install.set_defaults(func=cmd_install)

    args = parser.parse_args()
    try:
        args.func(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
