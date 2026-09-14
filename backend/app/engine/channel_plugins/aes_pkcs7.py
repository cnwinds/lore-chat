"""企微/公众号回调 AES-256-CBC + 32 字节 PKCS7（官方 WXBizMsgCrypt 口径）。"""

from __future__ import annotations

import base64
import hashlib
import os
import socket
import struct

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError:  # pragma: no cover - CI 装 cryptography
    Cipher = None  # type: ignore[misc, assignment]
    algorithms = None  # type: ignore[misc, assignment]
    modes = None  # type: ignore[misc, assignment]

_BLOCK = 32


def decode_aes_key(encoding_aes_key: str) -> bytes:
    raw = (encoding_aes_key or "").strip()
    if not raw:
        raise ValueError("缺少 EncodingAESKey")
    padded = raw + ("=" * ((4 - len(raw) % 4) % 4))
    key = base64.b64decode(padded)
    if len(key) != 32:
        raise ValueError("EncodingAESKey 无效")
    return key


def _pkcs7_pad(data: bytes) -> bytes:
    amount = _BLOCK - (len(data) % _BLOCK)
    return data + bytes([amount] * amount)


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise ValueError("empty")
    amount = data[-1]
    if amount < 1 or amount > _BLOCK or data[-amount:] != bytes([amount] * amount):
        raise ValueError("bad padding")
    return data[:-amount]


def _aes_crypt(key: bytes, data: bytes, *, encrypt: bool) -> bytes:
    if Cipher is None:
        raise RuntimeError("需要 cryptography 才能加解密企微回调")
    iv = key[:16]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    if encrypt:
        buf = _pkcs7_pad(data)
        encryptor = cipher.encryptor()
        return encryptor.update(buf) + encryptor.finalize()
    decryptor = cipher.decryptor()
    return _pkcs7_unpad(decryptor.update(data) + decryptor.finalize())


def encrypt_msg(aes_key: bytes, corp_id: str, plaintext: str | bytes) -> str:
    raw = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext
    random = os.urandom(16)
    packed = random + struct.pack(">I", len(raw)) + raw + corp_id.encode("utf-8")
    return base64.b64encode(_aes_crypt(aes_key, packed, encrypt=True)).decode("ascii")


def decrypt_msg(aes_key: bytes, corp_id: str, encrypt_b64: str) -> str:
    blob = base64.b64decode((encrypt_b64 or "").strip())
    plain = _aes_crypt(aes_key, blob, encrypt=False)
    msg_len = struct.unpack(">I", plain[16:20])[0]
    msg = plain[20 : 20 + msg_len]
    received_id = plain[20 + msg_len :].decode("utf-8", errors="replace")
    if corp_id and received_id and received_id != corp_id:
        raise ValueError("回调 corp_id 不匹配")
    return msg.decode("utf-8")


def signature(token: str, timestamp: str, nonce: str, encrypt: str) -> str:
    pieces = [token or "", timestamp or "", nonce or "", encrypt or ""]
    pieces.sort()
    return hashlib.sha1("".join(pieces).encode("utf-8")).hexdigest()


def local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "127.0.0.1"
