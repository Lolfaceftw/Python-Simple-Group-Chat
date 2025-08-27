"""
Client Performance Tests

Tests to validate client performance improvements including UI optimization,
update scheduling, and efficient rendering.
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch
from rich.console import Console

from chat_app.client.performance.ui_optimizer import UIOptimizer, UIConfig, RenderStats
from chat_app.client.performance.update_scheduler import UpdateScheduler, UpdateConfig, UpdatePriority
from chat_app.client.chat_client import ChatClient, ClientConfig
from chat_app.shared.models import ClientState, ConnectionStatus


class TestUIOptimizerPerformance:
    """Test UI optimizer performance improvements."""
    
    def test_ui_optimizer_initialization(self):
        """Test UI optimizer initializes correctly."""
        console = Console()
        config = UIConfig(
            target_fps=20,
            enable_frame_limiting=True,
            enable_content_caching=True
        )
        
        ui_optimizer = UIOptimizer(console, config)
        
        try:
            # Check initialization
            assert ui_optimizer.console == console
            assert ui_optimizer.config == config
            
            # Initialize layout
            layout = ui_optimizer.initialize_layout()
            assert layout is not None
            
            # Check initial stats
            stats = ui_optimizer.get_stats()
            assert isinstance(stats, RenderStats)
            assert stats.total_renders == 0
            assert stats.total_updates == 0
            
        finally:
            ui_optimizer.shutdown()
    
    def test_message_rendering_performance(self):
        """Test message rendering performance with optimization."""
        console = Console()
        config = UIConfig(
            target_fps=30,
            max_chat_lines=500,
            enable_content_caching=True,
            enable_partial_updates=True
        )
        
        ui_optimizer = UIOptimizer(console, config)
        
        try:
            # Initialize layout
            ui_optimizer.initialize_layout()
            
            # Test adding many messages
            start_time = time.time()
            
            for i in range(200):
                ui_optimizer.add_chat_message(
                    f"Performance test message {i} with some content to test rendering",
                    f"user_{i % 10}",
                    None
                )
            
            message_time = time.time() - start_time
            
            # Wait for processing
            time.sleep(1.0)
            
            # Check performance stats
            stats = ui_optimizer.get_stats()
            
            print(f"Added 200 messages in {message_time:.3f}s ({200/message_time:.1f} msg/s)")
            print(f"Total updates: {stats.total_updates}")
            print(f"Partial updates: {stats.partial_updates}")
            print(f"Cache hits: {stats.cache_hits}, misses: {stats.cache_misses}")
            
            # Performance assertions
            assert message_time < 2.0  # Should handle messages efficiently
            assert stats.total_updates > 0
            
            # Partial updates should be used for better performance
            if config.enable_partial_updates:
                assert stats.partial_updates > 0
            
            # Caching should improve performance
            if config.enable_content_caching:
                cache_hit_ratio = stats.cache_hits / (stats.cache_hits + stats.cache_misses) if (stats.cache_hits + stats.cache_misses) > 0 else 0
                print(f"Cache hit ratio: {cache_hit_ratio:.1%}")
            
        finally:
            ui_optimizer.shutdown()
    
    def test_user_list_update_performance(self):
        """Test user list update performance."""
        console = Console()
        config = UIConfig(
            target_fps=25,
            max_user_list_size=50,
            enable_content_caching=True
        )
        
        ui_optimizer = UIOptimizer(console, config)
        
        try:
            ui_optimizer.initialize_layout()
            
            # Test user list updates
            start_time = time.time()
            
            for i in range(100):
                # Vary user list size to test different scenarios
                user_count = (i % 20) + 1
                users = [f"user_{j}" for j in range(user_count)]
                ui_optimizer.update_user_list(users)
            
            update_time = time.time() - start_time
            
            # Wait for processing
            time.sleep(0.5)
            
            stats = ui_optimizer.get_stats()
            
            print(f"Updated user list 100 times in {update_time:.3f}s ({100/update_time:.1f} updates/s)")
            print(f"Total updates: {stats.total_updates}")
            
            # Performance assertions
            assert update_time < 1.0  # Should be very fast
            assert stats.total_updates > 0
            
        finally:
            ui_optimizer.shutdown()
    
    def test_frame_rate_limiting(self):
        """Test frame rate limiting functionality."""
        console = Console()
        config = UIConfig(
            target_fps=10,  # Low FPS for testing
            enable_frame_limiting=True
        )
        
        ui_optimizer = UIOptimizer(console, config)
        
        try:
            ui_optimizer.initialize_layout()
            
            # Rapidly add messages
            start_time = time.time()
            
            for i in range(50):
                ui_optimizer.add_chat_message(f"Message {i}", "test_user", None)
                ui_optimizer.force_refresh()  # Force immediate processing
            
            # Wait for processing
            time.sleep(2.0)
            
            processing_time = time.time() - start_time
            stats = ui_optimizer.get_stats()
            
            # Calculate actual FPS
            actual_fps = stats.current_fps
            
            print(f"Target FPS: {config.target_fps}")
            print(f"Actual FPS: {actual_fps:.1f}")
            print(f"Processing time: {processing_time:.2f}s")
            
            # Frame limiting should keep FPS close to target
            if config.enable_frame_limiting and actual_fps > 0:
                # Allow some variance but should be reasonably close
                assert actual_fps <= config.target_fps * 1.5
            
        finally:
            ui_optimizer.shutdown()


class TestUpdateSchedulerPerformance:
    """Test update scheduler performance."""
    
    def test_scheduler_initialization(self):
        """Test scheduler initializes correctly."""
        config = UpdateConfig(
            max_update_frequency_hz=30,
            worker_threads=2,
            enable_adaptive_scheduling=True
        )
        
        scheduler = UpdateScheduler(config)
        
        try:
            # Check initialization
            assert scheduler.config == config
            
            # Check initial stats
            stats = scheduler.get_stats()
            assert stats.total_scheduled == 0
            assert stats.total_executed == 0
            assert stats.current_queue_size == 0
            
        finally:
            scheduler.shutdown()
    
    def test_task_scheduling_performance(self):
        """Test task scheduling performance under load."""
        config = UpdateConfig(
            max_queue_size=500,
            worker_threads=3,
            enable_update_coalescing=True
        )
        
        scheduler = UpdateScheduler(config)
        
        try:
            executed_tasks = []
            
            def test_task(task_id: int) -> str:
                executed_tasks.append(task_id)
                time.sleep(0.005)  # Small delay to simulate work
                return f"completed_{task_id}"
            
            # Test scheduling performance
            start_time = time.time()
            
            for i in range(150):
                success = scheduler.schedule_update(
                    task_id=f"perf_task_{i}",
                    callback=test_task,
                    priority=UpdatePriority.NORMAL
                )
                assert success
            
            schedule_time = time.time() - start_time
            
            # Wait for execution
            time.sleep(3.0)
            
            stats = scheduler.get_stats()
            
            print(f"Scheduled 150 tasks in {schedule_time:.3f}s ({150/schedule_time:.1f} tasks/s)")
            print(f"Executed: {stats.total_executed}, Failed: {stats.total_failed}")
            print(f"Average execution time: {stats.average_execution_time:.3f}s")
            print(f"Worker utilization: {stats.worker_utilization:.1%}")
            
            # Performance assertions
            assert schedule_time < 1.0  # Scheduling should be very fast
            assert stats.total_scheduled == 150
            assert stats.total_executed > 0
            assert len(executed_tasks) > 0
            
        finally:
            scheduler.shutdown()
    
    def test_update_coalescing_efficiency(self):
        """Test update coalescing improves efficiency."""
        config = UpdateConfig(
            worker_threads=2,
            enable_update_coalescing=True
        )
        
        scheduler = UpdateScheduler(config)
        
        try:
            executed_updates = []
            
            def ui_update_task(update_type: str, data: str) -> None:
                executed_updates.append((update_type, data))
                time.sleep(0.01)
            
            # Schedule many updates with same coalesce key
            start_time = time.time()
            
            for i in range(50):
                scheduler.schedule_ui_update(
                    "chat_messages",
                    ui_update_task,
                    "chat_messages",
                    f"message_{i}"
                )
            
            # Wait for processing
            time.sleep(2.0)
            
            processing_time = time.time() - start_time
            stats = scheduler.get_stats()
            
            print(f"Scheduled 50 UI updates in {processing_time:.3f}s")
            print(f"Executed: {stats.total_executed}")
            print(f"Coalesced: {stats.total_coalesced}")
            print(f"Actual updates executed: {len(executed_updates)}")
            
            # Coalescing should reduce the number of actual executions
            if config.enable_update_coalescing:
                assert stats.total_coalesced > 0
                assert len(executed_updates) < 50  # Should be fewer than scheduled
            
        finally:
            scheduler.shutdown()
    
    def test_priority_handling_performance(self):
        """Test priority handling doesn't significantly impact performance."""
        config = UpdateConfig(
            worker_threads=2,
            max_queue_size=200
        )
        
        scheduler = UpdateScheduler(config)
        
        try:
            executed_priorities = []
            
            def priority_task(priority_name: str) -> None:
                executed_priorities.append(priority_name)
                time.sleep(0.005)
            
            # Schedule tasks with different priorities
            start_time = time.time()
            
            priorities = [
                (UpdatePriority.LOW, "low"),
                (UpdatePriority.NORMAL, "normal"),
                (UpdatePriority.HIGH, "high"),
                (UpdatePriority.CRITICAL, "critical")
            ]
            
            for i in range(40):  # 10 of each priority
                priority, name = priorities[i % 4]
                
                scheduler.schedule_update(
                    task_id=f"priority_task_{i}",
                    callback=priority_task,
                    priority_name=name,
                    priority=priority
                )
            
            schedule_time = time.time() - start_time
            
            # Wait for execution
            time.sleep(2.0)
            
            stats = scheduler.get_stats()
            
            print(f"Scheduled 40 priority tasks in {schedule_time:.3f}s")
            print(f"Executed: {stats.total_executed}")
            print(f"Priority distribution: {dict(zip(*zip(*[(p, executed_priorities.count(p)) for p in ['low', 'normal', 'high', 'critical']])))}")
            
            # Performance should still be good with priority handling
            assert schedule_time < 0.5
            assert stats.total_executed > 0
            
            # Higher priority tasks should be executed first
            if len(executed_priorities) > 10:
                # Check that critical tasks appear early in execution
                first_quarter = executed_priorities[:len(executed_priorities)//4]
                critical_count_early = first_quarter.count("critical")
                total_critical = executed_priorities.count("critical")
                
                if total_critical > 0:
                    critical_ratio_early = critical_count_early / total_critical
                    print(f"Critical tasks in first quarter: {critical_ratio_early:.1%}")
                    # Most critical tasks should be executed early
                    assert critical_ratio_early >= 0.5
            
        finally:
            scheduler.shutdown()


class TestClientPerformanceIntegration:
    """Test client performance with integrated optimizations."""
    
    @patch('chat_app.client.chat_client.Connection')
    @patch('chat_app.client.chat_client.ServiceDiscovery')
    def test_client_with_performance_optimizations(self, mock_discovery, mock_connection):
        """Test client performance with UI optimizer and update scheduler."""
        # Mock connection to avoid network operations
        mock_conn_instance = Mock()
        mock_connection.return_value = mock_conn_instance
        mock_conn_instance.connect.return_value = True
        mock_conn_instance.receive_messages.return_value = []
        
        config = ClientConfig(
            host="127.0.0.1",
            port=8080,
            username="test_user",
            ui_refresh_rate=20,
            max_message_history=500
        )
        
        client = ChatClient(config)
        
        try:
            # Check performance components are initialized
            assert client.ui_optimizer is not None
            assert client.update_scheduler is not None
            
            # Test UI optimizer configuration
            ui_stats = client.ui_optimizer.get_stats()
            assert isinstance(ui_stats, RenderStats)
            
            # Test update scheduler configuration
            scheduler_stats = client.update_scheduler.get_stats()
            assert scheduler_stats.total_scheduled == 0
            
            # Test performance-optimized UI updates
            start_time = time.time()
            
            # Simulate message updates
            for i in range(50):
                client._on_chat_message(f"Performance test message {i}")
            
            # Simulate user list updates
            for i in range(20):
                users = {f"user_{j}": f"User {j}" for j in range(i % 10 + 1)}
                client._on_user_list_update(users)
            
            update_time = time.time() - start_time
            
            # Wait for processing
            time.sleep(1.0)
            
            # Check performance metrics
            final_ui_stats = client.ui_optimizer.get_stats()
            final_scheduler_stats = client.update_scheduler.get_stats()
            
            print(f"Processed 50 messages + 20 user updates in {update_time:.3f}s")
            print(f"UI updates: {final_ui_stats.total_updates}")
            print(f"Scheduled tasks: {final_scheduler_stats.total_scheduled}")
            print(f"Executed tasks: {final_scheduler_stats.total_executed}")
            
            # Performance assertions
            assert update_time < 1.0  # Should handle updates quickly
            assert final_ui_stats.total_updates > 0
            assert final_scheduler_stats.total_scheduled > 0
            
        finally:
            client.shutdown()


@pytest.mark.performance
class TestClientPerformanceBenchmarks:
    """Performance benchmark tests for client optimizations."""
    
    def test_ui_rendering_benchmark(self):
        """Benchmark UI rendering performance."""
        console = Console()
        config = UIConfig(
            target_fps=60,
            max_chat_lines=1000,
            enable_content_caching=True,
            enable_partial_updates=True
        )
        
        ui_optimizer = UIOptimizer(console, config)
        
        try:
            ui_optimizer.initialize_layout()
            
            # Benchmark message rendering
            message_counts = [100, 250, 500, 1000]
            
            for count in message_counts:
                start_time = time.time()
                
                for i in range(count):
                    ui_optimizer.add_chat_message(
                        f"Benchmark message {i} with variable length content to test rendering performance",
                        f"user_{i % 15}",
                        None
                    )
                
                render_time = time.time() - start_time
                
                # Wait for processing
                time.sleep(1.0)
                
                stats = ui_optimizer.get_stats()
                throughput = count / render_time if render_time > 0 else 0
                
                print(f"Messages: {count}, Time: {render_time:.3f}s, "
                      f"Throughput: {throughput:.1f} msg/s, "
                      f"Cache hit ratio: {stats.cache_hits/(stats.cache_hits + stats.cache_misses):.1%}")
                
                # Performance targets
                assert throughput > 200  # Should handle at least 200 msg/s
                assert render_time < count * 0.005  # Should be much faster than 5ms per message
                
                # Clear for next test
                ui_optimizer.clear_chat_history()
        
        finally:
            ui_optimizer.shutdown()
    
    def test_update_scheduler_throughput_benchmark(self):
        """Benchmark update scheduler throughput."""
        config = UpdateConfig(
            max_queue_size=2000,
            worker_threads=4,
            enable_update_coalescing=True,
            enable_adaptive_scheduling=True
        )
        
        scheduler = UpdateScheduler(config)
        
        try:
            def benchmark_task(task_id: int) -> int:
                # Simulate mixed workload
                time.sleep(0.001)  # 1ms work simulation
                return task_id * 2
            
            # Test different load levels
            load_levels = [100, 300, 500, 1000]
            
            for load in load_levels:
                start_time = time.time()
                
                # Schedule tasks
                for i in range(load):
                    scheduler.schedule_update(
                        task_id=f"benchmark_{i}",
                        callback=benchmark_task,
                        priority=UpdatePriority.NORMAL
                    )
                
                schedule_time = time.time() - start_time
                
                # Wait for completion
                time.sleep(max(2.0, load * 0.002))  # Adaptive wait time
                
                stats = scheduler.get_stats()
                
                schedule_throughput = load / schedule_time if schedule_time > 0 else 0
                execution_throughput = stats.total_executed / (time.time() - start_time)
                
                print(f"Load: {load}, Schedule time: {schedule_time:.3f}s, "
                      f"Schedule throughput: {schedule_throughput:.1f} tasks/s, "
                      f"Execution throughput: {execution_throughput:.1f} tasks/s, "
                      f"Worker utilization: {stats.worker_utilization:.1%}")
                
                # Performance targets
                assert schedule_throughput > 1000  # Should schedule very quickly
                assert stats.total_executed > 0
                
                # Clear queue for next test
                scheduler.clear_queue()
        
        finally:
            scheduler.shutdown()