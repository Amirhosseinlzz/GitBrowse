# Proxy List

این فایل توسط workflow شماره ۵ ساخته شده است.

> مقدار `ping_ms` زمان رفت‌وبرگشت یک درخواست HTTP/HTTPS از داخل GitHub Actions از مسیر همان proxy است؛ ICMP ping نیست.

## Fastest proxies

| Rank | PROXY_SERVER | PROXY_USERNAME | PROXY_PASSWORD | ping_ms | protocol | status | observed_ip | source |
|---:|---|---|---|---:|---|---:|---|---|
| 1 | `http://190.9.48.193:999` | `` | `` | 385 | `http` | 200 | `201.159.20.193` | `https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt` |
| 2 | `http://174.138.168.90:8001` | `` | `` | 469 | `http` | 200 | `108.41.5.55` | `https://free-proxy-list.net/` |
| 3 | `http://38.123.220.52:999` | `` | `` | 512 | `http` | 200 | `38.123.220.52` | `https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt` |
| 4 | `http://159.203.61.169:3128` | `` | `` | 556 | `http` | 200 | `159.203.61.169` | `https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt` |
| 5 | `http://174.138.168.78:8001` | `` | `` | 606 | `http` | 200 | `24.210.111.82` | `https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt` |
| 6 | `http://174.138.161.218:8001` | `` | `` | 610 | `http` | 200 | `98.14.231.119` | `https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt` |
| 7 | `http://174.138.161.205:8001` | `` | `` | 751 | `http` | 200 | `172.59.184.242` | `https://free-proxy-list.net/` |
| 8 | `http://38.199.71.79:999` | `` | `` | 842 | `http` | 200 | `38.199.71.79` | `https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt` |
| 9 | `http://134.209.29.120:3128` | `` | `` | 893 | `http` | 200 | `134.209.29.120` | `https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/proto...` |
| 10 | `http://174.138.162.235:8001` | `` | `` | 906 | `http` | 200 | `50.33.107.159` | `https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt` |

## استفاده در workflow شماره ۴

در workflow `🌐 4-Browse the Web` مقدار `proxy_mode` را روی `fastest-from-file` بگذارید تا ردیف اول همین فایل استفاده شود. برای انتخاب ردیف دیگر، `proxy_mode=rank-from-file` و `proxy_list_rank` را برابر شماره ردیف جدول بگذارید.

فایل ماشینی متناظر: `proxy-list.json`
