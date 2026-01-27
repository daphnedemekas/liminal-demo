#!/usr/bin/env python3
"""Monitor backend logs for testing flow verification."""
import time
import subprocess
import re
import sys
from collections import defaultdict

class TestMonitor:
    def __init__(self):
        self.events = defaultdict(list)
        self.errors = []
        self.checkpoints = {
            'exploration_started': False,
            'goal_proposed': False,
            'goal_accepted': False,
            'goal_chat_opened': False,
            'exploration_context_used': False,
            'teaching_candidates_found': False,
            'curriculum_generated': False,
            'panel_context_gathered': False,
        }
        
    def check_log_file(self, log_file='backend.log'):
        """Check backend log file for key events."""
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                # Check last 100 lines for recent activity
                for line in lines[-100:]:
                    self.analyze_line(line)
        except FileNotFoundError:
            # Log file might not exist yet, that's okay
            pass
        except Exception as e:
            print(f"Error reading log: {e}")
    
    def analyze_line(self, line):
        """Analyze a log line for key events."""
        # Exploration context usage
        if 'Using' in line and 'messages from exploration chat as context' in line:
            self.checkpoints['exploration_context_used'] = True
            self.events['exploration_context'].append(line.strip())
            print(f"✅ EXPLORATION CONTEXT USED: {line.strip()}")
        
        # Goal proposed
        if 'Goal proposed:' in line or '__GOAL_PROPOSED__' in line:
            self.checkpoints['goal_proposed'] = True
            self.events['goal_proposed'].append(line.strip())
            print(f"✅ GOAL PROPOSED: {line.strip()}")
        
        # Goal accepted
        if 'GOAL ACCEPTED' in line or 'accept_proposed_goal' in line:
            self.checkpoints['goal_accepted'] = True
            self.events['goal_accepted'].append(line.strip())
            print(f"✅ GOAL ACCEPTED: {line.strip()}")
        
        # Goal chat opened
        if 'Goal session with existing user' in line or 'Goal provided:' in line:
            self.checkpoints['goal_chat_opened'] = True
            self.events['goal_chat'].append(line.strip())
            print(f"✅ GOAL CHAT OPENED: {line.strip()}")
        
        # Teaching candidates
        if 'Teaching candidate' in line and 'readiness_score' in line:
            self.checkpoints['teaching_candidates_found'] = True
            self.events['teaching_candidates'].append(line.strip())
            print(f"✅ TEACHING CANDIDATE FOUND: {line.strip()}")
        
        # Curriculum generation
        if 'MANUAL LEARNING PATH GENERATION' in line or '__GENERATE_LEARNING_PATH__' in line:
            self.checkpoints['curriculum_generated'] = True
            self.events['curriculum'].append(line.strip())
            print(f"✅ CURRICULUM GENERATION: {line.strip()}")
        
        # Panel context
        if 'Gathering panel context' in line or 'gather_goal_context_items' in line:
            self.checkpoints['panel_context_gathered'] = True
            self.events['panel_context'].append(line.strip())
            print(f"✅ PANEL CONTEXT GATHERED: {line.strip()}")
        
        # Errors
        if 'ERROR' in line or 'Error' in line or 'Traceback' in line:
            self.errors.append(line.strip())
            print(f"❌ ERROR: {line.strip()}")
        
        # Auto curriculum proposal (should NOT happen)
        if 'propose_tasks mode' in line and 'MANUAL' not in line:
            print(f"⚠️  WARNING: Auto curriculum proposal detected: {line.strip()}")
    
    def print_status(self):
        """Print current test status."""
        print("\n" + "="*60)
        print("TEST STATUS CHECKPOINTS:")
        print("="*60)
        for checkpoint, status in self.checkpoints.items():
            status_icon = "✅" if status else "⏳"
            print(f"{status_icon} {checkpoint.replace('_', ' ').title()}")
        print("="*60)
        if self.errors:
            print(f"\n❌ ERRORS FOUND: {len(self.errors)}")
            for error in self.errors[-5:]:  # Show last 5 errors
                print(f"  - {error}")
        print()

if __name__ == '__main__':
    monitor = TestMonitor()
    print("="*60)
    print("BACKEND LOG MONITOR - ACTIVE")
    print("="*60)
    print("Monitoring backend.log for test flow events...")
    print("Please test in browser at http://localhost:5173")
    print("Press Ctrl+C to stop")
    print("="*60)
    print()
    
    try:
        while True:
            monitor.check_log_file()
            time.sleep(2)  # Check every 2 seconds
            # Print status every 10 seconds
            if int(time.time()) % 10 == 0:
                monitor.print_status()
                time.sleep(1)  # Avoid printing multiple times in same second
    except KeyboardInterrupt:
        print("\n\n" + "="*60)
        print("FINAL TEST STATUS:")
        print("="*60)
        monitor.print_status()
        print("Monitoring stopped.")


