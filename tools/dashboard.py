#!/usr/bin/env python3
"""
Real-time performance monitoring dashboard
Web-based visualization of processing status and performance metrics
"""

import sys
import os
import json
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

# Try to import Flask
try:
    from flask import Flask, render_template, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    print("WARNING: Flask not installed. Dashboard disabled.")
    print("Install with: pip install flask")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'analysis'))

from parallel_analyzer.progress_monitor import ProgressState
from parallel_analyzer.performance_analyzer import PerformanceAnalyzer


@dataclass
class DashboardState:
    """Current dashboard state"""
    status: str = "idle"  # idle, running, completed, error
    stage: str = ""
    progress: float = 0.0
    completed: int = 0
    total: int = 0
    rate: float = 0.0
    eta_seconds: Optional[float] = None
    elapsed_seconds: float = 0.0
    
    # Resource usage
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    
    # Performance metrics
    files_per_second: float = 0.0
    total_extents: int = 0
    
    # Error tracking
    errors: int = 0
    
    timestamp: str = ""
    
    def to_dict(self):
        return asdict(self)


class DashboardServer:
    """
    Flask-based dashboard server
    
    Provides real-time web interface for monitoring processing
    """
    
    def __init__(self, host='127.0.0.1', port=5000):
        if not FLASK_AVAILABLE:
            raise ImportError("Flask not available")
        
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        
        self.state = DashboardState()
        self.state_lock = threading.Lock()
        
        self.history: List[DashboardState] = []
        self.max_history = 100
        
        self.performance_data = []
        
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/')
        def index():
            """Main dashboard page"""
            return render_template('dashboard.html')
        
        @self.app.route('/api/state')
        def get_state():
            """Get current state"""
            with self.state_lock:
                return jsonify(self.state.to_dict())
        
        @self.app.route('/api/history')
        def get_history():
            """Get state history"""
            with self.state_lock:
                return jsonify([s.to_dict() for s in self.history])
        
        @self.app.route('/api/performance')
        def get_performance():
            """Get performance metrics"""
            with self.state_lock:
                return jsonify(self.performance_data)
    
    def update_state(self, **kwargs):
        """Update dashboard state"""
        with self.state_lock:
            for key, value in kwargs.items():
                if hasattr(self.state, key):
                    setattr(self.state, key, value)
            
            self.state.timestamp = datetime.now().isoformat()
            
            # Add to history
            self.history.append(DashboardState(**asdict(self.state)))
            
            # Trim history
            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history:]
    
    def run(self):
        """Start dashboard server"""
        print(f"Starting dashboard server at http://{self.host}:{self.port}")
        self.app.run(host=self.host, port=self.port, debug=False)


