"""
Tests for metrics collection system.
"""

import threading
import time
from unittest.mock import patch

import pytest

from chat_app.shared.metrics import (
    MetricsCollector,
    Timer,
    get_metrics_collector,
    increment_counter,
    set_gauge,
    record_histogram,
    start_timer,
    update_health,
    get_health_status,
    get_metrics_summary,
    reset_global_collector
)


class TestMetricsCollector:
    """Test MetricsCollector class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.collector = MetricsCollector()
    
    def test_increment_counter(self):
        """Test counter increment functionality."""
        self.collector.increment_counter("test_counter")
        assert self.collector.get_counter("test_counter") == 1
        
        self.collector.increment_counter("test_counter", 5)
        assert self.collector.get_counter("test_counter") == 6
    
    def test_counter_with_labels(self):
        """Test counter with labels."""
        self.collector.increment_counter("requests", labels={"method": "GET"})
        self.collector.increment_counter("requests", labels={"method": "POST"})
        self.collector.increment_counter("requests", labels={"method": "GET"})
        
        assert self.collector.get_counter("requests", {"method": "GET"}) == 2
        assert self.collector.get_counter("requests", {"method": "POST"}) == 1
    
    def test_set_gauge(self):
        """Test gauge functionality."""
        self.collector.set_gauge("temperature", 25.5)
        assert self.collector.get_gauge("temperature") == 25.5
        
        self.collector.set_gauge("temperature", 30.0)
        assert self.collector.get_gauge("temperature") == 30.0
    
    def test_gauge_with_labels(self):
        """Test gauge with labels."""
        self.collector.set_gauge("cpu_usage", 50.0, {"core": "0"})
        self.collector.set_gauge("cpu_usage", 75.0, {"core": "1"})
        
        assert self.collector.get_gauge("cpu_usage", {"core": "0"}) == 50.0
        assert self.collector.get_gauge("cpu_usage", {"core": "1"}) == 75.0
    
    def test_record_histogram(self):
        """Test histogram functionality."""
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        for value in values:
            self.collector.record_histogram("response_time", value)
        
        stats = self.collector.get_histogram_stats("response_time")
        assert stats["count"] == 10
        assert stats["min"] == 1
        assert stats["max"] == 10
        assert stats["mean"] == 5.5
        assert stats["p50"] == 6  # 50th percentile of [1,2,3,4,5,6,7,8,9,10] is 6
    
    def test_timer_context_manager(self):
        """Test timer context manager."""
        with self.collector.start_timer("operation_time"):
            time.sleep(0.01)  # Sleep for 10ms
        
        stats = self.collector.get_timer_stats("operation_time")
        assert stats["count"] == 1
        assert stats["min"] >= 0.01
        assert stats["max"] >= 0.01
    
    def test_timer_manual_recording(self):
        """Test manual timer recording."""
        self.collector.record_timer("manual_timer", 0.5)
        self.collector.record_timer("manual_timer", 1.0)
        self.collector.record_timer("manual_timer", 0.25)
        
        stats = self.collector.get_timer_stats("manual_timer")
        assert stats["count"] == 3
        assert stats["min"] == 0.25
        assert stats["max"] == 1.0
        assert abs(stats["mean"] - 0.583333333333333) < 0.0001  # (0.5 + 1.0 + 0.25) / 3
    
    def test_health_status(self):
        """Test health status functionality."""
        self.collector.update_health("database", "healthy", "Connection OK")
        self.collector.update_health("cache", "degraded", "High latency")
        
        db_health = self.collector.get_health_status("database")
        assert db_health.component == "database"
        assert db_health.status == "healthy"
        assert db_health.message == "Connection OK"
        
        all_health = self.collector.get_health_status()
        assert len(all_health) == 2
        assert "database" in all_health
        assert "cache" in all_health
    
    def test_overall_health(self):
        """Test overall health calculation."""
        # All healthy
        self.collector.update_health("service1", "healthy")
        self.collector.update_health("service2", "healthy")
        
        overall = self.collector.get_overall_health()
        assert overall.status == "healthy"
        
        # One degraded
        self.collector.update_health("service2", "degraded")
        overall = self.collector.get_overall_health()
        assert overall.status == "degraded"
        
        # One unhealthy
        self.collector.update_health("service2", "unhealthy")
        overall = self.collector.get_overall_health()
        assert overall.status == "unhealthy"
    
    def test_metrics_summary(self):
        """Test metrics summary."""
        self.collector.increment_counter("requests")
        self.collector.set_gauge("active_connections", 5)
        self.collector.record_histogram("latency", 100)
        self.collector.record_timer("processing_time", 0.5)
        self.collector.update_health("api", "healthy")
        
        summary = self.collector.get_metrics_summary()
        
        assert "uptime_seconds" in summary
        assert "counters" in summary
        assert "gauges" in summary
        assert "histograms" in summary
        assert "timers" in summary
        assert "health" in summary
        
        assert summary["counters"]["requests"] == 1
        assert summary["gauges"]["active_connections"] == 5
    
    def test_thread_safety(self):
        """Test thread safety of metrics collector."""
        def increment_worker():
            for _ in range(100):
                self.collector.increment_counter("thread_test")
        
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=increment_worker)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Should be 10 threads * 100 increments = 1000
        assert self.collector.get_counter("thread_test") == 1000
    
    def test_reset_metrics(self):
        """Test metrics reset functionality."""
        self.collector.increment_counter("test")
        self.collector.set_gauge("test_gauge", 42)
        self.collector.update_health("test_service", "healthy")
        
        assert self.collector.get_counter("test") == 1
        assert self.collector.get_gauge("test_gauge") == 42
        assert len(self.collector.get_health_status()) == 1
        
        self.collector.reset_metrics()
        
        assert self.collector.get_counter("test") == 0
        assert self.collector.get_gauge("test_gauge") is None
        assert len(self.collector.get_health_status()) == 0


class TestTimer:
    """Test Timer class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.collector = MetricsCollector()
    
    def test_timer_context_manager(self):
        """Test timer as context manager."""
        with Timer(self.collector, "test_timer"):
            time.sleep(0.01)
        
        stats = self.collector.get_timer_stats("test_timer")
        assert stats["count"] == 1
        assert stats["min"] >= 0.01
    
    def test_timer_with_labels(self):
        """Test timer with labels."""
        with Timer(self.collector, "api_call", {"endpoint": "/users"}):
            time.sleep(0.01)
        
        stats = self.collector.get_timer_stats("api_call", {"endpoint": "/users"})
        assert stats["count"] == 1


