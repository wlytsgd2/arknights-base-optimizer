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
或双击 `dist\ArknightsInfo.exe`（需先用 PyInstaller 构建）

## 项目结构
```
├── main.py              # 程序入口 — Tkinter GUI (v5.0)
├── api.py               # API 请求模块 — 鹰角通行证 + 森空岛
├── auth.py              # 认证模块 — 短信验证码登录 (CLI 旧版)
├── browser_auth.py      # 浏览器自动捕获 Token — CDP 协议
├── config.py            # 全局配置 — API 地址、Headers
├── char_data.py         # 干员 ID → 中文名映射
├── display.py           # Rich 终端美化输出 (CLI 旧版)
├── char_table.json      # 干员映射表
├── requirements.txt     # 依赖: requests, rich
├── ArknightsInfo.spec   # PyInstaller 打包配置
└── README.md
```

## 构建 EXE
```bash
pip install pyinstaller websocket-client
pyinstaller ArknightsInfo.spec
```
