/* Theme switch (light/dark) and the header of the layer panel. */
(function () {
  var STORAGE_KEY = "coverage-map-theme";
  var root = document.documentElement;

  function storedTheme() {
    try {
      var value = localStorage.getItem(STORAGE_KEY);
      return value === "dark" || value === "light" ? value : null;
    } catch (e) {
      return null;
    }
  }

  function systemTheme() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    var button = document.getElementById("cov-theme");
    if (button) {
      var label = theme === "dark" ? "Светлая тема" : "Тёмная тема";
      button.setAttribute("title", label);
      button.setAttribute("aria-label", label);
    }
  }

  // Set the theme before the first paint to avoid a light flash.
  applyTheme(storedTheme() || systemTheme());

  document.addEventListener("DOMContentLoaded", function () {
    var panel = document.querySelector(".leaflet-control-layers");
    var template = document.getElementById("cov-header-template");
    if (!panel || !template) return;

    panel.insertBefore(template.content.cloneNode(true), panel.firstChild);
    applyTheme(root.getAttribute("data-theme"));

    document.getElementById("cov-theme").addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      applyTheme(next);
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch (e) {
        /* private mode: the choice just isn't remembered */
      }
    });

    var collapse = document.getElementById("cov-collapse");
    function setCollapsed(collapsed) {
      panel.classList.toggle("cov-collapsed", collapsed);
      var label = collapsed ? "Показать слои" : "Скрыть слои";
      collapse.setAttribute("title", label);
      collapse.setAttribute("aria-label", label);
      collapse.setAttribute("aria-expanded", String(!collapsed));
    }
    collapse.addEventListener("click", function () {
      setCollapsed(!panel.classList.contains("cov-collapsed"));
    });
    // On phones the panel would cover the map, so it starts collapsed.
    setCollapsed(window.innerWidth < 640);
  });
})();
