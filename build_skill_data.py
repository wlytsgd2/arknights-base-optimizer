import json, re

# Read from the ORIGINAL combined table which has 4 columns: # | name | desc | operators
with open(r'c:\Users\wangz\Desktop\新建文件夹\后勤技能表格.md', 'r', encoding='utf-8') as f:
    content = f.read()

# Extract only the 制造站 section
mfg_start = content.find('## 制造站')
mfg_end = content.find('## 贸易站')
if mfg_start >= 0 and mfg_end > mfg_start:
    content = content[mfg_start:mfg_end]

rows = []
for line in content.splitlines():
    m = re.match(r'\| (\d+) \| (.+?) \| (.+?) \| (.+?) \|', line)
    if m:
        rows.append({
            'num': m.group(1).strip(),
            'name': m.group(2).strip(),
            'desc': m.group(3).strip(),
            'operators': m.group(4).strip()
        })

seen = set()
unique_rows = []
for r in rows:
    if r['num'] not in seen:
        seen.add(r['num'])
        unique_rows.append(r)

unique_rows.sort(key=lambda x: int(x['num']))
print(f'Parsed {len(unique_rows)} unique skills')

skills = []
for r in unique_rows:
    desc = r['desc']
    s = {
        'id': int(r['num']),
        'name': r['name'],
        'desc': desc,
    }

    # Parse operators
    ops = []
    for op_part in r['operators'].split(','):
        op_part = op_part.strip()
        m = re.match(r'(.+)\(精(\d+)\)', op_part)
        if m:
            ops.append({'name': m.group(1), 'elite': int(m.group(2))})
    s['operators'] = ops

    # Recipe type
    if '作战记录' in desc:
        s['recipe'] = 'combat_record'
    elif '贵金属' in desc:
        s['recipe'] = 'gold'
    elif '源石' in desc:
        s['recipe'] = 'orundum'
    else:
        s['recipe'] = 'any'

    # Flat productivity
    prod_match = re.search(r'生产力([+-]\d+(?:\.\d+)?%)', desc)
    s['prod_flat'] = prod_match.group(1) if prod_match else None

    # Ramp-up productivity
    ramp_match = re.search(r'首小时([+-]\d+%).*最终达到([+-]\d+%)', desc)
    ramp2_match = re.search(r'每小时([+-]\d+%)，最终达到([+-]\d+%)', desc)
    if ramp_match:
        s['prod_ramp'] = {'start': ramp_match.group(1), 'end': ramp_match.group(2)}
    elif ramp2_match:
        s['prod_ramp'] = {'per_hour': ramp2_match.group(1), 'end': ramp2_match.group(2)}
    else:
        s['prod_ramp'] = None

    # Per-facility productivity
    s['prod_per_facility'] = None
    if '每个贸易站' in desc and '生产力' in desc:
        m = re.search(r'每个贸易站.*?生产力([+-]\d+%)', desc)
        if m: s['prod_per_facility'] = {'type': 'trading_post', 'value': m.group(1)}
    if '每个发电站' in desc and '生产力' in desc:
        m = re.search(r'每个发电站.*?生产力([+-]\d+%)', desc)
        if m: s['prod_per_facility'] = {'type': 'power_plant', 'value': m.group(1)}

    # Per-dorm-level productivity
    s['prod_per_dorm'] = None
    if '每间宿舍每级' in desc:
        m = re.search(r'生产力([+-]\d+%)', desc)
        if m: s['prod_per_dorm'] = {'value': m.group(1)}

    # Per-training-room productivity
    s['prod_per_training'] = None
    if '训练室每级' in desc:
        m = re.search(r'生产力([+-]\d+%)', desc)
        if m:
            max_m = re.search(r'最多(\d+%)', desc)
            s['prod_per_training'] = {'value': m.group(1), 'max': max_m.group(1) if max_m else '30%'}

    # Per-operator-in-same-facility (A1 squad)
    s['prod_per_same_op'] = None
    if 'A1小队' in desc:
        m = re.search(r'每个.*?A1小队.*?生产力([+-]\d+%)', desc)
        if m: s['prod_per_same_op'] = {'faction': 'A1', 'value': m.group(1)}

    # Per-faction-in-base
    s['prod_per_faction'] = None
    fm = re.search(r'每有(\d+)名(.+?)干员.*?生产力([+-]\d+%)', desc)
    if fm:
        s['prod_per_faction'] = {
            'count': int(fm.group(1)), 'faction': fm.group(2).strip(),
            'max': None, 'value': fm.group(3)
        }
        max_m = re.search(r'最多(\d+)名', desc)
        if max_m: s['prod_per_faction']['max'] = int(max_m.group(1))

    # Coop condition
    s['coop_with'] = None
    s['coop_extra_prod'] = None
    if '当与' in desc and '在同一个制造站' in desc:
        m = re.search(r'当与(.+?)在同一个制造站', desc)
        if m:
            s['coop_with'] = m.group(1).strip()
            em = re.search(r'额外([+-]\d+%)', desc)
            if em: s['coop_extra_prod'] = em.group(1)

    # External condition
    s['external_cond'] = None
    if '若古米在贸易站' in desc:
        s['external_cond'] = {'operator': '古米', 'facility': 'trading_post'}

    # Warehouse capacity
    wh_match = re.search(r'仓库容量上限([+-]\d+)', desc)
    s['warehouse'] = int(wh_match.group(1)) if wh_match else None

    # Mood consumption
    mood_match = re.search(r'心情每小时消耗([+-]\d+(?:\.\d+)?)', desc)
    s['mood'] = float(mood_match.group(1)) if mood_match else None

    # Mood all
    s['mood_all'] = None
    if '所有干员心情每小时消耗' in desc:
        m = re.search(r'所有干员心情每小时消耗([+-]\d+(?:\.\d+)?)', desc)
        if m: s['mood_all'] = float(m.group(1))

    # Eliminate mood
    s['eliminate_mood'] = '消除' in desc and '心情消耗' in desc

    # Skill class
    name = s['name']
    if '标准化' in name:
        s['skill_class'] = 'standard'
    elif '莱茵科技' in name:
        s['skill_class'] = 'rhine'
    elif '红松骑士团' in name:
        s['skill_class'] = 'redpine'
    elif '金属工艺' in name:
        s['skill_class'] = 'metal'
    elif '自动化' in name or '仿生海龙' in name:
        s['skill_class'] = 'automation'
    elif '工匠精神' in name:
        s['skill_class'] = 'craftsman'
    else:
        s['skill_class'] = 'other'

    # Per-skill-class bonus
    s['prod_per_skill_class'] = None
    sc_match = re.search(r'每个(.+?)类技能为自身([+-]\d+%)', desc)
    if sc_match:
        s['prod_per_skill_class'] = {'class_label': sc_match.group(1).strip(), 'value': sc_match.group(2)}

    # Zero-out mechanic
    s['zero_out'] = '全部归零' in desc
    if s['zero_out']:
        # per-operator bonus after zeroing
        zop_match = re.search(r'每个.*?干员.*?生产力([+-]\d+%)', desc)
        if zop_match: s['zero_out_per_op'] = zop_match.group(1)
        zpp_match = re.search(r'每个发电站.*?生产力([+-]\d+%)', desc)
        if zpp_match: s['zero_out_per_pp'] = zpp_match.group(1)
        zwh_match = re.search(r'每个.*?干员.*?仓库容量上限([+-]\d+)', desc)
        if zwh_match: s['zero_out_per_op_wh'] = int(zwh_match.group(1))

    # Mood gap
    s['mood_gap'] = '心情落差' in desc
    if s['mood_gap']:
        gap_match = re.search(r'每有(\d+)点心情落差.*?生产力([+-]\d+%)', desc)
        if gap_match:
            s['mood_gap_per'] = int(gap_match.group(1))
            s['mood_gap_prod'] = gap_match.group(2)
        gap2_match = re.search(r'心情落差大于(\d+).*?生产力([+-]\d+%).*?仓库容量([+-]\d+)', desc)
        if gap2_match:
            s['mood_gap_threshold'] = int(gap2_match.group(1))
            s['mood_gap_prod'] = gap2_match.group(2)
            s['mood_gap_wh'] = int(gap2_match.group(3))

    # Skill merge
    s['skill_merge'] = '视作' in desc
    if s['skill_merge']:
        s['merge_from'] = ['rhine', 'redpine']
        s['merge_to'] = 'standard'

    # Warehouse to productivity
    s['wh_to_prod'] = None
    whp_match = re.search(r'每格仓库容量.*?提供(\d+)%生产力', desc)
    if whp_match:
        s['wh_to_prod'] = {'per_grid': int(whp_match.group(1))}
    if '提升16格以下的' in desc:
        s['wh_to_prod'] = {'rule': 'tiered', 'below_16': 1, 'above_16': 3}

    # Intermediate products
    s['intermediates'] = []
    for ip in ['人间烟火', '巫术结晶', '思维链环', '记忆碎片', '感知信息',
               '木天蓼', '魔物料理', '工程机器人', '乌萨斯特饮', '热情值', '情报储备']:
        if ip in desc:
            s['intermediates'].append(ip)

    # Warehouse per skill class
    s['wh_per_skill_class'] = None
    wsc_match = re.search(r'每个(.+?)类技能为自身([+-]\d+)的仓库', desc)
    if wsc_match:
        s['wh_per_skill_class'] = {'class_label': wsc_match.group(1).strip(), 'value': int(wsc_match.group(2))}

    # Simplified flag
    s['simple'] = not any([
        s['coop_with'], s['prod_per_facility'], s['prod_per_dorm'],
        s['prod_per_training'], s['prod_per_faction'], s['prod_per_same_op'],
        s['prod_per_skill_class'], s['zero_out'], s['mood_gap'], s['skill_merge'],
        s['wh_to_prod'], s['intermediates'], s['external_cond'],
        s['prod_ramp'], s['eliminate_mood'], s['wh_per_skill_class']
    ])

    skills.append(s)

