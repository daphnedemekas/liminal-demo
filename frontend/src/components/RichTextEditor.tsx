import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import Placeholder from '@tiptap/extension-placeholder'
import { useCallback, useEffect, useState } from 'react'

interface RichTextEditorProps {
  content: string
  onChange: (content: string, json: object) => void
  placeholder?: string
  onBlur?: () => void
  disabled?: boolean
}

const isValidImageUrl = (url: string): boolean => {
  return url.startsWith('http://') || url.startsWith('https://')
}

export default function RichTextEditor({
  content,
  onChange,
  placeholder = 'Start writing...',
  onBlur,
  disabled = false
}: RichTextEditorProps) {
  const [isImageUrlDialogOpen, setIsImageUrlDialogOpen] = useState(false)
  const [imageUrl, setImageUrl] = useState('')
  const [imageUrlError, setImageUrlError] = useState('')

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: {
          levels: [1, 2, 3]
        }
      }),
      Image.configure({
        inline: true,
        allowBase64: false
      }),
      Placeholder.configure({
        placeholder
      })
    ],
    content: content || '',
    editable: !disabled,
    onUpdate: ({ editor }) => {
      const plainText = editor.getText()
      const json = editor.getJSON()
      onChange(plainText, json)
    },
    onBlur: () => {
      onBlur?.()
    }
  })

  // Update content when prop changes (for loading saved documents)
  useEffect(() => {
    if (editor && content !== editor.getText()) {
      // Only update if the content is significantly different
      // This prevents cursor jumping during typing
      const currentContent = editor.getText()
      if (content !== currentContent && !editor.isFocused) {
        editor.commands.setContent(content || '')
      }
    }
  }, [content, editor])

  // Update editable state
  useEffect(() => {
    if (editor) {
      editor.setEditable(!disabled)
    }
  }, [disabled, editor])

  const addImage = useCallback(() => {
    if (!imageUrl) return

    if (!isValidImageUrl(imageUrl)) {
      setImageUrlError('URL must start with http:// or https://')
      return
    }

    if (editor) {
      editor.chain().focus().setImage({ src: imageUrl }).run()
      setImageUrl('')
      setImageUrlError('')
      setIsImageUrlDialogOpen(false)
    }
  }, [editor, imageUrl])

  if (!editor) {
    return <div className="rich-editor-loading">Loading editor...</div>
  }

  return (
    <div className="rich-editor-container">
      {/* Toolbar */}
      <div className="rich-editor-toolbar">
        {/* Text formatting */}
        <div className="toolbar-group">
          <button
            type="button"
            onClick={() => editor.chain().focus().toggleBold().run()}
            className={`toolbar-btn ${editor.isActive('bold') ? 'active' : ''}`}
            title="Bold (Cmd+B)"
          >
            <strong>B</strong>
          </button>
          <button
            type="button"
            onClick={() => editor.chain().focus().toggleItalic().run()}
            className={`toolbar-btn ${editor.isActive('italic') ? 'active' : ''}`}
            title="Italic (Cmd+I)"
          >
            <em>I</em>
          </button>
          <button
            type="button"
            onClick={() => editor.chain().focus().toggleStrike().run()}
            className={`toolbar-btn ${editor.isActive('strike') ? 'active' : ''}`}
            title="Strikethrough (Cmd+Shift+X)"
          >
            <s>S</s>
          </button>
        </div>

        <div className="toolbar-divider" />

        {/* Headings */}
        <div className="toolbar-group">
          <button
            type="button"
            onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
            className={`toolbar-btn ${editor.isActive('heading', { level: 1 }) ? 'active' : ''}`}
            title="Heading 1"
          >
            H1
          </button>
          <button
            type="button"
            onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
            className={`toolbar-btn ${editor.isActive('heading', { level: 2 }) ? 'active' : ''}`}
            title="Heading 2"
          >
            H2
          </button>
          <button
            type="button"
            onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
            className={`toolbar-btn ${editor.isActive('heading', { level: 3 }) ? 'active' : ''}`}
            title="Heading 3"
          >
            H3
          </button>
        </div>

        <div className="toolbar-divider" />

        {/* Lists */}
        <div className="toolbar-group">
          <button
            type="button"
            onClick={() => editor.chain().focus().toggleBulletList().run()}
            className={`toolbar-btn ${editor.isActive('bulletList') ? 'active' : ''}`}
            title="Bullet List"
          >
            <span style={{ fontSize: '14px' }}>•</span>
          </button>
          <button
            type="button"
            onClick={() => editor.chain().focus().toggleOrderedList().run()}
            className={`toolbar-btn ${editor.isActive('orderedList') ? 'active' : ''}`}
            title="Numbered List"
          >
            1.
          </button>
        </div>

        <div className="toolbar-divider" />

        {/* Block */}
        <div className="toolbar-group">
          <button
            type="button"
            onClick={() => editor.chain().focus().toggleCodeBlock().run()}
            className={`toolbar-btn ${editor.isActive('codeBlock') ? 'active' : ''}`}
            title="Code Block (Cmd+Shift+C)"
          >
            {'</>'}
          </button>
          <button
            type="button"
            onClick={() => editor.chain().focus().toggleBlockquote().run()}
            className={`toolbar-btn ${editor.isActive('blockquote') ? 'active' : ''}`}
            title="Blockquote"
          >
            "
          </button>
          <button
            type="button"
            onClick={() => editor.chain().focus().setHorizontalRule().run()}
            className="toolbar-btn"
            title="Horizontal Rule"
          >
            ―
          </button>
        </div>

        <div className="toolbar-divider" />

        {/* Insert */}
        <div className="toolbar-group">
          <button
            type="button"
            onClick={() => {
              setImageUrlError('')
              setIsImageUrlDialogOpen(true)
            }}
            className="toolbar-btn"
            title="Insert Image URL"
          >
            IMG
          </button>
        </div>

        <div className="toolbar-divider" />

        {/* History */}
        <div className="toolbar-group">
          <button
            type="button"
            onClick={() => editor.chain().focus().undo().run()}
            disabled={!editor.can().undo()}
            className="toolbar-btn"
            title="Undo (Cmd+Z)"
          >
            ↶
          </button>
          <button
            type="button"
            onClick={() => editor.chain().focus().redo().run()}
            disabled={!editor.can().redo()}
            className="toolbar-btn"
            title="Redo (Cmd+Shift+Z)"
          >
            ↷
          </button>
        </div>
      </div>

      {/* Editor content */}
      <EditorContent editor={editor} className="rich-editor-content" />

      {/* Image URL Dialog */}
      {isImageUrlDialogOpen && (
        <div className="image-url-dialog-overlay" onClick={() => setIsImageUrlDialogOpen(false)}>
          <div className="image-url-dialog" onClick={(e) => e.stopPropagation()}>
            <h4>Insert Image URL</h4>
            <input
              type="url"
              value={imageUrl}
              onChange={(e) => {
                setImageUrl(e.target.value)
                setImageUrlError('')
              }}
              placeholder="https://example.com/image.png"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  addImage()
                } else if (e.key === 'Escape') {
                  setIsImageUrlDialogOpen(false)
                }
              }}
            />
            {imageUrlError && (
              <p style={{ color: '#e53e3e', fontSize: '12px', margin: '4px 0 0' }}>
                {imageUrlError}
              </p>
            )}
            <div className="image-url-dialog-buttons">
              <button type="button" onClick={() => setIsImageUrlDialogOpen(false)}>
                Cancel
              </button>
              <button type="button" onClick={addImage} disabled={!imageUrl}>
                Insert
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
