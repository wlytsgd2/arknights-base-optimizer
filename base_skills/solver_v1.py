"""
V1 纯数值 — 基于解包双槽位模型

规则:
- 每名干员有 0~2 个制造相关槽位，同时生效
- 同槽内取该精英阶段能解锁的最高版本
- 只考虑 category=="纯数值" 且正向赤金/通用产能的技能
"""
import json, re, os

DIR = os.path.dirname(os.path.abspath(__file__))

# 加载数据
with open(os.path.join(DIR, 'operator_skills_raw.json'), 'r', encoding='utf-8') as f:
    ops_raw = json.load(f)

with open(os.path.join(DIR, 'manufacturing_skills.json'), 'r', encoding='utf-8') as f:
    mfg_skills = json.load(f)

# 建立 buffName → category / recipe 的映射 (从PRTS解析数据)
skill_meta = {}
for s in mfg_skills:
    skill_meta[s['name']] = {
        'category': s['category'],
        'recipe': s['recipe'],
        'id': s['id'],
    }

# ============================================================
# 1. 计算单槽位在指定精英阶段的技能产能
# ============================================================
def extract_prod(desc):
    """从 buff 描述中提取生产力百分比"""
    # 格式: <@cc.vup>+30%</> 或 <@cc.vdown>-5%</>
    m = re.search(r'([+-]\d+(?:\.\d+)?%)', desc)
    if m:
        return float(m.group(1).replace('%', '').replace('+', ''))
    return None

def get_slot_prod(slot_skills, elite):
    """获取某个槽位在指定精英阶段下的制造产能贡献
    返回 (prod, buffName, skillId) 或 None"""
    best = None
    for sk in slot_skills:
        if sk['elite'] > elite:
            continue
        room = sk['roomType']
        if room not in ('MANUFACTURE', 'NONE', ''):
            continue

        name = sk['buffName']
        meta = skill_meta.get(name, {})
        cat = meta.get('category', '')
        recipe = meta.get('recipe', '')

        # V1: 只处理纯数值
        if cat != '纯数值':
            continue
        # 必须适配贵金属或通用
        if recipe not in ('gold', 'any'):
            continue

        prod = extract_prod(sk['description'])
        if prod is None or prod <= 0:
            continue

        if best is None or sk['elite'] >= best['elite']:
            best = {**sk, 'prod': prod, 'recipe': recipe}

    return best

# ============================================================
# 2. 汇总每名干员在每个精英阶段的总产能
# ============================================================
candidates = []
skipped = []

for char_id, info in ops_raw.items():
    slots = info.get('slots', [])
    max_elite = 2  # 假设可以精2

    for elite in [0, 1, 2]:
        slot_results = []
        total_prod = 0.0
        details = []

        for slot in slots:
            best = get_slot_prod(slot['skills'], elite)
            if best:
                slot_results.append(best)
                total_prod += best['prod']
                details.append(f'S{slot["slotIndex"]}:{best["buffName"]}({best["prod"]:+.0f}%)')

        if total_prod > 0:
            candidates.append({
                'charId': char_id,
                'elite': elite,
                'total_prod': total_prod,
                'details': ' + '.join(details),
                'slot_results': slot_results,
                'name': info.get('charId', char_id),  # 暂时用 ID，后续可映射为中文名
            })

# ============================================================
# 3. 去重: 每名干员取最高总产能的精英阶段
# ============================================================
best_op = {}
for c in candidates:
    key = c['charId']
    if key not in best_op or c['total_prod'] > best_op[key]['total_prod']:
        best_op[key] = c

operators = list(best_op.values())
operators.sort(key=lambda x: -x['total_prod'])

# ============================================================
# 4. 枚举三人组
# ============================================================
from itertools import combinations

results = []
for trio in combinations(operators, 3):
    total = sum(op['total_prod'] for op in trio)
    results.append({
        'total': total,
        'ops': trio,
    })
results.sort(key=lambda x: -x['total'])

# ============================================================
# 5. 输出
# ============================================================
out = []
out.append('=' * 70)
out.append('  V1 纯数值 — 基于解包双槽位模型')
out.append('=' * 70)
out.append('')
out.append(f'制造相关干员总数: {len(ops_raw)}')
out.append(f'去重后候选: {len(operators)} 人')
out.append(f'三人组总数: {len(results)}')
out.append('')

# 列出双槽位叠加的干员
out.append('双槽位同时生效的干员 (E2):')
for op in sorted(operators, key=lambda x: -x['total_prod']):
    if ' + ' in op['details']:
        out.append(f'  {op["charId"]:30s} E{op["elite"]}  {op["total_prod"]:+.0f}%  [{op["details"]}]')
out.append('')

out.append('-' * 70)
out.append(f'{"排名":<5} {"总产能":<8} {"组合"}')
out.append('-' * 70)

for rank, r in enumerate(results[:20], 1):
    names = ' + '.join(f'{op["charId"]}(E{op["elite"]})' for op in r['ops'])
    detail = ' | '.join(f'{op["details"]} = {op["total_prod"]:+.0f}%' for op in r['ops'])
    out.append(f'{rank:<5} {r["total"]:+.0f}%     {names}')
    out.append(f'       → {detail}')

out.append('')
out.append('-' * 70)
out.append('所有候选干员 (按产能排序):')
for i, op in enumerate(operators, 1):
    out.append(f'  {i:3d}. {op["charId"]:30s} E{op["elite"]}  {op["total_prod"]:+.0f}%  [{op["details"]}]')

result = '\n'.join(out)
output_path = os.path.join(DIR, 'output_v1_new.txt')
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(result)

print(f'Candidates: {len(operators)}, Combos: {len(results)}, Top1: {results[0]["total"]:+.0f}%')
print(f'Output: {output_path}')
