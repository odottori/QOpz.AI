document.addEventListener("DOMContentLoaded", function () {

  // ── Sidebar toggle ──────────────────────────────────────
  const toggleBtn = document.createElement("button");
  toggleBtn.id = "sidebar-toggle";
  toggleBtn.title = "Apri/chiudi menu";
  toggleBtn.innerHTML = `<svg viewBox="0 0 24 24"><path d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"/></svg>`;
  document.body.appendChild(toggleBtn);

  if (localStorage.getItem("sidebar-hidden") === "1") {
    document.body.classList.add("sidebar-hidden");
  }

  toggleBtn.addEventListener("click", function () {
    document.body.classList.toggle("sidebar-hidden");
    localStorage.setItem(
      "sidebar-hidden",
      document.body.classList.contains("sidebar-hidden") ? "1" : "0"
    );
  });

  // ── Print button ────────────────────────────────────────
  const printBtn = document.createElement("button");
  printBtn.id = "print-btn";
  printBtn.title = "Stampa / Salva PDF questa pagina";
  printBtn.innerHTML = `<svg viewBox="0 0 24 24"><path d="M19 8H5c-1.66 0-3 1.34-3 3v6h4v4h12v-4h4v-6c0-1.66-1.34-3-3-3zm-3 11H8v-5h8v5zm3-7c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm-1-9H6v4h12V3z"/></svg>`;
  document.body.appendChild(printBtn);

  printBtn.addEventListener("click", function () {
    const wasClosed = document.body.classList.contains("sidebar-hidden");
    document.body.classList.remove("sidebar-hidden");
    setTimeout(function () {
      window.print();
      if (wasClosed) document.body.classList.add("sidebar-hidden");
    }, 150);
  });

  // ── Print-all button (guida completa) ───────────────────
  const printAllBtn = document.createElement("button");
  printAllBtn.id = "print-all-btn";
  printAllBtn.title = "Stampa / Salva PDF — Guida Completa";
  printAllBtn.innerHTML = `<svg viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>`;
  document.body.appendChild(printAllBtn);

  printAllBtn.addEventListener("click", function () {
    // Detect base path from current location
    const base = document.querySelector("base") ? document.querySelector("base").href : window.location.origin + "/";
    // Build URL to guida_completa page (works for both mkdocs serve and static build)
    const loc = window.location.pathname;
    const root = loc.replace(/\/[^/]*\/?$/, "/");
    window.open(root + "guida_completa/", "_blank");
  });

});
