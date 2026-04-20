from __future__ import annotations

import struct
import zlib
from pathlib import Path

from .models import RasterImage

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PNGError(ValueError):
    pass


def read_png(path: str | Path) -> RasterImage:
    data = Path(path).read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise PNGError("Not a PNG file")

    offset = len(PNG_SIGNATURE)
    width = height = bit_depth = color_type = interlace = None
    idat = bytearray()

    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        chunk_type = data[offset + 4:offset + 8]
        chunk_data = data[offset + 8:offset + 8 + length]
        offset += 12 + length

        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
                ">IIBBBBB", chunk_data
            )
            if compression != 0 or filter_method != 0:
                raise PNGError("Unsupported PNG compression or filter method")
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break

    if width is None or height is None:
        raise PNGError("PNG missing IHDR")
    if bit_depth != 8:
        raise PNGError("Only 8-bit PNGs are currently supported")
    if interlace != 0:
        raise PNGError("Interlaced PNGs are not supported")

    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise PNGError(f"Unsupported PNG color type: {color_type}")

    row_length = width * channels
    raw = zlib.decompress(bytes(idat))
    expected = height * (row_length + 1)
    if len(raw) != expected:
        raise PNGError("Unexpected decompressed PNG size")

    rows: list[bytes] = []
    prev = bytes(row_length)
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        scanline = bytearray(raw[cursor + 1:cursor + 1 + row_length])
        cursor += row_length + 1
        _unfilter_scanline(filter_type, scanline, prev, channels)
        row = bytes(scanline)
        rows.append(row)
        prev = row

    pixels = []
    for row in rows:
        converted = []
        for index in range(0, len(row), channels):
            converted.append(_to_rgba(row[index:index + channels], color_type))
        pixels.append(converted)

    return RasterImage(width=width, height=height, pixels=pixels)


def write_png(path: str | Path, image: RasterImage) -> None:
    rows = bytearray()
    for row in image.pixels:
        rows.append(0)
        for red, green, blue, alpha in row:
            rows.extend((red, green, blue, alpha))

    compressed = zlib.compress(bytes(rows), level=9)
    ihdr = struct.pack(">IIBBBBB", image.width, image.height, 8, 6, 0, 0, 0)

    with Path(path).open("wb") as handle:
        handle.write(PNG_SIGNATURE)
        handle.write(_chunk(b"IHDR", ihdr))
        handle.write(_chunk(b"IDAT", compressed))
        handle.write(_chunk(b"IEND", b""))


def _chunk(name: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(name + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", crc)


def _to_rgba(raw: bytes, color_type: int) -> tuple[int, int, int, int]:
    if color_type == 0:
        value = raw[0]
        return (value, value, value, 255)
    if color_type == 2:
        return (raw[0], raw[1], raw[2], 255)
    if color_type == 4:
        value, alpha = raw
        return (value, value, value, alpha)
    return (raw[0], raw[1], raw[2], raw[3])


def _unfilter_scanline(filter_type: int, scanline: bytearray, prev: bytes, bpp: int) -> None:
    if filter_type == 0:
        return
    if filter_type == 1:
        for index in range(len(scanline)):
            left = scanline[index - bpp] if index >= bpp else 0
            scanline[index] = (scanline[index] + left) & 0xFF
        return
    if filter_type == 2:
        for index in range(len(scanline)):
            scanline[index] = (scanline[index] + prev[index]) & 0xFF
        return
    if filter_type == 3:
        for index in range(len(scanline)):
            left = scanline[index - bpp] if index >= bpp else 0
            up = prev[index]
            scanline[index] = (scanline[index] + ((left + up) // 2)) & 0xFF
        return
    if filter_type == 4:
        for index in range(len(scanline)):
            left = scanline[index - bpp] if index >= bpp else 0
            up = prev[index]
            up_left = prev[index - bpp] if index >= bpp else 0
            scanline[index] = (scanline[index] + _paeth(left, up, up_left)) & 0xFF
        return
    raise PNGError(f"Unsupported PNG filter type: {filter_type}")


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c
