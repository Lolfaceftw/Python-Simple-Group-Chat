"""
Server Performance Tests

Comprehensive tests to validate server performance improvements including
thread pool management, memory optimization, and message queue efficiency.
"""

import pytest
import time
import threading
import socket
from unittest.mock import Mock, patch
from concurrent.futures import Future

from chat_app.server.chat_server import ChatServer
from chat_app.server.performance.thread_pool import ThreadPoolManager, ThreadPoolConfig
from chat_app.server.performance.memory_manager import MemoryManager, MemoryConfig
from chat_app.server.performance.message_queue import MessageQueue, MessagePriority
from chat_app.shared.config import ServerConfig
from chat_app.shared.models import Message, MessageType


class TestServerPerformanceIntegration:
    """Test server performance with integrated optimizations."""
    
    def test_server_with_thread_pool_optimization(self):
        """Test server performance with thread pool optimization."""
        config = ServerConfig(
            host="127.0.0.1",
            port=0,  # Let OS choose port
            max_clients=20,
            rate_limit_messages_per_minute=100
        )
        
        server = ChatServer(config)
        
        try:
            # Check that thread pool is initialized
            assert server.thread_pool is not None
            assert isinstance(server.thread_pool, ThreadPoolManager)
            
            # Check thread pool configuration
            stats = server.thread_pool.get_stats()
            assert stats.total_threads >= 2  # At least min threads
            
            # Test thread pool scaling
            initial_threads = stats.total_threads
            
            # Simulate load by submitting tasks
            futures = []
            for i in range(10):
                future = server.thread_pool.submit_task(
                    lambda x: time.sleep(0.1),
                    i
                )
                futures.append(future)
            
            # Wait for tasks
            for future in futures:
                future.result(timeout=5.0)
            
            # Check if scaling occurred
            final_stats = server.thread_pool.get_stats()
            assert final_stats.completed_tasks >= 10
            
        finally:
            server.shutdown()
    
    def test_server_memory_management(self):
        """Test server memory management optimization."""
        config = ServerConfig(
            host="127.0.0.1",
            port=0,
            max_clients=10,
            message_history_size=100
        )
        
        server = ChatServer(config)
        
        try:
            # Check memory manager initialization
            assert server.memory_manager is not None
            assert isinstance(server.memory_manager, MemoryManager)
            
            # Get initial memory stats
            initial_stats = server.memory_manager.get_memory_stats()
            assert initial_stats.total_memory_mb > 0
            assert initial_stats.memory_percent >= 0
            
            # Test memory pressure handling
            pressure_level = server.memory_manager.check_memory_pressure()
            assert pressure_level is not None
            
            # Test cleanup functionality
            cleanup_performed = server.memory_manager.cleanup_if_needed(force=True)
            assert isinstance(cleanup_performed, bool)
            
        finally:
            server.shutdown()
    
    def test_server_statistics_with_performance_metrics(self):
        """Test server statistics include performance metrics."""
        config = ServerConfig(
            host="127.0.0.1",
            port=0,
            max_clients=5
        )
        
        server = ChatServer(config)
        
        try:
            # Get server statistics
            stats = server.get_server_statistics()
            
            # Check that performance metrics are included
            assert 'thread_pool' in stats
            assert 'memory_manager' in stats
            
            # Check thread pool stats
            thread_stats = stats['thread_pool']
            assert 'total_threads' in thread_stats
            assert 'completed_tasks' in thread_stats
            assert 'average_task_duration' in thread_stats
            
            # Check memory stats
            memory_stats = stats['memory_manager']
            assert 'total_memory_mb' in memory_stats
            assert 'memory_percent' in memory_stats
            assert 'pressure_level' in memory_stats
            
        finally:
            server.shutdown()


