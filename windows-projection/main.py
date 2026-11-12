"""Games Planet Projection: foreground payment, idle clock and tray control."""
import ctypes
from ctypes import wintypes
import logging
import os
import shutil
import sys
import threading
import time
from pathlib import Path
import winreg
import webview
import pystray
from PIL import Image, ImageDraw
from state import ProjectionState

URL = 'https://gamesplanet13.github.io/PAYMENT/preview.html'
APP_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'GamesPlanetProjection'
PROFILE = APP_DIR / 'webview-profile'
IDLE_SECONDS = 60
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.UINT), ('dwTime', wintypes.DWORD)]

def get_input():
    info = LASTINPUTINFO(); info.cbSize = ctypes.sizeof(info)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return 0, 0
    ticks = kernel32.GetTickCount() & 0xffffffff
    return info.dwTime, ((ticks - info.dwTime) & 0xffffffff) / 1000.0

def install_autostart():
    if not getattr(sys, 'frozen', False):
        return
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        destination = APP_DIR / 'GamesPlanetProjection.exe'
        if Path(sys.executable).resolve() != destination.resolve():
            shutil.copy2(sys.executable, destination)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
            winreg.SetValueEx(key, 'GamesPlanetProjection', 0, winreg.REG_SZ, '"' + str(destination) + '"')
    except OSError:
        logging.exception('Could not set up automatic startup')

def wake_monitor():
    # No secure-desktop or lock-screen bypass; this only requests display power.
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)
    user32.PostMessageW(0xFFFF, 0x0112, 0xF170, -1)  # SC_MONITORPOWER on
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)

PROBE = r'''(function(){
try {
 const result=document.getElementById('displayResult');
 if(!result) return {ready:false};
 const owner=!!localStorage.getItem('gp_preview_owner_v3');
 const qr=!result.hidden;
 return {ready:true,paired:owner,qr:qr,fingerprint:qr?[(document.getElementById('displayPrice')||{}).textContent,(document.getElementById('payeeName')||{}).textContent].join('|'):''};
}catch(e){return {ready:false};}})()'''
CLOCK_ON = r'''(function(){
if(!document.getElementById('gpWinStyle')){const s=document.createElement('style');s.id='gpWinStyle';s.textContent=`
body.gp-win-clock #projectionClock {display:flex!important;position:fixed!important;inset:0!important;width:100%!important;max-width:none!important;height:100vh!important;min-height:100vh!important;z-index:99999!important;background:black!important;align-items:center!important;justify-content:center!important}
body.gp-win-clock #shopFlyer {display:none!important}
body.gp-win-clock #clockDigits {height:min(23vw,48vh)!important}
body.gp-win-clock .led-colon {font-size:min(23vw,48vh)!important}
body.gp-win-clock .clock-days {font-size:clamp(22px,4vw,60px)!important}
body.gp-win-clock .digital-date {font-size:clamp(22px,3.8vw,55px)!important}
`;document.head.appendChild(s)}
if(typeof setFlyer==='function')setFlyer(false);document.body.classList.add('gp-win-clock');return true;})()'''
CLOCK_OFF = "document.body.classList.remove('gp-win-clock'); true"

class App:
    def __init__(self):
        self.window = None
        self.state = ProjectionState(IDLE_SECONDS)
        self.running = True
        self.tray = None
        self.manual_until = 0
        self.first = True

    def show_window(self, clock=False):
        try:
            self.window.evaluate_js(CLOCK_ON if clock else CLOCK_OFF)
            self.window.show()
        except Exception:
            logging.exception('Could not show projection')

    def open_window(self, *_):
        self.manual_until = time.monotonic() + 30
        self.state.visible = True
        self.state.mode = 'pairing'
        self.show_window(False)

    def quit(self, *_):
        self.running = False
        if self.tray:
            self.tray.stop()
        if self.window:
            self.window.destroy()

    def tray_loop(self):
        img = Image.new('RGB',(64,64),'#090909')
        d=ImageDraw.Draw(img);d.rounded_rectangle((3,3,61,61),radius=14,outline='#e7b44d',width=4)
        d.text((13,22),'GP',fill='#f0c467')
        self.tray=pystray.Icon('GamesPlanetProjection',img,'Games Planet Projection',
            menu=pystray.Menu(pystray.MenuItem('Open Projection',self.open_window,default=True),pystray.MenuItem('Exit',self.quit)))
        self.tray.run()

    def loop(self):
        # Keep the PC awake to receive payments, but allow the display to turn off.
        kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
        threading.Thread(target=self.tray_loop,daemon=True).start()
        failures=0
        while self.running:
            try:
                time.sleep(1)
                data = self.window.evaluate_js(PROBE)
                if not isinstance(data,dict) or not data.get('ready'):
                    failures+=1
                    if failures==30:
                        self.window.load_url(URL);failures=0
                    continue
                failures=0
                marker,idle=get_input()
                if self.first:
                    self.first=False
                    if not data.get('paired'):
                        self.window.evaluate_js("document.getElementById('pairDisplay').scrollIntoView({block:'center'}); true")
                was_visible=self.state.visible
                action=self.state.decide(paired=bool(data.get('paired')),qr=bool(data.get('qr')),
                    fingerprint=data.get('fingerprint',''),idle=idle,input_marker=marker)
                if action=='new_qr':
                    self.manual_until=0;wake_monitor();self.show_window(False)
                elif action=='clock':
                    if time.monotonic()>=self.manual_until:self.show_window(True)
                elif action=='hide':
                    if time.monotonic()>=self.manual_until:self.window.hide()
                    else:self.state.visible=True;self.state.mode='pairing'
                elif action=='pairing' and not was_visible:
                    self.show_window(False)
                elif action=='stay' and self.state.visible and self.state.mode=='clock':
                    self.window.evaluate_js(CLOCK_ON)
            except Exception:
                logging.exception('Projection monitor error')
        kernel32.SetThreadExecutionState(0x80000000)


def main():
    APP_DIR.mkdir(parents=True,exist_ok=True);PROFILE.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=str(APP_DIR / 'projection.log'),level=logging.WARNING)
    mutex=kernel32.CreateMutexW(None, False, 'Local\\GamesPlanetProjectionSingleInstance')
    if not mutex or kernel32.GetLastError()==183:
        return
    install_autostart()
    app=App()
    app.window=webview.create_window('Games Planet Projection', URL, fullscreen=True, on_top=True, background_color='#000000')
    def on_closed():
        app.running=False
        if app.tray:app.tray.stop()
    app.window.events.closed += on_closed
    try:
        webview.start(app.loop, private_mode=False, storage_path=str(PROFILE))
    finally:
        app.running=False
        if app.tray:app.tray.stop()
        kernel32.CloseHandle(mutex)
if __name__=='__main__':
    if '--self-test' in sys.argv:
        marker, idle = get_input()
        assert isinstance(marker, int) and idle >= 0
    else:
        main()
