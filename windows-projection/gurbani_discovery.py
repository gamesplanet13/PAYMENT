"""Share PC discovery on the Gurbani Control port with the Gurbani launcher."""

import ctypes
from ctypes import wintypes
import json
import os
import re
import socket


PORT = 46823
QUERY = re.compile(rb'GURBANI_FIND_V1:([a-f0-9-]{36})')
DISPLAY_CODE = re.compile(r'[0-9]{5}')
DISPLAY_NAMES = {'projection': 'Projection', 'book': 'Granth View', 'camera': 'Camera', 'qr': 'QR Payment'}


def process_start_ticks(pid):
    kernel = ctypes.WinDLL('kernel32')
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        start, exit_time, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
        if kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in (start, exit_time, kernel_time, user_time))) and not (
            exit_time.dwHighDateTime or exit_time.dwLowDateTime
        ):
            return str((start.dwHighDateTime << 32) + start.dwLowDateTime + 504911232000000000)
    finally:
        kernel.CloseHandle(handle)
    return None


def discovery_replies(packet, directory, hostname):
    match = QUERY.fullmatch(packet)
    if not match:
        return
    for role, label in DISPLAY_NAMES.items():
        try:
            record = json.loads((directory / f'{role}.active').read_text(encoding='ascii'))
            code, pid, started = record['code'], record['windowPid'], record['windowStart']
            if not DISPLAY_CODE.fullmatch(code) or not isinstance(pid, int) or not (0 < pid < 2**32):
                continue
            if not started or process_start_ticks(pid) != started:
                continue
        except (OSError, ValueError, KeyError, TypeError):
            continue
        name = f'{label} - {hostname}' if role in ('camera', 'qr') else f'{hostname} - {label}'
        yield json.dumps({'type': 'GURBANI_DISPLAY_V1', 'nonce': match[1].decode('ascii'),
                          'role': 'book' if role == 'book' else 'projection', 'code': code, 'name': name}).encode()


def advertise_gurbani(directory, lan):
    started = process_start_ticks(os.getpid())
    if not started:
        return
    directory.mkdir(parents=True, exist_ok=True)
    record = directory / 'qr.active'
    staged = record.with_suffix('.tmp')
    published_code = None
    receiver = None
    try:
        while not lan.closed.is_set():
            if lan.code and lan.code != published_code:
                staged.write_text(json.dumps({'code': lan.code, 'windowPid': os.getpid(), 'windowStart': started}),
                                  encoding='ascii')
                staged.replace(record)
                published_code = lan.code
            if receiver is None:
                try:
                    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    receiver.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                    receiver.bind(('', PORT))
                    receiver.settimeout(0.5)
                except OSError:
                    if receiver is not None:
                        receiver.close()
                        receiver = None
                    # A running Gurbani window is already replying for every registered app.
                    lan.closed.wait(0.75)
                continue
            try:
                packet, sender = receiver.recvfrom(512)
                for reply in discovery_replies(packet, directory, lan.name):
                    receiver.sendto(reply, sender)
            except OSError:
                pass
    finally:
        if receiver is not None:
            receiver.close()
        record.unlink(missing_ok=True)
        staged.unlink(missing_ok=True)
