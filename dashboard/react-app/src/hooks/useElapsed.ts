import { useEffect, useState } from "react";

export function useElapsed(startTime: number | null): string {
  const [display, setDisplay] = useState("00:00");

  useEffect(() => {
    if (!startTime) {
      setDisplay("00:00");
      return;
    }

    const tick = () => {
      const sec = Math.floor((Date.now() - startTime) / 1000);
      const m = String(Math.floor(sec / 60)).padStart(2, "0");
      const s = String(sec % 60).padStart(2, "0");
      setDisplay(`${m}:${s}`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [startTime]);

  return display;
}
