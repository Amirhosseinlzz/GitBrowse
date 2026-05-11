# راهنمای مرورگر پیشرفته در GitHub Actions

این پروژه از این به بعد برای workflow شماره ۴ به‌جای `curl/grep` و اسکریپت inline، از یک مرورگر واقعی Chromium با **Python + Playwright** استفاده می‌کند. دلیل انتخاب Playwright این است که در GitHub Actions به‌خوبی اجرا می‌شود و برای کارهایی مثل ذخیره session، اجرای کلیک/انتظار/فرم، کنترل pop-up، ثبت network/Ajax و گرفتن snapshot آفلاین، API مستقیم‌تر و پایدارتر از Selenium دارد.

فایل اصلی workflow:

```text
.github/workflows/04-browser.yml
```

اسکریپت اصلی مرورگر:

```text
scripts/browser_capture.py
```

وابستگی‌ها:

```text
requirements-browser.txt
```

---

## قابلیت‌هایی که اضافه شده است

### 1. هندل کردن pop-up کوکی، تایید سن، confirm و modal

اسکریپت چند قانون پیش‌فرض برای دکمه‌هایی مثل `Accept`, `Accept all`, `I agree`, `Continue`, `Enter`, `I am 18`, `قبول`, `تایید`, `ادامه`, `ورود`, `بله` و modalهای رایج کوکی دارد. علاوه بر آن می‌توانید قانون‌های اختصاصی خودتان را با JSON به workflow بدهید.

### 2. ساخت نسخه آفلاین از صفحه

برای هر اجرا، خروجی‌های آفلاین زیر ساخته می‌شود:

```text
pages/<domain>/<slug>/<timestamp>/offline/index.html
pages/<domain>/<slug>/<timestamp>/offline/page.mhtml
pages/<domain>/<slug>/<timestamp>/offline/assets/
```

`offline/index.html` نسخه بازنویسی‌شده HTML است که فایل‌های CSS، JS، عکس، icon، font و assetهای لازم را در پوشه `assets` ذخیره می‌کند. ویدیوها به‌صورت پیش‌فرض دانلود نمی‌شوند.

`offline/page.mhtml` یک snapshot مرورگری است که در Chrome/Chromium راحت‌تر باز می‌شود و گاهی برای صفحات پیچیده از `index.html` دقیق‌تر است.

### 3. اجرای automation شبیه Selenium

می‌توانید قبل از ذخیره صفحه، چند مرحله اجرا کنید؛ مثل کلیک، پر کردن input، زدن کلید Enter، صبر کردن، scroll، اجرای JavaScript یا گرفتن screenshot بین مراحل.

نمونه:

```json
[
  {"action":"click","selector":"button.load-more","timeout":10000},
  {"action":"wait","ms":2000},
  {"action":"click","text":"More results","timeout":10000},
  {"action":"wait_for_load_state","state":"networkidle","timeout":15000}
]
```

### 4. ذخیره و استفاده دوباره از session/cookie

اگر `persist_session` روشن باشد، کوکی‌ها، localStorage و sessionStorage در این مسیر ذخیره می‌شوند:

```text
sessions/<session_key>.json
```

اگر `session_key` خالی باشد، نام session از domain ساخته می‌شود. اجرای بعدی workflow برای همان domain یا همان `session_key` از این فایل استفاده می‌کند.

> هشدار امنیتی: فایل session می‌تواند شامل کوکی لاگین، token و داده‌های حساس باشد. اگر repository عمومی است، `persist_session=false` بگذارید یا repository را private کنید. اگر می‌خواهید network log حساسیت کمتری داشته باشد، `redact_sensitive=true` را فعال کنید.

### 5. ثبت کامل Network / Ajax

برای هر اجرا، تمام requestها و responseها در این مسیر ذخیره می‌شود:

```text
pages/<domain>/<slug>/<timestamp>/network/
```

فایل‌های مهم:

```text
network/network.md       # خلاصه قابل خواندن
network/network.json     # جزئیات کامل
network/network.jsonl    # هر request در یک خط JSON
network/bodies/          # body پاسخ‌های متنی مثل Ajax/JSON/HTML/CSS/JS
```

