import { useState } from 'react'

export interface ModelConfig {
  interviewer?: string
  ranker?: string
}

interface ModelSelectorProps {
  onModelSelect: (config: ModelConfig) => void
  initialConfig?: ModelConfig
}

interface ModelOption {
  value: string
  label: string
  description: string
}

const INTERVIEWER_MODELS: ModelOption[] = [
  { value: 'cerebras:llama-3.3-70b', label: 'Cerebras Llama 3.3 70B', description: 'Fast, natural conversation' },
  { value: 'cerebras:llama3.1-8b', label: 'Cerebras Llama 3.1 8B', description: 'Very fast, lower cost' },
  { value: 'anthropic:claude-sonnet-4-20250514', label: 'Claude Sonnet 4', description: 'High quality, slower' },
  { value: 'anthropic:claude-3-5-haiku-20241022', label: 'Claude Haiku 3.5', description: 'Good balance' },
  { value: 'openai:gpt-5', label: 'GPT-5', description: 'OpenAI most capable' },
  { value: 'openai:gpt-4o', label: 'GPT-4o', description: 'OpenAI balanced' },
  { value: 'openai:gpt-4o-mini', label: 'GPT-4o Mini', description: 'OpenAI fast' },
]

const RANKER_MODELS: ModelOption[] = [
  { value: 'cerebras:llama-3.3-70b', label: 'Cerebras Llama 3.3 70B', description: 'Fast analysis' },
  { value: 'anthropic:claude-sonnet-4-20250514', label: 'Claude Sonnet 4', description: 'Best quality' },
  { value: 'anthropic:claude-3-5-haiku-20241022', label: 'Claude Haiku 3.5', description: 'Good balance' },
  { value: 'openai:gpt-5', label: 'GPT-5', description: 'OpenAI most capable' },
  { value: 'openai:gpt-4o', label: 'GPT-4o', description: 'OpenAI balanced' },
  { value: 'openai:gpt-4o-mini', label: 'GPT-4o Mini', description: 'OpenAI fast' },
  { value: 'cerebras:llama3.1-8b', label: 'Cerebras Llama 3.1 8B', description: 'Very fast' },
]

export default function ModelSelector({ onModelSelect, initialConfig }: ModelSelectorProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [interviewerModel, setInterviewerModel] = useState(
    initialConfig?.interviewer || 'openai:gpt-4o'
  )
  const [rankerModel, setRankerModel] = useState(
    initialConfig?.ranker || 'openai:gpt-4o'
  )

  const handleApply = () => {
    onModelSelect({
      interviewer: interviewerModel,
      ranker: rankerModel,
    })
    setIsOpen(false)
  }

  const selectedInterviewer = INTERVIEWER_MODELS.find((m) => m.value === interviewerModel)
  const selectedRanker = RANKER_MODELS.find((m) => m.value === rankerModel)

  return (
    <div className="model-selector">
      <button className="model-selector-toggle" onClick={() => setIsOpen(!isOpen)}>
        Models
      </button>

      {isOpen && (
        <div className="model-selector-panel">
          <div className="model-selector-header">
            <h3>Model Configuration</h3>
            <button className="close-button" onClick={() => setIsOpen(false)}>
              ×
            </button>
          </div>

          <div className="model-section">
            <label className="model-label">
              <span className="label-text">Interviewer (Asks Questions)</span>
              <span className="current-selection">
                {selectedInterviewer?.label}
              </span>
            </label>
            <select
              className="model-select"
              value={interviewerModel}
              onChange={(e) => setInterviewerModel(e.target.value)}
            >
              {INTERVIEWER_MODELS.map((model) => (
                <option key={model.value} value={model.value}>
                  {model.label} - {model.description}
                </option>
              ))}
            </select>
          </div>

          <div className="model-section">
            <label className="model-label">
              <span className="label-text">Ranker (Analyzes Conversation)</span>
              <span className="current-selection">
                {selectedRanker?.label}
              </span>
            </label>
            <select
              className="model-select"
              value={rankerModel}
              onChange={(e) => setRankerModel(e.target.value)}
            >
              {RANKER_MODELS.map((model) => (
                <option key={model.value} value={model.value}>
                  {model.label} - {model.description}
                </option>
              ))}
            </select>
          </div>

          <div className="model-info">
            <p className="info-text">
              <strong>Tip:</strong> Use Cerebras models for fastest response, Claude Sonnet 4 for best quality.
            </p>
          </div>

          <div className="model-actions">
            <button className="apply-button" onClick={handleApply}>
              Apply & Start Session
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
