"""
Resource Monitor Module

Monitors system resources (CPU, memory, network, disk) for scalability
and performance optimization decisions.
"""

import threading
import time
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from collections import deque
import os

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from chat_app.shared.exceptions import ResourceMonitorError


logger = logging.getLogger(__name__)


@dataclass
class ResourceStats:
    """System resource statistics."""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_available_mb: float
    disk_usage_percent: float
    network_bytes_sent: int
    network_bytes_recv: int
    active_connections: int
    load_average: List[float]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'cpu_percent': self.cpu_percent,
            'memory_percent': self.memory_percent,
            'memory_used_mb': self.memory_used_mb,
            'memory_available_mb': self.memory_available_mb,
            'disk_usage_percent': self.disk_usage_percent,
            'network_bytes_sent': self.network_bytes_sent,
            'network_bytes_recv': self.network_bytes_recv,
            'active_connections': self.active_connections,
            'load_average': self.load_average
        }


@dataclass
class ResourceThresholds:
    """Resource usage thresholds for alerts and scaling decisions."""
    cpu_warning: float = 70.0
    cpu_critical: float = 90.0
    memory_warning: float = 75.0
    memory_critical: float = 90.0
    disk_warning: float = 80.0
    disk_critical: float = 95.0
    connections_warning: int = 800
    connections_critical: int = 950


class ResourceAlert:
    """Represents a resource usage alert."""
    
    def __init__(
        self,
        alert_type: str,
        resource: str,
        level: str,
        current_value: float,
        threshold: float,
        message: str
    ):
        self.alert_type = alert_type
        self.resource = resource
        self.level = level  # warning, critical
        self.current_value = current_value
        self.threshold = threshold
        self.message = message
        self.timestamp = datetime.now()
        self.alert_id = f"{resource}_{level}_{int(self.timestamp.timestamp())}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'alert_id': self.alert_id,
            'alert_type': self.alert_type,
            'resource': self.resource,
            'level': self.level,
            'current_value': self.current_value,
            'threshold': self.threshold,
            'message': self.message,
            'timestamp': self.timestamp.isoformat()
        }


