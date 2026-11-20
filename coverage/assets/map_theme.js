/* Wires the side panel to the Leaflet layers and handles the light/dark theme. */
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
      var label = theme === "dark" ? "Включить светлую тему" : "Включить тёмную тему";
      button.setAttribute("title", label);
      button.setAttribute("aria-label", label);
    }
  }

  // Before the first paint, so a dark-theme user never sees a light flash.
  applyTheme(storedTheme() || systemTheme());

  function setupTheme() {
    applyTheme(root.getAttribute("data-theme"));
    document.getElementById("cov-theme").addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      applyTheme(next);
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch (e) {
        /* storage blocked: the choice is simply not remembered */
      }
    });
  }

  function setupLayers(panel, map) {
    var modes = panel.querySelectorAll('input[name="cov-mode"]');

    function showMode() {
      modes.forEach(function (input) {
        var layer = window[input.dataset.layer];
        if (!layer) return;
        if (input.checked) {
          map.addLayer(layer);
          // keep rings, outlines and markers above the coverage colours
          if (layer.bringToBack) layer.bringToBack();
        } else {
          map.removeLayer(layer);
        }
      });
      var active = panel.querySelector('input[name="cov-mode"]:checked');
      panel.querySelectorAll(".cov-scale").forEach(function (scale) {
        scale.hidden = !active || scale.dataset.scale !== active.value;
      });
    }
    modes.forEach(function (input) {
      input.addEventListener("change", showMode);
    });

    panel.querySelectorAll('input[type="checkbox"][data-layer]').forEach(function (input) {
      input.addEventListener("change", function () {
        var layer = window[input.dataset.layer];
        if (!layer) return;
        if (input.checked) map.addLayer(layer);
        else map.removeLayer(layer);
      });
    });
  }

  function setupSheet(panel) {
    var button = document.getElementById("cov-sheet");
    function setOpen(open) {
      panel.classList.toggle("is-open", open);
      button.setAttribute("aria-expanded", String(open));
      button.setAttribute("aria-label", open ? "Свернуть панель" : "Развернуть панель");
    }
    button.addEventListener("click", function () {
      setOpen(!panel.classList.contains("is-open"));
    });
    setOpen(false);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var panel = document.getElementById("cov-panel");
    if (!panel) return;
    var map = window[panel.dataset.map];
    setupTheme();
    setupSheet(panel);
    if (map) {
      setupLayers(panel, map);
      // the map element was resized by CSS for the docked panel
      map.invalidateSize();
    }
  });
})();
