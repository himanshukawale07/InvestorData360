"""Offline unit tests only. Fixture observations never enter production output."""
import tempfile, unittest, sqlite3
from pathlib import Path
from datetime import date
from unittest.mock import patch
from contextlib import closing
import pipeline, feeds, operations
class RefreshTests(unittest.TestCase):
    def test_repeat_refresh_and_failed_fetch_preserves_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); day=date(2026,1,2)
            def fixture(price):
                return day,[('TEST','Equity','USD','Test fixture')],[('TEST',day.isoformat(),'Vendor A',price)],[],[],[]
            with patch.object(pipeline,'DATA',root/'data'),patch.object(pipeline,'OUT',root/'output'),patch.object(operations,'DB',root/'output'/'operations.db'):
                with patch.object(feeds,'fetch',return_value=fixture(100)): pipeline.run()
                db=root/'output'/'investment.db'
                with closing(sqlite3.connect(db)) as idle:
                    self.assertEqual(idle.execute('SELECT price FROM prices_master').fetchone()[0],100)
                    with patch.object(feeds,'fetch',return_value=fixture(101)): pipeline.run()
                    self.assertEqual(idle.execute('SELECT price FROM prices_master').fetchone()[0],101)
                    with patch.object(feeds,'fetch',side_effect=RuntimeError('test network failure')):
                        with self.assertRaises(RuntimeError): pipeline.run()
                    self.assertEqual(idle.execute('SELECT price FROM prices_master').fetchone()[0],101)
if __name__=='__main__': unittest.main()