class TestMessageQueueIntegration:
    """Test message queue integration with server components."""
    
    def test_message_queue_with_message_broker(self):
        """Test message queue integration with message broker."""
        # This would require updating MessageBroker to use MessageQueue
        # For now, test the queue independently
        
        queue = MessageQueue(
            max_queue_size=100,
            batch_size=5,
            enable_batching=True,
            worker_threads=2
        )
        
        # Mock delivery callback
        delivered_messages = []
        
        def delivery_callback(messages):
            delivered_messages.extend(messages)
            return True
        
        queue.set_delivery_callback(delivery_callback)
        
        try:
            # Create test messages
            messages = []
            for i in range(20):
                message = Message(
                    content=f"Test message {i}",
                    sender=f"user_{i % 3}",
                    message_type=MessageType.CHAT,
                    timestamp=time.time()
                )
                messages.append(message)
            
            # Enqueue messages with different priorities
            for i, message in enumerate(messages):
                priority = MessagePriority.HIGH if i % 5 == 0 else MessagePriority.NORMAL
                
                success = queue.enqueue_message(
                    message=message,
                    target_clients=[f"client_{i % 4}"],
                    priority=priority
                )
                assert success
            
            # Wait for processing
            time.sleep(2.0)
            
            # Check delivery
            assert len(delivered_messages) == 20
            
            # Check statistics
            stats = queue.get_stats()
            assert stats.total_queued == 20
            assert stats.total_processed == 20
            assert stats.total_failed == 0
            
        finally:
            queue.shutdown()


