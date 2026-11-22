import unittest
import pandas as pd
from assurance import comparison, PROVIDERS
class AssuranceTests(unittest.TestCase):
 def test_cases(self):
  day=pd.Timestamp('2026-01-02')
  for obs,primary,status,other in [([(1,100)],1,'Single-source approval','—'), ([(1,100),(2,100)],1,'2-source verified',PROVIDERS[2]), ([(0,100),(1,100)],0,'2-source verified',PROVIDERS[1]), ([(0,100),(1,110)],None,'Discrepancy — review required','—'), ([],None,'Price unavailable','—'), ([(0,100),(0,100),(1,100)],1,'Single-source approval','—'), ([(3,100)],3,'Single-source approval','—')]:
   raw=pd.DataFrame([('X',day,PROVIDERS[i],float(p)) for i,p in obs],columns=['security_id','price_date','source','price']).astype({'price':float})
   master=pd.DataFrame([] if primary is None else [('X',day,PROVIDERS[primary],100.)],columns=raw.columns)
   row=comparison(raw,master,['X'],[day]).iloc[0]
   self.assertEqual(row['Assurance status'],status); self.assertEqual(row['Verified by'],other); self.assertEqual(row['Primary pricing provider'], '—' if primary is None else PROVIDERS[primary])
