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

  // ---------- modals (<dialog>) ----------
  document.querySelectorAll("[data-modal-open]").forEach((btn) => {
    btn.addEventListener("click", () => document.getElementById(btn.dataset.modalOpen)?.showModal());
  });
  document.querySelectorAll("dialog.base-modal-dialog").forEach((dlg) => {
    dlg.querySelectorAll("[data-modal-close]").forEach((b) => b.addEventListener("click", () => dlg.close()));
    // click on the dimmed backdrop closes the modal
    dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  });

  // ---------- confirmations ----------
  // <form data-confirm="text" data-confirm-title="..." data-confirm-ok="..." [data-confirm-danger]>
  // <a data-confirm="text" ...> works the same for links.
  const confirmDlg = document.getElementById("confirm-dialog");
  let onConfirm = null;
  const askConfirm = (el, action) => {
    if (!confirmDlg) return action();  // no modal on the page: just do it
    confirmDlg.querySelector("[data-confirm-title-slot]").textContent = el.dataset.confirmTitle || "Are you sure?";
    confirmDlg.querySelector("[data-confirm-text-slot]").textContent = el.dataset.confirm || "";
    const ok = confirmDlg.querySelector("[data-confirm-ok-slot]");
    ok.textContent = el.dataset.confirmOk || "Confirm";
    ok.classList.toggle("btn-danger-solid", el.hasAttribute("data-confirm-danger"));
    onConfirm = action;
    confirmDlg.showModal();
    ok.focus();
  };
  confirmDlg?.querySelector("[data-confirm-ok-slot]").addEventListener("click", () => {
    confirmDlg.close();
    const run = onConfirm;
    onConfirm = null;
    run?.();
  });

  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (!form.hasAttribute("data-confirm") || form.dataset.confirmed) return;
    e.preventDefault();
    askConfirm(form, () => { form.dataset.confirmed = "1"; form.submit(); });
  });

  document.addEventListener("click", (e) => {
    const link = e.target.closest("a[data-confirm]");
    if (!link) return;
    // data-confirm-if-dirty="#form": only ask when that form has unsaved changes
    const watched = link.dataset.confirmIfDirty && document.querySelector(link.dataset.confirmIfDirty);
    if (watched && !watched.dataset.dirty) return;
    e.preventDefault();
    askConfirm(link, () => { window.location.href = link.href; });
  });

  // mark forms dirty once something changes, so Cancel can warn about losing edits
  document.querySelectorAll("form[data-track-dirty]").forEach((f) => {
    const markDirty = () => { f.dataset.dirty = "1"; };
    f.addEventListener("input", markDirty);
    f.addEventListener("change", markDirty);
  });
});
