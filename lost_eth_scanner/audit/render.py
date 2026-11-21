"""Server-rendered HTML report, self-contained enough to be shared as a link."""

from __future__ import annotations

import html
from typing import Any

from audit.engine import Report

DIFFICULTY_LABEL = {
    "easy": ("سهل", "easy"),
    "medium": ("متوسط", "medium"),
    "hard": ("صعب", "hard"),
}


def _e(value: Any) -> str:
    """HTML-escape every dynamic value that reaches the page."""
    return html.escape(str(value), quote=True)


def _fmt(amount: float, symbol: str) -> str:
    text = f"{amount:,.6f}".rstrip("0").rstrip(".")
    return f"{text} {_e(symbol)}"


def render_report(report: Report, *, standalone: bool = True) -> str:
    """Render the full report page."""
    data = report.to_dict()
    findings = data["findings"]
    total_usd = data["totals"].get("usd_total")
    count = data["totals"].get("count", 0)

    cards = "\n".join(_render_finding(f, data["address"]) for f in findings)
    native_rows = "\n".join(
        f"<li><span class='chain'>{_e(n['chain'])}</span>"
        f"<span class='num' dir='ltr'>{_fmt(n['amount'], n['symbol'])}</span></li>"
        for n in data["native"]
    )

    headline = (
        f"${total_usd:,.0f}" if total_usd and total_usd >= 1 else (f"{count}" if count else "0")
    )
    badge_class = "ok" if count else "none"

    body = f"""
<header class="hero">
  <div class="brand">
    <span class="logo">⛏</span>
    <div>
      <div class="brand-name">مستحقاتي</div>
      <div class="brand-sub">Stuck-funds audit · read-only</div>
    </div>
  </div>
  <div class="score {badge_class}">
    <div class="score-value">{_e(headline)}</div>
    <div class="score-label">{"قيمة تقديرية" if total_usd else "أرصدة"}</div>
  </div>
</header>

<section class="address-block">
  <div class="label">العنوان المفحوص</div>
  <code class="addr" dir="ltr">{_e(data["address"])}</code>
  <div class="meta">تم الفحص {_e(data["generated_at"].replace("T", " "))} UTC · استغرق {_e(data["elapsed"])} ثانية</div>
</section>

<section class="verdict {badge_class}">
  <p>{_e(data["verdict_ar"])}</p>
</section>

{"<section class='findings'><h2>الأرصدة القابلة للاسترداد</h2>" + cards + "</section>" if findings else "<section class='empty'><h2>لا شيء لعرضه</h2><p>لم نجد أي رصيد عالق في العقود التي نعرفها. هذا لا يعني استحالة وجود مال في عقود أخرى — راجع قسم التغطية أدناه.</p></section>"}

{"<section class='native'><h2>أرصدتك الحالية (للسياق فقط)</h2><p class='hint'>هذه أموال في محفظتك، ليست معلّقة.</p><ul>" + native_rows + "</ul></section>" if native_rows else ""}

<section class="coverage">
  <h2>ما الذي فُحص فعلاً</h2>
  <ul class="stats">
    <li><span>عقود مُفحَصة</span><b class="num">{_e(data["coverage"]["contracts_checked"])}</b></li>
    <li><span>شبكات</span><b class="num">{_e(len(data["coverage"]["chains_scanned"]))}</b></li>
    <li><span>استدعاءات RPC</span><b class="num">{_e(data["stats"]["rpc_calls"])}</b></li>
    <li><span>فشل اتصال</span><b class="num">{_e(data["stats"]["rpc_failures"])}</b></li>
    <li><span>نسبة التغطية</span><b class="num">{_e(round((1 - data["stats"]["failure_rate"]) * 100, 1))}%</b></li>
  </ul>
  <p class="hint">الفحص يغطي فقط العقود المعروفة في قاعدة المشروع. أي عقد غير معروف لا يظهر هنا.</p>
</section>

<footer class="foot">
  <p><b>أمان:</b> هذه الصفحة للقراءة فقط. لم نطلب مفتاحك الخاص، ولن نطلبه. كل خطوة استرداد تنفّذها أنت من محفظتك عبر Etherscan.</p>
  <p><b>تحذير:</b> أي «خدمة استرداد» تطلب رسوماً مقدماً أو عبارة الاسترداد هي عملية نصب.</p>
  <p class="src">مصدر البيانات: عقود عامة على السلسلة · <a href="https://github.com/Medzobro/My-core">My-core</a></p>
</footer>
"""

    if not standalone:
        return body
    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>تقرير {_e(data["address"][:10])}… · مستحقاتي</title>
