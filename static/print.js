(function () {
  function applyDocTypeLabel() {
    const el = document.getElementById("docTypeLabel");
    if (!el || !window.DgiiI18n) return;
    const tipoe = Number(window.__PRINT_TIPOE_CF__ || 31);
    el.textContent =
      tipoe === 31
        ? window.DgiiI18n.t("print_credit_invoice")
        : window.DgiiI18n.t("print_consumer_invoice");
  }

  async function boot() {
    const params = new URLSearchParams(window.location.search);
    const requested = params.get("lang");
    const res = await fetch("/api/config");
    const cfg = await res.json();
    window.DgiiI18n.initFromConfig(cfg);
    if (requested) {
      window.DgiiI18n.setLanguage(requested);
    }
    applyDocTypeLabel();
    document.addEventListener("languagechange", applyDocTypeLabel);
  }

  boot().catch((err) => {
    console.error(err);
  });
})();
