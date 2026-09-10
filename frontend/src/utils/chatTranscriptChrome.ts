/** 消息区空态 / 加载态：没有气泡时保持居中欢迎，避免贴底的「加载中」留下大片空白。 */
export function chatTranscriptChrome(input: {
  loadingHistory: boolean;
  hasHistory: boolean;
  tipHasBody: boolean;
  streaming: boolean;
  timelineHasMore: boolean;
  loadingOlder: boolean;
}) {
  const emptyThread =
    !input.hasHistory && !input.tipHasBody && !input.streaming;
  return {
    showWelcome: emptyThread,
    showWelcomeLoading: emptyThread && input.loadingHistory,
    showLoadOlderHint:
      !emptyThread && (input.timelineHasMore || input.loadingOlder),
  };
}
