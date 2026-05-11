# راهنمای Proxy در مرورگر و GitHub Actions

این نسخه دو قابلیت جدید دارد:

1. workflow شماره ۴ می‌تواند مرورگر Playwright را با proxy اجرا کند.
2. workflow شماره ۵ می‌تواند از چند منبع proxy رایگان، proxy جمع کند، آن‌ها را از داخل GitHub Actions تست کند، سریع‌ترین‌ها را انتخاب کند و در `proxy-list.md` و `proxy-list.json` ذخیره کند.

> نکته مهم: proxy رایگان برای تست خوب است، اما برای login، session حساس، حساب‌های اصلی، پرداخت، پنل مدیریت یا اطلاعات خصوصی مناسب نیست. ممکن است کند، ناپایدار، logگیر، آلوده یا از قبل توسط سایت‌ها blacklist شده باشد.

---

## فایل‌های اضافه‌شده

```text
.github/workflows/05-proxy-list.yml   # جمع‌آوری و تست proxy رایگان
scripts/proxy_collector.py            # اسکریپت تست و رتبه‌بندی proxy
proxy-list.md                         # جدول خواندنی proxyهای سریع‌تر
proxy-list.json                       # فایل ماشینی برای workflow شماره ۴
proxy-list.env                        # proxy اول/سریع‌ترین در قالب env
proxy-sources.example.txt             # نمونه فایل منبع‌های proxy
```

فایل‌های بروزرسانی‌شده:

```text
.github/workflows/04-browser.yml
scripts/browser_capture.py
requirements-browser.txt
```

---

## روش ۱: استفاده از proxy دستی در workflow شماره ۴

در تب **Actions**، workflow زیر را باز کنید:

```text
🌐 4-Browse the Web
```

برای proxy دستی این فیلدها را پر کنید:

| فیلد | مقدار نمونه | توضیح |
|---|---|---|
| `proxy_mode` | `manual` | فعال کردن proxy دستی |
| `proxy_server` | `http://1.2.3.4:8080` | آدرس proxy |
| `proxy_username` | خالی یا username | برای proxyهای دارای auth |
| `proxy_password` | خالی یا password | برای proxyهای دارای auth |

فرمت‌های قابل قبول:

```text
http://IP:PORT
https://IP:PORT
socks4://IP:PORT
socks5://IP:PORT
IP:PORT
http://username:password@IP:PORT
socks5://username:password@IP:PORT
```

اگر فقط `IP:PORT` بدهید، سیستم آن را `http://IP:PORT` فرض می‌کند.

### استفاده امن‌تر با GitHub Secrets

برای proxyهای پولی یا proxyهایی که username/password دارند، بهتر است اطلاعات را در **Settings → Secrets and variables → Actions** بگذارید:

```text
PROXY_SERVER
PROXY_USERNAME
PROXY_PASSWORD
```

بعد در workflow شماره ۴ فقط این را بگذارید:

```text
proxy_mode = manual
proxy_server = خالی
proxy_username = خالی
proxy_password = خالی
```

اسکریپت اگر inputها خالی باشند، از secretها استفاده می‌کند.

---

## روش ۲: ساخت خودکار `proxy-list.md` از proxyهای رایگان

در تب **Actions** workflow زیر را اجرا کنید:

```text
🧭 5-Collect Free Proxies
```

فیلدهای مهم:

| فیلد | پیش‌فرض | توضیح |
|---|---:|---|
| `count` | `10` | چند proxy سریع ذخیره شود. مثلا `10` یعنی ۱۰ proxy سریع‌تر. |
| `protocol` | `http` | نوع proxy: `http`، `https`، `socks4`، `socks5` یا `all`. |
| `test_url` | `https://api.ipify.org?format=json` | URL تست سرعت و سالم بودن proxy. |
| `timeout_seconds` | `8` | حداکثر زمان انتظار برای هر proxy. |
| `concurrency` | `80` | تعداد تست موازی. |
| `max_candidates` | `1200` | حداکثر candidateهایی که تست می‌شوند. |
| `sources_file` | خالی | فایل منبع اختصاصی. مثلا `proxy-sources.example.txt`. |

بعد از اجرا، این فایل‌ها commit می‌شوند:

```text
proxy-list.md
proxy-list.json
proxy-list.env
```

`proxy-list.md` جدولی شبیه این می‌سازد:

