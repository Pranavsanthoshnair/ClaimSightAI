import sys
sys.path.insert(0, 'code')
import pandas as pd

pred = pd.read_csv('code/outputs/sample_predictions.csv')
gt   = pd.read_csv('dataset/sample_claims.csv')
merged = gt.merge(pred, on='user_id', suffixes=('_gt', '_pred'))
n = len(merged)

def acc(col_gt, col_pred):
    t = merged[col_gt].astype(str).str.lower()
    p = merged[col_pred].astype(str).str.lower()
    correct = int((t == p).sum())
    return correct, n, round(correct / n * 100, 1)

cs_c,  cs_n,  cs_a  = acc('claim_status_gt',          'claim_status_pred')
esm_c, esm_n, esm_a = acc('evidence_standard_met_gt', 'evidence_standard_met_pred')
it_c,  it_n,  it_a  = acc('issue_type_gt',             'issue_type_pred')
op_c,  op_n,  op_a  = acc('object_part_gt',            'object_part_pred')

SEP = '=' * 64
print()
print(SEP)
print('  EVALUATION REPORT')
print(SEP)
print(f'  Predictions : code/outputs/sample_predictions.csv')
print(f'  Ground truth: dataset/sample_claims.csv')
print(f'  GT rows      : {len(gt)}')
print(f'  Pred rows    : {len(pred)}')
print(f'  Matched      : {n}  (coverage {round(n/len(gt)*100,1)}%)')
print()
print(f'  claim_status accuracy         : {cs_a}%   ({cs_c}/{cs_n})')
print(f'  evidence_standard_met accuracy: {esm_a}%   ({esm_c}/{esm_n})')
print(f'  issue_type accuracy           : {it_a}%  ({it_c}/{it_n})')
print(f'  object_part accuracy          : {op_a}%  ({op_c}/{op_n})')
print()
print('  Per-field accuracy:')
print(f'  {"Field":<30} {"Accuracy":>10}  {"Correct":>8}')
print('  ' + '-' * 52)
rows = [
    ('claim_status',          cs_c,  cs_n,  cs_a),
    ('evidence_standard_met', esm_c, esm_n, esm_a),
    ('issue_type',            it_c,  it_n,  it_a),
    ('object_part',           op_c,  op_n,  op_a),
]
for name, c, tot, a in rows:
    print(f'  {name:<30} {str(a)+"%":>10}  {str(c)+"/"+str(tot):>8}')
print(SEP)
print()
