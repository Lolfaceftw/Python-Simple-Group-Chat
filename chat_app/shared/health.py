"""
Health Check System

Provides health monitoring and status reporting capabilities.
"""

import logging
import socket
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from .exceptions import ChatAppError
from .metrics import get_metrics_collector, HealthStatus


logger = logging.getLogger(__name__)


class HealthCheck:
    """Represents a single health check."""
    
    def __init__(
        self,
        name: str,
        check_func: Callable[[], Tuple[bool, str, Dict[str, Any]]],
        interval: int = 30,
        timeout: int = 5,
        critical: bool = False
    ):
        """
        Initialize health check.
        
        Args:
            name: Health check name.
            check_func: Function that returns (success, message, details).
            interval: Check interval in seconds.
            timeout: Check timeout in seconds.
            critical: Whether this check is critical for overall health.
        """
        self.name = name
        self.check_func = check_func
        self.interval = interval
        self.timeout = timeout
        self.critical = critical
        self.last_check: Optional[datetime] = None
        self.last_status: Optional[HealthStatus] = None
        self._lock = threading.Lock()
    
    def run_check(self) -> HealthStatus:
        """Run the health check and return status."""
        with self._lock:
            try:
                start_time = time.time()
                success, message, details = self.check_func()
                duration = time.time() - start_time
                
                if duration > self.timeout:
                    success = False
                    message = f"Check timed out ({duration:.2f}s > {self.timeout}s)"
                
                status = "healthy" if success else ("unhealthy" if self.critical else "degraded")
                
                self.last_status = HealthStatus(
                    component=self.name,
                    status=status,
                    message=message,
                    details={
                        **details,
                        "check_duration": duration,
                        "timeout": self.timeout,
                        "critical": self.critical
                    }
                )
                self.last_check = datetime.now()
                
                logger.debug(f"Health check {self.name}: {status} - {message}")
                return self.last_status
                
            except Exception as e:
                error_msg = f"Health check failed: {str(e)}"
                logger.error(f"Health check {self.name} failed: {e}", exc_info=True)
                
                self.last_status = HealthStatus(
                    component=self.name,
                    status="unhealthy" if self.critical else "degraded",
                    message=error_msg,
                    details={
                        "error": str(e),
                        "critical": self.critical,
                        "exception_type": type(e).__name__
                    }
                )
                self.last_check = datetime.now()
                return self.last_status


