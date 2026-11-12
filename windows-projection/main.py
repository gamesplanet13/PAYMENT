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
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.OpenEventW.restype = wintypes.HANDLE
kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.SetEvent.argtypes = [wintypes.HANDLE]
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
OPEN_EVENT = 'Local\\GamesPlanetProjectionOpen'
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
 const connected=typeof approved!=='undefined' && !!approved;
 return {ready:true,paired:owner,connected:connected,qr:qr,fingerprint:qr?[(document.getElementById('displayPrice')||{}).textContent,(document.getElementById('payeeName')||{}).textContent].join('|'):''};
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
SHOW_SETTINGS = r"""(function(){
 document.body.classList.remove('gp-win-clock');
 const card=document.getElementById('pairDisplay');
 if(!card)return false;
 card.hidden=false;
 const unpair=document.getElementById('forgetControl');
 if(unpair)unpair.hidden=!localStorage.getItem('gp_preview_owner_v3');
 card.scrollIntoView({block:'center'});
 return true;
})()"""
CLOSE_SETTINGS = r"""(function(){
 const card=document.getElementById('pairDisplay');
 if(card && typeof approved!=='undefined' && approved)card.hidden=true;
 window.scrollTo(0,0); return true;
})()"""

class App:
    def __init__(self):
        self.window = None
        self.state = ProjectionState(IDLE_SECONDS)
        self.running = True
        self.tray = None
        self.ignore_input_until = time.monotonic() + 1
        self.lock = threading.RLock()
        self.open_event = None
        self.first = True

    def show_window(self, clock=False):
        try:
            self.window.evaluate_js(CLOCK_ON if clock else CLOCK_OFF)
            self.window.show()
        except Exception:
            logging.exception('Could not show projection')

    def open_window(self, *_):
        with self.lock:
            self.ignore_input_until = time.monotonic() + 1
            self.state.visible = True
            self.state.mode = 'pairing'
        self.show_window(False)

    def open_settings(self, *_):
        with self.lock:
            self.state.open_settings()
        try:
            self.window.show()
            self.window.evaluate_js(SHOW_SETTINGS)
        except Exception:
            logging.exception('Could not open connection settings')

    def close_settings(self, *_):
        with self.lock:
            self.state.close_settings()
            self.state.dismiss()
        try:
            self.window.evaluate_js(CLOSE_SETTINGS)
            self.window.hide()
        except Exception:
            logging.exception('Could not close connection settings')

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
            menu=pystray.Menu(pystray.MenuItem('Open Projection',self.open_window,default=True),pystray.MenuItem('Connection settings / code',self.open_settings),pystray.MenuItem('Hide Projection',self.close_settings),pystray.MenuItem('Exit',self.quit)))
        self.tray.run()

    def input_loop(self):
        previous = get_input()[0]
        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        position = (point.x, point.y)
        while self.running:
            time.sleep(.12)
            marker, _ = get_input()
            user32.GetCursorPos(ctypes.byref(point))
            current = (point.x, point.y)
            changed = marker != previous or current != position
            previous, position = marker, current
            with self.lock:
                if changed and self.state.can_hide_on_input() and time.monotonic() >= self.ignore_input_until:
                    self.state.dismiss()
                    try: self.window.hide()
                    except Exception: logging.exception('Could not hide projection')
            if self.open_event and kernel32.WaitForSingleObject(self.open_event, 0) == 0:
                self.open_window()

    def loop(self):
        # Keep the PC awake to receive payments, but allow the display to turn off.
        kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
        threading.Thread(target=self.tray_loop,daemon=True).start()
        threading.Thread(target=self.input_loop,daemon=True).start()
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
                    if not data.get('connected'):
                        self.window.evaluate_js(SHOW_SETTINGS)
                was_visible=self.state.visible
                with self.lock:
                    # Input is monitored independently, including when JavaScript is busy.
                    action=self.state.decide(paired=bool(data.get('paired')),connected=bool(data.get('connected')),qr=bool(data.get('qr')),
                        fingerprint=data.get('fingerprint',''),idle=idle,input_marker=self.state.input_marker)
                if action=='new_qr':
                    self.ignore_input_until=time.monotonic()+1;wake_monitor();self.show_window(False)
                elif action=='clock':
                    self.ignore_input_until=time.monotonic()+1;self.show_window(True)
                elif action=='hide':
                    self.window.hide()
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
    if not mutex: return
    if kernel32.GetLastError()==183:
        event=kernel32.OpenEventW(2, False, OPEN_EVENT)
        if event:
            kernel32.SetEvent(event);kernel32.CloseHandle(event)
        kernel32.CloseHandle(mutex)
        return
    install_autostart()
    app=App()
    app.open_event=kernel32.CreateEventW(None, False, False, OPEN_EVENT)
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
        if app.open_event: kernel32.CloseHandle(app.open_event)
        kernel32.CloseHandle(mutex)
if __name__=='__main__':
    if '--self-test' in sys.argv:
        marker, idle = get_input()
        assert isinstance(marker, int) and idle >= 0
    else:
        main()
