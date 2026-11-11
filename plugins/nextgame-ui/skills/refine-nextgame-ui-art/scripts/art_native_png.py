"""Copy a validated native RGBA8 PNG stream through IEND into a new file.

This lossless export boundary preserves every PNG byte, including compressed
IDAT payloads. It only removes bytes after IEND; it never renders, unfilters,
re-encodes or changes a capture contract. Native origin and rendering correctness
remain the caller's responsibility. The explicit context attests that scope.

Supported native subset: IHDR, consecutive IDAT chunks, IEND; RGBA8, compression
and filter method 0, no interlace. Other chunks (including metadata/APNG) are
rejected rather than silently discarded. Parser limits below are resource
bounds, not UI/design dimensions. PNG structure: https://www.w3.org/TR/png-3/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import zlib

NATIVE_CONTEXT = 'unreal-native-rgba8-noninterlaced/1'
MAX_SOURCE_BYTES = 128 * 1024 * 1024
MAX_DIMENSION = 16384
MAX_PIXELS = 16 * 1024 * 1024
MAX_CHUNKS = 4096
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


class NativePngError(ValueError):
    """A fixed diagnostic code/message; input or trailer bytes are never logged."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise NativePngError(code, message)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _read_source(path: Path) -> tuple[bytes, tuple[int, int, int, int, int]]:
    with path.open('rb') as handle:
        before = os.fstat(handle.fileno())
        _require(stat.S_ISREG(before.st_mode), 'source.type', 'Input must be a regular file.')
        _require(0 < before.st_size <= MAX_SOURCE_BYTES, 'source.size', 'Input exceeds the supported file-size bounds.')
        data = handle.read(MAX_SOURCE_BYTES + 1)
        after = os.fstat(handle.fileno())
    _require(len(data) <= MAX_SOURCE_BYTES, 'source.size', 'Input exceeds the supported file-size bounds.')
    _require(_identity(before) == _identity(after) and len(data) == before.st_size,
             'source.changed', 'Input changed during its read.')
    return data, _identity(after)


def _unchanged_source(path: Path, identity: tuple[int, int, int, int, int], digest: str) -> None:
    hasher = hashlib.sha256()
    with path.open('rb') as handle:
        _require(_identity(os.fstat(handle.fileno())) == identity, 'source.changed', 'Input identity changed.')
        total = 0
        while block := handle.read(1024 * 1024):
            total += len(block)
            _require(total <= MAX_SOURCE_BYTES, 'source.changed', 'Input changed during validation.')
            hasher.update(block)
        _require(_identity(os.fstat(handle.fileno())) == identity, 'source.changed', 'Input identity changed.')
    _require(hasher.hexdigest() == digest, 'source.changed', 'Input bytes changed during validation.')


def _parse_native_stream(data: bytes) -> tuple[int, dict]:
    _require(data.startswith(PNG_SIGNATURE), 'png.signature', 'Invalid or truncated PNG signature.')
    offset, chunk_count = len(PNG_SIGNATURE), 0
    header = None
    compressed_parts = []
    while True:
        _require(offset + 12 <= len(data), 'png.truncated', 'Missing IEND or truncated PNG chunk.')
        length = struct.unpack_from('>I', data, offset)[0]
        _require(length <= 0x7fffffff, 'png.chunk-size', 'PNG chunk length exceeds the format bound.')
        end = offset + length + 12
        _require(end <= len(data), 'png.truncated', 'PNG chunk data or CRC is truncated.')
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:end - 4]
        recorded_crc = struct.unpack_from('>I', data, end - 4)[0]
        actual_crc = zlib.crc32(payload, zlib.crc32(kind)) & 0xffffffff
        _require(actual_crc == recorded_crc, 'png.crc', 'PNG chunk CRC does not match.')
        chunk_count += 1
        _require(chunk_count <= MAX_CHUNKS, 'png.chunk-count', 'PNG exceeds the supported chunk count.')
        if kind == b'IHDR':
            _require(chunk_count == 1 and length == 13, 'png.structure', 'IHDR must occur once, first, with length 13.')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', payload)
            _require(0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION and width * height <= MAX_PIXELS,
                     'png.dimensions', 'PNG dimensions exceed the supported resource bounds.')
            _require((depth, color, compression, filtering, interlace) == (8, 6, 0, 0, 0),
                     'png.context', 'Only native RGBA8, method-0, noninterlaced PNG is supported.')
            header = {'width': width, 'height': height, 'bitDepth': depth, 'colorType': color,
                      'compressionMethod': compression, 'filterMethod': filtering, 'interlaceMethod': interlace}
        elif kind == b'IDAT':
            _require(header is not None, 'png.structure', 'IDAT must follow IHDR.')
            compressed_parts.append(payload)
        elif kind == b'IEND':
            _require(header is not None and compressed_parts and length == 0,
                     'png.structure', 'IEND requires IHDR, at least one IDAT, and zero data bytes.')
            offset = end
            break
        else:
            raise NativePngError('png.unsupported-chunk', 'Only IHDR, consecutive IDAT, and IEND chunks are supported.')
        offset = end

    # This validates the zlib/scanline envelope without reconstructing RGBA pixels.
    row_bytes = header['width'] * 4 + 1
    expected_bytes = row_bytes * header['height']
    inflater = zlib.decompressobj()
    try:
        scanlines = inflater.decompress(b''.join(compressed_parts), expected_bytes + 1)
    except zlib.error:
        raise NativePngError('png.inflate', 'PNG IDAT zlib stream is invalid.') from None
    _require(len(scanlines) == expected_bytes and inflater.eof and not inflater.unconsumed_tail and not inflater.unused_data,
             'png.inflate', 'PNG IDAT stream is incomplete, oversized, or contains extra compressed bytes.')
    _require(all(scanlines[index] <= 4 for index in range(0, expected_bytes, row_bytes)),
             'png.filter', 'PNG contains an unsupported scanline filter value.')
    return offset, {'image': header, 'chunkCount': chunk_count, 'idatChunkCount': len(compressed_parts),
                    'filteredScanlineBytes': expected_bytes, 'filteredScanlinesSha256': _sha256(scanlines)}