class HealthMonitor:
    """Health monitoring system."""
    
    def __init__(self):
        """Initialize health monitor."""
        self._checks: Dict[str, HealthCheck] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._metrics_collector = get_metrics_collector()
    
    def add_check(
        self,
        name: str,
        check_func: Callable[[], Tuple[bool, str, Dict[str, Any]]],
        interval: int = 30,
        timeout: int = 5,
        critical: bool = False
    ) -> None:
        """
        Add a health check.
        
        Args:
            name: Health check name.
            check_func: Function that returns (success, message, details).
            interval: Check interval in seconds.
            timeout: Check timeout in seconds.
            critical: Whether this check is critical for overall health.
        """
        with self._lock:
            self._checks[name] = HealthCheck(name, check_func, interval, timeout, critical)
            logger.info(f"Added health check: {name} (interval={interval}s, critical={critical})")
    
    def remove_check(self, name: str) -> None:
        """Remove a health check."""
        with self._lock:
            if name in self._checks:
                del self._checks[name]
                logger.info(f"Removed health check: {name}")
    
    def run_check(self, name: str) -> Optional[HealthStatus]:
        """Run a specific health check."""
        with self._lock:
            if name in self._checks:
                status = self._checks[name].run_check()
                self._metrics_collector.update_health(name, status.status, status.message, status.details)
                return status
            return None
    
    def run_all_checks(self) -> Dict[str, HealthStatus]:
        """Run all health checks."""
        results = {}
        with self._lock:
            for name, check in self._checks.items():
                try:
                    status = check.run_check()
                    results[name] = status
                    self._metrics_collector.update_health(name, status.status, status.message, status.details)
                except Exception as e:
                    logger.error(f"Failed to run health check {name}: {e}", exc_info=True)
        
        return results
    
    def get_status(self, name: Optional[str] = None) -> Optional[HealthStatus]:
        """Get health status for a specific check."""
        with self._lock:
            if name and name in self._checks:
                return self._checks[name].last_status
            return None
    
    def get_all_statuses(self) -> Dict[str, HealthStatus]:
        """Get all health statuses."""
        results = {}
        with self._lock:
            for name, check in self._checks.items():
                if check.last_status:
                    results[name] = check.last_status
        return results
    
    def get_overall_status(self) -> HealthStatus:
        """Get overall system health status."""
        statuses = self.get_all_statuses()
        
        if not statuses:
            return HealthStatus("system", "unknown", "No health checks configured")
        
        unhealthy = [s for s in statuses.values() if s.status == "unhealthy"]
        degraded = [s for s in statuses.values() if s.status == "degraded"]
        
        if unhealthy:
            critical_unhealthy = [s for s in unhealthy if s.details.get("critical", False)]
            if critical_unhealthy:
                return HealthStatus(
                    "system",
                    "unhealthy",
                    f"{len(critical_unhealthy)} critical components unhealthy",
                    {
                        "unhealthy_components": [s.component for s in unhealthy],
                        "critical_unhealthy": [s.component for s in critical_unhealthy]
                    }
                )
            else:
                return HealthStatus(
                    "system",
                    "degraded",
                    f"{len(unhealthy)} non-critical components unhealthy",
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
    
    def start_monitoring(self) -> None:
        """Start background health monitoring."""
        with self._lock:
            if self._running:
                return
            
            self._running = True
            self._thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self._thread.start()
            logger.info("Health monitoring started")
    
    def stop_monitoring(self) -> None:
        """Stop background health monitoring."""
        with self._lock:
            if not self._running:
                return
            
            self._running = False
            if self._thread:
                self._thread.join(timeout=5)
            logger.info("Health monitoring stopped")
    
    def _monitoring_loop(self) -> None:
        """Background monitoring loop."""
        last_check_times = {}
        
        while self._running:
            try:
                current_time = datetime.now()
                
                with self._lock:
                    for name, check in self._checks.items():
                        last_check = last_check_times.get(name)
                        
                        if (last_check is None or 
                            (current_time - last_check).total_seconds() >= check.interval):
                            
                            try:
                                status = check.run_check()
                                self._metrics_collector.update_health(
                                    name, status.status, status.message, status.details
                                )
                                last_check_times[name] = current_time
                            except Exception as e:
                                logger.error(f"Health check {name} failed in monitoring loop: {e}")
                
                # Sleep for a short interval before checking again
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in health monitoring loop: {e}", exc_info=True)
                time.sleep(5)  # Wait longer on error


# Global health monitor instance
_global_monitor: Optional[HealthMonitor] = None
_monitor_lock = threading.Lock()


def get_health_monitor() -> HealthMonitor:
    """Get the global health monitor instance."""
    global _global_monitor
    
    if _global_monitor is None:
        with _monitor_lock:
            if _global_monitor is None:
                _global_monitor = HealthMonitor()
    
    return _global_monitor


# Built-in health checks
def check_memory_usage(max_memory_mb: int = 1000) -> Tuple[bool, str, Dict[str, Any]]:
    """Check memory usage."""
    try:
        import psutil
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        
        success = memory_mb < max_memory_mb
        message = f"Memory usage: {memory_mb:.1f}MB"
        if not success:
            message += f" (exceeds limit of {max_memory_mb}MB)"
        
        return success, message, {
            "memory_mb": memory_mb,
            "memory_limit_mb": max_memory_mb,
            "memory_percent": (memory_mb / max_memory_mb) * 100
        }
    except ImportError:
        return True, "Memory check skipped (psutil not available)", {}
    except Exception as e:
        return False, f"Memory check failed: {e}", {"error": str(e)}


def check_disk_space(path: str = ".", min_free_gb: float = 1.0) -> Tuple[bool, str, Dict[str, Any]]:
    """Check disk space."""
    try:
        import shutil
        total, used, free = shutil.disk_usage(path)
        free_gb = free / (1024 ** 3)
        
        success = free_gb >= min_free_gb
        message = f"Free disk space: {free_gb:.1f}GB"
        if not success:
            message += f" (below minimum of {min_free_gb}GB)"
        
        return success, message, {
            "free_gb": free_gb,
            "min_free_gb": min_free_gb,
            "total_gb": total / (1024 ** 3),
            "used_gb": used / (1024 ** 3)
        }
    except Exception as e:
        return False, f"Disk space check failed: {e}", {"error": str(e)}


def check_port_binding(host: str, port: int) -> Tuple[bool, str, Dict[str, Any]]:
    """Check if a port can be bound."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            return True, f"Port {port} is available", {"host": host, "port": port}
    except OSError as e:
        return False, f"Port {port} binding failed: {e}", {"host": host, "port": port, "error": str(e)}


def check_network_connectivity(host: str = "8.8.8.8", port: int = 53, timeout: int = 3) -> Tuple[bool, str, Dict[str, Any]]:
    """Check network connectivity."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            
            success = result == 0
            message = "Network connectivity OK" if success else f"Network connectivity failed (error {result})"
            
            return success, message, {
                "target_host": host,
                "target_port": port,
                "timeout": timeout,
                "result_code": result
            }
    except Exception as e:
        return False, f"Network connectivity check failed: {e}", {"error": str(e)}


# Convenience functions
def add_health_check(
    name: str,
    check_func: Callable[[], Tuple[bool, str, Dict[str, Any]]],
    interval: int = 30,
    timeout: int = 5,
    critical: bool = False
) -> None:
    """Add a health check to the global monitor."""
    get_health_monitor().add_check(name, check_func, interval, timeout, critical)


def start_health_monitoring() -> None:
    """Start global health monitoring."""
    get_health_monitor().start_monitoring()


def stop_health_monitoring() -> None:
    """Stop global health monitoring."""
    get_health_monitor().stop_monitoring()


def get_system_health() -> HealthStatus:
    """Get overall system health status."""
    return get_health_monitor().get_overall_status()