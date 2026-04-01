# Giikin `api_proxy/rakuten` — PRD 1–10 完整代理 Payload（另见 PRD 2 补：RPP-EXP merchant）

`POST https://openapi.giikin.com/arachne/thirdshop_proxy/api_proxy/rakuten`  
Header：`Authorization: <oauth2/client_token 返回的 data.client_token>`  
`Content-Type: application/json`

`<USERNAME>` 换绑定用户名；`x-shop-url` 等按店修改。**PRD4 勿手写 `x-csrf-token`**（Giikin 代理按绑定会话代持）。PRD4 form 与 `docs/api.md` 抓包同步，改版后执行：`uv run python scripts/_build_giikin_proxy_payloads_md.py`

**与 `docs/proxy_openapi.md`（官方 OpenAPI）一致**：POST 乐天使用 **`req_data`**（JSON 对象），勿用旧字段 `body` 字符串。GET 的 query 可写在 `url` 或顶层 **`params`**。

---

## PRD 1 — RPP

```json
{
  "username": "<USERNAME>",
  "url": "https://ad.rms.rakuten.co.jp/rpp/api/reports/search",
  "method": "POST",
  "headers": {
    "accept": "application/json, text/plain, */*",
    "accept-language": "ja",
    "content-type": "application/json",
    "origin": "https://ad.rms.rakuten.co.jp",
    "referer": "https://ad.rms.rakuten.co.jp/rpp/reports",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin"
  },
  "req_data": {
    "page": 1,
    "selectionType": 1,
    "periodType": 2,
    "startDate": "2026-03-01",
    "endDate": "2026-03-07",
    "reportFilter": 1,
    "campaignType": "1",
    "rankType": 1,
    "allUsers": true,
    "newUsers": true,
    "existingUsers": true,
    "noOfClicks": true,
    "adsalesBefore": true,
    "cpc": true,
    "h12": true,
    "h720": true,
    "gms": true,
    "roas": true,
    "cv": true,
    "cvr": true,
    "cpa": true
  }
}
```

---

## PRD 2 — RPP-EXP

```json
{
  "username": "<USERNAME>",
  "url": "https://ad.rms.rakuten.co.jp/rppexp/api/core/report",
  "method": "POST",
  "headers": {
    "accept": "application/json, text/plain, */*",
    "accept-language": "ja",
    "content-type": "application/json",
    "referer": "https://ad.rms.rakuten.co.jp/rppexp/reports/",
    "page-id": "",
    "page-name": "rppexp_reports_",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-shop-url": "pettena-collections"
  },
  "req_data": {
    "pageNo": 1,
    "aggregationUnit": 1,
    "aggregationPeriod": 3,
    "campaignSearchType": 1,
    "productSearchType": 1,
    "productRanking": 1,
    "allUser": true,
    "newCustomer": true,
    "existingCustomer": true,
    "impression": true,
    "clicks": true,
    "amountSpent": true,
    "cpc": true,
    "ctr": true,
    "h720": true,
    "gms": true,
    "roas": true,
    "cv": true,
    "cvr": true,
    "cpa": true,
    "aov": true,
    "startDate": "2026-03-01",
    "endDate": "2026-03-05",
    "pageSize": 30
  }
}
```

### PRD 2 补 — RPP-EXP merchant（当前店铺信息 / `shopUrl`）

RMS 前端在加载 RPP-EXP 时会请求此接口；**无需** `x-shop-url`。成功时 `code` 为 `RPPEXP-CORE-API-S000`，`result` 含：

#### 与 `x-shop-url` 的关系（如何拿到报表用的 slug）

- **报表侧**：PRD 2（RPP-EXP `…/report`）与 PRD 6（TDA-EXP `…/report`）的请求头里需要 **`x-shop-url: <店铺 slug>`**（与乐天市場店铺 URL 中 `https://www.rakuten.co.jp/<slug>/` 的 `<slug>` 一致）。
- **本接口的作用**：`GET …/rppexp/api/core/merchant` **不**带 `x-shop-url`；响应里的 **`result.shopUrl` 就是上述 slug**。先调 merchant，再把 `shopUrl` 填入 PRD 2 / PRD 6 代理 JSON 的 **`headers["x-shop-url"]`**（或与 ziniao preset 的 **`-V shop_url=`** 同源）。
- **推荐顺序**：`merchant`（取 `shopUrl`）→ 再调 `rpp-exp` / `tda-exp` 报表接口，避免 slug 写错或多店会话不一致。
- **ziniao CLI**：`ziniao rakuten rpp-exp-merchant`（或 `network fetch -p rakuten/rpp-exp-merchant`）→ 从返回 JSON 的 **`result.shopUrl`** 读出后，传给 `ziniao rakuten rpp-exp-report -V shop_url=…` / `tda-exp-report -V shop_url=…`。

| 字段 | 说明 |
|------|------|
| `merchantName` | 店铺表示名 |
| `shopId` | 店铺 ID |
| `shopUrl` | 店铺 URL slug（与 `rpp-exp-report` / `tda-exp-report` 的 `-V shop_url=` 一致） |
| `customerId` | 与 `shopId` 同型会话字段 |
| `inactiveTime` | 非活跃时间等 |
| `shopStatus` | 店铺状态 |
| `rsFlag` | 标志位 |

