#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Listary 6.3.5.94 Pro 解锁补丁。

原理: 把 Listary.Core.Pro.LicenseChecker.CheckLicense 的方法体改写为
      ldc.i4.1; ret (IL: 17 2A), 使其恒返回 True, 从而解锁 Pro 功能。
      该程序集无强名称, 改 IL 不需要重新签名。

用法:
    python ListaryPro_patch.py --verify    # 只查状态, 不停进程、不改文件
    python ListaryPro_patch.py             # 打补丁 (自动停/启 Listary)
    python ListaryPro_patch.py --revert    # 回滚到未打补丁版本
"""

import argparse
import csv
import io
import os
import shutil
import subprocess
import sys
import time

# CheckLicense 方法体: fat header (12 字节) + IL 开头, 用于版本校验
OFFSET = 0x2ED00
EXPECT = bytes([0x13, 0x30, 0x04, 0x00, 0x22, 0x00, 0x00, 0x00,
                0xD9, 0x01, 0x00, 0x11, 0x18, 0x8D, 0x0D, 0x00])
PATCH = bytes([0x0A, 0x17, 0x2A])  # tiny header(size=2) + ldc.i4.1 + ret
DEFAULT_EXE = r"C:\Program Files\Listary\Listary.exe" # 请替换为您自己的安装目录
PROC_NAME = "Listary.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def hexs(data):
    return " ".join(f"{b:02X}" for b in data)


def read_head(path, size=16):
    with open(path, "rb") as f:
        f.seek(OFFSET)
        return f.read(size)


def state_of(head):
    if head[:3] == PATCH:
        return "patched"
    if head == EXPECT[:len(head)]:
        return "stock"
    return "unknown"


def listary_pids():
    """返回 Listary.exe 的 PID 列表, 不依赖 psutil。"""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {PROC_NAME}", "/NH", "/FO", "CSV"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=NO_WINDOW,
        )
    except OSError:
        return []
    pids = []
    for row in csv.reader(io.StringIO(out.stdout or "")):
        if len(row) >= 2 and row[0].strip().lower() == PROC_NAME.lower():
            try:
                pids.append(int(row[1]))
            except ValueError:
                pass
    return pids


def stop_listary():
    """停掉 Listary 主进程, 返回它之前是否在运行。"""
    if not listary_pids():
        return False
    subprocess.run(["taskkill", "/F", "/T", "/IM", PROC_NAME],
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace", creationflags=NO_WINDOW)
    time.sleep(2)
    if listary_pids():
        raise SystemExit("无法停止 Listary 进程(可能以管理员权限运行), "
                         "请用管理员身份的终端重新运行本脚本。")
    print("已停止 Listary 主进程")
    return True


def start_listary(path):
    subprocess.Popen([path], close_fds=True,
                     creationflags=NO_WINDOW | getattr(subprocess, "DETACHED_PROCESS", 0))
    time.sleep(3)
    print("已重新启动 Listary")


def do_verify(path):
    head = read_head(path)
    label = {"patched": "已注入补丁 (CheckLicense -> true)",
             "stock": "原版",
             "unknown": "未知字节, 可能是其他版本"}[state_of(head)]
    print(f"文件: {path}")
    print(f"状态: {label}")
    print(f"偏移 0x{OFFSET:X} 当前字节: {hexs(head)}")
    pids = listary_pids()
    print(f"进程: {'运行中 (PID ' + ','.join(map(str, pids)) + ')' if pids else '未运行'}")


def do_revert(path, no_restart):
    bak = path + ".pre_pro_patch"
    if not os.path.exists(bak):
        raise SystemExit(f"备份不存在, 无法回滚: {bak}")
    was_running = stop_listary()
    shutil.copyfile(bak, path)
    print(f"已回滚原版: {path}")
    print(f"偏移 0x{OFFSET:X} 当前字节: {hexs(read_head(path))}")
    if was_running and not no_restart:
        start_listary(path)


def do_patch(path, no_restart):
    with open(path, "rb") as f:
        f.seek(OFFSET)
        head = f.read(16)

    if state_of(head) == "patched":
        print(f"补丁已存在, 无需重复写入。偏移 0x{OFFSET:X}: {hexs(head)}")
        return
    if head != EXPECT:
        raise SystemExit("偏移 0x{:X} 处字节与预期不符, 拒绝写入。\n当前: {}\n预期: {}".format(
            OFFSET, hexs(head), hexs(EXPECT)))

    was_running = stop_listary()

    bak = path + ".pre_pro_patch"
    if not os.path.exists(bak):
        shutil.copyfile(path, bak)
        print(f"备份原文件 -> {bak}")
    else:
        print(f"备份已存在, 保留原有备份 -> {bak}")

    with open(path, "r+b") as f:
        f.seek(OFFSET)
        f.write(PATCH)
        f.flush()
        os.fsync(f.fileno())

    print(f"已写入 3 字节: {hexs(PATCH)}  (tiny header + ldc.i4.1 + ret)")
    print(f"偏移 0x{OFFSET:X} 现状: {hexs(read_head(path))}")

    if was_running and not no_restart:
        start_listary(path)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Listary Pro 解锁补丁 (CheckLicense 恒真)")
    parser.add_argument("--path", default=DEFAULT_EXE, help="Listary.exe 路径")
    parser.add_argument("--verify", action="store_true", help="只查状态, 不改文件")
    parser.add_argument("--revert", action="store_true", help="从备份回滚")
    parser.add_argument("--no-restart", action="store_true", help="改完不自动重启 Listary")
    args = parser.parse_args()

    if not os.path.exists(args.path):
        raise SystemExit(f"找不到文件: {args.path}")

    if args.verify:
        do_verify(args.path)
    elif args.revert:
        do_revert(args.path, args.no_restart)
    else:
        do_patch(args.path, args.no_restart)


if __name__ == "__main__":
    main()