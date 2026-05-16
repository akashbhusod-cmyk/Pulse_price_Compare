document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.querySelector("#q");
  const searchForm = document.querySelector("[data-search-form]");
  const searchButton = document.querySelector("[data-search-button]");
  const offerGrid = document.querySelector("[data-offer-grid]");
  const sortButtons = Array.from(document.querySelectorAll("[data-sort-button]"));
  const sortHeading = document.querySelector("[data-sort-heading]");
  const offerAnalysisData = document.querySelector("#offer-analysis-data");

  const formatCurrency = (value) => `Rs. ${Math.round(value).toLocaleString("en-IN")}`;

  const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

  const renderPriceCurve = (container, offers) => {
    if (!container || offers.length === 0) {
      return;
    }

    const width = 760;
    const height = 280;
    const padding = 28;
    const prices = offers.map((offer) => Number(offer.price || 0));
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...prices);
    const priceRange = Math.max(1, maxPrice - minPrice);
    const stepX = offers.length > 1 ? (width - padding * 2) / (offers.length - 1) : 0;

    const points = offers.map((offer, index) => {
      const price = Number(offer.price || 0);
      const x = padding + stepX * index;
      const y = height - padding - ((price - minPrice) / priceRange) * (height - padding * 2);
      return {
        x,
        y,
        price,
        platform: offer.platform,
        title: offer.title,
      };
    });
    const lastPoint = points[points.length - 1] || { x: padding };

    const linePath = points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
    const areaPath = `${linePath} L ${lastPoint.x} ${height - padding} L ${points[0]?.x ?? padding} ${height - padding} Z`;
    const labels = [
      { text: formatCurrency(maxPrice), y: padding + 8 },
      { text: formatCurrency((maxPrice + minPrice) / 2), y: height / 2 },
      { text: formatCurrency(minPrice), y: height - padding },
    ];

    container.innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" class="analytics-svg" role="img" aria-label="Price curve analysis chart">
        <defs>
          <linearGradient id="priceAreaGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="rgba(191, 91, 44, 0.46)"></stop>
            <stop offset="100%" stop-color="rgba(191, 91, 44, 0.05)"></stop>
          </linearGradient>
        </defs>
        <rect x="0" y="0" width="${width}" height="${height}" rx="22" fill="rgba(255,255,255,0.28)"></rect>
        ${labels.map((label) => `
          <line x1="${padding}" y1="${label.y}" x2="${width - padding}" y2="${label.y}" stroke="rgba(24, 32, 34, 0.08)" stroke-dasharray="5 8"></line>
          <text x="${padding}" y="${label.y - 10}" fill="#5f6b6c" font-size="12">${label.text}</text>
        `).join("")}
        <path d="${areaPath}" fill="url(#priceAreaGradient)"></path>
        <path d="${linePath}" fill="none" stroke="#bf5b2c" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></path>
        ${points.map((point) => `
          <circle cx="${point.x}" cy="${point.y}" r="5.5" fill="#fff7ef" stroke="#8f3f18" stroke-width="3">
            <title>${point.platform}: ${point.title} - ${formatCurrency(point.price)}</title>
          </circle>
        `).join("")}
      </svg>
    `;
  };

  const renderPlatformBars = (container, offers) => {
    if (!container || offers.length === 0) {
      return;
    }

    const cheapestByPlatform = new Map();
    offers.forEach((offer) => {
      const current = cheapestByPlatform.get(offer.platform);
      if (!current || Number(offer.price || 0) < Number(current.price || 0)) {
        cheapestByPlatform.set(offer.platform, offer);
      }
    });

    const rows = [...cheapestByPlatform.values()]
      .sort((left, right) => Number(left.price || 0) - Number(right.price || 0))
      .slice(0, 5);
    const highest = Math.max(...rows.map((row) => Number(row.price || 0)));

    container.innerHTML = rows.map((row) => {
      const value = Number(row.price || 0);
      const width = clamp((value / Math.max(highest, 1)) * 100, 10, 100);
      return `
        <div class="platform-bar-row">
          <div class="platform-bar-head">
            <strong>${row.platform}</strong>
            <span>${formatCurrency(value)}</span>
          </div>
          <div class="platform-bar-track">
            <div class="platform-bar-fill" style="width: ${width}%"></div>
          </div>
          <p>${row.title}</p>
        </div>
      `;
    }).join("");
  };

  const renderInsightPanel = (container, offers) => {
    if (!container || offers.length === 0) {
      return;
    }

    const prices = offers.map((offer) => Number(offer.price || 0));
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...prices);
    const averagePrice = prices.reduce((sum, value) => sum + value, 0) / prices.length;
    const savingsLeaders = offers.filter((offer) => Number(offer.savings_amount || 0) > 0).length;
    const spread = maxPrice - minPrice;

    const insights = [
      {
        label: "Price spread",
        value: formatCurrency(spread),
        note: "Difference between the cheapest and highest current result",
      },
      {
        label: "Average market price",
        value: formatCurrency(averagePrice),
        note: "Good baseline for judging whether a listing is actually cheap",
      },
      {
        label: "Offers with savings",
        value: `${savingsLeaders}/${offers.length}`,
        note: "Listings that include discount metadata or old-price context",
      },
    ];

    container.innerHTML = insights.map((insight) => `
      <article class="insight-card">
        <span>${insight.label}</span>
        <strong>${insight.value}</strong>
        <p>${insight.note}</p>
      </article>
    `).join("");
  };

  if (offerAnalysisData) {
    try {
      const offers = JSON.parse(offerAnalysisData.textContent || "[]");
      renderPriceCurve(document.querySelector('[data-chart="price-curve"]'), offers);
      renderPlatformBars(document.querySelector('[data-chart="platform-bars"]'), offers);
      renderInsightPanel(document.querySelector('[data-chart="insight-panel"]'), offers);
    } catch (error) {
      console.error("Failed to render analytics charts", error);
    }
  }

  if (searchInput) {
    searchInput.addEventListener("focus", () => {
      document.body.classList.add("searching");
    });

    searchInput.addEventListener("blur", () => {
      document.body.classList.remove("searching");
    });
  }

  if (searchForm && searchButton) {
    searchForm.addEventListener("submit", () => {
      searchButton.textContent = "Searching...";
      searchButton.disabled = true;
      searchButton.classList.add("is-loading");
    });
  }

  if (offerGrid && sortButtons.length > 0) {
    const offerCards = Array.from(offerGrid.querySelectorAll("[data-offer-card]"));
    const sortLabels = {
      price: "Best price first",
      savings: "Highest savings first",
    };

    /**
     * @param {"price" | "savings"} sortBy
     */
    const sortOffers = (sortBy) => {
      const sortedCards = [...offerCards].sort((leftCard, rightCard) => {
        const leftPrice = Number(leftCard.dataset.price || 0);
        const rightPrice = Number(rightCard.dataset.price || 0);
        const leftSavings = Number(leftCard.dataset.savings || 0);
        const rightSavings = Number(rightCard.dataset.savings || 0);
        const leftTitle = leftCard.dataset.title || "";
        const rightTitle = rightCard.dataset.title || "";

        if (sortBy === "savings") {
          return (
            rightSavings - leftSavings ||
            leftPrice - rightPrice ||
            leftTitle.localeCompare(rightTitle)
          );
        }

        return (
          leftPrice - rightPrice ||
          rightSavings - leftSavings ||
          leftTitle.localeCompare(rightTitle)
        );
      });

      sortedCards.forEach((card) => {
        offerGrid.appendChild(card);
      });

      if (sortHeading) {
        sortHeading.textContent = sortLabels[sortBy];
      }

      sortButtons.forEach((button) => {
        button.classList.toggle("is-active", button.dataset.sortBy === sortBy);
      });
    };

    sortButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const sortBy = button.dataset.sortBy === "savings" ? "savings" : "price";
        sortOffers(sortBy);
      });
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
