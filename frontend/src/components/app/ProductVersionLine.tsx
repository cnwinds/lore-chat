import type { ProductVersion } from "../../api";
import { productVersionCaption } from "../../utils/productVersion";

type Props = {
  product: ProductVersion | null;
  className?: string;
};

export function ProductVersionLine({ product, className = "" }: Props) {
  if (!product) return null;
  const { kind, value, title } = productVersionCaption(product);
  return (
    <p
      className={`product-version-line ${className}`.trim()}
      title={title}
      aria-label={`${kind} ${value}`}
    >
      <span className="product-version-kind">{kind}</span>
      <span className="product-version-value">{value}</span>
    </p>
  );
}
