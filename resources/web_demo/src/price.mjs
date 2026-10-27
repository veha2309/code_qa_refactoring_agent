export function invoiceTotal(amount, taxRate = 0.1) {
  return Math.round(amount * (1 + taxRate) * 100) / 100;
}

export function invoiceLabel(amount) {
  return `Total: ${invoiceTotal(amount).toFixed(2)}`;
}

export function shippingCost(weight) {
  return weight * 2;
}
