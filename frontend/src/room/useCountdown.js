import { useEffect, useState } from "react";

// Whole seconds left until `deadline` (client-clock ms, already skew-corrected
// from the server's phase frame). Display only: the server ends every Phase.
export default function useCountdown(deadline) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!deadline) return undefined;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [deadline]);
  return deadline ? Math.max(0, Math.ceil((deadline - now) / 1000)) : 0;
}