class TestGlobalFunctions:
    """Test global convenience functions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        reset_global_collector()
    
    def test_global_counter(self):
        """Test global counter functions."""
        increment_counter("global_test")
        increment_counter("global_test", 2)
        
        collector = get_metrics_collector()
        assert collector.get_counter("global_test") == 3
    
    def test_global_gauge(self):
        """Test global gauge functions."""
        set_gauge("global_gauge", 42.5)
        
        collector = get_metrics_collector()
        assert collector.get_gauge("global_gauge") == 42.5
    
    def test_global_histogram(self):
        """Test global histogram functions."""
        record_histogram("global_histogram", 100)
        record_histogram("global_histogram", 200)
        
        collector = get_metrics_collector()
        stats = collector.get_histogram_stats("global_histogram")
        assert stats["count"] == 2
    
    def test_global_timer(self):
        """Test global timer functions."""
        with start_timer("global_timer"):
            time.sleep(0.01)
        
        collector = get_metrics_collector()
        stats = collector.get_timer_stats("global_timer")
        assert stats["count"] == 1
    
    def test_global_health(self):
        """Test global health functions."""
        update_health("global_service", "healthy", "All good")
        
        status = get_health_status("global_service")
        assert status.component == "global_service"
        assert status.status == "healthy"
        assert status.message == "All good"
    
    def test_global_summary(self):
        """Test global metrics summary."""
        increment_counter("test")
        set_gauge("test_gauge", 10)
        
        summary = get_metrics_summary()
        assert "counters" in summary
        assert "gauges" in summary
        assert summary["counters"]["test"] == 1
        assert summary["gauges"]["test_gauge"] == 10
    
    def test_singleton_behavior(self):
        """Test that global collector is singleton."""
        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()
        
        assert collector1 is collector2
        
        collector1.increment_counter("singleton_test")
        assert collector2.get_counter("singleton_test") == 1