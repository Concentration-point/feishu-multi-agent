/**
 * roleProjectors/pm · 项目经理 PMDeck 投影
 *
 * 按 STAGE_LABELS 顺序生成 milestones；通过率从 pipeline.completed 事件取。
 */

import type { EventSnapshot } from "../eventNormalizer";
import { ROLE_NAME, ROLE_ORDER, STAGE_LABELS } from "../eventNormalizer";
import type { Milestone, PMDeck } from "../../types";

export function buildPMDeck(snap: EventSnapshot): PMDeck {
  const milestones: Milestone[] = STAGE_LABELS.map(({ role, label }, i) => {
    const isActive = snap.activeRole === role && !snap.pipelineCompleted;
    const done =
      snap.pipelineCompleted ||
      (snap.activeRole
        ? ROLE_ORDER.indexOf(role) < ROLE_ORDER.indexOf(snap.activeRole)
        : snap.stagesVisited.includes(role));
    return {
      id: `m${i + 1}`,
      title: `M${i + 1} · ${ROLE_NAME[role]}`,
      summary: isActive
        ? `当前阶段：${label}`
        : done
          ? `${label} · 已完成`
          : `${label} · 待开始`,
      done: done && !isActive,
    };
  });

  return {
    header: {
      title: "项目进度",
      subtitle: "PROJECT MANAGER · R4",
      meta: [
        {
          label: "完成",
          value: `${milestones.filter((m) => m.done).length} / ${milestones.length}`,
        },
        {
          label: "通过率",
          value: snap.passRate > 0 ? `${Math.round(snap.passRate * 100)}%` : "—",
        },
        { label: "状态", value: snap.pipelineCompleted ? "已完成" : snap.projectStatus || "进行中" },
      ],
    },
    milestones,
  };
}
