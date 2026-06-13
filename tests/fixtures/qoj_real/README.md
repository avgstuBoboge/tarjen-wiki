# 真实 QOJ HTML fixtures

从 https://qoj.ac 抓的真实页面，用于校验 parser + 记录结构。

## 文件

- `results_all.html` (75KB) — `/results/QOJ1357` 队赛榜单（Petrozavodsk Summer 2019）
- `user_profile.html` (12KB) — `/user/profile/Qingyu` 用户主页（公开部分）
- `contest_meta.html` (9KB) — `/contest/QOJ1357` 404（不存在）
- `results.html` (2KB) — `/results/303` CF challenge page

## 结论

公开能拿的：
- 比赛列表 `/contests`
- 队赛榜单 `/results/QOJ<cid>`（公开 ICPC 风格比赛）
- 用户主页公开部分

需要登录（拿不到 fixtures，需要用户提供）：
- 比赛详情 `/contest/<cid>` (meta)
- 个人提交列表 `/submissions?user=X`
- 单份提交代码 `/submission/<sid>`

## 用法

```python
import cloudscraper
scraper = cloudscraper.create_scraper()
scraper.get("https://qoj.ac/results/QOJ1357").text  # 公开
```

cloudscraper 自带 CF challenge 绕行（user-agent 模拟 + JA3 指纹），
比 urllib 强很多。
