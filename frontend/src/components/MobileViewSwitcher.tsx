interface MobileViewSwitcherProps {
  activeView: string
  views: { key: string; label: string }[]
  onViewChange: (key: string) => void
}

export default function MobileViewSwitcher({ activeView, views, onViewChange }: MobileViewSwitcherProps) {
  return (
    <div className="mobile-view-switcher">
      {views.map((view) => (
        <button
          key={view.key}
          className={`mobile-view-tab ${activeView === view.key ? 'active' : ''}`}
          onClick={() => onViewChange(view.key)}
        >
          {view.label}
        </button>
      ))}
    </div>
  )
}
