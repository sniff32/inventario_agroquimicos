/** Prueba de interacción REAL del buscador (sin navegador ni paquetes extra).
 * Protege contra errores que node --check no detecta, como referencias indefinidas
 * al seleccionar un producto y recalcular el total.
 */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

class Element {
  constructor(id = "") {
    this.id = id;
    this.children = [];
    this.listeners = {};
    this.textContent = "";
    this.value = "";
    this.hidden = false;
    this.disabled = false;
    this.dataset = {};
    this.className = "";
  }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  setAttribute(name, value) { this[name] = value; }
  closest(selector) {
    assert.equal(selector, "form");
    return elements.form;
  }
}

const ids = [
  "fermo-sale-picker", "sale-product-search", "sale-search-results",
  "sale-balance-id", "sale-quantity", "sale-type", "sale-add-button",
  "sale-product-card", "sale-product-info", "sale-product-warning",
  "sale-other-branches", "sale-extra-info", "sale-cart-raw", "sale-selected-name",
  "form",
];
const elements = Object.fromEntries(ids.map(id => [id, new Element(id)]));
elements["fermo-sale-picker"].dataset = {
  searchUrl: "/ventas/buscar/",
  detailPrefix: "/ventas/producto/",
  cartBranch: "",
  cartType: "MENUDEO",
};
elements["sale-cart-raw"].textContent = "[]";
elements["sale-type"].value = "MENUDEO";
elements["sale-quantity"].value = "5";
const product = {
  balance_id: 101, location_id: 201, product_id: 301,
  product: "Cable USB tipo B", sku: "DEMO-020",
  branch_id: 1, branch: "Almacén central",
  location: "Estante A", unit: "pieza", available: 10,
  retail_price: "45.00", wholesale_price: "41.40",
  wholesale_min_qty: 10, min_stock: 2,
  branches: [{name: "Almacén central", quantity: 10, selected: true}],
};
const other = {
  ...product, balance_id: 102, location_id: 202,
  branch_id: 2, branch: "Tienda Centro", location: "Repisa 2",
  available: 4,
  branches: [{name: "Almacén central", quantity: 10, selected: false},
             {name: "Tienda Centro", quantity: 4, selected: true}],
};
const fetch = async (url) => {
  if (url.startsWith("/ventas/buscar/"))
    return {ok: true, json: async () => ({results: [
      {...product, quantity: 10}, {...other, quantity: 4}
    ]})};
  if (url === "/ventas/producto/101/")
    return {ok: true, json: async () => product};
  if (url === "/ventas/producto/102/")
    return {ok: true, json: async () => other};
  throw Error("Fetch no previsto: " + url);
};
const document = {
  getElementById: id => {
    assert.ok(elements[id], "Falta nodo " + id);
    return elements[id];
  },
  createElement: tag => new Element(tag),
};
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  const source = fs.readFileSync("static/js/sales.js", "utf8");
  vm.runInNewContext(source, {
    document, fetch, setTimeout, clearTimeout, Intl, Number, JSON,
  }, {filename: "static/js/sales.js"});
  const search = elements["sale-product-search"];
  const results = elements["sale-search-results"];
  const picked = elements["sale-balance-id"];
  const card = elements["sale-product-card"];
  const button = elements["sale-add-button"];
  const qty = elements["sale-quantity"];
  const error = elements["sale-product-warning"];

  search.value = "020";
  search.listeners.input();
  await wait(280);
  assert.equal(results.hidden, false, "Los resultados deben aparecer al buscar");
  assert.equal(results.children.length, 2);

  await results.children[0].listeners.click();
  assert.equal(results.hidden, true, "Al seleccionar un resultado debe cerrarse el listado");
  assert.equal(picked.value, 101, "Debe seleccionarse el saldo específico");
  assert.equal(card.hidden, false, "La ficha del producto debe abrirse");
  assert.equal(button.disabled, false, "Debe poder agregar si existen 10 y solicita 5");
  assert.equal(elements["sale-product-info"].children.length, 4, "La ficha debe mostrar solo 4 datos esenciales");
  assert.ok(elements["sale-extra-info"].children.length >= 5, "Los demás datos quedan en desplegable");
  assert.equal(search.value, "DEMO-020 · Cable USB tipo B");

  qty.value = "11";
  qty.listeners.input();
  assert.equal(button.disabled, true, "No permitir 11 si quedan 10");
  assert.match(error.textContent, /Solo hay 10 unidades/);

  qty.value = "3";
  qty.listeners.input();
  assert.equal(button.disabled, false, "Reactivar al corregir la cantidad");

  search.value = "020";
  search.listeners.input();
  await wait(280);
  qty.value = "5";
  await results.children[1].listeners.click();
  assert.equal(results.hidden, true);
  assert.equal(picked.value, 102);
  assert.equal(button.disabled, true, "No permitir 5 si solo existen 4");
  qty.value = "2";
  qty.listeners.input();
  assert.equal(button.disabled, false);

  const ev = {preventDefault() {this.prevented = true;}, prevented: false};
  elements.form.listeners.submit(ev);
  assert.equal(ev.prevented, false, "Un producto válido debe poder enviarse al servidor");
  process.stdout.write("Interacción de buscador, selección, cierre, ficha y stock: OK\n");
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
