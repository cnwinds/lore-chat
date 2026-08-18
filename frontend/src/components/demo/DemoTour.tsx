import { useEffect, useState } from "react";
import { useDemoCapability } from "../../hooks/useDemoCapability";
import { shouldShowTour, TOUR_SEEN_KEY, TOUR_STEPS } from "./demoTour";

export function DemoTour() {
  const { isDemo, canWrite } = useDemoCapability();
  const [stepIndex, setStepIndex] = useState(0);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const seen = localStorage.getItem(TOUR_SEEN_KEY);
    setVisible(shouldShowTour(!canWrite && isDemo, seen));
  }, [canWrite, isDemo]);

  useEffect(() => {
    if (!visible) return;
    const step = TOUR_STEPS[stepIndex];
    if (!step) return;
    const el = document.querySelector(`[data-demo-anchor="${step.anchor}"]`);
    if (el instanceof HTMLElement) {
      el.scrollIntoView({ block: "nearest", behavior: "smooth" });
      el.classList.add("demo-tour-highlight");
      return () => el.classList.remove("demo-tour-highlight");
    }
    return undefined;
  }, [visible, stepIndex]);

  if (!visible) return null;
  const step = TOUR_STEPS[stepIndex];
  if (!step) return null;

  const dismiss = () => {
    localStorage.setItem(TOUR_SEEN_KEY, "1");
    setVisible(false);
  };

  const next = () => {
    if (stepIndex >= TOUR_STEPS.length - 1) {
      dismiss();
      return;
    }
    setStepIndex((i) => i + 1);
  };

  return (
    <div className="demo-tour" role="dialog" aria-label="演示引导">
      <div className="demo-tour__card">
        <h3>{step.title}</h3>
        <p>{step.body}</p>
        <div className="demo-tour__actions">
          <button type="button" className="demo-tour__skip" onClick={dismiss}>
            跳过
          </button>
          <button type="button" className="demo-tour__next" onClick={next}>
            {stepIndex >= TOUR_STEPS.length - 1 ? "开始体验" : "下一步"}
          </button>
        </div>
        <div className="demo-tour__dots" aria-hidden>
          {TOUR_STEPS.map((s, i) => (
            <span
              key={s.id}
              className={`demo-tour__dot${i === stepIndex ? " active" : ""}`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
