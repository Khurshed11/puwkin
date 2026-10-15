/* Мини-каталог Telegram: загрузка catalog.json и отрисовка */
(function () {
  "use strict";

  var tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      if (tg.themeParams && tg.themeParams.bg_color) {
        tg.setHeaderColor(tg.themeParams.bg_color);
      }
    } catch (e) { /* не критично */ }
  }

  var $status = document.getElementById("status");
  var $cats = document.getElementById("cats");
  var $grid = document.getElementById("grid");
  var data = null;
  var activeCat = "all";

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function priceHtml(p) {
    if (!p || p.price <= 0) {
      return '<span class="price unknown">Цена уточняйте</span>';
    }
    var n = Math.round(p.price).toLocaleString("ru-RU");
    return '<span class="price">' + n + " " + esc(p.currency) + "</span>";
  }

  function cardHtml(p) {
    var photo = p.photos && p.photos.length
      ? '<img class="photo" loading="lazy" src="' + esc(p.photos[0]) + '" alt="">'
      : '<div class="photo-placeholder">' + esc((p.name || "?").charAt(0)) + "</div>";
    var desc = p.description
      ? '<div class="desc">' + esc(p.description) + "</div>" +
        '<button class="more" type="button">показать полностью</button>'
      : "";
    return (
      '<article class="card" data-cat="' + p.category_id + '">' +
        photo +
        '<div class="body">' +
          "<h2>" + esc(p.name) + "</h2>" +
          priceHtml(p) +
          '<div class="meta">🚚 Доставка: ' + esc(p.delivery_price) +
            " · " + esc(p.delivery_range) + "</div>" +
          desc +
        "</div>" +
      "</article>"
    );
  }

  function renderCats() {
    var html = '<button class="chip active" data-id="all" type="button">Все</button>';
    data.categories.forEach(function (c) {
      html += '<button class="chip" data-id="' + c.id + '" type="button">' +
        esc(c.name) + "</button>";
    });
    $cats.innerHTML = html;
    $cats.querySelectorAll(".chip").forEach(function (btn) {
      btn.addEventListener("click", function () {
        activeCat = btn.dataset.id;
        $cats.querySelectorAll(".chip").forEach(function (b) {
          b.classList.toggle("active", b === btn);
        });
        renderGrid();
      });
    });
  }

  function renderGrid() {
    var items = data.products.filter(function (p) {
      return activeCat === "all" || String(p.category_id) === activeCat;
    });
    if (!items.length) {
      $grid.innerHTML = '<div class="status">В этой категории пока пусто</div>';
      return;
    }
    $grid.innerHTML = items.map(cardHtml).join("");
    $grid.querySelectorAll(".more").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var d = btn.previousElementSibling;
        var opened = d.classList.toggle("open");
        btn.textContent = opened ? "свернуть" : "показать полностью";
      });
    });
  }

  function renderHeader() {
    document.getElementById("shop-name").textContent = data.shop.name;
    document.getElementById("shop-meta").textContent =
      "⏱ Доставка " + data.shop.delivery + " · 💵 " + data.shop.currency;
    var link = document.getElementById("open-bot");
    if (data.shop.bot_url) link.href = data.shop.bot_url;
  }

  fetch("catalog.json", { cache: "no-store" })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (json) {
      data = json;
      $status.style.display = "none";
      renderHeader();
      renderCats();
      renderGrid();
      if (tg) tg.dataReady && tg.setData(JSON.stringify({ ready: true }));
    })
    .catch(function (e) {
      $status.textContent = "Не удалось загрузить каталог. Потяните вниз, чтобы обновить.";
      $status.classList.add("error");
      console.error(e);
    });
})();