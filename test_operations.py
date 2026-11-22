import tempfile, unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import operations as op
class OperationsTests(unittest.TestCase):
    def test_case_lifecycle(self):
        with tempfile.TemporaryDirectory() as d, patch.object(op,'DB',Path(d)/'ops.db'):
            err=[('Missing price','TEST','2026-01-02','High','Fixture')]
            op.record({'checks':1,'failed_checks':1},err)
            with closing(op.connect()) as c: key=c.execute('SELECT case_id FROM cases').fetchone()[0]
            op.update_case(key,'In review','Analyst','Investigating')
            with self.assertRaises(ValueError): op.update_case(key,'Resolved','Analyst','Premature resolution')
            op.record({'checks':1,'failed_checks':0},[])
            op.update_case(key,'Resolved','Analyst','Source corrected')
            op.record({'checks':1,'failed_checks':1},err)
            with closing(op.connect()) as c:
                self.assertEqual(c.execute('SELECT status FROM cases').fetchone()[0],'Reopened')
                self.assertEqual(c.execute('SELECT COUNT(*) FROM runs').fetchone()[0],3)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM audit').fetchone()[0],2)
