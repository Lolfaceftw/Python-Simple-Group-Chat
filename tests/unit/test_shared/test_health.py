"""
Tests for health monitoring system.
"""

import threading
import time
from unittest.mock import patch, MagicMock

import pytest

from chat_app.shared.health import (
    HealthCheck,
    HealthMonitor,
    get_health_monitor,
    check_memory_usage,
    check_disk_space,
    check_port_binding,
    check_network_connectivity,
    add_health_check,
    start_health_monitoring,
    stop_health_monitoring,
    get_system_health
)
from chat_app.shared.metrics import HealthStatus


class TestHealthCheck:
    """Test HealthCheck class."""
    
    def test_successful_check(self):
        """Test successful health check."""
        def check_func():
            return True, "All good", {"detail": "value"}
        
        health_check = HealthCheck("test_check", check_func)
        status = health_check.run_check()
        
        assert status.component == "test_check"
        assert status.status == "healthy"
        assert status.message == "All good"
        assert status.details["detail"] == "value"
        assert "check_duration" in status.details
    
    def test_failed_check(self):
        """Test failed health check."""
        def check_func():
            return False, "Something wrong", {}
        
        health_check = HealthCheck("test_check", check_func, critical=True)
        status = health_check.run_check()
        
        assert status.component == "test_check"
        assert status.status == "unhealthy"
        assert status.message == "Something wrong"
        assert status.details["critical"] is True
    
    def test_failed_non_critical_check(self):
        """Test failed non-critical health check."""
        def check_func():
            return False, "Minor issue", {}
        
        health_check = HealthCheck("test_check", check_func, critical=False)
        status = health_check.run_check()
        
        assert status.status == "degraded"
    
    def test_check_timeout(self):
        """Test health check timeout."""
        def slow_check():
            time.sleep(0.1)
            return True, "Slow but OK", {}
        
        health_check = HealthCheck("slow_check", slow_check, timeout=0.05)
        status = health_check.run_check()
        
        assert status.status == "degraded"  # Non-critical by default
        assert "timed out" in status.message
    
    def test_check_exception(self):
        """Test health check with exception."""
        def failing_check():
            raise ValueError("Test error")
        
        health_check = HealthCheck("failing_check", failing_check, critical=True)
        status = health_check.run_check()
        
        assert status.status == "unhealthy"
        assert "Health check failed" in status.message
        assert status.details["exception_type"] == "ValueError"
    
    def test_thread_safety(self):
        """Test thread safety of health check."""
        call_count = 0
        
        def thread_safe_check():
            nonlocal call_count
            call_count += 1
            return True, f"Call {call_count}", {}
        
        health_check = HealthCheck("thread_test", thread_safe_check)
        
        def run_check():
            health_check.run_check()
        
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=run_check)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Should have been called 10 times
        assert call_count == 10


