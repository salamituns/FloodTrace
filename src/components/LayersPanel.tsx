import { useState } from 'react';
import { LAYER_DEFS, useEvent, useStore, type LayerId } from '../state/store';
import { MODEL_SCENARIOS_MM } from '../lib/impacts';
import '../styles/flood.css';
import '../styles/map3d.css';

export function LayersPanel() {
  const layers = useStore((s) => s.layers);
  const setLayer = useStore((s) => s.setLayer);
  const viewMode = useStore((s) => s.viewMode);
  const modelScenario = useStore((s) => s.modelScenario);
  const setModelScenario = useStore((s) => s.setModelScenario);
  const event = useEvent();
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState<LayerId | null>(null);
  const available: Record<LayerId, boolean> = {
    evidence: event.evidence.length > 0,
    rainGrid: event.rainGrid !== null,
    sarFlood: event.sar !== null,
    rainCells: event.sar !== null,
    drainage: true,
    builtup: event.builtup !== null,
    points: true,
    waterEvidence: viewMode === '3d',
    waterModel: viewMode === '3d',
    buildings3d: viewMode === '3d',
  };
  const defs = LAYER_DEFS.filter((def) => available[def.id]);
  const onCount = defs.filter((def) => layers[def.id].visible).length;

  return (
    <section className="card">
      <button
        type="button"
        className="layers-card__toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <h2>Map layers · {onCount} on</h2>
        <span aria-hidden="true">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <ul className="layers">
          {defs.map((def) => {
            const l = layers[def.id];
            const rowOpen = expanded === def.id;
            return (
              <li key={def.id} className={l.visible ? '' : 'is-off'}>
                <label className="layer__main">
                  <input type="checkbox" checked={l.visible} onChange={(e) => setLayer(def.id, { visible: e.target.checked })} />
                  <span className="layer__swatch" style={{ background: def.swatch }} />
                </label>
                <button
                  type="button"
                  className="layer__name-btn"
                  aria-expanded={rowOpen}
                  onClick={() => setExpanded((id) => (id === def.id ? null : def.id))}
                >
                  {def.label}
                </button>
                {rowOpen && def.note && <p className="layer__note">{def.note}</p>}
                {rowOpen && def.id === 'waterModel' && (
                  <span className="layer__scenario">
                    <span className="layer__scenario-label">If {modelScenario} mm more rain falls than the drains can take</span>
                    <input
                      type="range"
                      min={0}
                      max={MODEL_SCENARIOS_MM.length - 1}
                      step={1}
                      value={Math.max(0, MODEL_SCENARIOS_MM.indexOf(modelScenario as (typeof MODEL_SCENARIOS_MM)[number]))}
                      disabled={!l.visible}
                      aria-label="Rough model rain scenario"
                      onChange={(e) => setModelScenario(MODEL_SCENARIOS_MM[Number(e.target.value)])}
                    />
                  </span>
                )}
                {def.hasOpacity && rowOpen && (
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
      )}
    </section>
  );
}
