"""Pure projection visibility rules, separated so they can be tested."""
class ProjectionState:
    def __init__(self, idle_seconds=60):
        self.idle_seconds = idle_seconds
        self.visible = True
        self.mode = 'pairing'
        self.fingerprint = None
        self.dismissed = None
        self.input_marker = None
        self.connected = False
        self.ready = False
        self.settings_open = False

    def can_hide_on_input(self):
        return self.visible and self.ready and self.connected and not self.settings_open

    def open_settings(self):
        self.settings_open = True
        self.visible = True
        self.mode = 'pairing'

    def close_settings(self):
        self.settings_open = False

    def dismiss(self):
        if self.mode == 'qr':
            self.dismissed = self.fingerprint
        self.visible = False
        self.mode = 'hidden'

    def decide(self, *, paired, connected, qr, fingerprint, idle, input_marker):
        moved = self.input_marker is not None and input_marker != self.input_marker
        self.input_marker = input_marker
        was_connected = self.connected
        self.ready = True
        self.connected = connected
        if connected and not was_connected and self.settings_open:
            self.close_settings()
        if self.settings_open:
            return 'stay'
        if not connected:
            return 'pairing' if self.visible else 'stay'
        if not qr:
            self.fingerprint = None
            self.dismissed = None
        elif fingerprint and fingerprint != self.fingerprint:
            self.fingerprint = fingerprint
            self.dismissed = None
            self.visible = True
            self.mode = 'qr'
            return 'new_qr'
        if moved and self.can_hide_on_input() and self.mode in ('qr', 'clock'):
            self.dismiss()
            return 'hide'
        if qr and self.dismissed != fingerprint:
            if not self.visible:
                self.visible = True
                self.mode = 'qr'
                return 'qr'
            return 'stay'
        if idle >= self.idle_seconds:
            if self.mode != 'clock' or not self.visible:
                self.mode = 'clock'
                self.visible = True
                return 'clock'
            return 'stay'
        if self.visible and self.mode != 'pairing':
            self.mode = 'hidden'
            self.visible = False
            return 'hide'
        if self.mode == 'pairing':
            return 'stay'
        return 'stay'
