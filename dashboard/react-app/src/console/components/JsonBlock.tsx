/**
 * JsonBlock
 *
 * 一等公民：结构化的 request / response。
 * 自己实现简易语法高亮，不引额外依赖。
 */

interface JsonBlockProps {
  value: unknown;
}

type Token =
  | { kind: "k"; text: string }
  | { kind: "s"; text: string }
  | { kind: "n"; text: string }
  | { kind: "b"; text: string }
  | { kind: "p"; text: string }
  | { kind: "t"; text: string };

function tokenize(src: string): Token[] {
  const out: Token[] = [];
  let i = 0;
  const len = src.length;
  while (i < len) {
    const ch = src[i];
    if (ch === '"') {
      let j = i + 1;
      while (j < len && src[j] !== '"') {
        if (src[j] === "\\") j += 2;
        else j++;
      }
      const text = src.slice(i, j + 1);
      // 判断是不是 key：看它后面是不是紧跟 `:`
      let k = j + 1;
      while (k < len && src[k] === " ") k++;
      const isKey = src[k] === ":";
      out.push({ kind: isKey ? "k" : "s", text });
      i = j + 1;
      continue;
    }
    if (/[0-9\-]/.test(ch)) {
      let j = i;
      while (j < len && /[0-9.\-eE+]/.test(src[j])) j++;
      out.push({ kind: "n", text: src.slice(i, j) });
      i = j;
      continue;
    }
    if (src.startsWith("true", i) || src.startsWith("false", i) || src.startsWith("null", i)) {
      const w = src.startsWith("true", i) ? "true" : src.startsWith("false", i) ? "false" : "null";
      out.push({ kind: "b", text: w });
      i += w.length;
      continue;
    }
    if ("{}[],:".includes(ch)) {
      out.push({ kind: "p", text: ch });
      i++;
      continue;
    }
    out.push({ kind: "t", text: ch });
    i++;
  }
  return out;
}

const TOKEN_CLASS: Record<Token["kind"], string> = {
  k: "text-info",
  s: "text-accent",
  n: "text-purple",
  b: "text-warn",
  p: "text-text-4",
  t: "text-text-2",
};

export function JsonBlock({ value }: JsonBlockProps) {
  let formatted: string;
  if (typeof value === "string") formatted = value;
  else {
    try {
      formatted = JSON.stringify(value, null, 2);
    } catch {
      formatted = String(value);
    }
  }

  const tokens = tokenize(formatted);

  return (
    <pre className="scroll-thin bg-bg-0 border border-border rounded-md p-4 font-mono text-[12px] leading-[1.65] text-text-2 overflow-x-auto whitespace-pre">
      {tokens.map((t, i) => (
        <span key={i} className={TOKEN_CLASS[t.kind]}>
          {t.text}
        </span>
      ))}
    </pre>
  );
}
