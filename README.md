# 每日财经新闻微信推送

自动抓取财联社新闻，筛选猪肉涨价、A股重组、订单相关新闻，生成网页并通过微信模板消息推送。

## 功能

- 自动抓取财联社电报新闻
- 智能筛选三类事件：猪肉涨价、A股重组、订单
- 生成美观的HTML网页（GitHub Pages托管）
- 微信模板消息推送（带网页链接）

## 快速开始

### 1. 克隆仓库
git clone https://github.com/你的用户名/daily-news-push.git
cd daily-news-push

### 2. 安装依赖
pip install -r requirements.txt

### 3. 本地测试
python main.py

运行后会在当前目录生成 index.html，双击即可查看效果。

### 4. 配置微信推送

在仓库 Settings → Secrets and variables → Actions 中添加以下 Secrets：

APP_ID：微信测试号 appID
APP_SECRET：微信测试号 appSecret
OPEN_ID：收信人 openId
TEMPLATE_ID：模板消息 ID
GITHUB_USERNAME：你的 GitHub 用户名

### 5. 开启 GitHub Pages

仓库 Settings → Pages → Source 选 main 分支，根目录选 / (root)，点 Save。

### 6. 启用自动推送

仓库已配置 GitHub Actions，每天北京时间 19:00 自动运行。
也可在 Actions 页面手动触发"每日新闻推送" workflow。

## 模板消息配置

在微信测试号后台新增模板：

模板标题：新闻日常推送
模板内容：{{summary.DATA}}

## 项目结构

daily-news-push/
├── main.py              # 主程序（爬虫 + HTML生成 + 微信推送）
├── requirements.txt     # Python 依赖
├── README.md            # 本文件
├── index.html           # 自动生成的新闻网页
└── .github/
    └── workflows/
        └── daily.yml    # GitHub Actions 定时任务

## 筛选规则

猪肉涨价：关键词包括猪肉、猪价、生猪、猪周期等
A股重组：关键词包括重组、收购、并购、借壳等，需包含个股信息
订单：关键词包括订单、中标、合同、签约等，需包含金额信息

## 定时任务

默认每天北京时间 19:00 自动执行，可在 .github/workflows/daily.yml 中修改 cron 表达式。
UTC 11:00 = 北京时间 19:00

## 数据来源

新闻数据来自财联社 https://www.cls.cn/telegraph

## 许可

MIT License