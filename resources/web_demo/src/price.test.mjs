import test from 'node:test';
import assert from 'node:assert/strict';
import { invoiceTotal, invoiceLabel, shippingCost } from './price.mjs';

test('invoice total includes tax', () => {
  assert.equal(invoiceTotal(100), 110);
});

test('invoice label shows rounded total', () => {
  assert.equal(invoiceLabel(50), 'Total: 55.00');
});

test('shipping price uses weight', () => {
  assert.equal(shippingCost(3), 6);
});
