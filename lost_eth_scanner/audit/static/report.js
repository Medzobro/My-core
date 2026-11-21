/* Copy-to-clipboard for the calldata blocks. No inline handlers: the report's
   Content-Security-Policy allows only same-origin scripts. The textarea path is
   the fallback when the Clipboard API is unavailable or permission is denied. */
function legacyCopy(text) {
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch (err) {
    ok = false;
  }
  document.body.removeChild(area);
  return ok;
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("button.copy");
  if (!button) return;
  const text = button.dataset.copy || "";
  const original = button.textContent;
  let ok = false;
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch (err) {
      ok = false;
    }
  }
  if (!ok) ok = legacyCopy(text);
  button.textContent = ok ? "تم النسخ" : "تعذّر النسخ";
  window.setTimeout(() => {
    button.textContent = original;
  }, 1600);
});
