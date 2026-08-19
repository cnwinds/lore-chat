import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useDemoCapability } from "../../hooks/useDemoCapability";
import {
  areTourAnchorsReady,
  shouldShowTour,
  TOUR_STEPS,
} from "./demoTour";
import { measureAnchorBox, type HighlightBox } from "./demoTourGeometry";
import {
  computeTourCardLayout,
  type TourCardLayout,
} from "./demoTourPlacement";

/** 锚点迟迟不齐时仍展示，避免永久卡住 */
const TOUR_READY_FALLBACK_MS = 12_000;

export function DemoTour() {
  const { isDemo, canWrite } = useDemoCapability();
  const [stepIndex, setStepIndex] = useState(0);
  const [visible, setVisible] = useState(false);
  const [highlight, setHighlight] = useState<HighlightBox | null>(null);
  const [cardLayout, setCardLayout] = useState<TourCardLayout | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!shouldShowTour(!canWrite && isDemo)) {
      setVisible(false);
      return;
    }

    let cancelled = false;
    let revealed = false;

    const reveal = () => {
      if (cancelled || revealed) return;
      revealed = true;
      setStepIndex(0);
      setVisible(true);
    };

    const tryReady = () => {
      if (cancelled || revealed) return true;
      if (!areTourAnchorsReady()) return false;
      requestAnimationFrame(() => {
        if (cancelled || revealed) return;
        if (!areTourAnchorsReady()) return;
        reveal();
      });
      return true;
    };

    if (tryReady()) {
      return () => {
        cancelled = true;
      };
    }

    const obs = new MutationObserver(() => {
      if (tryReady()) obs.disconnect();
    });
    obs.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["data-demo-anchor", "class", "style"],
    });

    const poll = window.setInterval(() => {
      if (tryReady()) {
        obs.disconnect();
        window.clearInterval(poll);
      }
    }, 150);

    const fallback = window.setTimeout(() => {
      obs.disconnect();
      window.clearInterval(poll);
      reveal();
    }, TOUR_READY_FALLBACK_MS);

    return () => {
      cancelled = true;
      obs.disconnect();
      window.clearInterval(poll);
      window.clearTimeout(fallback);
    };
  }, [canWrite, isDemo]);

  useEffect(() => {
    if (!visible) {
      setHighlight(null);
      return;
    }
    const step = TOUR_STEPS[stepIndex];
    if (!step) return;

    const sync = () => setHighlight(measureAnchorBox(step.anchor));

    const el = document.querySelector(`[data-demo-anchor="${step.anchor}"]`);
    if (el instanceof HTMLElement) {
      el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    sync();
    const raf1 = requestAnimationFrame(() => {
      sync();
      requestAnimationFrame(sync);
    });

    window.addEventListener("resize", sync);
    window.addEventListener("scroll", sync, true);
    return () => {
      cancelAnimationFrame(raf1);
      window.removeEventListener("resize", sync);
      window.removeEventListener("scroll", sync, true);
      setHighlight(null);
    };
  }, [visible, stepIndex]);

  useLayoutEffect(() => {
    if (!visible || !highlight) {
      setCardLayout(null);
      return;
    }
    const el = cardRef.current;
    const layout = computeTourCardLayout(highlight, {
      viewportW: window.innerWidth,
      viewportH: window.innerHeight,
      cardW: el?.offsetWidth || 320,
      cardH: el?.offsetHeight || 180,
    });
    setCardLayout(layout);
  }, [visible, highlight, stepIndex]);

  if (!visible) return null;
  const step = TOUR_STEPS[stepIndex];
  if (!step) return null;

  const dismiss = () => {
    setVisible(false);
  };

  const next = () => {
    if (stepIndex >= TOUR_STEPS.length - 1) {
      dismiss();
      return;
    }
    setStepIndex((i) => i + 1);
  };

  const placement = cardLayout?.placement ?? "bottom";

  return (
    <div className="demo-tour" role="dialog" aria-label="演示引导">
      {highlight ? (
        <div
          key={step.id}
          className="demo-tour__spotlight"
          aria-hidden
          style={{
            top: highlight.top,
            left: highlight.left,
            width: highlight.width,
            height: highlight.height,
          }}
        />
      ) : null}
      <div
        ref={cardRef}
        className={`demo-tour__card demo-tour__card--${placement}`}
        style={{
          top: cardLayout?.top ?? 0,
          left: cardLayout?.left ?? 0,
          visibility: cardLayout ? "visible" : "hidden",
          ["--demo-tour-arrow" as string]: `${cardLayout?.arrowOffset ?? 28}px`,
        }}
      >
        <span className="demo-tour__arrow" aria-hidden />
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
