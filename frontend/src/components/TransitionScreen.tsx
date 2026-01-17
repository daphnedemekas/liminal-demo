interface TransitionScreenProps {
  topic: {
    topic: string
    learning_hook: string
  }
  onStartLearning: () => void
}

export default function TransitionScreen({ topic, onStartLearning }: TransitionScreenProps) {
  return (
    <div className="transition-screen">
      <h2 className="topic-title">{topic.topic}</h2>
      <p className="learning-hook">{topic.learning_hook}</p>

      <button className="start-learning-btn" onClick={onStartLearning}>
        Start Learning
      </button>
    </div>
  )
}
