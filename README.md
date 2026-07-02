# 明日方舟账号信息查询工具 v5.0

## 功能
- 多账号管理（添加 / 删除 / 切换）
- Edge/Chrome 浏览器自动登录鹰角通行证
- 获取账号基本信息（UID、手机号、实名等）
- 获取明日方舟游戏角色数据（干员列表等）
- 查看绑定的游戏账号列表
- Tkinter GUI 图形界面

## 使用方法
```bash
pip install -r requirements.txt
python main.py
```

## 项目结构
```
├── main.py              # 程序入口 — Tkinter GUI (v5.0)
├── api.py               # API 请求模块 — 鹰角通行证 + 森空岛
├── browser_auth.py      # 浏览器自动捕获 Token — CDP 协议
├── config.py            # 全局配置 — API 地址、Headers
├── char_data.py         # 干员 ID → 中文名映射
├── char_table.json      # 干员映射表
├── requirements.txt     # 依赖: requests, websocket-client
├── ArknightsInfo.spec   # PyInstaller 打包配置
├── README.md
└── base_skills/         # 基建技能优化子项目
    ├── WORKFLOW.md      # 工作流程文档
    ├── building_data.json         # 游戏解包数据
    ├── operator_skills_raw.json   # 干员双槽位技能
    ├── manufacturing_skills.json  # 制造站技能结构化数据
    ├── extract_operator_skills.py # 解包数据提取脚本
    ├── build_skill_data.py        # PRTS wiki 解析脚本
    ├── solver_v1.py / v2.py       # 逐步求解器
    └── 制造站_重新分类.md          # 技能分类跟踪表
```
