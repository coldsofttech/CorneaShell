import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent, ReactNode } from "react";
import { Controller } from "./controller";
import type { Options } from "./controller";
import type { MenuClickDetail } from "./types";

const Context = createContext<Controller | null>(null);

/** Starts the menus once for everything below it. */
export function CorneaMenus(props: Options & { children?: ReactNode }): ReactNode {
  const { children, ...options } = props;
  const [controller, setController] = useState<Controller | null>(null);
  const key = JSON.stringify(options);
  useEffect(() => {
    const next = new Controller(document, JSON.parse(key) as Options);
    let cancelled = false;
    void next.start().then(() => {
      if (!cancelled) setController(next);
    });
    return () => {
      cancelled = true;
    };
  }, [key]);
  return <Context.Provider value={controller}>{children}</Context.Provider>;
}

function useController(): Controller | null {
  return useContext(Context);
}

/** The menu bar. Put it where the bar should be. */
export function MenuBar(props: { className?: string }): ReactNode {
  const controller = useController();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!controller || !ref.current) return undefined;
    const mounted = controller.mountBar(ref.current);
    return () => mounted.destroy();
  }, [controller]);
  return <div ref={ref} className={props.className} />;
}

/** The title bar of a frameless window. It stays empty when the window has its frame. */
export function TitleBar(props: { className?: string }): ReactNode {
  const controller = useController();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!controller || !ref.current) return undefined;
    let destroy: (() => void) | undefined;
    let cancelled = false;
    void controller.mountTitleBar(ref.current).then((bar) => {
      if (cancelled || !bar.frameless) bar.destroy();
      else destroy = bar.destroy;
    });
    return () => {
      cancelled = true;
      destroy?.();
    };
  }, [controller]);
  return <div ref={ref} className={props.className} />;
}

/** Props that open the context menu `name` on right-click: `<div {...useContextMenu("editor")} />`. */
export function useContextMenu(name: string): {
  onContextMenu: (event: ReactMouseEvent) => void;
  "data-cornea-context": string;
} {
  const controller = useController();
  return useMemo(
    () => ({
      "data-cornea-context": name,
      onContextMenu: (event: ReactMouseEvent) => {
        if (controller?.popup(name, { x: event.clientX, y: event.clientY })) event.preventDefault();
      },
    }),
    [controller, name],
  );
}

/** Calls `handler` whenever a menu entry is chosen. */
export function useMenuClick(handler: (detail: MenuClickDetail) => void): void {
  const latest = useRef(handler);
  latest.current = handler;
  useEffect(() => {
    const listener = (event: Event): void => latest.current((event as CustomEvent<MenuClickDetail>).detail);
    window.addEventListener("cornea:menu-click", listener);
    return () => window.removeEventListener("cornea:menu-click", listener);
  }, []);
}