موارد ثبت‌شده شامل method، URL، resource type، headers، post data، status، response headers، خطاها، timing/sizes در صورت دسترس بودن و body پاسخ‌های متنی است. برای جلوگیری از بزرگ شدن repository، فایل‌های body متنی به‌صورت پیش‌فرض تا ۲ مگابایت ذخیره می‌شوند.

---

## نحوه اجرا از GitHub Actions

1. وارد repository فورک‌شده خودتان شوید.
2. به تب **Actions** بروید.
3. workflow با نام **🌐 4-Browse the Web** را انتخاب کنید.
4. روی **Run workflow** بزنید.
5. فیلد `url` را پر کنید.
6. در صورت نیاز فیلدهای `automation` و `popup_rules` را با JSON پر کنید.
7. روی **Run workflow** بزنید.

خروجی هم داخل repository commit می‌شود و هم به‌صورت artifact در همان run قابل دانلود است.

---

## فیلدهای workflow

| فیلد | پیش‌فرض | توضیح |
|---|---:|---|
| `url` | اجباری | آدرس صفحه‌ای که باید باز شود. اگر `https://` ننویسید، خودکار اضافه می‌شود. |
| `automation` | `[]` | آرایه JSON از مراحل automation. |
| `popup_rules` | `[]` | قانون‌های اختصاصی برای popupها. قبل از قانون‌های پیش‌فرض اجرا می‌شود. |
| `session_key` | خالی | نام فایل session. اگر خالی باشد، از domain استفاده می‌شود. |
| `wait_after_load` | `2` | چند ثانیه بعد از load و automation صبر کند. |
| `auto_scroll` | `true` | صفحه را scroll می‌کند تا lazy-load و Ajaxهای وابسته به scroll اجرا شوند. |
| `persist_session` | `true` | session/cookie/localStorage را در `sessions/` ذخیره و در اجرای بعدی استفاده کند. |
| `save_response_bodies` | `true` | body پاسخ‌های متنی network را ذخیره کند. |
| `max_response_body_mb` | `2` | سقف ذخیره body هر response متنی. |
| `max_asset_size_mb` | `25` | سقف دانلود هر asset آفلاین. |
| `include_videos` | `false` | ویدیوها را هم به‌عنوان asset آفلاین دانلود کند. معمولاً خاموش بماند. |
| `redact_sensitive` | `false` | headerهای حساس مثل Cookie/Authorization را در network log مخفی کند. |

---

## ساختار خروجی هر اجرا

نمونه مسیر:

```text
pages/example.com/https_example.com_path/20260506_174455/
```

داخل هر پوشه:

```text
index.md                         # گزارش اصلی اجرا
metadata.json                    # تنظیمات و آمار اجرا
automation-log.json              # pop-upها، dialogها، دانلودها و مراحل automation
screenshot.png                   # screenshot کامل صفحه
source/final_dom.html            # DOM نهایی بعد از automation
source/visible_text.txt          # متن قابل مشاهده صفحه
source/all_links.txt             # همه لینک‌های DOM
source/media_links.txt           # لینک‌های media/document در DOM
offline/index.html               # نسخه آفلاین HTML
offline/page.mhtml               # snapshot آفلاین مرورگر
offline/assets/                  # assetهای محلی آفلاین
offline/assets.md                # گزارش assetها
network/network.md               # گزارش خواندنی network
network/network.json             # گزارش کامل network
network/network.jsonl            # گزارش خطی network
network/bodies/                  # response bodyهای متنی
```

همچنین در کنار همان پوشه، فایل zip ساخته می‌شود:

```text
pages/<domain>/<slug>/<timestamp>.zip
```

---

## قانون اختصاصی برای pop-upها

اگر popup سایت با قانون‌های پیش‌فرض بسته نشد، در ورودی `popup_rules` یک JSON بدهید.

### کلیک با CSS selector

```json
[
  {"name":"custom age confirm","selector":"button.age-confirm","timeout":5000}
]
```

### کلیک روی متن

```json
[
  {"name":"persian accept","text":"من بالای ۱۸ سال هستم","timeout":5000}
]
```

### کلیک روی role/button با regex

