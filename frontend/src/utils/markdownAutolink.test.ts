import { describe, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { remarkTrimAutolinkUrls, trimAutolinkUrl } from "./markdownAutolink";

describe("trimAutolinkUrl", () => {
  it("stops before markdown emphasis and CJK after URL", () => {
    const raw =
      "https://store.steampowered.com/about/**（页面里有";
    expect(trimAutolinkUrl(raw)).toBe(
      "https://store.steampowered.com/about/",
    );
  });
});

describe("remarkTrimAutolinkUrls", () => {
  it("fixes Steam about link in bold-adjacent Chinese text", () => {
    const text =
      '网页版：**https://store.steampowered.com/about/**（页面里有 "Install Steam" 按钮）';
    const html = renderToStaticMarkup(
      React.createElement(
        ReactMarkdown,
        { remarkPlugins: [remarkGfm, remarkTrimAutolinkUrls] },
        text,
      ),
    );
    expect(html).toContain('href="https://store.steampowered.com/about/"');
    expect(html).not.toContain("%EF%BC%88");
  });
});
