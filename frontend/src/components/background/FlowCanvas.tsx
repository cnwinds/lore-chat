import type { BgOverview } from "../../types/background";
import { groupOverviewLanes, laneTitleById } from "./backgroundUtils";
import { FlowLane } from "./FlowLane";

type Props = {
  overview: BgOverview;
  stacked: boolean;
  highlightLaneId: string | null;
  selectedNodeId: string | null;
  pauseBusy: boolean;
  onSelectNode: (id: string) => void;
  onLinkClick: (laneId: string) => void;
  onPauseChange: (pauseKey: string, paused: boolean) => void;
};

export function FlowCanvas({
  overview,
  stacked,
  highlightLaneId,
  selectedNodeId,
  pauseBusy,
  onSelectNode,
  onLinkClick,
  onPauseChange,
}: Props) {
  const groups = groupOverviewLanes(overview);
  const titleForLane = (id: string) => laneTitleById(overview.lanes, id);

  return (
    <div className="bgflow-canvas">
      {groups.map((group) =>
        group.lanes.length === 0 ? null : (
          <section key={group.id} className="bgflow-group">
            <h3 className="bgflow-group-title">{group.title}</h3>
            {group.hint ? <p className="bgflow-group-hint">{group.hint}</p> : null}
            {group.lanes.map((lane) => (
              <FlowLane
                key={lane.id}
                lane={lane}
                nodes={overview.nodes}
                status={overview.status}
                pausable={overview.pausable}
                stacked={stacked}
                highlighted={highlightLaneId === lane.id}
                selectedNodeId={selectedNodeId}
                pauseBusy={pauseBusy}
                onSelectNode={onSelectNode}
                onLinkClick={onLinkClick}
                onPauseChange={onPauseChange}
                laneTitleById={titleForLane}
              />
            ))}
          </section>
        ),
      )}
    </div>
  );
}
