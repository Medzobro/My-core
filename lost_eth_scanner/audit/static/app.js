/* Mustahaqati — client renderer. All dynamic text goes through textContent. */
(() => {
  const form = document.getElementById("form");
  const input = document.getElementById("address");
  const submit = document.getElementById("submit");
  const statusBox = document.getElementById("status");
  const resultBox = document.getElementById("result");
  const lead = document.getElementById("lead");
  const scoreBox = document.getElementById("score");
  const scoreValue = document.getElementById("scoreValue");
  const scoreLabel = document.getElementById("scoreLabel");

  let controller = null;
  let timer = null;

  const DIFF = { easy: "سهل", medium: "متوسط", hard: "صعب" };
  const ADDR_RE = /^0x[0-9a-fA-F]{40}$/;

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value === null || value === undefined) continue;
      if (key === "class") node.className = value;
      else if (key === "dir") node.dir = value;
      else if (key === "href") node.href = value;
      else if (key === "target") node.target = value;
      else if (key === "rel") node.rel = value;
      else node.setAttribute(key, value);
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  function fmt(amount, symbol) {
    const digits = Number(amount) >= 1 ? 4 : 6;
    const text = Number(amount).toLocaleString("en-US", { maximumFractionDigits: digits });
    return `${text} ${symbol}`;
  }

  function setScore(kind, value, label) {
    scoreBox.className = `score ${kind}`;
    scoreValue.textContent = value;
    scoreLabel.textContent = label;
  }

  function showStatus(message, { error = false, busy = false } = {}) {
    statusBox.className = `status show${error ? " error" : ""}`;
    statusBox.replaceChildren(el("span", {}, message));
    if (busy) statusBox.append(el("div", { class: "bar" }, el("i")));
  }

  function hideStatus() {
    statusBox.className = "status";
    statusBox.replaceChildren();
  }

  function renderFinding(finding) {
    const steps = el(
      "ol",
      { class: "steps" },
      finding.steps.map((step) =>
        el("li", {}, el("span", { class: "ar" }, step.ar), el("span", { class: "en", dir: "ltr" }, step.en))
      )
    );

    const head = el(
      "div",
      { class: "card-head" },
      el(
        "div",
        {},
        el("h3", {}, finding.contract_name),
        el(
          "div",
          { class: "tags" },
          el("span", { class: "tag" }, finding.chain),
          el("span", { class: "tag diff" }, DIFF[finding.difficulty] || finding.difficulty),
          finding.withdraw_method ? el("code", { class: "method", dir: "ltr" }, finding.withdraw_method) : null
        )
      ),
      el(
        "div",
        { class: "amount" },
        el("div", { class: "big num", dir: "ltr" }, fmt(finding.amount, finding.symbol)),
        finding.usd ? el("span", { class: "usd" }, `≈ $${Math.round(finding.usd).toLocaleString("en-US")}`) : null
      )
    );

    return el(
      "article",
      { class: `card diff-${finding.difficulty}` },
      head,
      steps,
      finding.note_ar ? el("p", { class: "note" }, finding.note_ar) : null,
      el("a", { class: "cta", href: finding.etherscan, target: "_blank", rel: "noopener" }, "افتح العقد في Etherscan ↗")
    );
  }

  function render(data) {
    const findings = data.findings || [];
    const total = data.totals?.count || 0;
    const usd = data.totals?.usd_total;

    if (usd && usd >= 1) setScore("ok", `$${Math.round(usd).toLocaleString("en-US")}`, "قيمة تقديرية");
    else if (total) setScore("ok", String(total), total === 1 ? "رصيد" : "أرصدة");
    else setScore("none", "0", "لا شيء عالق");

    const nodes = [];

    nodes.push(
      el(
        "section",
        { class: "address-block" },
        el("div", { class: "label" }, "العنوان المفحوص"),
        el("code", { class: "addr", dir: "ltr" }, data.address),
        el(
          "div",
          { class: "meta" },
          `تم الفحص ${String(data.generated_at).replace("T", " ")} UTC · ${data.elapsed} ثانية · ${data.stats.rpc_calls} استدعاء`
        )
      )
    );

    nodes.push(el("section", { class: `verdict ${total ? "ok" : "none"}` }, el("p", {}, data.verdict_ar)));

    const actions = el(
      "div",
      { class: "actions" },
      el("button", { type: "button", class: "chip", id: "shareBtn" }, "نسخ رابط التقرير"),
      el("button", { type: "button", class: "chip", id: "rescanBtn" }, "إعادة الفحص")
    );
    nodes.push(actions);

    if (findings.length) {
      nodes.push(el("section", { class: "findings" }, el("h2", {}, "الأرصدة القابلة للاسترداد"), findings.map(renderFinding)));
    } else {
      nodes.push(
        el(
          "section",
          { class: "empty" },
          el("h2", {}, "لا شيء لعرضه"),
          el("p", {}, "لم نجد رصيداً عالقاً لهذا العنوان في العقود المعروفة. هذا لا يعني استحالة وجود مال في عقود خارج تغطيتنا.")
        )
      );
    }

    if (data.native && data.native.length) {
      nodes.push(
        el(
          "section",
          { class: "native" },
          el("h2", {}, "أرصدتك الحالية (للسياق فقط)"),
          el("p", { class: "hint" }, "أموال في محفظتك، ليست معلّقة."),
          el(
            "ul",
            {},
            data.native.map((n) =>
              el("li", {}, el("span", { class: "chain" }, n.chain), el("span", { class: "num", dir: "ltr" }, fmt(n.amount, n.symbol)))
            )
          )
        )
      );
    }

    const coverage = data.coverage || {};
    const stats = data.stats || {};
    nodes.push(
      el(
        "section",
        { class: "coverage" },
        el("h2", {}, "ما الذي فُحص فعلاً"),
        el(
          "ul",
          { class: "stats" },
          el("li", {}, el("span", {}, "عقود"), el("b", { class: "num" }, coverage.contracts_checked ?? "—")),
          el("li", {}, el("span", {}, "شبكات"), el("b", { class: "num" }, (coverage.chains_scanned || []).length)),
          el("li", {}, el("span", {}, "استدعاءات"), el("b", { class: "num" }, stats.rpc_calls ?? "—")),
          el("li", {}, el("span", {}, "فشل اتصال"), el("b", { class: "num" }, stats.rpc_failures ?? "—")),
          el(
            "li",
            {},
            el("span", {}, "تغطية"),
            el("b", { class: "num" }, `${Math.round((1 - (stats.failure_rate || 0)) * 1000) / 10}%`)
          )
        ),
        el("p", { class: "hint" }, "التقرير يغطي العقود المعروفة في قاعدة المشروع فقط.")
      )
    );

    resultBox.replaceChildren(...nodes);
    lead.style.display = "none";

    const shareBtn = document.getElementById("shareBtn");
    if (shareBtn) {
      shareBtn.addEventListener("click", async () => {
        const url = `${location.origin}/report/${data.address}`;
        try {
          await navigator.clipboard.writeText(url);
          shareBtn.textContent = "تم النسخ ✓";
          setTimeout(() => (shareBtn.textContent = "نسخ رابط التقرير"), 1800);
        } catch {
          window.prompt("انسخ الرابط:", url);
        }
      });
    }
    const rescanBtn = document.getElementById("rescanBtn");
    if (rescanBtn) rescanBtn.addEventListener("click", () => run(data.address, { force: true }));
  }

  async function run(address, { force = false } = {}) {
    if (!ADDR_RE.test(address)) {
      resultBox.replaceChildren();
      setScore("none", "—", "غير مفحوص");
      showStatus("العنوان غير صحيح: يجب أن يبدأ بـ 0x ويتكون من 40 خانة ست عشرية.", { error: true });
      input.focus();
      return;
    }

    if (controller) controller.abort();
    controller = new AbortController();

    submit.disabled = true;
    submit.textContent = "يفحص…";
    resultBox.replaceChildren();
    const started = Date.now();
    showStatus("نقرأ السلسلة الآن… 0 ثانية", { busy: true });
    timer = setInterval(() => {
      const secs = ((Date.now() - started) / 1000).toFixed(0);
      const node = statusBox.querySelector("span");
      if (node) node.textContent = `نقرأ السلسلة الآن… ${secs} ثانية`;
    }, 500);

    try {
      const response = await fetch("/api/audit", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ address, include_native: true, force }),
        signal: controller.signal,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || `خطأ ${response.status}`);
      hideStatus();
      render(payload);
      const url = new URL(location.href);
      url.searchParams.set("a", payload.address);
      history.replaceState(null, "", url);
    } catch (error) {
      if (error.name === "AbortError") return;
      const message = String(error.message || error);
      showStatus(
        message.includes("429")
          ? "عدد الفحوصات كبير من هذا الجهاز. انتظر دقيقة ثم أعد المحاولة."
          : `تعذّر إتمام الفحص: ${message}`,
        { error: true }
      );
      setScore("none", "—", "لم يكتمل");
    } finally {
      clearInterval(timer);
      submit.disabled = false;
      submit.textContent = "افحص الآن";
      controller = null;
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    run(input.value.trim());
  });

  document.querySelectorAll(".chip[data-addr]").forEach((chip) => {
    chip.addEventListener("click", () => {
      input.value = chip.dataset.addr;
      run(chip.dataset.addr);
    });
  });

  const shared = new URL(location.href).searchParams.get("a");
  if (shared && ADDR_RE.test(shared)) {
    input.value = shared;
    run(shared);
  }
})();
