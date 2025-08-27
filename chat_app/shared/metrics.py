"""
Metrics Collection and Monitoring

Provides performance metrics collection and health monitoring capabilities.
"""

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from .exceptions import ChatAppError


logger = logging.getLogger(__name__)


@dataclass
class MetricValue:
    """Represents a single metric value with timestamp."""
    
    value: Union[int, float]
    timestamp: datetime = field(default_factory=datetime.now)
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class HealthStatus:
    """Represents the health status of a component."""
    
    component: str
    status: str  # "healthy", "degraded", "unhealthy"
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    details: Dict[str, Any] = field(default_factory=dict)


class MetricsCollector:
    """Thread-safe metrics collector for performance monitoring."""
    
    def __init__(self, max_history: int = 1000):
        """
        Initialize metrics collector.
        
        Args:
            max_history: Maximum number of metric values to keep in history.
        """
        self._lock = threading.RLock()
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, Union[int, float]] = {}
        self._histograms: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self._timers: Dict[str, List[float]] = defaultdict(list)
        self._health_checks: Dict[str, HealthStatus] = {}
        self._max_history = max_history
        self._start_time = datetime.now()
    
    def increment_counter(self, name: str, value: int = 1, labels: Optional[Dict[str, str]] = None) -> None:
        """
        Increment a counter metric.
        
        Args:
            name: Counter name.
            value: Value to increment by.
            labels: Optional labels for the metric.
        """
        with self._lock:
            key = self._make_key(name, labels)
            self._counters[key] += value
            logger.debug(f"Counter {key} incremented by {value}, total: {self._counters[key]}")
    
    def set_gauge(self, name: str, value: Union[int, float], labels: Optional[Dict[str, str]] = None) -> None:
        """
        Set a gauge metric value.
        
        Args:
            name: Gauge name.
            value: Gauge value.
            labels: Optional labels for the metric.
        """
        with self._lock:
            key = self._make_key(name, labels)
            self._gauges[key] = value
            logger.debug(f"Gauge {key} set to {value}")
    
    def record_histogram(self, name: str, value: Union[int, float], labels: Optional[Dict[str, str]] = None) -> None:
        """
        Record a value in a histogram metric.
        
        Args:
            name: Histogram name.
            value: Value to record.
            labels: Optional labels for the metric.
        """
        with self._lock:
            key = self._make_key(name, labels)
            self._histograms[key].append(MetricValue(value, labels=labels or {}))
            logger.debug(f"Histogram {key} recorded value {value}")
    
    def start_timer(self, name: str, labels: Optional[Dict[str, str]] = None) -> 'Timer':
        """
        Start a timer for measuring duration.
        
        Args:
            name: Timer name.
            labels: Optional labels for the metric.
            
        Returns:
            Timer context manager.
        """
        return Timer(self, name, labels)
    
    def record_timer(self, name: str, duration: float, labels: Optional[Dict[str, str]] = None) -> None:
        """
        Record a timer duration.
        
        Args:
            name: Timer name.
            duration: Duration in seconds.
            labels: Optional labels for the metric.
        """
        with self._lock:
            key = self._make_key(name, labels)
            self._timers[key].append(duration)
            # Keep only recent values
            if len(self._timers[key]) > self._max_history:
                self._timers[key] = self._timers[key][-self._max_history:]
            logger.debug(f"Timer {key} recorded duration {duration:.3f}s")
    
    def update_health(self, component: str, status: str, message: str = "", details: Optional[Dict[str, Any]] = None) -> None:
        """
        Update health status for a component.
        
        Args:
            component: Component name.
            status: Health status ("healthy", "degraded", "unhealthy").
            message: Optional status message.
            details: Optional additional details.
        """
        with self._lock:
            self._health_checks[component] = HealthStatus(
                component=component,
                status=status,
                message=message,
                details=details or {}
            )
            logger.info(f"Health status updated for {component}: {status} - {message}")
    
    def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> int:
        """Get current counter value."""
        with self._lock:
            key = self._make_key(name, labels)
            return self._counters.get(key, 0)
    
    def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[Union[int, float]]:
        """Get current gauge value."""
        with self._lock:
            key = self._make_key(name, labels)
            return self._gauges.get(key)
    
    def get_histogram_stats(self, name: str, labels: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        """Get histogram statistics."""
        with self._lock:
            key = self._make_key(name, labels)
            values = [mv.value for mv in self._histograms.get(key, [])]
            
            if not values:
                return {}
            
            values.sort()
            count = len(values)
            
            return {
                "count": count,
                "min": min(values),
                "max": max(values),
                "mean": sum(values) / count,
                "p50": values[int(count * 0.5)] if count > 0 else 0,
                "p90": values[int(count * 0.9)] if count > 0 else 0,
                "p95": values[int(count * 0.95)] if count > 0 else 0,
                "p99": values[int(count * 0.99)] if count > 0 else 0,
            }
    
    def get_timer_stats(self, name: str, labels: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        """Get timer statistics."""
        with self._lock:
            key = self._make_key(name, labels)
            values = self._timers.get(key, [])
            
            if not values:
                return {}
            
            sorted_values = sorted(values)
            count = len(sorted_values)
            
            return {
                "count": count,
                "min": min(sorted_values),
                "max": max(sorted_values),
                "mean": sum(sorted_values) / count,
                "p50": sorted_values[int(count * 0.5)] if count > 0 else 0,
                "p90": sorted_values[int(count * 0.9)] if count > 0 else 0,
                "p95": sorted_values[int(count * 0.95)] if count > 0 else 0,
                "p99": sorted_values[int(count * 0.99)] if count > 0 else 0,
            }
    
    def get_health_status(self, component: Optional[str] = None) -> Union[HealthStatus, Dict[str, HealthStatus]]:
        """
        Get health status for a component or all components.
        
        Args:
            component: Component name. If None, returns all health statuses.
            
        Returns:
            Health status or dictionary of all health statuses.
        """
        with self._lock:
            if component:
                return self._health_checks.get(component)
            return dict(self._health_checks)
    
    def get_overall_health(self) -> HealthStatus:
        """Get overall system health status."""
        with self._lock:
            if not self._health_checks:
                return HealthStatus("system", "unknown", "No health checks registered")
            
            statuses = list(self._health_checks.values())
            unhealthy = [s for s in statuses if s.status == "unhealthy"]
            degraded = [s for s in statuses if s.status == "degraded"]
            
            if unhealthy:
                return HealthStatus(
                    "system", 
                    "unhealthy", 
                    f"{len(unhealthy)} components unhealthy",
                    {"unhealthy_components": [s.component for s in unhealthy]}
                )
            elif degraded:
                return HealthStatus(
                    "system", 
                    "degraded", 
                    f"{len(degraded)} components degraded",
                    {"degraded_components": [s.component for s in degraded]}
                )
            else:
                return HealthStatus("system", "healthy", "All components healthy")
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get a summary of all metrics."""
        with self._lock:
            uptime = (datetime.now() - self._start_time).total_seconds()
            
            return {
                "uptime_seconds": uptime,
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {name: self.get_histogram_stats(name.split("|")[0], 
                                                             self._parse_labels(name)) 
                              for name in self._histograms.keys()},
                "timers": {name: self.get_timer_stats(name.split("|")[0], 
                                                     self._parse_labels(name)) 
                          for name in self._timers.keys()},
                "health": {name: {
                    "status": status.status,
                    "message": status.message,
                    "timestamp": status.timestamp.isoformat(),
                    "details": status.details
                } for name, status in self._health_checks.items()}
            }
    
    def reset_metrics(self) -> None:
        """Reset all metrics (useful for testing)."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._timers.clear()
            self._health_checks.clear()
            self._start_time = datetime.now()
            logger.info("All metrics reset")
    
    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """Create a key for storing metrics with labels."""
        if not labels:
            return name
        
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}|{label_str}"
    
    def _parse_labels(self, key: str) -> Optional[Dict[str, str]]:
        """Parse labels from a metric key."""
        if "|" not in key:
            return None
        
        _, label_str = key.split("|", 1)
        labels = {}
        for pair in label_str.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                labels[k] = v
        return labels


class Timer:
    """Context manager for timing operations."""
    
    def __init__(self, collector: MetricsCollector, name: str, labels: Optional[Dict[str, str]] = None):
        """
        Initialize timer.
        
        Args:
            collector: Metrics collector instance.
            name: Timer name.
            labels: Optional labels for the metric.
        """
        self.collector = collector
        self.name = name
        self.labels = labels
        self.start_time: Optional[float] = None
    
    def __enter__(self) -> 'Timer':
        """Start timing."""
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Stop timing and record duration."""
        if self.start_time is not None:
            duration = time.time() - self.start_time
            self.collector.record_timer(self.name, duration, self.labels)


# Global metrics collector instance
_global_collector: Optional[MetricsCollector] = None
_collector_lock = threading.Lock()


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    global _global_collector
    
    if _global_collector is None:
        with _collector_lock:
            if _global_collector is None:
                _global_collector = MetricsCollector()
    
    return _global_collector


def reset_global_collector() -> None:
    """Reset the global metrics collector (useful for testing)."""
    global _global_collector
    
    with _collector_lock:
        if _global_collector is not None:
            _global_collector.reset_metrics()


# Convenience functions for common metrics operations
def increment_counter(name: str, value: int = 1, labels: Optional[Dict[str, str]] = None) -> None:
    """Increment a counter metric."""
    get_metrics_collector().increment_counter(name, value, labels)


def set_gauge(name: str, value: Union[int, float], labels: Optional[Dict[str, str]] = None) -> None:
    """Set a gauge metric value."""
    get_metrics_collector().set_gauge(name, value, labels)


def record_histogram(name: str, value: Union[int, float], labels: Optional[Dict[str, str]] = None) -> None:
    """Record a value in a histogram metric."""
    get_metrics_collector().record_histogram(name, value, labels)


def start_timer(name: str, labels: Optional[Dict[str, str]] = None) -> Timer:
    """Start a timer for measuring duration."""
    return get_metrics_collector().start_timer(name, labels)


def update_health(component: str, status: str, message: str = "", details: Optional[Dict[str, Any]] = None) -> None:
    """Update health status for a component."""
    get_metrics_collector().update_health(component, status, message, details)


def get_health_status(component: Optional[str] = None) -> Union[HealthStatus, Dict[str, HealthStatus]]:
    """Get health status for a component or all components."""
    return get_metrics_collector().get_health_status(component)


def get_metrics_summary() -> Dict[str, Any]:
    """Get a summary of all metrics."""
    return get_metrics_collector().get_metrics_summary()