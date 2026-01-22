"""Scheduler for coordinating parallel loop execution."""
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
import yaml


@dataclass
class SchedulerConfig:
    """Configuration for the loop scheduler."""
    
    concurrency: int = 3  # Max parallel iterations
    global_limit: int = 15  # Total outstanding across all operations


def load_scheduler_config(config_path: Optional[Path] = None) -> SchedulerConfig:
    """
    Load scheduler config from file or use defaults.
    
    Args:
        config_path: Optional path to config file (YAML format)
        
    Returns:
        SchedulerConfig object
    """
    if config_path and config_path.exists():
        try:
            data = yaml.safe_load(config_path.read_text()) or {}
            return SchedulerConfig(
                concurrency=data.get("concurrency", 3),
                global_limit=data.get("global_limit", 15),
            )
        except Exception:
            pass
    
    return SchedulerConfig()


class Scheduler:
    """
    Coordinates multiple agent operations with shared resource limits.
    
    Thread-safe slot management for parallel execution.
    """
    
    def __init__(self, config: Optional[SchedulerConfig] = None):
        """
        Initialize scheduler.
        
        Args:
            config: Optional scheduler configuration. If None, uses defaults.
        """
        self.config = config or SchedulerConfig()
        self._running: set[str] = set()  # run IDs currently executing
        self._lock = threading.Lock()
    
    @property
    def concurrency(self) -> int:
        """Maximum number of concurrent operations."""
        return self.config.concurrency
    
    @property
    def global_limit(self) -> int:
        """Global limit on outstanding operations."""
        return self.config.global_limit
    
    def slots_available(self) -> int:
        """Number of slots currently available."""
        with self._lock:
            return max(0, self.concurrency - len(self._running))
    
    def slots_used(self) -> int:
        """Number of slots currently in use."""
        with self._lock:
            return len(self._running)
    
    def total_outstanding(self) -> int:
        """
        Total outstanding operations across all agents.
        
        This is a placeholder - in a full implementation, would query
        the database or state manager to count outstanding operations.
        
        Returns:
            Number of outstanding operations
        """
        # For now, return number of running operations
        # In full implementation, would count pending tasks, unmerged PRs, etc.
        return len(self._running)
    
    def can_start(self) -> Tuple[bool, Optional[str]]:
        """
        Check if a new iteration can start.
        
        Returns:
            Tuple of (can_start, reason) where reason explains why if can't start.
        """
        with self._lock:
            if len(self._running) >= self.concurrency:
                return False, "concurrency"
        
        if self.total_outstanding() >= self.global_limit:
            return False, "global_limit"
        
        return True, None
    
    def acquire(self, run_id: str) -> Tuple[bool, Optional[str]]:
        """
        Try to acquire a slot for an operation.
        
        Args:
            run_id: Unique identifier for this run
            
        Returns:
            Tuple of (acquired, reason) where reason explains why if not acquired.
        """
        # Double-check pattern to avoid race conditions
        with self._lock:
            if len(self._running) >= self.concurrency:
                return False, "concurrency"
        
        if self.total_outstanding() >= self.global_limit:
            return False, "global_limit"
        
        # Acquire slot
        with self._lock:
            if len(self._running) >= self.concurrency:
                return False, "concurrency"
            self._running.add(run_id)
        
        return True, None
    
    def release(self, run_id: str) -> None:
        """
        Release a slot when an operation completes.
        
        Args:
            run_id: Unique identifier for the run to release
        """
        with self._lock:
            self._running.discard(run_id)


# Global scheduler instance for shared use
_scheduler: Optional[Scheduler] = None


def get_scheduler() -> Scheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler


def reset_scheduler() -> None:
    """Reset the global scheduler (for testing)."""
    global _scheduler
    _scheduler = None

