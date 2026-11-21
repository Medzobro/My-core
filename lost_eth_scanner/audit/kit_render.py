"""Server-rendered page for the DigixDAO recovery kit.

One contract, one question: how much ETH does this address get, and what does
it sign? The page is deliberately narrow so the numbers and the calldata stay
the only things on screen.
"""

from __future__ import annotations

import html
from typing import Any

from audit.kit import ACID, DGD, DigixdaoKit


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _num(value: float, digits: int = 6) -> str:
    text = f"{value:,.{digits}f}".rstrip("0").rstrip(".")
    return text or "0"


def _calldata_steps(steps: list[dict[str, Any]]) -> str:
    rows = "".join(
        f"""
<li class="kit-step">
  <div class="kit-step-head">
    <span class="kit-index">{index}</span>
    <div>
      <div class="kit-fn" dir="ltr">{_e(step["function"])}</div>
      <div class="kit-to">إلى: <code dir="ltr">{_e(step["to"])}</code></div>
    </div>
  </div>
  <p class="kit-label">{_e(step["label_ar"])}</p>
  <code class="hex" dir="ltr">{_e(step["data"])}</code>
  <button class="copy" type="button" data-copy="{_e(step["data"])}">نسخ calldata</button>
</li>"""
        for index, step in enumerate(steps, 1)
    )
    return f"<ol class='kit-steps'>{rows}</ol>"


def _shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)} · مستحقاتي</title>
<meta property="og:title" content="{_e(title)}">
<link rel="stylesheet" href="/static/app.css">
<script src="/static/report.js" defer></script>
<script src="/static/kit.js" defer></script>
</head>
<body>
<main class="wrap kit-wrap">{body}</main>
</body>
</html>"""


def render_kit_form(error: str = "") -> str:
    error_html = f"<p class='kit-error'>{_e(error)}</p>" if error else ""
    body = f"""
<header class="kit-hero">
  <a class="kit-back" href="/">→ الفحص العام</a>
  <div class="kit-badge">DigixDAO · Ragnarok</div>
  <h1>عدّة استرداد DGD</h1>
  <p class="kit-sub">عقد Acid يحرق توكنات DGD ويعيد ETH بسعر ثابت. الصفحة تقرأ رصيدك
  والسعر من السلسلة، وتعطيك المعاملتين بالبايت.</p>
</header>

<section class="kit-panel">
  <form id="kitForm" class="audit kit-form" method="get" action="/kit/digixdao">
    <label class="field">
      <span>عنوان المحفظة</span>
      <input id="kitAddress" name="address" type="text" inputmode="text" spellcheck="false"
             placeholder="0x…" autocomplete="off" required>
    </label>
    <button class="primary" type="submit">افحص الرصيد</button>
  </form>
  {error_html}
  <p class="hint">لا نطلب مفتاحاً ولا نوقّع. ثلاث قراءات عامة فقط: رصيد DGD، سعر الصرف، ورصيد العقد.</p>
</section>

<section class="kit-facts">
  <article><span>التوكن</span><b dir="ltr">DGD</b><small>9 decimals</small></article>
  <article><span>العقد</span><b dir="ltr">Acid</b><small dir="ltr">{_e(ACID)}</small></article>
  <article><span>السعر</span><b dir="ltr">0.193 ETH / DGD</b><small>يُقرأ من العقد</small></article>
</section>

<footer class="foot">
  <p><b>تحذير:</b> burn() يحرق كامل رصيد DGD. راجع الرقم قبل التوقيع.</p>
  <p class="src">مصدر الأرقام: Ethereum mainnet · <a href="/">مستحقاتي</a></p>
</footer>"""
    return _shell("عدّة استرداد DGD", body)


def render_kit(kit: DigixdaoKit) -> str:
    if kit.error == "acid-not-initialised":
        body = f"""
<header class="kit-hero">
  <a class="kit-back" href="/kit/digixdao">→ عنوان آخر</a>
  <div class="kit-badge">DigixDAO · Ragnarok</div>
  <h1>العقد غير مهيأ</h1>
  <p class="kit-sub">لم يُرجع عقد Acid سعراً صالحاً. لا يمكن حساب أي استرداد الآن.</p>
</header>
<section class="kit-panel"><code class="addr" dir="ltr">{_e(kit.address)}</code></section>"""
        return _shell("عدّة استرداد DGD", body)

    stats = f"""
<section class="kit-stats">
  <article><span>رصيد DGD</span><b class="num" dir="ltr">{_num(kit.dgd)}</b><small>DGD</small></article>
  <article><span>سعر الاسترداد</span><b class="num" dir="ltr">{_num(kit.rate_per_dgd, 9)}</b><small>ETH لكل DGD</small></article>
  <article class="accent"><span>المبلغ المسترد</span><b class="num" dir="ltr">{_num(kit.eth)}</b><small>ETH</small></article>
  <article><span>رصيد العقد</span><b class="num" dir="ltr">{_num(kit.acid_balance, 2)}</b><small>ETH</small></article>
