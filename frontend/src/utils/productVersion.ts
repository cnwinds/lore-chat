import type { ProductVersion } from "../api";

export function productVersionCaption(product: ProductVersion): {
  kind: string;
  value: string;
  title: string;
} {
  const kind = product.channel === "release" ? "发行" : "开发";
  const value = product.display || product.version;
  const titleParts = [value];
  if (product.revision && !value.includes(product.revision)) {
    titleParts.push(product.revision);
  }
  return { kind, value, title: titleParts.filter(Boolean).join(" · ") };
}
