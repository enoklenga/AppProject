(() => {
    "use strict";

    const shell = document.querySelector("[data-app-shell]");
    const toggle = document.querySelector("[data-sidebar-toggle]");
    const closeButtons = document.querySelectorAll("[data-sidebar-close]");
    const sidebar = document.querySelector("[data-sidebar]");
    const desktopMedia = window.matchMedia("(min-width: 1081px)");

    const focusableSelector = [
        "a[href]",
        "button:not([disabled])",
        "input:not([disabled])",
        "select:not([disabled])",
        "textarea:not([disabled])",
        "summary",
        '[tabindex]:not([tabindex="-1"])',
    ].join(",");

    const isOpen = () => Boolean(
        shell && shell.classList.contains("is-sidebar-open")
    );

    const setSidebarState = (open) => {
        if (!sidebar) return;
        if (desktopMedia.matches) {
            sidebar.removeAttribute("aria-hidden");
            return;
        }
        sidebar.setAttribute("aria-hidden", open ? "false" : "true");
    };

    const openSidebar = () => {
        if (!shell || !toggle || !sidebar) return;

        shell.classList.add("is-sidebar-open");
        document.body.classList.add("has-open-navigation");
        toggle.setAttribute("aria-expanded", "true");
        setSidebarState(true);

        const firstFocusable = sidebar.querySelector(focusableSelector);
        if (firstFocusable) {
            window.setTimeout(() => firstFocusable.focus(), 30);
        }
    };

    const closeSidebar = ({ restoreFocus = true } = {}) => {
        if (!shell || !toggle) return;

        shell.classList.remove("is-sidebar-open");
        document.body.classList.remove("has-open-navigation");
        toggle.setAttribute("aria-expanded", "false");
        setSidebarState(false);

        if (restoreFocus && !desktopMedia.matches) toggle.focus();
    };

    const trapSidebarFocus = (event) => {
        if (!sidebar || desktopMedia.matches || !isOpen() || event.key !== "Tab") {
            return;
        }

        const items = Array.from(sidebar.querySelectorAll(focusableSelector))
            .filter((node) => node.offsetParent !== null);
        if (!items.length) return;

        const first = items[0];
        const last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    };

    if (toggle) {
        toggle.addEventListener("click", () => {
            if (isOpen()) closeSidebar();
            else openSidebar();
        });
    }

    closeButtons.forEach((button) => {
        button.addEventListener("click", () => closeSidebar());
    });

    if (sidebar) {
        sidebar.addEventListener("click", (event) => {
            if (!desktopMedia.matches && event.target.closest("a")) {
                closeSidebar({ restoreFocus: false });
            }
        });
    }

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && isOpen()) closeSidebar();
        trapSidebarFocus(event);
    });

    const syncViewport = () => {
        if (desktopMedia.matches) {
            closeSidebar({ restoreFocus: false });
            setSidebarState(false);
        } else {
            setSidebarState(isOpen());
        }
    };

    if (desktopMedia.addEventListener) desktopMedia.addEventListener("change", syncViewport);
    else if (desktopMedia.addListener) desktopMedia.addListener(syncViewport);
    syncViewport();

    document.querySelectorAll("[data-message-dismiss]").forEach((button) => {
        button.addEventListener("click", () => {
            const message = button.closest("[data-message]");
            if (!message) return;
            message.classList.add("is-dismissing");
            window.setTimeout(() => message.remove(), 180);
        });
    });

    /* Make horizontally scrollable tables keyboard reachable only when needed. */
    const updateScrollableTables = () => {
        document.querySelectorAll(".table-wrapper").forEach((wrapper, index) => {
            const scrollable = wrapper.scrollWidth > wrapper.clientWidth + 1;
            wrapper.classList.toggle("is-scrollable", scrollable);

            if (scrollable) {
                wrapper.setAttribute("tabindex", "0");
                wrapper.setAttribute("role", "region");
                if (!wrapper.hasAttribute("aria-label")) {
                    wrapper.setAttribute("aria-label", `Tabella scorrevole ${index + 1}`);
                }
            } else {
                wrapper.removeAttribute("tabindex");
                wrapper.removeAttribute("role");
            }
        });
    };

    updateScrollableTables();
    window.addEventListener("resize", updateScrollableTables, { passive: true });
})();

