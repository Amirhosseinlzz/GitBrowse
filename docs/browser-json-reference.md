# Browser JSON Reference

این فایل یک مرجع سریع برای JSONهای ورودی workflow شماره ۴ است.

## automation

ورودی `automation` باید یک آرایه JSON باشد:

```json
[
  {"action":"click","selector":"button.start"},
  {"action":"wait","ms":2000}
]
```

یا یک object با کلید `steps`:

```json
{
  "steps": [
    {"action":"click","selector":"button.start"},
    {"action":"wait","ms":2000}
  ]
}
```

## انتخاب المنت

هر step که به المنت نیاز دارد یکی از این روش‌ها را قبول می‌کند:

```json
{"selector":"button.load-more"}
```

```json
{"text":"Load more"}
```

```json
{"text_regex":"Load|More|ادامه"}
```

```json
{"role":"button","name":"Search"}
```

```json
{"role":"button","name_regex":"^(Search|Go|جستجو)$"}
```

برای iframe:

```json
{"frame_url_contains":"consent","selector":"button.accept"}
```

یا:

```json
{"frame_name":"my-frame","selector":"button.accept"}
```

## actionها

### click

```json
{"action":"click","selector":"button","timeout":10000,"force":false,"continue_on_error":false}
```

### fill

```json
{"action":"fill","selector":"input[name=email]","value":"name@example.com"}
```

### press

```json
{"action":"press","selector":"input[name=q]","key":"Enter"}
```

### type

```json
{"action":"type","selector":"textarea","value":"hello","delay":30}
```

### check / uncheck

```json
{"action":"check","selector":"input[type=checkbox]"}
```

```json
{"action":"uncheck","selector":"input[type=checkbox]"}
```

### select_option

```json
{"action":"select_option","selector":"select#country","value":"NL"}
```

### wait

```json
{"action":"wait","ms":1500}
```

### wait_for_selector

```json
{"action":"wait_for_selector","selector":".loaded","state":"visible","timeout":15000}
```

### wait_for_load_state

```json
{"action":"wait_for_load_state","state":"networkidle","timeout":15000}
```

### goto

```json
{"action":"goto","url":"https://example.com/page","wait_until":"domcontentloaded","timeout":60000}
```

### scroll

```json
{"action":"scroll","x":0,"y":1000}
```

```json
{"action":"scroll","selector":"#target"}
```

### scroll_to_bottom

```json
{"action":"scroll_to_bottom","max_scrolls":20}
```

### screenshot

```json
{"action":"screenshot","name":"after-step.png","full_page":true}
```

### evaluate

```json
{"action":"evaluate","script":"() => document.title"}
```

## popup_rules

ورودی `popup_rules` هم آرایه JSON است:

```json
[
  {"name":"cookie","selector":"button:has-text('Accept all')","timeout":5000}
]
```

یا object با کلید `rules`:

```json
{
  "rules": [
    {"name":"cookie","selector":"button:has-text('Accept all')","timeout":5000}
  ]
}
```

نمونه‌های کاربردی:

```json
[
  {"selector":"#onetrust-accept-btn-handler","timeout":5000},
  {"role":"button","name_regex":"^(Accept|I agree|Continue|تایید|قبول)$","timeout":5000},
  {"text":"من بالای ۱۸ سال هستم","timeout":5000}
]
```
