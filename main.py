"""
明日方舟账号信息查询工具 - v5.0

多账号管理: 添加 / 删除 / 切换
"""

import sys, os, json, threading, time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from api import get_user_info, get_full_game_data, APIError
from char_data import get_name
from browser_auth import capture_token

# EXE 要用 exe 所在目录，不是临时解压目录
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(APP_DIR, "accounts.json")


def load_accounts():
    try:
        with open(ACCOUNTS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []

def save_accounts(accounts):
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(accounts, f, ensure_ascii=False)


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("明日方舟 - 账号信息查询工具")
        self.root.geometry("950x680")
        self.root.minsize(750, 500)
        self.accounts = load_accounts()
        self.current_token = ""
        self._setup_ui()
        self._refresh_account_list()

    def _setup_ui(self):
        title_frame = ttk.Frame(self.root)
        title_frame.pack(fill="x", padx=10, pady=(10, 5))
        ttk.Label(title_frame, text="明日方舟 - 账号信息查询工具",
                  font=("Microsoft YaHei", 14, "bold")).pack()
        ttk.Label(title_frame, text="多账号管理 | Edge 浏览器自动登录",
                  foreground="gray").pack()

        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # === 左侧: 账号列表 ===
        left = ttk.LabelFrame(main_frame, text="账号列表", padding=8)
        left.pack(side="left", fill="y", padx=(0, 5))

        self.account_list = tk.Listbox(left, width=22, height=14,
                                        font=("Microsoft YaHei", 10))
        self.account_list.pack(fill="both", expand=True, pady=(0, 8))
        self.account_list.bind("<<ListboxSelect>>", self._on_select_account)

        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="+ 添加", command=self._add_account).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(btn_frame, text="- 删除", command=self._delete_account).pack(side="left", fill="x", expand=True, padx=(2, 0))

        self.refresh_btn = ttk.Button(left, text="刷新数据", command=self._refresh_data)
        self.refresh_btn.pack(fill="x", pady=(8, 0))

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(left, textvariable=self.status_var, foreground="blue",
                  wraplength=180).pack(fill="x", pady=(8, 0))

        # === 右侧: 数据 ===
        right = ttk.Frame(main_frame)
        right.pack(side="left", fill="both", expand=True)

        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill="both", expand=True)

        info_frame = ttk.Frame(self.notebook)
        self.notebook.add(info_frame, text="账号信息")
        self.info_text = scrolledtext.ScrolledText(info_frame, wrap="word",
                                                    font=("Microsoft YaHei", 10))
        self.info_text.pack(fill="both", expand=True)

        char_frame = ttk.Frame(self.notebook)
        self.notebook.add(char_frame, text="干员列表")
        cols = ("name", "rarity", "level", "elite", "potential")
        self.char_tree = ttk.Treeview(char_frame, columns=cols, show="headings", height=20)
        self.char_tree.heading("name", text="名称")
        self.char_tree.heading("rarity", text="星级")
        self.char_tree.heading("level", text="等级")
        self.char_tree.heading("elite", text="精英化")
        self.char_tree.heading("potential", text="潜能")
        self.char_tree.column("name", width=120)
        self.char_tree.column("rarity", width=80, anchor="center")
        self.char_tree.column("level", width=60, anchor="center")
        self.char_tree.column("elite", width=70, anchor="center")
        self.char_tree.column("potential", width=60, anchor="center")
        sb = ttk.Scrollbar(char_frame, orient="vertical", command=self.char_tree.yview)
        self.char_tree.configure(yscrollcommand=sb.set)
        self.char_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.stats_var = tk.StringVar()
        ttk.Label(char_frame, textvariable=self.stats_var).pack(side="bottom", anchor="e", padx=5)

    def _set_status(self, msg):
        self.status_var.set(msg)
        self.root.update_idletasks()

    def _refresh_account_list(self, select_index=None):
        self.account_list.delete(0, "end")
        for a in self.accounts:
            nick = a.get("nickname", "") or a.get("uid", "") or "未命名"
            self.account_list.insert("end", nick)
        if select_index is not None and 0 <= select_index < len(self.accounts):
            self.account_list.selection_set(select_index)
            self.account_list.activate(select_index)

    def _on_select_account(self, evt):
        sel = self.account_list.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self.accounts):
            return
        token = self.accounts[idx]["token"]
        if token != self.current_token:
            self.current_token = token
            self._set_status("正在加载...")
            threading.Thread(target=self._fetch_data, args=(token,), daemon=True).start()

    def _add_account(self):
        """浏览器登录并添加账号"""
        self._set_status("正在启动浏览器...")

        def task():
            token, err = capture_token()
            if not token:
                self.root.after(0, lambda: self._set_status(f"登录失败: {err}"))
                self.root.after(0, lambda: messagebox.showwarning("登录失败", str(err)))
                return

            # 获取账号信息
            phone, uid, nickname = "", "", ""
            try:
                info = get_user_info(token)
                d = info.get("data", {})
                phone = d.get("phone", "")
                uid = d.get("hgId", "")
            except Exception:
                pass

            try:
                game = get_full_game_data(token)
                nickname = game.get("nickname", "") or phone or uid
            except Exception:
                nickname = phone or uid or ""

            account = {
                "token": token,
                "nickname": nickname,
                "uid": uid,
                "lastLogin": int(time.time()),
            }

            # 去重（相同 uid）
            existing_idx = None
            for i, a in enumerate(self.accounts):
                if a.get("uid") and a["uid"] == account["uid"]:
                    existing_idx = i
                    break

            if existing_idx is not None:
                self.accounts[existing_idx] = account
                idx = existing_idx
            else:
                self.accounts.append(account)
                idx = len(self.accounts) - 1

            save_accounts(self.accounts)
            self.current_token = token

            self.root.after(0, lambda: self._refresh_account_list(idx))
            self.root.after(0, lambda: self._set_status("登录成功，正在获取数据..."))
            self.root.after(0, lambda: self._fetch_data(token))
        threading.Thread(target=task, daemon=True).start()

    def _refresh_data(self):
        if self.current_token:
            self._set_status("正在刷新...")
            threading.Thread(target=self._fetch_data, args=(self.current_token,), daemon=True).start()
        else:
            messagebox.showwarning("提示", "请先选择账号")

    def _delete_account(self):
        sel = self.account_list.curselection()
        if not sel:
            messagebox.showwarning("提示", "请先选择要删除的账号")
            return
        idx = sel[0]
        if not messagebox.askyesno("确认", "确定要删除该账号吗？"):
            return
        self.accounts.pop(idx)
        save_accounts(self.accounts)
        self.info_text.delete("1.0", "end")
        self._clear_tree()
        self.stats_var.set("")
        self.current_token = ""
        self._refresh_account_list()
        self._set_status("已删除")

    def _fetch_data(self, token):
        self.info_text.delete("1.0", "end")
        self._clear_tree()
        self.stats_var.set("")

        self._set_status("获取账号信息...")
        try:
            info = get_user_info(token)
            d = info.get("data", {})
            lines = [f"{k}: {v}" for k, v in [
                ("鹰角 UID", d.get("hgId")), ("手机号", d.get("phone")),
                ("邮箱", d.get("email")), ("实名姓名", d.get("identityName")),
                ("未成年", "是" if d.get("isMinor") else "否")
            ] if v and v != "None"]
            self.info_text.insert("1.0", "\n".join(lines) if lines else "未获取到详细信息")
        except APIError as e:
            self.info_text.insert("1.0", f"获取失败: {e}")

        self._set_status("获取游戏数据...")
        try:
            result = get_full_game_data(token)
            gid = result.get("game_uid", "")
            nick = result.get("nickname", "")
            if gid:
                self._set_status(f"游戏 UID: {gid} ({nick})")

            gd = result.get("game_data", {})
            gi = gd.get("data", gd)
            if gi:
                chars = gi.get("chars")
                char_map = gi.get("charInfoMap", {})
                if isinstance(chars, dict):
                    chars = chars.get("list", [])
                if chars:
                    for c in sorted(chars, key=lambda x: x.get("rarity", x.get("star", 0)), reverse=True):
                        cid = c.get("charId", c.get("char_id", ""))
                        api_name = char_map.get(cid, {}).get("name", "")
                        name = api_name or get_name(cid) or cid
                        rarity = c.get("rarity", char_map.get(cid, {}).get("rarity", 0)) or 0
                        rstr = "★" * max(1, int(rarity)) if rarity else ""
                        lv = str(c.get("level", "?"))
                        elite = f"精{c.get('evolvePhase', c.get('elite', 0))}"
                        pot = str(c.get("potentialRank", c.get("potential", 0)))
                        self.char_tree.insert("", "end", values=(name, rstr, lv, elite, pot))
                    self.stats_var.set(f"共 {len(chars)} 名干员")
                    self._set_status(f"完成 - {len(chars)} 名干员")
                elif gi:
                    self.info_text.insert("end",
                        f"\n\n游戏数据:\n{json.dumps(gi, ensure_ascii=False, indent=2)[:3000]}")
            elif result.get("game_data_error"):
                self._set_status(f"游戏数据失败: {result['game_data_error']}")
        except Exception as e:
            self._set_status(f"失败: {e}")

    def _clear_tree(self):
        for item in self.char_tree.get_children():
            self.char_tree.delete(item)

    def run(self):
        # 如果有账号，自动加载第一个
        if self.accounts:
            self.account_list.selection_set(0)
            self.account_list.activate(0)
            self.current_token = self.accounts[0]["token"]
            self._set_status("正在加载...")
            threading.Thread(target=self._fetch_data, args=(self.current_token,), daemon=True).start()
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
