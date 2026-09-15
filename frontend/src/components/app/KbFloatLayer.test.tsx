import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChannelFloatLayer } from "./ChannelFloatLayer";
import { KbFloatLayer } from "./KbFloatLayer";
import { MediaGalleryFloatLayer } from "./MediaGalleryFloatLayer";
import { MemoryFloatLayer } from "./MemoryFloatLayer";

vi.mock("../channels/ChannelPanel", () => ({
  ChannelPanel: () => <div>channel-content</div>,
}));

vi.mock("../media/MediaGalleryPanel", () => ({
  MediaGalleryPanel: () => <div>media-content</div>,
}));

vi.mock("../memory/MemoryPanel", () => ({
  MemoryPanel: () => <div>memory-content</div>,
}));

describe("KbFloatLayer", () => {
  it("renders the shared doc-float shell and closes from the backdrop", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { container } = render(
      <KbFloatLayer onClose={onClose}>
        <div>inner</div>
      </KbFloatLayer>,
    );
    expect(container.querySelector(".doc-float-backdrop")).not.toBeNull();
    expect(container.querySelector(".doc-float-panel")).not.toBeNull();
    expect(screen.getByText("inner")).toBeInTheDocument();
    await user.click(container.querySelector(".doc-float-backdrop")!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("can hide the backdrop like document focus mode", () => {
    const { container } = render(
      <KbFloatLayer onClose={() => undefined} showBackdrop={false}>
        <div>inner</div>
      </KbFloatLayer>,
    );
    expect(container.querySelector(".doc-float-backdrop")).toBeNull();
    expect(container.querySelector(".doc-float-panel")).not.toBeNull();
  });
});

describe("left-edge float layers share KbFloatLayer", () => {
  it("media gallery, memory, and channels all mount doc-float chrome", () => {
    const onClose = () => undefined;
    const media = render(
      <MediaGalleryFloatLayer directory="媒体/生成" onClose={onClose} />,
    );
    expect(media.container.querySelector(".doc-float-backdrop")).not.toBeNull();
    expect(media.container.querySelector(".doc-float-panel")).not.toBeNull();
    expect(media.getByText("media-content")).toBeInTheDocument();
    media.unmount();

    const memory = render(<MemoryFloatLayer onClose={onClose} />);
    expect(memory.container.querySelector(".doc-float-panel")).not.toBeNull();
    expect(memory.getByText("memory-content")).toBeInTheDocument();
    memory.unmount();

    const channels = render(<ChannelFloatLayer onClose={onClose} />);
    expect(channels.container.querySelector(".doc-float-backdrop")).not.toBeNull();
    expect(channels.container.querySelector(".doc-float-panel")).not.toBeNull();
    expect(channels.getByText("channel-content")).toBeInTheDocument();
  });
});