Giikin 代理示例（GET、无 body）：

```json
{
  "username": "<USERNAME>",
  "url": "https://ad.rms.rakuten.co.jp/rppexp/api/core/merchant",
  "method": "GET",
  "headers": {
    "accept": "application/json, text/plain, */*",
    "accept-language": "ja",
    "referer": "https://ad.rms.rakuten.co.jp/rppexp/reports/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin"
  }
}
```

---

## PRD 3 — CPA

```json
{
  "username": "<USERNAME>",
  "url": "https://ad.rms.rakuten.co.jp/cpa/api/reports/search?page=1&periodType=2&startDate=2026-03-01&endDate=2026-03-05",
  "method": "GET",
  "headers": {
    "accept": "application/json, text/plain, */*",
    "accept-language": "ja",
    "referer": "https://ad.rms.rakuten.co.jp/cpa/reports",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin"
  }
}
```

---

## PRD 4 — 運用型クーポン

```json
{
  "username": "<USERNAME>",
  "url": "https://ad.rms.rakuten.co.jp/cpnadv/performance_reports/retrieve",
  "method": "POST",
  "headers": {
    "accept": "application/json",
    "accept-language": "ja",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "priority": "u=1, i",
    "sec-ch-ua": "\"Chromium\";v=\"142\", \"Google Chrome\";v=\"142\", \"Not_A Brand\";v=\"99\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "referer": "https://ad.rms.rakuten.co.jp/cpnadv/performance_reports",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
  },
  "req_data": {
    "selectionType": "1",
    "periodType": "2",
    "searchStartDate": "2026-03-01",
    "searchEndDate": "2026-03-29",
    "templateDiv": "101",
    "displayStatuses": "true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true",
    "page": "0"
  }
}
```

---

## PRD 5 — TDA

```json
{
  "username": "<USERNAME>",
  "url": "https://ad.rms.rakuten.co.jp/tda/api/aggregator/v2/reports/search?page=1&campaignType=1&selectionType=1&periodType=3&reportStartDate=2026-03-01&reportEndDate=2026-03-05",
  "method": "GET",
  "headers": {
    "accept": "application/json, text/plain, */*",
    "accept-language": "ja",
    "referer": "https://ad.rms.rakuten.co.jp/tda/performanceReport",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin"
  }
}
```

---

## PRD 6 — TDA-EXP

```json
{
  "username": "<USERNAME>",
  "url": "https://ad.rms.rakuten.co.jp/tdaexp/api/tdaexp-core/report",
  "method": "POST",
  "headers": {
    "accept": "application/json, text/plain, */*",
    "accept-language": "ja",
    "content-type": "application/json",
    "referer": "https://ad.rms.rakuten.co.jp/tdaexp/reports/",
    "page-id": "",
    "page-name": "tdaexp_reports_",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-shop-url": "pettena-collections"
  },
  "req_data": {
    "pageNo": 1,
    "aggregationUnit": 1,
    "aggregationPeriod": 3,
    "startDate": "2026-03-01",
    "endDate": "2026-03-05",
    "pageSize": 30
  }
}
```

---

## PRD 7 — メルマガ

```json
{
  "username": "<USERNAME>",
  "url": "https://auto-rmail.rms.rakuten.co.jp/reports",
  "method": "GET",
  "headers": {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "ja",
    "referer": "https://mainmenu.rms.rakuten.co.jp/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-site",
    "upgrade-insecure-requests": "1"
  }
}
```

---

## PRD 8 — DEAL CSV

```json
{
  "username": "<USERNAME>",
  "url": "https://datatool.rms.rakuten.co.jp/datadownload/get-csv/campaign?startDate=20260301&endDate=20260331&period=daily",
  "method": "GET",
  "headers": {
    "accept": "*/*",
    "accept-language": "ja",
    "referer": "https://datatool.rms.rakuten.co.jp/datadownload",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin"
  }
}
```

---

## PRD 9 — 広告購入履歴明細

```json
{
  "username": "<USERNAME>",
  "url": "https://ad.rms.rakuten.co.jp/shared/api/purchase_detail?targetMonth=2026-03&period=1&serviceTypeEcFlag=true&serviceTypeGrpOrExFlag=true&serviceTypeRppFlag=false&serviceTypeRppExpFlag=false&serviceTypeCpaFlag=false&serviceTypeCaFlag=false&serviceTypeTdaFlag=false&serviceTypeTdaExpFlag=false&agreementYesFlag=false&agreementNoFlag=false",
  "method": "GET",
  "headers": {
    "accept": "application/json, text/plain, */*",
    "accept-language": "ja",
    "referer": "https://ad.rms.rakuten.co.jp/shared/purchase_detail?selectedDate=2026-03&selectedMonths=1&selectedServices=EC%2CGRP_OR_EX&page=1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin"
  }
}
```

---

## PRD 10 — 超级联盟 pending

```json
{
  "username": "<USERNAME>",
  "url": "https://afl.rms.rakuten.co.jp/api/report/pending?order=asc&offset=0&limit=100&date=2026-03",
  "method": "GET",
  "headers": {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "ja",
    "content-type": "application/json",
    "referer": "https://afl.rms.rakuten.co.jp/report/pending-daily?date=2026-03",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-requested-with": "XMLHttpRequest"
  }
}
```