</section>"""

    if not kit.has_balance:
        body = f"""
<header class="kit-hero">
  <a class="kit-back" href="/kit/digixdao">→ عنوان آخر</a>
  <div class="kit-badge">DigixDAO · Ragnarok</div>
  <h1>لا يوجد رصيد DGD</h1>
  <p class="kit-sub">هذا العنوان لا يحمل DGD، لذا لا يوجد ما يُحرق مقابل ETH.</p>
</header>
<section class="kit-panel">
  <div class="label">العنوان المفحوص</div>
  <code class="addr" dir="ltr">{_e(kit.address)}</code>
  {stats}
  <p class="hint">السعر الحالي يُقرأ من <code dir="ltr">weiPerNanoDGD()</code> على عقد Acid.
  إذا كنت تتوقع رصيداً، تأكد أن DGD في نفس المحفظة وليس في محفظة أخرى.</p>
</section>"""
        return _shell("عدّة استرداد DGD", body)

    coverage = max(0.0, min(kit.coverage, 1.5))
    bar_width = min(coverage * 100, 100)
    solvent = (
        "<p class='kit-ok'>العقد يغطي هذا المبلغ بالكامل.</p>"
        if kit.solvent
        else "<p class='kit-warn'>تحذير: رصيد العقد أقل من المبلغ المحسوب. قد تفشل المعاملة.</p>"
    )
    body = f"""
<header class="kit-hero">
  <a class="kit-back" href="/kit/digixdao">→ عنوان آخر</a>
  <div class="kit-badge">DigixDAO · Ragnarok</div>
  <h1 class="kit-amount" dir="ltr">{_num(kit.eth)} ETH</h1>
  <p class="kit-sub">مقابل حرق <b dir="ltr">{_num(kit.dgd)} DGD</b>. الأرقام مقروءة الآن من
  Ethereum mainnet، والمعاملتان جاهزتان أدناه.</p>
</header>

<section class="kit-panel">
  <div class="label">العنوان المفحوص</div>
  <code class="addr" dir="ltr">{_e(kit.address)}</code>
  <div class="meta">تم الفحص {_e(kit.generated_at.replace("T", " ").replace("+00:00", ""))} UTC</div>
  {stats}
  <div class="kit-bar">
    <div class="kit-bar-fill" style="width:{bar_width:.1f}%"></div>
  </div>
  <div class="kit-bar-legend">
    <span>استهلاك من رصيد العقد: {_num(kit.coverage * 100, 1)}%</span>
    <span dir="ltr">{_num(kit.eth)} / {_num(kit.acid_balance, 2)} ETH</span>
  </div>
  {solvent}
</section>

<section class="kit-panel">
  <h2>المعاملتان</h2>
  <p class="hint">نفّذهما بالترتيب من نفس المحفظة. الأولى تسمح لعقد Acid بسحب DGD،
  والثانية تحرقه وتُرسل ETH. لا تشارك مفتاحك مع أي جهة.</p>
  {_calldata_steps(kit.steps)}
</section>

<section class="kit-panel kit-verify">
  <h2>تحقق بنفسك</h2>
  <ul>
    <li>رصيدك: <code dir="ltr">balanceOf({_e(kit.address)})</code> على
      <a href="https://etherscan.io/token/{_e(DGD)}#readContract" target="_blank" rel="noopener">عقد DGD ↗</a></li>
    <li>السعر: <code dir="ltr">weiPerNanoDGD()</code> على
      <a href="https://etherscan.io/address/{_e(ACID)}#readContract" target="_blank" rel="noopener">عقد Acid ↗</a></li>
    <li>المعاملة: Etherscan ← Write Contract ← <code dir="ltr">burn()</code> (بعد approve).</li>
  </ul>
</section>

<footer class="foot">
  <p><b>أمان:</b> هذه الصفحة للقراءة فقط. لا مفتاح، لا توقيع، لا إرسال. كل معاملة تنفّذها أنت.</p>
  <p><b>تحذير:</b> <code dir="ltr">burn()</code> يحرق كامل رصيد DGD — لا يوجد استرداد جزئي.</p>
  <p class="src">DGD: <span dir="ltr">{_e(DGD)}</span> · Acid: <span dir="ltr">{_e(ACID)}</span></p>
</footer>"""
    return _shell("عدّة استرداد DGD", body)


def render_kit_error(message: str, status: int = 400) -> str:
    body = f"""
<header class="kit-hero">
  <a class="kit-back" href="/kit/digixdao">→ عنوان آخر</a>
  <div class="kit-badge">DigixDAO · Ragnarok</div>
  <h1>تعذّر الفحص</h1>
  <p class="kit-sub">{_e(message)}</p>
</header>"""
    return _shell("خطأ", body)
