"""Tests for scheduler."""
import pytest
import threading
import time
from src.scheduler.scheduler import Scheduler, SchedulerConfig, load_scheduler_config


def test_scheduler_default_config():
    """Test scheduler with default config."""
    scheduler = Scheduler()
    
    assert scheduler.concurrency == 3
    assert scheduler.global_limit == 15
    assert scheduler.slots_available() == 3
    assert scheduler.slots_used() == 0


def test_scheduler_custom_config():
    """Test scheduler with custom config."""
    config = SchedulerConfig(concurrency=5, global_limit=10)
    scheduler = Scheduler(config)
    
    assert scheduler.concurrency == 5
    assert scheduler.global_limit == 10


def test_scheduler_acquire_release():
    """Test acquiring and releasing slots."""
    scheduler = Scheduler(SchedulerConfig(concurrency=2))
    
    # Acquire first slot
    acquired, reason = scheduler.acquire("run1")
    assert acquired is True
    assert reason is None
    assert scheduler.slots_used() == 1
    assert scheduler.slots_available() == 1
    
    # Acquire second slot
    acquired, reason = scheduler.acquire("run2")
    assert acquired is True
    assert scheduler.slots_used() == 2
    assert scheduler.slots_available() == 0
    
    # Try to acquire third (should fail)
    acquired, reason = scheduler.acquire("run3")
    assert acquired is False
    assert reason == "concurrency"
    
    # Release a slot
    scheduler.release("run1")
    assert scheduler.slots_used() == 1
    assert scheduler.slots_available() == 1
    
    # Now can acquire again
    acquired, reason = scheduler.acquire("run3")
    assert acquired is True


def test_scheduler_can_start():
    """Test can_start() method."""
    scheduler = Scheduler(SchedulerConfig(concurrency=2))
    
    can_start, reason = scheduler.can_start()
    assert can_start is True
    assert reason is None
    
    # Fill slots
    scheduler.acquire("run1")
    scheduler.acquire("run2")
    
    can_start, reason = scheduler.can_start()
    assert can_start is False
    assert reason == "concurrency"
    
    scheduler.release("run1")
    can_start, reason = scheduler.can_start()
    assert can_start is True


def test_scheduler_thread_safety():
    """Test that scheduler is thread-safe."""
    scheduler = Scheduler(SchedulerConfig(concurrency=3))
    results = []
    
    def worker(worker_id: int):
        run_id = f"run_{worker_id}"
        acquired, _ = scheduler.acquire(run_id)
        results.append((worker_id, acquired))
        if acquired:
            time.sleep(0.1)  # Simulate work
            scheduler.release(run_id)
    
    # Start 10 threads trying to acquire slots
    threads = []
    for i in range(10):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
    
    # Wait for all threads
    for t in threads:
        t.join()
    
    # Should have exactly 3 successful acquisitions (concurrency limit)
    successful = [r for r in results if r[1] is True]
    assert len(successful) == 3
    
    # All slots should be released
    assert scheduler.slots_used() == 0
    assert scheduler.slots_available() == 3


def test_scheduler_load_config(tmp_path):
    """Test loading scheduler config from file."""
    config_file = tmp_path / "scheduler.yaml"
    config_file.write_text("concurrency: 5\nglobal_limit: 20\n")
    
    config = load_scheduler_config(config_file)
    assert config.concurrency == 5
    assert config.global_limit == 20


def test_scheduler_load_config_defaults():
    """Test loading scheduler config with defaults."""
    config = load_scheduler_config()
    assert config.concurrency == 3
    assert config.global_limit == 15




