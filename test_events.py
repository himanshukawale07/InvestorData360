import unittest
from events import alpaca_rows,assurance
class EventsTest(unittest.TestCase):
    def test_parsing_and_matching(self):
        rows=alpaca_rows({'corporate_actions':{'cash_dividends':[{'symbol':'AAPL','id':'test','rate':.25,'ex_date':'2025-01-02'}],'forward_splits':[{'symbol':'AAPL','id':'split','old_rate':1,'new_rate':4,'ex_date':'2024-01-01'}],'cash_mergers':[{'acquiree_symbol':'AAPL','id':'merge','effective_date':'2025-01-01'}]}},['AAPL'])
        self.assertEqual(len(rows),3); self.assertEqual(rows[1][4],4); self.assertIsNone(rows[2][4]); self.assertIsNone(rows[0][10]); self.assertEqual(assurance(rows)[0][-1],'Single-source observation')
        peer=list(rows[0]); peer[6]='Yahoo Finance'; peer=tuple(peer)
        self.assertEqual(assurance([rows[0],peer])[0][-2],'Yahoo Finance')
        conflict=list(peer); conflict[4]=.50
        self.assertEqual(assurance([rows[0],tuple(conflict)])[0][-1],'Review amount discrepancy')
