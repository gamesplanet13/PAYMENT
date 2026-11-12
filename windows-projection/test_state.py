import unittest
from state import ProjectionState
class Tests(unittest.TestCase):
 def test_pair_qr_mouse_idle_close_and_reopen(self):
  s=ProjectionState(60)
  def step(**kwargs):
   vals=dict(paired=True,qr=False,fingerprint='',idle=0,input_marker=1);vals.update(kwargs);return s.decide(**vals)
  self.assertEqual(step(paired=False),'pairing')
  self.assertEqual(step(),'hide')
  self.assertEqual(step(qr=True,fingerprint='102'),'new_qr')
  self.assertEqual(step(qr=True,fingerprint='102',input_marker=2),'hide')
  self.assertEqual(step(qr=True,fingerprint='102',input_marker=2),'stay')
  self.assertEqual(step(qr=True,fingerprint='102',idle=61,input_marker=2),'clock')
  self.assertEqual(step(qr=True,fingerprint='102',input_marker=3),'hide')
  self.assertEqual(step(input_marker=3),'stay')
  self.assertEqual(step(qr=True,fingerprint='102',input_marker=3),'new_qr')
 def test_new_amount_overrides_dismissal(self):
  s=ProjectionState();s.decide(paired=True,qr=True,fingerprint='a',idle=0,input_marker=1)
  s.decide(paired=True,qr=True,fingerprint='a',idle=0,input_marker=2)
  self.assertEqual(s.decide(paired=True,qr=True,fingerprint='b',idle=0,input_marker=2),'new_qr')
if __name__=='__main__':unittest.main()
