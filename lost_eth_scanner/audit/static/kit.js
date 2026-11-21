/* Progressive enhancement: submit the address as a path, keep no-JS form as fallback. */
(() => {
  const form = document.getElementById("kitForm");
  const input = document.getElementById("kitAddress");
  if (!form || !input) return;
  form.addEventListener("submit", (event) => {
    const value = input.value.trim();
    if (!/^0x[0-9a-fA-F]{40}$/.test(value)) return; // let the browser show "required"/server 400
    event.preventDefault();
    window.location.href = `/kit/digixdao/${value.toLowerCase()}`;
  });
})();