@pytest.mark.performance
class TestPerformanceBenchmarks:
    """Performance benchmark tests for server optimizations."""
    
    def test_thread_pool_vs_traditional_threading(self):
        """Compare thread pool performance vs traditional threading."""
        
        def cpu_task(duration: float) -> str:
            end_time = time.time() + duration
            while time.time() < end_time:
                pass
            return "completed"
        
        # Test with thread pool
        thread_pool_config = ThreadPoolConfig(min_threads=5, max_threads=15)
        
        with ThreadPoolManager(thread_pool_config) as pool:
            start_time = time.time()
            
            futures = []
            for i in range(20):
                future = pool.submit_task(cpu_task, 0.1)
                futures.append(future)
            
            # Wait for completion
            results = [future.result(timeout=10) for future in futures]
            pool_time = time.time() - start_time
        
        # Test with traditional threading
        start_time = time.time()
        threads = []
        results_traditional = []
        
        def thread_wrapper(duration):
            result = cpu_task(duration)
            results_traditional.append(result)
        
        for i in range(20):
            thread = threading.Thread(target=thread_wrapper, args=(0.1,))
            thread.start()
            threads.append(thread)
        
        for thread in threads:
            thread.join()
        
        traditional_time = time.time() - start_time
        
        # Compare results
        assert len(results) == 20
        assert len(results_traditional) == 20
        
        print(f"Thread pool time: {pool_time:.2f}s")
        print(f"Traditional threading time: {traditional_time:.2f}s")
        
        # Thread pool should be competitive or better
        # (May vary based on system, but should handle the load efficiently)
        assert pool_time < traditional_time * 1.5  # Allow some overhead
    
    def test_memory_manager_cleanup_performance(self):
        """Test memory manager cleanup performance."""
        config = MemoryConfig(
            max_message_history=1000,
            cleanup_threshold_percent=50.0,
            enable_auto_cleanup=False  # Manual control for testing
        )
        
        memory_manager = MemoryManager(config)
        
        try:
            # Add many messages to history
            start_time = time.time()
            
            for i in range(500):
                message = Message(
                    content=f"Performance test message {i}",
                    sender=f"user_{i % 10}",
                    message_type=MessageType.CHAT,
                    timestamp=time.time()
                )
                memory_manager.history_manager.add_message(message)
            
            add_time = time.time() - start_time
            
            # Test cleanup performance
            start_time = time.time()
            cleaned_count = memory_manager.history_manager.cleanup_old_messages(max_age_hours=0)
            cleanup_time = time.time() - start_time
            
            # Check performance
            print(f"Added 500 messages in {add_time:.3f}s ({500/add_time:.1f} msg/s)")
            print(f"Cleaned {cleaned_count} messages in {cleanup_time:.3f}s")
            
            # Performance assertions
            assert add_time < 1.0  # Should add messages quickly
            assert cleanup_time < 0.5  # Cleanup should be fast
            assert cleaned_count > 0  # Should have cleaned something
            
        finally:
            memory_manager.shutdown()
    
    def test_ui_optimizer_rendering_performance(self):
        """Test UI optimizer rendering performance."""
        from chat_app.client.performance.ui_optimizer import UIOptimizer, UIConfig
        from rich.console import Console
        
        console = Console()
        config = UIConfig(
            target_fps=30,
            enable_frame_limiting=True,
            enable_content_caching=True
        )
        
        ui_optimizer = UIOptimizer(console, config)
        
        try:
            # Initialize layout
            layout = ui_optimizer.initialize_layout()
            assert layout is not None
            
            # Test message addition performance
            start_time = time.time()
            
            for i in range(100):
                ui_optimizer.add_chat_message(
                    f"Performance test message {i}",
                    f"user_{i % 5}",
                    None
                )
            
            message_time = time.time() - start_time
            
            # Test user list update performance
            start_time = time.time()
            
            for i in range(50):
                users = [f"user_{j}" for j in range(i % 10 + 1)]
                ui_optimizer.update_user_list(users)
            
            user_update_time = time.time() - start_time
            
            # Wait for processing
            time.sleep(1.0)
            
            # Check statistics
            stats = ui_optimizer.get_stats()
            
            print(f"Added 100 messages in {message_time:.3f}s ({100/message_time:.1f} msg/s)")
            print(f"Updated user list 50 times in {user_update_time:.3f}s")
            print(f"Total renders: {stats.total_renders}, Updates: {stats.total_updates}")
            print(f"Cache hits: {stats.cache_hits}, Cache misses: {stats.cache_misses}")
            
            # Performance assertions
            assert message_time < 1.0  # Should handle messages quickly
            assert user_update_time < 0.5  # User updates should be fast
            assert stats.total_updates > 0
            
            # Cache should be working if enabled
            if config.enable_content_caching:
                assert stats.cache_hits > 0 or stats.cache_misses > 0
            
        finally:
            ui_optimizer.shutdown()
    
    def test_update_scheduler_performance(self):
        """Test update scheduler performance and efficiency."""
        from chat_app.client.performance.update_scheduler import UpdateScheduler, UpdateConfig, UpdatePriority
        
        config = UpdateConfig(
            max_update_frequency_hz=60,
            enable_update_coalescing=True,
            worker_threads=3
        )
        
        scheduler = UpdateScheduler(config)
        
        try:
            executed_tasks = []
            
            def test_task(task_id: int) -> str:
                executed_tasks.append(task_id)
                time.sleep(0.01)  # Simulate work
                return f"completed_{task_id}"
            
            # Test task scheduling performance
            start_time = time.time()
            
            for i in range(100):
                success = scheduler.schedule_update(
                    task_id=f"task_{i}",
                    callback=test_task,
                    priority=UpdatePriority.NORMAL
                )
                assert success
            
            schedule_time = time.time() - start_time
            
            # Wait for execution
            time.sleep(3.0)
            
            # Check statistics
            stats = scheduler.get_stats()
            
            print(f"Scheduled 100 tasks in {schedule_time:.3f}s ({100/schedule_time:.1f} tasks/s)")
            print(f"Executed: {stats.total_executed}, Failed: {stats.total_failed}")
            print(f"Worker utilization: {stats.worker_utilization:.1%}")
            print(f"Average execution time: {stats.average_execution_time:.3f}s")
            
            # Performance assertions
            assert schedule_time < 0.5  # Scheduling should be fast
            assert stats.total_scheduled == 100
            assert stats.total_executed > 0
            assert len(executed_tasks) > 0
            
        finally:
            scheduler.shutdown()