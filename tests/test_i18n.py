from app.config import Settings
from app.i18n import default_language, language_options, translations_for


def test_available_languages_from_env_string(tmp_path, p12_path):
    settings = Settings(
        DGII_ENV="testecf",
        DGII_P12_PATH=p12_path,
        DGII_P12_PASSWORD="secret",
        ISSUER_RNC="131880738",
        ISSUER_NAME="EMPRESA DE PRUEBA SRL",
        ISSUER_ADDRESS="Av. Test 1",
        DATA_DIR=tmp_path / "data",
        AVAILABLE_LANGUAGES="en,es,fr,de,ru,it",
    )
    assert settings.available_languages == ["en", "es", "fr", "de", "ru", "it"]
    assert default_language(settings.available_languages) == "en"
    options = language_options(settings.available_languages)
    assert [item["code"] for item in options] == settings.available_languages
    assert options[1]["label"] == "Español"
    packs = translations_for(settings.available_languages)
    assert packs["es"]["emit"] == "Emitir e-CF"
    assert packs["fr"]["language"] == "Langue"
    assert packs["de"]["back"] == "Zurück"
    assert packs["ru"]["print"] == "Печать"
    assert packs["it"]["buyer"] == "Acquirente"


def _config_client(settings, monkeypatch, languages: str):
    from fastapi.testclient import TestClient

    from app.api import app
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DGII_ENV", settings.dgii_env)
    monkeypatch.setenv("DGII_P12_PATH", str(settings.dgii_p12_path))
    monkeypatch.setenv("DGII_P12_PASSWORD", settings.dgii_p12_password)
    monkeypatch.setenv("ISSUER_RNC", settings.issuer_rnc)
    monkeypatch.setenv("ISSUER_NAME", settings.issuer_name)
    monkeypatch.setenv("ISSUER_ADDRESS", settings.issuer_address)
    monkeypatch.setenv("DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("DATABASE_PATH", str(settings.data_dir / "invoices.db"))
    monkeypatch.setenv("AVAILABLE_LANGUAGES", languages)
    get_settings.cache_clear()
    return TestClient(app)


def test_api_config_exposes_languages(settings, monkeypatch):
    with _config_client(settings, monkeypatch, "en,es,fr") as client:
        response = client.get("/api/config")
    from app.config import get_settings

    get_settings.cache_clear()
    assert response.status_code == 200
    data = response.json()
    assert [item["code"] for item in data["available_languages"]] == ["en", "es", "fr"]
    assert data["default_language"] == "en"
    assert data["translations"]["es"]["emit"] == "Emitir e-CF"


def test_api_config_single_language(settings, monkeypatch):
    with _config_client(settings, monkeypatch, "es") as client:
        response = client.get("/api/config")
        page = client.get("/")
    from app.config import get_settings

    get_settings.cache_clear()
    assert response.status_code == 200
    data = response.json()
    assert [item["code"] for item in data["available_languages"]] == ["es"]
    assert data["default_language"] == "es"
    assert "es" in data["translations"]
    assert page.status_code == 200
    assert 'id="languageSelect"' in page.text
    assert 'class="lang-switcher"' in page.text


def test_language_switcher_js_hides_when_single(tmp_path):
    """Exercise static/i18n.js hide/show rules with a minimal DOM stub."""
    import subprocess
    import textwrap
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    script = tmp_path / "run_i18n_switcher.js"
    script.write_text(
        textwrap.dedent(
            f"""
            const fs = require("fs");
            const {{ JSDOM }} = require("jsdom");

            const html = `
              <html><body>
                <label class="lang-switcher">
                  <span data-i18n="language">Language</span>
                  <select id="languageSelect"></select>
                </label>
                <h1 data-i18n="emit">Emit</h1>
              </body></html>
            `;
            const dom = new JSDOM(html, {{ url: "http://localhost/", runScripts: "outside-only" }});
            const {{ window }} = dom;
            global.window = window;
            global.document = window.document;
            global.localStorage = window.localStorage;

            const src = fs.readFileSync({str(root / "static" / "i18n.js")!r}, "utf8");
            window.eval(src);

            const single = window.DgiiI18n.initFromConfig({{
              available_languages: [{{ code: "es", label: "Español" }}],
              default_language: "es",
              translations: {{ es: {{ language: "Idioma", emit: "Emitir e-CF" }} }},
            }});
            const switcher = document.querySelector(".lang-switcher");
            if (single !== "es") throw new Error("expected es, got " + single);
            if (!switcher.hidden || !switcher.classList.contains("hidden")) {{
              throw new Error("switcher should be hidden for one language");
            }}
            if (document.querySelector("h1").textContent !== "Emitir e-CF") {{
              throw new Error("single-language translation not applied");
            }}

            const multi = window.DgiiI18n.initFromConfig({{
              available_languages: [
                {{ code: "en", label: "English" }},
                {{ code: "es", label: "Español" }},
              ],
              default_language: "en",
              translations: {{
                en: {{ language: "Language", emit: "Emit e-CF" }},
                es: {{ language: "Idioma", emit: "Emitir e-CF" }},
              }},
            }});
            if (multi !== "en" && multi !== "es") throw new Error("unexpected lang " + multi);
            if (switcher.hidden || switcher.classList.contains("hidden")) {{
              throw new Error("switcher should be visible for multiple languages");
            }}
            const select = document.getElementById("languageSelect");
            if (select.options.length !== 2) {{
              throw new Error("expected 2 options, got " + select.options.length);
            }}
            window.DgiiI18n.setLanguage("es");
            if (window.DgiiI18n.current !== "es") throw new Error("setLanguage failed");
            if (document.querySelector("h1").textContent !== "Emitir e-CF") {{
              throw new Error("switch did not translate emit");
            }}
            console.log("ok");
            """
        ),
        encoding="utf-8",
    )
    install = subprocess.run(
        ["npm", "install", "--no-save", "jsdom@24"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    if install.returncode != 0:
        # Fall back: assert the hide rule is present in source when jsdom cannot install.
        source = (root / "static" / "i18n.js").read_text(encoding="utf-8")
        assert "state.languages.length > 1" in source
        assert 'classList.toggle("hidden", !showSwitcher)' in source
        return
    result = subprocess.run(
        ["node", str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "ok" in result.stdout
