/* FERMO · Búsqueda de ventas y validación previa (el servidor revalida al cerrar). */
(() => {
  "use strict";
  const root = document.getElementById("fermo-sale-picker");
  if (!root) return;
  const $ = id => document.getElementById(id);
  const search = $("sale-product-search");
  const list = $("sale-search-results");
  const selectedInput = $("sale-balance-id");
  const qtyInput = $("sale-quantity");
  const typeInput = $("sale-type");
  const submit = $("sale-add-button");
  const card = $("sale-product-card");
  const info = $("sale-product-info");
  const extraInfo = $("sale-extra-info");
  const warning = $("sale-product-warning");
  const branchResults = $("sale-other-branches");
  const searchUrl = root.dataset.searchUrl;
  const detailPrefix = root.dataset.detailPrefix;
  const cartBranch = root.dataset.cartBranch;
  const cartRows = JSON.parse($("sale-cart-raw").textContent);
  let selection = null;
  let timer = null;
  let querySeq = 0;

  const money = value => new Intl.NumberFormat("es-MX", {
    style: "currency", currency: "MXN"
  }).format(Number(value));
  const make = (tag, css = "", value = "") => {
    const el = document.createElement(tag);
    el.className = css;
    if (value) el.textContent = value;
    return el;
  };
  function setWarning(message, kind = "invalid") {
    warning.textContent = message;
    warning.hidden = !message;
    warning.className = "sale-live-warning " + kind;
  }
  function clearSelected() {
    selectedInput.value = "";
    selection = null;
    card.hidden = true;
    info.replaceChildren();
    extraInfo.replaceChildren();
    branchResults.replaceChildren();
    submit.disabled = true;
    setWarning("");
  }
  function metric(label, value, emphasis = false) {
    const cell = make("div", "sale-info-item" + (emphasis ? " emphasis" : ""));
    cell.append(make("small", "", label), make("strong", "", value));
    info.append(cell);
  }
  function detail(label, value) {
    const row = make("div", "sale-extra-row");
    row.append(make("span", "", label), make("strong", "", value));
    extraInfo.append(row);
  }
  function recalc() {
    submit.disabled = true;
    if (!selection) return;
    info.replaceChildren();
    extraInfo.replaceChildren();
    const qty = Number(qtyInput.value);
    const validQty = Number.isInteger(qty) && qty > 0;
    const chosenQty = validQty ? qty : 0;
    const mode = typeInput.value;
    const available = Number(selection.available);
    const sameLocation = cartRows.filter(line =>
      Number(line.product_id) === selection.product_id &&
      Number(line.location_id) === selection.location_id
    );
    const alreadyAtLocation = sameLocation.reduce((n, line) => n + Number(line.quantity), 0);
    const allAtLocation = chosenQty + alreadyAtLocation;

    // Solo líneas mayoristas suman al escalón de descuentos mayoristas.
    const wholesaleInCart = cartRows.filter(line =>
      Number(line.product_id) === selection.product_id && line.sale_type === "MAYOREO"
    ).reduce((n, line) => n + Number(line.quantity), 0);
    const wholesaleQty = wholesaleInCart + (mode === "MAYOREO" ? chosenQty : 0);
    const percent = mode === "MAYOREO" ? Math.min(10, Math.floor(wholesaleQty / 10) * 2) : 0;
    const hasWholesalePrice = selection.wholesale_price !== null;
    const base = mode === "MAYOREO" ? Number(selection.wholesale_price) : Number(selection.retail_price);
    const unitPrice = mode === "MAYOREO" && !hasWholesalePrice
      ? null
      : Math.round((base * (100 - percent) / 100 + Number.EPSILON) * 100) / 100;
    const branch = selection.branches.find(b => b.selected);
    const branchTotal = branch ? Number(branch.quantity) : available;
    const inBranch = cartRows.filter(line =>
      Number(line.product_id) === selection.product_id
    ).reduce((sum, line) => sum + Number(line.quantity), 0);
    const branchAfter = branchTotal - inBranch - chosenQty;

    metric("Ubicación de salida", selection.branch + " · " + selection.location);
    metric("Disponible en esta ubicación", available + " " + selection.unit +
      (alreadyAtLocation ? " · " + alreadyAtLocation + " en carrito" : ""), true);
    metric("Precio unitario " + (mode === "MAYOREO" ? "mayoreo" : "menudeo"),
      unitPrice === null ? "Sin configurar" : money(unitPrice));
    metric("Importe de este renglón",
      validQty && unitPrice !== null ? money(unitPrice * qty) : "—", true);

    detail("Código", selection.sku);
    detail("Disponible en sucursal", branchTotal + " " + selection.unit);
    detail("Precio menudeo", money(selection.retail_price));
    detail("Precio base mayoreo", hasWholesalePrice ? money(selection.wholesale_price) : "Sin configurar");
    detail("Mínimo mayoreo", selection.wholesale_min_qty + " " + selection.unit);
    detail("Escalón de descuento", mode === "MAYOREO"
      ? percent + "% sobre " + wholesaleQty + " uds. mayoristas del mismo SKU"
      : "No aplica en menudeo");

    if (!validQty) return setWarning("Ingresa una cantidad entera mayor a cero.");
    if (cartRows.length && Number(cartBranch) !== selection.branch_id) {
      return setWarning("Este carrito pertenece a otra sucursal. Termínalo o vacíalo antes de cambiar de tienda.");
    }
    if (allAtLocation > available) {
      return setWarning("Solo hay " + available + " unidades en esta ubicación; " +
        alreadyAtLocation + " ya están en el carrito entre ambas modalidades.");
    }
    if (mode === "MAYOREO" && !hasWholesalePrice) {
      return setWarning("Configura el precio mayorista antes de agregar este artículo.");
    }
    // Se puede completar un mínimo mayorista desde varias repisas, por eso
    // aceptamos renglones parciales en el carrito, pero no confirmamos aún.
    if (mode === "MAYOREO" && wholesaleQty < Number(selection.wholesale_min_qty)) {
      const missing = Number(selection.wholesale_min_qty) - wholesaleQty;
      setWarning("Mayoreo pendiente: agrega " + missing +
        " unidades mayoristas más de este producto antes de confirmar.", "valid");
    } else if (branchAfter <= Number(selection.min_stock)) {
      setWarning("Atención: esta sucursal quedaría con " + branchAfter +
        " unidades, en nivel de reposición.", "valid");
    } else {
      setWarning("");
    }
    submit.disabled = false;
  }

  async function selectBalance(id) {
    clearTimeout(timer);
    ++querySeq;
    list.hidden = true;
    submit.disabled = true;
    selectedInput.value = "";
    selection = null;
    setWarning("");
    try {
      const response = await fetch(detailPrefix + encodeURIComponent(id) + "/", {
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("No se pudieron consultar las existencias.");
      selection = await response.json();
      selectedInput.value = selection.balance_id;
      card.hidden = false;
      $("sale-selected-name").textContent = selection.product;
      branchResults.replaceChildren();
      selection.branches.forEach(store => {
        const row = make("div", "other-branch-stock" + (store.selected ? " selected" : ""));
        row.append(make("span", "", store.name), make("strong", "", store.quantity + " uds."));
        branchResults.append(row);
      });
      search.value = selection.sku + " · " + selection.product;
      recalc();
    } catch (error) {
      clearSelected();
      setWarning(error.message);
    }
  }

  async function findProducts() {
    const current = ++querySeq;
    try {
      const response = await fetch(searchUrl + "?q=" + encodeURIComponent(search.value.trim()), {
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("No se pudo completar la búsqueda.");
      const {results} = await response.json();
      if (current !== querySeq) return;
      list.replaceChildren();
      for (const item of results) {
        const button = make("button", "sale-search-item");
        button.type = "button";
        button.setAttribute("role", "option");
        const lhs = make("span");
        lhs.append(
          make("strong", "", item.sku + " · " + item.product),
          make("small", "", item.branch + " · " + item.location)
        );
        const rhs = make("span", "sale-search-stock",
          item.quantity + " uds. · " + money(item.retail_price));
        button.append(lhs, rhs);
        button.addEventListener("click", () => selectBalance(item.balance_id));
        list.append(button);
      }
      if (!results.length) {
        list.append(make("div", "sale-no-results", "Sin resultados con existencias disponibles."));
      }
      list.hidden = false;
    } catch (error) {
      if (current === querySeq) {
        list.replaceChildren(make("div", "sale-no-results", error.message));
        list.hidden = false;
      }
    }
  }

  search.addEventListener("input", () => {
    clearSelected();
    clearTimeout(timer);
    timer = setTimeout(findProducts, 200);
  });
  search.addEventListener("focus", () => {
    if (!search.value || !selectedInput.value) findProducts();
  });
  qtyInput.addEventListener("input", recalc);
  typeInput.addEventListener("change", recalc);
  root.closest("form").addEventListener("submit", event => {
    recalc();
    if (submit.disabled || !selectedInput.value) event.preventDefault();
  });
  clearSelected();
})();
