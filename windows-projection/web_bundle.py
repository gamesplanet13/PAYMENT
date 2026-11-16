"""Package the Projection page and serve it at its existing WebView2 origin."""

from pathlib import Path
import shutil
import sys


HOST = 'gamesplanet13.github.io'
PROJECTION_URL = f'https://{HOST}/PAYMENT/preview.html?desktop=windows'


def bundle_root():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'projection-web'
    return None


def attach_bundle(window, root):
    from Microsoft.Web.WebView2.Core import CoreWebView2HostResourceAccessKind

    def navigate(view):
        view.SetVirtualHostNameToFolderMapping(
            HOST, str(root), CoreWebView2HostResourceAccessKind.DenyCors,
        )
        view.Navigate(PROJECTION_URL)

    def initialized(sender, args):
        if args.IsSuccess:
            navigate(sender.CoreWebView2)

    control = window.native.webview
    if control.CoreWebView2 is None:
        control.CoreWebView2InitializationCompleted += initialized
    else:
        navigate(control.CoreWebView2)


def stage_bundle(source, target):
    site = target / 'PAYMENT'
    site.mkdir(parents=True, exist_ok=True)
    preview = (source / 'preview.html').read_text(encoding='utf-8')
    peer_script = 'https://unpkg.com/peerjs@1.5.5/dist/peerjs.min.js'
    if preview.count(peer_script) != 1:
        raise ValueError('Expected one PeerJS script in preview.html')
    preview = preview.replace(peer_script, 'peerjs-1.5.5.min.js')
    preview = preview.replace('<head>', '<head><meta name="gp-windows-bundle" content="1">', 1)
    (site / 'preview.html').write_text(preview, encoding='utf-8')
    shutil.copy2(source / 'qr-lan.js', site)
    shutil.copy2(source / 'ring-bell' / 'peerjs-1.5.5.min.js', site)
    shutil.copy2(source / 'ring-bell' / 'PEERJS-LICENSE.txt', site)
    shutil.copytree(source / 'assets', site / 'assets', dirs_exist_ok=True)


if __name__ == '__main__':
    stage_bundle(Path(__file__).resolve().parents[1], Path(sys.argv[1]))
