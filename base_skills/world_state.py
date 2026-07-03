"""
WorldState — 全局基建状态

各层之间通过 WorldState 单向传递数据。
每一层只读取上一层的快照, 写入自己的结果。
"""
import json, os, re
from itertools import combinations

DIR = os.path.dirname(os.path.abspath(__file__))

# 基建常量
TRADING_POSTS = 2
POWER_PLANTS = 3
DORMS = 4
DORM_LEVEL = 5
TRAINING_LEVEL = 3
ROBOTS = 64
HOURS = 12

# 设施需求
FACILITY_SLOTS = {
    'TRADING': 3,        # 每贸易站3人
    'MANUFACTURE': 3,    # 每制造站3人
    'CONTROL': 5,        # 控制中枢5人
}

class WorldState:
    def __init__(self):
        self.baseline = {}     # {facility_key: [top_results]}
        self.snapshot = {}     # 自动提取的条件快照
        self.control_buffs = {}  # {buff_type: value}
        self.adjusted = {}     # buff后的重算结果
        self.final = {}        # 最终排班

    def to_dict(self):
        return {
            'baseline': self.baseline,
            'snapshot': self.snapshot,
            'control_buffs': self.control_buffs,
            'adjusted': self.adjusted,
            'final': self.final,
        }


# ============================================================
# 层0: 基线排班 — 无中枢, 无联动
# ============================================================

def load_all_data():
    """加载所有数据"""
    data = {}
    for fname in ['all_facility_skills.json', 'manufacturing_skills.json']:
        with open(os.path.join(DIR, fname), 'r', encoding='utf-8') as f:
            data[fname.replace('.json', '')] = json.load(f)
    ct_path = os.path.join(DIR, '..', 'char_table.json')
    if os.path.exists(ct_path):
        with open(ct_path, 'r', encoding='utf-8') as f:
            data['char_table'] = json.load(f)
    return data

def cn_name(char_id, data):
    ct = data.get('char_table', {})
    if char_id in ct and isinstance(ct[char_id], dict):
        return ct[char_id].get('name', char_id)
    return char_id

def layer0_baseline(data):
    """
    层0: 独立求解所有设施 (无中枢buff, 无联动)
    返回 baseline dict
    """
    from solver_core import solve, resolve_trio

    world = WorldState()
    baseline = {}

    # --- 制造站 gold ×2 ---
    results, ops, _ = solve('MANUFACTURE', 'gold', HOURS)
    used = set()
    stations = []
    for _ in range(2):
        remaining = [op for op in ops if op['charId'] not in used]
        best = None
        for trio in combinations(remaining, 3):
            t, _ = resolve_trio(trio, data['all_facility_skills'])
            if best is None or t > best['total']:
                best = {'total': t, 'ops': trio}
        if best:
            stations.append(best)
            used.update(op['charId'] for op in best['ops'])
    baseline['gold'] = stations

    # --- 制造站 combat_record ×2 ---
    results, ops, _ = solve('MANUFACTURE', 'combat_record', HOURS)
    stations = []
    for _ in range(2):
        remaining = [op for op in ops if op['charId'] not in used]
        best = None
        for trio in combinations(remaining, 3):
            t, _ = resolve_trio(trio, data['all_facility_skills'])
            if best is None or t > best['total']:
                best = {'total': t, 'ops': trio}
        if best:
            stations.append(best)
            used.update(op['charId'] for op in best['ops'])
    baseline['exp'] = stations

    # --- 贸易站 ×2 ---
    from trading_solver import solve_trading_standalone
    tr_results, tr_ops = solve_trading_standalone(data, exclude=used)
    stations = []
    for r in tr_results:
        trio_used = any(op['charId'] in used for op in r['ops'])
        if trio_used: continue
        stations.append(r)
        used.update(op['charId'] for op in r['ops'])
        if len(stations) >= 2: break
    baseline['trading'] = stations

    world.baseline = baseline
    return world


def _score_trading_trio(trio):
    """贸易站三人组评分, 适配 trading_solver 的 operator 结构"""
    base_eff = 100; base_lim = 10
    total_eff = 0; total_lim = 0
    trio_names = {op.get('cn_name', op['charId']) for op in trio}
    for op in trio:
        eff = op.get('total_eff', 0); lim = op.get('total_lim', 0)
        # COOP check
        for need in op.get('coop_needs', []):
            if need not in trio_names:
                eff = op.get('total_eff_nc', eff)
                lim = op.get('total_lim_nc', lim)
                break
        total_eff += eff; total_lim += lim
    return (base_eff + total_eff) * (base_lim + total_lim)


# ============================================================
# 层1: 快照提取
# ============================================================

def layer1_snapshot(world, data):
    """
    从基线排班提取条件快照:
    - 赤金生产线数
    - 各站派系分布
    - 谢拉格/叙拉古/龙门近卫局 等关键派系在哪些站
    """
    snap = {
        'gold_lines': len(world.baseline.get('gold', [])),
        'factions_in_mfg': {},
        'factions_in_trade': {},
        'operators_in_mfg': set(),
        'operators_in_trade': set(),
    }
    for station in world.baseline.get('gold', []) + world.baseline.get('exp', []):
        for op in station['ops']:
            snap['operators_in_mfg'].add(op['charId'])
    for station in world.baseline.get('trading', []):
        for op in station['ops']:
            snap['operators_in_trade'].add(op['charId'])

    world.snapshot = snap
    return world


# ============================================================
# 层2: 中枢求解 (后续实现)
# ============================================================

def layer2_control(world, data):
    """根据快照计算中枢最优5人 (待实现)"""
    world.control_buffs = {
        'trade_efficiency': 0,
        'mfg_productivity': 0,
    }
    return world


# ============================================================
# 管线入口
# ============================================================

def run_pipeline():
    data = load_all_data()
    world = layer0_baseline(data)
    world = layer1_snapshot(world, data)
    world = layer2_control(world, data)
    return world


if __name__ == '__main__':
    world = run_pipeline()
    print('=== 层0: 基线排班 ===')
    for key, stations in world.baseline.items():
        for i, st in enumerate(stations):
            names = ' + '.join(cn_name(op['charId'], load_all_data()) for op in st['ops'])
            metric = st.get('total', st.get('score', '?'))
            print('  {}_{}: {} = {}'.format(key, chr(65+i), metric, names))

    print()
    print('=== 层1: 快照 ===')
    for k, v in world.snapshot.items():
        if isinstance(v, set):
            print('  {}: {} operators'.format(k, len(v)))
        else:
            print('  {}: {}'.format(k, v))

    print()
    print('=== 层2: 中枢 (待实现) ===')
    print(world.control_buffs)