/* UX operativa */
(() => {
    "use strict";

    const liveRegion = document.getElementById("ux-live-region");
    const confirmDialog = document.getElementById("ux-confirm-dialog");
    const confirmMessage = document.getElementById("ux-confirm-message");
    const confirmAccept = confirmDialog?.querySelector("[data-confirm-accept]");
    const confirmCancel = confirmDialog?.querySelector("[data-confirm-cancel]");

    let pendingConfirmation = null;

    const announce = (message) => {
        if (!liveRegion) return;
        liveRegion.textContent = "";
        window.setTimeout(() => {
            liveRegion.textContent = message;
        }, 25);
    };

    const isLogoutForm = (form) => {
        const action = form.getAttribute("action") || "";
        return /\/logout\/?(?:\?|$)/.test(action);
    };

    const hasEditableFields = (form) => Boolean(
        form.querySelector(
            'input:not([type="hidden"]):not([type="submit"]):not([type="button"]), select, textarea'
        )
    );

    const needsConfirmation = (form, submitter) => {
        if (isLogoutForm(form)) return false;
        if (form.hasAttribute("data-confirm-message")) return true;
        if (submitter?.hasAttribute("data-confirm-message")) return true;
        return Boolean(
            submitter?.matches(".button-danger, .link-button, [data-confirm]")
        );
    };

    const confirmationText = (form, submitter) => (
        submitter?.getAttribute("data-confirm-message") ||
        form.getAttribute("data-confirm-message") ||
        "Confermi questa operazione? L'azione potrebbe non essere reversibile."
    );

    const closeConfirmation = () => {
        if (!confirmDialog?.open) return;
        confirmDialog.close("cancel");
    };

    const openConfirmation = (form, submitter) => {
        const message = confirmationText(form, submitter);

        if (!confirmDialog || typeof confirmDialog.showModal !== "function") {
            if (window.confirm(message)) {
                form.dataset.uxConfirmed = "true";
                form.requestSubmit(submitter || undefined);
            }
            return;
        }

        pendingConfirmation = { form, submitter };
        if (confirmMessage) confirmMessage.textContent = message;
        confirmDialog.showModal();
        window.setTimeout(() => confirmCancel?.focus(), 20);
    };

    confirmAccept?.addEventListener("click", (event) => {
        event.preventDefault();
        const pending = pendingConfirmation;
        pendingConfirmation = null;
        confirmDialog?.close("confirm");

        if (!pending) return;
        pending.form.dataset.uxConfirmed = "true";
        pending.form.requestSubmit(pending.submitter || undefined);
    });

    confirmCancel?.addEventListener("click", (event) => {
        event.preventDefault();
        pendingConfirmation = null;
        closeConfirmation();
    });

    confirmDialog?.addEventListener("cancel", () => {
        pendingConfirmation = null;
    });

    const setSubmittingState = (form, submitter) => {
        form.dataset.uxSubmitting = "true";
        form.setAttribute("aria-busy", "true");
        form.dataset.dirty = "false";
        form.querySelector(".ux-unsaved-indicator")?.remove();

        if (submitter) {
            submitter.classList.add("is-loading");
            submitter.setAttribute("aria-disabled", "true");
        }

        announce("Operazione in corso.");
    };

    document.querySelectorAll("form").forEach((form) => {
        const method = (form.getAttribute("method") || "get").toLowerCase();
        const tracksChanges = (
            method === "post" &&
            !isLogoutForm(form) &&
            hasEditableFields(form) &&
            !form.hasAttribute("data-no-unsaved-warning")
        );

        if (tracksChanges) {
            form.dataset.dirty = "false";

            const markDirty = () => {
                if (form.dataset.uxSubmitting === "true") return;
                const wasDirty = form.dataset.dirty === "true";
                form.dataset.dirty = "true";

                if (!wasDirty) {
                    const actions = form.querySelector(".form-actions");
                    if (actions && !actions.querySelector(".ux-unsaved-indicator")) {
                        const indicator = document.createElement("span");
                        indicator.className = "ux-unsaved-indicator";
                        indicator.textContent = "Modifiche non salvate";
                        actions.prepend(indicator);
                    }
                    announce("Modifiche non salvate.");
                }
            };

            form.addEventListener("input", markDirty);
            form.addEventListener("change", markDirty);
        }

        form.addEventListener("submit", (event) => {
            const submitter = event.submitter || form.querySelector('[type="submit"]');

            if (form.dataset.uxSubmitting === "true") {
                event.preventDefault();
                announce("La richiesta è già in corso.");
                return;
            }

            if (
                form.dataset.uxConfirmed !== "true" &&
                needsConfirmation(form, submitter)
            ) {
                event.preventDefault();
                openConfirmation(form, submitter);
                return;
            }

            delete form.dataset.uxConfirmed;
            setSubmittingState(form, submitter);
        });
    });

    window.addEventListener("beforeunload", (event) => {
        const dirtyForm = Array.from(document.querySelectorAll('form[data-dirty="true"]'))
            .find((form) => form.dataset.uxSubmitting !== "true");

        if (!dirtyForm) return;
        event.preventDefault();
        event.returnValue = "";
    });

    /* Link server-side field errors to their controls and focus the first one. */
    const invalidControls = [];
    document.querySelectorAll(".errorlist").forEach((errorList, index) => {
        const field = errorList.closest(".field") || errorList.parentElement;
        const control = field?.querySelector("input, select, textarea");
        if (!control) return;

        field?.classList.add("has-error");
        control.setAttribute("aria-invalid", "true");

        if (!errorList.id) errorList.id = `field-error-${index + 1}`;
        const describedBy = new Set(
            (control.getAttribute("aria-describedby") || "")
                .split(/\s+/)
                .filter(Boolean)
        );
        describedBy.add(errorList.id);
        control.setAttribute("aria-describedby", Array.from(describedBy).join(" "));
        invalidControls.push(control);
    });

    if (invalidControls.length) {
        const first = invalidControls[0];
        window.setTimeout(() => {
            first.focus({ preventScroll: true });
            first.scrollIntoView({ behavior: "smooth", block: "center" });
            announce(`Controlla il modulo: ${invalidControls.length} campo${invalidControls.length === 1 ? "" : "i"} da correggere.`);
        }, 60);
    }
})();


/* =========================================================
   PASSWORD VISIBILITY TOGGLE
   ========================================================= */

(() => {
    "use strict";

    document.querySelectorAll("[data-password-toggle]").forEach((button) => {
        const wrapper = button.closest(".input-with-icon, .login-input");
        const input = wrapper?.querySelector('input[type="password"], input[type="text"]');
        const use = button.querySelector("use");
        if (!input) return;

        button.addEventListener("click", () => {
            const showing = input.type === "text";
            input.type = showing ? "password" : "text";
            button.setAttribute("aria-pressed", String(!showing));
            button.setAttribute(
                "aria-label",
                showing ? "Mostra password" : "Nascondi password"
            );
            if (use) {
                use.setAttribute("href", showing ? "#icon-eye" : "#icon-eye-off");
            }
        });
    });
})();