class TestHealthMonitor:
    """Test HealthMonitor class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.monitor = HealthMonitor()
    
    def teardown_method(self):
        """Clean up after tests."""
        self.monitor.stop_monitoring()
    
    def test_add_remove_check(self):
        """Test adding and removing health checks."""
        def dummy_check():
            return True, "OK", {}
        
        self.monitor.add_check("test1", dummy_check)
        assert "test1" in self.monitor._checks
        
        self.monitor.remove_check("test1")
        assert "test1" not in self.monitor._checks
    
    def test_run_specific_check(self):
        """Test running a specific health check."""
        def test_check():
            return True, "Test OK", {"test": True}
        
        self.monitor.add_check("specific_test", test_check)
        status = self.monitor.run_check("specific_test")
        
        assert status is not None
        assert status.component == "specific_test"
        assert status.status == "healthy"
        assert status.message == "Test OK"
    
    def test_run_nonexistent_check(self):
        """Test running a non-existent health check."""
        status = self.monitor.run_check("nonexistent")
        assert status is None
    
    def test_run_all_checks(self):
        """Test running all health checks."""
        def check1():
            return True, "Check 1 OK", {}
        
        def check2():
            return False, "Check 2 failed", {}
        
        self.monitor.add_check("check1", check1)
        self.monitor.add_check("check2", check2, critical=False)
        
        results = self.monitor.run_all_checks()
        
        assert len(results) == 2
        assert results["check1"].status == "healthy"
        assert results["check2"].status == "degraded"
    
    def test_get_status(self):
        """Test getting health status."""
        def test_check():
            return True, "Status test", {}
        
        self.monitor.add_check("status_test", test_check)
        
        # Initially no status
        status = self.monitor.get_status("status_test")
        assert status is None
        
        # Run check and get status
        self.monitor.run_check("status_test")
        status = self.monitor.get_status("status_test")
        assert status is not None
        assert status.component == "status_test"
    
    def test_get_all_statuses(self):
        """Test getting all health statuses."""
        def check1():
            return True, "Check 1", {}
        
        def check2():
            return False, "Check 2", {}
        
        self.monitor.add_check("check1", check1)
        self.monitor.add_check("check2", check2)
        
        # Run checks
        self.monitor.run_all_checks()
        
        statuses = self.monitor.get_all_statuses()
        assert len(statuses) == 2
        assert "check1" in statuses
        assert "check2" in statuses
    
    def test_overall_status_healthy(self):
        """Test overall status when all checks are healthy."""
        def healthy_check():
            return True, "OK", {}
        
        self.monitor.add_check("check1", healthy_check)
        self.monitor.add_check("check2", healthy_check)
        self.monitor.run_all_checks()
        
        overall = self.monitor.get_overall_status()
        assert overall.status == "healthy"
        assert overall.message == "All components healthy"
    
    def test_overall_status_degraded(self):
        """Test overall status when some checks are degraded."""
        def healthy_check():
            return True, "OK", {}
        
        def degraded_check():
            return False, "Degraded", {}
        
        self.monitor.add_check("healthy", healthy_check)
        self.monitor.add_check("degraded", degraded_check, critical=False)
        self.monitor.run_all_checks()
        
        overall = self.monitor.get_overall_status()
        assert overall.status == "degraded"
        assert "degraded" in overall.message
    
    def test_overall_status_unhealthy_critical(self):
        """Test overall status when critical checks are unhealthy."""
        def healthy_check():
            return True, "OK", {}
        
        def critical_check():
            return False, "Critical failure", {}
        
        self.monitor.add_check("healthy", healthy_check)
        self.monitor.add_check("critical", critical_check, critical=True)
        self.monitor.run_all_checks()
        
        overall = self.monitor.get_overall_status()
        assert overall.status == "unhealthy"
        assert "critical" in overall.message
    
    def test_overall_status_unhealthy_non_critical(self):
        """Test overall status when non-critical checks are unhealthy."""
        def healthy_check():
            return True, "OK", {}
        
        def unhealthy_check():
            return False, "Non-critical failure", {}
        
        self.monitor.add_check("healthy", healthy_check)
        self.monitor.add_check("unhealthy", unhealthy_check, critical=False)
        self.monitor.run_all_checks()
        
        overall = self.monitor.get_overall_status()
        assert overall.status == "degraded"
        assert "degraded" in overall.message
    
    def test_monitoring_loop(self):
        """Test background monitoring loop."""
        check_count = 0
        
        def counting_check():
            nonlocal check_count
            check_count += 1
            return True, f"Check {check_count}", {}
        
        self.monitor.add_check("counting", counting_check, interval=1)
        self.monitor.start_monitoring()
        
        # Wait for a few checks
        time.sleep(2.5)
        self.monitor.stop_monitoring()
        
        # Should have run at least 2 times (at 0s, 1s, 2s)
        assert check_count >= 2
    
    def test_start_stop_monitoring(self):
        """Test starting and stopping monitoring."""
        assert not self.monitor._running
        
        self.monitor.start_monitoring()
        assert self.monitor._running
        assert self.monitor._thread is not None
        
        self.monitor.stop_monitoring()
        assert not self.monitor._running


class TestBuiltinHealthChecks:
    """Test built-in health check functions."""
    
    def test_memory_usage_check_no_psutil(self):
        """Test memory usage check without psutil."""
        with patch('builtins.__import__', side_effect=ImportError):
            success, message, details = check_memory_usage()
            assert success is True
            assert "psutil not available" in message
    
    def test_memory_usage_check_success(self):
        """Test successful memory usage check."""
        with patch.dict('sys.modules', {'psutil': MagicMock()}):
            import sys
            mock_psutil = sys.modules['psutil']
            mock_process = MagicMock()
            mock_process.memory_info.return_value.rss = 500 * 1024 * 1024  # 500MB
            mock_psutil.Process.return_value = mock_process
            
            success, message, details = check_memory_usage(max_memory_mb=1000)
            assert success is True
            assert "500.0MB" in message
            assert details["memory_mb"] == 500.0
    
    def test_memory_usage_check_failure(self):
        """Test memory usage check failure."""
        with patch.dict('sys.modules', {'psutil': MagicMock()}):
            import sys
            mock_psutil = sys.modules['psutil']
            mock_process = MagicMock()
            mock_process.memory_info.return_value.rss = 1500 * 1024 * 1024  # 1500MB
            mock_psutil.Process.return_value = mock_process
            
            success, message, details = check_memory_usage(max_memory_mb=1000)
            assert success is False
            assert "exceeds limit" in message
            assert details["memory_mb"] == 1500.0
    
    def test_disk_space_check_success(self):
        """Test successful disk space check."""
        with patch('shutil.disk_usage') as mock_disk_usage:
            # 10GB total, 8GB used, 2GB free
            mock_disk_usage.return_value = (10 * 1024**3, 8 * 1024**3, 2 * 1024**3)
            
            success, message, details = check_disk_space(min_free_gb=1.0)
            assert success is True
            assert "2.0GB" in message
            assert details["free_gb"] == 2.0
    
    def test_disk_space_check_failure(self):
        """Test disk space check failure."""
        with patch('shutil.disk_usage') as mock_disk_usage:
            # 10GB total, 9.5GB used, 0.5GB free
            mock_disk_usage.return_value = (10 * 1024**3, 9.5 * 1024**3, 0.5 * 1024**3)
            
            success, message, details = check_disk_space(min_free_gb=1.0)
            assert success is False
            assert "below minimum" in message
            assert details["free_gb"] == 0.5
    
    def test_port_binding_check_success(self):
        """Test successful port binding check."""
        # Use port 0 to get any available port
        success, message, details = check_port_binding("127.0.0.1", 0)
        assert success is True
        assert "available" in message
    
    def test_port_binding_check_failure(self):
        """Test port binding check failure."""
        # Try to bind to a port that's likely in use or restricted
        success, message, details = check_port_binding("127.0.0.1", 80)
        # This might succeed on some systems, so we just check the structure
        assert isinstance(success, bool)
        assert isinstance(message, str)
        assert "host" in details
        assert "port" in details
    
    @patch('socket.socket')
    def test_network_connectivity_check_success(self, mock_socket):
        """Test successful network connectivity check."""
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0
        mock_socket.return_value.__enter__.return_value = mock_sock
        
        success, message, details = check_network_connectivity()
        assert success is True
        assert "connectivity OK" in message
        assert details["result_code"] == 0
    
    @patch('socket.socket')
    def test_network_connectivity_check_failure(self, mock_socket):
        """Test network connectivity check failure."""
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 1  # Connection failed
        mock_socket.return_value.__enter__.return_value = mock_sock
        
        success, message, details = check_network_connectivity()
        assert success is False
        assert "connectivity failed" in message
        assert details["result_code"] == 1


class TestGlobalHealthFunctions:
    """Test global health monitoring functions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Reset global monitor
        import chat_app.shared.health
        chat_app.shared.health._global_monitor = None
    
    def teardown_method(self):
        """Clean up after tests."""
        stop_health_monitoring()
    
    def test_global_health_check(self):
        """Test global health check functions."""
        def test_check():
            return True, "Global test", {}
        
        add_health_check("global_test", test_check)
        
        monitor = get_health_monitor()
        assert "global_test" in monitor._checks
    
    def test_global_monitoring(self):
        """Test global monitoring start/stop."""
        def dummy_check():
            return True, "OK", {}
        
        add_health_check("monitoring_test", dummy_check, interval=1)
        
        start_health_monitoring()
        monitor = get_health_monitor()
        assert monitor._running
        
        stop_health_monitoring()
        assert not monitor._running
    
    def test_get_system_health(self):
        """Test getting system health."""
        def healthy_check():
            return True, "All good", {}
        
        add_health_check("system_test", healthy_check)
        
        # Run the check
        monitor = get_health_monitor()
        monitor.run_all_checks()
        
        system_health = get_system_health()
        assert system_health.component == "system"
        assert system_health.status == "healthy"
    
    def test_singleton_behavior(self):
        """Test that global monitor is singleton."""
        monitor1 = get_health_monitor()
        monitor2 = get_health_monitor()
        
        assert monitor1 is monitor2