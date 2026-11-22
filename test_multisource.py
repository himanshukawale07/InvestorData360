import unittest,tempfile,sqlite3
from datetime import date
from pathlib import Path
from unittest.mock import patch
from contextlib import closing
import pipeline,feeds,operations
class MultiSourceTests(unittest.TestCase):
 def test_consensus_and_conflict(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); day=date(2026,1,2); d=day.isoformat()
   def fixture(last):
    return day,[('TEST','Equity','USD','Fixture')],[('TEST',d,v,p) for v,p in zip(('Vendor A','Vendor B','Vendor C','Vendor D'),(100,100.5,101,last))],[],[],[]
   with patch.object(pipeline,'DATA',root/'data'),patch.object(pipeline,'OUT',root/'output'),patch.object(operations,'DB',root/'output'/'operations.db'):
    with patch.object(feeds,'fetch',return_value=fixture(100.8)): s=pipeline.run()
    self.assertEqual(s['dual_source_approved_prices'],1)
    with patch.object(feeds,'fetch',return_value=fixture(110)): s=pipeline.run()
    self.assertEqual(s['mastered_prices'],0); self.assertEqual(s['dual_source_approved_prices'],0)
