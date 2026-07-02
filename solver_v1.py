"""
赤金最高生产力三人组 — V1 纯数值技能

仅考虑 category=="纯数值" 且 recipe∈{gold,any} 且正向生产力的技能。
无条件、无联动、无中间产物，每名干员独立贡献固定加成。
"""
import json, re, os
from itertools import combinations

DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(DIR, 'manufacturing_skills.json')
OUTPUT = os.path.join(DIR, 'output_v1.txt')

with open(DATA, 'r', encoding='utf-8') as f:
    all_skills = json.load(f)

# ============================================================
# 1. 筛选：纯数值 + 赤金/通用 + 正向生产力
# ============================================================
def extract_prod(skill):
    """从描述中提取生产力百分比数值"""
    d = skill['desc']
    m = re.search(r'生产力([+-]\d+(?:\.\d+)?%)', d)
    if m:
        return float(m.group(1).replace('%', '').replace('+', ''))
    return None

candidates = []
skipped = []

for s in all_skills:
    if s['category'] != '纯数值':
        continue
    if s['recipe'] not in ('gold', 'any'):
        continue

    prod = extract_prod(s)
    if prod is None or prod <= 0:
        skipped.append(s)
        continue

    for op in s['operators']:
        candidates.append({
            'operator': op['name'],
            'elite': op['elite'],
            'skill_id': s['id'],
            'skill_name': s['name'],
            'prod': prod,
            'recipe': s['recipe'],
            'mood': s.get('mood'),
            'warehouse': s.get('warehouse'),
        })

# ============================================================
# 2. 去重：每名干员只取生产力最高的技能
# ============================================================
best = {}
for c in candidates:
    key = c['operator']
    if key not in best or c['prod'] > best[key]['prod']:
        best[key] = c
operators = list(best.values())

# ============================================================
# 3. 枚举所有三人组
# ============================================================
results = []
for trio in combinations(operators, 3):
    names = [op['operator'] for op in trio]
    if len(names) != len(set(names)):
        continue
    total = sum(op['prod'] for op in trio)
    results.append({
        'total': total,
        'ops': trio,
    })
results.sort(key=lambda x: -x['total'])

# ============================================================
# 4. 输出
# ============================================================
out = []
out.append('=' * 70)
out.append('  赤金最高生产力三人组 — V1 纯数值技能')
out.append('=' * 70)
out.append('')
out.append(f'候选干员: {len(operators)} 人  (排除 {len(skipped)} 条无产能/负产能技能)')
out.append(f'三人组总数: {len(results)}')
out.append('')
out.append('-' * 70)
out.append(f'{"排名":<5} {"总产能":<8} {"组合"}')
out.append('-' * 70)

for rank, r in enumerate(results[:20], 1):
    names = ' + '.join(f'{op["operator"]}(精{op["elite"]})' for op in r['ops'])
    details = ' | '.join(f'{op["skill_name"]} {op["prod"]:+.0f}%' for op in r['ops'])
    out.append(f'{rank:<5} {r["total"]:+.0f}%     {names}')
    out.append(f'       → {details}')

out.append('')
out.append('-' * 70)
out.append('排除的无产能/负产能技能:')
for s in skipped:
    ops = ', '.join(f'{o["name"]}(精{o["elite"]})' for o in s['operators'])
    out.append(f'  #{s["id"]} {s["name"]} ({ops})')

# 写入文件
result = '\n'.join(out)
with open(OUTPUT, 'w', encoding='utf-8') as f:
    f.write(result)

# 屏幕摘要
print(f'候选: {len(operators)} 人 → 组合: {len(results)} → Top1: {results[0]["total"]:+.0f}%')
print(f'完整结果: {OUTPUT}')
