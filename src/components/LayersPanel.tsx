import { LAYER_DEFS, useEvent, useStore, type LayerId } from '../state/store';

export function LayersPanel() {
  const layers = useStore((s) => s.layers);
  const setLayer = useStore((s) => s.setLayer);
  const event = useEvent();
  // Only offer layers this event actually has data for.
  const available: Record<LayerId, boolean> = {
    evidence: event.evidence.length > 0,
    rainGrid: event.rainGrid !== null,
    sarFlood: event.sar !== null,
    rainCells: event.sar !== null,
    drainage: true,
    builtup: event.builtup !== null,
    points: true,
    buildings3d: true,
  };
  return (
    <ul className="layers">
      {LAYER_DEFS.filter((def) => available[def.id]).map((def) => {
        const l = layers[def.id];
        return (
          <li key={def.id} className={l.visible ? '' : 'is-off'}>
            <label className="layer__main">
              <input type="checkbox" checked={l.visible} onChange={(e) => setLayer(def.id, { visible: e.target.checked })} />
              <span className="layer__swatch" style={{ background: def.swatch }} />
              <span className="layer__name">{def.label}</span>
            </label>
            {def.hasOpacity && (
              <span className="layer__opacity">
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={Math.round(l.opacity * 100)}
                  disabled={!l.visible}
                  aria-label={`${def.label} opacity`}
                  onChange={(e) => setLayer(def.id, { opacity: Number(e.target.value) / 100 })}
                />
                <span className="layer__pct">{Math.round(l.opacity * 100)}%</span>
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
