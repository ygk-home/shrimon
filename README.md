# 🦐 Shrimon

轻量级网页内容监控工具。适合树莓派 7×24 小时运行，监控价格变动、新闻更新、页面内容变化等。

## 特性

- 🔧 **零依赖**（仅需 Python3 + requests + beautifulsoup4）
- 📝 **CSS 选择器**精确提取目标内容
- 🔔 **多种通知方式**：Webhook、命令执行、日志文件
- 💾 **哈希存储**：仅保存内容指纹，节省空间
- 🐢 **请求间隔**：避免对目标站点造成压力

## 安装

```bash
pip3 install requests beautifulsoup4
```

## 使用

1. 复制配置文件：
```bash
cp config.json my-config.json
```

2. 编辑 `my-config.json`，添加你要监控的页面。

3. 运行：
```bash
python3 shrimon.py -c my-config.json
```

## 配合 cron 定时执行

```bash
# 每15分钟检查一次
*/15 * * * * cd /path/to/shrimon && python3 shrimon.py -c my-config.json >> cron.log 2>&1
```

## 配置说明

| 字段 | 说明 |
|------|------|
| `name` | 监控任务名称（唯一） |
| `url` | 目标网页地址 |
| `selector` | CSS 选择器，用于提取特定内容（为空则监控整个页面文本） |
| `notify.webhook` | 变化时 POST 的 Webhook URL |
| `notify.command` | 变化时执行的 shell 命令 |
| `notify.log_file` | 变化时追加的日志文件路径 |

## 示例：监控商品价格

```json
{
  "name": "steam-deck-price",
  "url": "https://store.steampowered.com/steamdeck",
  "selector": ".game_purchase_price",
  "notify": {
    "command": "echo 'Steam Deck 价格变动！' | mail -s Alert user@example.com",
    "log_file": "./price-alerts.log"
  }
}
```

## License

MIT
