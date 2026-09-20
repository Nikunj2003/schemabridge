"use client";

import { useEffect, useRef } from "react";

type Point = { x: number; y: number } | null;

/**
 * Decorative, pointer-responsive honeycomb for the public landing page.
 *
 * The static lattice is cached and only composited again on resize, palette
 * changes, or pointer movement. It never captures input or runs an idle loop.
 */
export function HexGridBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const cache = document.createElement("canvas");
    const cacheContext = cache.getContext("2d");
    if (!cacheContext) return;

    const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let point: Point = null;
    let frame = 0;
    let hidden = document.hidden;
    let size = { width: 0, height: 0, ratio: 1 };

    const colors = () => {
      const style = getComputedStyle(canvas);
      return {
        line: style.getPropertyValue("--accent").trim(),
        glow: style.getPropertyValue("--accent-soft").trim(),
      };
    };

    /**
     * One flat-top hexagon.
     *
     * The 30° offset is what makes it flat-top, and it has to match the spacing
     * below: `horizontal = √3·r` and `vertical = 1.5·r` are the flat-top
     * tessellation offsets. Without the offset this drew pointy-top hexagons on
     * flat-top spacing, so they overlapped instead of interlocking and the
     * lattice read as a field of stars rather than a honeycomb.
     */
    const hex = (target: CanvasRenderingContext2D, x: number, y: number, radius: number) => {
      target.beginPath();
      for (let corner = 0; corner < 6; corner += 1) {
        const angle = Math.PI / 3 * corner + Math.PI / 6;
        const px = x + Math.cos(angle) * radius;
        const py = y + Math.sin(angle) * radius;
        if (corner === 0) target.moveTo(px, py);
        else target.lineTo(px, py);
      }
      target.closePath();
    };

    const metrics = () => {
      // Larger cells than before: a dense lattice competes with the headline
      // instead of sitting behind it.
      const radius = Math.max(30, Math.min(44, size.width / 22));
      return { radius, horizontal: Math.sqrt(3) * radius, vertical: 1.5 * radius };
    };

    const rebuildBase = () => {
      const rect = canvas.getBoundingClientRect();
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      size = { width: Math.max(0, rect.width), height: Math.max(0, rect.height), ratio };
      const pixelWidth = Math.round(size.width * ratio);
      const pixelHeight = Math.round(size.height * ratio);
      canvas.width = pixelWidth;
      canvas.height = pixelHeight;
      cache.width = pixelWidth;
      cache.height = pixelHeight;
      cacheContext.setTransform(ratio, 0, 0, ratio, 0, 0);
      cacheContext.clearRect(0, 0, size.width, size.height);
      if (size.width === 0 || size.height === 0) return;

      const { radius, horizontal, vertical } = metrics();
      const { line } = colors();
      cacheContext.strokeStyle = line;
      // Quieter, so the grid is felt rather than read.
      cacheContext.globalAlpha = 0.055;
      cacheContext.lineWidth = 1;
      for (let row = -2; row < size.height / vertical + 3; row += 1) {
        for (let column = -2; column < size.width / horizontal + 3; column += 1) {
          hex(cacheContext, column * horizontal + (row % 2 ? horizontal / 2 : 0), row * vertical, radius);
          cacheContext.stroke();
        }
      }
      cacheContext.globalAlpha = 1;
    };

    const render = () => {
      frame = 0;
      if (hidden || size.width === 0 || size.height === 0) return;
      context.setTransform(size.ratio, 0, 0, size.ratio, 0, 0);
      context.clearRect(0, 0, size.width, size.height);
      context.drawImage(cache, 0, 0, size.width, size.height);
      if (!point || !finePointer.matches || reducedMotion.matches) return;

      const { radius, horizontal, vertical } = metrics();
      const { line, glow } = colors();
      const influence = 180;
      const startRow = Math.max(-2, Math.floor((point.y - influence) / vertical) - 2);
      const endRow = Math.min(Math.ceil(size.height / vertical) + 2, Math.ceil((point.y + influence) / vertical) + 2);
      context.lineWidth = 1.3;
      for (let row = startRow; row <= endRow; row += 1) {
        for (let column = Math.max(-2, Math.floor((point.x - influence) / horizontal) - 2); column <= Math.ceil((point.x + influence) / horizontal) + 2; column += 1) {
          const x = column * horizontal + (row % 2 ? horizontal / 2 : 0);
          const y = row * vertical;
          const distance = Math.hypot(x - point.x, y - point.y);
          if (distance > influence) continue;
          const intensity = (1 - distance / influence) ** 2;
          hex(context, x, y, radius);
          context.strokeStyle = line;
          context.globalAlpha = 0.25 + intensity * 0.65;
          context.stroke();
          context.fillStyle = glow;
          context.globalAlpha = intensity * 0.45;
          context.fill();
        }
      }
      context.globalAlpha = 1;
    };

    const requestRender = () => {
      if (!frame) frame = window.requestAnimationFrame(render);
    };
    const refresh = () => {
      rebuildBase();
      requestRender();
    };
    const onMove = (event: PointerEvent) => {
      if (!finePointer.matches || reducedMotion.matches) return;
      const rect = canvas.getBoundingClientRect();
      point = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      requestRender();
    };
    const onLeave = () => {
      if (!point) return;
      point = null;
      requestRender();
    };
    const onVisibility = () => {
      hidden = document.hidden;
      if (!hidden) refresh();
    };

    const observer = new ResizeObserver(refresh);
    observer.observe(canvas);
    const themeObserver = new MutationObserver(refresh);
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "style"] });
    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("pointerleave", onLeave);
    document.addEventListener("visibilitychange", onVisibility);
    finePointer.addEventListener("change", onLeave);
    reducedMotion.addEventListener("change", onLeave);
    refresh();

    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      themeObserver.disconnect();
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerleave", onLeave);
      document.removeEventListener("visibilitychange", onVisibility);
      finePointer.removeEventListener("change", onLeave);
      reducedMotion.removeEventListener("change", onLeave);
    };
  }, []);

  return <canvas ref={canvasRef} className="marketing-hex-grid" aria-hidden="true" />;
}
