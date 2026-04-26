"""
每日财经新闻抓取 + 微信推送 + GitHub Pages 部署
专为 GitHub Actions 环境设计
"""
import time
import random
import requests
import json
import hashlib
import re
import os
from datetime import datetime
import pandas as pd


# ==================== 微信配置 ====================
# 这些敏感信息用环境变量，不要在代码里写死
APP_ID = os.environ.get("APP_ID", "")
APP_SECRET = os.environ.get("APP_SECRET", "")
OPEN_ID = os.environ.get("OPEN_ID", "")
TEMPLATE_ID = os.environ.get("TEMPLATE_ID", "")

# GitHub Pages 地址（改成你自己的）
GITHUB_USERNAME = os.environ.get("USERNAME", "你的用户名")
REPO_NAME = "xinwen"  # 改成你的仓库名
PAGES_URL = f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}"


# ==================== 微信API ====================
def get_access_token():
    """获取微信 access_token"""
    url = f'https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={APP_ID}&secret={APP_SECRET}'
    resp = requests.get(url).json()
    if "access_token" not in resp:
        print(f"❌ 获取access_token失败: {resp}")
        raise Exception(f"微信API错误: {resp}")
    return resp["access_token"]


def send_news_msg(access_token, summary, html_url):
    """发送模板消息（带网页链接）"""
    body = {
        "touser": OPEN_ID,
        "template_id": TEMPLATE_ID,
        "url": html_url,
        "data": {
            "summary": {
                "value": summary
            }
        }
    }
    url = f'https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}'
    resp = requests.post(url, json.dumps(body)).json()
    
    if resp.get("errcode") == 0:
        print("✅ 微信推送成功")
    else:
        print(f"❌ 微信推送失败: {resp}")
    return resp


