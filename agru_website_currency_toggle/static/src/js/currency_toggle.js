/* AGRU - Selector visual de moneda para el sitio web.
 *
 * v3:
 * - Arregla el parseo de números: Odoo (en formato chileno) siempre usa
 *   coma como separador DECIMAL y punto como separador de MILES.
 * - En el carrito (/shop/cart) el selector convierte cada línea, pero el
 *   bloque de Entrega/Subtotal/Impuestos/Total (lo que realmente se
 *   cobra) se detecta por su campo técnico y se deja SIEMPRE en pesos.
 * - El selector se oculta por completo en los pasos posteriores al
 *   carrito (dirección, pago, confirmación).
 *
 * v4:
 * - Fix doble conversión en /shop/cart y fix de reconversión cuando la
 *   ficha de producto pide el precio por AJAX (variantes/stock).
 *
 * v5:
 * - Se elimina por completo la idea de "guardar el HTML original y
 *   restaurarlo". Ahora se guarda SOLO el monto numérico puro
 *   (agruBaseAmount) y el HTML se reconstruye desde cero cada vez
 *   (símbolo + formato), tanto en modo principal como secundario. La
 *   versión anterior guardaba el HTML completo como "original"; si
 *   Odoo pisaba el número mientras el símbolo ya estaba convertido (o
 *   viceversa), ese Frankenstein quedaba grabado como si fuera el
 *   estado pristino, y reaparecía cada vez que se volvía a esa moneda.
 *   Con un número puro como única fuente de verdad, esto ya no puede
 *   pasar.
 * - El símbolo/código "principal" ahora lo manda el backend
 *   (agru-currency-main-code / -main-symbol), calculado con la MISMA
 *   lógica que ya sabe que el carrito es un caso especial (siempre
 *   CLP) — antes la plantilla recalculaba el símbolo principal leyendo
 *   website.currency_id directo, sin pasar por esa lógica, y en el
 *   carrito los dos botones del toggle terminaban mostrando la misma
 *   moneda.
 */
