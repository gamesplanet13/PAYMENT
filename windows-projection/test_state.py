import unittest
from state import ProjectionState

class Tests(unittest.TestCase):
    def step(self, state, **kwargs):
        values=dict(paired=True,connected=True,qr=False,fingerprint='',idle=0,input_marker=1)
        values.update(kwargs)
        return state.decide(**values)

    def test_unpaired_or_disconnected_remains_visible_during_mouse_and_keys(self):
        s=ProjectionState()
        self.assertEqual(self.step(s,paired=False,connected=False),'pairing')
        self.assertFalse(s.can_hide_on_input())
        self.assertEqual(self.step(s,paired=False,connected=False,input_marker=2),'pairing')
        self.assertTrue(s.visible)
        self.assertEqual(self.step(s,paired=True,connected=False,input_marker=3),'pairing')
        self.assertFalse(s.can_hide_on_input())
        self.assertTrue(s.visible)

    def test_connected_qr_mouse_idle_close_and_reopen(self):
        s=ProjectionState(60)
        self.step(s,paired=False,connected=False)
        self.assertEqual(self.step(s),'stay')
        self.assertFalse(s.can_hide_on_input())
        self.assertEqual(self.step(s,qr=True,fingerprint='102'),'new_qr')
        self.assertTrue(s.can_hide_on_input())
        self.assertEqual(self.step(s,qr=True,fingerprint='102',input_marker=2),'hide')
        self.assertEqual(self.step(s,qr=True,fingerprint='102',input_marker=2),'stay')
        self.assertEqual(self.step(s,qr=True,fingerprint='102',idle=61,input_marker=2),'clock')
        self.assertEqual(self.step(s,qr=True,fingerprint='102',input_marker=3),'hide')
        self.assertEqual(self.step(s,input_marker=3),'stay')
        self.assertEqual(self.step(s,qr=True,fingerprint='102',input_marker=3),'new_qr')

    def test_connection_settings_stay_open_when_already_connected(self):
        s=ProjectionState()
        self.step(s)
        s.open_settings()
        self.assertFalse(s.can_hide_on_input())
        self.assertEqual(self.step(s,qr=True,fingerprint='102',input_marker=9),'stay')
        self.assertTrue(s.settings_open)
        self.assertTrue(s.visible)
        s.close_settings()
        self.assertFalse(s.can_hide_on_input())

    def test_connecting_from_settings_restores_screensaver_behavior(self):
        s=ProjectionState()
        self.step(s,paired=False,connected=False)
        s.open_settings()
        self.assertEqual(self.step(s,paired=True,connected=True),'stay')
        self.assertFalse(s.settings_open)
        self.assertFalse(s.can_hide_on_input())
        self.assertEqual(self.step(s,idle=60),'clock')
        self.assertTrue(s.can_hide_on_input())

    def test_clock_without_any_controller_hides_and_returns(self):
        s=ProjectionState(60)
        self.assertEqual(self.step(s,paired=False,connected=False,idle=61),'clock')
        self.assertTrue(s.can_hide_on_input())
        self.assertEqual(self.step(s,paired=False,connected=False,input_marker=2),'hide')
        self.assertEqual(self.step(s,paired=False,connected=False,idle=59,input_marker=2),'stay')
        self.assertEqual(self.step(s,paired=False,connected=False,idle=60,input_marker=2),'clock')

    def test_playback_suppresses_idle_clock_and_new_payment_still_opens(self):
        s=ProjectionState(60)
        self.assertEqual(self.step(s,idle=61,media_active=True),'stay')
        self.assertEqual(self.step(s,idle=61,media_active=True,qr=True,fingerprint='new'),'new_qr')

    def test_new_amount_overrides_dismissal(self):
        s=ProjectionState()
        self.step(s,qr=True,fingerprint='a')
        self.step(s,qr=True,fingerprint='a',input_marker=2)
        self.assertEqual(self.step(s,qr=True,fingerprint='b',input_marker=2),'new_qr')

if __name__=='__main__':unittest.main()
