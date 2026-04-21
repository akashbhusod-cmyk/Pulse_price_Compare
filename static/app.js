document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.querySelector("#q");
  if (searchInput) {
    searchInput.addEventListener("focus", () => {
      document.body.classList.add("searching");
    });

    searchInput.addEventListener("blur", () => {
      document.body.classList.remove("searching");
    });
  }

  document.querySelectorAll("[data-load-more-button]").forEach((button) => {
    const tableBlock = button.closest(".table-block");
    const container = tableBlock?.querySelector("[data-load-more-container]");
    if (!container) {
      return;
    }

    const items = Array.from(container.querySelectorAll("[data-load-more-item]"));
    const step = Number(button.dataset.step || container.dataset.initialItems || 5);
    let visibleCount = items.filter((item) => !item.hidden).length;

    const syncButton = () => {
      const hiddenItems = items.filter((item) => item.hidden).length;
      button.hidden = hiddenItems === 0;
      if (!button.hidden) {
        button.textContent = `Load more (${hiddenItems} left)`;
      }
    };

    button.addEventListener("click", () => {
      items.slice(visibleCount, visibleCount + step).forEach((item) => {
        item.hidden = false;
      });
      visibleCount = items.filter((item) => !item.hidden).length;
      syncButton();
    });

    syncButton();
  });
});
