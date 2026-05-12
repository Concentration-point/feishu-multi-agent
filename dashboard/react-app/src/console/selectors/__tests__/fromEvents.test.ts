/**
 * fromEvents · fixture 测试
 *
 * 不依赖 vitest / jest（项目目前没有引入测试 runner）。
 * 用自带 assert helper 跑，可被 `npx tsx <file>` 或未来接入的 vitest 直接消费。
 *
 * 覆盖三类核心场景：
 *   1. 典型流水线（pipeline.started → strategy → write_content → completed）
 *   2. 审核驳回（review_summary 内含统计句 "驳回条数：0"，验证 verdict 正则不误判）
 *   3. 红线命中（write_project 写 review_red_flag，验证 RiskBadge 输出）
 *
 * 注：本文件不会被 vite 打包到生产产物，仅在显式跑 tsc/tsx 时参与。
 */

import type { PipelineEvent } from "../../../types";
import { hasLiveSession, projectAgentSession } from "../fromEvents";

// =============== 自包含 assert helpers ===============

let assertions = 0;
let failures: string[] = [];

function assertEq<T>(actual: T, expected: T, label: string): void {
  assertions++;
  if (actual !== expected) {
    failures.push(`[FAIL] ${label}: expected ${String(expected)}, got ${String(actual)}`);
  }
}

function assertTrue(cond: boolean, label: string): void {
  assertions++;
  if (!cond) failures.push(`[FAIL] ${label}`);
}

// =============== 事件构造 helper ===============

function evt(
  event_type: string,
  agent_role: string,
  timestamp: number,
  payload: Record<string, unknown>,
  round = 1,
): PipelineEvent {
  return {
    event_type,
    timestamp,
    record_id: "rec_test",
    agent_role,
    agent_name: agent_role,
    round,
    payload,
  };
}

// =============== 场景一：典型流水线 ===============

function fixtureNormalPipeline(): PipelineEvent[] {
  const t0 = 1_700_000_000;
  return [
    evt("pipeline.started", "system", t0, {
      project_name: "测试客户A",
      brief: "为新品上市做内容推广",
    }),
    evt("agent.started", "account_manager", t0 + 1, { project_type: "新品发布" }),
    evt("pipeline.stage_changed", "system", t0 + 2, {
      current_role: "account_manager",
      prev_role: "",
    }),
    evt("tool.called", "account_manager", t0 + 3, {
      tool_name: "write_project",
      arguments: {
        field_name: "brief_analysis",
        content: "# 1. 项目摘要\n新品上市内容矩阵\n\n# 8. 准入结论\n通过。建议立即推进。",
      },
    }),
    evt("tool.returned", "account_manager", t0 + 4, {
      tool_name: "write_project",
      result: "ok",
    }),
    evt("pipeline.stage_changed", "system", t0 + 5, {
      current_role: "strategist",
      prev_role: "account_manager",
    }),
    evt("tool.called", "strategist", t0 + 6, {
      tool_name: "batch_create_content",
      arguments: {
        items: [
          {
            sequence: 1,
            title: "首发预热",
            platform: "小红书",
            content_type: "种草笔记",
            key_message: "突出新品卖点",
            target_audience: "25-35 都市女性",
          },
          {
            sequence: 2,
            title: "正式发布",
            platform: "抖音",
            content_type: "短视频脚本",
            key_message: "演示使用场景",
            target_audience: "18-30 年轻人",
          },
        ],
      },
    }),
    evt("tool.returned", "strategist", t0 + 7, {
      tool_name: "batch_create_content",
      result: JSON.stringify({ record_ids: ["recA001", "recA002"] }),
    }),
    evt("pipeline.stage_changed", "system", t0 + 8, {
      current_role: "copywriter",
      prev_role: "strategist",
    }),
    evt("tool.called", "copywriter", t0 + 9, {
      tool_name: "write_content",
      arguments: {
        content_record_id: "recA001",
        field_name: "draft_content",
        value: "# 首发预热\n\n这是一篇 200 字的小红书种草笔记正文……",
      },
    }),
    evt("tool.returned", "copywriter", t0 + 10, {
      tool_name: "write_content",
      result: "已写入 200 字",
    }),
    evt("pipeline.stage_changed", "system", t0 + 11, {
      current_role: "reviewer",
      prev_role: "copywriter",
    }),
    evt("tool.called", "reviewer", t0 + 12, {
      tool_name: "write_project",
      arguments: {
        field_name: "review_summary",
        content: "本轮审核概况 通过条数：1 驳回条数：0\n\n## 首发预热\n通过。",
      },
    }),
    evt("tool.returned", "reviewer", t0 + 13, {
      tool_name: "write_project",
      result: "ok",
    }),
    evt("pipeline.completed", "system", t0 + 20, {
      status: "已完成",
      pass_rate: 1.0,
    }),
  ];
}

