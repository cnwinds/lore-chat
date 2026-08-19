export type TourStep = {
  id: string;
  title: string;
  body: string;
  anchor: string;
};

export const TOUR_STEPS: readonly TourStep[] = [
  {
    id: "tree",
    title: "这是聊出来的知识库",
    body: "左侧目录不是手工维护的。每一篇都来自一次真实对话，AI 判断该新建还是归入已有目录。",
    anchor: "kb-tree",
  },
  {
    id: "conversation",
    title: "点开看一次沉淀的全过程",
    body: "这条会话里，Lore 搜了网、比对了来源，最后把结论写成了知识库里的一篇笔记——都能展开看。",
    anchor: "highlight-conversation",
  },
  {
    id: "composer",
    title: "直接问它",
    body: "可以基于这份知识库提问。演示环境的对话不会被保存，放心试。",
    anchor: "composer",
  },
];

/** 演示访客每次进入页面都展示引导（不持久化「已看过」）。 */
export function shouldShowTour(isGuest: boolean): boolean {
  return isGuest;
}

/** 三步锚点均已挂到 DOM 且有布局尺寸，才开始引导。 */
export function areTourAnchorsReady(root: ParentNode = document): boolean {
  return TOUR_STEPS.every((step) => {
    const el = root.querySelector(`[data-demo-anchor="${step.anchor}"]`);
    if (!(el instanceof HTMLElement)) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  });
}
