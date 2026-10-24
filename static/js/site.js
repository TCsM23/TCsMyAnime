// Small progressive enhancements. The site works without this file.
document.addEventListener("DOMContentLoaded", () => {
  // Mobile menu toggle
  const toggle = document.querySelector("[data-nav-toggle]");
  const nav = document.querySelector("[data-nav]");
  if (toggle && nav) {
    toggle.addEventListener("click", () => {
      const open = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!open));
      nav.classList.toggle("is-open", !open);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && nav.classList.contains("is-open")) {
        nav.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
        toggle.focus();
      }
    });
  }

  // Header gets a shadow once you scroll
  const header = document.querySelector("[data-header]");
  if (header) {
    const onScroll = () => header.classList.toggle("is-scrolled", window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  // Stagger the entrance animation of cards and tiles (capped so long lists don't lag)
  document
    .querySelectorAll(".catalog-card-item, .main-watchlist-card, .stats-tiles-item, .stats-bar-row")
    .forEach((el, i) => el.style.setProperty("--i", Math.min(i, 14)));

  // Dismissable flash messages, auto-hide success ones
  document.querySelectorAll("[data-message]").forEach((msg) => {
    const close = () => {
      msg.classList.add("is-leaving");
      msg.addEventListener("animationend", () => msg.remove(), { once: true });
    };
    msg.querySelector("[data-message-close]")?.addEventListener("click", close);
    if (msg.classList.contains("is-success")) setTimeout(close, 5000);
  });
});
