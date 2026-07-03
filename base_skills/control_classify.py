"""
控制中枢技能分类
"""
import json, re, os
from collections import defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(DIR, 'all_facility_skills.json'), 'r', encoding='utf-8') as f:
    data = json.load(f)

buffs = data['buffs']

# 提取 CONTROL buffs
control = []
for bid, b in buffs.items():
    if b['roomType'] != 'CONTROL': continue
    desc = re.sub(r'<[^>]+>', '', b.get('description', ''))
    name = b.get('name', '')
    control.append({'name': name, 'desc': desc, 'id': bid})

# === 分类 ===
def classify(sk):
    d = sk['desc']
    n = sk['name']
    effects = []

    # 制造站
    if '贵金属' in d and '制造站' in d:
        m = re.search(r'生产力([+-]\d+\.?\d*)%', d)
        val = m.group(1) if m else '?'
        effects.append(('制造站(贵金属)', f'+{val}%'))
    elif '制造站' in d and '生产力' in d:
        m = re.search(r'生产力([+-]\d+)%', d)
        val = m.group(1) if m else '?'
        effects.append(('制造站(通用)', f'+{val}%'))

    # 贸易站
    if '贸易站' in d and '订单效率' in d and '所有' in d:
        m = re.search(r'([+-]\d+)%', d)
        val = m.group(1) if m else '?'
        effects.append(('贸易站(全局)', f'{val}%'))
    elif '贸易站' in d and '订单' in d:
        effects.append(('贸易站(条件)', '条件触发'))

    # 会客室
    if '会客室' in d and '线索' in d:
        m = re.search(r'线索搜集速度([+-]\d+)%', d)
        val = m.group(1) if m else '?'
        effects.append(('会客室', f'{val}%'))

    # 训练室
    if '训练室' in d or '专精' in d:
        m = re.search(r'训练速度([+-]\d+)%', d)
        val = m.group(1) if m else '5%'
        effects.append(('训练室', f'{val}%'))

    # 办公室
    if '办公室' in d or '联络速度' in d:
        m = re.search(r'联络速度([+-]\d+)%', d)
        val = m.group(1) if m else '?'
        effects.append(('办公室', f'{val}%'))

    # 发电站
    if '发电站' in d:
        effects.append(('发电站', '数量+2'))

    # 宿舍
    if '宿舍' in d and '心情' in d:
        effects.append(('宿舍', '心情恢复'))

    # 中间产物
    for ip in ['人间烟火', '感知信息', '热情值', '乌萨斯特饮', '情报储备', '木天蓼']:
        if ip in d:
            effects.append(('中间产物', ip))
            break

    # 心情管理
    if '心情' in d and not effects:
        effects.append(('心情管理', ''))

    # COOP
    if '当与' in d:
        cm = re.search(r'当与(.+?)一起', d)
        effects.append(('COOP', cm.group(1) if cm else ''))

    if not effects:
        effects.append(('其他', ''))

    return effects


# 构建分类输出
cat_order = ['制造站(贵金属)', '制造站(通用)', '贸易站(全局)', '贸易站(条件)',
             '会客室', '训练室', '办公室', '发电站', '宿舍', '中间产物', 'COOP', '心情管理', '其他']

by_cat = defaultdict(list)
for sk in control:
    for cat, detail in classify(sk):
        by_cat[cat].append((sk, detail))

lines = []
lines.append('# 控制中枢技能分类')
lines.append('')
lines.append(f'总计 {len(control)} 条')
lines.append('')
lines.append('> 控制中枢最多5人，所有buff全局生效')
lines.append('')

our_interest = {'制造站(贵金属)', '制造站(通用)', '贸易站(全局)', '贸易站(条件)', '中间产物'}
lines.append('## 对我们目标有用的 (制造/贸易/中间产物)')
lines.append('')
for cat in cat_order:
    if cat not in our_interest: continue
    items = by_cat.get(cat, [])
    if not items: continue
    lines.append(f'### {cat} ({len(items)}条)')
    lines.append('')
    lines.append('| 技能名称 | 效果 | 描述 |')
    lines.append('|----------|------|------|')
    for sk, detail in items:
        d = sk['desc'][:100]
        n = sk['name']
        lines.append(f'| {n} | {detail} | {d} |')
    lines.append('')

lines.append('---')
lines.append('')
lines.append('## 全部类别统计')
lines.append('')
lines.append('| 类别 | 数量 | 对我们有用? |')
lines.append('|------|------|------------|')
for cat in cat_order:
    items = by_cat.get(cat, [])
    useful = 'YES' if cat in our_interest else ''
    lines.append(f'| {cat} | {len(items)} | {useful} |')

with open(os.path.join(DIR, '控制中枢_技能分类.md'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

# Summary
print(f'Total CONTROL buffs: {len(control)}')
for cat in cat_order:
    items = by_cat.get(cat, [])
    useful = '←' if cat in our_interest else ''
    if items:
        print(f'  {cat}: {len(items)} {useful}')
