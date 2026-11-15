"""Fetch and stage Windows releases for the current executable architecture."""
import hashlib
import json
import os
import struct
import subprocess
from urllib.request import urlopen

VERSION = 2026111503
RELEASE = 'https://github.com/gamesplanet13/PAYMENT/releases/download/projection-windows-current/'
ARCH = 'x64' if struct.calcsize('P') == 8 else 'x86'


def stage_update(directory):
    with urlopen(RELEASE + f'qr-windows-{ARCH}.json', timeout=12) as response:
        manifest = json.loads(response.read(8192))
    version = int(manifest['version'])
    if version <= VERSION:
        return None
    stage = directory / 'GamesPlanetProjection.update.exe'
    try:
        digest = hashlib.sha256()
        size = 0
        with urlopen(RELEASE + f'GamesPlanetProjection-{ARCH}.exe', timeout=20) as response, stage.open('wb') as output:
            for chunk in iter(lambda: response.read(65536), b''):
                size += len(chunk)
                if size > 100 * 1024 * 1024:
                    raise ValueError('Update exceeds the download limit')
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != manifest['sha256']:
            raise ValueError('Update hash mismatch')
        return stage
    except Exception:
        stage.unlink(missing_ok=True)
        raise


def install_after_exit(stage):
    command = [
        'powershell.exe', '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
        '-Command',
        '$wait=$env:GP_UPDATE_PID; Wait-Process -Id $wait -Timeout 45 -ErrorAction SilentlyContinue; '
        'if (Get-Process -Id $wait -ErrorAction SilentlyContinue) {exit 1}; '
        '$from=$env:GP_UPDATE_FILE; $to=$env:GP_CURRENT_EXE; '
        '[IO.File]::Replace($from,$to,$to+".previous",$true); Start-Process -FilePath $to',
    ]
    subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW, env={
        **os.environ, 'GP_UPDATE_PID': str(os.getpid()), 'GP_UPDATE_FILE': str(stage),
        'GP_CURRENT_EXE': str(stage.with_name('GamesPlanetProjection.exe')),
    })