def extract_native_rgba8_png(source_path: str | os.PathLike, output_path: str | os.PathLike, *,
                            context: str, expected_source_sha256: str | None = None) -> dict:
    """Read native export bytes and exclusively create an exact PNG prefix copy.

    The output must not exist, including symlinks or aliases of the input. Input
    is opened read-only and rechecked before/after output creation. Validation
    failures create no output. The returned source/output bindings cover whole
    files; removed trailer bytes are represented only by length and SHA-256.
    No contract, lineage, rendering or native-origin acceptance is performed.
    """
    _require(context == NATIVE_CONTEXT, 'context.unsupported', 'An explicit supported native export context is required.')
    if expected_source_sha256 is not None:
        _require(isinstance(expected_source_sha256, str) and len(expected_source_sha256) == 64
                 and all(character in '0123456789abcdefABCDEF' for character in expected_source_sha256),
                 'source.expected-hash', 'Expected source SHA-256 must contain 64 hexadecimal characters.')
        expected_source_sha256 = expected_source_sha256.lower()
    destination = None
    created_identity = None
    try:
        source = Path(source_path).expanduser().resolve(strict=True)
        requested_output = Path(output_path).expanduser()
        _require(not os.path.lexists(requested_output), 'output.exists', 'Output must be a new, nonexistent path.')
        destination = requested_output.resolve(strict=False)
        _require(destination != source and not os.path.lexists(destination), 'output.exists', 'Output cannot overwrite or alias the input or another file.')
        _require(destination.parent.is_dir(), 'output.parent', 'Output parent directory must already exist.')
        data, source_identity = _read_source(source)
        source_digest = _sha256(data)
        _require(expected_source_sha256 is None or source_digest == expected_source_sha256,
                 'source.expected-hash', 'Input does not match the expected source SHA-256.')
        stream_end, parsed = _parse_native_stream(data)
        prefix = data[:stream_end]
        _unchanged_source(source, source_identity, source_digest)
        with destination.open('xb') as handle:
            created = os.fstat(handle.fileno())
            created_identity = created.st_dev, created.st_ino
            handle.write(prefix)
            handle.flush()
            os.fsync(handle.fileno())
        _unchanged_source(source, source_identity, source_digest)
        output_data, output_identity = _read_source(destination)
        _require(output_identity[:2] == created_identity and output_data == prefix,
                 'output.changed', 'New output identity or bytes changed during creation.')
        return {'kind': 'nextgame-ui-native-png-boundary', 'version': '1', 'context': context,
                'operation': 'copy-original-png-bytes-through-IEND',
                'source': {'path': str(source), 'sizeBytes': len(data), 'sha256': source_digest},
                'output': {'path': str(destination), 'sizeBytes': stream_end, 'sha256': _sha256(prefix)},
                'removedTrailer': {'sizeBytes': len(data) - stream_end, 'sha256': _sha256(data[stream_end:])},
                'validation': parsed}
    except (NativePngError, OSError) as error:
        # Remove only the new file created by this call, never a replaced path.
        if created_identity is not None and destination is not None:
            try:
                actual = destination.stat(follow_symlinks=False)
                if (actual.st_dev, actual.st_ino) == created_identity:
                    destination.unlink()
            except OSError:
                pass
        if isinstance(error, NativePngError):
            raise
        raise NativePngError('io.error', 'Input/output filesystem operation failed.') from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--context', required=True, choices=[NATIVE_CONTEXT])
    parser.add_argument('--expected-source-sha256')
    args = parser.parse_args(argv)
    try:
        result = extract_native_rgba8_png(args.source, args.output, context=args.context,
                                          expected_source_sha256=args.expected_source_sha256)
    except NativePngError as error:
        print(json.dumps({'ok': False, 'error': {'code': error.code, 'message': str(error)}}), file=sys.stderr)
        return 2
    print(json.dumps({'ok': True, **result}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