class ResourceMonitor:
    """
    System resource monitor for scalability and performance optimization.
    
    Features:
    - CPU, memory, disk, and network monitoring
    - Configurable thresholds and alerts
    - Historical data collection
    - Resource trend analysis
    - Integration with scaling decisions
    - Performance metrics collection
    """
    
    def __init__(
        self,
        monitoring_interval: int = 30,
        history_size: int = 1000,
        thresholds: Optional[ResourceThresholds] = None,
        enable_alerts: bool = True
    ):
        """
        Initialize the resource monitor.
        
        Args:
            monitoring_interval: Interval between resource checks in seconds
            history_size: Number of historical data points to keep
            thresholds: Resource usage thresholds
            enable_alerts: Whether to generate alerts
        """
        self.monitoring_interval = monitoring_interval
        self.history_size = history_size
        self.thresholds = thresholds or ResourceThresholds()
        self.enable_alerts = enable_alerts
        
        # Data storage
        self._lock = threading.RLock()
        self._resource_history: deque = deque(maxlen=history_size)
        self._active_alerts: Dict[str, ResourceAlert] = {}
        self._alert_history: deque = deque(maxlen=100)
        
        # Monitoring thread
        self._monitoring_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        
        # Alert callbacks
        self._alert_callbacks: List[Callable[[ResourceAlert], None]] = []
        
        # Statistics
        self.start_time = datetime.now()
        self.monitoring_cycles = 0
        self.alerts_generated = 0
        
        # Network baseline for calculating rates
        self._last_network_stats = None
        self._last_network_time = None
        
        if not HAS_PSUTIL:
            logger.warning("psutil not available - resource monitoring will use fallback values")
        
        logger.info(f"ResourceMonitor initialized with interval={monitoring_interval}s")
    
    def start(self) -> None:
        """Start resource monitoring."""
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            logger.warning("Resource monitoring is already running")
            return
        
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            name="Resource-Monitor",
            daemon=True
        )
        self._monitoring_thread.start()
        
        logger.info("Resource monitoring started")
    
    def stop(self) -> None:
        """Stop resource monitoring."""
        logger.info("Stopping resource monitoring...")
        
        self._shutdown_event.set()
        
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            self._monitoring_thread.join(timeout=5.0)
            if self._monitoring_thread.is_alive():
                logger.warning("Resource monitoring thread did not stop gracefully")
        
        logger.info("Resource monitoring stopped")
    
    def get_current_stats(self) -> ResourceStats:
        """
        Get current resource statistics.
        
        Returns:
            Current resource statistics
        """
        return self._collect_resource_stats()
    
    def get_historical_stats(self, minutes: int = 60) -> List[ResourceStats]:
        """
        Get historical resource statistics.
        
        Args:
            minutes: Number of minutes of history to retrieve
            
        Returns:
            List of resource statistics
        """
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        
        with self._lock:
            return [
                stats for stats in self._resource_history
                if stats.timestamp >= cutoff_time
            ]
    
    def get_resource_trends(self, minutes: int = 30) -> Dict[str, Dict[str, float]]:
        """
        Get resource usage trends.
        
        Args:
            minutes: Time window for trend analysis
            
        Returns:
            Dictionary with trend information for each resource
        """
        historical_stats = self.get_historical_stats(minutes)
        
        if len(historical_stats) < 2:
            return {}
        
        trends = {}
        
        # Calculate trends for each metric
        metrics = ['cpu_percent', 'memory_percent', 'disk_usage_percent']
        
        for metric in metrics:
            values = [getattr(stats, metric) for stats in historical_stats]
            
            if len(values) >= 2:
                # Simple linear trend calculation
                first_half = values[:len(values)//2]
                second_half = values[len(values)//2:]
                
                avg_first = sum(first_half) / len(first_half)
                avg_second = sum(second_half) / len(second_half)
                
                trend_direction = "increasing" if avg_second > avg_first else "decreasing"
                trend_magnitude = abs(avg_second - avg_first)
                
                trends[metric] = {
                    'direction': trend_direction,
                    'magnitude': trend_magnitude,
                    'current': values[-1],
                    'average': sum(values) / len(values),
                    'min': min(values),
                    'max': max(values)
                }
        
        return trends
    
    def get_active_alerts(self) -> List[ResourceAlert]:
        """
        Get currently active alerts.
        
        Returns:
            List of active resource alerts
        """
        with self._lock:
            return list(self._active_alerts.values())
    
    def get_alert_history(self) -> List[ResourceAlert]:
        """
        Get alert history.
        
        Returns:
            List of historical alerts
        """
        with self._lock:
            return list(self._alert_history)
    
    def add_alert_callback(self, callback: Callable[[ResourceAlert], None]) -> None:
        """
        Add a callback function to be called when alerts are generated.
        
        Args:
            callback: Function to call with ResourceAlert parameter
        """
        self._alert_callbacks.append(callback)
        logger.debug(f"Added alert callback: {callback.__name__}")
    
    def remove_alert_callback(self, callback: Callable[[ResourceAlert], None]) -> None:
        """
        Remove an alert callback.
        
        Args:
            callback: Callback function to remove
        """
        if callback in self._alert_callbacks:
            self._alert_callbacks.remove(callback)
            logger.debug(f"Removed alert callback: {callback.__name__}")
    
    def should_scale_up(self) -> bool:
        """
        Determine if the system should scale up based on resource usage.
        
        Returns:
            True if scaling up is recommended
        """
        current_stats = self.get_current_stats()
        
        # Scale up if any critical threshold is exceeded
        scale_up_conditions = [
            current_stats.cpu_percent > self.thresholds.cpu_critical,
            current_stats.memory_percent > self.thresholds.memory_critical,
            current_stats.active_connections > self.thresholds.connections_critical
        ]
        
        return any(scale_up_conditions)
    
    def should_scale_down(self) -> bool:
        """
        Determine if the system can scale down based on resource usage.
        
        Returns:
            True if scaling down is safe
        """
        # Get recent stats to ensure consistent low usage
        recent_stats = self.get_historical_stats(minutes=10)
        
        if len(recent_stats) < 3:
            return False
        
        # Check if all recent measurements are below scale-down thresholds
        scale_down_safe = all(
            stats.cpu_percent < 30.0 and
            stats.memory_percent < 40.0 and
            stats.active_connections < 200
            for stats in recent_stats[-3:]
        )
        
        return scale_down_safe
    
    def get_monitoring_statistics(self) -> Dict[str, Any]:
        """
        Get monitoring system statistics.
        
        Returns:
            Dictionary with monitoring statistics
        """
        with self._lock:
            uptime = datetime.now() - self.start_time
            
            return {
                'uptime_seconds': uptime.total_seconds(),
                'monitoring_cycles': self.monitoring_cycles,
                'alerts_generated': self.alerts_generated,
                'active_alerts': len(self._active_alerts),
                'history_size': len(self._resource_history),
                'max_history_size': self.history_size,
                'monitoring_interval': self.monitoring_interval,
                'alert_callbacks': len(self._alert_callbacks)
            }
    
    def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        while not self._shutdown_event.is_set():
            try:
                # Collect resource statistics
                stats = self._collect_resource_stats()
                
                # Store in history
                with self._lock:
                    self._resource_history.append(stats)
                
                # Check for alerts
                if self.enable_alerts:
                    self._check_alerts(stats)
                
                self.monitoring_cycles += 1
                
                # Wait for next cycle
                self._shutdown_event.wait(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Resource monitoring error: {e}")
                self._shutdown_event.wait(self.monitoring_interval)
    
    def _collect_resource_stats(self) -> ResourceStats:
        """Collect current resource statistics."""
        timestamp = datetime.now()
        
        if HAS_PSUTIL:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_mb = memory.used / (1024 * 1024)
            memory_available_mb = memory.available / (1024 * 1024)
            
            # Disk usage (root filesystem)
            disk = psutil.disk_usage('/')
            disk_usage_percent = (disk.used / disk.total) * 100
            
            # Network statistics
            network = psutil.net_io_counters()
            network_bytes_sent = network.bytes_sent
            network_bytes_recv = network.bytes_recv
            
            # Active connections
            try:
                connections = psutil.net_connections()
                active_connections = len([c for c in connections if c.status == 'ESTABLISHED'])
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                active_connections = 0
            
            # Load average (Unix-like systems)
            try:
                load_average = list(os.getloadavg())
            except (OSError, AttributeError):
                load_average = [0.0, 0.0, 0.0]
                
        else:
            # Fallback values when psutil is not available
            cpu_percent = 50.0
            memory_percent = 60.0
            memory_used_mb = 2048.0
            memory_available_mb = 2048.0
            disk_usage_percent = 50.0
            network_bytes_sent = 0
            network_bytes_recv = 0
            active_connections = 0
            load_average = [0.0, 0.0, 0.0]
        
        return ResourceStats(
            timestamp=timestamp,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_mb=memory_used_mb,
            memory_available_mb=memory_available_mb,
            disk_usage_percent=disk_usage_percent,
            network_bytes_sent=network_bytes_sent,
            network_bytes_recv=network_bytes_recv,
            active_connections=active_connections,
            load_average=load_average
        )
    
    def _check_alerts(self, stats: ResourceStats) -> None:
        """Check resource statistics against thresholds and generate alerts."""
        alerts_to_check = [
            ('cpu', stats.cpu_percent, self.thresholds.cpu_warning, self.thresholds.cpu_critical),
            ('memory', stats.memory_percent, self.thresholds.memory_warning, self.thresholds.memory_critical),
            ('disk', stats.disk_usage_percent, self.thresholds.disk_warning, self.thresholds.disk_critical),
            ('connections', stats.active_connections, self.thresholds.connections_warning, self.thresholds.connections_critical)
        ]
        
        for resource, current_value, warning_threshold, critical_threshold in alerts_to_check:
            # Check for critical alert
            if current_value >= critical_threshold:
                self._generate_alert(
                    'threshold_exceeded',
                    resource,
                    'critical',
                    current_value,
                    critical_threshold,
                    f"{resource.upper()} usage is critical: {current_value:.1f}% (threshold: {critical_threshold:.1f}%)"
                )
            # Check for warning alert
            elif current_value >= warning_threshold:
                self._generate_alert(
                    'threshold_exceeded',
                    resource,
                    'warning',
                    current_value,
                    warning_threshold,
                    f"{resource.upper()} usage is high: {current_value:.1f}% (threshold: {warning_threshold:.1f}%)"
                )
            else:
                # Clear any existing alerts for this resource
                self._clear_alert(resource)
    
    def _generate_alert(
        self,
        alert_type: str,
        resource: str,
        level: str,
        current_value: float,
        threshold: float,
        message: str
    ) -> None:
        """Generate a resource alert."""
        alert_key = f"{resource}_{level}"
        
        with self._lock:
            # Don't generate duplicate alerts
            if alert_key in self._active_alerts:
                return
            
            alert = ResourceAlert(
                alert_type=alert_type,
                resource=resource,
                level=level,
                current_value=current_value,
                threshold=threshold,
                message=message
            )
            
            self._active_alerts[alert_key] = alert
            self._alert_history.append(alert)
            self.alerts_generated += 1
            
            logger.warning(f"Resource alert generated: {message}")
            
            # Call alert callbacks
            for callback in self._alert_callbacks:
                try:
                    callback(alert)
                except Exception as e:
                    logger.error(f"Error in alert callback {callback.__name__}: {e}")
    
    def _clear_alert(self, resource: str) -> None:
        """Clear alerts for a specific resource."""
        with self._lock:
            keys_to_remove = [
                key for key in self._active_alerts.keys()
                if key.startswith(f"{resource}_")
            ]
            
            for key in keys_to_remove:
                alert = self._active_alerts.pop(key)
                logger.info(f"Resource alert cleared: {alert.message}")
    
    def __enter__(self) -> 'ResourceMonitor':
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop()