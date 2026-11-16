"""Games Planet Projection: foreground payment, idle clock and tray control."""
import ctypes
from ctypes import wintypes
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
import winreg
import webview
import pystray
from PIL import Image, ImageDraw
from state import ProjectionState
from updater import install_after_exit, stage_update
from lan import ProjectionLAN
from weather import read_weather

URL = 'https://gamesplanet13.github.io/PAYMENT/preview.html?desktop=windows'
APP_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'GamesPlanetProjection'
PROFILE = APP_DIR / 'webview-profile'
IDLE_SECONDS = 60
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
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

def playback_blocks_clock():
    state = wintypes.DWORD()
    query = ctypes.windll.powrprof.CallNtPowerInformation
    # SystemExecutionState reports display power requests, including media playback.
    if query(16, None, 0, ctypes.byref(state), ctypes.sizeof(state)) == 0 and state.value & 2:
        return True
    window = user32.GetForegroundWindow()
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
    if pid.value in (0, os.getpid()):
        return False
    rect = wintypes.RECT()
    return bool(user32.GetWindowRect(window, ctypes.byref(rect)) and rect.left <= 0
                and rect.top <= 0 and rect.right >= user32.GetSystemMetrics(0)
                and rect.bottom >= user32.GetSystemMetrics(1))


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
 const controls=JSON.parse(localStorage.getItem('gp_preview_controls_v1')||'null');
 const paired=Array.isArray(controls)?controls.length>0:!!localStorage.getItem('gp_preview_owner_v3');
 const qr=!result.hidden;
 const connected=typeof approved!=='undefined' && !!approved;
 return {ready:true,paired:paired,connected:connected,qr:qr,fingerprint:qr?[(document.getElementById('displayPrice')||{}).textContent,(document.getElementById('payeeName')||{}).textContent].join('|'):''};
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
        self.ignore_input_until = 0
        self.lock = threading.RLock()
        self.open_event = None
        self.first = True
        self.lan = ProjectionLAN()
        self.last_physical_input = time.monotonic()

    def show_window(self, script=CLOCK_OFF, *, on_top=False):
        try:
            with self.lock:
                if not self.running or not self.state.visible:
                    return
                self.window.on_top = on_top
                self.window.maximize()
                self.window.show()
            self.window.evaluate_js(script)
        except Exception:
            logging.exception('Could not show projection')

    def open_window(self, *_):
        with self.lock:
            self.state.visible = True
            self.state.mode = 'pairing'
        self.show_window()

    def open_settings(self, *_):
        with self.lock:
            self.state.open_settings()
        self.show_window(SHOW_SETTINGS)

    def close_settings(self, *_):
        with self.lock:
            self.state.close_settings()
            self.state.dismiss()
        try:
            self.window.evaluate_js(CLOSE_SETTINGS)
            self.window.hide()
        except Exception:
            logging.exception('Could not close connection settings')

    def request_exit(self):
        self.quit()

    def update_loop(self):
        while self.running:
            try:
                stage = stage_update(APP_DIR)
                if stage and self.running:
                    self.open_window()
                    if self.window.create_confirmation_dialog('Update ready', 'Install the Games Planet Projection update now?'):
                        install_after_exit(stage)
                        self.quit()
                        return
                    stage.unlink(missing_ok=True)
            except Exception:
                logging.debug('Update unavailable', exc_info=True)
            time.sleep(300)

    def quit(self, *_):
        with self.lock:
            if not self.running:
                return
            self.running = False
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
                if changed:
                    self.last_physical_input = time.monotonic()
                    if self.running and self.state.can_hide_on_input() and (
                        self.state.mode == 'clock' or time.monotonic() >= self.ignore_input_until
                    ):
                        self.state.dismiss()
                        try:
                            self.window.hide()
                        except Exception:
                            logging.exception('Could not hide projection')
            if self.open_event and kernel32.WaitForSingleObject(self.open_event, 0) == 0:
                self.open_window()

    def loop(self):
        # Keep the PC awake to receive payments, but allow the display to turn off.
        kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
        self.lan.start()
        threading.Thread(target=self.tray_loop,daemon=True).start()
        threading.Thread(target=self.input_loop,daemon=True).start()
        if getattr(sys, 'frozen', False):
            threading.Thread(target=self.update_loop,daemon=True).start()
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
                _,idle=get_input()
                idle=min(idle,time.monotonic()-self.last_physical_input)
                busy_media=idle>=IDLE_SECONDS and playback_blocks_clock()
                if self.first:
                    self.first=False
                    if not data.get('connected'):
                        self.window.evaluate_js(SHOW_SETTINGS)
                with self.lock:
                    was_visible=self.state.visible
                    # Input is monitored independently, including when JavaScript is busy.
                    idle=min(idle,time.monotonic()-self.last_physical_input)
                    action=self.state.decide(paired=bool(data.get('paired')),connected=bool(data.get('connected')),qr=bool(data.get('qr')),
                        fingerprint=data.get('fingerprint',''),idle=idle,input_marker=self.state.input_marker,media_active=busy_media)
                    if action=='new_qr':
                        self.ignore_input_until=time.monotonic()+1
                    elif action=='hide':
                        self.window.hide()
                if action=='new_qr':
                    wake_monitor()
                    self.show_window(on_top=True)
                elif action=='clock':
                    self.show_window(CLOCK_ON, on_top=True)
                elif action=='pairing' and not was_visible:
                    self.show_window()

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
    background_args = '--disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows'
    os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = (
        os.environ.get('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS','') + ' ' + background_args
    ).strip()
    app.window=webview.create_window('Games Planet Projection', URL, maximized=True, background_color='#000000')
    app.window.expose(app.request_exit)
    def qr_advertise(code): app.lan.advertise(code)
    def qr_send(identity, payload): app.lan.send(identity, payload)
    def qr_close(identity): app.lan.close_link(identity)
    def qr_poll(): return app.lan.poll()
    def qr_weather():
        try: return read_weather()
        except (OSError, ValueError, KeyError):
            logging.debug('Weather unavailable', exc_info=True)
            return None
    app.window.expose(qr_advertise, qr_send, qr_close, qr_poll, qr_weather)
    def on_loaded():
        app.window.evaluate_js("window.addEventListener('keydown', e=>{if(e.key==='Escape'||e.key==='BrowserBack'||(e.altKey&&e.key==='ArrowLeft')){e.preventDefault();e.stopImmediatePropagation();window.pywebview?.api?.request_exit()}},true)")
    app.window.events.loaded += on_loaded
    try:
        webview.start(app.loop, private_mode=False, storage_path=str(PROFILE))
    finally:
        app.running=False
        app.lan.close()
        if app.tray:app.tray.stop()
        if app.open_event: kernel32.CloseHandle(app.open_event)
        kernel32.CloseHandle(mutex)
if __name__=='__main__':
    if '--self-test' in sys.argv:
        marker, idle = get_input()
        assert isinstance(marker, int) and idle >= 0
    else:
        main()