# ==================== CLS爬虫（直接从filter3.py整合） ====================
class ClsSpider:
    def __init__(self):
        self.api_url = "https://www.cls.cn/v1/roll/get_roll_list"
        self.all_news_data = []
        self.keywords_config = {
            "猪肉涨价": {
                "keywords": ["猪肉", "猪价", "生猪", "肉价上涨", "猪周期", "猪肉价格", "猪瘟", "能繁母猪", "仔猪"]
            },
            "A股重组": {
                "keywords": ["重组", "收购", "并购", "资产注入", "股权转让", "借壳", "合并", "重大资产"]
            },
            "订单": {
                "keywords": ["订单", "中标", "合同", "签约", "大单"]
            }
        }
        self.stock_code_pattern = re.compile(r'[60|30|00|68]\d{4}|[0-9]{6}')
        self.stock_name_pattern = re.compile(r'[\u4e00-\u9fa5]{2,4}(?:股份|集团|科技|控股|生物|医药|证券|银行|保险|能源|汽车|地产)')

    def _generate_sign(self, params):
        sorted_keys = sorted(k for k in params if k != "sign")
        query_string = "&".join(f"{k}={params[k]}" for k in sorted_keys if params[k] is not None)
        return hashlib.md5(hashlib.sha1(query_string.encode()).hexdigest().encode()).hexdigest()

    def extract_title_content(self, content):
        if content.startswith("【") and "】" in content:
            end_idx = content.find("】")
            return content[1:end_idx].strip(), content[end_idx+1:].strip()
        return "", content.strip()

    def has_stock_info(self, text):
        return bool(self.stock_code_pattern.search(text) or self.stock_name_pattern.search(text))

    def check_order_amount(self, text):
        for pattern in [r'(\d+(?:\.\d+)?)\s*亿', r'(\d+(?:\.\d+)?)\s*千万', r'(\d+(?:\.\d+)?)\s*万',
                        r'逾\s*\d+', r'超\s*\d+', r'达\s*\d+']:
            if re.search(pattern, text):
                return True
        return False

    def classify_news(self, title, body):
        text = f"{title} {body}".lower()
        for kw in self.keywords_config["猪肉涨价"]["keywords"]:
            if kw in text:
                return "猪肉涨价"
        for kw in self.keywords_config["订单"]["keywords"]:
            if kw in text and self.check_order_amount(text):
                return "订单"
        for kw in self.keywords_config["A股重组"]["keywords"]:
            if kw in text and self.has_stock_info(text):
                return "A股重组"
        return "其他"

    def process_data(self, roll_data, target_date):
        if not roll_data:
            return 0
        saved = 0
        for item in roll_data:
            ctime = item.get("ctime", 0)
            publish_time = datetime.fromtimestamp(ctime)
            if publish_time.strftime("%Y-%m-%d") != target_date:
                continue
            content = item.get("content", "")
            title, body = self.extract_title_content(content)
            event_type = self.classify_news(title, body)
            self.all_news_data.append({
                "发布时间": publish_time.strftime("%Y-%m-%d %H:%M:%S"),
                "事件类型": event_type,
                "标题": title,
                "内容": body
            })
            saved += 1
        return saved

    def run(self, target_date):
        self.all_news_data = []
        start_ts = int(datetime.strptime(f"{target_date} 00:00:00", "%Y-%m-%d %H:%M:%S").timestamp())
        end_ts = int(datetime.strptime(f"{target_date} 23:59:59", "%Y-%m-%d %H:%M:%S").timestamp())

        # GitHub Actions环境用requests直接调API，不用Playwright开浏览器
        print(f"\n📰 开始抓取 {target_date} 新闻...")
        cursor = end_ts
        page_num = 1
        total = 0

        while True:
            params = {
                "app": "CailianpressWeb",
                "lastTime": cursor,
                "last_time": cursor,
                "os": "web",
                "refresh_type": "1",
                "rn": "50",
                "sv": "8.4.6"
            }
            params["sign"] = self._generate_sign(params)

            resp = requests.get(self.api_url, params=params, 
                              headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                break

            data = resp.json()
            if data.get("errno") != 0:
                break

            roll_list = data.get("data", {}).get("roll_data", [])
            if not roll_list:
                break

            saved = self.process_data(roll_list, target_date)
            total += saved

            min_ctime = min(item["ctime"] for item in roll_list)
            print(f"  第{page_num}页 | +{saved}条 | 累计{total}条")
            
            if min_ctime < start_ts:
                break

            cursor = min(min_ctime, cursor - 1)
            page_num += 1
            time.sleep(random.uniform(3, 6))

        print(f"✅ 共抓取 {len(self.all_news_data)} 条新闻")
        return self.all_news_data


# ==================== HTML生成 ====================
def generate_html(news_data, target_date):
    """把新闻数据生成HTML网页"""
    # 筛选相关新闻
    related = [n for n in news_data if n["事件类型"] != "其他"]
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>今日相关新闻 - {target_date}</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f5f5f5;padding:20px;color:#333}}
  .container{{max-width:800px;margin:0 auto}}
  h1{{text-align:center;color:#2c3e50;margin-bottom:10px;font-size:24px}}
  .date{{text-align:center;color:#7f8c8d;margin-bottom:20px;font-size:14px}}
  .summary{{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;padding:20px;border-radius:12px;margin-bottom:25px;text-align:center}}
  .summary h2{{font-size:20px;margin-bottom:10px}}
  .summary .count{{font-size:48px;font-weight:bold}}
  .summary .tags{{margin-top:10px;font-size:14px;opacity:0.9}}
  .news-card{{background:#fff;border-radius:12px;padding:20px;margin-bottom:15px;box-shadow:0 2px 8px rgba(0,0,0,0.08)}}
  .news-card .badge{{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:bold;color:#fff;margin-right:10px}}
  .badge.pork{{background:#e74c3c}}
  .badge.ma{{background:#e67e22}}
  .badge.order{{background:#27ae60}}
  .news-card .time{{color:#7f8c8d;font-size:13px}}
  .news-card .title{{font-size:18px;font-weight:bold;margin:8px 0;line-height:1.4}}
  .news-card .content{{color:#555;font-size:14px;line-height:1.8}}
  .empty{{text-align:center;padding:80px 20px;color:#999}}
  .footer{{text-align:center;color:#bbb;font-size:12px;margin-top:30px;padding:20px 0}}
</style>
</head>
<body>
<div class="container">
  <h1>📊 今日相关新闻</h1>
  <div class="date">{target_date}</div>
  <div class="summary">
    <h2>今日筛选结果</h2>
    <div class="count">{len(related)}</div>
    <div>条相关新闻</div>
"""
    
    # 统计各类数量
    pork_count = sum(1 for n in related if n["事件类型"] == "猪肉涨价")
    mna_count = sum(1 for n in related if n["事件类型"] == "A股重组")
    order_count = sum(1 for n in related if n["事件类型"] == "订单")
    
    html += f'<div class="tags">🐷 猪肉涨价 {pork_count}条 &nbsp;|&nbsp; 🔄 A股重组 {mna_count}条 &nbsp;|&nbsp; 📦 订单 {order_count}条</div>'
    html += '</div>\n'
    
    # 每条新闻
    if not related:
        html += '<div class="empty">📭 今日暂无相关新闻</div>'
    else:
        for news in related:
            badge_class = {"猪肉涨价": "pork", "A股重组": "ma", "订单": "order"}
            badge_text = {"猪肉涨价": "猪肉涨价", "A股重组": "A股重组", "订单": "订单"}
            bc = badge_class.get(news["事件类型"], "order")
            bt = badge_text.get(news["事件类型"], news["事件类型"])
            
            html += f"""
  <div class="news-card">
    <span class="badge {bc}">{bt}</span>
    <span class="time">{news['发布时间']}</span>
    <div class="title">{news['标题']}</div>
    <div class="content">{news['内容']}</div>
  </div>"""
    
    html += """
  <div class="footer">🤖 自动生成 · 数据来源：财联社</div>
</div>
</body>
</html>"""
    
    return html


def generate_summary(news_data):
    """生成微信推送的摘要文本"""
    related = [n for n in news_data if n["事件类型"] != "其他"]
    if not related:
        return "今日无相关新闻"
    
    pork = sum(1 for n in related if n["事件类型"] == "猪肉涨价")
    mna = sum(1 for n in related if n["事件类型"] == "A股重组")
    order = sum(1 for n in related if n["事件类型"] == "订单")
    
    lines = [
        f"📊 今日相关新闻共 {len(related)} 条",
        f"🐷 猪肉涨价: {pork}条 | 🔄 A股重组: {mna}条 | 📦 订单: {order}条",
        "",
        "👇 点击查看完整内容"
    ]
    
    # 加前3条摘要
    for i, news in enumerate(related[:3]):
        title = news["标题"][:25]
        lines.insert(2 + i, f"{news['事件类型'][:2]} {title}")
    
    return " · ".join(lines)


# ==================== 主流程 ====================
def main():
    # 取北京时间今天
    # GitHub Actions的时区是UTC，需要减8小时
    today = datetime.utcnow()
    # 如果是北京时间下午7点后运行，已经是第二天了
    # 简单处理：取今天的日期
    target_date = today.strftime("%Y-%m-%d")
    
    print(f"\n{'='*60}")
    print(f"📅 执行日期: {target_date}")
    print(f"🔧 APP_ID: {APP_ID[:6]}...")
    print(f"{'='*60}")
    
    # 1. 爬新闻
    spider = ClsSpider()
    news_data = spider.run(target_date)
    
    # 2. 生成HTML
    html_content = generate_html(news_data, target_date)
    
    # 保存HTML到仓库根目录（GitHub Pages会从这里读取）
    html_path = "index.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✅ HTML已生成: {html_path}")
    
    # 3. 尝试发微信推送
    if APP_ID and APP_SECRET and OPEN_ID and TEMPLATE_ID:
        try:
            token = get_access_token()
            summary = generate_summary(news_data)
            html_url = PAGES_URL  # GitHub Pages主页
            send_news_msg(token, summary, html_url)
        except Exception as e:
            print(f"⚠️ 微信推送失败: {e}")
    else:
        print("⚠️ 未配置微信参数，跳过推送")

    print(f"\n🎉 完成！网页地址: {PAGES_URL}")


if __name__ == "__main__":
    main()
