(() => {
  "use strict";

  const navToggle = document.querySelector(".site-nav-toggle");
  const navLinks = document.querySelector(".site-nav-links");

  if (navToggle && navLinks) {
    navToggle.addEventListener("click", () => {
      const open = navLinks.classList.toggle("open");
      navToggle.setAttribute("aria-expanded", String(open));
      navToggle.textContent = open ? "×" : "☰";
    });

    navLinks.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        navLinks.classList.remove("open");
        navToggle.setAttribute("aria-expanded", "false");
        navToggle.textContent = "☰";
      });
    });
  }

  const healthcarePresentation = document.getElementById(
    "kapacita-bez-efektivity-zdravotnická-infrastruktura-a-zdravotní-výsledky-v-socialistickém-československu"
  );

  if (healthcarePresentation) {
    const heading = healthcarePresentation.querySelector("h3");
    if (heading && !heading.querySelector("a")) {
      const link = document.createElement("a");
      link.href = "healthcare-capacity.html";
      link.className = "ac-title-link";
      link.textContent = heading.textContent;
      heading.replaceChildren(link);
    }

    const linkParagraph = healthcarePresentation.querySelector("p:last-child");
    if (linkParagraph && !healthcarePresentation.querySelector('a[href="healthcare-capacity.html"]:not(.ac-title-link)')) {
      const details = document.createElement("a");
      details.href = "healthcare-capacity.html";
      details.className = "pill-link";
      details.textContent = "Preliminary results and figures";
      linkParagraph.prepend(details, " ");
    }
  }

  document.querySelectorAll('a[href^="http"]').forEach((link) => {
    const url = new URL(link.href, window.location.href);
    if (url.origin !== window.location.origin) {
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    }
  });

  const search = document.querySelector(".static-search");
  const searchInput = document.querySelector("#static-search-input");
  const searchResults = document.querySelector(".static-search-results");
  const searchTriggers = document.querySelectorAll(".search-trigger");
  const searchClose = document.querySelector(".static-search-close");
  let index = [];

  const closeSearch = () => {
    if (!search) return;
    search.classList.remove("open");
    search.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  };

  const openSearch = async () => {
    if (!search) return;
    search.classList.add("open");
    search.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    searchInput?.focus();
    if (!index.length) {
      try {
        const response = await fetch("search-index.json");
        index = await response.json();
      } catch (_) {
        index = [];
      }
    }
  };

  searchTriggers.forEach((trigger) => trigger.addEventListener("click", openSearch));
  searchClose?.addEventListener("click", closeSearch);
  search?.addEventListener("click", (event) => {
    if (event.target === search) closeSearch();
  });

  document.addEventListener("keydown", (event) => {
    if (search && (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openSearch();
    }
    if (event.key === "Escape") closeSearch();
  });

  searchInput?.addEventListener("input", () => {
    const query = searchInput.value.trim().toLowerCase();
    if (!searchResults) return;
    if (query.length < 2) {
      searchResults.innerHTML = '<p>Type at least two characters.</p>';
      return;
    }

    const terms = query.split(/\s+/).filter(Boolean);
    const matches = index
      .map((item) => {
        const haystack = `${item.title} ${item.text}`.toLowerCase();
        const score = terms.reduce((sum, term) => sum + (haystack.includes(term) ? 1 : 0), 0);
        return { ...item, score };
      })
      .filter((item) => item.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 8);

    searchResults.innerHTML = matches.length
      ? matches.map((item) => `
          <div class="static-search-result">
            <a href="${item.href}">${item.title}</a>
            <p>${item.excerpt}</p>
          </div>`).join("")
      : '<p>No matching pages found.</p>';
  });
})();
