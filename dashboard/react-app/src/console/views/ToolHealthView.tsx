/**
 * ToolHealthView · 工具健康监控面板
 *
 * 数据来源：GET /api/tool-stats → logs/tool_calls.jsonl
 * 展示：
 *   - 顶部摘要卡片（总调用、成功率、最慢工具、失败次数）
 *   - 工具健康卡片列表（成功率进度条、avg_ms、调用量）
 *   - 最近失败记录表（tool / error / role / record_id / duration / 时间）
 */

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ShieldCheck, ShieldAlert, RefreshCw, Clock, Zap,
  AlertTriangle, CheckCircle, XCircle, Activity
} from "lucide-react";

interface ToolStat {
  tool: string;
  total: number;
  ok: number;
  fail: number;
  success_rate: number;
  avg_ms: number | null;
  top_errors: string[];
}

interface FailureRecord {
  tool: string;
  success: boolean;
  error: string | null;
  duration_ms: number | null;
  record_id: string;
  role_id: string;
  event: string;
}

interface StatsData {
  total_records: number;
  since_hours: number;
  oldest_ts: string | null;
  newest_ts: string | null;
  tool_stats: ToolStat[];
  recent_failures: FailureRecord[];
}

const ROLE_LABEL: Record<string, string> = {
  account_manager: "客户经理",
  strategist: "策略师",
  copywriter: "文案",
  reviewer: "审核",
  project_manager: "项目经理",
  data_analyst: "数据分析师",
};

const ROLE_COLOR: Record<string, string> = {
  account_manager: "#6ee7b7",
  strategist:      "#93c5fd",
  copywriter:      "#fbbf24",
  reviewer:        "#f87171",
  project_manager: "#a78bfa",
  data_analyst:    "#67e8f9",
};

function rateColor(rate: number): string {
  if (rate >= 95) return "var(--color-accent)";
  if (rate >= 80) return "var(--color-warn)";
  return "var(--color-danger)";
}

