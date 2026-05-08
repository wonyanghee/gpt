export type Product = {
  id: number;
  name: string;
  category: 'OUTERWEAR' | 'TOPS' | 'PANTS';
  line: string;
  price: number;
  badge: string;
};

export function ProductCard({ product }: { product: Product }) {
  return (
    <article className="card">
      <div className="media"><span className="badge">{product.badge}</span></div>
      <div className="meta">
        <div className="name">{product.name}</div>
        <div className="muted">{product.line}</div>
        <div className="price">${product.price}</div>
      </div>
    </article>
  );
}
