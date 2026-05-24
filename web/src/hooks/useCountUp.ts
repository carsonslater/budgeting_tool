import { useState, useEffect } from 'react';

export function useCountUp(end: number, duration: number = 1000) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    // If end is 0 or undefined, just set it immediately.
    if (!end) {
      setCount(0);
      return;
    }

    let startTime: number | null = null;
    let animationFrame: number;

    const animate = (timestamp: number) => {
      if (!startTime) startTime = timestamp;
      const progress = timestamp - startTime;
      const percentage = Math.min(progress / duration, 1);
      
      // easeOutExpo for a nice snappy count
      const easeProgress = percentage === 1 ? 1 : 1 - Math.pow(2, -10 * percentage);
      
      setCount(end * easeProgress);

      if (progress < duration) {
        animationFrame = requestAnimationFrame(animate);
      } else {
        setCount(end);
      }
    };

    animationFrame = requestAnimationFrame(animate);

    return () => cancelAnimationFrame(animationFrame);
  }, [end, duration]);

  return count;
}
