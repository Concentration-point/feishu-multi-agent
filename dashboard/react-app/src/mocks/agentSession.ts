/**
 * Mock Agent Session · CDSS 六一儿童节益智玩具套装促销
 *
 * 完整覆盖 5 个角色主视图和右侧栏。所有字段结构严格对齐 console/types.ts。
 * 后续接入 SSE 时，只需在 useConsoleStore 里把事件流投影成这个结构即可。
 */

import type { AgentSession } from "../console/types";

export const MOCK_SESSION: AgentSession = {
  client: "CDSS",
  campaign: "六一儿童节 · 益智玩具套装促销",
  timeline: "2025-05-25 → 2025-06-01",

  roleCounts: {
    account: 18,
    strategy: 16,
    copy: 45,
    review: 75,
    pm: 12,
  },

  timelineSteps: [
    { label: "Brief 解读", done: true, current: false },
    { label: "策略中", done: true, current: false },
    { label: "撰写中", done: false, current: true },
    { label: "待审核", done: false, current: false },
    { label: "交付", done: false, current: false },
  ],

  // ============ 工具调用（统一收纳在这里，各角色视图按 role 过滤）============
  toolCalls: [
    {
      id: "copy-read-project",
      name: "read_project",
      role: "copy",
      round: 1,
      calls: 1,
      avgMs: 142,
      kind: "info",
      request: {
        fields: [
          "client_name",
          "project_type",
          "brand_tone",
          "dept_style",
          "status",
          "strategy",
        ],
      },
      response: {
        client_name: "cdss",
        project_type: "电商大促",
        brand_tone: "",
        dept_style: "",
        status: "策略中",
        strategy: "围绕六一节点完成家长认知建立...",
      },
    },
    {
      id: "copy-list-content",
      name: "list_content",
      role: "copy",
      round: 1,
      calls: 1,
      avgMs: 89,
      kind: "info",
      response: [
        {
          record_id: "recvgYM0Dx6Rav",
          seq: 4,
          title: "同样是六一礼物，为什么益智玩具套装更适合家长决策",
          platform: "小红书",
          content_type: "对比种草笔记",
          target_audience: "28-40岁家长",
        },
        { record_id: "recA1", seq: 1, title: "…" },
        { record_id: "recA2", seq: 2, title: "…" },
        { record_id: "recA3", seq: 3, title: "…" },
      ],
    },
    {
      id: "copy-search-knowledge",
      name: "search_knowledge",
      role: "copy",
      round: 1,
      calls: 3,
      avgMs: 420,
      kind: "purple",
      invocations: [
        { label: "益智玩具 家长决策模型", ms: 398 },
        { label: "小红书种草结构 对比笔记", ms: 441 },
        { label: "28-40岁家长 节日情绪 画像", ms: 421 },
      ],
    },
    {
      id: "copy-write-content",
      name: "write_content",
      role: "copy",
      round: 2,
      calls: 4,
      avgMs: 1850,
      kind: "ok",
      producesContent: true,
      invocations: [
        { label: "seq_1", ms: 1900, note: "六一儿童节给孩子选益智玩具..." },
        { label: "seq_2", ms: 1600, note: "同样是六一礼物，为什么..." },
        { label: "seq_3", ms: 2100, note: "真实六一场景｜孩子拿到礼物..." },
        { label: "seq_4", ms: 1800, note: "【开箱脚本】六一惊喜礼物..." },
      ],
    },
    {
      id: "copy-update-status",
      name: "update_status",
      role: "copy",
      round: 1,
      calls: 1,
      avgMs: 14,
      kind: "warn",
      stateTransition: "策略中 → 撰写中",
      request: { from: "策略中", to: "撰写中" },
    },

    // Strategy
    {
      id: "strategy-read-project",
      name: "read_project",
      role: "strategy",
      round: 1,
      calls: 1,
      avgMs: 130,
      kind: "info",
      request: { fields: ["client_name", "project_type", "brief"] },
    },
    {
      id: "strategy-write-project",
      name: "write_project",
      role: "strategy",
      round: 1,
      calls: 1,
      avgMs: 240,
      kind: "ok",
      request: {
        strategy:
          "围绕六一节点完成家长认知建立，公众号做教育价值信任，小红书做种草和场景代入，抖音做开箱承接转化。",
      },
    },
    {
      id: "strategy-search-knowledge",
      name: "search_knowledge",
      role: "strategy",
      round: 1,
      calls: 5,
      avgMs: 408,
      kind: "purple",
      invocations: [
        { label: "电商大促 节点营销 结构", ms: 390 },
        { label: "益智玩具 决策漏斗", ms: 421 },
        { label: "多渠道内容分工 模板", ms: 411 },
        { label: "28-40岁家长 画像", ms: 402 },
        { label: "小红书 种草转化", ms: 416 },
      ],
    },

    // Review
    {
      id: "review-list-content",
      name: "list_content",
      role: "review",
      round: 1,
      calls: 1,
      avgMs: 91,
      kind: "info",
    },
    {
      id: "review-read-project",
      name: "read_project",
      role: "review",
      round: 1,
      calls: 1,
      avgMs: 138,
      kind: "info",
    },
    {
      id: "review-request-human",
      name: "request_human_review",
      role: "review",
      round: 2,
      calls: 1,
      avgMs: 22,
      kind: "warn",
      stateTransition: "seq_4 → 人工复核",
    },
    {
      id: "review-read-knowledge",
      name: "read_knowledge",
      role: "review",
      round: 1,
      calls: 1,
      avgMs: 310,
      kind: "purple",
      request: { doc: "品牌合规检查清单" },
    },

    // Account
    {
      id: "account-read-project",
      name: "read_project",
      role: "account",
      round: 1,
      calls: 1,
      avgMs: 128,
      kind: "info",
    },
    {
      id: "account-write-project",
      name: "write_project",
      role: "account",
      round: 1,
      calls: 1,
      avgMs: 210,
      kind: "ok",
    },
    {
      id: "account-send-message",
      name: "send_message",
      role: "account",
      round: 1,
      calls: 2,
      avgMs: 290,
      kind: "warn",
    },

    // PM
    {
      id: "pm-list-content",
      name: "list_content",
      role: "pm",
      round: 1,
      calls: 1,
      avgMs: 88,
      kind: "info",
    },
    {
      id: "pm-update-status",
      name: "update_status",
      role: "pm",
      round: 3,
      calls: 2,
      avgMs: 15,
      kind: "warn",
      stateTransition: "审核中 → 排期中",
    },
    {
      id: "pm-send-message",
      name: "send_message",
      role: "pm",
      round: 3,
      calls: 3,
      avgMs: 270,
      kind: "ok",
    },
  ],

  // ============ 客户经理 ============
  account: {
    header: {
      title: "客户经理 · Brief 解读",
      subtitle: "ACCOUNT · R1",
      meta: [
        { label: "状态", value: "已交付" },
        { label: "耗时", value: "58s" },
        { label: "工具", value: "5 次" },
      ],
    },
    kicker: "CLIENT BRIEF · CDSS",
    title: "六一儿童节 · 益智玩具套装促销",
    tagline:
      "客户希望在 5/25 - 6/1 完成一轮全渠道内容铺设，核心目标是促销窗口内的转化，兼顾品牌教育价值沉淀。",
    blocks: [
      { label: "Summary", value: "六一节点全渠道内容铺设，5/25-6/1 共 7 天，3 渠道 4 篇文。" },
      { label: "Target", value: "促销窗口内的转化为主要目标，兼顾品牌教育价值沉淀。" },
      { label: "Audience", value: "28-40 岁家长，追求孩子陪伴与能力成长。" },
      { label: "Constraints", value: "预算待客户补充；母婴功效词需合规审查；交付时间 5/25-6/1。" },
    ],
    gate: {
      verdict: "conditional",
      label: "有条件通过",
      body: "**有条件通过**：核心需求与时间线明确，可进入策略阶段。\n\n**待补充**：\n- 预算上限（影响渠道分配）\n- 品牌方关于功效词的禁用清单\n\n**风险提示**：母婴品类涉及医疗健康类红线词，文案撰写需走合规自检。",
    },
  },

  // ============ 策略师 ============
  strategy: {
    header: {
      title: "策略方案 · 内容总纲",
      subtitle: "STRATEGIST · R1",
      meta: [
        { label: "渠道", value: "3" },
        { label: "篇目", value: "4" },
        { label: "KPI", value: "认知→转化" },
      ],
    },
    kicker: "CAMPAIGN STRATEGY · 电商大促",
    title: "围绕六一完成家长认知建立、种草转化和购买承接",
    tagline:
      "用公众号建立教育价值信任，用小红书强化真实种草与场景代入，用抖音完成开箱。目标：在促销窗口内形成有效转化。",
    blocks: [
      {
        label: "Target Audience",
        value:
          "**28-40岁**家长，关注孩子陪伴与能力成长，节日期待仪式感、警惕吃灰礼物",
      },
      {
        label: "Core Insight",
        value:
          '选益智玩具的真正决策点，不是外观而是 **"玩多久、学到什么"** —— 家长要的是教育价值承诺',
      },
      {
        label: "Brand Tone",
        value: "专业而亲切，拒绝强推，依托 **场景 + 证据** 做信任建立",
      },
      {
        label: "KPI Funnel",
        value: "认知建立 → 种草 → 场景代入 → **开箱承接转化**",
      },
    ],
    channels: [
      { name: "公众号", role: "长文 · 教育价值信任建立 · 权威背书", count: 1 },
      { name: "小红书", role: "对比种草 + 真实场景笔记 · 28-40 家长决策路径", count: 2 },
      { name: "抖音", role: "开箱脚本 · 15秒钩子 · 转化落点", count: 1 },
    ],
  },

  // ============ 文案（主展示角色）============
  copywriter: {
    header: {
      title: "文案 · 六一益智玩具套装",
      subtitle: "COPYWRITER · R2",
      meta: [
        { label: "产出", value: "4 篇" },
        { label: "字数", value: "3,247" },
        { label: "耗时", value: "2m 14s" },
      ],
    },
    drafts: [
      {
        id: "mock-draft-1",
        seq: 1,
        platform: "gzh",
        contentType: "教育价值信任",
        title: "六一儿童节给孩子选益智玩具，家长先看这3点",
        excerpt:
          "六一快到了，很多家长都会遇到同一个问题：礼物到底怎么选，才不会买回去吃灰？比起只看好不好看、孩子会不会一时喜欢，真正值得慎重考虑的，是这份礼物能不能玩得久、用得上、孩子愿意反复拿出来。",
        fullBody: `六一快到了，很多家长都会遇到同一个问题：礼物到底怎么选，才不会买回去吃灰？

比起只看"好不好看""孩子会不会一时喜欢"，真正值得慎重考虑的，是这份礼物能不能玩得久、用得上、孩子愿意反复拿出来。

这篇文章想和你聊三个选择维度：能力长期训练、陪伴仪式感、以及和孩子当下兴趣的契合度。

1. 能力长期训练
好的益智玩具不是一个游戏，而是一个长期陪伴孩子成长的工具。它允许孩子在不同阶段拿出来玩出新花样。

2. 陪伴仪式感
六一不是一天，而是一段回忆的锚点。玩具本身要能带出"我们一起玩"的记忆。

3. 和孩子当下兴趣的契合度
孩子现在爱什么，就从哪儿切入。硬塞一个教育性很强但孩子不感兴趣的产品，结果只会吃灰。`,
        wordCount: 1247,
        status: "done",
      },
      {
        id: "mock-draft-2",
        seq: 2,
        platform: "xhs",
        contentType: "对比种草",
        title: "同样是六一礼物，为什么益智玩具套装更适合家长决策",
        excerpt:
          "28-40岁家长的痛点：送娃的礼物不能是短命款。对比了市面上三类主流六一礼物之后，我把关注点落在了陪伴感+仪式感+能力长期训练三个维度。",
        fullBody: `28-40岁家长的痛点：送娃的礼物不能是短命款。

对比了市面上三类主流六一礼物之后，我把关注点落在了"陪伴感 + 仪式感 + 能力长期训练"三个维度。

【玩偶类】：好看但吃灰快，3 天后基本不再拿出来。
【零食类】：即时快乐，零留存价值。
【益智玩具套装】：拆箱仪式感 + 可玩性 + 能力训练，三个月后依然是孩子的"常玩榜单"。

选礼物的本质是在选"和孩子共同记忆的介质"。`,
        wordCount: 856,
        status: "done",
      },
      {
        id: "mock-draft-3",
        seq: 3,
        platform: "xhs",
        contentType: "场景代入",
        title: "真实六一场景｜孩子拿到礼物的前30秒",
        excerpt:
          "节日当天真实测评：拆箱 → 初次上手 → 30分钟后仍在专注。这套玩具的精妙在于它不依赖家长陪玩，孩子自己能进入节奏。",
        fullBody: `节日当天真实测评：拆箱 → 初次上手 → 30 分钟后仍在专注。

这套玩具的精妙在于它不依赖家长陪玩——孩子自己就能进入节奏。对我这种下班回家还要自己带娃的妈妈来说，这点太珍贵了。

实测：拆箱后 30 秒内孩子就开始按说明书摸索，全程无需介入。
30 分钟后：依然在玩，没有出现常见的"新鲜感消退"。
1 小时后：孩子主动把玩具收好，表示"明天还要玩"。

这就是"能陪伴孩子很久的礼物"应该有的样子。`,
        wordCount: 724,
        status: "draft",
      },
      {
        id: "mock-draft-4",
        seq: 4,
        platform: "dy",
        contentType: "开箱脚本",
        title: "【开箱脚本】六一惊喜礼物 · 15秒钩子版",
        excerpt:
          "0-3s：孩子眼神镜头 + 猜猜妈妈送了什么；3-8s：拆箱节奏快剪，落在关键部件；8-15s：孩子开始玩 → 专注镜头 → 品牌落版。",
        fullBody: `【15秒 TikTok / 抖音 开箱脚本】

0-3s（钩子）：
  - 画面：孩子闭眼，妈妈把礼物递到面前
  - 旁白："猜猜妈妈送了什么？"
  - 字幕：六一惊喜 已备好

3-8s（拆箱）：
  - 快剪拆箱节奏 × 3 次，每次落在关键部件
  - BGM 节奏卡点

8-15s（转化）:
  - 孩子开始玩，镜头推到专注的眼神
  - 品牌落版 + CTA: "六一礼物清单 👉"`,
        wordCount: 420,
        status: "review",
      },
    ],
    knowledge: [
      { label: "益智玩具 · 家长决策模型", kind: "purple" },
      { label: "小红书种草结构库", kind: "purple" },
      { label: "六一节日话术 · 2024", kind: "purple" },
      { label: "品牌 tone · CDSS", kind: "purple" },
      { label: "28-40岁家长画像", kind: "purple" },
    ],
  },

  // ============ 审核 ============
  reviewer: {
    header: {
      title: "审核报告 · 4 篇产出",
      subtitle: "REVIEWER · R3",
      meta: [
        { label: "通过", value: "2" },
        { label: "待修订", value: "1" },
        { label: "问题", value: "1" },
      ],
    },
    items: [
      {
        id: "mock-draft-1",
        draftSeq: 1,
        verdict: "approve",
        platform: "gzh",
        title: "公众号｜六一儿童节给孩子选益智玩具，家长先看这3点",
        note: "结构完整，论据充分，品牌 tone 一致。建议直接交付。",
        action: "APPROVE",
      },
      {
        id: "mock-draft-2",
        draftSeq: 2,
        verdict: "approve",
        platform: "xhs",
        title: "小红书｜同样是六一礼物，为什么益智玩具套装更适合家长决策",
        note: "对比结构清晰，符合平台种草范式。可直接发布。",
        action: "APPROVE",
      },
      {
        id: "mock-draft-3",
        draftSeq: 3,
        verdict: "revise",
        platform: "xhs",
        title: "小红书｜真实六一场景｜孩子拿到礼物的前30秒",
        note: "场景描述偏单薄，缺少家长自己的情绪钩子。建议补一段'送的时候我自己也紧张'。",
        action: "REVISE",
      },
      {
        id: "mock-draft-4",
        draftSeq: 4,
        verdict: "reject",
        platform: "dy",
        title: "抖音｜【开箱脚本】六一惊喜礼物 · 15秒钩子版",
        note: "0-3s 的孩子眼神镜头需求不明确；缺少转化落点的具体 CTA 文案。",
        action: "REJECT",
      },
    ],
  },

  // ============ 项目经理 ============
  pm: {
    header: {
      title: "项目进度",
      subtitle: "PROJECT MANAGER · R4",
      meta: [
        { label: "完成", value: "3 / 5" },
        { label: "通过率", value: "75%" },
        { label: "待处理", value: "2" },
      ],
    },
    milestones: [
      {
        id: "m1",
        title: "M1 · Brief 共识",
        summary: "客户需求、目标、预算、时间线对齐完毕。",
        done: true,
      },
      {
        id: "m2",
        title: "M2 · 策略定稿",
        summary: "三渠道内容分工、信息漏斗、KPI 明确。",
        done: true,
      },
      {
        id: "m3",
        title: "M3 · 产出完成",
        summary: "4 篇内容已交付，其中 2 篇通过审核，1 篇待修订，1 篇问题待解决。",
        done: true,
      },
      {
        id: "m4",
        title: "M4 · 审核修订",
        summary: "seq_3 文案补情绪钩子；seq_4 补 CTA，由文案二次修改后重审。",
        done: false,
      },
      {
        id: "m5",
        title: "M5 · 排期交付",
        summary: "5/25 - 6/1 分阶段发布：公众号 → 小红书 → 抖音。",
        done: false,
      },
    ],
  },

  // ============ Sidebar ============
  memoryProgress: [
    { label: "Brief 解读", state: "done" },
    { label: "策略方案", state: "done" },
    { label: "文案撰写", state: "current" },
    { label: "审核总评", state: "pending" },
    { label: "交付摘要", state: "pending" },
  ],

  auditLog: [
    { time: "14:02", name: "write_content → seq_4", durMs: 1800, kind: "ok" },
    { time: "14:01", name: "write_content → seq_3", durMs: 2100, kind: "ok" },
    { time: "14:01", name: "update_status", durMs: 12, kind: "warn" },
    { time: "14:00", name: "write_content → seq_2", durMs: 1600, kind: "ok" },
    { time: "14:00", name: "search_knowledge", durMs: 420, kind: "info" },
    { time: "13:59", name: "write_content → seq_1", durMs: 1900, kind: "ok" },
    { time: "13:59", name: "list_content", durMs: 89, kind: "info" },
    { time: "13:58", name: "read_project", durMs: 142, kind: "info" },
    { time: "13:58", name: "update_status · 撰写中", durMs: 14, kind: "warn" },
    { time: "13:57", name: "read_knowledge · tone", durMs: 310, kind: "info" },
  ],

  toolStats: [
    { name: "write_content", count: 31 },
    { name: "search_knowledge", count: 11 },
    { name: "send_message", count: 8 },
    { name: "read_project", count: 7 },
    { name: "read_knowledge", count: 5 },
    { name: "list_content", count: 5 },
    { name: "write_project", count: 4 },
    { name: "update_status", count: 4 },
    { name: "request_human_review", count: 1 },
  ],

  riskBadges: [
    { label: "人工驳回", kind: "error" },
    { label: "知识沉淀 3 次", kind: "ok" },
  ],

  experienceEvolution: {
    cards: [
      {
        roleId: "account_manager",
        roleName: "客户经理",
        category: "电商大促",
        lesson: "母婴品类 Brief 解读需特别关注功效词合规，提前标注易触红线表述",
        confidence: 0.85,
        threshold: 0.7,
        passed: true,
        phase: "saved",
        factors: { pass_rate: 0.75, task_completed: true, no_rework: true, knowledge_cited: true },
        bitableSaved: true,
        wikiSaved: true,
        bitableCount: 3,
        formalLoaded: true,
      },
      {
        roleId: "strategist",
        roleName: "策略师",
        category: "电商大促",
        lesson: "六一节点的家长群体，核心洞察应聚焦「陪伴感」而非「促销价格」",
        confidence: 0.82,
        threshold: 0.7,
        passed: true,
        phase: "merged",
        factors: { pass_rate: 0.75, task_completed: true, no_rework: true, knowledge_cited: true },
        mergedFrom: 2,
        bitableCount: 2,
        formalLoaded: false,
      },
      {
        roleId: "copywriter",
        roleName: "文案",
        category: "电商大促",
        lesson: "小红书对比种草笔记，三段式（痛点→对比→结论）转化率最优",
        confidence: 0.58,
        threshold: 0.7,
        passed: false,
        phase: "skipped",
        factors: { pass_rate: 0.75, task_completed: true, no_rework: false, knowledge_cited: false },
        bitableCount: 4,
        formalLoaded: true,
      },
      {
        roleId: "reviewer",
        roleName: "审核",
        category: "电商大促",
        lesson: "益智玩具品类需检查「锻炼大脑」等伪科学表述",
        confidence: 0.78,
        threshold: 0.7,
        passed: true,
        phase: "saved",
        factors: { pass_rate: 0.75, task_completed: true, no_rework: true, knowledge_cited: true },
        bitableSaved: true,
        wikiSaved: false,
        bitableCount: 1,
        formalLoaded: false,
      },
      {
        roleId: "project_manager",
        roleName: "项目经理",
        category: "电商大促",
        lesson: "加载 2 条 Bitable 经验 + 正式沉淀区",
        confidence: 0,
        threshold: 0,
        passed: true,
        phase: "loaded",
        bitableCount: 2,
        formalLoaded: true,
      },
    ],
    loadedRoles: ["account_manager", "strategist", "copywriter", "reviewer", "project_manager"],
    totalDistilled: 4,
    passedScoring: 3,
    mergedGroups: 1,
    finalSettled: 2,
    settled: true,
  },
};
