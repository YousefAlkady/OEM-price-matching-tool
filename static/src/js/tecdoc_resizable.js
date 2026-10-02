/** @odoo-module **/
/**
 * tecdoc_resizable.js
 * ───────────────────
 * Drag-to-resize for the TecDoc Specs tab panels in the Odoo backend.
 * Written as an Odoo 17 ES module so it is bundled correctly.
 *
 * Watches the DOM for .tecdoc-resizer elements (added by the
 * product_template_views.xml view) and wires up mouse drag logic
 * so the user can resize the Alternative Parts and Compatible Vehicles
 * panels by dragging the divider between them.
 */

function initResizer(resizer) {
    if (resizer._resizerReady) return;
    resizer._resizerReady = true;

    const container  = resizer.closest(".tecdoc-split-container");
    const leftPanel  = container.querySelector(".tecdoc-panel-left");
    const rightPanel = container.querySelector(".tecdoc-panel-right");

    let isResizing = false;
    let startX     = 0;
    let startLeftW = 0;

    resizer.addEventListener("mousedown", (e) => {
        isResizing = true;
        startX     = e.clientX;
        startLeftW = leftPanel.getBoundingClientRect().width;
        document.body.style.cursor     = "col-resize";
        document.body.style.userSelect = "none";
        e.preventDefault();
    });

    document.addEventListener("mousemove", (e) => {
        if (!isResizing) return;
        const dx         = e.clientX - startX;
        const totalW     = container.getBoundingClientRect().width;
        const resizerW   = resizer.getBoundingClientRect().width;
        const available  = totalW - resizerW;
        const newLeftPct = Math.min(85, Math.max(15, ((startLeftW + dx) / available) * 100));
        leftPanel.style.flex  = `0 0 ${newLeftPct}%`;
        rightPanel.style.flex = `0 0 ${100 - newLeftPct}%`;
    });

    document.addEventListener("mouseup", () => {
        if (!isResizing) return;
        isResizing = false;
        document.body.style.cursor     = "";
        document.body.style.userSelect = "";
    });
}

document.addEventListener("DOMContentLoaded", () => {
    const observer = new MutationObserver(() => {
        document.querySelectorAll(".tecdoc-resizer").forEach(initResizer);
    });

    if (document.body) {
        observer.observe(document.body, { childList: true, subtree: true });
    }

    document.querySelectorAll(".tecdoc-resizer").forEach(initResizer);
});
