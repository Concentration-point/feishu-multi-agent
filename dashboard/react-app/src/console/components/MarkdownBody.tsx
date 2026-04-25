/**
 * MarkdownBody · 面向 agent 真实输出的 markdown 渲染器
 *
 * 底层逻辑：agent 写给 Bitable 的字段（brief_analysis / strategy /
 * draft_content / review_summary）都是 markdown，面板必须把它们渲染成
 * 真正的层次结构，而不是一大块 pre-line 文本。
 *
 * 两种密度：
 *   - compact: 给 PlanGrid block 用 —— 紧凑、缩小字号、弱化标题
 *   - full: 给 ToolDrawer draft body 用 —— 完整排版、serif 标题、清晰节奏
 *
 * 所有 markdown 元素样式和当前视觉系统对齐（Plex Serif 标题 / Plex Sans 正文 /
 * JetBrains Mono 代码 / 青绿 accent 给 strong）。
 */

import type { ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

type Density = "compact" | "full";

interface MarkdownBodyProps {
  children: string;
  density?: Density;
}

export function MarkdownBody({ children, density = "full" }: MarkdownBodyProps) {
  if (!children || !children.trim()) return null;
  return (
    <div style={{ color: "var(--color-text-1)" }}>
      <Markdown remarkPlugins={[remarkGfm]} components={componentsFor(density)}>
        {children}
      </Markdown>
    </div>
  );
}

function componentsFor(density: Density): Components {
  const isFull = density === "full";

  const baseP = {
    fontSize: isFull ? "14px" : "13px",
    lineHeight: isFull ? 1.75 : 1.6,
    color: "var(--color-text-2)",
    margin: isFull ? "0 0 14px" : "0 0 8px",
  } as const;

  return {
    h1: ({ children }) => (
      <h1
        style={{
          fontFamily: "var(--font-serif)",
          fontSize: isFull ? "22px" : "15px",
          fontWeight: 600,
          color: "var(--color-text-1)",
          margin: isFull ? "16px 0 12px" : "4px 0 6px",
          lineHeight: 1.35,
          letterSpacing: "-0.005em",
        }}
      >
        {children}
      </h1>
    ),
    h2: ({ children }) => (
      <h2
        style={{
          fontFamily: "var(--font-serif)",
          fontSize: isFull ? "17px" : "14px",
          fontWeight: 600,
          color: "var(--color-text-1)",
          margin: isFull ? "22px 0 10px" : "10px 0 4px",
          lineHeight: 1.4,
        }}
      >
        {children}
      </h2>
    ),
    h3: ({ children }) => (
      <h3
        style={{
          fontFamily: "var(--font-sans)",
          fontSize: isFull ? "14.5px" : "13px",
          fontWeight: 600,
          color: "var(--color-text-1)",
          margin: isFull ? "16px 0 6px" : "8px 0 4px",
          letterSpacing: "0.01em",
        }}
      >
        {children}
      </h3>
    ),
    h4: ({ children }) => (
      <h4
        style={{
          fontFamily: "var(--font-sans)",
          fontSize: "13px",
          fontWeight: 600,
          color: "var(--color-text-2)",
          margin: "8px 0 4px",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
        }}
      >
        {children}
      </h4>
    ),
    p: ({ children }) => <p style={baseP}>{children}</p>,
    strong: ({ children }) => (
      <strong
        style={{
          color: "var(--color-accent)",
          fontWeight: 600,
        }}
      >
        {children}
      </strong>
    ),
    em: ({ children }) => (
      <em
        style={{
          color: "var(--color-text-1)",
          fontStyle: "italic",
        }}
      >
        {children}
      </em>
    ),
    del: ({ children }) => (
      <del style={{ color: "var(--color-text-3)", opacity: 0.7 }}>{children}</del>
    ),
    ul: ({ children }) => (
      <ul
        style={{
          margin: isFull ? "0 0 14px" : "0 0 8px",
          paddingLeft: "1.2em",
          listStyle: "disc",
        }}
      >
        {children}
      </ul>
    ),
    ol: ({ children }) => (
      <ol
        style={{
          margin: isFull ? "0 0 14px" : "0 0 8px",
          paddingLeft: "1.4em",
          listStyle: "decimal",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {children}
      </ol>
    ),
    li: ({ children }) => (
      <li
        style={{
          fontSize: isFull ? "14px" : "13px",
          lineHeight: isFull ? 1.7 : 1.55,
          color: "var(--color-text-2)",
          marginBottom: isFull ? "6px" : "3px",
          paddingLeft: "2px",
        }}
      >
        {children}
      </li>
    ),
    blockquote: ({ children }) => (
      <blockquote
        style={{
          margin: isFull ? "12px 0 14px" : "6px 0 8px",
          paddingLeft: "14px",
          borderLeft: "2px solid var(--color-accent)",
          color: "var(--color-text-2)",
          fontStyle: "italic",
          opacity: 0.9,
        }}
      >
        {children}
      </blockquote>
    ),
    code: ({ className, children, ...rest }) => {
      const isInline = !className;
      if (isInline) {
        return (
          <code
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.88em",
              padding: "1px 6px",
              borderRadius: "3px",
              background: "var(--color-bg-2)",
              color: "var(--color-accent)",
              border: "1px solid var(--color-border-soft)",
            }}
            {...rest}
          >
            {children}
          </code>
        );
      }
      return (
        <code
          className={className}
          style={{ fontFamily: "var(--font-mono)", fontSize: "12.5px" }}
          {...rest}
        >
          {children}
        </code>
      );
    },
    pre: ({ children }) => (
      <pre
        className="scroll-thin"
        style={{
          background: "var(--color-bg-0)",
          border: "1px solid var(--color-border)",
          borderRadius: "6px",
          padding: "14px 16px",
          margin: isFull ? "12px 0 16px" : "8px 0",
          overflowX: "auto",
          fontFamily: "var(--font-mono)",
          fontSize: "12px",
          lineHeight: 1.65,
          color: "var(--color-text-2)",
        }}
      >
        {children}
      </pre>
    ),
    a: ({ href, children }) => (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        style={{
          color: "var(--color-accent)",
          textDecoration: "underline",
          textDecorationColor: "rgba(110,231,183,0.4)",
          textUnderlineOffset: "3px",
        }}
      >
        {children}
      </a>
    ),
    hr: () => (
      <hr
        style={{
          border: "none",
          borderTop: "1px dashed var(--color-border-soft)",
          margin: "18px 0",
        }}
      />
    ),
    table: ({ children }) => (
      <div style={{ overflowX: "auto", margin: "10px 0 14px" }}>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "13px",
            border: "1px solid var(--color-border)",
            borderRadius: "6px",
            overflow: "hidden",
          }}
        >
          {children}
        </table>
      </div>
    ),
    thead: ({ children }) => (
      <thead style={{ background: "var(--color-bg-2)" }}>{children}</thead>
    ),
    th: ({ children }) => (
      <th
        style={{
          padding: "8px 12px",
          textAlign: "left",
          fontWeight: 600,
          color: "var(--color-text-1)",
          borderBottom: "1px solid var(--color-border)",
          fontSize: "12px",
          letterSpacing: "0.02em",
        }}
      >
        {children}
      </th>
    ),
    td: ({ children }) => (
      <td
        style={{
          padding: "8px 12px",
          borderBottom: "1px solid var(--color-border-soft)",
          color: "var(--color-text-2)",
          verticalAlign: "top",
        }}
      >
        {children}
      </td>
    ),
  };
}

/**
 * 工具方法 —— 把 excerpt 展示用的"干净短文"从 markdown 抽出，
 * 保持 PlanGrid block 可以混用"短短一句 plain text"和"markdown 片段"。
 */
export function plainFromMarkdown(src: string): string {
  if (!src) return "";
  return src
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/^\s*#{1,6}\s+/gm, "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/__(.+?)__/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^\s*[-*]\s+/gm, "")
    .replace(/\n{2,}/g, "\n")
    .trim();
}

/** 隐藏使用警告：保留 ReactNode 导出供其他组件类型引用 */
export type MarkdownChildren = ReactNode;
