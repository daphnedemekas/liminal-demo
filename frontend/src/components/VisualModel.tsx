import React from 'react';

interface VisualModelProps {
  schema: any;
}

export default function VisualModel({ schema }: VisualModelProps) {
  if (!schema) return null;

  const getActiveFocus = (controller: any) => {
    if (!controller) return 'neutral';
    
    const intent = (controller.question_intent || '').toLowerCase();
    const focus = (controller.focus_instruction || '').toLowerCase();
    const combined = `${intent} ${focus}`;

    if (combined.includes('pacing') || combined.includes('fast') || combined.includes('slow')) 
      return 'profile-pacing';
    if (combined.includes('uncertainty') || combined.includes('ambiguity') || combined.includes('unknown')) 
      return 'profile-uncertainty';
    if (combined.includes('goal') || combined.includes('outcome') || combined.includes('achieve')) 
      return 'goals';
    if (combined.includes('curiosity') || combined.includes('interest') || combined.includes('explore')) 
      return 'profile-curiosity';
    if (combined.includes('motivation') || combined.includes('why') || combined.includes('drive'))
      return 'profile-motivation';
    
    return 'neutral';
  };

  const activeFocus = getActiveFocus(schema.controller);
  const profile = schema.user_profile || {};
  const goalCandidates = schema.goal_candidates || [];

  return (
    <div className="visual-model">
      {/* 1. THE CORE: User Traits */}
      <div className="vm-section vm-core">
        <h3 className="vm-title">Core Identity</h3>
        <div className="vm-traits-grid">
          <TraitCard 
            label="Pacing" 
            value={profile.pacing_preference?.value}
            isActive={activeFocus === 'profile-pacing'} 
            type="pacing"
          />
          <TraitCard 
            label="Uncertainty" 
            value={profile.uncertainty_tolerance?.value}
            isActive={activeFocus === 'profile-uncertainty'} 
            type="uncertainty"
          />
          <TraitCard 
            label="Curiosity" 
            value={profile.curiosity_type?.value}
            isActive={activeFocus === 'profile-curiosity'} 
            type="curiosity"
          />
          <TraitCard 
            label="Motivation" 
            value={profile.motivation_profile?.primary_driver} // Assuming this exists or derived
            isActive={activeFocus === 'profile-motivation'} 
            type="motivation"
          />
        </div>
      </div>

      {/* 2. THE HORIZON: Possibilities */}
      <div className={`vm-section vm-horizon ${activeFocus === 'goals' ? 'active-section' : ''}`}>
        <h3 className="vm-title">Horizon</h3>
        <div className="vm-bubbles-container">
          {goalCandidates.length === 0 ? (
            <div className="vm-empty-state">Exploring possibilities...</div>
          ) : (
            goalCandidates.map((goal: any, i: number) => (
              <GoalBubble 
                key={i} 
                goal={goal} 
                isActive={activeFocus === 'goals'}
                index={i}
              />
            ))
          )}
        </div>
      </div>
      
      {/* 3. THE LENS: Current Focus (Visualized as an overlay or border effect on active elements) */}
      <div className="vm-status-bar">
        <span className="vm-status-label">Current Focus:</span>
        <span className="vm-status-value">
           {schema.controller?.question_intent || 'Observing...'}
        </span>
      </div>
    </div>
  );
}

// Sub-components

function TraitCard({ label, value, isActive, type }: { label: string, value: string | null, isActive: boolean, type: string }) {
  const isKnown = value !== null && value !== undefined;
  
  return (
    <div className={`vm-trait-card ${isActive ? 'active' : ''} ${isKnown ? 'known' : 'unknown'}`}>
      <span className="vm-trait-label">{label}</span>
      <span className="vm-trait-value">{value || '...'}</span>
      {isActive && <div className="vm-pulse-ring"></div>}
    </div>
  );
}

function GoalBubble({ goal, isActive, index }: { goal: any, isActive: boolean, index: number }) {
  // Size based on concreteness or another metric if available, else default
  const size = 60 + ((goal.concreteness || 0) * 40); 
  
  return (
    <div 
      className={`vm-goal-bubble ${isActive ? 'active' : ''}`}
      style={{ 
        width: `${size}px`, 
        height: `${size}px`,
        animationDelay: `${index * 0.2}s` 
      }}
      title={goal.goal}
    >
      <span className="vm-goal-text">{goal.goal.split(' ').slice(0, 3).join(' ')}...</span>
    </div>
  );
}