(function () {
    "use strict";

    function getMeta(name) {
        var el = document.querySelector('meta[name="' + name + '"]');
        return el ? el.getAttribute("content") : null;
    }

    var STORAGE_KEY = "_agru_display_currency"; // "main" | "secondary"

    // Solo se oculta en los pasos DESPUÉS del carrito (dirección, pago,
    // confirmación) — en el carrito mismo sí se muestra.
    var HIDDEN_PATH_PREFIXES = [
        "/shop/checkout", "/shop/confirmation",
        "/shop/payment", "/shop/address", "/shop/extra_info",
    ];

    // Campos que representan el TOTAL real a cobrar: nunca se tocan,
    // pase lo que pase con el selector, porque ya vienen forzados a
    // pesos por el otro módulo y eso es lo que se cobra de verdad.
    var LOCKED_FIELD_PATTERN = /amount_(total|untaxed|tax|delivery|undiscounted)/i;

    function isCheckoutPath() {
        var path = window.location.pathname;
        return HIDDEN_PATH_PREFIXES.some(function (p) {
            return path.indexOf(p) === 0;
        });
    }

    function isLockedTotalField(el) {
        var expr = el.getAttribute("data-oe-expression") || "";
        return LOCKED_FIELD_PATTERN.test(expr);
    }

    function init() {
        if (isCheckoutPath()) {
            return;
        }

        var rate = parseFloat(getMeta("agru-currency-rate"));
        var code = getMeta("agru-currency-code"); // moneda secundaria
        var symbol = getMeta("agru-currency-symbol") || code;
        var mainCode = getMeta("agru-currency-main-code") || "";
        var mainSymbol = getMeta("agru-currency-main-symbol") || "";

        if (!rate || !code || !mainCode) {
            return; // módulo sin par de monedas configurado: no hacer nada
        }

        var currentMode = window.localStorage.getItem(STORAGE_KEY) || "main";

        // Odoo (locale es_CL) siempre usa punto = miles, coma = decimal.
        function parseAmount(text) {
            var cleaned = text.replace(/[^\d.,\-]/g, "");
            cleaned = cleaned.replace(/\./g, ""); // quitar separador de miles
            cleaned = cleaned.replace(",", ".");   // coma = decimal
            return parseFloat(cleaned) || 0;
        }

        function formatAmount(amount, curCode) {
            var maxDigits = curCode === "CLP" ? 0 : 2;
            return amount.toLocaleString("es-CL", {
                minimumFractionDigits: 0,
                maximumFractionDigits: maxDigits,
            });
        }

        function buildHtml(amount, sym, curCode) {
            return sym + '\u00A0<span class="oe_currency_value">' +
                formatAmount(amount, curCode) + "</span>";
        }

        // Única fuente de verdad: un número puro (agruBaseAmount),
        // siempre en la moneda "principal" de la página. El HTML se
        // reconstruye desde cero en cada aplicación — nunca se guarda
        // ni se restaura un HTML completo, así que no hay forma de que
        // quede un símbolo viejo pegado a un monto nuevo.
        function applyToElement(el, forceRecapture) {
            if (isLockedTotalField(el)) {
                return; // Entrega/Subtotal/Impuestos/Total: siempre en pesos
            }
            if (forceRecapture) {
                // Odoo pisó el número por su cuenta (ej. recalcula el
                // precio al cambiar de variante/cantidad): lo que hay
                // ahora en pantalla es el valor real y crudo, en la
                // moneda principal. Se descarta lo cacheado.
                delete el.dataset.agruBaseAmount;
            }
            if (typeof el.dataset.agruBaseAmount === "undefined") {
                var valueEl = el.querySelector(".oe_currency_value");
                var rawText = valueEl ? valueEl.textContent : el.textContent;
                el.dataset.agruBaseAmount = String(parseAmount(rawText));
            }
            var amount = parseFloat(el.dataset.agruBaseAmount);
            if (isNaN(amount)) {
                return;
            }
            var newHtml = currentMode === "main"
                ? buildHtml(amount, mainSymbol, mainCode)
                : buildHtml(amount * rate, symbol, code);
            if (el.innerHTML !== newHtml) {
                el.innerHTML = newHtml;
            }
            // Huella de lo que ACABAMOS de escribir nosotros mismos, para
            // que el observer de más abajo pueda distinguir "esto lo
            // cambié yo" de "esto lo cambió otro script" sin entrar en
            // bucle infinito.
            el.dataset.agruLastAppliedHtml = el.innerHTML;
        }

        function scan(root) {
            (root || document)
                .querySelectorAll("[data-oe-type='monetary']")
                .forEach(function (el) { applyToElement(el, false); });
        }

        function setMode(mode) {
            currentMode = mode;
            window.localStorage.setItem(STORAGE_KEY, mode);
            scan(document);
            document.querySelectorAll(".agru-toggle-btn").forEach(function (btn) {
                btn.classList.toggle("active", btn.dataset.mode === mode);
            });
        }

        function buildToggle() {
            var wrap = document.createElement("div");
            wrap.className = "agru-currency-toggle";

            var btnMain = document.createElement("button");
            btnMain.type = "button";
            btnMain.className = "agru-toggle-btn";
            btnMain.dataset.mode = "main";
            btnMain.textContent = mainCode || "USD";

            var btnSecondary = document.createElement("button");
            btnSecondary.type = "button";
            btnSecondary.className = "agru-toggle-btn";
            btnSecondary.dataset.mode = "secondary";
            btnSecondary.textContent = code;

            [btnMain, btnSecondary].forEach(function (btn) {
                btn.addEventListener("click", function () {
                    setMode(btn.dataset.mode);
                });
            });

            wrap.appendChild(btnMain);
            wrap.appendChild(btnSecondary);
            document.body.appendChild(wrap);
        }

        buildToggle();
        setMode(currentMode);

        // El carrito, la ficha de producto y otras zonas se re-renderizan
        // vía AJAX al cambiar cantidades/variantes; se observa el DOM
        // para volver a aplicar el precio correcto cuando aparecen
        // montos nuevos (nodos agregados) o cuando Odoo pisa el NÚMERO
        // en el mismo nodo que ya existía (cambio de texto, sin agregar
        // nodos).
        var observer = new MutationObserver(function (mutations) {
            var toRecheck = [];
            mutations.forEach(function (m) {
                m.addedNodes.forEach(function (node) {
                    if (node.nodeType !== 1) {
                        return;
                    }
                    if (node.matches && node.matches("[data-oe-type='monetary']")) {
                        applyToElement(node, false);
                    }
                    scan(node);
                });
                var target = m.target.nodeType === 1 ? m.target : m.target.parentElement;
                var monetaryEl = target && target.closest("[data-oe-type='monetary']");
                if (monetaryEl && toRecheck.indexOf(monetaryEl) === -1) {
                    toRecheck.push(monetaryEl);
                }
            });
            toRecheck.forEach(function (el) {
                // Si lo que hay ahora coincide con lo último que
                // ESCRIBIMOS nosotros, no hay nada que hacer (evita
                // bucle infinito). Si no coincide, algún otro script
                // tocó el número: se vuelve a capturar y convertir
                // desde cero.
                if (el.innerHTML !== el.dataset.agruLastAppliedHtml) {
                    applyToElement(el, true);
                }
            });
        });
        observer.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true,
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