function testNormalPipeline(): void {
  const events = fixtureNormalPipeline();
  assertTrue(hasLiveSession(events), "normal/hasLiveSession");

  const sess = projectAgentSession(events);

  // 顶层元信息
  assertEq(sess.client, "测试客户A", "normal/client");
  assertEq(sess.campaign, "新品发布", "normal/campaign");

  // 时间线全 done
  assertTrue(
    sess.timelineSteps.every((s) => s.done && !s.current),
    "normal/timelineSteps all done",
  );

  // 文案 drafts：2 条骨架 + 1 条正文回填
  assertEq(sess.copywriter.drafts.length, 2, "normal/drafts count");
  const first = sess.copywriter.drafts[0];
  assertEq(first.id, "recA001", "normal/draft id replaced from pending");
  assertEq(first.platform, "xhs", "normal/platform normalized to xhs");
  assertEq(first.status, "done", "normal/draft status done");
  assertTrue(first.fullBody.includes("这是一篇 200 字"), "normal/fullBody preserved");

  // 第二条 draft 没有正文 → status draft
  const second = sess.copywriter.drafts[1];
  assertEq(second.status, "draft", "normal/second draft pending");
  assertEq(second.platform, "dy", "normal/抖音 normalized to dy");

  // 审核 verdict：第一条 approve，第二条无正文 → revise（降级）
  assertEq(sess.reviewer.items[0].verdict, "approve", "normal/first review approve");
  assertEq(sess.reviewer.items[1].verdict, "revise", "normal/second review revise (no draft)");

  // PM 通过率
  assertTrue(
    sess.pm.header.meta.some((m) => m.label === "通过率" && m.value === "100%"),
    "normal/pm pass rate 100%",
  );

  // Account Deck gate verdict
  assertEq(sess.account.gate?.verdict, "pass", "normal/account gate pass");
}

// =============== 场景二：审核驳回（防"驳回条数"误判） ===============

function fixtureReviewReject(): PipelineEvent[] {
  const t0 = 1_700_001_000;
  return [
    evt("pipeline.started", "system", t0, { project_name: "驳回测试", brief: "测试 brief" }),
    evt("agent.started", "account_manager", t0 + 1, { project_type: "电商大促" }),
    evt("tool.called", "strategist", t0 + 2, {
      tool_name: "batch_create_content",
      arguments: {
        items: [
          {
            sequence: 1,
            title: "夸大宣传文案",
            platform: "微博",
            content_type: "话题",
            key_message: "全网最低",
            target_audience: "全员",
          },
        ],
      },
    }),
    evt("tool.returned", "strategist", t0 + 3, {
      tool_name: "batch_create_content",
      result: JSON.stringify({ record_ids: ["recB001"] }),
    }),
    evt("tool.called", "copywriter", t0 + 4, {
      tool_name: "write_content",
      arguments: {
        content_record_id: "recB001",
        field_name: "draft_content",
        value: "全网最低！绝对真实！",
      },
    }),
    evt("tool.returned", "copywriter", t0 + 5, {
      tool_name: "write_content",
      result: "已写入",
    }),
    // 审核 agent 用 write_content 写每条审核结论（最权威）
    evt("tool.called", "reviewer", t0 + 6, {
      tool_name: "write_content",
      arguments: {
        content_record_id: "recB001",
        field_name: "review_status",
        value: "驳回",
      },
    }),
    evt("tool.returned", "reviewer", t0 + 7, {
      tool_name: "write_content",
      result: "ok",
    }),
    evt("tool.called", "reviewer", t0 + 8, {
      tool_name: "write_content",
      arguments: {
        content_record_id: "recB001",
        field_name: "review_feedback",
        value: "含极限词，违反广告法",
      },
    }),
    evt("tool.returned", "reviewer", t0 + 9, {
      tool_name: "write_content",
      result: "ok",
    }),
    // review_summary 开头带"驳回条数：1"统计句——旧版正则会把所有 draft 误判为 reject
    evt("tool.called", "reviewer", t0 + 10, {
      tool_name: "write_project",
      arguments: {
        field_name: "review_summary",
        content: "本轮审核概况 通过条数：0 驳回条数：1\n\n## 夸大宣传文案\n极限词命中。",
      },
    }),
    evt("tool.returned", "reviewer", t0 + 11, {
      tool_name: "write_project",
      result: "ok",
    }),
  ];
}