with open(r'c:\Users\wangz\Desktop\新建文件夹\manufacturing_skills.json', 'w', encoding='utf-8') as f:
    json.dump(skills, f, ensure_ascii=False, indent=2)

simple = [s for s in skills if s['simple']]
complex_skills = [s for s in skills if not s['simple']]
gold = [s for s in skills if s['recipe'] in ('gold', 'any')]

print(f'Total: {len(skills)}')
print(f'Simple (flat prod): {len(simple)}')
print(f'Complex: {len(complex_skills)}')
print(f'Gold-compatible: {len(gold)}')
print()

for s in complex_skills:
    reasons = []
    if s['coop_with']: reasons.append('coop')
    if s['prod_per_facility']: reasons.append('per_fac')
    if s['prod_per_dorm']: reasons.append('per_dorm')
    if s['prod_per_training']: reasons.append('per_train')
    if s['prod_per_faction']: reasons.append('per_faction')
    if s['prod_per_same_op']: reasons.append('per_same_op')
    if s['prod_per_skill_class']: reasons.append('per_class')
    if s['zero_out']: reasons.append('zero_out')
    if s['mood_gap']: reasons.append('mood_gap')
    if s['skill_merge']: reasons.append('merge')
    if s['wh_to_prod']: reasons.append('wh_to_prod')
    if s['intermediates']: reasons.append('inter')
    if s['external_cond']: reasons.append('ext_cond')
    if s['prod_ramp']: reasons.append('ramp')
    if s['eliminate_mood']: reasons.append('elim_mood')
    if s['wh_per_skill_class']: reasons.append('wh_per_class')
    print(f'  #{s["id"]:3d} {s["name"]:16s} [{s["recipe"]:14s}] {", ".join(reasons)}')