```text
| Rank | PROXY_SERVER | PROXY_USERNAME | PROXY_PASSWORD | ping_ms | protocol | status | observed_ip | source |
```

`ping_ms` زمان رفت‌وبرگشت یک درخواست واقعی HTTP/HTTPS از داخل GitHub Actions از مسیر همان proxy است. این عدد ICMP ping نیست؛ برای کار مرورگر و scraper معمولاً همین معیار مفیدتر است.

---

## استفاده از proxyهای ساخته‌شده در workflow شماره ۴

بعد از اجرای workflow شماره ۵، workflow شماره ۴ را اجرا کنید و یکی از حالت‌های زیر را انتخاب کنید.

### سریع‌ترین proxy فایل

```text
proxy_mode = fastest-from-file
proxy_list_file = proxy-list.json
```

این حالت ردیف اول، یعنی سریع‌ترین proxy، را استفاده می‌کند.

### انتخاب ردیف خاص از جدول

```text
proxy_mode = rank-from-file
proxy_list_file = proxy-list.json
proxy_list_rank = 3
```

این مثال ردیف سوم `proxy-list.json` را استفاده می‌کند.

### انتخاب تصادفی از لیست

```text
proxy_mode = random-from-file
proxy_list_file = proxy-list.json
```

این حالت هر بار یکی از proxyهای موجود در فایل را انتخاب می‌کند.

---

## پیشنهاد برای سایت‌هایی که GitHub را block می‌کنند

در workflow شماره ۵، مقدار `test_url` را بهتر است نزدیک به همان سایت هدف بگذارید. مثلا اگر سایت `example.com` روی IPهای GitHub حساس است، workflow شماره ۵ را این‌طور اجرا کنید:

```text
test_url = https://example.com/
protocol = http
count = 10
```

با این کار proxyهایی انتخاب می‌شوند که حداقل از داخل GitHub Actions توانسته‌اند به همان سایت یا همان مسیر تست برسند. سپس در workflow شماره ۴ از `fastest-from-file` یا `rank-from-file` استفاده کنید.

---

## منبع‌های proxy

به‌صورت پیش‌فرض اسکریپت از چند endpoint عمومی استفاده می‌کند. برای کنترل کامل‌تر، یک فایل مثل `proxy-sources.example.txt` بسازید یا همان فایل نمونه را ویرایش کنید و در workflow شماره ۵ در فیلد `sources_file` مقدار زیر را بدهید:

```text
proxy-sources.example.txt
```

فرمت فایل source:

```text
http https://example.com/http.txt
socks5 https://example.com/socks5.txt
auto https://example.com/mixed-list.txt
```

یا:

```text
http,https://example.com/http.txt
```

اگر protocol را ننویسید، parser تلاش می‌کند protocol را از خود محتوا تشخیص بدهد. اگر محتوا فقط `IP:PORT` باشد، معمولاً `http` فرض می‌شود.

---

## خطاهای رایج

### `proxy list is empty`

یعنی قبل از اجرای workflow شماره ۴، workflow شماره ۵ را اجرا نکرده‌اید یا هیچ proxy سالمی پیدا نشده است.

راه‌حل‌ها:

```text
count = 10
protocol = all
timeout_seconds = 12
max_candidates = 3000
```

### سایت با proxy باز هم block می‌کند

proxy رایگان ممکن است از قبل blacklist شده باشد. این حالت طبیعی است. چند کار کمک می‌کند:

```text
proxy_mode = rank-from-file
proxy_list_rank = 2 یا 3 یا 4
```

یا workflow شماره ۵ را دوباره اجرا کنید. برای سایت‌های سخت‌گیر، proxy دیتاسنتری ارزان یا residential معتبر معمولاً نتیجه بهتری دارد.

### اطلاعات حساس در network log

اگر login یا cookie مهم دارید:

```text
redact_sensitive = true
persist_session = false
```

اگر session لازم دارید، repository را private نگه دارید.

---

## خلاصه استفاده سریع

اول proxy بسازید:

```text
Actions → 🧭 5-Collect Free Proxies → Run workflow
count = 10
protocol = http
test_url = https://site-target.com/
```

بعد مرورگر را با proxy اجرا کنید:

```text
Actions → 🌐 4-Browse the Web → Run workflow
url = https://site-target.com/
proxy_mode = fastest-from-file
proxy_list_file = proxy-list.json
```
