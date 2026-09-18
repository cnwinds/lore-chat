import { useEffect, useState } from "react";
import { getHealth, type ProductVersion } from "../api";

export function useProductVersion() {
  const [product, setProduct] = useState<ProductVersion | null>(null);

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((body) => {
        if (!cancelled) setProduct(body.product ?? null);
      })
      .catch(() => {
        if (!cancelled) setProduct(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return product;
}
