/** The "Show me in 3D" invitation (Task 40, section E). The camera flight itself
 *  lives in MapView, which owns the map handle; this button just asks the store for it. */

import { useStore } from '../state/store';

export function ShowMeIn3DButton({ lon, lat }: { lon: number; lat: number }) {
  const requestShowMe3D = useStore((s) => s.requestShowMe3D);
  return (
    <button type="button" className="show-me-3d" onClick={() => requestShowMe3D(lon, lat)}>
      Show me in 3D
    </button>
  );
}
