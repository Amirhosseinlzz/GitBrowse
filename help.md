# راهنمای GitHub Actions این مخزن

این فایل برای هر **Workflow** توضیح می‌دهد برای چه کاری است و چطور از آن استفاده کنید.

## قبل از شروع (مشترک)

1. مخزن را **Fork** کنید (یا روی مخزنی که دسترسی دارید **Actions** را فعال کنید).
2. در GitHub به مسیر **Actions** بروید.
3. از ستون چپ نام workflow را انتخاب کنید.
4. دکمه **Run workflow** را بزنید، ورودی‌ها را پر کنید و **Run workflow** را تأیید کنید.
5. برای دیدن لاگ و خروجی، روی همان اجرا (run) کلیک کنید؛ در صورت وجود، **Artifacts** را از پایین صفحهٔ اجرا دانلود کنید.

برای مرورگر، پروکسی و JSON اتوماسیون، [مستندات `docs/`](docs/) را هم ببینید:

| فایل | موضوع |
|------|--------|
| [docs/proxy-setup.md](docs/proxy-setup.md) | پروکسی در Actions و ارتباط با `proxy-list.json` |
| [docs/browser-automation.md](docs/browser-automation.md) | قابلیت‌های capture، session، شبکه |
| [docs/browser-json-reference.md](docs/browser-json-reference.md) | ساختار `automation` و `popup_rules` |

نمونه JSON: [browser-configs/automation.example.json](browser-configs/automation.example.json) و [browser-configs/popup-rules.example.json](browser-configs/popup-rules.example.json).

---

## ۱. ⬇️ Download from url

**فایل workflow:** [`.github/workflows/downloader.yaml`](.github/workflows/downloader.yaml)

### برای چه کاری است؟

دانلود یک یا چند فایل از اینترنت **روی runner گیتهاب** (یعنی از شبکه‌ای که GitHub دارد، نه از IP خانهٔ شما) و ذخیرهٔ نتیجه در پوشهٔ `downloads/` داخل همین مخزن، همراه با `README.md` توضیحی در هر پوشه و به‌روزرسانی فهرست در `downloads/README.md`. در صورت نیاز، فایل‌های بزرگ به چند بخش ZIP تقسیم می‌شوند (حد تقسیم حدود ۹۰ مگابایت). برای دانلود از `aria2c` استفاده می‌شود و در صورت شکست، **curl** امتحان می‌شود.

> توجه: این workflow می‌تواند بخشی با عنوان «فایل های دانلود شده در گیتهاب شما» را به **README.md ریشهٔ مخزن** اضافه کند. اگر README شما را دستی ویرایش کرده‌اید، بعد از اجرا خروجی git را بررسی کنید.

### چطور استفاده می‌شود؟

| ورودی | توضیح |
|--------|--------|
| **urls** | اجباری. یک یا چند آدرس با **فاصله** از هم جدا شده‌اند (نه کاما). مثال: `https://example.com/a.zip https://example.com/b.iso` |
| **mode** | `normal`: هر فایل جداگانه در زیرپوشهٔ خودش ZIP می‌شود (یا در صورت حجم بالا، چندپارچه). `zip`: همهٔ فایل‌های موفق در **یک** آرشیو با نام زمانی قرار می‌گیرند. |
| **password** | اختیاری. اگر پر باشد، ZIP با رمز ساخته می‌شود (`zip -P`). |

**نکات:**

- نام فایل از `basename` URL گرفته می‌شود؛ کاراکترهای نامعتبر در نام فایل sanitize می‌شوند.
- اگر دانلود شکست بخورد، در `downloads/<نام‌پوشه>/README.md` گزارش خطا ساخته می‌شود.
- commitها به صورت **دسته‌های ۵تایی** فایل push می‌شوند تا محدودیت‌های حجمی راحت‌تر رعایت شود.

---

## ۲. 🌐 Browse the Web

**فایل workflow:** [`.github/workflows/browser.yml`](.github/workflows/browser.yml)

### برای چه کاری است؟

باز کردن یک **URL** با مرورگر واقعی (**Chromium + Playwright + Python**) روی سرور GitHub، اجرای اتوماسیون اختیاری، هندل پاپ‌آپ/کوکی، ذخیرهٔ **نسخهٔ آفلاین** صفحه، لاگ شبکه، و در صورت تنظیم، اتصال از طریق **پروکسی**. خروجی معمولاً در `pages/`، `browse.md` و در صورت فعال بودن `sessions/` commit می‌شود؛ علاوه بر آن **Artifact** و در صورت نیاز ZIP یا ZIPهای تقسیم‌شده (حد حدود ۵۰ مگابایت برای هر بخش) ساخته می‌شود.

### چطور استفاده می‌شود؟

