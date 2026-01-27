"""Prompt formatter that converts PromptComponents into structured prompt strings."""
from pathlib import Path
from typing import List, Tuple, Optional
import json

from src.prompt.components import PromptComponents


def format_files(files: List[Tuple[Path, str]], repo_root: Path) -> str:
    """
    Format file contents with XML-like tags.
    
    Args:
        files: List of (path, content) tuples
        repo_root: Repository root for relative paths
        
    Returns:
        Formatted string with file contents
    """
    if not files:
        return ""
    
    file_parts = []
    for file_path, content in files:
        # Get relative path from repo root
        try:
            rel_path = file_path.relative_to(repo_root)
        except ValueError:
            rel_path = file_path
        
        file_parts.append(f'<lf:file path="{rel_path}">\n{content}\n</lf:file>')
    
    return "Files referenced in this context.\n\n" + "\n\n".join(file_parts)


def format_prompt(components: PromptComponents) -> str:
    """
    Format prompt components into the final prompt string with XML-like tags.
    
    Follows LoopFlow's format_prompt() pattern, with additions for Liminal-specific
    fields (conversation_history, schema_state, user_background, goal_context).
    
    Args:
        components: PromptComponents object with all context
        
    Returns:
        Formatted prompt string ready for LLM
    """
    parts = []
    
    # Run mode indicator
    if components.run_mode == "auto":
        parts.append(
            "Run mode is auto (headless). Proceed without pausing for questions. "
            "If you need clarification, make the best assumption you can."
        )
    
    # System instructions (like loopflow_doc)
    if components.system_instructions:
        parts.append(f"<lf:system>\n{components.system_instructions}\n</lf:system>")
    
    # Step/task prompt (highest priority content)
    if components.step:
        name, content = components.step
        if name == "inline":
            step_tag = f"<lf:step>\n{content}\n</lf:step>"
        else:
            step_tag = f"<lf:step:{name}>\n{content}\n</lf:step:{name}>"
        
        # Voices go between "The step." header and the actual step content
        if components.voices:
            if len(components.voices) == 1:
                v = components.voices[0]
                voice_section = f"<lf:voice:{v.name}>\n{v.content}\n</lf:voice:{v.name}>"
            else:
                voice_parts = [
                    f"<lf:voice:{v.name}>\n{v.content}\n</lf:voice:{v.name}>"
                    for v in components.voices
                ]
                voice_section = f"<lf:voices>\n{chr(10).join(voice_parts)}\n</lf:voices>"
            parts.append(f"The step.\n\n{voice_section}\n\n{step_tag}")
        else:
            parts.append(f"The step.\n\n{step_tag}")
    
    # Liminal-specific: User background
    if components.user_background:
        parts.append(
            f"User background information.\n\n"
            f"<lf:user_background>\n{components.user_background}\n</lf:user_background>"
        )
    
    # Liminal-specific: Conversation history
    if components.conversation_history:
        from src.prompt.gather import gather_conversation
        conversation_text = gather_conversation(components.conversation_history)
        if conversation_text:
            parts.append(
                f"Recent conversation history.\n\n"
                f"<lf:conversation>\n{conversation_text}\n</lf:conversation>"
            )
    
    # Liminal-specific: Schema state
    if components.schema_state:
        schema_json = json.dumps(components.schema_state, indent=2)
        parts.append(
            f"Current schema state.\n\n"
            f"<lf:schema>\n{schema_json}\n</lf:schema>"
        )
    
    # Liminal-specific: Goal context
    if components.goal_context:
        goal_json = json.dumps(components.goal_context, indent=2)
        parts.append(
            f"Goal-specific context.\n\n"
            f"<lf:goal_context>\n{goal_json}\n</lf:goal_context>"
        )

    # Panel context: Context tab items
    if components.goal_context_items:
        context_parts = []
        for item in components.goal_context_items:
            item_type = item.get("type", "text")
            content = item.get("content", "")
            file_name = item.get("file_name")
            if file_name:
                context_parts.append(f'<lf:context_item type="{item_type}" file="{file_name}">\n{content}\n</lf:context_item>')
            else:
                context_parts.append(f'<lf:context_item type="{item_type}">\n{content}\n</lf:context_item>')
        parts.append(
            f"User-provided context materials.\n\n"
            f"<lf:panel_context>\n{chr(10).join(context_parts)}\n</lf:panel_context>"
        )

    # Panel context: Active document from Draft tab
    if components.active_document:
        doc_title = components.active_document.get("title", "Untitled")
        doc_type = components.active_document.get("document_type", "notes")
        doc_content = components.active_document.get("content", "")
        parts.append(
            f"User's active document draft.\n\n"
            f'<lf:document title="{doc_title}" type="{doc_type}">\n{doc_content}\n</lf:document>'
        )

    # Panel context: Terminal observation
    if components.terminal_observation and components.terminal_observation.get("has_activity"):
        terminal = components.terminal_observation
        cwd = terminal.get("working_directory", "~")
        commands = terminal.get("commands", [])

        command_parts = []
        for cmd in commands:
            cmd_str = cmd.get("command", "")
            output = cmd.get("output", "")
            exit_code = cmd.get("exit_code", 0)
            if exit_code != 0:
                command_parts.append(f"$ {cmd_str}\n{output}\n[exit code: {exit_code}]")
            else:
                command_parts.append(f"$ {cmd_str}\n{output}")

        if command_parts:
            parts.append(
                f"Recent terminal activity (cwd: {cwd}).\n\n"
                f"<lf:terminal>\n{chr(10).join(command_parts)}\n</lf:terminal>"
            )

    # Channel suggestion context
    if components.channel_suggestion_context:
        context_json = json.dumps(components.channel_suggestion_context, indent=2)
        parts.append(
            f"Instructions for generating suggestions.\n\n"
            f"<lf:suggestion_context>\n{context_json}\n</lf:suggestion_context>"
        )

    # Documentation
    if components.docs:
        doc_parts = []
        for doc_path, content in components.docs:
            name = doc_path.stem
            doc_parts.append(f"<lf:{name}>\n{content}\n</lf:{name}>")
        docs_body = "\n\n".join(doc_parts)
        parts.append(
            "Repository documentation. Follow STYLE carefully.\n\n"
            f"<lf:docs>\n{docs_body}\n</lf:docs>"
        )
    
    # Summaries
    if components.summaries:
        summary_parts = []
        for summary_path, content in components.summaries:
            summary_parts.append(f'<lf:summary path="{summary_path}">\n{content}\n</lf:summary>')
        summaries_body = "\n\n".join(summary_parts)
        parts.append(
            "Pre-generated codebase summaries.\n\n"
            f"<lf:summaries>\n{summaries_body}\n</lf:summaries>"
        )
    
    # Diff
    if components.diff:
        parts.append(
            f"Changes on this branch (diff against main).\n\n"
            f"<lf:diff>\n{components.diff}\n</lf:diff>"
        )
    
    # Diff files
    if components.diff_files:
        parts.append(format_files(components.diff_files, components.repo_root))
    
    # Clipboard content
    if components.clipboard and components.clipboard.text:
        parts.append(
            f"Content from clipboard.\n\n"
            f"<lf:clipboard>\n{components.clipboard.text}\n</lf:clipboard>"
        )
    
    # Images (clipboard + image_files)
    all_images = list(components.image_files) if components.image_files else []
    if components.clipboard and components.clipboard.image_path:
        all_images.insert(0, components.clipboard.image_path)
    
    if all_images:
        image_refs = []
        for img_path in all_images:
            try:
                rel_path = img_path.relative_to(components.repo_root)
            except ValueError:
                rel_path = img_path
            image_refs.append(f'<lf:image path="{rel_path}">')
        parts.append("Images referenced in this context.\n\n" + "\n".join(image_refs))
    
    return "\n\n".join(parts)




