import { describe, expect, it } from "vitest";
import { productVersionCaption } from "./productVersion";

describe("productVersionCaption", () => {
  it("shows the release number without a plus suffix", () => {
    const cap = productVersionCaption({
      version: "0.2.10",
      revision: "abc1234",
      commits_ahead: 0,
      channel: "release",
      display: "0.2.10",
    });
    expect(cap.kind).toBe("发行");
    expect(cap.value).toBe("0.2.10");
    expect(cap.title).toContain("abc1234");
  });

  it("shows commits ahead for development builds", () => {
    const cap = productVersionCaption({
      version: "0.2.10",
      revision: "217f1c8",
      commits_ahead: 12,
      channel: "development",
      display: "0.2.10+12.g217f1c8",
    });
    expect(cap.kind).toBe("开发");
    expect(cap.value).toBe("0.2.10+12.g217f1c8");
    expect(cap.title).toContain("217f1c8");
  });
});
