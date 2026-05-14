#!/usr/bin/env python3
"""
Shrimon - 虾宝监控器
轻量级网页内容监控工具，适合树莓派7x24运行。
"""

import json
import hashlib
import os
import sys
import time
import argparse
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


DEFAULT_CONFIG = {
    "monitors": [],
    "storage_dir": "./snapshots",
    "request_timeout": 30,
    "user_agent": "Shrimon/1.0 (Web Monitor Bot)",
    "delay_between_requests": 2
}


def load_config(path):
    """加载配置文件，如果不存在则创建默认配置。"""
    if not os.path.exists(path):
        print(f"[INFO] 配置文件不存在，创建默认配置: {path}")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        return DEFAULT_CONFIG.copy()

    with open(path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    # 合并默认值
    for key, val in DEFAULT_CONFIG.items():
        config.setdefault(key, val)
    return config


def ensure_dir(path):
    """确保目录存在。"""
    Path(path).mkdir(parents=True, exist_ok=True)


def fetch_url(url, timeout, headers):
    """获取网页内容，返回(text, status_code)。"""
    try:
        resp = requests.get(url, timeout=timeout, headers=headers)
        resp.raise_for_status()
        return resp.text, resp.status_code
    except requests.RequestException as e:
        return None, str(e)


def extract_content(html, selector, selector_type='css'):
    """提取内容，支持CSS选择器、regex、xpath。"""
    if selector_type == 'css':
        soup = BeautifulSoup(html, 'html.parser')
        elements = soup.select(selector)
        return [elem.get_text(strip=True) for elem in elements]
    elif selector_type == 'regex':
        matches = re.findall(selector, html)
        return matches
    else:
        soup = BeautifulSoup(html, 'html.parser')
        elements = soup.select(selector)
        return [elem.get_text(strip=True) for elem in elements]


def compute_hash(text):
    """计算文本的SHA256哈希。"""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def get_snapshot_path(storage_dir, monitor_name):
    """获取监控项的snapshot文件路径。"""
    safe_name = "".join(c if c.isalnum() or c in '-_' else '_' for c in monitor_name)
    return os.path.join(storage_dir, f"{safe_name}.hash")


def read_last_hash(snapshot_path):
    """读取上次保存的哈希值。"""
    if not os.path.exists(snapshot_path):
        return None
    with open(snapshot_path, 'r', encoding='utf-8') as f:
        return f.read().strip()


def save_hash(snapshot_path, hash_value):
    """保存哈希值。"""
    with open(snapshot_path, 'w', encoding='utf-8') as f:
        f.write(hash_value)


def send_webhook(url, payload):
    """发送Webhook通知。"""
    try:
        headers = {'Content-Type': 'application/json'}
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        return True, None
    except requests.RequestException as e:
        return False, str(e)


def run_command(cmd):
    """执行命令通知。"""
    import subprocess
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        return result.returncode == 0, result.stderr
    except Exception as e:
        return False, str(e)


def notify(monitor, old_text, new_text):
    """触发通知。"""
    name = monitor.get('name', 'unknown')
    notify_cfg = monitor.get('notify', {})

    payload = {
        "monitor": name,
        "url": monitor.get('url'),
        "old_preview": old_text[:200] if old_text else None,
        "new_preview": new_text[:200],
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
    }

    # Webhook通知
    webhook_url = notify_cfg.get('webhook')
    if webhook_url:
        ok, err = send_webhook(webhook_url, payload)
        status = "OK" if ok else f"FAIL: {err}"
        print(f"  [WEBHOOK] {status}")

    # 命令通知
    command = notify_cfg.get('command')
    if command:
        ok, err = run_command(command)
        status = "OK" if ok else f"FAIL: {err}"
        print(f"  [COMMAND] {status}")

    # 日志通知（默认）
    log_file = notify_cfg.get('log_file')
    if log_file:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(payload, ensure_ascii=False) + '\n')
        print(f"  [LOG] 已写入 {log_file}")


def check_monitor(monitor, config):
    """检查单个监控项，返回是否有变化。"""
    name = monitor.get('name', 'unnamed')
    url = monitor.get('url')
    selector = monitor.get('selector')

    if not url:
        print(f"[SKIP] {name}: 缺少URL")
        return False

    print(f"[CHECK] {name}: {url}")

    headers = {'User-Agent': config.get('user_agent', DEFAULT_CONFIG['user_agent'])}
    html, status = fetch_url(url, config.get('request_timeout', 30), headers)

    if html is None:
        print(f"  [ERROR] 获取失败: {status}")
        return False

    # 提取内容
    selector_type = monitor.get('selector_type', 'css')
    if selector:
        contents = extract_content(html, selector, selector_type)
        text = '\n'.join(contents)
    else:
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(separator='\n', strip=True)

    if not text:
        print(f"  [WARN] 提取内容为空")
        return False

    # 条件触发检查
    condition = monitor.get('condition')
    if condition:
        op = condition.get('op')
        value = condition.get('value')
        if op == 'contains' and value not in text:
            print(f"  [SKIP] 不满足条件: 内容不包含 '{value}'")
            return False
        elif op == 'not_contains' and value in text:
            print(f"  [SKIP] 不满足条件: 内容包含 '{value}'")
            return False
        elif op == 'regex' and not re.search(value, text):
            print(f"  [SKIP] 不满足条件: 不匹配正则 '{value}'")
            return False

    current_hash = compute_hash(text)
    snapshot_path = get_snapshot_path(config['storage_dir'], name)
    last_hash = read_last_hash(snapshot_path)

    if last_hash is None:
        print(f"  [INIT] 首次运行，保存初始状态")
        save_hash(snapshot_path, current_hash)
        # 首次运行如果满足条件也通知（可选）
        if condition and condition.get('notify_on_init'):
            notify(monitor, "", text)
        return False

    if current_hash == last_hash:
        print(f"  [OK] 无变化")
        return False

    # 有变化！
    print(f"  [CHANGE] 内容发生变化！")
    old_text = "(previous snapshot)"  # 我们不存完整文本，只存hash
    notify(monitor, old_text, text)
    save_hash(snapshot_path, current_hash)
    return True


def run(config_path):
    """主运行函数。"""
    config = load_config(config_path)
    ensure_dir(config['storage_dir'])

    monitors = config.get('monitors', [])
    if not monitors:
        print("[WARN] 配置中没有监控项，请先编辑配置文件添加监控任务。")
        return

    changed_count = 0
    for i, monitor in enumerate(monitors):
        if check_monitor(monitor, config):
            changed_count += 1
        # 请求间隔，避免对目标站造成压力
        if i < len(monitors) - 1:
            delay = config.get('delay_between_requests', 2)
            time.sleep(delay)

    print(f"[DONE] 共检查 {len(monitors)} 个监控项，{changed_count} 个有变化。")


def main():
    parser = argparse.ArgumentParser(description='Shrimon - 轻量级网页监控器')
    parser.add_argument('-c', '--config', default='config.json', help='配置文件路径 (默认: config.json)')
    args = parser.parse_args()

    print(f"🦐 Shrimon 启动 - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    run(args.config)


if __name__ == '__main__':
    main()
