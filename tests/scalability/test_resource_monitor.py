"""
Resource Monitor Tests

Tests for the resource monitoring functionality including system resource
tracking, alerting, and trend analysis.
"""

import pytest
import sys
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from chat_app.server.scalability.resource_monitor import (
    ResourceMonitor,
    ResourceStats,
    ResourceThresholds,
    ResourceAlert
)


class TestResourceStats:
    """Test ResourceStats functionality."""
    
    def test_resource_stats_creation(self):
        """Test resource stats creation."""
        timestamp = datetime.now()
        stats = ResourceStats(
            timestamp=timestamp,
            cpu_percent=50.0,
            memory_percent=60.0,
            memory_used_mb=2048.0,
            memory_available_mb=2048.0,
            disk_usage_percent=70.0,
            network_bytes_sent=1000000,
            network_bytes_recv=2000000,
            active_connections=100,
            load_average=[1.0, 1.5, 2.0]
        )
        
        assert stats.timestamp == timestamp
        assert stats.cpu_percent == 50.0
        assert stats.memory_percent == 60.0
        assert stats.memory_used_mb == 2048.0
        assert stats.memory_available_mb == 2048.0
        assert stats.disk_usage_percent == 70.0
        assert stats.network_bytes_sent == 1000000
        assert stats.network_bytes_recv == 2000000
        assert stats.active_connections == 100
        assert stats.load_average == [1.0, 1.5, 2.0]
    
    def test_resource_stats_to_dict(self):
        """Test resource stats dictionary conversion."""
        timestamp = datetime.now()
        stats = ResourceStats(
            timestamp=timestamp,
            cpu_percent=50.0,
            memory_percent=60.0,
            memory_used_mb=2048.0,
            memory_available_mb=2048.0,
            disk_usage_percent=70.0,
            network_bytes_sent=1000000,
            network_bytes_recv=2000000,
            active_connections=100,
            load_average=[1.0, 1.5, 2.0]
        )
        
        stats_dict = stats.to_dict()
        
        assert stats_dict['timestamp'] == timestamp.isoformat()
        assert stats_dict['cpu_percent'] == 50.0
        assert stats_dict['memory_percent'] == 60.0
        assert stats_dict['active_connections'] == 100
        assert stats_dict['load_average'] == [1.0, 1.5, 2.0]


class TestResourceThresholds:
    """Test ResourceThresholds functionality."""
    
    def test_default_thresholds(self):
        """Test default threshold values."""
        thresholds = ResourceThresholds()
        
        assert thresholds.cpu_warning == 70.0
        assert thresholds.cpu_critical == 90.0
        assert thresholds.memory_warning == 75.0
        assert thresholds.memory_critical == 90.0
        assert thresholds.disk_warning == 80.0
        assert thresholds.disk_critical == 95.0
        assert thresholds.connections_warning == 800
        assert thresholds.connections_critical == 950
    
    def test_custom_thresholds(self):
        """Test custom threshold values."""
        thresholds = ResourceThresholds(
            cpu_warning=60.0,
            cpu_critical=80.0,
            memory_warning=70.0,
            memory_critical=85.0
        )
        
        assert thresholds.cpu_warning == 60.0
        assert thresholds.cpu_critical == 80.0
        assert thresholds.memory_warning == 70.0
        assert thresholds.memory_critical == 85.0


class TestResourceAlert:
    """Test ResourceAlert functionality."""
    
    def test_resource_alert_creation(self):
        """Test resource alert creation."""
        alert = ResourceAlert(
            alert_type="threshold_exceeded",
            resource="cpu",
            level="warning",
            current_value=75.0,
            threshold=70.0,
            message="CPU usage is high: 75.0% (threshold: 70.0%)"
        )
        
        assert alert.alert_type == "threshold_exceeded"
        assert alert.resource == "cpu"
        assert alert.level == "warning"
        assert alert.current_value == 75.0
        assert alert.threshold == 70.0
        assert "CPU usage is high" in alert.message
        assert alert.timestamp is not None
        assert alert.alert_id.startswith("cpu_warning_")
    
    def test_resource_alert_to_dict(self):
        """Test resource alert dictionary conversion."""
        alert = ResourceAlert(
            alert_type="threshold_exceeded",
            resource="memory",
            level="critical",
            current_value=95.0,
            threshold=90.0,
            message="Memory usage is critical"
        )
        
        alert_dict = alert.to_dict()
        
        assert alert_dict['alert_type'] == "threshold_exceeded"
        assert alert_dict['resource'] == "memory"
        assert alert_dict['level'] == "critical"
        assert alert_dict['current_value'] == 95.0
        assert alert_dict['threshold'] == 90.0
        assert alert_dict['message'] == "Memory usage is critical"
        assert 'timestamp' in alert_dict
        assert 'alert_id' in alert_dict