```json
[
  {
    "name":"accept by regex",
    "role":"button",
    "name_regex":"^(Accept|I agree|Enter|Continue|تایید|قبول)$",
    "timeout":5000
  }
]
```

### popup داخل iframe

```json
[
  {
    "name":"iframe consent",
    "frame_url_contains":"consent",
    "selector":"button:has-text('Accept')",
    "timeout":8000
  }
]
```

قانون‌ها از بالا به پایین اجرا می‌شوند. قانون‌های شما قبل از قانون‌های داخلی اجرا می‌شوند.

---

## مراحل automation قابل استفاده

### click

```json
{"action":"click","selector":"button.load-more","timeout":10000}
```

با متن:

```json
{"action":"click","text":"Load more","timeout":10000}
```

با role:

```json
{"action":"click","role":"button","name":"Search","timeout":10000}
```

### fill

```json
{"action":"fill","selector":"input[name='q']","value":"test search"}
```

### press

```json
{"action":"press","selector":"input[name='q']","key":"Enter"}
```

### wait

```json
{"action":"wait","ms":3000}
```

### wait_for_selector

```json
{"action":"wait_for_selector","selector":".results","state":"visible","timeout":15000}
```

`state` می‌تواند `attached`, `detached`, `visible`, یا `hidden` باشد.

### wait_for_load_state

```json
{"action":"wait_for_load_state","state":"networkidle","timeout":15000}
```

### scroll

```json
{"action":"scroll","y":1200}
```

یا scroll تا یک المنت خاص:

```json
{"action":"scroll","selector":"#comments"}
```

### scroll_to_bottom

```json
{"action":"scroll_to_bottom","max_scrolls":20}
```

### screenshot بین مراحل

```json
{"action":"screenshot","name":"after-login.png","full_page":true}
```

### evaluate برای اجرای JavaScript

```json
{"action":"evaluate","script":"() => window.scrollTo(0, document.body.scrollHeight)"}
```

### goto

```json
{"action":"goto","url":"https://example.com/account","wait_until":"domcontentloaded","timeout":60000}
```

---

## نمونه‌های آماده

### نمونه ۱: قبول cookie و کلیک روی Load more

`automation`:

```json
[
  {"action":"click","selector":"button.load-more","timeout":10000,"continue_on_error":true},
  {"action":"wait","ms":2000},
  {"action":"scroll_to_bottom","max_scrolls":12}
]
```

`popup_rules`:

```json
[
  {"name":"site cookie","selector":"button:has-text('Accept all')","timeout":5000}
]
```

### نمونه ۲: جستجو در سایت و ذخیره نتیجه

`automation`:

```json
[
  {"action":"fill","selector":"input[type='search']","value":"playwright"},
  {"action":"press","selector":"input[type='search']","key":"Enter"},
  {"action":"wait_for_load_state","state":"networkidle","timeout":15000},
  {"action":"screenshot","name":"search-result.png"}
]
```

### نمونه ۳: استفاده از session ثابت برای چند اجرای پشت سر هم

در اجرای اول:

```text
session_key = my_site_login
persist_session = true
```

بعد از اینکه automation شما وارد سایت شد، فایل زیر commit می‌شود:

```text
sessions/my_site_login.json
```

در اجرای بعدی همان `session_key` را وارد کنید تا session قبلی استفاده شود.

---

## اجرای local روی سیستم خودتان

اگر خواستید قبل از GitHub Actions محلی تست کنید:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-browser.txt
python -m playwright install --with-deps chromium
python scripts/browser_capture.py --url "https://example.com" --automation-json '[]'
```

برای Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-browser.txt
python -m playwright install chromium
python scripts/browser_capture.py --url "https://example.com" --automation-json "[]"
```

---

## تفاوت نسخه جدید با workflow قبلی

نسخه قبلی:

- HTML را با `curl` می‌گرفت؛ پس DOM ساخته‌شده با JavaScript را نمی‌دید.
- لینک‌ها را با `grep` استخراج می‌کرد؛ پس lazy-loaded image و Ajax را کامل نمی‌گرفت.
- pop-up، cookie banner، age gate و dialog را کنترل نمی‌کرد.
- session/cookie را ذخیره نمی‌کرد.
- network/Ajax را لاگ نمی‌کرد.
- نسخه آفلاین قابل اتکا نمی‌ساخت.

