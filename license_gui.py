"""
ThingsWindows 授权码生成器 - GUI 版
双击 EXE 打开, 命令行: python license_gui.py
"""
import sys
import os
import tkinter as tk
from tkinter import ttk, messagebox

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from lic import generate_license, parse_license, get_machine_code


class LicenseGenerator:
    def __init__(self, root):
        self.root = root
        root.title("ThingsWindows 授权码生成器")
        root.geometry("620x500")
        root.minsize(540, 460)

        pad = {"padx": 14, "pady": 8}

        # ① 本机机器码
        frm1 = ttk.LabelFrame(root, text="① 本机机器码 (你自己的)", padding=12)
        frm1.pack(fill="x", **pad)
        self.lbl_self = tk.Label(frm1, text="读取中...", font=("Consolas", 13, "bold"), fg="#1a6eff")
        self.lbl_self.pack(anchor="w")
        ttk.Button(frm1, text="📋 复制机器码", command=self.copy_self).pack(anchor="e", pady=(6, 0))

        # ② 给客户生成
        frm2 = ttk.LabelFrame(root, text="② 给客户生成授权码", padding=12)
        frm2.pack(fill="x", **pad)

        ttk.Label(frm2, text="客户机器码:").grid(row=0, column=0, sticky="w", pady=4)
        self.var_machine = tk.StringVar()
        ttk.Entry(frm2, textvariable=self.var_machine, width=40, font=("Consolas", 12)).grid(
            row=0, column=1, padx=6, sticky="we")

        ttk.Label(frm2, text="有效期:").grid(row=1, column=0, sticky="w", pady=4)
        self.var_days = tk.StringVar(value="30")
        ttk.Combobox(frm2, textvariable=self.var_days, width=10,
                     values=["7", "15", "30", "90", "180", "365", "永久"],
                     state="readonly").grid(row=1, column=1, padx=6, sticky="w")

        ttk.Button(frm2, text="✨ 生成授权码", command=self.do_gen).grid(
            row=2, column=0, columnspan=2, pady=(10, 0), sticky="we")

        ttk.Label(frm2, text="授权码:", foreground="#888").grid(row=3, column=0, sticky="w", pady=(10, 2))
        self.var_result = tk.StringVar()
        ent = ttk.Entry(frm2, textvariable=self.var_result, width=44, font=("Consolas", 11))
        ent.grid(row=4, column=0, columnspan=2, sticky="we")

        btns = ttk.Frame(frm2)
        btns.grid(row=5, column=0, columnspan=2, sticky="we", pady=(8, 0))
        ttk.Button(btns, text="📋 复制授权码", command=self.copy_result).pack(side="left")
        ttk.Button(btns, text="🔍 验证上面的授权码", command=self.do_verify).pack(side="left", padx=6)

        frm2.columnconfigure(1, weight=1)

        # ③ 验证任意授权码
        frm3 = ttk.LabelFrame(root, text="③ 验证任意授权码 (粘到这里)", padding=12)
        frm3.pack(fill="x", **pad)
        self.var_check = tk.StringVar()
        ttk.Entry(frm3, textvariable=self.var_check, font=("Consolas", 10)).pack(fill="x")
        ttk.Button(frm3, text="验证", command=self.do_verify_external).pack(anchor="e", pady=(6, 0))

        # 状态条
        self.lbl_status = tk.Label(root, text="", fg="#888", font=("Segoe UI", 9))
        self.lbl_status.pack(pady=(4, 12))

        self.refresh_self()

    def refresh_self(self):
        try:
            self.lbl_self.config(text=get_machine_code(), fg="#1a6eff")
            self.lbl_status.config(text="✅ 已就绪", fg="#34a853")
        except Exception as e:
            self.lbl_self.config(text=f"❌ {e}", fg="#d93025")
            self.lbl_status.config(text=str(e), fg="#d93025")

    def copy_self(self):
        self._copy(self.lbl_self.cget("text"), "✅ 本机机器码已复制到剪贴板")

    def copy_result(self):
        v = self.var_result.get()
        if v: self._copy(v, "✅ 授权码已复制, 发给客户即可")
        else: self.lbl_status.config(text="⚠️ 先生成授权码", fg="#ea4335")

    def _copy(self, text, msg):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.lbl_status.config(text=msg, fg="#34a853")

    def do_gen(self):
        m = self.var_machine.get().strip()
        if not m:
            messagebox.showwarning("提醒", "粘贴客户发来的机器码\n(16位字符, 比如: abc123def4567890)")
            return
        days_raw = self.var_days.get()
        is_perm = days_raw == "永久"
        valid_days = None if is_perm else int(days_raw)
        try:
            lic = generate_license(m, valid_days=valid_days)
            self.var_result.set(lic)
            info = parse_license(lic)
            if info.get("is_permanent"):
                duration = "永久"
            else:
                duration = f"{info['days_remaining']}天"
            tip = (f"✅ 已生成 → 机器码={info['machine_code']}  "
                   f"到期={info['expiry_date']}  ({duration})")
            self.lbl_status.config(text=tip, fg="#34a853")
        except Exception as e:
            self.lbl_status.config(text=f"❌ {e}", fg="#d93025")
            messagebox.showerror("生成失败", str(e))

    def do_verify(self):
        lic = self.var_result.get().strip()
        if lic: self._show_verify(lic)

    def do_verify_external(self):
        lic = self.var_check.get().strip()
        if not lic:
            messagebox.showinfo("提示", "把授权码粘贴到 ③ 输入框里")
            return
        self._show_verify(lic)

    def _show_verify(self, lic):
        try:
            v = parse_license(lic)
            ok = v.get("ok", False)
            if ok:
                parts = [f"✅ 授权有效"]
                if v.get("is_permanent"):
                    parts.append("类型=永久")
                else:
                    parts.append(f"剩余={v['days_remaining']}天")
                parts.append(f"到期={v['expiry_date']}")
                parts.append(f"机器码={v['machine_code']}")
                fg = "#34a853"
            else:
                parts = [f"❌ 授权无效: {v.get('reason', '未知原因')}"]
                fg = "#d93025"
            self.lbl_status.config(text="  |  ".join(parts), fg=fg)
        except Exception as e:
            self.lbl_status.config(text=f"❌ 解析失败: {e}", fg="#d93025")


def main():
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    LicenseGenerator(root)
    root.mainloop()


if __name__ == "__main__":
    main()