function testReviewReject(): void {
  const events = fixtureReviewReject();
  const sess = projectAgentSession(events);

  assertEq(sess.reviewer.items.length, 1, "reject/review items count");
  assertEq(sess.reviewer.items[0].verdict, "reject", "reject/verdict from row.review_status");
  assertEq(sess.reviewer.items[0].action, "REJECT", "reject/action REJECT");
  assertTrue(
    sess.reviewer.items[0].note.includes("极限词"),
    "reject/note from row.review_feedback",
  );
  // 平台 normalize：微博 → wb
  assertEq(sess.reviewer.items[0].platform, "wb", "reject/platform wb");
}

// =============== 场景三：红线命中 ===============

function fixtureRedFlag(): PipelineEvent[] {
  const t0 = 1_700_002_000;
  return [
    evt("pipeline.started", "system", t0, { project_name: "红线测试", brief: "敏感行业 brief" }),
    evt("agent.started", "account_manager", t0 + 1, { project_type: "医疗健康" }),
    evt("tool.called", "account_manager", t0 + 2, {
      tool_name: "write_project",
      arguments: {
        field_name: "brief_analysis",
        content: "# 1. 摘要\n包含医疗器械推广\n\n# 8. 准入结论\n不通过。涉及红线行业。",
      },
    }),
    evt("tool.returned", "account_manager", t0 + 3, {
      tool_name: "write_project",
      result: "ok",
    }),
    evt("tool.called", "reviewer", t0 + 4, {
      tool_name: "write_project",
      arguments: {
        field_name: "review_red_flag",
        content: "医疗虚假宣传",
      },
    }),
    evt("tool.returned", "reviewer", t0 + 5, {
      tool_name: "write_project",
      result: "ok",
    }),
    evt("tool.called", "reviewer", t0 + 6, {
      tool_name: "write_project",
      arguments: {
        field_name: "review_status",
        content: "rejected",
      },
    }),
    evt("tool.returned", "reviewer", t0 + 7, {
      tool_name: "write_project",
      result: "ok",
    }),
  ];
}

function testRedFlag(): void {
  const events = fixtureRedFlag();
  const sess = projectAgentSession(events);

  // Account gate 应该为 reject
  assertEq(sess.account.gate?.verdict, "reject", "redflag/account gate reject");

  // RiskBadge 应该包含人工驳回 + 红线风险
  const labels = sess.riskBadges.map((b) => b.label);
  assertTrue(
    labels.some((l) => l.includes("人工驳回")),
    "redflag/risk badge 人工驳回",
  );
  assertTrue(
    labels.some((l) => l.includes("红线风险")),
    "redflag/risk badge 红线风险",
  );
}

// =============== 入口 ===============

export function runFixtureTests(): { assertions: number; failures: string[] } {
  assertions = 0;
  failures = [];

  testNormalPipeline();
  testReviewReject();
  testRedFlag();

  return { assertions, failures: failures.slice() };
}

/**
 * 备注：未引入测试 runner（vitest/jest）以避免新增依赖。
 * 想跑这套 fixture 可以：
 *   - 引入 vitest 后给 runFixtureTests() 写 wrapper（最小改动）
 *   - 或直接 `npx tsx` 运行一个 thin runner 调用 runFixtureTests()
 * 当前提交里仅靠 `npx tsc --noEmit` 保证测试和被测代码同构。
 */