class TerminalDashboard:
    """
    Terminal-based dashboard for systems without Flask
    Uses ANSI escape codes for live updates
    """
    
    def __init__(self):
        self.state = DashboardState()
        self._stop_event = threading.Event()
        self._update_thread = None
    
    def start(self):
        """Start terminal dashboard"""
        self._update_thread = threading.Thread(target=self._render_loop, daemon=True)
        self._update_thread.start()
    
    def stop(self):
        """Stop terminal dashboard"""
        self._stop_event.set()
        if self._update_thread:
            self._update_thread.join(timeout=1)
    
    def update_state(self, **kwargs):
        """Update state"""
        for key, value in kwargs.items():
            if hasattr(self.state, key):
                setattr(self.state, key, value)
    
    def _render_loop(self):
        """Render loop"""
        while not self._stop_event.is_set():
            self._render()
            time.sleep(0.5)
    
    def _render(self):
        """Render dashboard to terminal"""
        # Clear screen
        print("\033[2J\033[H", end='')
        
        print("=" * 80)
        print(" " * 20 + "FRAGPICKER PARALLEL ANALYZER DASHBOARD")
        print("=" * 80)
        print()
        
        # Status
        status_color = {
            'idle': '\033[90m',      # Gray
            'running': '\033[92m',   # Green
            'completed': '\033[94m', # Blue
            'error': '\033[91m'      # Red
        }.get(self.state.status, '\033[0m')
        
        print(f"Status: {status_color}{self.state.status.upper()}\033[0m")
        print(f"Stage:  {self.state.stage}")
        print()
        
        # Progress bar
        if self.state.total > 0:
            width = 50
            filled = int(width * self.state.progress / 100)
            bar = "█" * filled + "░" * (width - filled)
            
            print(f"Progress: [{bar}] {self.state.progress:.1f}%")
            print(f"Files:    {self.state.completed:,} / {self.state.total:,}")
            print()
        
        # Performance metrics
        print("Performance:")
        print(f"  Rate:        {self.state.rate:.1f} files/sec")
        print(f"  Elapsed:     {self._format_time(self.state.elapsed_seconds)}")
        
        if self.state.eta_seconds:
            print(f"  ETA:         {self._format_time(self.state.eta_seconds)}")
        print()
        
        # Resource usage
        print("Resources:")
        print(f"  CPU:         {self.state.cpu_percent:.1f}%")
        print(f"  Memory:      {self.state.memory_mb:.1f} MB")
        print()
        
        # Statistics
        print("Statistics:")
        print(f"  Total extents: {self.state.total_extents:,}")
        print(f"  Errors:        {self.state.errors}")
        print()
        
        print("=" * 80)
        print("Press Ctrl+C to stop")
    
    def _format_time(self, seconds: float) -> str:
        """Format seconds as HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def create_dashboard_html():
    """
    Create HTML template for web dashboard
    
    This should be saved as templates/dashboard.html
    """
    html = '''<!DOCTYPE html>
<html>
<head>
    <title>FragPicker Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a1a;
            color: #e0e0e0;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        h1 { font-size: 2em; margin-bottom: 10px; }
        .status { font-size: 1.2em; opacity: 0.9; }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .card {
            background: #2a2a2a;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        .card h2 {
            font-size: 1.2em;
            margin-bottom: 15px;
            color: #667eea;
        }
        .metric {
            display: flex;
            justify-content: space-between;
            margin: 10px 0;
            padding: 10px;
            background: #333;
            border-radius: 5px;
        }
        .metric-label { opacity: 0.8; }
        .metric-value { font-weight: bold; font-size: 1.1em; }
        .progress-container {
            width: 100%;
            height: 30px;
            background: #333;
            border-radius: 15px;
            overflow: hidden;
            margin: 10px 0;
        }
        .progress-bar {
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            transition: width 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
        }
        .chart-container {
            position: relative;
            height: 300px;
            margin-top: 20px;
        }
        .status-badge {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: bold;
        }
        .status-running { background: #4CAF50; }
        .status-idle { background: #9E9E9E; }
        .status-completed { background: #2196F3; }
        .status-error { background: #F44336; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>FragPicker Parallel Analyzer</h1>
            <div class="status">
                Status: <span id="status" class="status-badge status-idle">IDLE</span>
                <span id="stage"></span>
            </div>
        </div>
        
        <div class="card">
            <h2>Progress</h2>
            <div class="progress-container">
                <div id="progress-bar" class="progress-bar" style="width: 0%">0%</div>
            </div>
            <div class="metric">
                <span class="metric-label">Files Processed</span>
                <span class="metric-value" id="completed">0 / 0</span>
            </div>
            <div class="metric">
                <span class="metric-label">Elapsed Time</span>
                <span class="metric-value" id="elapsed">00:00:00</span>
            </div>
            <div class="metric">
                <span class="metric-label">ETA</span>
                <span class="metric-value" id="eta">--:--:--</span>
            </div>
        </div>
        
        <div class="grid">
            <div class="card">
                <h2>Performance</h2>
                <div class="metric">
                    <span class="metric-label">Processing Rate</span>
                    <span class="metric-value" id="rate">0 files/sec</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Total Extents</span>
                    <span class="metric-value" id="extents">0</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Errors</span>
                    <span class="metric-value" id="errors">0</span>
                </div>
            </div>
            
            <div class="card">
                <h2>Resources</h2>
                <div class="metric">
                    <span class="metric-label">CPU Usage</span>
                    <span class="metric-value" id="cpu">0%</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Memory Usage</span>
                    <span class="metric-value" id="memory">0 MB</span>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>Performance Over Time</h2>
            <div class="chart-container">
                <canvas id="performanceChart"></canvas>
            </div>
        </div>
    </div>
    
    <script>
        // Chart setup
        const ctx = document.getElementById('performanceChart').getContext('2d');
        const chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Files/sec',
                    data: [],
                    borderColor: '#667eea',
                    tension: 0.4,
                    fill: false
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true }
                }
            }
        });
        
        // Update function
        async function updateDashboard() {
            try {
                const response = await fetch('/api/state');
                const state = await response.json();
                
                // Update status
                const statusEl = document.getElementById('status');
                statusEl.textContent = state.status.toUpperCase();
                statusEl.className = 'status-badge status-' + state.status;
                
                document.getElementById('stage').textContent = state.stage;
                
                // Update progress
                const progress = state.progress || 0;
                document.getElementById('progress-bar').style.width = progress + '%';
                document.getElementById('progress-bar').textContent = progress.toFixed(1) + '%';
                
                document.getElementById('completed').textContent = 
                    `${state.completed.toLocaleString()} / ${state.total.toLocaleString()}`;
                
                // Update times
                document.getElementById('elapsed').textContent = formatTime(state.elapsed_seconds);
                document.getElementById('eta').textContent = 
                    state.eta_seconds ? formatTime(state.eta_seconds) : '--:--:--';
                
                // Update metrics
                document.getElementById('rate').textContent = state.rate.toFixed(1) + ' files/sec';
                document.getElementById('extents').textContent = state.total_extents.toLocaleString();
                document.getElementById('errors').textContent = state.errors;
                
                document.getElementById('cpu').textContent = state.cpu_percent.toFixed(1) + '%';
                document.getElementById('memory').textContent = state.memory_mb.toFixed(1) + ' MB';
                
                // Update chart
                if (state.rate > 0) {
                    const now = new Date().toLocaleTimeString();
                    chart.data.labels.push(now);
                    chart.data.datasets[0].data.push(state.rate);
                    
                    // Keep last 20 points
                    if (chart.data.labels.length > 20) {
                        chart.data.labels.shift();
                        chart.data.datasets[0].data.shift();
                    }
                    
                    chart.update('none'); // No animation for performance
                }
                
            } catch (error) {
                console.error('Error updating dashboard:', error);
            }
        }
        
        function formatTime(seconds) {
            if (!seconds || seconds < 0) return '--:--:--';
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = Math.floor(seconds % 60);
            return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
        }
        
        // Update every 500ms
        setInterval(updateDashboard, 500);
        updateDashboard();
    </script>
</body>
</html>'''
    
    return html


def save_dashboard_template():
    """Save dashboard HTML template"""
    template_dir = Path(__file__).parent / 'templates'
    template_dir.mkdir(exist_ok=True)
    
    template_path = template_dir / 'dashboard.html'
    with open(template_path, 'w') as f:
        f.write(create_dashboard_html())
    
    print(f"Dashboard template saved to {template_path}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='FragPicker Dashboard')
    parser.add_argument('--mode', choices=['web', 'terminal', 'save-template'],
                       default='terminal',
                       help='Dashboard mode')
    parser.add_argument('--host', default='127.0.0.1',
                       help='Web dashboard host')
    parser.add_argument('--port', type=int, default=5000,
                       help='Web dashboard port')
    
    args = parser.parse_args()
    
    if args.mode == 'save-template':
        save_dashboard_template()
    
    elif args.mode == 'web':
        if not FLASK_AVAILABLE:
            print("ERROR: Flask not installed")
            print("Install with: pip install flask")
            sys.exit(1)
        
        # Save template if needed
        save_dashboard_template()
        
        dashboard = DashboardServer(host=args.host, port=args.port)
        
        # Demo: update dashboard in background
        def demo_updates():
            time.sleep(2)
            dashboard.update_state(
                status='running',
                stage='Processing files',
                total=1000
            )
            
            for i in range(1000):
                time.sleep(0.01)
                dashboard.update_state(
                    completed=i+1,
                    progress=(i+1)/10,
                    rate=100,
                    cpu_percent=75,
                    memory_mb=250
                )
            
            dashboard.update_state(status='completed')
        
        demo_thread = threading.Thread(target=demo_updates, daemon=True)
        demo_thread.start()
        
        dashboard.run()
    
    else:  # terminal
        dashboard = TerminalDashboard()
        dashboard.start()
        
        # Demo updates
        dashboard.update_state(status='running', stage='Demo', total=100)
        
        try:
            for i in range(100):
                time.sleep(0.1)
                dashboard.update_state(
                    completed=i+1,
                    progress=i+1,
                    rate=10,
                    elapsed_seconds=(i+1)*0.1,
                    cpu_percent=50 + i % 30,
                    memory_mb=200 + i
                )
            
            dashboard.update_state(status='completed')
            time.sleep(2)
        
        except KeyboardInterrupt:
            pass
        
        finally:
            dashboard.stop()