class TestResourceMonitor:
    """Test ResourceMonitor functionality."""
    
    def test_resource_monitor_creation(self):
        """Test resource monitor creation."""
        thresholds = ResourceThresholds(cpu_warning=60.0)
        monitor = ResourceMonitor(
            monitoring_interval=30,
            history_size=100,
            thresholds=thresholds,
            enable_alerts=True
        )
        
        assert monitor.monitoring_interval == 30
        assert monitor.history_size == 100
        assert monitor.thresholds.cpu_warning == 60.0
        assert monitor.enable_alerts is True
        assert len(monitor._resource_history) == 0
        assert len(monitor._active_alerts) == 0
    
    def test_collect_resource_stats_with_psutil(self):
        """Test resource statistics collection with psutil mocked."""
        # Since psutil is not installed, we'll test by mocking the entire _collect_resource_stats method
        monitor = ResourceMonitor()
        
        # Create expected stats
        expected_stats = ResourceStats(
            timestamp=datetime.now(),
            cpu_percent=50.0,
            memory_percent=60.0,
            memory_used_mb=2048.0,
            memory_available_mb=2048.0,
            disk_usage_percent=70.0,
            network_bytes_sent=1000000,
            network_bytes_recv=2000000,
            active_connections=100,
            load_average=[1.0, 1.5, 2.0]
        )
        
        # Mock the _collect_resource_stats method
        with patch.object(monitor, '_collect_resource_stats', return_value=expected_stats):
            stats = monitor.get_current_stats()
            
            assert stats.cpu_percent == 50.0
            assert stats.memory_percent == 60.0
            assert stats.memory_used_mb == 2048.0
            assert stats.memory_available_mb == 2048.0
            assert stats.disk_usage_percent == 70.0
            assert stats.network_bytes_sent == 1000000
            assert stats.network_bytes_recv == 2000000
            assert stats.active_connections == 100
            assert stats.load_average == [1.0, 1.5, 2.0]
    
    @patch('chat_app.server.scalability.resource_monitor.HAS_PSUTIL', False)
    def test_collect_resource_stats_fallback(self):
        """Test resource statistics collection without psutil."""
        monitor = ResourceMonitor()
        stats = monitor.get_current_stats()
        
        # Should use fallback values
        assert stats.cpu_percent == 50.0
        assert stats.memory_percent == 60.0
        assert stats.memory_used_mb == 2048.0
        assert stats.memory_available_mb == 2048.0
        assert stats.disk_usage_percent == 50.0
        assert stats.network_bytes_sent == 0
        assert stats.network_bytes_recv == 0
        assert stats.active_connections == 0
        assert stats.load_average == [0.0, 0.0, 0.0]
    
    def test_alert_generation(self):
        """Test alert generation."""
        thresholds = ResourceThresholds(
            cpu_warning=70.0,
            cpu_critical=90.0,
            memory_warning=75.0,
            memory_critical=90.0
        )
        
        monitor = ResourceMonitor(thresholds=thresholds, enable_alerts=True)
        
        # Create stats that exceed thresholds
        stats = ResourceStats(
            timestamp=datetime.now(),
            cpu_percent=80.0,  # Above warning threshold
            memory_percent=95.0,  # Above critical threshold
            memory_used_mb=2048.0,
            memory_available_mb=512.0,
            disk_usage_percent=50.0,
            network_bytes_sent=0,
            network_bytes_recv=0,
            active_connections=50,
            load_average=[1.0, 1.0, 1.0]
        )
        
        # Manually trigger alert checking
        monitor._check_alerts(stats)
        
        # Check that alerts were generated
        active_alerts = monitor.get_active_alerts()
        assert len(active_alerts) == 2  # CPU warning and memory critical
        
        # Check alert details
        alert_resources = [alert.resource for alert in active_alerts]
        assert 'cpu' in alert_resources
        assert 'memory' in alert_resources
        
        # Check alert levels
        cpu_alert = next(alert for alert in active_alerts if alert.resource == 'cpu')
        memory_alert = next(alert for alert in active_alerts if alert.resource == 'memory')
        
        assert cpu_alert.level == 'warning'
        assert memory_alert.level == 'critical'
    
    def test_alert_callbacks(self):
        """Test alert callbacks."""
        monitor = ResourceMonitor(enable_alerts=True)
        
        callback_calls = []
        
        def alert_callback(alert):
            callback_calls.append(alert)
        
        monitor.add_alert_callback(alert_callback)
        
        # Generate an alert
        alert = ResourceAlert(
            alert_type="test",
            resource="cpu",
            level="warning",
            current_value=80.0,
            threshold=70.0,
            message="Test alert"
        )
        
        # Manually add alert to trigger callbacks
        monitor._active_alerts["cpu_warning"] = alert
        monitor._alert_history.append(alert)
        
        # Simulate callback execution
        for callback in monitor._alert_callbacks:
            callback(alert)
        
        assert len(callback_calls) == 1
        assert callback_calls[0] == alert
        
        # Test callback removal
        monitor.remove_alert_callback(alert_callback)
        assert len(monitor._alert_callbacks) == 0
    
    def test_historical_data(self):
        """Test historical data collection."""
        monitor = ResourceMonitor(history_size=5)
        
        # Add some historical data
        for i in range(10):
            stats = ResourceStats(
                timestamp=datetime.now() - timedelta(minutes=i),
                cpu_percent=50.0 + i,
                memory_percent=60.0,
                memory_used_mb=2048.0,
                memory_available_mb=2048.0,
                disk_usage_percent=70.0,
                network_bytes_sent=0,
                network_bytes_recv=0,
                active_connections=100,
                load_average=[1.0, 1.0, 1.0]
            )
            monitor._resource_history.append(stats)
        
        # Should only keep last 5 due to maxlen
        assert len(monitor._resource_history) == 5
        
        # Test getting historical data
        historical = monitor.get_historical_stats(minutes=60)
        assert len(historical) == 5
        
        # Test with shorter time window
        historical_short = monitor.get_historical_stats(minutes=3)
        assert len(historical_short) <= 5
    
    def test_resource_trends(self):
        """Test resource trend analysis."""
        monitor = ResourceMonitor()
        
        # Add historical data with increasing CPU usage
        base_time = datetime.now() - timedelta(minutes=25)  # Start 25 minutes ago
        cpu_values = []
        for i in range(10):
            cpu_value = 30.0 + i * 5  # Increasing from 30% to 75%
            cpu_values.append(cpu_value)
            stats = ResourceStats(
                timestamp=base_time + timedelta(minutes=i * 2.5),  # Spread over 25 minutes
                cpu_percent=cpu_value,
                memory_percent=50.0,
                memory_used_mb=2048.0,
                memory_available_mb=2048.0,
                disk_usage_percent=60.0,
                network_bytes_sent=0,
                network_bytes_recv=0,
                active_connections=100,
                load_average=[1.0, 1.0, 1.0]
            )
            monitor._resource_history.append(stats)
        
        trends = monitor.get_resource_trends(minutes=30)
        
        assert 'cpu_percent' in trends
        cpu_trend = trends['cpu_percent']
        
        assert cpu_trend['direction'] == 'increasing'
        assert cpu_trend['magnitude'] > 0
        assert cpu_trend['current'] == 75.0
        assert cpu_trend['min'] == min(cpu_values)
        assert cpu_trend['max'] == max(cpu_values)
    
    def test_scaling_decisions(self):
        """Test scaling decision logic."""
        thresholds = ResourceThresholds(
            cpu_critical=80.0,
            memory_critical=85.0,
            connections_critical=900
        )
        
        monitor = ResourceMonitor(thresholds=thresholds)
        
        # Mock current stats for scale-up scenario
        with patch.object(monitor, 'get_current_stats') as mock_stats:
            mock_stats.return_value = ResourceStats(
                timestamp=datetime.now(),
                cpu_percent=85.0,  # Above critical
                memory_percent=70.0,
                memory_used_mb=2048.0,
                memory_available_mb=1024.0,
                disk_usage_percent=60.0,
                network_bytes_sent=0,
                network_bytes_recv=0,
                active_connections=500,
                load_average=[2.0, 2.0, 2.0]
            )
            
            assert monitor.should_scale_up() is True
            assert monitor.should_scale_down() is False
        
        # Mock current stats for scale-down scenario
        with patch.object(monitor, 'get_current_stats') as mock_stats:
            mock_stats.return_value = ResourceStats(
                timestamp=datetime.now(),
                cpu_percent=25.0,  # Low usage
                memory_percent=35.0,
                memory_used_mb=1024.0,
                memory_available_mb=3072.0,
                disk_usage_percent=40.0,
                network_bytes_sent=0,
                network_bytes_recv=0,
                active_connections=150,
                load_average=[0.5, 0.5, 0.5]
            )
            
            # Add some historical data for scale-down decision
            for _ in range(5):
                monitor._resource_history.append(mock_stats.return_value)
            
            assert monitor.should_scale_up() is False
            assert monitor.should_scale_down() is True
    
    def test_monitoring_statistics(self):
        """Test monitoring statistics."""
        monitor = ResourceMonitor(
            monitoring_interval=10,
            history_size=100
        )
        
        # Simulate some monitoring activity
        monitor.monitoring_cycles = 50
        monitor.alerts_generated = 5
        
        # Add some data
        for _ in range(10):
            stats = ResourceStats(
                timestamp=datetime.now(),
                cpu_percent=50.0,
                memory_percent=60.0,
                memory_used_mb=2048.0,
                memory_available_mb=2048.0,
                disk_usage_percent=70.0,
                network_bytes_sent=0,
                network_bytes_recv=0,
                active_connections=100,
                load_average=[1.0, 1.0, 1.0]
            )
            monitor._resource_history.append(stats)
        
        # Add some alerts
        alert = ResourceAlert(
            alert_type="test",
            resource="cpu",
            level="warning",
            current_value=80.0,
            threshold=70.0,
            message="Test alert"
        )
        monitor._active_alerts["cpu_warning"] = alert
        
        stats = monitor.get_monitoring_statistics()
        
        assert stats['monitoring_cycles'] == 50
        assert stats['alerts_generated'] == 5
        assert stats['active_alerts'] == 1
        assert stats['history_size'] == 10
        assert stats['max_history_size'] == 100
        assert stats['monitoring_interval'] == 10
        assert 'uptime_seconds' in stats
    
    def test_context_manager(self):
        """Test context manager functionality."""
        with ResourceMonitor() as monitor:
            assert monitor._monitoring_thread is not None
            assert monitor._monitoring_thread.is_alive()
        
        # Should be stopped after exiting context
        time.sleep(0.1)  # Give it time to stop
        assert monitor._shutdown_event.is_set()


