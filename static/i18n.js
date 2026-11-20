(function (global) {
  const STORAGE_KEY = "dgii_ecf_lang";

  const state = {
    languages: [],
    defaultLanguage: "en",
    translations: {},
    current: "en",
  };

  function t(key) {
    const pack = state.translations[state.current] || {};
    const fallback = state.translations.en || {};
    return pack[key] || fallback[key] || key;
  }

  function applyTranslations(root) {
    const scope = root || document;
    scope.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      if (!key) return;
      const value = t(key);
      if (el.tagName === "TITLE") {
        document.title = value;
      } else if (el.tagName === "OPTION") {
        el.textContent = value;
      } else if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
        el.placeholder = value;
      } else {
        el.textContent = value;
      }
    });
    document.documentElement.lang = state.current;
  }

  function setLanguage(code) {
    const available = state.languages.map((item) => item.code);
    const next = available.includes(code) ? code : state.defaultLanguage;
    state.current = next;
    localStorage.setItem(STORAGE_KEY, next);
    applyTranslations(document);
    document.dispatchEvent(
      new CustomEvent("languagechange", { detail: { language: next } })
    );
    return next;
  }

  function populateSwitcher(selectEl) {
    if (!selectEl) return;
    const switcher = selectEl.closest(".lang-switcher");
    const showSwitcher = state.languages.length > 1;
    if (switcher) {
      switcher.classList.toggle("hidden", !showSwitcher);
      switcher.hidden = !showSwitcher;
    }
    if (!showSwitcher) return;

    selectEl.innerHTML = "";
    state.languages.forEach((lang) => {
      const option = document.createElement("option");
      option.value = lang.code;
      option.textContent = lang.label;
      selectEl.appendChild(option);
    });
    selectEl.value = state.current;
    selectEl.addEventListener("change", () => setLanguage(selectEl.value));
  }

  function initFromConfig(cfg) {
    state.languages = cfg.available_languages || [{ code: "en", label: "English" }];
    state.defaultLanguage = cfg.default_language || state.languages[0].code;
    state.translations = cfg.translations || {};
    const saved = localStorage.getItem(STORAGE_KEY);
    const initial =
      saved && state.languages.some((item) => item.code === saved)
        ? saved
        : state.defaultLanguage;
    state.current = initial;
    populateSwitcher(document.getElementById("languageSelect"));
    applyTranslations(document);
    return state.current;
  }

  global.DgiiI18n = {
    t,
    setLanguage,
    applyTranslations,
    initFromConfig,
    get current() {
      return state.current;
    },
  };
})(window);
