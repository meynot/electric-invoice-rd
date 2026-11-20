(function () {
  const itemsEl = document.getElementById("items");
  const form = document.getElementById("invoiceForm");
  const resultEl = document.getElementById("result");
  const resultBody = document.getElementById("resultBody");
  const errorsEl = document.getElementById("errors");
  const errorBody = document.getElementById("errorBody");
  let lastResult = null;

  function t(key) {
    return window.DgiiI18n ? window.DgiiI18n.t(key) : key;
  }

  document.querySelectorAll("[data-collapse]").forEach((section) => {
    const toggle = section.querySelector(".collapse-toggle");
    if (!toggle) return;
    toggle.addEventListener("click", () => {
      const collapsed = section.classList.toggle("collapsed");
      toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    });
  });

  function todayISO() {
    return new Date().toISOString().slice(0, 10);
  }

  function addItem(defaults) {
    const row = document.createElement("div");
    row.className = "item-row";
    row.innerHTML = `
      <label><span data-i18n="item_name">${t("item_name")}</span>
        <input name="item_name" required value="${defaults?.name || ""}" />
      </label>
      <label><span data-i18n="quantity">${t("quantity")}</span>
        <input name="item_qty" type="number" min="0.01" step="0.01" required value="${defaults?.qty || "1"}" />
      </label>
      <label><span data-i18n="price">${t("price")}</span>
        <input name="item_price" type="number" min="0" step="0.0001" required value="${defaults?.price || "100"}" />
      </label>
      <label><span data-i18n="good_or_service">${t("good_or_service")}</span>
        <select name="item_gos">
          <option value="1" data-i18n="good">${t("good")}</option>
          <option value="2" data-i18n="service">${t("service")}</option>
        </select>
      </label>
      <label><span data-i18n="itbis">${t("itbis")}</span>
        <select name="item_tax">
          <option value="1" data-i18n="tax_1">${t("tax_1")}</option>
          <option value="2" data-i18n="tax_2">${t("tax_2")}</option>
          <option value="3" data-i18n="tax_3">${t("tax_3")}</option>
          <option value="4" data-i18n="tax_4">${t("tax_4")}</option>
        </select>
      </label>
      <button type="button" class="secondary remove-item">X</button>
    `;
    row.querySelector(".remove-item").addEventListener("click", () => {
      if (itemsEl.children.length > 1) row.remove();
    });
    if (defaults?.gos) row.querySelector('[name="item_gos"]').value = String(defaults.gos);
    if (defaults?.tax) row.querySelector('[name="item_tax"]').value = String(defaults.tax);
    itemsEl.appendChild(row);
  }

  document.getElementById("addItem").addEventListener("click", () => addItem());

  function syncDocumentFields() {
    const type = document.getElementById("tipoe_cf").value;
    const paymentType = document.getElementById("tipo_pago").value;
    const encf = document.getElementById("encf");
    const sequenceField = document.getElementById("sequenceExpiryField");
    const venc = document.getElementById("fecha_vencimiento_secuencia");
    const paymentDueField = document.getElementById("paymentDueField");
    const paymentDue = document.getElementById("fecha_limite_pago");

    if (!encf.value || /^E3[12]0+$/.test(encf.value) || encf.value.length < 13) {
      encf.value = `E${type}0000000001`;
    } else if (!encf.value.startsWith(`E${type}`)) {
      encf.value = `E${type}` + encf.value.slice(3);
    }

    const isE31 = type === "31";
    sequenceField.classList.toggle("hidden", !isE31);
    venc.required = isE31;
    if (!isE31) {
      venc.value = "";
    }

    const isCredit = paymentType === "2";
    paymentDueField.classList.toggle("hidden", !isCredit);
    paymentDue.required = isCredit;
    if (!isCredit) {
      paymentDue.value = "";
    } else if (!paymentDue.value) {
      const due = new Date();
      due.setDate(due.getDate() + 30);
      paymentDue.value = due.toISOString().slice(0, 10);
    }
  }

  document.getElementById("tipoe_cf").addEventListener("change", syncDocumentFields);
  document.getElementById("tipo_pago").addEventListener("change", syncDocumentFields);

  async function loadInvoiceList() {
    const listEl = document.getElementById("invoiceList");
    if (!listEl) return;
    try {
      const res = await fetch("/api/invoices?limit=20");
      const data = await res.json();
      if (!res.ok) {
        listEl.textContent = data.detail || "—";
        return;
      }
      const items = data.items || [];
      if (!items.length) {
        listEl.textContent = "—";
        return;
      }
      listEl.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>${t("invoice_number")}</th>
              <th>e-NCF</th>
              <th>${t("total")}</th>
              <th>${t("status")}</th>
            </tr>
          </thead>
          <tbody>
            ${items
              .map(
                (item) => `
              <tr>
                <td>${item.invoice_number}</td>
                <td><a href="/invoices/${item.encf}/print" target="_blank">${item.encf}</a></td>
                <td>RD$ ${item.monto_total}</td>
                <td>${item.estado || "—"}</td>
              </tr>`
              )
              .join("")}
          </tbody>
        </table>
      `;
    } catch (err) {
      listEl.textContent = err.message || String(err);
    }
  }

  async function loadConfig() {
    const res = await fetch("/api/config");
    const cfg = await res.json();
    window.DgiiI18n.initFromConfig(cfg);
    document.getElementById("envLabel").textContent = cfg.dgii_env || "—";
    document.getElementById("nextInvoiceLabel").textContent =
      cfg.next_invoice_number || "—";
    if (cfg.issuer_rnc) document.getElementById("issuer_rnc").value = cfg.issuer_rnc;
    if (cfg.issuer_name) document.getElementById("issuer_name").value = cfg.issuer_name;
    if (cfg.issuer_address) document.getElementById("issuer_address").value = cfg.issuer_address;
    document.getElementById("encf").value = "E310000000001";
    document.getElementById("fecha_emision").value = todayISO();
    const nextYear = new Date();
    nextYear.setFullYear(nextYear.getFullYear() + 1);
    document.getElementById("fecha_vencimiento_secuencia").value = nextYear.toISOString().slice(0, 10);
    syncDocumentFields();
    if (!itemsEl.children.length) {
      addItem({ name: t("example_item"), qty: "1", price: "100.00", gos: 1, tax: 1 });
    }
    await loadInvoiceList();
  }

  function collectItems() {
    return Array.from(itemsEl.querySelectorAll(".item-row")).map((row) => ({
      name: row.querySelector('[name="item_name"]').value.trim(),
      quantity: row.querySelector('[name="item_qty"]').value,
      unit_price: row.querySelector('[name="item_price"]').value,
      good_or_service: Number(row.querySelector('[name="item_gos"]').value),
      tax_indicator: Number(row.querySelector('[name="item_tax"]').value),
    }));
  }

  function buildPayload() {
    const tipoe_cf = Number(document.getElementById("tipoe_cf").value);
    const buyerRnc = document.getElementById("buyer_rnc").value.trim();
    const buyerName = document.getElementById("buyer_name").value.trim();
    const tipo_pago = Number(document.getElementById("tipo_pago").value);
    const payload = {
      tipoe_cf,
      encf: document.getElementById("encf").value.trim().toUpperCase(),
      fecha_vencimiento_secuencia:
        tipoe_cf === 31
          ? document.getElementById("fecha_vencimiento_secuencia").value || null
          : null,
      fecha_emision: document.getElementById("fecha_emision").value || null,
      tipo_ingresos: document.getElementById("tipo_ingresos").value,
      tipo_pago,
      fecha_limite_pago:
        tipo_pago === 2
          ? document.getElementById("fecha_limite_pago").value || null
          : null,
      dry_run: document.getElementById("dry_run").checked,
      issuer: {
        rnc: document.getElementById("issuer_rnc").value.trim(),
        name: document.getElementById("issuer_name").value.trim(),
        address: document.getElementById("issuer_address").value.trim(),
      },
      items: collectItems(),
    };
    if (buyerRnc || buyerName) {
      payload.buyer = {
        rnc: buyerRnc,
        name: buyerName || t("final_consumer"),
        address: document.getElementById("buyer_address").value.trim() || null,
      };
    }
    return payload;
  }

  function showError(detail) {
    errorsEl.classList.remove("hidden");
    resultEl.classList.add("hidden");
    errorBody.textContent =
      typeof detail === "string" ? detail : JSON.stringify(detail, null, 2);
  }

  function showResult(data) {
    lastResult = data;
    errorsEl.classList.add("hidden");
    resultEl.classList.remove("hidden");
    const messages = (data.mensajes || []).map((m) => `<li>${m}</li>`).join("");
    const lang = window.DgiiI18n.current;
    resultBody.innerHTML = `
      <div class="result-grid">
        <img src="/api/invoices/${data.encf}/qr.png" alt="QR" width="140" height="140" />
        <div>
          <p><strong>${t("invoice_number")}:</strong> ${data.invoice_number}</p>
          <p><strong>e-NCF:</strong> ${data.encf}</p>
          <p><strong>${t("status")}:</strong> ${data.estado || "—"}</p>
          <p><strong>${t("total")}:</strong> RD$ ${data.monto_total}</p>
          <p><strong>${t("rfce")}:</strong> ${data.used_rfce ? t("yes") : t("no")}</p>
          <p><strong>${t("security_code")}:</strong> ${data.codigo_seguridad}</p>
          <p><strong>${t("signature_date")}:</strong> ${data.fecha_firma}</p>
          ${data.track_id ? `<p><strong>TrackId:</strong> ${data.track_id}</p>` : ""}
          ${data.error ? `<p><strong>${t("dgii_error")}:</strong> ${data.error}</p>` : ""}
          ${messages ? `<ul>${messages}</ul>` : ""}
          <p class="links">
            <a href="/invoices/${data.encf}/print?lang=${lang}" target="_blank">${t("print_view")}</a>
            <a href="/api/invoices/${data.encf}/xml">${t("download_xml")}</a>
            ${data.track_id ? `<a href="#" id="refreshStatus">${t("refresh_status")}</a>` : ""}
          </p>
        </div>
      </div>
    `;
    const refresh = document.getElementById("refreshStatus");
    if (refresh) {
      refresh.addEventListener("click", async (event) => {
        event.preventDefault();
        const res = await fetch(`/api/invoices/${data.encf}/status`);
        const updated = await res.json();
        if (!res.ok) {
          showError(updated.detail || updated);
          return;
        }
        showResult(updated);
      });
    }
  }

  document.addEventListener("languagechange", () => {
    if (lastResult) showResult(lastResult);
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorsEl.classList.add("hidden");
    try {
      const payload = buildPayload();
      const res = await fetch("/api/invoices", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        showError(data.detail || data);
        return;
      }
      showResult(data);
      const cfgRes = await fetch("/api/config");
      const cfg = await cfgRes.json();
      document.getElementById("nextInvoiceLabel").textContent =
        cfg.next_invoice_number || "—";
      await loadInvoiceList();
    } catch (err) {
      showError(err.message || String(err));
    }
  });

  loadConfig().catch((err) => showError(err.message || String(err)));
})();
