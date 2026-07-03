"""
提取所有设施的干员技能数据
输出: all_facility_skills.json
"""
import json, os

DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(DIR, 'building_data.json'), 'r', encoding='utf-8') as f:
    data = json.load(f)

chars = data['chars']
buffs = data['buffs']

# 设施类型中文名
ROOM_CN = {
    'MANUFACTURE': '制造站', 'TRADING': '贸易站', 'POWER': '发电站',
    'CONTROL': '控制中枢', 'DORMITORY': '宿舍', 'MEETING': '会客室',
    'HIRE': '办公室', 'TRAINING': '训练室', 'WORKSHOP': '加工站',
    'NONE': '通用', '': '通用',
}

result = {
    'operators': {},
    'buffs': {},
}

# 保存所有 buff 定义
for bid, b in buffs.items():
    result['buffs'][bid] = {
        'id': bid,
        'name': b.get('buffName', ''),
        'roomType': b.get('roomType', ''),
        'description': b.get('description', ''),
        'skillIcon': b.get('skillIcon', ''),
    }

# 提取所有干员的所有槽位
for char_id, char_data in chars.items():
    op = {'charId': char_id, 'slots': []}
    for slot_idx, buff_slot in enumerate(char_data.get('buffChar', [])):
        slot_skills = []
        for bd in buff_slot.get('buffData', []):
            phase = bd.get('cond', {}).get('phase', 'PHASE_0')
            level = bd.get('cond', {}).get('level', 1)
            buff_id = bd.get('buffId', '')
            buff = buffs.get(buff_id, {})
            elite_map = {'PHASE_0': 0, 'PHASE_1': 1, 'PHASE_2': 2}
            slot_skills.append({
                'elite': elite_map.get(phase, 0),
                'level': level,
                'buffId': buff_id,
                'roomType': buff.get('roomType', ''),
                'buffName': buff.get('buffName', buff_id),
                'description': buff.get('description', ''),
            })
        if slot_skills:
            slot_skills.sort(key=lambda x: x['elite'])
            op['slots'].append({'slotIndex': slot_idx, 'skills': slot_skills})
    if op['slots']:
        result['operators'][char_id] = op

# 统计
from collections import Counter
by_room = Counter()
for cid, op in result['operators'].items():
    rooms = set()
    for slot in op['slots']:
        for sk in slot['skills']:
            if sk['roomType']:
                rooms.add(sk['roomType'])
    for r in rooms:
        by_room[r] += 1

print('设施覆盖:')
for rt, count in by_room.most_common():
    print(f'  {ROOM_CN.get(rt, rt):10s} ({rt:15s}): {count:3d} 干员')

# 保存
out_path = os.path.join(DIR, 'all_facility_skills.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False)

file_size = os.path.getsize(out_path)
ops_n = len(result['operators'])
buffs_n = len(result['buffs'])
print(f'\nSaved: {out_path} ({file_size/1024:.0f} KB)')
print(f'Operators: {ops_n}, Buffs: {buffs_n}')
