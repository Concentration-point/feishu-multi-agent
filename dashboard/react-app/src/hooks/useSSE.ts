import { useEffect, useRef } from "react";
import type { PipelineEvent } from "../types";

export function useSSE(
  url: string | null,
  onEvent: (evt: PipelineEvent) => void,
) {
  const cbRef = useRef(onEvent);
  cbRef.current = onEvent;

  useEffect(() => {
    if (!url) return;

    const es = new EventSource(url);
    es.onmessage = (e) => {
      try {
        const evt: PipelineEvent = JSON.parse(e.data);
        cbRef.current(evt);
      } catch {
        /* ignore parse errors */
      }
    };
    es.onerror = () => {
      /* SSE will auto-reconnect */
    };

    return () => es.close();
  }, [url]);
}
