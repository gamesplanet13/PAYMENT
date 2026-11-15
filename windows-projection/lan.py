"""Windows endpoint for Android QR discovery and local WebRTC signalling."""
import json
import logging
import queue
import socket
import struct
import threading
import uuid

DISCOVERY = 'GP_QR_CONNECTION_DISCOVER_V1'
LEGACY_REQUEST = b'GP_PROJECTION_DISCOVER_V1'
LIMIT = 128 * 1024


def read_frame(stream):
    header = stream.read(4)
    if len(header) != 4:
        raise EOFError
    size = struct.unpack('!I', header)[0]
    if not 0 < size <= LIMIT:
        raise ValueError('Invalid frame size')
    payload = stream.read(size)
    if len(payload) != size:
        raise EOFError
    return payload.decode('utf-8')


def send_frame(connection, payload):
    encoded = payload.encode('utf-8')
    if not 0 < len(encoded) <= LIMIT:
        raise ValueError('Invalid frame size')
    connection.sendall(struct.pack('!I', len(encoded)) + encoded)


class ProjectionLAN:
    def __init__(self):
        self.code = ''
        self.name = socket.gethostname() or 'Windows PC'
        self.events = queue.Queue(maxsize=128)
        self.links = {}
        self.lock = threading.Lock()
        self.sockets = []
        self.closed = threading.Event()
        self.port = 0

    def start(self):
        try:
            listener = socket.socket()
            listener.bind(('', 0))
            listener.listen(12)
            listener.settimeout(1)
            self.port = listener.getsockname()[1]
            self.sockets.append(listener)
            threading.Thread(target=self.listen, args=(listener,), daemon=True).start()
        except OSError:
            logging.exception('Could not start QR local connection listener')
        for default_port in (46822, 46824):
            try:
                receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                receiver.bind(('', default_port))
                receiver.settimeout(1)
                self.sockets.append(receiver)
                threading.Thread(target=self.discover, args=(receiver, default_port), daemon=True).start()
            except OSError:
                logging.exception('Could not listen for QR Wi-Fi discovery on %s', default_port)

    def advertise(self, code):
        if isinstance(code, str) and len(code) == 5 and code.isascii() and code.isdigit():
            self.code = code

    def discover(self, receiver, port):
        while not self.closed.is_set():
            try:
                packet, sender = receiver.recvfrom(1024)
                if not self.code:
                    continue
                if port == 46822 and packet == LEGACY_REQUEST:
                    reply = {'type':'GP_PROJECTION_V1', 'code':self.code, 'name':self.name}
                elif port == 46824 and self.port:
                    request = json.loads(packet)
                    if not isinstance(request, dict) or request.get('type') != DISCOVERY or request.get('role') != 'projection':
                        continue
                    if request.get('code') not in ('', self.code):
                        continue
                    nonce = request.get('nonce', '')
                    if not isinstance(nonce, str) or len(nonce) != 36:
                        continue
                    reply = {'type':DISCOVERY,'code':self.code,'role':'projection','port':self.port,
                             'name':self.name,'nonce':nonce}
                else:
                    continue
                receiver.sendto(json.dumps(reply).encode(), sender)
            except (ValueError, OSError):
                continue

    def listen(self, listener):
        slots = threading.BoundedSemaphore(12)
        while not self.closed.is_set():
            try:
                connection, _ = listener.accept()
            except OSError:
                continue
            if not slots.acquire(blocking=False):
                connection.close()
                continue
            threading.Thread(target=self.handle, args=(connection, slots), daemon=True).start()

    def handle(self, connection, slots):
        identity = str(uuid.uuid4())
        ready = False
        try:
            with connection, connection.makefile('rb') as stream:
                connection.settimeout(5)
                hello = json.loads(read_frame(stream))
                if not isinstance(hello, dict):
                    return
                code = hello.get('code', '')
                if not self.code or hello.get('target') != self.code or hello.get('role') != 'control':
                    return
                if not isinstance(code, str) or len(code) != 5 or not code.isascii() or not code.isdigit():
                    return
                send_frame(connection, 'OK')
                connection.settimeout(None)
                with self.lock:
                    self.links[identity] = (connection, threading.Lock())
                ready = True
                self.events.put_nowait(['incoming', identity, code])
                while not self.closed.is_set():
                    self.events.put_nowait(['frame', identity, read_frame(stream)])
        except (OSError, EOFError, ValueError, queue.Full):
            pass
        finally:
            slots.release()
            with self.lock:
                self.links.pop(identity, None)
            if ready:
                try: self.events.put_nowait(['closed', identity, ''])
                except queue.Full: pass

    def send(self, identity, payload):
        with self.lock:
            link = self.links.get(identity)
        if link and isinstance(payload, str):
            try:
                with link[1]:
                    send_frame(link[0], payload)
            except (OSError, ValueError):
                self.close_link(identity)

    def close_link(self, identity):
        with self.lock:
            link = self.links.pop(identity, None)
        if link:
            try: link[0].shutdown(socket.SHUT_RDWR)
            except OSError: pass
            link[0].close()

    def poll(self):
        batch = []
        for _ in range(32):
            try: batch.append(self.events.get_nowait())
            except queue.Empty: break
        return batch

    def close(self):
        self.closed.set()
        for listener in self.sockets:
            listener.close()
        with self.lock:
            identities = list(self.links)
        for identity in identities:
            self.close_link(identity)
