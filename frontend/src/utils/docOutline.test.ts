import { describe, expect, it } from "vitest";
import {
  getShareDocOutlineActiveIndex,
  mapOutlineHeadingIds,
  parseDocOutline,
} from "./docOutline";

describe("mapOutlineHeadingIds", () => {
  it("maps sequential outline ids", () => {
    const items = parseDocOutline("# A\n\n## B");
    const mapped = mapOutlineHeadingIds(items);
    expect(mapped.map((i) => i.id)).toEqual(["outline-0", "outline-1"]);
  });
});

describe("getShareDocOutlineActiveIndex", () => {
  it("returns active heading based on scroll position", () => {
    const root = document.createElement("div");
    root.style.height = "200px";
    root.style.overflow = "auto";
    document.body.appendChild(root);

    const h1 = document.createElement("h1");
    h1.id = "outline-0";
    h1.textContent = "First";
    h1.style.height = "120px";
    const h2 = document.createElement("h2");
    h2.id = "outline-1";
    h2.textContent = "Second";
    h2.style.height = "400px";
    root.append(h1, h2);

    const items = mapOutlineHeadingIds(parseDocOutline("# First\n\n## Second"));
    Object.defineProperty(root, "scrollTop", { value: 100, writable: true });

    const active = getShareDocOutlineActiveIndex(root, items, 0);
    expect(active).toBe(1);

    root.remove();
  });
});