<meta property="og:title" content="تقرير أرصدة عالقة — {_e(data["address"][:10])}…">
<meta property="og:description" content="{_e(data["verdict_ar"])}">
<link rel="stylesheet" href="/static/app.css">
<script src="/static/report.js" defer></script>
</head>
<body>
<main class="wrap">{body}</main>
</body>
</html>"""


def _render_recovery(finding: dict) -> str:
    """Render exact calldata the user can review and sign themselves."""
    steps = finding.get("calldata") or []
    if not steps:
        return ""
    items = "".join(
        "<li>"
        f"<div class='fn'>{_e(step['label_ar'])} "
        f"<span dir='ltr'>({_e(step['function'])})</span></div>"
        f"<div class='fn'>إلى: <code dir='ltr'>{_e(step['to'])}</code></div>"
        f"<code class='hex' dir='ltr'>{_e(step['data'])}</code>"
        f"<button class='copy' type='button' data-copy='{_e(step['data'])}'>نسخ calldata</button>"
        "</li>"
        for step in steps
    )
    return (
        "<details class='recovery'>"
        "<summary>بيانات المعاملة الجاهزة (calldata)</summary>"
        "<p class='hint'>الصقها في محفظة تدعم «البيانات المخصصة»، أو استخدم Write Contract "
        "في Etherscan. راجعها قبل التوقيع — نحن لا نوقّع ولا نرسل شيئاً.</p>"
        f"<ul class='calldata'>{items}</ul>"
        "</details>"
    )


def _render_finding(finding: dict, address: str) -> str:
    label_ar, label_en = DIFFICULTY_LABEL.get(finding["difficulty"], ("متوسط", "medium"))
    steps = "\n".join(
        f"<li><span class='ar'>{_e(s['ar'])}</span>"
        f"<span class='en' dir='ltr'>{_e(s['en'])}</span></li>"
        for s in finding["steps"]
    )
    note = ""
    if finding.get("note_ar"):
        note = f"<p class='note'>{_e(finding['note_ar'])}</p>"
    usd = f"<span class='usd'>≈ ${finding['usd']:,.0f}</span>" if finding.get("usd") else ""
    method = (
        f"<code class='method' dir='ltr'>{_e(finding['withdraw_method'])}</code>"
        if finding.get("withdraw_method")
        else ""
    )
    source = ""
    if finding.get("source_symbol") and finding.get("source_amount") is not None:
        source = (
            f"<div class='source' dir='ltr'>{_fmt(finding['source_amount'], finding['source_symbol'])}"
            f" → {_fmt(finding['amount'], finding['symbol'])}</div>"
        )
    kit = (
        f"<a class='cta ghost' href='/kit/digixdao/{_e(address)}'>عدّة الاسترداد الكاملة ↗</a>"
        if finding.get("check_type") == "digixdao"
        else ""
    )
    return f"""
<article class="card diff-{_e(finding["difficulty"])}">
  <div class="card-head">
    <div>
      <h3>{_e(finding["contract_name"])}</h3>
      <div class="tags">
        <span class="tag">{_e(finding["chain"])}</span>
        <span class="tag diff">{_e(label_ar)}</span>
        {method}
      </div>
    </div>
    <div class="amount">
      <div class="big num" dir="ltr">{_fmt(finding["amount"], finding["symbol"])}</div>
      {usd}
      {source}
    </div>
  </div>
  <ol class="steps">{steps}</ol>
  {note}
  {_render_recovery(finding)}
  {kit}
  <a class="cta" href="{_e(finding["etherscan"])}" target="_blank" rel="noopener">افتح العقد في Etherscan ↗</a>
</article>"""


def render_error(message: str, status: int = 400) -> str:
    return f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>خطأ</title><link rel="stylesheet" href="/static/app.css"></head>
<body><main class="wrap"><section class="verdict none"><h2>تعذّر إتمام الفحص</h2>
<p>{_e(message)}</p><p><a class="cta" href="/">رجوع</a></p></section></main></body></html>"""
