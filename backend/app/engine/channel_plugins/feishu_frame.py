"""飞书长连接 protobuf Frame（不引入 lark.ws.Client，避免抢 FastAPI 事件循环）。"""

from __future__ import annotations

from dataclasses import dataclass, field

_WIRE_VARINT = 0
_WIRE_FIXED64 = 1
_WIRE_LEN = 2
_WIRE_FIXED32 = 5

FRAME_CONTROL = 0
FRAME_DATA = 1

HEADER_TYPE = "type"
HEADER_MESSAGE_ID = "message_id"
HEADER_SUM = "sum"
HEADER_SEQ = "seq"
HEADER_TRACE_ID = "trace_id"

TYPE_EVENT = "event"
TYPE_CARD = "card"
TYPE_PING = "ping"
TYPE_PONG = "pong"


def _encode_varint(value: int) -> bytes:
    if value < 0:
        value &= (1 << 64) - 1
    out = bytearray()
    while value > 0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value & 0x7F)
    return bytes(out)


def _decode_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while pos < len(buf):
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
        if shift > 70:
            break
    raise ValueError("truncated varint")


def _key(field: int, wire: int) -> bytes:
    return _encode_varint((field << 3) | wire)


def _encode_bytes(field: int, data: bytes) -> bytes:
    return _key(field, _WIRE_LEN) + _encode_varint(len(data)) + data


def _encode_string(field: int, value: str) -> bytes:
    return _encode_bytes(field, value.encode("utf-8"))


def _encode_varint_field(field: int, value: int) -> bytes:
    if not value:
        return b""
    return _key(field, _WIRE_VARINT) + _encode_varint(value)


def _encode_header(key: str, value: str) -> bytes:
    body = _encode_string(1, key) + _encode_string(2, value)
    return _encode_bytes(5, body)


@dataclass
class WsFrame:
    seq_id: int = 0
    log_id: int = 0
    service: int = 0
    method: int = 0
    headers: list[tuple[str, str]] = field(default_factory=list)
    payload: bytes = b""

    def header(self, key: str, default: str | None = None) -> str | None:
        for name, value in self.headers:
            if name == key:
                return value
        return default

    def set_header(self, key: str, value: str) -> None:
        for i, (name, _) in enumerate(self.headers):
            if name == key:
                self.headers[i] = (key, value)
                return
        self.headers.append((key, value))

    def encode(self) -> bytes:
        out = bytearray()
        out += _encode_varint_field(1, self.seq_id)
        out += _encode_varint_field(2, self.log_id)
        out += _encode_varint_field(3, self.service)
        out += _encode_varint_field(4, self.method)
        for key, value in self.headers:
            out += _encode_header(key, value)
        if self.payload:
            out += _encode_bytes(8, self.payload)
        return bytes(out)

    @classmethod
    def decode(cls, buf: bytes) -> "WsFrame":
        pos = 0
        frame = cls()
        while pos < len(buf):
            tag, pos = _decode_varint(buf, pos)
            field = tag >> 3
            wire = tag & 7
            if wire == _WIRE_VARINT:
                value, pos = _decode_varint(buf, pos)
                if field == 1:
                    frame.seq_id = value
                elif field == 2:
                    frame.log_id = value
                elif field == 3:
                    frame.service = value
                elif field == 4:
                    frame.method = value
            elif wire == _WIRE_LEN:
                length, pos = _decode_varint(buf, pos)
                data = buf[pos : pos + length]
                pos += length
                if field == 5:
                    frame.headers.append(_decode_header(data))
                elif field == 6:
                    pass
                elif field == 7:
                    pass
                elif field == 8:
                    frame.payload = data
            elif wire == _WIRE_FIXED64:
                pos += 8
            elif wire == _WIRE_FIXED32:
                pos += 4
            else:
                break
        return frame


def _decode_header(buf: bytes) -> tuple[str, str]:
    pos = 0
    key = ""
    value = ""
    while pos < len(buf):
        tag, pos = _decode_varint(buf, pos)
        field = tag >> 3
        wire = tag & 7
        if wire != _WIRE_LEN:
            if wire == _WIRE_VARINT:
                _, pos = _decode_varint(buf, pos)
            elif wire == _WIRE_FIXED64:
                pos += 8
            elif wire == _WIRE_FIXED32:
                pos += 4
            else:
                break
            continue
        length, pos = _decode_varint(buf, pos)
        data = buf[pos : pos + length]
        pos += length
        text = data.decode("utf-8", errors="replace")
        if field == 1:
            key = text
        elif field == 2:
            value = text
    return key, value


def ping_frame(service_id: int) -> WsFrame:
    return WsFrame(
        service=int(service_id or 0),
        method=FRAME_CONTROL,
        headers=[(HEADER_TYPE, TYPE_PING)],
    )
