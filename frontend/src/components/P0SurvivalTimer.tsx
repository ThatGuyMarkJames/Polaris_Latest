import React from 'react';
import { Shield, AlertTriangle, BatteryCharging, Flame, Cpu, Zap, Info } from 'lucide-react';
import { P0SurvivalHorizon } from '../types';

interface P0SurvivalTimerProps {
  horizon?: P0SurvivalHorizon;
  compact?: boolean;
}

export const P0SurvivalTimer: React.FC<P0SurvivalTimerProps> = ({ horizon, compact = false }) => {
  if (!horizon) {
    return (
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 text-slate-400 text-sm flex items-center gap-2">
        <Shield className="w-5 h-5 text-cyan-400 animate-pulse" />
        <span>Calculating real-time P0 survival horizon...</span>
      </div>
    );
  }

  const isEmergency = horizon.operating_mode === 'EMERGENCY';
  const isWarning = horizon.operating_mode === 'WARNING';

  const modeBadgeColor = isEmergency
    ? 'bg-rose-500/20 text-rose-400 border-rose-500/30'
    : isWarning
    ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
    : 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';

  return (
    <div className={`bg-slate-900/90 border ${isEmergency ? 'border-rose-500/50 shadow-rose-950/30 shadow-lg' : 'border-slate-800'} rounded-2xl p-5 backdrop-blur-md transition-all`}>
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3 mb-4">
        <div className="flex items-center gap-3">
          <div className={`p-2.5 rounded-xl ${isEmergency ? 'bg-rose-500/20 text-rose-400' : isWarning ? 'bg-amber-500/20 text-amber-400' : 'bg-cyan-500/20 text-cyan-400'}`}>
            <Shield className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-semibold text-slate-100 text-base flex items-center gap-2">
              P0 Life-Support Survival Timer
              <span className={`text-xs px-2.5 py-0.5 rounded-full border ${modeBadgeColor} font-mono font-medium tracking-wide uppercase`}>
                {horizon.operating_mode}
              </span>
            </h3>
            <p className="text-xs text-slate-400">Continuous physical blackout & critical reserve monitor</p>
          </div>
        </div>

        {/* Source Badge */}
        <span className="text-[11px] bg-slate-800/80 text-cyan-300/80 px-2 py-1 rounded-md border border-slate-700/50 font-mono">
          PHYSICS + MILP
        </span>
      </div>

      {/* Main Countdown Display */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        {/* Nominal Survival Hours */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-3.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span>Nominal Survival Horizon</span>
            <Info className="w-3.5 h-3.5 text-slate-500" />
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className={`text-2xl font-bold font-mono ${isEmergency ? 'text-rose-400' : 'text-slate-100'}`}>
              {horizon.survival_hours_remaining >= 72 ? '72+' : horizon.survival_hours_remaining.toFixed(1)}
            </span>
            <span className="text-xs text-slate-400">hours</span>
          </div>
          <p className="text-[11px] text-slate-500 mt-1 truncate">
            {horizon.estimated_breach_time === 'NO_BREACH_IN_72H' ? 'Secure > 72h window' : `Deficit: ${new Date(horizon.estimated_breach_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`}
          </p>
        </div>

        {/* Conservative Survival Hours (P10 Solar / P90 Load) */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-3.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span>Conservative Bound (P10/P90)</span>
            <AlertTriangle className="w-3.5 h-3.5 text-amber-500/70" />
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-2xl font-bold font-mono text-amber-400">
              {horizon.conservative_survival_hours >= 72 ? '72+' : horizon.conservative_survival_hours.toFixed(1)}
            </span>
            <span className="text-xs text-slate-400">hours</span>
          </div>
          <p className="text-[11px] text-slate-500 mt-1 truncate">
            {horizon.conservative_breach_time === 'NO_BREACH_IN_72H' ? 'Safe under storm stress' : `Conservative breach in ${horizon.conservative_survival_hours.toFixed(0)}h`}
          </p>
        </div>

        {/* Minimum SOC Expected */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-3.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span>Min Forecast Battery SOC</span>
            <BatteryCharging className="w-3.5 h-3.5 text-cyan-400/70" />
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className={`text-2xl font-bold font-mono ${horizon.expected_minimum_soc_pct < 25 ? 'text-rose-400' : 'text-cyan-400'}`}>
              {horizon.expected_minimum_soc_pct.toFixed(1)}%
            </span>
            <span className="text-[11px] text-slate-500">(cons: {horizon.conservative_minimum_soc_pct.toFixed(0)}%)</span>
          </div>
          <p className="text-[11px] text-slate-500 mt-1">Floor reserve: 15%</p>
        </div>
      </div>

      {/* Subsystem Shedding Status Badges */}
      <div className="flex flex-wrap items-center gap-2.5 pt-2 border-t border-slate-800/60 text-xs">
        {/* P0 */}
        <div className="flex items-center gap-1.5 bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800">
          <Zap className="w-3.5 h-3.5 text-emerald-400" />
          <span className="text-slate-300 font-medium">P0 Life Support:</span>
          <span className="text-emerald-400 font-mono font-semibold">{horizon.current_p0_load_kw.toFixed(1)} kW (100% SERVED)</span>
        </div>

        {/* P1 Jacket */}
        <div className="flex items-center gap-1.5 bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800">
          <Flame className={`w-3.5 h-3.5 ${horizon.p1_shed_status === 'SHED' ? 'text-rose-400' : 'text-amber-400'}`} />
          <span className="text-slate-300 font-medium">P1 Battery Jacket:</span>
          <span className={`font-mono font-semibold ${horizon.p1_shed_status === 'SHED' ? 'text-rose-400' : 'text-amber-400'}`}>
            {horizon.p1_shed_status === 'SHED' ? 'SHED (Emergency Reallocated)' : 'ACTIVE'}
          </span>
        </div>

        {/* P2 General */}
        <div className="flex items-center gap-1.5 bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800">
          <Cpu className={`w-3.5 h-3.5 ${horizon.p2_shed_status === 'CURTAILED' ? 'text-amber-400' : 'text-cyan-400'}`} />
          <span className="text-slate-300 font-medium">P2 General/Labs:</span>
          <span className={`font-mono font-semibold ${horizon.p2_shed_status === 'CURTAILED' ? 'text-amber-400' : 'text-cyan-400'}`}>
            {horizon.p2_shed_status === 'CURTAILED' ? 'CURTAILED' : 'NOMINAL'}
          </span>
        </div>
      </div>

      {/* Explainability Callout */}
      {horizon.explainability && horizon.explainability.length > 0 && (
        <div className="mt-3.5 bg-slate-950/80 border border-cyan-950/40 rounded-xl p-3 text-xs text-slate-300 space-y-1">
          <div className="font-semibold text-cyan-400 flex items-center gap-1.5 mb-1">
            <Info className="w-3.5 h-3.5" /> Physical Explainability & Action Rationale:
          </div>
          {horizon.explainability.map((exp, idx) => (
            <p key={idx} className="text-slate-400 pl-5 relative before:content-['•'] before:absolute before:left-1 before:text-cyan-500">
              {exp}
            </p>
          ))}
        </div>
      )}
    </div>
  );
};
