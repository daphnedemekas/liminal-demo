"""PTY-based terminal session management."""
import sys
import os
import pty
import select
import subprocess
import asyncio
import signal
from pathlib import Path
from typing import Optional, Dict, Callable, Any
from datetime import datetime
import uuid

# Add parent directory to path to import from src
sys.path.append(str(Path(__file__).parent.parent.parent))


class TerminalSession:
    """A single terminal session with PTY."""

    def __init__(
        self,
        session_id: str,
        working_dir: str = "~",
        shell: str = "/bin/zsh",
        rows: int = 24,
        cols: int = 80,
        on_output: Optional[Callable[[str], None]] = None
    ):
        self.session_id = session_id
        self.working_dir = os.path.expanduser(working_dir)
        self.shell = shell
        self.rows = rows
        self.cols = cols
        self.on_output = on_output

        self.master_fd: Optional[int] = None
        self.slave_fd: Optional[int] = None
        self.pid: Optional[int] = None
        self.is_active = False
        self.created_at = datetime.now()
        self.last_activity = datetime.now()

        # Buffer for output
        self._output_buffer: bytes = b""
        self._read_task: Optional[asyncio.Task] = None

    async def start(self) -> bool:
        """Start the terminal session with PTY."""
        try:
            # Create PTY pair
            self.master_fd, self.slave_fd = pty.openpty()

            # Set terminal size
            self._set_terminal_size(self.rows, self.cols)

            # Fork process
            self.pid = os.fork()

            if self.pid == 0:
                # Child process
                os.setsid()
                os.dup2(self.slave_fd, 0)  # stdin
                os.dup2(self.slave_fd, 1)  # stdout
                os.dup2(self.slave_fd, 2)  # stderr

                # Close master in child
                os.close(self.master_fd)

                # Change to working directory
                try:
                    os.chdir(self.working_dir)
                except Exception:
                    os.chdir(os.path.expanduser("~"))

                # Execute shell
                os.execv(self.shell, [self.shell, "-i"])
            else:
                # Parent process
                os.close(self.slave_fd)
                self.slave_fd = None
                self.is_active = True

                # Start async read task
                self._read_task = asyncio.create_task(self._read_output_loop())

                return True

        except Exception as e:
            print(f"[TerminalSession] Failed to start: {e}")
            self.is_active = False
            return False

    def _set_terminal_size(self, rows: int, cols: int):
        """Set the terminal window size."""
        if self.master_fd is None:
            return

        import fcntl
        import termios
        import struct

        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
        self.rows = rows
        self.cols = cols

    async def resize(self, rows: int, cols: int):
        """Resize the terminal."""
        self._set_terminal_size(rows, cols)

    async def _read_output_loop(self):
        """Continuously read output from the PTY."""
        try:
            while self.is_active and self.master_fd is not None:
                # Use select with timeout for non-blocking read
                readable, _, _ = select.select([self.master_fd], [], [], 0.1)

                if readable:
                    try:
                        data = os.read(self.master_fd, 4096)
                        if data:
                            self._output_buffer += data
                            self.last_activity = datetime.now()

                            if self.on_output:
                                try:
                                    self.on_output(data.decode("utf-8", errors="replace"))
                                except Exception as e:
                                    print(f"[TerminalSession] Output callback error: {e}")
                        else:
                            # EOF - process terminated
                            self.is_active = False
                            break
                    except OSError:
                        self.is_active = False
                        break

                await asyncio.sleep(0.01)  # Small delay to prevent CPU spinning

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[TerminalSession] Read loop error: {e}")
            self.is_active = False

    async def write_input(self, data: str):
        """Write input to the terminal."""
        if not self.is_active or self.master_fd is None:
            return False

        try:
            os.write(self.master_fd, data.encode("utf-8"))
            self.last_activity = datetime.now()
            return True
        except Exception as e:
            print(f"[TerminalSession] Write error: {e}")
            return False

    async def read_output(self, clear_buffer: bool = True) -> str:
        """Read available output from the buffer."""
        output = self._output_buffer.decode("utf-8", errors="replace")
        if clear_buffer:
            self._output_buffer = b""
        return output

    async def close(self):
        """Close the terminal session."""
        self.is_active = False

        # Cancel read task
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        # Close master FD
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except Exception:
                pass
            self.master_fd = None

        # Terminate child process
        if self.pid is not None:
            try:
                os.kill(self.pid, signal.SIGTERM)
                # Wait a bit then force kill if needed
                await asyncio.sleep(0.1)
                try:
                    os.kill(self.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            except ProcessLookupError:
                pass
            self.pid = None


class TerminalManager:
    """Manages multiple terminal sessions."""

    def __init__(self, max_sessions: int = 100, session_timeout_hours: int = 1):
        self.sessions: Dict[str, TerminalSession] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self.max_sessions = max_sessions
        self.session_timeout_hours = session_timeout_hours

    def _get_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create a lock for the given session_id."""
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    async def create_session(
        self,
        working_dir: str = "~",
        shell: str = "/bin/zsh",
        rows: int = 24,
        cols: int = 80,
        on_output: Optional[Callable[[str], None]] = None,
        session_id: Optional[str] = None
    ) -> Optional[TerminalSession]:
        """Create a new terminal session."""
        # Check session limit
        if len(self.sessions) >= self.max_sessions:
            # Try cleanup first
            await self.cleanup_old_sessions()
            if len(self.sessions) >= self.max_sessions:
                print(f"[TerminalManager] Session limit reached ({self.max_sessions})")
                return None

        session_id = session_id or str(uuid.uuid4())

        async with self._get_lock(session_id):
            session = TerminalSession(
                session_id=session_id,
                working_dir=working_dir,
                shell=shell,
                rows=rows,
                cols=cols,
                on_output=on_output
            )

            if await session.start():
                self.sessions[session_id] = session
                print(f"[TerminalManager] Session created: {session_id}")
                return session
            else:
                return None

    async def get_session(self, session_id: str) -> Optional[TerminalSession]:
        """Get an existing terminal session."""
        async with self._get_lock(session_id):
            session = self.sessions.get(session_id)
            if session and session.is_active:
                session.last_activity = datetime.now()
                return session
            return None

    async def write_input(self, session_id: str, data: str) -> bool:
        """Write input to a terminal session."""
        session = await self.get_session(session_id)
        if session:
            return await session.write_input(data)
        return False

    async def read_output(self, session_id: str) -> Optional[str]:
        """Read output from a terminal session."""
        session = await self.get_session(session_id)
        if session:
            return await session.read_output()
        return None

    async def resize(self, session_id: str, rows: int, cols: int) -> bool:
        """Resize a terminal session."""
        session = await self.get_session(session_id)
        if session:
            await session.resize(rows, cols)
            return True
        return False

    async def close_session(self, session_id: str) -> bool:
        """Close a terminal session."""
        async with self._get_lock(session_id):
            session = self.sessions.get(session_id)
            if session:
                await session.close()
                del self.sessions[session_id]
                print(f"[TerminalManager] Session closed: {session_id}")
                return True
            return False

    async def cleanup_old_sessions(self):
        """Remove sessions older than timeout."""
        now = datetime.now()
        to_close = []

        for session_id, session in self.sessions.items():
            age_hours = (now - session.last_activity).total_seconds() / 3600
            if age_hours > self.session_timeout_hours or not session.is_active:
                to_close.append(session_id)

        for session_id in to_close:
            await self.close_session(session_id)

        if to_close:
            print(f"[TerminalManager] Cleaned up {len(to_close)} old sessions")

    async def close_all(self):
        """Close all terminal sessions."""
        session_ids = list(self.sessions.keys())
        for session_id in session_ids:
            await self.close_session(session_id)


# Global terminal manager instance
terminal_manager = TerminalManager()
