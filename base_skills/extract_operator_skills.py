"""
从 building_data.json 提取所有干员的制造站技能槽位信息
输出: operator_skills.json — 每个干员两个槽位的技能及其精英解锁条件
"""
import json, os

DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(DIR, 'building_data.json'), 'r', encoding='utf-8') as f:
    data = json.load(f)

chars = data['chars']
buffs = data['buffs']

# 制造站 roomType
MANUFACTURE_ROOM = 'MANUFACTURE'

result = {}
for char_id, char_data in chars.items():
    op_info = {
        'charId': char_id,
        'slots': [],
    }

    for slot_idx, buff_slot in enumerate(char_data.get('buffChar', [])):
        slot_skills = []
        for bd in buff_slot.get('buffData', []):
            phase_str = bd.get('cond', {}).get('phase', 'PHASE_0')
            level = bd.get('cond', {}).get('level', 1)
            buff_id = bd.get('buffId', '')

            # 解析精阶段
            phase_map = {'PHASE_0': 0, 'PHASE_1': 1, 'PHASE_2': 2}
            elite = phase_map.get(phase_str, 0)

            # 查找 buff 定义
            buff = buffs.get(buff_id)
            if not buff:
                # Try with [000] suffix stripped
                base_id = buff_id.split('[')[0] if '[' in buff_id else buff_id
                # Search all buffs with matching prefix
                for bid, b in buffs.items():
                    if bid.startswith(base_id):
                        buff = b
                        break

            room_type = buff.get('roomType', '') if buff else ''
            buff_name = buff.get('buffName', buff_id) if buff else buff_id
            description = buff.get('description', '') if buff else ''
            skill_icon = buff.get('skillIcon', '') if buff else ''

            slot_skills.append({
                'elite': elite,
                'level': level,
                'buffId': buff_id,
                'buffName': buff_name,
                'roomType': room_type,
                'description': description,
                'skillIcon': skill_icon,
            })

        if slot_skills:
            # 按精英阶段排序
            slot_skills.sort(key=lambda x: x['elite'])
            op_info['slots'].append({
                'slotIndex': slot_idx,
                'skills': slot_skills,
            })

    if op_info['slots']:
        result[char_id] = op_info

# === 筛选制造站相关干员 ===
mfg_ops = {}
for char_id, info in result.items():
    for slot in info['slots']:
        for sk in slot['skills']:
            if sk['roomType'] == MANUFACTURE_ROOM or sk['roomType'] in ('', 'NONE'):
                mfg_ops[char_id] = info
                break

print(f'Total operators with buffs: {len(result)}')
print(f'Manufacturing-relevant: {len(mfg_ops)}')

# === 为每个干员生成技能摘要 ===
summary = []
for char_id, info in sorted(mfg_ops.items()):
    lines = [f'{char_id}:']
    for slot in info['slots']:
        active = {}  # elite -> skill
        for sk in slot['skills']:
            if sk['roomType'] not in (MANUFACTURE_ROOM, '', 'NONE'):
                continue
            e = sk['elite']
            if e not in active or e > list(active.keys())[-1] if active else True:
                # This is a bit tricky - same elite can have multiple entries (level-gated)
                # For now, take the highest level entry per elite
                key = f'E{e}'
                if key not in active:
                    active[key] = sk
                elif sk['level'] >= active[key].get('level', 0):
                    active[key] = sk

        for key, sk in sorted(active.items()):
            lines.append(f'  Slot{slot["slotIndex"]} {key}: {sk["buffName"]} ({sk["description"][:80]})')

    summary.append('\n'.join(lines))

with open(os.path.join(DIR, 'manufacturing_operators.txt'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(summary[:100]))  # First 100 operators

# Save full structured data
with open(os.path.join(DIR, 'operator_skills_raw.json'), 'w', encoding='utf-8') as f:
    json.dump(mfg_ops, f, ensure_ascii=False, indent=2)

print(f'\nSaved {len(mfg_ops)} operators to operator_skills_raw.json')
print(f'Sample operators in manufacturing_operators.txt')
