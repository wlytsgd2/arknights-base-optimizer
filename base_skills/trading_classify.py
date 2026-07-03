"""
T.1: 贸易站技能分类
"""
import json, re, os
from collections import defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(DIR, 'all_facility_skills.json'), 'r', encoding='utf-8') as f:
    data = json.load(f)

buffs = data['buffs']

# 提取所有 TRADING buff
trading = []
for bid, b in buffs.items():
    if b['roomType'] != 'TRADING':
        continue
    desc = b.get('description', '')
    name = b.get('name', '')
    clean = re.sub(r'<[^>]+>', '', desc)
    trading.append({'id': bid, 'name': name, 'desc': clean, 'raw_desc': desc})

print(f'TRADING buffs: {len(trading)}')

# === 分类 ===
def classify(skill):
    d = skill['desc']
    n = skill['name']

    # 提取数值
    eff = None
    eff_m = re.search(r'订单获取效率([+-]\d+)%', d)
    if not eff_m: eff_m = re.search(r'([+-]\d+)%.*?效率', d)
    if eff_m: eff = int(eff_m.group(1))

    limit = None
    lim_m = re.search(r'订单上限([+-]\d+)', d)
    if not lim_m: lim_m = re.search(r'订单容量上限([+-]\d+)', d)
    if lim_m: limit = int(lim_m.group(1))

    mood = None
    mood_m = re.search(r'心情每小时消耗([+-]\d+\.?\d*)', d)
    if mood_m: mood = float(mood_m.group(1))

    # 1. 品质相关
    if '品质' in d:
        return ('品质', eff, limit, mood, '调整订单品质出现概率')

    # 2. 归零
    if '全部归零' in d:
        return ('归零', eff, limit, mood, '清零其他效率→自身补偿')

    # 3. 特殊订单类型
    if '赤金' in d and '违约' not in d:
        return ('赤金专属', eff, limit, mood, '仅赤金订单生效')
    if '违约' in d or '赤金' in d:
        return ('特殊订单', eff, limit, mood, '违约/赤金专属机制')

    # 4. 中间产物
    for ip in ['人间烟火', '巫术结晶', '思维链环', '感知信息', '木天蓼', '魔物料理',
               '乌萨斯特饮', '情报储备', '工程机器人']:
        if ip in d:
            return ('中间产物', eff, limit, mood, f'涉及{ip}')

    # 5. 每有/每个条件 (per X)
    if '每有' in d or '每个' in d or '每间' in d or '每级' in d or '每1' in d or '每2' in d or '每4' in d:
        return ('条件加成', eff, limit, mood, '按其他干员/设施/资源累加')

    # 6. COOP同站
    if '当与' in d and '在同一' in d:
        return ('COOP同站', eff, limit, mood, '需特定干员同站')

    # 7. 同站联动 (同设施内特定条件)
    if '当前贸易站' in d and '每' in d:
        return ('条件加成', eff, limit, mood, '同站内条件加成')

    # 8. 纯数值
    if eff is not None:
        return ('纯数值', eff, limit, mood, '')

    # 9. 其他
    if '心情' in d or '每小时消耗' in d:
        return ('心情管理', eff, limit, mood, '')
    if '订单' in d:
        return ('其他', eff, limit, mood, '')
    return ('其他', eff, limit, mood, '')

results = []
for sk in trading:
    cat, eff, limit, mood, note = classify(sk)
    results.append({**sk, 'cat': cat, 'eff': eff, 'limit': limit, 'mood': mood, 'note': note})

# 输出
by_cat = defaultdict(list)
for r in results:
    by_cat[r['cat']].append(r)

order = ['纯数值', '条件加成', 'COOP同站', '品质', '归零', '特殊订单', '赤金专属', '中间产物', '心情管理', '其他']

lines = []
lines.append('# 贸易站技能分类')
lines.append('')
lines.append(f'总计 {len(trading)} 条')
lines.append('')

for cat in order:
    if cat not in by_cat: continue
    items = sorted(by_cat[cat], key=lambda x: -(x['eff'] or 0))
    lines.append(f'## {cat} ({len(items)}条)')
    lines.append('')
    lines.append('| # | 技能名称 | 效率 | 上限 | 心情 | 说明 |')
    lines.append('|---|----------|------|------|------|------|')
    for i, sk in enumerate(items, 1):
        eff_s = f'{sk["eff"]:+d}%' if sk['eff'] is not None else '—'
        lim_s = f'{sk["limit"]:+d}' if sk['limit'] is not None else '—'
        mood_s = f'{sk["mood"]:+.2f}' if sk['mood'] is not None else '—'
        lines.append(f'| {i} | {sk["name"]} | {eff_s} | {lim_s} | {mood_s} | {sk.get("note","")} |')
    lines.append('')

# 统计
lines.append('---')
lines.append('')
lines.append('## 汇总')
lines.append('')
lines.append('| 类别 | 数量 | 有效率 | 有上限 |')
lines.append('|------|------|--------|--------|')
for cat in order:
    if cat not in by_cat: continue
    items = by_cat[cat]
    has_eff = sum(1 for x in items if x['eff'] is not None)
    has_lim = sum(1 for x in items if x['limit'] is not None)
    lines.append(f'| {cat} | {len(items)} | {has_eff} | {has_lim} |')

with open(os.path.join(DIR, '贸易站_技能分类.md'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

for cat in order:
    if cat in by_cat:
        print(f'{cat}: {len(by_cat[cat])} 条')
print(f'\nSaved: 贸易站_技能分类.md')