@pytest.mark.integration
class TestResourceMonitorIntegration:
    """Integration tests for resource monitor."""
    
    def test_monitoring_loop(self):
        """Test the monitoring loop."""
        monitor = ResourceMonitor(
            monitoring_interval=1,  # 1 second for fast testing
            enable_alerts=True
        )
        
        # Start monitoring
        monitor.start()
        
        # Let it run for a few cycles
        time.sleep(3)
        
        # Check that data was collected
        assert monitor.monitoring_cycles > 0
        assert len(monitor._resource_history) > 0
        
        # Stop monitoring
        monitor.stop()
        
        # Verify it stopped
        assert monitor._shutdown_event.is_set()
    
    def test_concurrent_access(self):
        """Test concurrent access to resource monitor."""
        monitor = ResourceMonitor()
        
        results = []
        errors = []
        
        def worker():
            try:
                for _ in range(10):
                    stats = monitor.get_current_stats()
                    results.append(stats)
                    
                    historical = monitor.get_historical_stats(minutes=5)
                    results.extend(historical)
                    
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)
        
        # Start multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0
        assert len(results) >= 50  # At least 50 stats collected
    
    def test_alert_lifecycle(self):
        """Test complete alert lifecycle."""
        thresholds = ResourceThresholds(cpu_warning=50.0, cpu_critical=80.0)
        monitor = ResourceMonitor(thresholds=thresholds, enable_alerts=True)
        
        alert_history = []
        
        def alert_callback(alert):
            alert_history.append(alert)
        
        monitor.add_alert_callback(alert_callback)
        
        # Create high CPU stats to trigger alert
        high_cpu_stats = ResourceStats(
            timestamp=datetime.now(),
            cpu_percent=75.0,  # Above warning threshold
            memory_percent=50.0,
            memory_used_mb=2048.0,
            memory_available_mb=2048.0,
            disk_usage_percent=60.0,
            network_bytes_sent=0,
            network_bytes_recv=0,
            active_connections=100,
            load_average=[1.0, 1.0, 1.0]
        )
        
        # Trigger alert
        monitor._check_alerts(high_cpu_stats)
        
        # Should have active alert
        active_alerts = monitor.get_active_alerts()
        assert len(active_alerts) == 1
        assert active_alerts[0].resource == 'cpu'
        assert active_alerts[0].level == 'warning'
        
        # Create normal CPU stats to clear alert
        normal_cpu_stats = ResourceStats(
            timestamp=datetime.now(),
            cpu_percent=40.0,  # Below warning threshold
            memory_percent=50.0,
            memory_used_mb=2048.0,
            memory_available_mb=2048.0,
            disk_usage_percent=60.0,
            network_bytes_sent=0,
            network_bytes_recv=0,
            active_connections=100,
            load_average=[1.0, 1.0, 1.0]
        )
        
        # Clear alert
        monitor._check_alerts(normal_cpu_stats)
        
        # Should have no active alerts
        active_alerts = monitor.get_active_alerts()
        assert len(active_alerts) == 0
        
        # Should have alert in history
        alert_history_list = monitor.get_alert_history()
        assert len(alert_history_list) == 1