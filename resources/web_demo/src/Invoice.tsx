import { invoiceLabel } from './price.mjs';

export function Invoice({ amount }: { amount: number }) {
  return <section><h2>Invoice</h2><p>{invoiceLabel(amount)}</p></section>;
}