| ورودی | پیش‌فرض / نوع | توضیح |
|--------|----------------|--------|
| **url** | اجباری | آدرس صفحه‌ای که باید باز شود. |
| **automation** | `[]` | آرایهٔ JSON مراحل (کلیک، wait، fill، …). نمونه در `browser-configs/automation.example.json`. |
| **popup_rules** | `[]` | قوانین JSON برای کوکی/سن/مودال؛ نمونه در `browser-configs/popup-rules.example.json`. |
| **session_key** | خالی | نام فایل نشست؛ اگر خالی باشد از دامنه ساخته می‌شود (`sessions/<domain>.json`). |
| **wait_after_load** | `2` | ثانیهٔ انتظار بعد از بارگذاری و بعد از اتوماسیون قبل از capture. |
| **auto_scroll** | `true` | اسکرول برای بارگذاری تنبل. |
| **persist_session** | `true` | ذخیره/بازاستفادهٔ کوکی و storage در مخزن. برای مخزن عمومی با احتیاط. |
| **save_response_bodies** | `true` | ذخیرهٔ بدنهٔ پاسخ درخواست‌های متنی (Ajax و …). |
| **max_response_body_mb** | `2` | سقف حجم هر بدنهٔ ذخیره‌شده. |
| **max_asset_size_mb** | `25` | سقف هر داراییٔ آفلاین. |
| **include_videos** | `false` | دانلود ویدیوها (معمولاً خاموش بماند). |
| **redact_sensitive** | `false` | مخفی کردن هدرهای حساس در لاگ شبکه. |
| **proxy_mode** | `none` | یکی از: `none`, `manual`, `fastest-from-file`, `rank-from-file`, `random-from-file`. |
| **proxy_server** | خالی | برای `manual`: مثل `http://IP:PORT` یا `socks5://…`. خالی + manual → استفاده از secret `PROXY_SERVER`. |
| **proxy_username** / **proxy_password** | خالی | ترجیحاً از Secrets `PROXY_USERNAME` و `PROXY_PASSWORD` استفاده کنید. |
| **proxy_list_file** | `proxy-list.json` | فایل لیست پروکسی (خروجی workflow جمع‌آوری پروکسی). |
| **proxy_list_rank** | `1` | وقتی `rank-from-file`: رتبهٔ پروکسی در فایل JSON. |
| **proxy_allow_direct_fallback** | `false` | اگر پروکسی کار نکرد، بدون پروکسی ادامه دهد یا خیر. |

جزئیات پروکسی و امنیت در [docs/proxy-setup.md](docs/proxy-setup.md) و [docs/browser-automation.md](docs/browser-automation.md) آمده است.

---

## ۳. 🧭 Collect Free Proxies

**فایل workflow:** [`.github/workflows/proxy-list.yml`](.github/workflows/proxy-list.yml)

### برای چه کاری است؟

جمع‌آوری کاندید پروکسی از منابع **رایگان**، تست موازی، انتخاب سریع‌ترین‌ها و ذخیره در:

- `proxy-list.md` (جدول خوانا، در خلاصهٔ اجرا هم کپی می‌شود)،
- `proxy-list.json` (برای workflow مرورگر)،
- `proxy-list.env`.

### چطور استفاده می‌شود؟

| ورودی | پیش‌فرض | توضیح |
|--------|---------|--------|
| **count** | `10` | چند پروکسی برتر ذخیره شود. |
| **protocol** | `http` | `http`, `https`, `socks4`, `socks5`, یا `all`. |
| **test_url** | ipify | URLای که برای تست زمان پاسخ/کارکرد استفاده می‌شود؛ برای سایت خاص، همان URL را بگذارید. |
| **timeout_seconds** | `8` | تایم‌اوت هر درخواست تست. |
| **concurrency** | `80` | تعداد تست همزمان. |
| **max_candidates** | `1200` | حداکثر کاندید قبل از تست. |
| **sources_file** | خالی | مسیر فایل منبع سفارشی؛ خالی = منابع داخلی. مثال: `proxy-sources.example.txt`. |

بعد از موفقیت، می‌توانید در **Browse the Web** مثلاً `proxy_mode` را `fastest-from-file` بگذارید و `proxy_list_file` را `proxy-list.json` نگه دارید.

---

## ۴. 🗑 Clean generated folders

**فایل workflow:** [`.github/workflows/cleaner.yml`](.github/workflows/cleaner.yml)

### برای چه کاری است؟

**حذف دائمی** داده‌های تولیدشدهٔ زیر و ایجاد دوبارهٔ پوشه‌های خالی:

- `downloads/`
- `pages/`
- `sessions/`
- فایل `browse.md`

برای سبک کردن مخزن یا شروع تمیز قبل از capture یا دانلود جدید.

### چطور استفاده می‌شود؟

| ورودی | توضیح |
|--------|--------|
| **warning** | فقط یادآوری متنی؛ محتوایش روی منطق اجرا اثر ندارد. قبل از اجرا حتماً بدانید که **پوشش‌ها و browse.md پاک می‌شوند**. |

Workflow را اجرا کنید؛ در پایان در صورت تغییر، commit با پیام مربوط به AVASAM push می‌شود.

---

## ترتیب پیشنهادی (سناریوهای رایج)

| هدف | ترتیب پیشنهادی |
|-----|----------------|
| فقط ذخیرهٔ صفحهٔ وب به صورت آفلاین | **Browse the Web** → در صورت پر شدن مخزن، **Clean** |
| دانلود فایل بزرگ/چند فایل از لینک مستقیم | **Download from url** |
| مرور سایت‌هایی که از IP GitHub باز می‌شوند ولی از ایران نه | همان **Browse**؛ در صورت نیاز **Collect Free Proxies** سپس **Browse** با `proxy_mode` مناسب |
| خالی کردن همهٔ خروجی‌های تولیدی | **Clean generated folders** |

اگر نکته‌ای در workflowها عوض شد، اول فایل YAML همان workflow را مرجع قرار دهید؛ این `help.md` خلاصهٔ رفتار فعلی است.