نسخه جدید:

- صفحه را با Chromium واقعی باز می‌کند.
- automation و pop-up handling دارد.
- session را بین اجراها نگه می‌دارد.
- network را مثل DevTools در قالب JSON/JSONL/Markdown ذخیره می‌کند.
- هم `MHTML` و هم `offline/index.html` می‌سازد.

---

## محدودیت‌ها و نکته‌ها

- بعضی سایت‌ها با anti-bot، CAPTCHA، geo-block یا نیاز به login انسانی جلوی اجرای headless را می‌گیرند.
- نسخه آفلاین HTML برای همه سایت‌ها ۱۰۰٪ شبیه مرور آنلاین نیست، چون بعضی JavaScriptها نیاز به server/API زنده دارند. برای همین `page.mhtml` هم ذخیره می‌شود.
- ویدیوها به‌صورت پیش‌فرض دانلود نمی‌شوند تا حجم repository زیاد نشود.
- اگر `network/bodies/` خیلی بزرگ شد، `save_response_bodies=false` یا `max_response_body_mb=0.2` بگذارید.
- اگر خروجی session یا network شامل اطلاعات حساس است، repository را private کنید یا `redact_sensitive=true` بگذارید.

---

## عیب‌یابی سریع

### popup بسته نمی‌شود

یک rule اختصاصی با selector دقیق بدهید:

```json
[
  {"selector":"#age-confirm-button","timeout":10000}
]
```

### عکس‌ها در نسخه آفلاین کم هستند

`auto_scroll=true` را روشن نگه دارید یا automation دستی برای scroll اضافه کنید:

```json
[
  {"action":"scroll_to_bottom","max_scrolls":30},
  {"action":"wait","ms":3000}
]
```

### Ajax بعد از کلیک لاگ نمی‌شود

بعد از click یک wait اضافه کنید:

```json
[
  {"action":"click","selector":"#load-comments"},
  {"action":"wait_for_load_state","state":"networkidle","timeout":15000},
  {"action":"wait","ms":2000}
]
```

### session استفاده نمی‌شود

- مطمئن شوید `persist_session=true` است.
- در اجرای دوم همان `session_key` را وارد کنید.
- بررسی کنید فایل `sessions/<session_key>.json` واقعاً commit شده باشد.
- بعضی کوکی‌ها خیلی زود expire می‌شوند یا به IP/UA وابسته هستند.

---

## اجرای مرورگر با Proxy

workflow شماره ۴ حالا ورودی‌های proxy دارد. برای توضیح کامل‌تر، فایل زیر را ببینید:

```text
docs/proxy-setup.md
```

فیلدهای جدید workflow شماره ۴:

| فیلد | پیش‌فرض | توضیح |
|---|---:|---|
| `proxy_mode` | `none` | حالت proxy: `none`، `manual`، `fastest-from-file`، `rank-from-file` یا `random-from-file`. |
| `proxy_server` | خالی | proxy دستی مثل `http://IP:PORT` یا `socks5://IP:PORT`. |
| `proxy_username` | خالی | username برای proxyهای دارای auth. برای اطلاعات حساس از GitHub Secrets استفاده کنید. |
| `proxy_password` | خالی | password برای proxyهای دارای auth. برای اطلاعات حساس از GitHub Secrets استفاده کنید. |
| `proxy_list_file` | `proxy-list.json` | فایل خروجی workflow شماره ۵. |
| `proxy_list_rank` | `1` | ردیف proxy هنگام استفاده از `rank-from-file`. |
| `proxy_allow_direct_fallback` | `false` | اگر proxy انتخاب‌شده مشکل داشت، بدون proxy ادامه بدهد. |

### proxy دستی

```text
proxy_mode = manual
proxy_server = http://1.2.3.4:8080
```

### proxy از لیست ساخته‌شده

اول workflow شماره ۵ را اجرا کنید تا `proxy-list.md` و `proxy-list.json` ساخته شود. بعد:

```text
proxy_mode = fastest-from-file
proxy_list_file = proxy-list.json
```

یا برای انتخاب ردیف سوم:

```text
proxy_mode = rank-from-file
proxy_list_rank = 3
```
