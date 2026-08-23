const YANDEX_METRIKA_ID = 111872223;

declare global {
  interface Window {
    ym?: (counterId: number, method: string, ...args: unknown[]) => void;
  }
}

type RouteLocation = {
  pathname: string;
  search: string;
  hash: string;
};

export function onRouteDidUpdate({
  location,
  previousLocation,
}: {
  location: RouteLocation;
  previousLocation?: RouteLocation | null;
}): void {
  if (!previousLocation) {
    return;
  }

  if (
    location.pathname === previousLocation.pathname &&
    location.search === previousLocation.search
  ) {
    return;
  }

  window.ym?.(
    YANDEX_METRIKA_ID,
    'hit',
    `${location.pathname}${location.search}${location.hash}`,
    {
      title: document.title,
      referer: `${window.location.origin}${previousLocation.pathname}${previousLocation.search}${previousLocation.hash}`,
    },
  );
}
