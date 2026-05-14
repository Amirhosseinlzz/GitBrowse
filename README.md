# GitBrowse

**English:** For the English version of this README and the workflows guide, see [docs/english.md](docs/english.md) — [README (English)](docs/english.md#readme-english) · [Workflows guide (English)](docs/english.md#repository-github-actions-guide-english).

**این پروژه و اسکریپت‌هایش تقدیم می‌شود به مردم شریف ایران.**

هدف ساخت این مخزن این بوده که هموطنانی که در شرایط محدودیت شبکه (از جمله **نت ملی** یا فیلترینگ) به اینترنت آزاد و منابع جهانی دسترسی مستقیم ندارند، بتوانند با اجرای مرورگر روی زیرساخت **GitHub Actions** (خارج از مرز شبکه محدود شما) صفحات وب را باز، ذخیره و به صورت **آرشیو آفلاین** (HTML، MHTML، دارایی‌ها و گزارش شبکه) در همان مخزن دریافت کنند؛ در کنار آن، امکان جمع‌آوری و تست **پروکسی** و اتصال مرورگر از طریق پروکسی برای رسیدن به سایت‌های هدف هم فراهم است.

> این ابزار یک «پل» بین شما و اینترنت از مسیر GitHub است؛ مسئولیت قانونی، اخلاقی و امنیتی استفاده صحیح از آن با خودتان است. برای ورود به حساس‌ها، پرداخت و داده خصوصی از پروکسی‌های ناشناس و مخزن عمومی استفاده نکنید.

این مخزن **فورک** و ادامهٔ کار بر پایهٔ پروژهٔ [nikzad-avasam/downloader](https://github.com/nikzad-avasam/downloader) است.

---

## فهرست GitHub Actions

| نام در GitHub Actions | فایل workflow | نقش کوتاه |
|------------------------|---------------|-----------|
| 🌐 Browse the Web | [`.github/workflows/browser.yml`](.github/workflows/browser.yml) | مرور واقعی صفحه، خروجی آفلاین، پروکسی، اتوماسیون |
| ⬇️ Download from url | [`.github/workflows/downloader.yaml`](.github/workflows/downloader.yaml) | دانلود فایل از URL به پوشهٔ `downloads/` |
| 🧭 Collect Free Proxies | [`.github/workflows/proxy-list.yml`](.github/workflows/proxy-list.yml) | جمع‌آوری و تست پروکسی رایگان → `proxy-list.json` |
| 🗑 Clean generated folders | [`.github/workflows/cleaner.yml`](.github/workflows/cleaner.yml) | پاک کردن `downloads/`، `pages/`، `sessions/` و `browse.md` |

راهنمای گام‌به‌گام هر workflow: [`help.md`](help.md).

---

## قابلیت‌ها (بر اساس GitHub Actions)

### [🌐 Browse the Web](.github/workflows/browser.yml)

اجرای **Chromium + Playwright** روی اوبونتو، بازدید از یک URL و ذخیره خروجی در مخزن:

| موضوع | توضیح کوتاه |
|--------|-------------|
| ورودی اصلی | آدرس صفحه (`url`) |
| اتوماسیون | JSON مراحل کلیک، پر کردن فرم، انتظار، اسکرول و … (`automation`) — نمونه: [`browser-configs/automation.example.json`](browser-configs/automation.example.json) |
| پاپ‌آپ / کوکی | قوانین JSON برای مودال‌ها (`popup_rules`) — نمونه: [`browser-configs/popup-rules.example.json`](browser-configs/popup-rules.example.json) |
| نشست | نام نشست اختیاری؛ ذخیره/بازاستفاده کوکی و storage در `sessions/` (`session_key`, `persist_session`) |
| بعد از بارگذاری | ثانیه انتظار قبل از گرفتن خروجی (`wait_after_load`) |
| اسکرول خودکار | برای تصاویر و محتوای تنبل (`auto_scroll`) |
| شبکه | ذخیره بدنه پاسخ‌های متنی درخواست‌ها (`save_response_bodies`, محدودیت حجم) |
| دارایی‌ها | حداکثر حجم هر فایل؛ امکان نادیده گرفتن ویدیو (`max_asset_size_mb`, `include_videos`) |
| حریم خصوصی در لاگ | مخفی‌سازی هدرهای حساس (`redact_sensitive`) |
| پروکسی | حالت‌های `none`، `manual`، `fastest-from-file`، `rank-from-file`، `random-from-file` + فایل لیست (`proxy_mode`, `proxy_list_file`, …) و اسرار اختیاری `PROXY_SERVER` / `PROXY_USERNAME` / `PROXY_PASSWORD` |

خروجی معمولاً شامل پوشه‌های `pages/`، فایل `browse.md`، در صورت فعال بودن `sessions/` و آرشیو ZIP (در صورت بزرگی، تقسیم به چند بخش) و **Artifact** در همان اجرای Action است. اسکریپت اجرا: [`scripts/browser_capture.py`](scripts/browser_capture.py).

### [⬇️ Download from url](.github/workflows/downloader.yaml)

دانلود یک یا چند فایل با **فاصله** بین URLها از روی runner گیتهاب؛ خروجی در `downloads/` و به‌روزرسانی `downloads/README.md`. حالت **normal** (هر فایل در پوشهٔ خودش، در صورت حجم بالا ZIP چندپارچه حدود ۹۰ مگابایتی) یا **zip** (یک آرشیو از همهٔ موفق‌ها). فیلد اختیاری **password** برای ZIP رمزدار. توجه: این workflow ممکن است بخشی به **README ریشه** برای فهرست دانلودها اضافه کند.

### [🧭 Collect Free Proxies](.github/workflows/proxy-list.yml)

جمع‌آوری کاندید از منابع پروکسی رایگان، تست موازی، رتبه‌بندی بر اساس سرعت/کارکرد و ذخیره در:

- `proxy-list.md` — جدول خوانا  
- `proxy-list.json` — برای استفاده در workflow مرورگر  
- `proxy-list.env` — متغیرهای محیطی سریع  

قابل تنظیم: تعداد، پروتکل (`http` / `https` / `socks4` / `socks5` / `all`)، URL تست (برای پروکسی‌های متناسب با سایت خاص)، تایم‌اوت، همزمانی، سقف کاندیدها و فایل منبع سفارشی (`proxy-sources.example.txt` در ریشه در صورت نیاز).

### [🗑 Clean generated folders](.github/workflows/cleaner.yml)

پاک‌سازی داده‌های تولیدشده: `downloads/`، `pages/`، `sessions/` و `browse.md` و بازسازی ساختار پایه (برای سبک کردن مخزن یا شروع تمیز).

---

## شروع سریع

1. این مخزن را **Fork** کنید (یا از همان نسخه‌ای که اعتماد دارید استفاده کنید).
2. در GitHub به **Actions** بروید و workflow مورد نظر را با **Run workflow** اجرا کنید.
3. **صفحهٔ وب (آفلاین + شبکه):** workflow [**Browse the Web**](.github/workflows/browser.yml) را باز کنید، فیلد **url** را پر کنید و اجرا کنید.
4. برای مرور از طریق پروکسی: یا ابتدا **Collect Free Proxies** را اجرا کنید و سپس در **Browse the Web** حالت پروکسی مناسب و نام فایل لیست را انتخاب کنید، یا پروکسی دستی/اسرار را طبق [راهنمای پروکسی](docs/proxy-setup.md) تنظیم کنید.

---

## مستندات (`docs`)

| سند | موضوع |
|-----|--------|
| [راهنمای پروکسی و Actions](docs/proxy-setup.md) | حالت‌های پروکسی، اسرار GitHub، ارتباط با لیست پروکسی |
| [مرورگر و اتوماسیون در Actions](docs/browser-automation.md) | Playwright، خروجی آفلاین، session، شبکه، امنیت |
| [مرجع JSON اتوماسیون و پاپ‌آپ](docs/browser-json-reference.md) | ساختار `automation` و `popup_rules` |

---

## نمونه تنظیمات مرورگر (`browser-configs`)

| فایل | کاربرد |
|------|--------|
| [`browser-configs/automation.example.json`](browser-configs/automation.example.json) | الگوی مراحل اتوماسیون برای ورودی workflow مرورگر |
| [`browser-configs/popup-rules.example.json`](browser-configs/popup-rules.example.json) | الگوی قوانین پاپ‌آپ/کوکی |

---

## وابستگی‌های محلی (در صورت اجرای اسکریپت روی ماشین خودتان)

فایل [`requirements-browser.txt`](requirements-browser.txt) و اسکریپت‌های [`scripts/`](scripts/) برای همان منطق استفاده در CI طراحی شده‌اند؛ جزئیات در مستندات بالا آمده است.

---

## یادآوری امنیتی

پروکسی‌های رایگان برای **تست** مناسب‌اند نه برای لاگین حساس یا پرداخت. فایل‌های `sessions/` می‌توانند توکن و کوکی داشته باشند؛ در مخزن **عمومی** با احتیاط `persist_session` را تنظیم کنید و در صورت نیاز `redact_sensitive` را فعال کنید.

---

## مجوز (License)

کد این مخزن تحت [مجوز MIT](LICENSE) منتشر شده است.

---

*اگر این README یا workflowها با نام فایل‌های واقعی در شاخه `.github/workflows` فرق داشت، نام فایل‌های YAML همان منبع نهایی است.*

---

## فایل های دانلود شده در گیتهاب شما :

1. [PersianMind-v1.0.Q4_K_M](https://github.com/Amirhosseinlzz/GitBrowse/tree/main/downloads/PersianMind-v1.0.Q4_K_M)

---