function fmtMs(ms: number | null): string {
  if (ms == null) return "—";
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms}ms`;
}

function SummaryCard({ icon, label, value, sub, accent }: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  sub?: string;
  accent?: string;
}) {
  return (
    <div style={{
      background: "var(--color-bg-1)",
      border: "1px solid var(--color-border)",
      borderRadius: "10px",
      padding: "18px 22px",
      display: "flex",
      flexDirection: "column",
      gap: "10px",
      minWidth: "160px",
      flex: 1,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--color-text-3)" }}>
        {icon}
        <span style={{ fontSize: "11px", fontFamily: "var(--font-mono)", letterSpacing: ".06em", textTransform: "uppercase" }}>{label}</span>
      </div>
      <div style={{ fontSize: "26px", fontWeight: 700, color: accent ?? "var(--color-text-1)", fontVariantNumeric: "tabular-nums" }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: "11.5px", color: "var(--color-text-3)" }}>{sub}</div>}
    </div>
  );
}

function ToolCard({ stat }: { stat: ToolStat }) {
  const color = rateColor(stat.success_rate);
  const barW = `${stat.success_rate}%`;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      style={{
        background: "var(--color-bg-1)",
        border: `1px solid ${stat.fail > 0 ? "rgba(248,113,113,.3)" : "var(--color-border)"}`,
        borderRadius: "10px",
        padding: "16px 20px",
        display: "flex",
        flexDirection: "column",
        gap: "12px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: "13px", fontWeight: 600, color: "var(--color-text-1)", fontFamily: "var(--font-mono)" }}>
          {stat.tool}
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          {stat.fail > 0
            ? <XCircle size={14} color="var(--color-danger)" />
            : <CheckCircle size={14} color="var(--color-accent)" />}
          <span style={{ fontSize: "13px", fontWeight: 700, color, fontVariantNumeric: "tabular-nums" }}>
            {stat.success_rate}%
          </span>
        </div>
      </div>

      {/* 成功率进度条 */}
      <div style={{
        height: "4px",
        background: "var(--color-bg-3)",
        borderRadius: "2px",
        overflow: "hidden",
      }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: barW }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          style={{ height: "100%", background: color, borderRadius: "2px" }}
        />
      </div>

      <div style={{ display: "flex", gap: "16px" }}>
        <span style={{ fontSize: "11.5px", color: "var(--color-text-3)" }}>
          <span style={{ color: "var(--color-text-2)", fontVariantNumeric: "tabular-nums" }}>{stat.total}</span> 次调用
        </span>
        <span style={{ fontSize: "11.5px", color: "var(--color-text-3)" }}>
          avg <span style={{ color: "var(--color-text-2)", fontVariantNumeric: "tabular-nums" }}>{fmtMs(stat.avg_ms)}</span>
        </span>
        {stat.fail > 0 && (
          <span style={{ fontSize: "11.5px", color: "var(--color-danger)", fontVariantNumeric: "tabular-nums" }}>
            {stat.fail} 次失败
          </span>
        )}
      </div>

      {stat.top_errors.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
          {stat.top_errors.map((e) => (
            <span key={e} style={{
              fontSize: "10px",
              fontFamily: "var(--font-mono)",
              padding: "2px 7px",
              borderRadius: "3px",
              background: "rgba(248,113,113,.1)",
              color: "var(--color-danger)",
              border: "1px solid rgba(248,113,113,.2)",
            }}>
              {e}
            </span>
          ))}
        </div>
      )}
    </motion.div>
  );
}

function FailureRow({ rec, idx }: { rec: FailureRecord; idx: number }) {
  const roleColor = ROLE_COLOR[rec.role_id] ?? "var(--color-text-3)";
  const roleLabel = ROLE_LABEL[rec.role_id] ?? rec.role_id;
  return (
    <motion.tr
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.15, delay: idx * 0.03 }}
      style={{
        borderBottom: "1px solid var(--color-border)",
      }}
    >
      <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text-3)", whiteSpace: "nowrap" }}>
        {(rec as any).ts
          ? new Date((rec as any).ts).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" })
          : "—"}
      </td>
      <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--color-danger)", fontWeight: 600 }}>
        {rec.tool}
      </td>
      <td style={{ padding: "10px 12px" }}>
        {rec.error ? (
          <span style={{
            fontSize: "11px",
            fontFamily: "var(--font-mono)",
            padding: "2px 7px",
            borderRadius: "3px",
            background: "rgba(248,113,113,.1)",
            color: "var(--color-danger)",
            border: "1px solid rgba(248,113,113,.2)",
          }}>
            {rec.error}
          </span>
        ) : <span style={{ color: "var(--color-text-4)" }}>—</span>}
      </td>
      <td style={{ padding: "10px 12px" }}>
        <span style={{
          fontSize: "11px",
          fontFamily: "var(--font-mono)",
          padding: "2px 8px",
          borderRadius: "3px",
          background: "rgba(0,0,0,.2)",
          color: roleColor,
          border: `1px solid ${roleColor}40`,
        }}>
          {roleLabel}
        </span>
      </td>
      <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text-3)" }}>
        {rec.record_id ? rec.record_id.slice(-8) : "—"}
      </td>
      <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--color-text-2)", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
        {fmtMs(rec.duration_ms)}
      </td>
    </motion.tr>
  );
}

export function ToolHealthView() {
  const [data, setData] = useState<StatsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [sinceHours, setSinceHours] = useState(0); // 0 = 全量历史

  const fetchStats = useCallback(async (hours = sinceHours) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/tool-stats?limit=50&since_hours=${hours}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
      setLastUpdated(new Date());
    } catch (e: any) {
      setError(e.message ?? "请求失败");
    } finally {
      setLoading(false);
    }
  }, [sinceHours]);

  useEffect(() => {
    fetchStats(sinceHours);
    const timer = setInterval(() => fetchStats(sinceHours), 30000);
    return () => clearInterval(timer);
  }, [fetchStats, sinceHours]);

  // 汇总指标
  const totalCalls = data?.total_records ?? 0;
  const totalFail = data?.tool_stats.reduce((s, t) => s + t.fail, 0) ?? 0;
  const overallRate = totalCalls > 0
    ? Math.round(((totalCalls - totalFail) / totalCalls) * 1000) / 10
    : 100;
  const slowestTool = data?.tool_stats.reduce<ToolStat | null>((best, t) => {
    if (t.avg_ms == null) return best;
    if (best == null || (t.avg_ms ?? 0) > (best.avg_ms ?? 0)) return t;
    return best;
  }, null);

  const allOk = totalFail === 0 && totalCalls > 0;

  return (
    <div
      className="scroll-thin"
      style={{
        height: "100%",
        overflowY: "auto",
        padding: "28px 36px 80px",
        fontFamily: "var(--font-sans)",
      }}
    >
      <div style={{ maxWidth: "1100px", margin: "0 auto", display: "flex", flexDirection: "column", gap: "28px" }}>

        {/* 标题栏 */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "12px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            {allOk
              ? <ShieldCheck size={22} color="var(--color-accent)" />
              : <ShieldAlert size={22} color={totalFail > 0 ? "var(--color-danger)" : "var(--color-warn)"} />}
            <div>
              <div style={{ fontSize: "18px", fontWeight: 700, color: "var(--color-text-1)" }}>工具健康监控</div>
              <div style={{ fontSize: "11.5px", color: "var(--color-text-3)", marginTop: "3px" }}>
                logs/tool_calls.jsonl · append-only 全局日志
                {data?.oldest_ts && (
                  <> · <span style={{ fontFamily: "var(--font-mono)" }}>
                    {new Date(data.oldest_ts).toLocaleDateString("zh-CN")}
                  </span> 起</>
                )}
                {lastUpdated && ` · 刷新于 ${lastUpdated.toLocaleTimeString("zh-CN")}`}
              </div>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            {/* 时间范围选择器 */}
            {([
              [0,   "全量历史"],
              [24,  "近 24h"],
              [168, "近 7 天"],
              [720, "近 30 天"],
            ] as [number, string][]).map(([h, label]) => (
              <button
                key={h}
                onClick={() => setSinceHours(h)}
                style={{
                  padding: "5px 12px",
                  borderRadius: "5px",
                  fontSize: "11.5px",
                  fontFamily: "var(--font-mono)",
                  color: sinceHours === h ? "var(--color-accent)" : "var(--color-text-3)",
                  background: sinceHours === h ? "var(--color-bg-0)" : "transparent",
                  border: sinceHours === h ? "1px solid rgba(110,231,183,.3)" : "1px solid transparent",
                  cursor: "pointer",
                }}
              >
                {label}
              </button>
            ))}

            <span aria-hidden style={{ width: 1, height: 16, background: "var(--color-border)" }} />

            <button
              onClick={() => fetchStats(sinceHours)}
              disabled={loading}
              style={{
                display: "flex", alignItems: "center", gap: "6px",
                padding: "7px 14px", borderRadius: "6px", fontSize: "12px",
                color: loading ? "var(--color-text-4)" : "var(--color-text-2)",
                background: "var(--color-bg-2)",
                border: "1px solid var(--color-border)",
                cursor: loading ? "not-allowed" : "pointer",
              }}
            >
              <motion.span
                animate={loading ? { rotate: 360 } : { rotate: 0 }}
                transition={loading ? { duration: 1, repeat: Infinity, ease: "linear" } : { duration: 0.3 }}
                style={{ display: "inline-flex" }}
              >
                <RefreshCw size={13} />
              </motion.span>
              刷新
            </button>
          </div>
        </div>

        {/* 错误提示 */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              style={{
                padding: "12px 16px",
                borderRadius: "8px",
                background: "rgba(248,113,113,.1)",
                border: "1px solid rgba(248,113,113,.3)",
                color: "var(--color-danger)",
                fontSize: "13px",
                display: "flex",
                alignItems: "center",
                gap: "8px",
              }}
            >
              <AlertTriangle size={14} />
              {error} — 请确认 server 已启动（python main.py serve）
            </motion.div>
          )}
        </AnimatePresence>

        {/* 摘要卡片 */}
        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
          <SummaryCard
            icon={<Activity size={14} />}
            label="总调用次数"
            value={totalCalls.toLocaleString()}
            sub={`覆盖 ${data?.tool_stats.length ?? 0} 个工具`}
          />
          <SummaryCard
            icon={<CheckCircle size={14} />}
            label="A类成功率"
            value={`${overallRate}%`}
            sub={`${totalCalls - totalFail} / ${totalCalls} 成功`}
            accent={rateColor(overallRate)}
          />
          <SummaryCard
            icon={<XCircle size={14} />}
            label="技术失败"
            value={totalFail}
            sub="工具抛异常次数"
            accent={totalFail > 0 ? "var(--color-danger)" : "var(--color-accent)"}
          />
          <SummaryCard
            icon={<Clock size={14} />}
            label="最慢工具"
            value={slowestTool ? fmtMs(slowestTool.avg_ms) : "—"}
            sub={slowestTool?.tool ?? "暂无数据"}
            accent="var(--color-warn)"
          />
          <SummaryCard
            icon={<Zap size={14} />}
            label="最快工具"
            value={(() => {
              const withMs = data?.tool_stats.filter(t => t.avg_ms != null) ?? [];
              if (!withMs.length) return "—";
              const fastest = withMs.reduce((a, b) => (a.avg_ms! < b.avg_ms! ? a : b));
              return fmtMs(fastest.avg_ms);
            })()}
            sub={(() => {
              const withMs = data?.tool_stats.filter(t => t.avg_ms != null) ?? [];
              if (!withMs.length) return "暂无数据";
              return withMs.reduce((a, b) => (a.avg_ms! < b.avg_ms! ? a : b)).tool;
            })()}
            accent="var(--color-info)"
          />
        </div>

        {/* 工具健康卡片 */}
        {data && data.tool_stats.length > 0 && (
          <section>
            <div style={{
              fontSize: "12px",
              fontFamily: "var(--font-mono)",
              letterSpacing: ".08em",
              textTransform: "uppercase",
              color: "var(--color-text-3)",
              marginBottom: "14px",
              paddingBottom: "8px",
              borderBottom: "1px solid var(--color-border)",
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}>
              <span style={{ width: "2px", height: "12px", background: "var(--color-accent)", borderRadius: "1px", display: "inline-block" }} />
              各工具健康状态
            </div>
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
              gap: "12px",
            }}>
              {[...data.tool_stats]
                .sort((a, b) => a.success_rate - b.success_rate)
                .map((stat) => (
                  <ToolCard key={stat.tool} stat={stat} />
                ))}
            </div>
          </section>
        )}

        {/* 最近失败记录 */}
        {data && (
          <section>
            <div style={{
              fontSize: "12px",
              fontFamily: "var(--font-mono)",
              letterSpacing: ".08em",
              textTransform: "uppercase",
              color: "var(--color-text-3)",
              marginBottom: "14px",
              paddingBottom: "8px",
              borderBottom: "1px solid var(--color-border)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ width: "2px", height: "12px", background: "var(--color-danger)", borderRadius: "1px", display: "inline-block" }} />
                最近失败记录
              </div>
              <span style={{ color: "var(--color-text-4)" }}>{data.recent_failures.length} 条</span>
            </div>

            {data.recent_failures.length === 0 ? (
              <div style={{
                padding: "40px",
                textAlign: "center",
                color: "var(--color-accent)",
                background: "var(--color-bg-1)",
                borderRadius: "10px",
                border: "1px solid var(--color-border)",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: "10px",
              }}>
                <CheckCircle size={32} />
                <div style={{ fontSize: "14px", fontWeight: 500 }}>暂无技术失败记录</div>
                <div style={{ fontSize: "12px", color: "var(--color-text-3)" }}>A 类技术失败率 0%，工具层运行健康</div>
              </div>
            ) : (
              <div style={{
                background: "var(--color-bg-1)",
                border: "1px solid var(--color-border)",
                borderRadius: "10px",
                overflow: "hidden",
              }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ background: "var(--color-bg-2)" }}>
                      {["时间", "工具", "错误类型", "调用角色", "Record ID", "耗时"].map((h) => (
                        <th key={h} style={{
                          padding: "10px 12px",
                          textAlign: h === "耗时" ? "right" : "left",
                          fontSize: "11px",
                          fontFamily: "var(--font-mono)",
                          letterSpacing: ".06em",
                          color: "var(--color-text-3)",
                          fontWeight: 500,
                          borderBottom: "1px solid var(--color-border)",
                          textTransform: "uppercase",
                        }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_failures.map((rec, i) => (
                      <FailureRow key={i} rec={rec} idx={i} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {/* 空数据提示 */}
        {!loading && !error && data?.total_records === 0 && (
          <div style={{
            padding: "60px 40px",
            textAlign: "center",
            color: "var(--color-text-3)",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: "14px",
          }}>
            <Activity size={36} style={{ opacity: 0.4 }} />
            <div style={{ fontSize: "15px", color: "var(--color-text-2)" }}>暂无工具调用数据</div>
            <div style={{ fontSize: "12.5px" }}>
              先跑一次 Demo（<code style={{ fontFamily: "var(--font-mono)", background: "var(--color-bg-2)", padding: "2px 6px", borderRadius: "3px" }}>python demo/run_demo.py --scene 电商大促</code>）<br />
              数据会自动写入 logs/tool_calls.jsonl
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
