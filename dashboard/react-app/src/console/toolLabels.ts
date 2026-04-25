/**
 * 工具函数名 → 中文人类可读名的映射
 *
 * 底层逻辑：面板面向非技术用户，raw function name 不暴露给 UI 主体；
 * 开发者如需溯源，hover tooltip 或 drawer 里仍然保留英文原名。
 *
 * 颗粒度要求：
 *   - 动词开头，一个任务一句话 —— "搜索知识库" 优于 "知识搜索"
 *   - 不超过 6 个中文字，chip 能容纳
 *   - 和 Bitable / wiki / im 三个领域术语对齐
 */

const TOOL_LABELS: Record<string, string> = {
  // 项目主表 —— 共享大脑
  read_project: "读取项目主表",
  write_project: "写入项目主表",
  update_status: "更新项目状态",

  // 内容排期
  list_content: "查看内容排期",
  create_content: "新建内容行",
  batch_create_content: "批量创建内容",
  write_content: "写入成稿",

  // 知识库
  search_knowledge: "搜索知识库",
  read_knowledge: "读取知识文档",
  write_wiki: "沉淀经验 wiki",
  search_reference: "搜索参考资料",
  read_reference: "读取参考资料",

  // 经验池
  get_experience: "查询经验池",

  // IM / 人工
  send_message: "发送群消息",
  request_human_review: "请求人工审核",
};

/**
 * 拿工具的中文名。未知工具回退到把下划线换成空格、首字母大写的 fallback 格式。
 */
export function toolLabel(name: string): string {
  if (!name) return "未知工具";
  const hit = TOOL_LABELS[name];
  if (hit) return hit;
  return name
    .split("_")
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(" ");
}
