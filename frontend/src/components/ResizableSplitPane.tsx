import { useState, useRef, useEffect, ReactNode } from 'react'

interface ResizableSplitPaneProps {
  top: ReactNode
  bottom: ReactNode
  initialTopHeight?: number // Percentage (0-100)
  minTopHeight?: number // Percentage
  maxTopHeight?: number // Percentage
}

export default function ResizableSplitPane({
  top,
  bottom,
  initialTopHeight = 50,
  minTopHeight = 20,
  maxTopHeight = 80,
}: ResizableSplitPaneProps) {
  const [topHeight, setTopHeight] = useState(initialTopHeight)
  const [isDragging, setIsDragging] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const startYRef = useRef<number>(0)
  const startHeightRef = useRef<number>(initialTopHeight)

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging || !containerRef.current) return

      const container = containerRef.current
      const containerHeight = container.clientHeight
      const deltaY = e.clientY - startYRef.current
      const deltaPercent = (deltaY / containerHeight) * 100
      
      let newHeight = startHeightRef.current + deltaPercent
      
      // Clamp to min/max
      newHeight = Math.max(minTopHeight, Math.min(maxTopHeight, newHeight))
      
      setTopHeight(newHeight)
    }

    const handleMouseUp = () => {
      setIsDragging(false)
    }

    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = 'row-resize'
      document.body.style.userSelect = 'none'
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [isDragging, minTopHeight, maxTopHeight])

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    setIsDragging(true)
    startYRef.current = e.clientY
    startHeightRef.current = topHeight
  }

  return (
    <div 
      ref={containerRef}
      className="resizable-split-pane"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        width: '100%',
        overflow: 'hidden',
      }}
    >
      {/* Top Section */}
      <div
        style={{
          flex: `0 0 ${topHeight}%`,
          minHeight: 0,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {top}
      </div>

      {/* Resizer */}
      <div
        onMouseDown={handleMouseDown}
        className="resizable-split-pane-divider"
        style={{
          height: '4px',
          cursor: 'row-resize',
          backgroundColor: '#e2e8f0',
          position: 'relative',
          flexShrink: 0,
          transition: isDragging ? 'none' : 'background-color 0.2s',
        }}
        onMouseEnter={(e) => {
          if (!isDragging) {
            e.currentTarget.style.backgroundColor = '#3b82f6'
          }
        }}
        onMouseLeave={(e) => {
          if (!isDragging) {
            e.currentTarget.style.backgroundColor = '#e2e8f0'
          }
        }}
      >
        <div
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            width: '40px',
            height: '4px',
            backgroundColor: isDragging ? '#3b82f6' : '#cbd5e1',
            borderRadius: '2px',
            transition: isDragging ? 'none' : 'background-color 0.2s',
          }}
        />
      </div>

      {/* Bottom Section */}
      <div
        style={{
          flex: `0 0 ${100 - topHeight}%`,
          minHeight: 0,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {bottom}
      </div>
    </div>
  )
}

