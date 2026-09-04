import React from 'react';
import { AlertOctagon, ShieldAlert, Cpu, Flame, Zap, ArrowRight, CheckCircle2 } from 'lucide-react';
import { P0SurvivalHorizon, InstantEnergyState } from '../types';

interface EmergencyPanelProps {
  horizon?: P0SurvivalHorizon;
  energyState?: InstantEnergyState;
  sourceLabel?: string;
}

export const EmergencyPanel: React.FC<EmergencyPanelProps> = ({
  horizon,
  energyState,
  sourceLabel = 'Synthetic telemetry — simulation mode'
}) => {
  if (!horizon) return null;

  const isEmergency = horizon.operating_mode === 'EMERGENCY';
  const isWarning = horizon.operating_mode === 'WARNING';

  if (!isEmergency && !isWarning) return null;

  return (
    <div className={`rounded-2xl p-5 border mb-6 ${isEmergency ? 'bg-rose-950/30 border-rose-500/40 text-rose-200' : 'bg-amber-950/30 border-amber-500/40 text-amber-200'} backdrop-blur-md`}>
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-3 pb-3 border-b border-white/10">
        <div className="flex items-center gap-3">
          <div className={`p-2.5 rounded-xl ${isEmergency ? 'bg-rose-500 text-white animate-pulse' : 'bg-amber-500 text-slate-950'}`}>
            {isEmergency ? <AlertOctagon className="w-6 h-6" /> : <ShieldAlert className="w-6 h-6" />}
          </div>
          <div>
            <h2 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
              {isEmergency ? 'CRITICAL P0 EMERGENCY PROTOCOL ACTIVE' : 'EARLY WARNING: BLACKOUT MITIGATION ACTIVE'}
            </h2>
            <p className="text-xs text-slate-300">
              {isEmergency
                ? 'Automatic mathematical power reallocation engaged to sustain habitat life support.'
                : 'Proactive load curtailment and battery pre-charging engaged.'}
            </p>
          </div>
        </div>

        {/* Source tagging */}
        <div className="text-[11px] bg-black/40 border border-white/10 px-3 py-1 rounded-full font-mono text-slate-300">
          {sourceLabel}
        </div>
      </div>

      {/* Grid of Emergency KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
        <div className="bg-black/30 rounded-xl p-3 border border-white/5">
          <div className="text-[11px] text-slate-400">P0 Life Support</div>
          <div className="text-lg font-bold font-mono text-emerald-400 mt-0.5">
            {horizon.p0_status === 'SECURE' ? '100% PROTECTED' : 'AT RISK'}
          </div>
        </div>

        <div className="bg-black/30 rounded-xl p-3 border border-white/5">
          <div className="text-[11px] text-slate-400">P1 Battery Jacket</div>
          <div className={`text-lg font-bold font-mono mt-0.5 ${horizon.p1_shed_status === 'SHED' ? 'text-rose-400' : 'text-amber-400'}`}>
            {horizon.p1_shed_status}
          </div>
        </div>

        <div className="bg-black/30 rounded-xl p-3 border border-white/5">
          <div className="text-[11px] text-slate-400">P2 General Loads</div>
          <div className="text-lg font-bold font-mono text-amber-400 mt-0.5">
            {horizon.p2_shed_status}
          </div>
        </div>

        <div className="bg-black/30 rounded-xl p-3 border border-white/5">
          <div className="text-[11px] text-slate-400">Survival Remaining</div>
          <div className="text-lg font-bold font-mono text-white mt-0.5">
            {horizon.conservative_survival_hours.toFixed(1)} hrs
          </div>
        </div>
      </div>

      {/* Recommended Emergency Actions */}
      <div className="mt-4 pt-3 border-t border-white/10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-2 text-slate-300">
          <CheckCircle2 className="w-4 h-4 text-cyan-400 shrink-0" />
          <span>Recommended Action: {horizon.recommended_actions[0] || 'Enforce P0 critical load priority.'}</span>
        </div>
      </div>
    </div>
  );
};
